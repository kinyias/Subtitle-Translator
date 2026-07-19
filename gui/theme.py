"""Shared colours and fonts for the CustomTkinter UI."""
from __future__ import annotations

# Log-level colours used by the log console and toasts.
LEVEL_COLORS = {
    "INFO": "#8ab4f8",
    "WARNING": "#f5c518",
    "ERROR": "#ff6b6b",
    "SUCCESS": "#4ade80",
}

# Status-bar state colours.
STATUS_COLORS = {
    "Ready": "#4ade80",
    "Running": "#f5c518",
    "Completed": "#4ade80",
    "Failed": "#ff6b6b",
}

ACCENT = "#3b82f6"
ACCENT_HOVER = "#2563eb"
SURFACE = "#1e1e2e"
SURFACE_ALT = "#181825"
MONO_FONT = ("Consolas", 12)
TITLE_FONT = ("Segoe UI", 22, "bold")
SUBTITLE_FONT = ("Segoe UI", 13)
LABEL_FONT = ("Segoe UI", 13)
