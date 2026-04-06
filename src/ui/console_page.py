#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
系统日志页签。
"""
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QPlainTextEdit,
    QFrame,
)

from utils.logger import clear_recent_logs, get_recent_logs


class ConsolePage(QWidget):
    """Display recent in-memory program and Qt logs."""

    REFRESH_INTERVAL_MS = 1000
    MAX_LINES = 500

    def __init__(self):
        super().__init__()
        self._setup_ui()
        self._refresh_logs()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_logs)
        self.refresh_timer.start(self.REFRESH_INTERVAL_MS)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        header = QFrame()
        header.setStyleSheet(
            """
            QFrame {
                background: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 8px;
            }
            """
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(15, 12, 15, 12)

        title = QLabel("系统日志")
        title.setStyleSheet(
            """
            QLabel {
                color: #2c3e50;
                font-size: 16px;
                font-weight: bold;
            }
            """
        )
        header_layout.addWidget(title)

        header_layout.addStretch()

        self.summary_label = QLabel("最新在上")
        self.summary_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        header_layout.addWidget(self.summary_label)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setMinimumHeight(32)
        refresh_btn.setStyleSheet(
            """
            QPushButton {
                background: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background: #2980b9;
            }
            """
        )
        refresh_btn.clicked.connect(self._refresh_logs)
        header_layout.addWidget(refresh_btn)

        clear_btn = QPushButton("清空显示")
        clear_btn.setMinimumHeight(32)
        clear_btn.setStyleSheet(
            """
            QPushButton {
                background: #7f8c8d;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background: #95a5a6;
            }
            """
        )
        clear_btn.clicked.connect(self._clear_logs)
        header_layout.addWidget(clear_btn)

        layout.addWidget(header)

        hint = QLabel("显示程序运行日志与 Qt 系统消息，最新在上；日志会每 5 分钟批量写入 JSON 文件。")
        hint.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        layout.addWidget(hint)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log_view.setStyleSheet(
            """
            QPlainTextEdit {
                background: #111827;
                color: #d1d5db;
                border: 1px solid #1f2937;
                border-radius: 8px;
                padding: 10px;
            }
            """
        )
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.log_view.setFont(font)
        layout.addWidget(self.log_view, 1)

    def _refresh_logs(self):
        recent_logs = get_recent_logs(self.MAX_LINES)
        display_logs = list(reversed(recent_logs))
        self.log_view.setPlainText("\n".join(display_logs))
        self.summary_label.setText(f"最新在上 · 共显示 {len(display_logs)} 条")
        cursor = self.log_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        self.log_view.setTextCursor(cursor)

    def _clear_logs(self):
        clear_recent_logs()
        self._refresh_logs()
