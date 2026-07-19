"""Task-polling service for both TTS and STT results.

Wraps the backend's ``tts-query`` / ``stt-query`` requests. The query type
selects the ``req_key`` and the ``appid`` header exactly as the CLI did.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from services.base import RequestPreview, TaskResult, build_preview, execute, make_args


class QueryType(str, Enum):
    """Which task family to poll; maps directly to the CLI modes."""

    TTS = "tts-query"
    STT = "stt-query"

    @property
    def label(self) -> str:
        return "TTS" if self is QueryType.TTS else "STT"


@dataclass
class QueryRequest:
    """User inputs for a task-status query."""

    task_id: str
    token: str
    query_type: QueryType = QueryType.TTS
    bind_id: str = ""

    def to_args(self, device_json_path: Optional[str]):
        return make_args(
            mode=self.query_type.value,
            device_json=device_json_path,
            task_id=self.task_id,
            token=self.token,
            bind_id=self.bind_id or "",
        )


class QueryService:
    """Builds and executes CapCut ``common_task/query`` requests."""

    def __init__(self, timeout: int = 60) -> None:
        self.timeout = timeout

    def preview(self, request: QueryRequest, device_json_path: Optional[str]) -> RequestPreview:
        return build_preview(request.to_args(device_json_path))

    def query(self, request: QueryRequest, device_json_path: Optional[str]) -> TaskResult:
        return execute(request.to_args(device_json_path), self.timeout)
