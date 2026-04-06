#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置工具
"""
from pathlib import Path
import json
from typing import Any, Optional


def get_app_dir() -> Path:
    """获取应用目录"""
    return Path(__file__).parent.parent


def get_data_dir() -> Path:
    """获取数据存储目录"""
    data_dir = Path.home() / ".thunder-dedupe"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_config_path() -> Path:
    """获取配置文件路径"""
    return get_data_dir() / "config.json"


class Config:
    """配置管理类"""

    _instance: Optional['Config'] = None

    DEFAULT_CONFIG = {
        "intercept_enabled": True,
        "auto_start": False,
        "minimize_to_tray": False,
        "notification_duration": 5,
        "auto_scan_interval_minutes": 10,
        "scan_paths": [],
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
        """加载配置"""
        if self._config_path.exists():
            try:
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                    # 合并默认配置
                    return {**self.DEFAULT_CONFIG, **saved}
            except (json.JSONDecodeError, IOError):
                pass
        return self.DEFAULT_CONFIG.copy()

    def save(self):
        """保存配置"""
        with open(self._config_path, 'w', encoding='utf-8') as f:
            json.dump(self._config, f, indent=2, ensure_ascii=False)

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        return self._config.get(key, default)

    def set(self, key: str, value: Any, auto_save: bool = True):
        """设置配置项"""
        self._config[key] = value
        if auto_save:
            self.save()

    @property
    def intercept_enabled(self) -> bool:
        """拦截是否启用"""
        return self._config.get("intercept_enabled", True)

    @intercept_enabled.setter
    def intercept_enabled(self, value: bool):
        self.set("intercept_enabled", value)

    @property
    def scan_paths(self) -> list:
        """扫描路径列表"""
        return self._config.get("scan_paths", [])

    @scan_paths.setter
    def scan_paths(self, value: list):
        self.set("scan_paths", value)


# 全局配置实例
config = Config()
