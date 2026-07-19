"""Parsing of CapCut ``common_task/query`` results.

Both TTS and STT store their real output inside ``data.tasks[0].payload`` - a
*string* containing nested JSON. This module isolates the response shape so the
pipeline stays readable:

* TTS  payload -> ``audio_subtitles[].speech_url`` (direct ``audio_mpeg`` URLs).
* STT  payload -> ``utterances[]`` with millisecond ``start_time`` / ``end_time``.

Confirmed against a live TTS ``succeed`` response; the STT layout follows the
project README ("Where Are the Subtitles?").
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

# Task ``status`` strings observed / expected from the API.
_SUCCESS_STATES = {"succeed", "success", "done", "finished", "complete", "completed"}
_FAILURE_STATES = {"failed", "fail", "error", "cancelled", "canceled", "timeout"}


def first_task(response: Any) -> Dict[str, Any]:
    """Return ``data.tasks[0]`` or an empty dict when absent."""
    if not isinstance(response, dict):
        return {}
    tasks = (response.get("data") or {}).get("tasks") or []
    return tasks[0] if tasks and isinstance(tasks[0], dict) else {}


def task_status(response: Any) -> str:
    """Lower-cased status string of the first task ('' when unknown)."""
    return str(first_task(response).get("status") or "").strip().lower()


def task_progress(response: Any) -> Optional[int]:
    value = first_task(response).get("progress")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def is_success(status: str) -> bool:
    return status in _SUCCESS_STATES


def is_failure(status: str) -> bool:
    return status in _FAILURE_STATES


def task_payload(response: Any) -> Dict[str, Any]:
    """Parse the nested JSON string in ``data.tasks[0].payload``."""
    raw = first_task(response).get("payload")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}
    return {}


def tts_speech_urls(payload: Dict[str, Any]) -> List[str]:
    """Ordered list of MP3 URLs from a TTS payload's ``audio_subtitles``."""
    urls: List[str] = []
    for item in payload.get("audio_subtitles") or []:
        if isinstance(item, dict):
            url = item.get("speech_url")
            if url:
                urls.append(str(url))
    return urls


def stt_utterances(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Ordered subtitle segments from an STT payload.

    Segments live under ``utterances``; some responses nest them again inside
    ``audio_subtitles[].utterances``, so both are checked.
    """
    direct = payload.get("utterances")
    if isinstance(direct, list) and direct:
        return [u for u in direct if isinstance(u, dict)]
    collected: List[Dict[str, Any]] = []
    for item in payload.get("audio_subtitles") or []:
        if isinstance(item, dict):
            for u in item.get("utterances") or []:
                if isinstance(u, dict):
                    collected.append(u)
    return collected


def ms_to_timestamp(ms: Any) -> str:
    """Format a millisecond offset as an SRT timestamp ``HH:MM:SS,mmm``."""
    try:
        total = max(0, int(round(float(ms))))
    except (TypeError, ValueError):
        total = 0
    hours, total = divmod(total, 3_600_000)
    minutes, total = divmod(total, 60_000)
    seconds, millis = divmod(total, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def build_srt(utterances: List[Dict[str, Any]]) -> str:
    """Render subtitle segments as SRT text."""
    blocks: List[str] = []
    for index, item in enumerate(utterances, start=1):
        start = item.get("start_time", 0)
        end = item.get("end_time", start)
        text = str(item.get("text") or "").strip()
        blocks.append(
            f"{index}\n{ms_to_timestamp(start)} --> {ms_to_timestamp(end)}\n{text}\n"
        )
    return "\n".join(blocks).strip() + "\n" if blocks else ""
