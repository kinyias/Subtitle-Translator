"""Speech-to-Text (subtitle recognition) service.

Wraps the backend's ``stt-new`` request. The audio must already be uploaded
(see :mod:`services.uploader`); this service submits the recognition task for a
known ``vid``/``md5``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from services.base import RequestPreview, TaskResult, build_preview, execute, make_args


@dataclass
class STTRequest:
    """User inputs for a subtitle-recognition task."""

    audio_vid: str
    audio_md5: str
    duration_ms: int
    language: str = "zh-CN"
    translation_language: str = "vi-VN"
    use_translation: bool = False

    def to_args(self, device_json_path: Optional[str]):
        return make_args(
            mode="stt-new",
            device_json=device_json_path,
            audio_vid=self.audio_vid,
            audio_md5=self.audio_md5,
            duration_ms=int(self.duration_ms) if self.duration_ms else None,
            language=self.language,
            translation_language=self.translation_language,
            use_translation=bool(self.use_translation),
        )


class STTService:
    """Builds and executes CapCut STT (``cc_audio_subtitle_asr``) tasks."""

    def __init__(self, timeout: int = 60) -> None:
        self.timeout = timeout

    def preview(self, request: STTRequest, device_json_path: Optional[str]) -> RequestPreview:
        return build_preview(request.to_args(device_json_path))

    def generate(self, request: STTRequest, device_json_path: Optional[str]) -> TaskResult:
        return execute(request.to_args(device_json_path), self.timeout)
