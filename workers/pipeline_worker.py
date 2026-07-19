"""Background worker for the subtitle recognition + translation pipeline."""
from __future__ import annotations

from typing import Any, Dict, Optional

from services.pipeline import SubtitlePipeline, SubtitleResult
from services.translator import TranslatorConfig
from workers.base_worker import WorkerCallbacks, WorkerPool


class SubtitlePipelineWorker:
    """Runs :meth:`SubtitlePipeline.run` off the GUI thread."""

    def __init__(self, pool: WorkerPool, pipeline: SubtitlePipeline) -> None:
        self._pool = pool
        self._pipeline = pipeline

    def run(
        self,
        audio_path: str,
        device: Dict[str, Any],
        device_json_path: Optional[str],
        language: str,
        use_translation: bool,
        translator_config: Optional[TranslatorConfig],
        callbacks: WorkerCallbacks[SubtitleResult],
    ) -> None:
        self._pool.submit(
            lambda: self._pipeline.run(
                audio_path, device, device_json_path,
                language, use_translation, translator_config,
            ),
            callbacks,
        )
