"""Application shell.

Creates the root window, applies the theme, wires the config lifecycle
(load on startup / save on exit), installs a global Tk exception hook so the
app never crashes silently, and starts the worker dispatcher pump.
"""
from __future__ import annotations

import tkinter as tk
import traceback
from tkinter import messagebox

import customtkinter as ctk

from gui.context import AppContext
from gui.main_window import MainWindow
from utils.config import ConfigManager
from utils.helpers import base_dir
from utils.logger import logger
from workers.base_worker import TkDispatcher


class SubtitleApp:
    """Owns the Tk root and the application lifecycle."""

    def __init__(self) -> None:
        self.config = ConfigManager()
        self.config.load()

        ctk.set_appearance_mode(self.config.config.theme)
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("Subtitle Translate Studio")
        self.root.geometry(self.config.config.window_geometry)
        self.root.minsize(980, 720)
        self._apply_icon()

        self.dispatcher = TkDispatcher(self.root)
        self.context = AppContext.build(self.config, logger, self.dispatcher)

        self.main = MainWindow(self.root, self.context)
        self.main.pack(fill="both", expand=True)

        self.dispatcher.start()
        self._install_exception_hook()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        logger.success("Application started.")

    def _apply_icon(self) -> None:
        icon = base_dir() / "resources" / "icon.ico"
        if icon.exists():
            try:
                self.root.iconbitmap(str(icon))
            except tk.TclError:
                pass

    def _install_exception_hook(self) -> None:
        def report(exc_type, exc_value, exc_tb) -> None:
            tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            logger.error(f"Unhandled exception:\n{tb}")
            try:
                messagebox.showerror("Unexpected error", str(exc_value) or exc_type.__name__)
            except Exception:
                pass

        self.root.report_callback_exception = report  # type: ignore[assignment]

    def _on_close(self) -> None:
        try:
            self.config.config.window_geometry = self.root.geometry()
            self.config.save()
            logger.info("Configuration saved on exit.")
        except Exception as exc:
            logger.exception("Error while saving on exit", exc)
        finally:
            self.dispatcher.stop()
            self.context.pool.shutdown()
            self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
