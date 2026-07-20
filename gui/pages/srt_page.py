"""SRT page: load an existing .srt, AI-translate it, preview, then export.

Workflow:
  1. Pick an existing ``.srt`` file - it is parsed into cues immediately.
  2. Configure the AI translation endpoint (URL, key, model, target language and
     a style prompt) - the same settings the Subtitle page uses, persisted to
     config.json so both pages share one configuration.
  3. Translate: the text of each cue is rewritten in the background.
  4. Preview the result, then Export to a new ``.srt`` file.

Only the *text* of each cue is translated; timings are copied straight from the
source file, so the exported SRT keeps its original timeframe.
"""
from __future__ import annotations

import tkinter as tk
from typing import List, Optional

import customtkinter as ctk

from gui.pages.base_page import BasePage
from gui.widgets.path_row import PathRow
from gui.widgets.progress_card import ProgressCard
from services.pipeline import SubtitleEntry, SubtitleResult
from services.srt import entries_to_srt, read_srt, write_srt
from services.translator import TranslatorConfig
from workers.base_worker import WorkerCallbacks

_SRT_TYPES = [("SubRip subtitle", "*.srt"), ("All files", "*.*")]


class SrtPage(BasePage):
    title = "SRT Translator"
    subtitle = "Load an existing .srt, translate with AI, preview, then export."

    def __init__(self, master, context, set_status) -> None:
        self._entries: List[SubtitleEntry] = []
        self._last_translated = False
        super().__init__(master, context, set_status)

    # -- construction ----------------------------------------------------
    def build(self) -> None:
        self._build_io()
        self._build_translation()
        self._build_actions()
        self._progress = ProgressCard(self.body, title="Progress")
        self._progress.pack(fill="x", pady=(0, 12))
        self._build_preview()

    def _build_io(self) -> None:
        card = ctk.CTkFrame(self.body, corner_radius=10)
        card.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(card, text="Input", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=14, pady=(12, 6)
        )
        self._input_path = PathRow(
            card, "Input .srt file", mode="open", filetypes=_SRT_TYPES,
            on_pick=self._on_pick_file,
        )
        self._input_path.pack(fill="x", padx=14, pady=(0, 12))

    def _build_translation(self) -> None:
        cfg = self.context.config.config
        card = ctk.CTkFrame(self.body, corner_radius=10)
        card.pack(fill="x", pady=(0, 12))
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card, text="AI Translation", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 6)
        )

        fields = ctk.CTkFrame(card, fg_color="transparent")
        fields.grid(row=1, column=0, columnspan=2, sticky="ew", padx=0, pady=(0, 8))
        fields.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(fields, text="Endpoint URL", font=("Segoe UI", 13)).grid(
            row=0, column=0, sticky="w", padx=14, pady=6
        )
        self._ai_url = ctk.CTkEntry(fields, placeholder_text="http://localhost:20128/v1/chat/completions")
        self._ai_url.grid(row=0, column=1, sticky="ew", padx=14, pady=6)
        self._ai_url.insert(0, cfg.ai_base_url)

        ctk.CTkLabel(fields, text="API Key", font=("Segoe UI", 13)).grid(
            row=1, column=0, sticky="w", padx=14, pady=6
        )
        self._ai_key = ctk.CTkEntry(fields, show="*", placeholder_text="sk-...")
        self._ai_key.grid(row=1, column=1, sticky="ew", padx=14, pady=6)
        self._ai_key.insert(0, cfg.ai_api_key)

        ctk.CTkLabel(fields, text="Model", font=("Segoe UI", 13)).grid(
            row=2, column=0, sticky="w", padx=14, pady=6
        )
        self._ai_model = ctk.CTkEntry(fields, placeholder_text="openai/gpt-5")
        self._ai_model.grid(row=2, column=1, sticky="ew", padx=14, pady=6)
        self._ai_model.insert(0, cfg.ai_model)

        ctk.CTkLabel(fields, text="Target Language", font=("Segoe UI", 13)).grid(
            row=3, column=0, sticky="w", padx=14, pady=6
        )
        self._ai_target = ctk.CTkEntry(fields, placeholder_text="Vietnamese")
        self._ai_target.grid(row=3, column=1, sticky="ew", padx=14, pady=6)
        self._ai_target.insert(0, cfg.ai_target_language)

        ctk.CTkLabel(fields, text="Style Prompt", font=("Segoe UI", 13)).grid(
            row=4, column=0, sticky="nw", padx=14, pady=6
        )
        self._ai_prompt = ctk.CTkTextbox(fields, height=90, wrap="word")
        self._ai_prompt.grid(row=4, column=1, sticky="ew", padx=14, pady=6)
        if cfg.ai_style_prompt:
            self._ai_prompt.insert("1.0", cfg.ai_style_prompt)

    def _build_actions(self) -> None:
        actions = ctk.CTkFrame(self.body, fg_color="transparent")
        actions.pack(fill="x", pady=(0, 12))
        self._translate_btn = ctk.CTkButton(
            actions, text="Translate", width=180, command=self._translate
        )
        self._translate_btn.pack(side="left", padx=(0, 8))
        self._export_btn = ctk.CTkButton(
            actions, text="Export SRT", width=140, state="disabled",
            fg_color="#16a34a", hover_color="#15803d", command=self._export,
        )
        self._export_btn.pack(side="left", padx=8)
        ctk.CTkButton(
            actions, text="Clear", width=100, fg_color="#374151", hover_color="#4b5563",
            command=self._clear,
        ).pack(side="left", padx=8)

    def _build_preview(self) -> None:
        card = ctk.CTkFrame(self.body, corner_radius=10)
        card.pack(fill="both", expand=True)
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(head, text="Preview", font=("Segoe UI", 14, "bold")).pack(side="left")
        self._preview_count = ctk.CTkLabel(head, text="", font=("Segoe UI", 12), text_color="#9ca3af")
        self._preview_count.pack(side="left", padx=10)
        self._preview = ctk.CTkTextbox(card, height=240, wrap="word", font=("Consolas", 12))
        self._preview.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        self._preview.configure(state="disabled")

    # -- behavior --------------------------------------------------------
    def _on_pick_file(self, path: str) -> None:
        """Parse the chosen file right away so the user sees it before translating."""
        try:
            self._entries = read_srt(path)
        except Exception as exc:  # ServiceError / OSError
            self._entries = []
            self._export_btn.configure(state="disabled")
            self.show_error("Could not read SRT", exc)
            return
        self._last_translated = False
        self._render_preview()
        self._export_btn.configure(state="normal")
        self.status("Loaded", f"{len(self._entries)} cue(s) loaded")
        self.context.logger.info(f"Loaded {len(self._entries)} cue(s) from {path}.")

    def _translator_config(self) -> TranslatorConfig:
        return TranslatorConfig(
            base_url=self._ai_url.get().strip(),
            api_key=self._ai_key.get().strip(),
            model=self._ai_model.get().strip(),
            target_language=self._ai_target.get().strip() or "Vietnamese",
            style_prompt=self._ai_prompt.get("1.0", "end").strip(),
        )

    def _persist_settings(self) -> None:
        cfg = self.context.config.config
        cfg.ai_base_url = self._ai_url.get().strip()
        cfg.ai_api_key = self._ai_key.get().strip()
        cfg.ai_model = self._ai_model.get().strip()
        cfg.ai_target_language = self._ai_target.get().strip()
        cfg.ai_style_prompt = self._ai_prompt.get("1.0", "end").strip()
        self.context.config.save()

    def _translate(self) -> None:
        if not self._entries:
            self.show_warning("SRT", "Please choose an input .srt file first.")
            return
        config = self._translator_config()
        if not config.base_url:
            self.show_warning("SRT", "Please enter the AI endpoint URL.")
            return
        if not config.model:
            self.show_warning("SRT", "Please enter the AI model name.")
            return
        self._persist_settings()

        callbacks: WorkerCallbacks[SubtitleResult] = WorkerCallbacks(
            on_start=lambda: self._set_running(True),
            on_success=self._on_success,
            on_error=self._on_error,
            on_done=lambda: self._set_running(False),
        )
        self.context.logger.info("SRT translation started.")
        self.context.pipeline.translate_entries(self._entries, config, callbacks)

    def _set_running(self, running: bool) -> None:
        self._translate_btn.configure(state="disabled" if running else "normal")
        if running:
            self._export_btn.configure(state="disabled")
            self._progress.start("Translating subtitles in the background ...")
            self.status("Running", "SRT translation in progress")

    def _on_success(self, result: SubtitleResult) -> None:
        self._entries = result.entries
        self._last_translated = result.translated
        self._render_preview()
        self._export_btn.configure(state="normal")
        self._progress.finish(True, f"Done: {result.detail}")
        self.status("Completed", result.detail)
        self.context.logger.success(f"SRT translation complete ({result.detail}).")

    def _on_error(self, exc: BaseException) -> None:
        self._progress.finish(False, "Failed")
        self.status("Failed", str(exc))
        # Loaded cues are still exportable, so re-enable export on failure.
        if self._entries:
            self._export_btn.configure(state="normal")
        self.show_error("SRT translation failed", exc)

    def _render_preview(self) -> None:
        srt = entries_to_srt(self._entries, self._last_translated)
        self._preview.configure(state="normal")
        self._preview.delete("1.0", "end")
        self._preview.insert("1.0", srt)
        self._preview.configure(state="disabled")
        kind = "translated" if self._last_translated else "source"
        self._preview_count.configure(text=f"{len(self._entries)} cue(s) - {kind}")

    def _export(self) -> None:
        if not self._entries:
            self.show_warning("SRT", "Nothing to export yet.")
            return
        from tkinter import filedialog

        path = filedialog.asksaveasfilename(
            title="Export SRT", defaultextension=".srt",
            initialfile="translated.srt", filetypes=_SRT_TYPES,
        )
        if not path:
            return
        try:
            count = write_srt(path, self._entries, self._last_translated)
        except OSError as exc:
            self.show_error("Export failed", exc)
            return
        self.status("Completed", f"Exported {count} cue(s)")
        self.context.logger.success(f"Exported {count} subtitle(s) to {path}.")

    def _clear(self) -> None:
        self._entries = []
        self._last_translated = False
        self._input_path.set_path("")
        self._preview.configure(state="normal")
        self._preview.delete("1.0", "end")
        self._preview.configure(state="disabled")
        self._preview_count.configure(text="")
        self._export_btn.configure(state="disabled")
        self._progress.reset()
        self.status("Ready")
