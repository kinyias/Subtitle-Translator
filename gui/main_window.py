"""Main application window: sidebar + content area + status bar."""
from __future__ import annotations

import tkinter as tk
from typing import Dict, Optional

import customtkinter as ctk

from gui.context import AppContext
from gui.pages.base_page import BasePage
from gui.pages.logs_page import LogsPage
from gui.pages.settings_page import SettingsPage
from gui.pages.subtitle_page import SubtitlePage
from gui.widgets.status_bar import StatusBar

NAV_ITEMS = ["Subtitle", "Settings", "Logs"]


class MainWindow(ctk.CTkFrame):
    """The root layout hosted inside the application root window."""

    def __init__(self, master: tk.Misc, context: AppContext) -> None:
        super().__init__(master, fg_color="transparent")
        self.context = context
        self._pages: Dict[str, BasePage] = {}
        self._buttons: Dict[str, ctk.CTkButton] = {}
        self._current: Optional[str] = None

        self._build_layout()
        self.navigate("Subtitle")

    def _build_layout(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self._sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        self._sidebar.grid(row=0, column=0, sticky="nsw")
        self._sidebar.grid_rowconfigure(len(NAV_ITEMS) + 1, weight=1)
        self._sidebar.grid_propagate(False)

        ctk.CTkLabel(
            self._sidebar, text="Subtitle Translate", font=("Segoe UI", 18, "bold"),
        ).grid(row=0, column=0, padx=20, pady=(22, 18), sticky="w")

        for index, name in enumerate(NAV_ITEMS, start=1):
            button = ctk.CTkButton(
                self._sidebar, text=name, anchor="w", height=40, corner_radius=8,
                fg_color="transparent", text_color="#cbd5e1", hover_color="#26263a",
                command=lambda n=name: self.navigate(n),
            )
            button.grid(row=index, column=0, padx=12, pady=3, sticky="ew")
            self._buttons[name] = button

        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.grid(row=0, column=1, sticky="nsew")
        self._content.grid_rowconfigure(0, weight=1)
        self._content.grid_columnconfigure(0, weight=1)

        self.grid_rowconfigure(1, weight=0)
        self._status_bar = StatusBar(self)
        self._status_bar.grid(row=1, column=0, columnspan=2, sticky="ew")

    def _create_page(self, name: str) -> BasePage:
        set_status = self._status_bar.set_state
        if name == "Subtitle":
            return SubtitlePage(self._content, self.context, set_status)
        if name == "Settings":
            return SettingsPage(self._content, self.context, set_status, on_theme_change=self._apply_theme)
        if name == "Logs":
            return LogsPage(self._content, self.context, set_status)
        raise ValueError(f"Unknown page: {name}")

    def _get_page(self, name: str) -> BasePage:
        if name not in self._pages:
            page = self._create_page(name)
            page.grid(row=0, column=0, sticky="nsew")
            self._pages[name] = page
        return self._pages[name]

    def navigate(self, name: str) -> None:
        page = self._get_page(name)
        page.tkraise()
        page.on_show()
        self._current = name
        for btn_name, button in self._buttons.items():
            active = btn_name == name
            button.configure(fg_color="#3b82f6" if active else "transparent",
                             text_color="#ffffff" if active else "#cbd5e1")

    def _apply_theme(self, theme: str) -> None:
        ctk.set_appearance_mode(theme)
