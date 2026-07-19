"""Compact single-line path selector (open or save).

Unlike :class:`~gui.widgets.file_picker.FilePicker` (a large drag-and-drop
card), this is a slim label + entry + browse button meant to sit inside a form
for choosing an input file to load or an output file to write.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog
from typing import Callable, List, Optional, Tuple

import customtkinter as ctk


class PathRow(ctk.CTkFrame):
    """A labelled path entry with a Browse button.

    ``mode='open'`` opens an existing file; ``mode='save'`` chooses a save
    target. ``on_pick`` fires with the chosen path (never with empty).
    """

    def __init__(
        self,
        master: tk.Misc,
        label: str,
        mode: str = "open",
        filetypes: Optional[List[Tuple[str, str]]] = None,
        default_extension: str = "",
        default_name: str = "",
        on_pick: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        if mode not in ("open", "save"):
            raise ValueError("mode must be 'open' or 'save'")
        self._mode = mode
        self._filetypes = filetypes or [("All files", "*.*")]
        self._default_extension = default_extension
        self._default_name = default_name
        self._on_pick = on_pick
        self._path = tk.StringVar()

        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text=label, font=("Segoe UI", 13), width=140, anchor="w").grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        self._entry = ctk.CTkEntry(self, textvariable=self._path, placeholder_text="Not selected")
        self._entry.grid(row=0, column=1, sticky="ew")
        ctk.CTkButton(self, text="Browse", width=90, command=self._browse).grid(
            row=0, column=2, padx=(8, 0)
        )

    def _browse(self) -> None:
        if self._mode == "open":
            path = filedialog.askopenfilename(title="Select file", filetypes=self._filetypes)
        else:
            path = filedialog.asksaveasfilename(
                title="Save as",
                defaultextension=self._default_extension,
                initialfile=self._default_name,
                filetypes=self._filetypes,
            )
        if path:
            self.set_path(path)
            if self._on_pick:
                self._on_pick(path)

    def set_path(self, path: str) -> None:
        self._path.set(path)

    def get_path(self) -> str:
        return self._path.get().strip()
