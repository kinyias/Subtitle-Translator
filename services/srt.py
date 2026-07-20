"""SRT parsing and rendering for :class:`SubtitleEntry` cues.

Kept separate from :mod:`services.results` (which parses raw API dicts) so the
preview and the exported file are produced from the exact same cue objects the
user sees - guaranteeing the file matches the preview.

Parsing turns an existing ``.srt`` file back into cues so it can be re-translated
and re-exported, mirroring the recognition pipeline's output shape.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List

from services.base import ServiceError
from services.pipeline import SubtitleEntry
from services.results import ms_to_timestamp

# Matches an SRT timing line: ``HH:MM:SS,mmm --> HH:MM:SS,mmm`` (also tolerating
# ``.`` as the millisecond separator and flexible whitespace around ``-->``).
_TIMING_RE = re.compile(
    r"(\d+):(\d{1,2}):(\d{1,2})[,.](\d{1,3})\s*-->\s*"
    r"(\d+):(\d{1,2}):(\d{1,2})[,.](\d{1,3})"
)


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


def _timestamp_to_ms(hours: str, minutes: str, seconds: str, millis: str) -> int:
    """Convert a parsed ``HH:MM:SS,mmm`` timestamp into milliseconds."""
    return (
        int(hours) * 3_600_000
        + int(minutes) * 60_000
        + int(seconds) * 1000
        + int(millis.ljust(3, "0"))  # ``,5`` -> 500ms, ``,05`` -> 50ms
    )


def read_srt(path: str) -> List[SubtitleEntry]:
    """Parse an SRT file into :class:`SubtitleEntry` cues.

    Cue text lands in ``text`` (the source field), so a loaded file can flow
    through translation and export exactly like recognized subtitles. Blank
    separators, indices and BOMs are tolerated; ``translated`` stays ``None``.
    """
    try:
        raw = Path(path).read_text(encoding="utf-8-sig")
    except OSError:
        raise
    except UnicodeDecodeError:
        raw = Path(path).read_text(encoding="latin-1")

    # Split into blocks on blank lines; normalise CRLF/CR first.
    blocks = re.split(r"\n\s*\n", raw.replace("\r\n", "\n").replace("\r", "\n").strip())
    entries: List[SubtitleEntry] = []
    index = 1
    for block in blocks:
        lines = block.split("\n")
        timing_idx = -1
        match = None
        for i, line in enumerate(lines):
            match = _TIMING_RE.search(line)
            if match:
                timing_idx = i
                break
        if match is None:
            continue  # not a valid cue (e.g. stray text); skip it

        start_ms = _timestamp_to_ms(*match.group(1, 2, 3, 4))
        end_ms = _timestamp_to_ms(*match.group(5, 6, 7, 8))
        text = "\n".join(lines[timing_idx + 1 :]).strip()
        entries.append(SubtitleEntry(index=index, start_ms=start_ms, end_ms=end_ms, text=text))
        index += 1

    if not entries:
        raise ServiceError("No subtitle cues found in the file. Is it a valid .srt?")
    return entries
