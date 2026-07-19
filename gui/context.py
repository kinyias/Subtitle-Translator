"""Dependency container shared across the GUI."""
from __future__ import annotations

from dataclasses import dataclass

from services.pipeline import SubtitlePipeline
from services.query_service import QueryService
from services.stt_service import STTService
from services.translator import Translator
from services.uploader import UploaderService
from utils.config import ConfigManager
from utils.logger import AppLogger
from workers.base_worker import TkDispatcher, WorkerPool
from workers.pipeline_worker import SubtitlePipelineWorker


@dataclass
class AppContext:
    """Everything the pages need, wired once and shared read-only."""

    config: ConfigManager
    logger: AppLogger
    dispatcher: TkDispatcher
    pool: WorkerPool
    pipeline: SubtitlePipelineWorker

    @classmethod
    def build(cls, config: ConfigManager, logger: AppLogger, dispatcher: TkDispatcher) -> "AppContext":
        timeout = config.config.api_timeout
        pool = WorkerPool(dispatcher, max_workers=4)

        stt_service = STTService(timeout=timeout)
        query_service = QueryService(timeout=timeout)
        uploader_service = UploaderService()
        translator = Translator(timeout=max(timeout, 120))

        pipeline = SubtitlePipeline(uploader_service, stt_service, query_service, translator, logger)

        return cls(
            config=config,
            logger=logger,
            dispatcher=dispatcher,
            pool=pool,
            pipeline=SubtitlePipelineWorker(pool, pipeline),
        )

    def device_json_path(self) -> str:
        return str(self.config.device_path)
