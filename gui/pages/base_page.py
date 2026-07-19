"""Base class for all content pages."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import Callable

import customtkinter as ctk

from gui.context import AppContext
from gui.theme import SUBTITLE_FONT, TITLE_FONT


class BasePage(ctk.CTkFrame):
    """Common scaffolding shared by every page."""

    title: str = "Page"
    subtitle: str = ""

    def __init__(self, master: tk.Misc, context: AppContext, set_status: Callable[[str, str], None]) -> None:
        super().__init__(master, fg_color="transparent")
        self.context = context
        self._set_status = set_status

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(20, 4))
        ctk.CTkLabel(header, text=self.title, font=TITLE_FONT).pack(anchor="w")
        if self.subtitle:
            ctk.CTkLabel(header, text=self.subtitle, font=SUBTITLE_FONT, text_color="#9ca3af").pack(
                anchor="w", pady=(2, 0)
            )

        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=16, pady=8)

        self.build()

    def build(self) -> None:  # pragma: no cover - overridden by subclasses
        raise NotImplementedError

    def on_show(self) -> None:
        """Called each time the page becomes visible. Override as needed."""

    # -- shared helpers --------------------------------------------------
    def status(self, state: str, detail: str = "") -> None:
        self._set_status(state, detail)

    def show_error(self, title: str, exc: BaseException) -> None:
        self.context.logger.exception(title, exc if isinstance(exc, BaseException) else Exception(str(exc)))
        messagebox.showerror(title, str(exc))

    def show_warning(self, title: str, message: str) -> None:
        self.context.logger.warning(f"{title}: {message}")
        messagebox.showwarning(title, message)
