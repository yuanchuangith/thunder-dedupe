#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Decision popup shown after intercepting a download link.
"""
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QWidget,
)

from core.clipboard_monitor import clipboard_monitor
from core.index_manager import index_manager
from db.database import db
from utils.config import config
from utils.logger import logger


class DecisionPopup(QDialog):
    """Popup that lets the user allow or block the intercepted link."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        link_content: str = "",
        av_code: str = "",
        source: str = "clipboard",
    ):
        super().__init__(parent)

        self._link_content = link_content
        self._av_code = av_code or ""
        self._source = source
        self._result: Optional[str] = None
        self._status = "unparsed"

        self._setup_window()
        self._setup_ui()
        self._check_exists()

        duration = config.get("notification_duration", 5)
        self._auto_close_timer = QTimer(self)
        self._auto_close_timer.timeout.connect(self._auto_ignore)
        self._auto_close_timer.start(duration * 1000)

    def _setup_window(self):
        self.setWindowTitle("检测到下载链接")
        self.setFixedSize(420, 260)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint
        )

        screen = self.screen()
        if screen:
            geometry = screen.availableGeometry()
            x = geometry.x() + (geometry.width() - self.width()) // 2
            y = geometry.y() + (geometry.height() - self.height()) // 2
            self.move(x, y)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        title_frame = QFrame()
        title_frame.setStyleSheet(
            """
            QFrame {
                background: #3498db;
                border-radius: 8px;
            }
            """
        )
        title_layout = QHBoxLayout(title_frame)
        title_layout.setContentsMargins(15, 10, 15, 10)

        icon_label = QLabel("T")
        icon_label.setStyleSheet("font-size: 20px; color: white; font-weight: bold;")
        title_layout.addWidget(icon_label)

        title_text = QLabel("检测到下载链接")
        title_text.setStyleSheet(
            """
            QLabel {
                color: white;
                font-size: 16px;
                font-weight: bold;
            }
            """
        )
        title_layout.addWidget(title_text)
        title_layout.addStretch()
        layout.addWidget(title_frame)

        info_frame = QFrame()
        info_frame.setStyleSheet(
            """
            QFrame {
                background: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 8px;
            }
            """
        )
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(15, 15, 15, 15)
        info_layout.setSpacing(10)

        code_layout = QHBoxLayout()
        code_label = QLabel("番号:")
        code_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        code_layout.addWidget(code_label)

        self.code_value = QLabel(self._av_code or "未解析")
        self.code_value.setStyleSheet(
            "color: #27ae60; font-size: 16px; font-weight: bold;"
        )
        code_layout.addWidget(self.code_value)
        code_layout.addStretch()
        info_layout.addLayout(code_layout)

        status_layout = QHBoxLayout()
        status_label = QLabel("状态:")
        status_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        status_layout.addWidget(status_label)

        self.status_value = QLabel("检查中...")
        self.status_value.setStyleSheet("color: #7f8c8d;")
        status_layout.addWidget(self.status_value)
        status_layout.addStretch()
        info_layout.addLayout(status_layout)

        location_layout = QHBoxLayout()
        location_label = QLabel("位置:")
        location_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        location_layout.addWidget(location_label)

        self.location_value = QLabel("")
        self.location_value.setWordWrap(True)
        self.location_value.setStyleSheet("color: #555;")
        location_layout.addWidget(self.location_value, 1)
        info_layout.addLayout(location_layout)

        layout.addWidget(info_frame)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.allow_btn = QPushButton("放行下载")
        self.allow_btn.setFixedHeight(40)
        self._set_allow_button_style("#27ae60", "#2ecc71")
        self.allow_btn.clicked.connect(self._allow)
        btn_layout.addWidget(self.allow_btn)

        self.block_btn = QPushButton("拦截")
        self.block_btn.setFixedHeight(40)
        self.block_btn.setStyleSheet(
            """
            QPushButton {
                background: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background: #c0392b;
            }
            """
        )
        self.block_btn.clicked.connect(self._block)
        btn_layout.addWidget(self.block_btn)

        self.ignore_btn = QPushButton("忽略")
        self.ignore_btn.setFixedHeight(40)
        self.ignore_btn.setStyleSheet(
            """
            QPushButton {
                background: #7f8c8d;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background: #95a5a6;
            }
            """
        )
        self.ignore_btn.clicked.connect(self._ignore)
        btn_layout.addWidget(self.ignore_btn)

        layout.addLayout(btn_layout)

    def _set_allow_button_style(self, background: str, hover: str):
        self.allow_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: {background};
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background: {hover};
            }}
            """
        )

    def _check_exists(self):
        if not self._av_code:
            self.code_value.setText("未解析")
            self.code_value.setStyleSheet(
                "color: #f39c12; font-size: 16px; font-weight: bold;"
            )
            self.status_value.setText("未解析番号，等待手动放行")
            self.status_value.setStyleSheet("color: #f39c12; font-weight: bold;")
            self.location_value.setText("放行后才会交给迅雷解析当前磁力链接")
            self.allow_btn.setText("放行给迅雷")
            self._set_allow_button_style("#3498db", "#2980b9")
            self._status = "unparsed"
            return

        result = index_manager.search(self._av_code)
        if result:
            self.status_value.setText("已存在")
            self.status_value.setStyleSheet("color: #27ae60; font-weight: bold;")
            self.location_value.setText(result["file_path"])
            self.block_btn.setText("拒绝重复")
            self.block_btn.setStyleSheet(
                """
                QPushButton {
                    background: #e74c3c;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: #c0392b;
                }
                """
            )
            self._status = "found"
            return

        self.status_value.setText("未下载")
        self.status_value.setStyleSheet("color: #3498db; font-weight: bold;")
        self.location_value.setText("无")
        self.allow_btn.setText("允许下载")
        self._set_allow_button_style("#3498db", "#2980b9")
        self._status = "not_found"

    def _display_code(self) -> str:
        return self._av_code or "未解析链接"

    def _allow(self):
        self._result = "allow"
        self._log_decision("allow")
        self._stop_timer()
        self.accept()

        clipboard_monitor.restore_link()
        logger.info(f"放行下载: {self._display_code()}，链接已恢复到剪贴板")

    def _block(self):
        self._result = "block"
        self._log_decision("block")
        self._stop_timer()
        self.reject()

        clipboard_monitor.keep_blocked()
        logger.info(f"拦截下载: {self._display_code()}，剪贴板保持清空")

    def _ignore(self):
        self._result = "ignore"
        self._log_decision("ignore")
        self._stop_timer()
        self.reject()

        clipboard_monitor.keep_blocked()
        logger.info(f"忽略下载: {self._display_code()}")

    def _auto_ignore(self):
        self._result = "ignore"
        self._log_decision("ignore", user_decision=False)
        self._stop_timer()
        self.reject()

        clipboard_monitor.keep_blocked()
        logger.info(f"超时忽略: {self._display_code()}")

    def _stop_timer(self):
        if self._auto_close_timer:
            self._auto_close_timer.stop()

    def _log_decision(self, action: str, user_decision: bool = True):
        db.execute(
            """
            INSERT INTO intercept_logs
            (av_code, source, file_name, status, user_action, user_decision)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                self._av_code or None,
                self._source,
                self._link_content[:100],
                self._status,
                action,
                user_decision,
            ),
        )

    def get_result(self) -> str:
        return self._result or "ignore"

    def is_allowed(self) -> bool:
        return self._result == "allow"


def show_decision_popup(
    parent: Optional[QWidget] = None,
    link_content: str = "",
    av_code: str = "",
    source: str = "clipboard",
) -> str:
    """Show the popup and return the user's decision."""
    popup = DecisionPopup(parent, link_content, av_code, source)
    popup.exec()
    return popup.get_result()
