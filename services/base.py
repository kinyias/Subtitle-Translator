"""Shared plumbing for the service wrappers.

The services reuse the original backend (:mod:`services.capcut_api`) unchanged.
Each request is assembled by the backend's own ``build_request`` and executed
here, mirroring exactly what the CLI ``main()`` did (``requests.post`` with the
utf-8 encoded body). This keeps every request identical to the original tool.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Dict, Optional

from services import capcut_api
from utils.logger import logger


class ServiceError(RuntimeError):
    """Raised for recoverable, user-presentable service failures."""


@dataclass
class RequestPreview:
    """The fully-built request, matching the CLI ``--dry-run`` dump."""

    url: str
    headers: Dict[str, str]
    body: Any

    def to_dict(self) -> Dict[str, Any]:
        return {"url": self.url, "headers": self.headers, "body": self.body}


@dataclass
class TaskResult:
    """Outcome of a network call plus the request that produced it."""

    status_code: int
    text: str
    json: Optional[Any] = None
    preview: Optional[RequestPreview] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 400


def make_args(**overrides: Any) -> SimpleNamespace:
    """Create an args object with every field ``build_request`` may read.

    Defaults mirror the CLI's ``argparse`` defaults so the backend behaves
    identically whether driven by the terminal or the GUI.
    """
    defaults: Dict[str, Any] = {
        "mode": None,
        "device_json": None,
        "dry_run": False,
        "out": None,
        "text": None,
        "text_file": None,
        "voice": "BV074_streaming",
        "resource_id": "7102355709945188865",
        "rate": "1.0",
        "audio_vid": None,
        "audio_md5": None,
        "audio_file": None,
        "duration_ms": None,
        "language": "zh-CN",
        "translation_language": "vi-VN",
        "use_translation": False,
        "task_id": None,
        "token": None,
        "bind_id": "",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def build_preview(args: SimpleNamespace) -> RequestPreview:
    """Assemble the request via the backend without sending it."""
    url, headers, body_text = capcut_api.build_request(args)
    return RequestPreview(url=url, headers=headers, body=json.loads(body_text))


def execute(args: SimpleNamespace, timeout: int) -> TaskResult:
    """Build and POST a request, replicating the CLI ``main()`` network path."""
    if capcut_api.requests is None:  # same guard the CLI used
        raise ServiceError("The 'requests' package is required. Run: pip install requests")

    url, headers, body_text = capcut_api.build_request(args)
    preview = RequestPreview(url=url, headers=headers, body=json.loads(body_text))
    logger.info(f"POST {url.split('?', 1)[0]}")

    try:
        resp = capcut_api.requests.post(
            url, headers=headers, data=body_text.encode("utf-8"), timeout=timeout
        )
    except Exception as exc:  # network layer failures -> friendly error
        raise ServiceError(f"Network request failed: {exc}") from exc

    parsed: Optional[Any]
    try:
        parsed = resp.json()
    except ValueError:
        parsed = None

    return TaskResult(
        status_code=resp.status_code,
        text=resp.text,
        json=parsed,
        preview=preview,
    )
