"""Realtime, colour-coded log console widget.

Subscribes to the :class:`AppLogger` through a thread-safe queue and renders
records with per-level colours on the Tk main thread. Supports auto-scroll,
clear and save-to-file.
"""
from __future__ import annotations

import datetime as _dt
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Optional

import customtkinter as ctk

from gui.theme import LEVEL_COLORS, MONO_FONT
from utils.logger import AppLogger, LogRecord, QueueLogSink


class LogConsole(ctk.CTkFrame):
    """A scrolling text box that displays coloured log records."""

    def __init__(self, master: tk.Misc, logger: AppLogger, auto_scroll: bool = True) -> None:
        super().__init__(master, fg_color="transparent")
        self._logger = logger
        self._sink = QueueLogSink()
        self._auto_scroll = tk.BooleanVar(value=auto_scroll)

        self._build()
        # tk.Text gives us per-line colour tags that CTkTextbox exposes underneath.
        for level, color in LEVEL_COLORS.items():
            self._text._textbox.tag_config(level, foreground=color)

        logger.subscribe(self._sink, replay=True)
        self._poll()

    # -- construction ----------------------------------------------------
    def _build(self) -> None:
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", padx=4, pady=(0, 6))

        ctk.CTkCheckBox(
            toolbar, text="Auto Scroll", variable=self._auto_scroll, onvalue=True, offvalue=False
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(toolbar, text="Save Log", width=90, command=self._save).pack(side="right", padx=4)
        ctk.CTkButton(
            toolbar, text="Clear Log", width=90, fg_color="#dc2626", hover_color="#b91c1c",
            command=self._clear,
        ).pack(side="right", padx=4)

        self._text = ctk.CTkTextbox(self, font=MONO_FONT, wrap="word")
        self._text.pack(fill="both", expand=True, padx=4)
        self._text.configure(state="disabled")

    # -- log pump --------------------------------------------------------
    def _poll(self) -> None:
        for record in self._sink.drain():
            self._append(record)
        self.after(120, self._poll)

    def _append(self, record: LogRecord) -> None:
        self._text.configure(state="normal")
        self._text._textbox.insert("end", record.formatted() + "\n", record.level.value)
        self._text.configure(state="disabled")
        if self._auto_scroll.get():
            self._text.see("end")

    def set_auto_scroll(self, value: bool) -> None:
        self._auto_scroll.set(value)

    # -- actions ---------------------------------------------------------
    def _clear(self) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")
        self._logger.clear()

    def _save(self) -> None:
        default = f"capcut_log_{_dt.datetime.now():%Y%m%d_%H%M%S}.txt"
        path: Optional[str] = filedialog.asksaveasfilename(
            title="Save Log",
            defaultextension=".txt",
            initialfile=default,
            filetypes=[("Text", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            Path(path).write_text(
                "\n".join(r.formatted() for r in self._logger.history()), encoding="utf-8"
            )
        except OSError as exc:
            messagebox.showerror("Save Log", f"Could not save log:\n{exc}")
