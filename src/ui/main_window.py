#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
主窗口。
"""
import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QIcon, QPixmap
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QTabWidget, QVBoxLayout, QWidget

from db.migrations import init_database
from ui.config_page import ConfigPage
from ui.console_page import ConsolePage
from ui.duplicate_page import DuplicatePage
from ui.file_list_page import FileListPage
from ui.file_history_page import FileHistoryPage
from ui.home_page import HomePage
from ui.rule_page import RulePage
from core.index_manager import index_manager
from utils.config import config
from utils.logger import logger


class MainWindow(QMainWindow):
    """Application main window."""

    def __init__(self):
        super().__init__()

        init_database()
        index_manager.refresh_search_index()

        self._setup_window()
        self._setup_ui()
        self._load_icon()

    def _setup_window(self):
        self.setWindowTitle("迅雷去重助手")
        self.setMinimumSize(800, 600)
        self.resize(900, 700)

        screen = self.screen().availableGeometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._create_header())

        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setStyleSheet(
            """
            QTabWidget::pane {
                border: 1px solid #ddd;
                background: #fff;
            }
            QTabBar::tab {
                background: #f5f5f5;
                padding: 8px 20px;
                margin: 2px;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            QTabBar::tab:selected {
                background: #fff;
                border-bottom-color: #fff;
            }
            QTabBar::tab:hover:!selected {
                background: #e8e8e8;
            }
            """
        )

        self.home_page = HomePage()
        self.tab_widget.addTab(self.home_page, "主页")

        self.file_list_page = FileListPage()
        self.tab_widget.addTab(self.file_list_page, "文件列表")

        self.file_history_page = FileHistoryPage()
        self.tab_widget.addTab(self.file_history_page, "文件历史")

        self.duplicate_page = DuplicatePage()
        self.tab_widget.addTab(self.duplicate_page, "重复检测")

        self.config_page = ConfigPage()
        self.tab_widget.addTab(self.config_page, "配置")

        self.rule_page = RulePage()
        self.tab_widget.addTab(self.rule_page, "规则")

        self.console_page = ConsolePage()
        self.tab_widget.addTab(self.console_page, "系统日志")

        self.tab_widget.addTab(self._create_about_page(), "关于")

        layout.addWidget(self.tab_widget)

        self.home_page.scan_completed_signal.connect(self._on_scan_completed)

    def _on_scan_completed(self):
        self.file_list_page.refresh()
        self.file_history_page.refresh()
        self.duplicate_page.refresh()

    def _create_header(self) -> QWidget:
        header = QWidget()
        header.setFixedHeight(60)
        header.setStyleSheet(
            """
            QWidget {
                background: #2c3e50;
            }
            """
        )

        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 10, 20, 10)

        title_label = QLabel("迅雷去重助手")
        title_label.setStyleSheet(
            """
            QLabel {
                color: #fff;
                font-size: 18px;
                font-weight: bold;
            }
            """
        )
        layout.addWidget(title_label)

        layout.addStretch()

        version_label = QLabel("v1.0.0")
        version_label.setStyleSheet(
            """
            QLabel {
                color: #bdc3c7;
                font-size: 12px;
            }
            """
        )
        layout.addWidget(version_label)

        return header

    def _create_about_page(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        info_style = """
            QLabel {
                font-size: 14px;
                color: #555;
            }
        """

        title = QLabel("迅雷去重助手")
        title.setStyleSheet(
            """
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #2c3e50;
            }
            """
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        layout.addSpacing(20)

        desc = QLabel("一款桌面端下载去重工具，通过番号识别已下载内容。")
        desc.setStyleSheet(info_style)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)

        layout.addSpacing(10)

        features = QLabel("避免重复下载，节省时间和带宽。")
        features.setStyleSheet(info_style)
        features.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(features)

        layout.addSpacing(30)

        version = QLabel("版本: 1.0.0")
        version.setStyleSheet(info_style)
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        layout.addSpacing(10)

        author = QLabel("本地运行，数据安全。")
        author.setStyleSheet(info_style)
        author.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(author)

        return widget

    def _load_icon(self):
        icon_path = config.get("tray_icon_path", "")

        if icon_path and os.path.exists(icon_path):
            try:
                icon = QIcon(icon_path)
                self.setWindowIcon(icon)

                app = QApplication.instance()
                if app:
                    app.setWindowIcon(icon)

                logger.info(f"已加载自定义图标: {icon_path}")
            except Exception as exc:
                logger.warning(f"加载图标失败: {exc}")
                self._load_default_icon()
        else:
            self._load_default_icon()

    def _load_default_icon(self):
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)

        from PyQt6.QtGui import QColor, QPainter

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(52, 152, 219))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(4, 4, 56, 56)

        painter.setPen(QColor(255, 255, 255))
        font = QFont("Arial", 28, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "T")
        painter.end()

        icon = QIcon(pixmap)
        self.setWindowIcon(icon)

        app = QApplication.instance()
        if app:
            app.setWindowIcon(icon)
