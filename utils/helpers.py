"""Small, dependency-free helper functions shared across the application.

Nothing here contains business logic; these are formatting, path and
clipboard conveniences used by the GUI and service layers.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterator, List, Optional, Tuple


def is_frozen() -> bool:
    """Return ``True`` when running from a PyInstaller ``--onefile`` build."""
    return bool(getattr(sys, "frozen", False))


def base_dir() -> Path:
    """Directory used to resolve external, user-editable resources.

    For a frozen build this is the folder that contains the executable so
    ``config/`` and ``Voice.json`` live next to the ``.exe``. During
    development it resolves to the project root.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def pretty_json(obj: Any) -> str:
    """Serialize *obj* as indented, human-readable JSON.

    Accepts already-parsed objects or raw JSON strings; invalid strings are
    returned unchanged so the viewer never blows up on malformed input.
    """
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except (ValueError, TypeError):
            return obj
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return str(obj)


def format_bytes(size: Any) -> str:
    """Render a byte count as a compact human-readable size."""
    try:
        value = float(size)
    except (TypeError, ValueError):
        return "-"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{value:.2f} PB"


def format_duration_ms(duration_ms: Any) -> str:
    """Render a millisecond duration as ``mm:ss.mmm``."""
    try:
        total = int(duration_ms)
    except (TypeError, ValueError):
        return "-"
    if total <= 0:
        return "0:00.000"
    minutes, rem = divmod(total, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{minutes}:{seconds:02d}.{millis:03d}"


def truncate(text: str, limit: int = 4000) -> str:
    """Clamp very long text so log widgets stay responsive."""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated {len(text) - limit} chars]"


def _walk(obj: Any) -> Iterator[dict]:
    """Yield every dict nested anywhere inside *obj*."""
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _walk(value)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            yield from _walk(value)


def extract_task_ids(response: Any) -> Tuple[Optional[str], Optional[str]]:
    """Best-effort pull of ``(task_id, token)`` from a ``common_task/new`` reply.

    The CapCut response nests the created task under varying keys, so this walks
    the whole structure and returns the first plausible id/token pair. Returns
    ``(None, None)`` when nothing is found; callers should fall back to manual
    entry in that case.
    """
    id_keys = ("task_id", "id", "taskId")
    for node in _walk(response):
        token = node.get("token")
        if not token:
            continue
        for key in id_keys:
            value = node.get(key)
            if value:
                return str(value), str(token)
    # token and id may live in sibling nodes; grab the first of each as a fallback
    task_id = token = None
    for node in _walk(response):
        if task_id is None:
            for key in id_keys:
                if node.get(key):
                    task_id = str(node[key])
                    break
        if token is None and node.get("token"):
            token = str(node["token"])
        if task_id and token:
            break
    return task_id, token


def read_text_file(path: str) -> str:
    """Read a UTF-8 text file, tolerating a BOM."""
    return Path(path).read_text(encoding="utf-8-sig")


def write_text_file(path: str, content: str) -> None:
    Path(path).write_text(content, encoding="utf-8")
