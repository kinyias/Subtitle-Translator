"""Application configuration and device-profile persistence.

Two JSON files live in the ``config/`` folder next to the executable:

* ``config.json``  - user preferences, including the AI-translation endpoint
  (URL / API key / model / target language / style prompt) so they are reused
  across sessions.
* ``device.json``  - CapCut device profile that overrides ``DEFAULT_DEVICE``.

Both are created automatically on first launch and saved on exit.
"""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict

from services.capcut_api import DEFAULT_DEVICE
from utils.helpers import base_dir
from utils.logger import logger

CONFIG_DIRNAME = "config"
CONFIG_FILENAME = "config.json"
DEVICE_FILENAME = "device.json"


@dataclass
class AppConfig:
    """User-facing preferences persisted in ``config.json``."""

    theme: str = "Dark"
    default_language: str = "vi-VN"
    api_timeout: int = 60
    auto_scroll_logs: bool = True
    window_geometry: str = "1150x880"

    # AI translation endpoint (OpenAI-compatible /chat/completions).
    ai_base_url: str = "http://localhost:20128/v1/chat/completions"
    ai_api_key: str = ""
    ai_model: str = "openai/gpt-5"
    ai_target_language: str = "Vietnamese"
    ai_style_prompt: str = ""
    use_translation: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        known = {f for f in cls().to_dict()}
        filtered = {k: v for k, v in (data or {}).items() if k in known}
        return cls(**filtered)


class ConfigManager:
    """Loads, holds and saves application config and device profile."""

    def __init__(self, root: Path | None = None) -> None:
        self._config_dir = (root or base_dir()) / CONFIG_DIRNAME
        self._config_path = self._config_dir / CONFIG_FILENAME
        self._device_path = self._config_dir / DEVICE_FILENAME
        self.config: AppConfig = AppConfig()
        self.device_overrides: Dict[str, Any] = {}

    @property
    def config_path(self) -> Path:
        return self._config_path

    @property
    def device_path(self) -> Path:
        return self._device_path

    # -- lifecycle -------------------------------------------------------
    def load(self) -> None:
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self.config = self._load_config()
        self.device_overrides = self._load_device()
        self.save()

    def _load_config(self) -> AppConfig:
        if not self._config_path.exists():
            logger.info("config.json not found; creating defaults.")
            return AppConfig()
        try:
            with self._config_path.open("r", encoding="utf-8") as fp:
                return AppConfig.from_dict(json.load(fp))
        except (ValueError, OSError) as exc:
            logger.warning(f"Could not read config.json ({exc}); using defaults.")
            return AppConfig()

    def _load_device(self) -> Dict[str, Any]:
        if not self._device_path.exists():
            logger.info("device.json not found; creating from DEFAULT_DEVICE.")
            return deepcopy(DEFAULT_DEVICE)
        try:
            with self._device_path.open("r", encoding="utf-8") as fp:
                data = json.load(fp)
            return data if isinstance(data, dict) else deepcopy(DEFAULT_DEVICE)
        except (ValueError, OSError) as exc:
            logger.warning(f"Could not read device.json ({exc}); using defaults.")
            return deepcopy(DEFAULT_DEVICE)

    def save(self) -> None:
        try:
            self._config_dir.mkdir(parents=True, exist_ok=True)
            with self._config_path.open("w", encoding="utf-8") as fp:
                json.dump(self.config.to_dict(), fp, ensure_ascii=False, indent=2)
                fp.write("\n")
            with self._device_path.open("w", encoding="utf-8") as fp:
                json.dump(self.device_overrides, fp, ensure_ascii=False, indent=2)
                fp.write("\n")
        except OSError as exc:
            logger.error(f"Failed to save configuration: {exc}")

    # -- device ----------------------------------------------------------
    def resolve_device(self) -> Dict[str, Any]:
        device = deepcopy(DEFAULT_DEVICE)
        device.update(self.device_overrides or {})
        return device
