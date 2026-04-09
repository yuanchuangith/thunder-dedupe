#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Decision popup shown after intercepting a download link.
"""
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QWidget,
    QMessageBox,
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
        super().__init__(None)

        self._link_content = link_content
        self._av_code = av_code or ""
        self._source = source
        self._result: Optional[str] = None
        self._status = "unparsed"
        self._existing_info: Optional[dict] = None

        self._setup_window()
        self._setup_ui()
        self._check_exists()

        duration = config.get("notification_duration", 5)
        self._auto_close_timer = QTimer(self)
        self._auto_close_timer.timeout.connect(self._auto_ignore)
        self._auto_close_timer.start(duration * 1000)

    def _setup_window(self):
        self.setWindowTitle("检测到下载链接")
        self.setFixedSize(420, 280)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(True)

        screen = self.screen() or QApplication.primaryScreen()
        if screen:
            geometry = screen.availableGeometry()
            x = geometry.x() + (geometry.width() - self.width()) // 2
            y = geometry.y() + (geometry.height() - self.height()) // 2
            self.move(x, y)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Title frame
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

        # Info frame
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

        # AV Code row
        code_layout = QHBoxLayout()
        self.code_label = QLabel("番号:")
        self.code_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        code_layout.addWidget(self.code_label)

        self.code_value = QLabel(self._av_code or "未解析")
        self.code_value.setStyleSheet(
            "color: #27ae60; font-size: 16px; font-weight: bold;"
        )
        code_layout.addWidget(self.code_value)
        code_layout.addStretch()
        info_layout.addLayout(code_layout)

        # Status row
        status_layout = QHBoxLayout()
        self.status_label = QLabel("状态:")
        self.status_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        status_layout.addWidget(self.status_label)

        self.status_value = QLabel("检查中...")
        self.status_value.setStyleSheet("color: #7f8c8d;")
        status_layout.addWidget(self.status_value)
        status_layout.addStretch()
        info_layout.addLayout(status_layout)

        # Location row
        location_layout = QHBoxLayout()
        self.location_label = QLabel("位置:")
        self.location_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        location_layout.addWidget(self.location_label)

        self.location_value = QLabel("")
        self.location_value.setWordWrap(True)
        self.location_value.setStyleSheet("color: #555;")
        location_layout.addWidget(self.location_value, 1)
        info_layout.addLayout(location_layout)

        layout.addWidget(info_frame)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.allow_btn = QPushButton("放行下载")
        self.allow_btn.setFixedHeight(40)
        self._set_allow_button_style("#27ae60", "#2ecc71", enabled=True)
        self.allow_btn.clicked.connect(self._on_allow_clicked)
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

    def _set_allow_button_style(self, background: str, hover: str, enabled: bool = True):
        """Set allow button style with optional disabled state."""
        if enabled:
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
            self.allow_btn.setEnabled(True)
        else:
            self.allow_btn.setStyleSheet(
                """
                QPushButton {
                    background: #bdc3c7;
                    color: #7f8c8d;
                    border: none;
                    border-radius: 4px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background: #bdc3c7;
                }
                """
            )
            self.allow_btn.setEnabled(True)  # Keep enabled to show confirm dialog

    def _apply_exists_style(self):
        """Apply red warning style for existing files (file_index)."""
        # Red style for labels
        red_label_style = "font-weight: bold; color: #c0392b;"
        red_value_style = "color: #e74c3c; font-size: 16px; font-weight: bold;"
        red_location_style = "color: #e74c3c;"

        self.code_label.setStyleSheet(red_label_style)
        self.code_value.setStyleSheet(red_value_style)
        self.status_label.setStyleSheet(red_label_style)
        self.status_value.setStyleSheet(red_value_style)
        self.location_label.setStyleSheet(red_label_style)
        self.location_value.setStyleSheet(red_location_style)

        # Gray out allow button
        self.allow_btn.setText("允许下载")
        self._set_allow_button_style("#bdc3c7", "#bdc3c7", enabled=False)

        # Warning style for block button
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

    def _apply_history_exists_style(self):
        """Apply orange warning style for history existing files."""
        # Orange style for labels
        orange_label_style = "font-weight: bold; color: #d35400;"
        orange_value_style = "color: #e67e22; font-size: 16px; font-weight: bold;"
        orange_location_style = "color: #e67e22;"

        self.code_label.setStyleSheet(orange_label_style)
        self.code_value.setStyleSheet(orange_value_style)
        self.status_label.setStyleSheet(orange_label_style)
        self.status_value.setStyleSheet(orange_value_style)
        self.location_label.setStyleSheet(orange_label_style)
        self.location_value.setStyleSheet(orange_location_style)

        # Orange allow button
        self.allow_btn.setText("允许下载")
        self._set_allow_button_style("#e67e22", "#d35400", enabled=True)

        self.block_btn.setText("拦截")
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

    def _apply_history_deleted_style(self):
        """Apply gray warning style for history deleted files - needs confirmation."""
        # Gray style for labels
        gray_label_style = "font-weight: bold; color: #7f8c8d;"
        gray_value_style = "color: #95a5a6; font-size: 16px; font-weight: bold;"
        gray_location_style = "color: #95a5a6;"

        self.code_label.setStyleSheet(gray_label_style)
        self.code_value.setStyleSheet(gray_value_style)
        self.status_label.setStyleSheet(gray_label_style)
        self.status_value.setStyleSheet(gray_value_style)
        self.location_label.setStyleSheet(gray_label_style)
        self.location_value.setStyleSheet(gray_location_style)

        # Gray allow button (needs confirmation)
        self.allow_btn.setText("允许下载")
        self._set_allow_button_style("#bdc3c7", "#bdc3c7", enabled=False)

        self.block_btn.setText("拦截")
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

    def _apply_not_exists_style(self):
        """Apply normal style for non-existing files."""
        self.code_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        self.code_value.setStyleSheet("color: #27ae60; font-size: 16px; font-weight: bold;")
        self.status_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        self.status_value.setStyleSheet("color: #3498db; font-weight: bold;")
        self.location_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        self.location_value.setStyleSheet("color: #555;")

        self.allow_btn.setText("允许下载")
        self._set_allow_button_style("#3498db", "#2980b9", enabled=True)

        self.block_btn.setText("拦截")
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
            self._existing_info = result
            self.location_value.setText(result.get("file_path") or "未知")

            if result.get("match_source") == "file_index":
                # 文件索引中存在 - 红色警告
                self.status_value.setText("已存在（文件索引）")
                self._status = "found"
                self._apply_exists_style()
            elif result.get("match_source") == "file_history":
                if result.get("is_deleted"):
                    # 历史表中存在但已删除 - 灰色提示
                    self.status_value.setText("历史存在（已删除）")
                    self._status = "history_deleted"
                    self._apply_history_deleted_style()
                else:
                    # 历史表中存在且正常 - 橙色警告
                    self.status_value.setText("历史存在")
                    self._status = "history_found"
                    self._apply_history_exists_style()
            else:
                # 兼容旧数据
                self.status_value.setText("已存在")
                self._status = "found"
                self._apply_exists_style()
            return

        self.status_value.setText("未下载")
        self.location_value.setText("无")
        self._apply_not_exists_style()
        self._status = "not_found"

    def _on_allow_clicked(self):
        """Handle allow button click - show confirmation if file exists."""
        if self._status in {"found", "history_found", "history_deleted"} and self._existing_info:
            existing_label = "已有文件"
            prompt_text = "文件已存在，是否确认下载？"

            if self._status == "found":
                existing_label = "文件索引"
                prompt_text = "该番号在文件索引中存在，是否确认下载？"
            elif self._status == "history_deleted":
                existing_label = "历史记录（已删除）"
                prompt_text = "该番号在历史记录中存在但文件已删除，是否仍然下载？"
            elif self._status == "history_found":
                existing_label = "历史记录"
                prompt_text = "该番号在历史记录中存在，是否仍然下载？"

            reply = QMessageBox.question(
                self,
                "确认下载",
                f"{prompt_text}\n\n"
                f"番号: {self._av_code}\n"
                f"{existing_label}: {self._existing_info.get('file_path', '未知')}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply != QMessageBox.StandardButton.Yes:
                return  # User cancelled

        self._allow()

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
            (av_code, source, file_name, status, user_action, user_decision, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self._av_code or None,
                self._source,
                self._link_content[:100],
                self._status,
                action,
                user_decision,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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
