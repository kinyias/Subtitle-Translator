"""Reusable progress card: a title, an indeterminate bar and a state line."""
from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from gui.theme import STATUS_COLORS


class ProgressCard(ctk.CTkFrame):
    """Shows task progress with an indeterminate animated bar.

    The backend calls are single blocking requests with no incremental
    progress, so an indeterminate bar communicates "working" honestly rather
    than faking a percentage.
    """

    def __init__(self, master: tk.Misc, title: str = "Progress") -> None:
        super().__init__(master, corner_radius=10)

        ctk.CTkLabel(self, text=title, font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=14, pady=(12, 6)
        )
        self._bar = ctk.CTkProgressBar(self, mode="indeterminate")
        self._bar.pack(fill="x", padx=14)
        self._bar.set(0)

        self._status = ctk.CTkLabel(self, text="Idle", text_color="#9ca3af")
        self._status.pack(anchor="w", padx=14, pady=(6, 12))

    def start(self, message: str = "Running ...") -> None:
        self._bar.configure(mode="indeterminate")
        self._bar.start()
        self._status.configure(text=message, text_color=STATUS_COLORS["Running"])

    def finish(self, success: bool, message: str) -> None:
        self._bar.stop()
        self._bar.configure(mode="determinate")
        self._bar.set(1 if success else 0)
        key = "Completed" if success else "Failed"
        self._status.configure(text=message, text_color=STATUS_COLORS[key])

    def reset(self) -> None:
        self._bar.stop()
        self._bar.configure(mode="determinate")
        self._bar.set(0)
        self._status.configure(text="Idle", text_color="#9ca3af")
