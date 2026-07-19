"""SRT rendering for :class:`SubtitleEntry` cues.

Kept separate from :mod:`services.results` (which parses raw API dicts) so the
preview and the exported file are produced from the exact same cue objects the
user sees - guaranteeing the file matches the preview.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from services.pipeline import SubtitleEntry
from services.results import ms_to_timestamp


def entries_to_srt(entries: List[SubtitleEntry], use_translation: bool) -> str:
    """Render cues as SRT text.

    When *use_translation* is true the translated text is written; otherwise the
    recognized source text. Timings always come from the cue, never the text.
    """
    blocks: List[str] = []
    for position, entry in enumerate(entries, start=1):
        text = (entry.translated if (use_translation and entry.translated is not None) else entry.text)
        text = (text or "").strip()
        blocks.append(
            f"{position}\n{ms_to_timestamp(entry.start_ms)} --> "
            f"{ms_to_timestamp(entry.end_ms)}\n{text}\n"
        )
    return "\n".join(blocks).strip() + "\n" if blocks else ""


def write_srt(path: str, entries: List[SubtitleEntry], use_translation: bool) -> int:
    """Write cues to *path* as UTF-8 SRT; returns the number of cues written."""
    Path(path).write_text(entries_to_srt(entries, use_translation), encoding="utf-8")
    return len(entries)
