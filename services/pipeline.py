"""Subtitle recognition + AI translation pipeline.

Flow (all on a worker thread):

    upload audio -> create STT task -> poll until succeed -> parse utterances
    -> (optional) AI-translate the text of each cue -> return SubtitleEntry list

The pipeline does **not** write any file. It returns the cues so the GUI can
render a preview; exporting to ``.srt`` is a separate, explicit step. Timings
(``start_ms`` / ``end_ms``) come straight from CapCut and are never derived from
the translation, so translated subtitles keep their original timeframe.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from services import capcut_api, results
from services.audio_extract import prepare_audio_for_upload
from services.base import ServiceError, TaskResult
from services.query_service import QueryRequest, QueryService, QueryType
from services.stt_service import STTRequest, STTService
from services.translator import Translator, TranslatorConfig
from services.uploader import UploaderService
from utils.helpers import extract_task_ids
from utils.logger import AppLogger

_POLL_INTERVAL_S = 5.0
_POLL_TIMEOUT_S = 1000.0


@dataclass
class SubtitleEntry:
    """A single subtitle cue with millisecond timing.

    ``text`` is the recognized (source) text; ``translated`` holds the AI
    translation when translation is enabled, otherwise ``None``.
    """

    index: int
    start_ms: int
    end_ms: int
    text: str
    translated: Optional[str] = None

    def display_text(self) -> str:
        """Text used when exporting: the translation if present, else source."""
        return self.translated if self.translated is not None else self.text


@dataclass
class SubtitleResult:
    """Outcome of a pipeline run, ready for preview and export."""

    entries: List[SubtitleEntry]
    translated: bool
    task_id: str = ""
    detail: str = ""
    final_response: Any = field(default=None, repr=False)


def _require_requests() -> None:
    if capcut_api.requests is None:
        raise ServiceError("The 'requests' package is required. Run: pip install requests")


def _resolve_task(result: TaskResult, label: str) -> tuple[str, str]:
    if not result.ok:
        raise ServiceError(f"{label} request failed: HTTP {result.status_code} {result.text[:300]}")
    task_id, token = extract_task_ids(result.json)
    if not task_id or not token:
        raise ServiceError(f"{label} response had no task id/token. Raw: {result.text[:300]}")
    return task_id, token


def _poll(query: QueryService, request: QueryRequest, device_json_path: Optional[str],
          logger: AppLogger, label: str) -> Any:
    deadline = time.monotonic() + _POLL_TIMEOUT_S
    attempt = 0
    while True:
        attempt += 1
        result = query.query(request, device_json_path)
        if not result.ok:
            raise ServiceError(f"{label} query failed: HTTP {result.status_code} {result.text[:300]}")
        status = results.task_status(result.json)
        progress = results.task_progress(result.json)
        logger.info(f"{label} poll #{attempt}: status='{status or '?'}'"
                    + (f" ({progress}%)" if progress is not None else ""))
        if results.is_success(status):
            return result.json
        if results.is_failure(status):
            raise ServiceError(f"{label} task reported status '{status}'. Raw: {result.text[:300]}")
        if time.monotonic() >= deadline:
            raise ServiceError(f"{label} timed out after {int(_POLL_TIMEOUT_S)}s (last '{status}').")
        time.sleep(_POLL_INTERVAL_S)


def _to_entries(utterances: List[Dict[str, Any]]) -> List[SubtitleEntry]:
    entries: List[SubtitleEntry] = []
    for i, u in enumerate(utterances, start=1):
        start = int(round(float(u.get("start_time", 0) or 0)))
        end = int(round(float(u.get("end_time", start) or start)))
        entries.append(SubtitleEntry(
            index=i, start_ms=start, end_ms=end, text=str(u.get("text") or "").strip()
        ))
    return entries


class SubtitlePipeline:
    """upload -> recognize -> poll -> (optional AI translate) -> cues."""

    def __init__(self, uploader: UploaderService, stt: STTService, query: QueryService,
                 translator: Translator, logger: AppLogger) -> None:
        self._uploader = uploader
        self._stt = stt
        self._query = query
        self._translator = translator
        self._logger = logger

    def run(
        self,
        audio_path: str,
        device: Dict[str, Any],
        device_json_path: Optional[str],
        language: str,
        use_translation: bool,
        translator_config: Optional[TranslatorConfig],
    ) -> SubtitleResult:
        _require_requests()
        # Large videos are transcoded to a compact audio track first so the
        # upload stays small and memory-friendly (see audio_extract).
        upload_path, cleanup = prepare_audio_for_upload(audio_path, self._logger)
        try:
            self._logger.info(f"Uploading '{upload_path}' ...")
            upload = self._uploader.upload(upload_path, device)
        finally:
            cleanup()
        if not upload.vid or not upload.md5:
            raise ServiceError("Upload did not return a vid/md5; cannot start recognition.")
        self._logger.info(f"Uploaded (vid={upload.vid}); submitting recognition ...")

        request = STTRequest(
            audio_vid=upload.vid,
            audio_md5=upload.md5,
            duration_ms=upload.duration_ms or 10000,
            language=language,
            use_translation=False,  # never use CapCut's translation; we use AI
        )
        created = self._stt.generate(request, device_json_path)
        task_id, token = _resolve_task(created, "STT")
        self._logger.info(f"Task {task_id} created; polling ...")

        query_req = QueryRequest(task_id=task_id, token=token, query_type=QueryType.STT)
        final = _poll(self._query, query_req, device_json_path, self._logger, "STT")

        utterances = results.stt_utterances(results.task_payload(final))
        if not utterances:
            raise ServiceError("Recognition succeeded but returned no subtitle utterances.")
        entries = _to_entries(utterances)
        self._logger.success(f"Recognized {len(entries)} subtitle segment(s).")

        translated = False
        if use_translation and translator_config is not None:
            self._logger.info("Translating subtitles with AI ...")
            texts = [e.text for e in entries]
            out = self._translator.translate_segments(texts, translator_config, self._logger)
            for entry, value in zip(entries, out):
                entry.translated = value
            translated = True
            self._logger.success("AI translation complete.")

        detail = f"{len(entries)} segment(s)" + (" + translated" if translated else "")
        return SubtitleResult(
            entries=entries, translated=translated, task_id=task_id,
            detail=detail, final_response=final,
        )

    def translate_entries(
        self,
        entries: List[SubtitleEntry],
        translator_config: TranslatorConfig,
    ) -> SubtitleResult:
        """AI-translate already-parsed cues (e.g. loaded from an SRT file).

        No upload or recognition happens; only the ``text`` of each cue is
        translated and stored in ``translated``. Timings are untouched, so the
        exported SRT keeps the source file's timeframe.
        """
        if not entries:
            raise ServiceError("No subtitle cues to translate.")
        self._logger.info(f"Translating {len(entries)} subtitle segment(s) with AI ...")
        texts = [e.text for e in entries]
        out = self._translator.translate_segments(texts, translator_config, self._logger)
        for entry, value in zip(entries, out):
            entry.translated = value
        self._logger.success("AI translation complete.")
        return SubtitleResult(
            entries=entries, translated=True,
            detail=f"{len(entries)} segment(s) + translated",
        )
