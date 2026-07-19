"""Subtitle page: recognize audio, optionally AI-translate, preview, export.

Workflow:
  1. Pick an input audio/video file.
  2. Choose the recognition language.
  3. Optionally enable AI translation - this reveals endpoint URL, API key,
     target language and a style-prompt textarea (all persisted to config.json).
  4. Generate: upload -> recognize -> poll -> (translate) runs in the background.
  5. Preview the resulting subtitles, then Export to a ``.srt`` file.

Translation only rewrites the *text* of each cue; timings are preserved, so the
exported SRT keeps CapCut's original timeframe.
"""
from __future__ import annotations

import tkinter as tk
from typing import List, Optional

import customtkinter as ctk

from gui.pages.base_page import BasePage
from gui.widgets.path_row import PathRow
from gui.widgets.progress_card import ProgressCard
from services.pipeline import SubtitleEntry, SubtitleResult
from services.srt import entries_to_srt, write_srt
from services.results import ms_to_timestamp
from services.translator import TranslatorConfig
from workers.base_worker import WorkerCallbacks

_AUDIO_TYPES = [
    ("Audio/Video", "*.mp3 *.m4a *.wav *.aac *.flac *.ogg *.mp4 *.mov *.mkv"),
    ("All files", "*.*"),
]
_SRT_TYPES = [("SubRip subtitle", "*.srt"), ("All files", "*.*")]

_PROMPT_PLACEHOLDER = (
    "e.g. Natural, conversational Vietnamese. Keep names untranslated. "
    "Use informal tone for dialogue."
)


