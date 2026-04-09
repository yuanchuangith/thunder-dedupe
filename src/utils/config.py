#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Configuration helpers.
"""
from pathlib import Path
import json
from typing import Any, Optional


def get_app_dir() -> Path:
    """Return the application directory."""
    return Path(__file__).parent.parent


def get_data_dir() -> Path:
    """Return the user data directory."""
    data_dir = Path.home() / ".thunder-dedupe"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_config_path() -> Path:
    """Return the config file path."""
    return get_data_dir() / "config.json"


class Config:
    """Simple config manager."""

    _instance: Optional["Config"] = None

    DEFAULT_VIDEO_EXTENSIONS = (
        ".mp4", ".mkv", ".avi", ".wmv", ".flv", ".mov",
        ".mpg", ".mpeg", ".m4v", ".rm", ".rmvb", ".ts", ".m2ts",
    )

    DEFAULT_TEMP_EXTENSIONS = (
        ".xltd", ".td", ".bt", ".thunder",
    )

    DEFAULT_CONFIG = {
        "intercept_enabled": True,
        "auto_start": False,
        "minimize_to_tray": False,
        "notification_duration": 5,
        "auto_scan_interval_minutes": 10,
        "scan_paths": [],
        "extra_video_extensions": "",
        "extra_temp_extensions": "",
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._config_path = get_config_path()
        self._config = self._load()

    def _load(self) -> dict:
        """Load config data."""
        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    return {**self.DEFAULT_CONFIG, **saved}
            except (json.JSONDecodeError, IOError):
                pass
        return self.DEFAULT_CONFIG.copy()

    def save(self):
        """Persist config data."""
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(self._config, f, indent=2, ensure_ascii=False)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value."""
        return self._config.get(key, default)

    def set(self, key: str, value: Any, auto_save: bool = True):
        """Set a config value."""
        self._config[key] = value
        if auto_save:
            self.save()

    @staticmethod
    def normalize_extensions(raw: Any) -> list[str]:
        """Normalize extension values into a deduplicated ordered list."""
        if raw is None:
            return []

        if isinstance(raw, str):
            items = raw.split(",")
        elif isinstance(raw, (list, tuple, set)):
            items = list(raw)
        else:
            items = [raw]

        normalized = []
        seen = set()

        for item in items:
            ext = str(item).strip().lower()
            if not ext:
                continue
            if not ext.startswith("."):
                ext = f".{ext}"
            if ext in seen:
                continue
            seen.add(ext)
            normalized.append(ext)

        return normalized

    @classmethod
    def format_extensions(cls, raw: Any) -> str:
        """Format extensions for display/storage."""
        return ", ".join(cls.normalize_extensions(raw))

    def _get_extra_extensions(self, extra_key: str, legacy_key: str, defaults: tuple[str, ...]) -> list[str]:
        """Read extra extensions with legacy-key fallback."""
        raw_extra = self._config.get(extra_key, None)
        if raw_extra not in (None, ""):
            return self.normalize_extensions(raw_extra)

        legacy_raw = self._config.get(legacy_key, "")
        legacy_extensions = self.normalize_extensions(legacy_raw)
        default_set = set(defaults)
        return [ext for ext in legacy_extensions if ext not in default_set]

    def get_default_video_extensions(self) -> list[str]:
        return list(self.DEFAULT_VIDEO_EXTENSIONS)

    def get_default_temp_extensions(self) -> list[str]:
        return list(self.DEFAULT_TEMP_EXTENSIONS)

    def get_extra_video_extensions(self) -> list[str]:
        return self._get_extra_extensions(
            "extra_video_extensions",
            "video_extensions",
            self.DEFAULT_VIDEO_EXTENSIONS,
        )

    def get_extra_temp_extensions(self) -> list[str]:
        return self._get_extra_extensions(
            "extra_temp_extensions",
            "temp_extensions",
            self.DEFAULT_TEMP_EXTENSIONS,
        )

    def get_video_extensions(self) -> set:
        return set(self.DEFAULT_VIDEO_EXTENSIONS) | set(self.get_extra_video_extensions())

    def get_temp_extensions(self) -> set:
        return set(self.DEFAULT_TEMP_EXTENSIONS) | set(self.get_extra_temp_extensions())

    def set_extra_video_extensions(self, raw: Any, auto_save: bool = True):
        extra_extensions = self.normalize_extensions(raw)
        self._config["extra_video_extensions"] = self.format_extensions(extra_extensions)
        self._config["video_extensions"] = self.format_extensions(
            list(self.DEFAULT_VIDEO_EXTENSIONS) + extra_extensions
        )
        if auto_save:
            self.save()

    def set_extra_temp_extensions(self, raw: Any, auto_save: bool = True):
        extra_extensions = self.normalize_extensions(raw)
        self._config["extra_temp_extensions"] = self.format_extensions(extra_extensions)
        self._config["temp_extensions"] = self.format_extensions(
            list(self.DEFAULT_TEMP_EXTENSIONS) + extra_extensions
        )
        if auto_save:
            self.save()

    @property
    def intercept_enabled(self) -> bool:
        return self._config.get("intercept_enabled", True)

    @intercept_enabled.setter
    def intercept_enabled(self, value: bool):
        self.set("intercept_enabled", value)

    @property
    def scan_paths(self) -> list:
        return self._config.get("scan_paths", [])

    @scan_paths.setter
    def scan_paths(self, value: list):
        self.set("scan_paths", value)


config = Config()
