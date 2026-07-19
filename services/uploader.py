"""Audio upload service.

Wraps the backend's :func:`services.capcut_api.upload_audio_file`, which
performs the full CapCut VOD flow (upload_sign -> ApplyUploadInner -> transfer
-> finish -> CommitUploadInner) with pure-Python AWS SigV4 signing. That
function takes a resolved device dict, so this service accepts one directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from services import capcut_api
from services.base import ServiceError
from utils.logger import logger


@dataclass
class UploadResult:
    """Normalised result of an audio upload (superset of backend output)."""

    vid: str
    md5: str
    local_md5: str
    duration_ms: int
    format: Optional[str]
    size: Optional[int]
    file_type: Optional[str]
    store_uri: Optional[str]
    raw: Dict[str, Any]

    @classmethod
    def from_backend(cls, data: Dict[str, Any]) -> "UploadResult":
        return cls(
            vid=str(data.get("vid") or ""),
            md5=str(data.get("md5") or ""),
            local_md5=str(data.get("local_md5") or ""),
            duration_ms=int(data.get("duration_ms") or 0),
            format=data.get("format"),
            size=data.get("size"),
            file_type=data.get("file_type"),
            store_uri=data.get("store_uri"),
            raw=data,
        )


class UploaderService:
    """Uploads local audio/video to the CapCut text-recognition VOD space."""

    def upload(self, path: str, device: Dict[str, Any]) -> UploadResult:
        if capcut_api.requests is None:
            raise ServiceError("The 'requests' package is required. Run: pip install requests")
        logger.info(f"Uploading '{path}' to CapCut VOD ...")
        try:
            data = capcut_api.upload_audio_file(path, device)
        except SystemExit as exc:  # backend uses SystemExit for missing requests
            raise ServiceError(str(exc)) from exc
        except Exception as exc:
            raise ServiceError(f"Upload failed: {exc}") from exc
        logger.success(f"Upload complete (vid={data.get('vid')}).")
        return UploadResult.from_backend(data)
