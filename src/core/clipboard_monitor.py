#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Clipboard monitor.

The monitor immediately clears detected download links from the clipboard so
Thunder cannot continue parsing them until the user explicitly allows it.
"""
from typing import Optional, Callable

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from core.av_parser import AVParser
from utils.config import config
from utils.logger import logger


class ClipboardMonitor(QObject):
    """Monitor clipboard changes and block download links by default."""

    link_detected = pyqtSignal(str, str)  # link content, parsed av code (may be empty)

    def __init__(self):
        super().__init__()
        self._parser = AVParser()
        self._running = False
        self._last_content = ""
        self._callback: Optional[Callable[[str, str], None]] = None

        self._saved_link: Optional[str] = None
        self._saved_av_code: Optional[str] = None
        self._suppressed_content: Optional[str] = None

        self._clipboard = None
        self._signal_connected = False

    def _ensure_clipboard(self):
        if self._clipboard:
            return self._clipboard

        app = QApplication.instance()
        if app:
            self._clipboard = app.clipboard()

        return self._clipboard

    def start(self, callback: Optional[Callable[[str, str], None]] = None):
        """Start listening for clipboard changes."""
        if self._running:
            logger.warning("剪贴板监听已启动")
            return

        self._callback = callback
        self._running = True

        app = QApplication.instance()
        if not app:
            logger.warning("无法获取 QApplication 实例，剪贴板监听未启动")
            return

        self._clipboard = app.clipboard()
        if not self._signal_connected:
            self._clipboard.dataChanged.connect(self._on_clipboard_changed)
            self._signal_connected = True

        self._last_content = self._clipboard.text()
        logger.info("剪贴板监听已启动")

    def stop(self):
        """Stop listening for clipboard changes."""
        self._running = False

        if self._clipboard and self._signal_connected:
            try:
                self._clipboard.dataChanged.disconnect(self._on_clipboard_changed)
            except Exception:
                pass
            finally:
                self._signal_connected = False

        self._callback = None
        logger.info("剪贴板监听已停止")

    def is_running(self) -> bool:
        """Return whether the monitor is running."""
        return self._running

    def _on_clipboard_changed(self):
        """React to clipboard changes as early as possible."""
        if not self._running or not config.intercept_enabled or not self._clipboard:
            return

        try:
            current_content = self._clipboard.text()
            if current_content == self._last_content:
                return

            if self._suppressed_content is not None and current_content == self._suppressed_content:
                self._last_content = current_content
                self._suppressed_content = None
                logger.debug("Skipping self-restored clipboard content")
                return

            self._last_content = current_content
            self._process_content(current_content)
        except Exception as exc:
            logger.warning(f"剪贴板处理出错: {exc}")

    def _process_content(self, content: str):
        """Block all supported download links until the user decides."""
        if not content:
            return

        if not self._parser.is_download_link(content):
            return

        logger.info(f"检测到下载链接: {content[:50]}...")

        self._clear_clipboard_immediately()

        av_code = self._parser.parse(content)
        if av_code:
            logger.info(f"解析到番号: {av_code}")
        else:
            logger.info("未解析出番号，保持拦截并等待用户放行")

        self._saved_link = content
        self._saved_av_code = av_code
        self._last_content = ""

        emitted_code = av_code or ""
        self.link_detected.emit(content, emitted_code)

        if self._callback:
            self._callback(content, emitted_code)

    def stage_link(self, link: str, av_code: str = ""):
        """Stage an externally intercepted link so allow can restore it later."""
        self._saved_link = link
        self._saved_av_code = av_code or None
        self._last_content = ""

    def _clear_clipboard_immediately(self):
        """Clear clipboard text immediately to stop external readers."""
        try:
            if self._ensure_clipboard():
                self._clipboard.setText("")
                self._clipboard.clear()
                logger.debug("剪贴板已即时清理")
        except Exception as exc:
            logger.warning(f"清理剪贴板失败: {exc}")

    def restore_link(self):
        """Restore the blocked link after the user chooses allow."""
        if not self._saved_link:
            return

        try:
            if self._ensure_clipboard():
                self._suppressed_content = self._saved_link
                self._last_content = self._saved_link
                self._clipboard.setText(self._saved_link)
                logger.info(f"已恢复链接到剪贴板: {self._saved_link[:50]}...")
        except Exception as exc:
            logger.warning(f"恢复剪贴板失败: {exc}")
        finally:
            self._saved_link = None
            self._saved_av_code = None

    def keep_blocked(self):
        """Keep the current intercepted link blocked."""
        self._saved_link = None
        self._saved_av_code = None
        self._last_content = ""
        logger.info("保持拦截，剪贴板不会恢复下载链接")

    def _restore_clipboard(self, content: str):
        """Restore arbitrary clipboard content."""
        try:
            if self._ensure_clipboard():
                self._clipboard.setText(content)
                self._last_content = content
                logger.debug("剪贴板已恢复")
        except Exception as exc:
            logger.warning(f"恢复剪贴板失败: {exc}")

    def get_saved_link(self) -> Optional[str]:
        """Return the currently blocked link."""
        return self._saved_link

    def get_saved_av_code(self) -> Optional[str]:
        """Return the parsed AV code for the blocked link."""
        return self._saved_av_code

    def get_current_content(self) -> str:
        """Return current clipboard text."""
        try:
            if self._ensure_clipboard():
                return self._clipboard.text()
        except Exception:
            pass
        return ""


clipboard_monitor = ClipboardMonitor()