class SubtitlePage(BasePage):
    title = "Subtitle Translator"
    subtitle = "Recognize speech, translate with AI, preview, then export SRT."

    def __init__(self, master, context, set_status) -> None:
        self._entries: List[SubtitleEntry] = []
        self._last_translated = False
        super().__init__(master, context, set_status)

    # -- construction ----------------------------------------------------
    def build(self) -> None:
        self._build_io()
        self._build_recognition()
        self._build_translation()
        self._build_actions()
        self._progress = ProgressCard(self.body, title="Progress")
        self._progress.pack(fill="x", pady=(0, 12))
        self._build_preview()
        self._toggle_translation_fields()

    def _build_io(self) -> None:
        card = ctk.CTkFrame(self.body, corner_radius=10)
        card.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(card, text="Input", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=14, pady=(12, 6)
        )
        self._input_path = PathRow(card, "Input audio file", mode="open", filetypes=_AUDIO_TYPES)
        self._input_path.pack(fill="x", padx=14, pady=(0, 12))

    def _build_recognition(self) -> None:
        card = ctk.CTkFrame(self.body, corner_radius=10)
        card.pack(fill="x", pady=(0, 12))
        card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(card, text="Recognition", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 6)
        )
        ctk.CTkLabel(card, text="Language", font=("Segoe UI", 13)).grid(
            row=1, column=0, sticky="w", padx=14, pady=(0, 12)
        )
        self._language = ctk.CTkEntry(card)
        self._language.grid(row=1, column=1, sticky="ew", padx=14, pady=(0, 12))
        self._language.insert(0, self.context.config.config.default_language)

    def _build_translation(self) -> None:
        cfg = self.context.config.config
        card = ctk.CTkFrame(self.body, corner_radius=10)
        card.pack(fill="x", pady=(0, 12))
        card.grid_columnconfigure(1, weight=1)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(12, 4))
        ctk.CTkLabel(header, text="AI Translation", font=("Segoe UI", 14, "bold")).pack(side="left")

        self._use_translation = tk.BooleanVar(value=cfg.use_translation)
        ctk.CTkSwitch(
            header, text="Use Translation", variable=self._use_translation,
            onvalue=True, offvalue=False, command=self._toggle_translation_fields,
        ).pack(side="right")

        # Container for the fields revealed only when translation is enabled.
        self._ai_fields = ctk.CTkFrame(card, fg_color="transparent")
        self._ai_fields.grid(row=1, column=0, columnspan=2, sticky="ew", padx=0, pady=(0, 8))
        self._ai_fields.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self._ai_fields, text="Endpoint URL", font=("Segoe UI", 13)).grid(
            row=0, column=0, sticky="w", padx=14, pady=6
        )
        self._ai_url = ctk.CTkEntry(self._ai_fields, placeholder_text="http://localhost:20128/v1/chat/completions")
        self._ai_url.grid(row=0, column=1, sticky="ew", padx=14, pady=6)
        self._ai_url.insert(0, cfg.ai_base_url)

        ctk.CTkLabel(self._ai_fields, text="API Key", font=("Segoe UI", 13)).grid(
            row=1, column=0, sticky="w", padx=14, pady=6
        )
        self._ai_key = ctk.CTkEntry(self._ai_fields, show="*", placeholder_text="sk-...")
        self._ai_key.grid(row=1, column=1, sticky="ew", padx=14, pady=6)
        self._ai_key.insert(0, cfg.ai_api_key)

        ctk.CTkLabel(self._ai_fields, text="Model", font=("Segoe UI", 13)).grid(
            row=2, column=0, sticky="w", padx=14, pady=6
        )
        self._ai_model = ctk.CTkEntry(self._ai_fields, placeholder_text="openai/gpt-5")
        self._ai_model.grid(row=2, column=1, sticky="ew", padx=14, pady=6)
        self._ai_model.insert(0, cfg.ai_model)

        ctk.CTkLabel(self._ai_fields, text="Target Language", font=("Segoe UI", 13)).grid(
            row=3, column=0, sticky="w", padx=14, pady=6
        )
        self._ai_target = ctk.CTkEntry(self._ai_fields, placeholder_text="Vietnamese")
        self._ai_target.grid(row=3, column=1, sticky="ew", padx=14, pady=6)
        self._ai_target.insert(0, cfg.ai_target_language)

        ctk.CTkLabel(self._ai_fields, text="Style Prompt", font=("Segoe UI", 13)).grid(
            row=4, column=0, sticky="nw", padx=14, pady=6
        )
        self._ai_prompt = ctk.CTkTextbox(self._ai_fields, height=90, wrap="word")
        self._ai_prompt.grid(row=4, column=1, sticky="ew", padx=14, pady=6)
        if cfg.ai_style_prompt:
            self._ai_prompt.insert("1.0", cfg.ai_style_prompt)

    def _build_actions(self) -> None:
        actions = ctk.CTkFrame(self.body, fg_color="transparent")
        actions.pack(fill="x", pady=(0, 12))
        self._generate_btn = ctk.CTkButton(
            actions, text="Generate Subtitles", width=180, command=self._generate
        )
        self._generate_btn.pack(side="left", padx=(0, 8))
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
    def _toggle_translation_fields(self) -> None:
        if self._use_translation.get():
            self._ai_fields.grid()
        else:
            self._ai_fields.grid_remove()

    def _translator_config(self) -> Optional[TranslatorConfig]:
        if not self._use_translation.get():
            return None
        return TranslatorConfig(
            base_url=self._ai_url.get().strip(),
            api_key=self._ai_key.get().strip(),
            model=self._ai_model.get().strip(),
            target_language=self._ai_target.get().strip() or "Vietnamese",
            style_prompt=self._ai_prompt.get("1.0", "end").strip(),
        )

    def _persist_settings(self) -> None:
        cfg = self.context.config.config
        cfg.default_language = self._language.get().strip() or cfg.default_language
        cfg.use_translation = self._use_translation.get()
        cfg.ai_base_url = self._ai_url.get().strip()
        cfg.ai_api_key = self._ai_key.get().strip()
        cfg.ai_model = self._ai_model.get().strip()
        cfg.ai_target_language = self._ai_target.get().strip()
        cfg.ai_style_prompt = self._ai_prompt.get("1.0", "end").strip()
        self.context.config.save()

    def _generate(self) -> None:
        audio = self._input_path.get_path()
        if not audio:
            self.show_warning("Subtitle", "Please choose an input audio file.")
            return
        translator_config = self._translator_config()
        if translator_config is not None:
            if not translator_config.base_url:
                self.show_warning("Subtitle", "Please enter the AI endpoint URL.")
                return
            if not translator_config.model:
                self.show_warning("Subtitle", "Please enter the AI model name.")
                return
        self._persist_settings()

        callbacks: WorkerCallbacks[SubtitleResult] = WorkerCallbacks(
            on_start=lambda: self._set_running(True),
            on_success=self._on_success,
            on_error=self._on_error,
            on_done=lambda: self._set_running(False),
        )
        self.context.logger.info("Subtitle pipeline started.")
        self.context.pipeline.run(
            audio,
            self.context.config.resolve_device(),
            self.context.device_json_path(),
            self._language.get().strip() or "vi-VN",
            self._use_translation.get(),
            translator_config,
            callbacks,
        )

    def _set_running(self, running: bool) -> None:
        self._generate_btn.configure(state="disabled" if running else "normal")
        if running:
            self._export_btn.configure(state="disabled")
            self._progress.start("Uploading, recognizing and translating in the background ...")
            self.status("Running", "Subtitle pipeline in progress")

    def _on_success(self, result: SubtitleResult) -> None:
        self._entries = result.entries
        self._last_translated = result.translated
        self._render_preview()
        self._export_btn.configure(state="normal")
        self._progress.finish(True, f"Done: {result.detail}")
        self.status("Completed", result.detail)
        self.context.logger.success(f"Subtitle pipeline complete ({result.detail}).")

    def _on_error(self, exc: BaseException) -> None:
        self._progress.finish(False, "Failed")
        self.status("Failed", str(exc))
        self.show_error("Subtitle pipeline failed", exc)

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
            self.show_warning("Subtitle", "Nothing to export yet.")
            return
        from tkinter import filedialog

        path = filedialog.asksaveasfilename(
            title="Export SRT", defaultextension=".srt",
            initialfile="subtitles.srt", filetypes=_SRT_TYPES,
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
        self._preview.configure(state="normal")
        self._preview.delete("1.0", "end")
        self._preview.configure(state="disabled")
        self._preview_count.configure(text="")
        self._export_btn.configure(state="disabled")
        self._progress.reset()
        self.status("Ready")
