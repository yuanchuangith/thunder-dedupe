#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Logging helpers.

Recent log lines are kept in memory for the UI, while structured program logs
are buffered and written to JSON files every five minutes.
"""
from __future__ import annotations

import atexit
import json
import logging
import sys
from collections import deque
from datetime import datetime
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Dict, List, Optional

from utils.config import get_data_dir

try:
    from PyQt6.QtCore import QtMsgType, qInstallMessageHandler
except ImportError:  # pragma: no cover - fallback for non-Qt environments
    QtMsgType = None
    qInstallMessageHandler = None


MAX_IN_MEMORY_LOGS = 2000
JSON_FLUSH_INTERVAL_SECONDS = 5 * 60

_recent_logs = deque(maxlen=MAX_IN_MEMORY_LOGS)
_recent_logs_lock = Lock()

_pending_json_logs: List[Dict[str, object]] = []
_pending_json_logs_lock = Lock()

_qt_handler_installed = False
_flush_thread: Optional[Thread] = None
_flush_stop_event = Event()


def get_program_log_dir() -> Path:
    """Return the directory used for JSON program logs."""
    log_dir = get_data_dir() / "logs" / "program"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


class BufferedAppLogHandler(logging.Handler):
    """Store recent text logs for the UI and queue JSON log records for disk."""

    def emit(self, record: logging.LogRecord):
        try:
            message = self.format(record)
        except Exception:
            message = record.getMessage()

        with _recent_logs_lock:
            _recent_logs.append(message)

        with _pending_json_logs_lock:
            _pending_json_logs.append(self._build_payload(record))

    @staticmethod
    def _build_payload(record: logging.LogRecord) -> Dict[str, object]:
        timestamp = datetime.fromtimestamp(record.created).astimezone()
        return {
            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "process_id": record.process,
            "thread": record.threadName,
        }


def get_recent_logs(limit: Optional[int] = None) -> List[str]:
    """Return recent in-memory log lines."""
    with _recent_logs_lock:
        logs = list(_recent_logs)

    if limit is None or limit >= len(logs):
        return logs
    return logs[-limit:]


def clear_recent_logs():
    """Clear recent in-memory log lines shown in the UI."""
    with _recent_logs_lock:
        _recent_logs.clear()


def _write_stderr(message: str):
    try:
        sys.stderr.write(f"{message}\n")
    except Exception:
        pass


def _drain_pending_json_logs() -> List[Dict[str, object]]:
    with _pending_json_logs_lock:
        pending_logs = list(_pending_json_logs)
        _pending_json_logs.clear()
    return pending_logs


def _restore_pending_json_logs(entries: List[Dict[str, object]]):
    if not entries:
        return

    with _pending_json_logs_lock:
        _pending_json_logs[:0] = entries


def _append_entries_to_json_file(file_path: Path, entries: List[Dict[str, object]]):
    existing_entries: List[Dict[str, object]] = []

    if file_path.exists():
        try:
            with file_path.open("r", encoding="utf-8") as file:
                loaded = json.load(file)
            if isinstance(loaded, list):
                existing_entries = loaded
            else:
                _write_stderr(f"[logger] Invalid JSON log format, resetting file: {file_path}")
        except Exception as exc:
            _write_stderr(f"[logger] Failed to read JSON log file {file_path}: {exc}")

    temp_path = file_path.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(existing_entries + entries, file, ensure_ascii=False, indent=2)
    temp_path.replace(file_path)


def flush_json_logs():
    """Flush buffered structured logs to daily JSON files."""
    pending_logs = _drain_pending_json_logs()
    if not pending_logs:
        return

    grouped_entries: Dict[str, List[Dict[str, object]]] = {}
    for entry in pending_logs:
        date_key = str(entry.get("timestamp", ""))[:10] or datetime.now().strftime("%Y-%m-%d")
        grouped_entries.setdefault(date_key, []).append(entry)

    failed_entries: List[Dict[str, object]] = []

    for date_key, entries in grouped_entries.items():
        file_path = get_program_log_dir() / f"{date_key}.json"
        try:
            _append_entries_to_json_file(file_path, entries)
        except Exception as exc:
            _write_stderr(f"[logger] Failed to flush logs to {file_path}: {exc}")
            failed_entries.extend(entries)

    _restore_pending_json_logs(failed_entries)


def _json_flush_worker():
    while not _flush_stop_event.wait(JSON_FLUSH_INTERVAL_SECONDS):
        flush_json_logs()


def _ensure_background_flush_thread():
    global _flush_thread

    if _flush_thread and _flush_thread.is_alive():
        return

    _flush_stop_event.clear()
    _flush_thread = Thread(
        target=_json_flush_worker,
        name="program-log-flusher",
        daemon=True,
    )
    _flush_thread.start()


def shutdown_logger():
    """Flush buffered logs before the process exits."""
    _flush_stop_event.set()

    if _flush_thread and _flush_thread.is_alive():
        _flush_thread.join(timeout=1.0)

    flush_json_logs()


def _install_qt_message_handler(target_logger: logging.Logger):
    """Forward Qt internal messages to the main logger."""
    global _qt_handler_installed

    if _qt_handler_installed or qInstallMessageHandler is None or QtMsgType is None:
        return

    def qt_message_handler(mode, context, message):
        category = getattr(context, "category", "") or ""
        log_message = f"{category}: {message}" if category else message

        if mode == QtMsgType.QtDebugMsg:
            level = logging.DEBUG
        elif mode == QtMsgType.QtWarningMsg:
            level = logging.WARNING
        elif mode == QtMsgType.QtCriticalMsg:
            level = logging.ERROR
        elif mode == QtMsgType.QtFatalMsg:
            level = logging.CRITICAL
        else:
            level = logging.INFO

        target_logger.log(level, log_message)

    qInstallMessageHandler(qt_message_handler)
    _qt_handler_installed = True


def setup_logger(name: str = "thunder-dedupe") -> logging.Logger:
    """Set up the shared application logger."""
    target_logger = logging.getLogger(name)
    target_logger.setLevel(logging.DEBUG)
    target_logger.propagate = False

    if target_logger.handlers:
        return target_logger

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S")
    )
    target_logger.addHandler(console_handler)

    buffered_handler = BufferedAppLogHandler()
    buffered_handler.setLevel(logging.DEBUG)
    buffered_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    target_logger.addHandler(buffered_handler)

    _ensure_background_flush_thread()
    _install_qt_message_handler(target_logger)
    target_logger.info(f"系统日志已启动: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return target_logger


atexit.register(shutdown_logger)

logger = setup_logger()
