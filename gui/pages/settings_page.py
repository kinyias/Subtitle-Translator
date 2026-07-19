"""Settings page: appearance, timeout and default recognition language.

The AI-translation endpoint (URL / key / model / prompt) is configured inline on
the Subtitle page and persisted from there; this page holds the app-wide bits.
"""
from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from gui.pages.base_page import BasePage


class SettingsPage(BasePage):
    title = "Settings"
    subtitle = "Appearance and network defaults. Saved on exit."

    def __init__(self, master, context, set_status, on_theme_change: Callable[[str], None]) -> None:
        self._on_theme_change = on_theme_change
        super().__init__(master, context, set_status)

    def build(self) -> None:
        cfg = self.context.config.config
        card = ctk.CTkFrame(self.body, corner_radius=10)
        card.pack(fill="x", pady=(0, 12))
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card, text="Appearance", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 6)
        )
        ctk.CTkLabel(card, text="Theme", font=("Segoe UI", 13)).grid(
            row=1, column=0, sticky="w", padx=14, pady=6
        )
        self._theme = ctk.CTkOptionMenu(
            card, values=["Dark", "Light", "System"], command=self._change_theme
        )
        self._theme.grid(row=1, column=1, sticky="w", padx=14, pady=6)
        self._theme.set(cfg.theme)

        ctk.CTkLabel(card, text="API Timeout (s)", font=("Segoe UI", 13)).grid(
            row=2, column=0, sticky="w", padx=14, pady=6
        )
        self._timeout = ctk.CTkEntry(card, width=120)
        self._timeout.grid(row=2, column=1, sticky="w", padx=14, pady=6)
        self._timeout.insert(0, str(cfg.api_timeout))

        ctk.CTkLabel(card, text="Default Language", font=("Segoe UI", 13)).grid(
            row=3, column=0, sticky="w", padx=14, pady=(6, 14)
        )
        self._language = ctk.CTkEntry(card, width=160)
        self._language.grid(row=3, column=1, sticky="w", padx=14, pady=(6, 14))
        self._language.insert(0, cfg.default_language)

        ctk.CTkButton(self.body, text="Save Settings", width=140, command=self._save).pack(
            anchor="w", pady=4
        )

    def _change_theme(self, value: str) -> None:
        self.context.config.config.theme = value
        self._on_theme_change(value)

    def _save(self) -> None:
        cfg = self.context.config.config
        cfg.theme = self._theme.get()
        try:
            cfg.api_timeout = max(5, int(self._timeout.get().strip()))
        except ValueError:
            self.show_warning("Settings", "Timeout must be a whole number of seconds.")
            return
        cfg.default_language = self._language.get().strip() or cfg.default_language
        self.context.config.save()
        self.status("Completed", "Settings saved")
