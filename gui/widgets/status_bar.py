"""Bottom status bar showing the current application state."""
from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from gui.theme import STATUS_COLORS


class StatusBar(ctk.CTkFrame):
    """Displays a coloured state dot, a state label and a detail message."""

    STATES = ("Ready", "Running", "Completed", "Failed")

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, height=32, corner_radius=0)
        self.pack_propagate(False)

        self._dot = ctk.CTkLabel(self, text="●", font=("Segoe UI", 16))
        self._dot.pack(side="left", padx=(12, 4))

        self._state = ctk.CTkLabel(self, text="Ready", font=("Segoe UI", 12, "bold"))
        self._state.pack(side="left")

        self._detail = ctk.CTkLabel(self, text="", font=("Segoe UI", 12), text_color="#9ca3af")
        self._detail.pack(side="left", padx=12)

        self.set_state("Ready")

    def set_state(self, state: str, detail: str = "") -> None:
        color = STATUS_COLORS.get(state, "#9ca3af")
        self._dot.configure(text_color=color)
        self._state.configure(text=state, text_color=color)
        self._detail.configure(text=detail)
