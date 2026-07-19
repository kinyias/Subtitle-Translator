"""Subtitle Translate Studio - application entry point.

Recognizes speech from an audio/video file via CapCut, optionally translates the
subtitles with an OpenAI-compatible AI endpoint (preserving timing), lets you
preview the result, and exports a ``.srt`` file.

Build a single-file executable with:

    pyinstaller --onefile --windowed main.py
"""
from __future__ import annotations

import sys
import traceback


def main() -> int:
    try:
        from gui.app import SubtitleApp
    except Exception as exc:  # import-time failure (e.g. missing dependency)
        _fatal("Failed to start Subtitle Translate Studio", exc)
        return 1

    try:
        SubtitleApp().run()
    except Exception as exc:  # last-resort guard so the app never crashes raw
        _fatal("A fatal error occurred", exc)
        return 1
    return 0


def _fatal(title: str, exc: BaseException) -> None:
    detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    try:
        from tkinter import Tk, messagebox

        root = Tk()
        root.withdraw()
        messagebox.showerror(title, f"{exc}\n\n{detail}")
        root.destroy()
    except Exception:
        print(f"{title}: {exc}\n{detail}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
