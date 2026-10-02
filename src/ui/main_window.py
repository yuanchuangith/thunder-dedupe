#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Application main window.
"""
import os
from typing import Callable, Dict

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from db.migrations import init_database
from ui.home_page import HomePage
from utils.config import config
from utils.logger import logger


HOME_TAB_TITLE = "\u4e3b\u9875"
FILE_LIST_TAB_TITLE = "\u6587\u4ef6\u5217\u8868"
FILE_HISTORY_TAB_TITLE = "\u6587\u4ef6\u5386\u53f2"
COMPARE_TAB_TITLE = "\u5bf9\u6bd4"
DECODE_TAB_TITLE = "Lada\u89e3\u7801"
DUPLICATE_TAB_TITLE = "\u91cd\u590d\u68c0\u6d4b"
CONFIG_TAB_TITLE = "\u914d\u7f6e"
RULE_TAB_TITLE = "\u89c4\u5219"
VIDEO_SIMILARITY_TAB_TITLE = "\u89c6\u9891\u76f8\u4f3c\u5ea6"
CONSOLE_TAB_TITLE = "\u7cfb\u7edf\u65e5\u5fd7"
ABOUT_TAB_TITLE = "\u5173\u4e8e"


class MainWindow(QMainWindow):
    """Application main window."""

    def __init__(self):
        super().__init__()

        init_database()

        self._lazy_tabs: Dict[int, Dict[str, object]] = {}
        self.file_list_page = None
        self.file_history_page = None
        self.compare_page = None
        self.decode_page = None
        self.duplicate_page = None
        self.config_page = None
        self.rule_page = None
        self.video_similarity_page = None
        self.console_page = None

        self._setup_window()
        self._setup_ui()
        self._load_icon()

    def _setup_window(self):
        self.setWindowTitle("\u8fc5\u96f7\u53bb\u91cd\u52a9\u624b")
        self.setMinimumSize(1100, 760)
        self.resize(1280, 900)

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
        self.tab_widget.addTab(self.home_page, HOME_TAB_TITLE)

        self._add_lazy_tab("file_list_page", self._create_file_list_page, FILE_LIST_TAB_TITLE)
        self._add_lazy_tab("file_history_page", self._create_file_history_page, FILE_HISTORY_TAB_TITLE)
        self._add_lazy_tab("compare_page", self._create_compare_page, COMPARE_TAB_TITLE)
        self._add_lazy_tab("decode_page", self._create_decode_page, DECODE_TAB_TITLE)
        self._add_lazy_tab("duplicate_page", self._create_duplicate_page, DUPLICATE_TAB_TITLE)
        self._add_lazy_tab("config_page", self._create_config_page, CONFIG_TAB_TITLE)
        self._add_lazy_tab("rule_page", self._create_rule_page, RULE_TAB_TITLE)
        self._add_lazy_tab(
            "video_similarity_page",
            self._create_video_similarity_page,
            VIDEO_SIMILARITY_TAB_TITLE,
        )
        self._add_lazy_tab("console_page", self._create_console_page, CONSOLE_TAB_TITLE)

        self.tab_widget.addTab(self._create_about_page(), ABOUT_TAB_TITLE)
        self.tab_widget.currentChanged.connect(self._ensure_lazy_tab_loaded)

        layout.addWidget(self.tab_widget)

        self.home_page.scan_completed_signal.connect(self._on_scan_completed)

    def _add_lazy_tab(self, attr_name: str, factory: Callable[[], QWidget], title: str):
        placeholder = self._create_lazy_placeholder(title)
        index = self.tab_widget.addTab(placeholder, title)
        self._lazy_tabs[index] = {
            "attr_name": attr_name,
            "factory": factory,
            "title": title,
        }

    def _create_lazy_placeholder(self, title: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet(
            """
            QLabel {
                color: #2c3e50;
                font-size: 18px;
                font-weight: bold;
            }
            """
        )
        layout.addWidget(title_label)

        hint_label = QLabel("\u9996\u6b21\u70b9\u5f00\u65f6\u518d\u52a0\u8f7d\uff0c\u4ee5\u7f29\u77ed\u542f\u52a8\u65f6\u95f4")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label.setStyleSheet(
            """
            QLabel {
                color: #7f8c8d;
                font-size: 13px;
            }
            """
        )
        layout.addWidget(hint_label)

        return widget

    def _ensure_lazy_tab_loaded(self, index: int):
        page_info = self._lazy_tabs.get(index)
        if not page_info:
            return

        attr_name = page_info["attr_name"]
        if getattr(self, attr_name) is not None:
            return

        logger.info(f"Lazy loading tab: {attr_name}")
        page = page_info["factory"]()
        setattr(self, attr_name, page)

        self.tab_widget.blockSignals(True)
        self.tab_widget.removeTab(index)
        self.tab_widget.insertTab(index, page, page_info["title"])
        self.tab_widget.setCurrentIndex(index)
        self.tab_widget.blockSignals(False)

    def _create_file_list_page(self) -> QWidget:
        from ui.file_list_page import FileListPage

        return FileListPage()

    def _create_file_history_page(self) -> QWidget:
        from ui.file_history_page import FileHistoryPage

        return FileHistoryPage()

    def _create_compare_page(self) -> QWidget:
        from ui.compare_page import ComparePage

        return ComparePage()

    def _create_decode_page(self) -> QWidget:
        from ui.decode_page import DecodePage
        import ui.decode_page_overrides  # noqa: F401

        return DecodePage()

    def _create_duplicate_page(self) -> QWidget:
        from ui.duplicate_page import DuplicatePage

        return DuplicatePage()

    def _create_config_page(self) -> QWidget:
        from ui.config_page import ConfigPage

        return ConfigPage()

    def _create_rule_page(self) -> QWidget:
        from ui.rule_page import RulePage

        return RulePage()

    def _create_video_similarity_page(self) -> QWidget:
        from ui.video_similarity_page import VideoSimilarityPage

        return VideoSimilarityPage()

    def _create_console_page(self) -> QWidget:
        from ui.console_page import ConsolePage

        return ConsolePage()

    def _on_scan_completed(self):
        for attr_name in ("file_list_page", "file_history_page", "duplicate_page"):
            page = getattr(self, attr_name, None)
            if page is not None:
                page.refresh()

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

        title_label = QLabel("\u8fc5\u96f7\u53bb\u91cd\u52a9\u624b")
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

        title = QLabel("\u8fc5\u96f7\u53bb\u91cd\u52a9\u624b")
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

        desc = QLabel(
            "\u4e00\u6b3e\u684c\u9762\u7aef\u4e0b\u8f7d\u53bb\u91cd\u5de5\u5177\uff0c"
            "\u901a\u8fc7\u756a\u53f7\u8bc6\u522b\u5df2\u4e0b\u8f7d\u5185\u5bb9\u3002"
        )
        desc.setStyleSheet(info_style)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)

        layout.addSpacing(10)

        features = QLabel(
            "\u907f\u514d\u91cd\u590d\u4e0b\u8f7d\uff0c\u8282\u7701\u65f6\u95f4\u548c\u5e26\u5bbd\u3002"
        )
        features.setStyleSheet(info_style)
        features.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(features)

        layout.addSpacing(30)

        version = QLabel("\u7248\u672c: 1.0.0")
        version.setStyleSheet(info_style)
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        layout.addSpacing(10)

        author = QLabel("\u672c\u5730\u8fd0\u884c\uff0c\u6570\u636e\u5b89\u5168\u3002")
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

                logger.info(f"\u5df2\u52a0\u8f7d\u81ea\u5b9a\u4e49\u56fe\u6807: {icon_path}")
            except Exception as exc:
                logger.warning(f"\u52a0\u8f7d\u56fe\u6807\u5931\u8d25: {exc}")
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
