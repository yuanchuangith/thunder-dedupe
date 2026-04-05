#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
主窗口
"""
import os

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QApplication
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QFont, QPixmap

from ui.home_page import HomePage
from ui.config_page import ConfigPage
from ui.rule_page import RulePage
from ui.file_list_page import FileListPage
from ui.duplicate_page import DuplicatePage
from db.migrations import init_database
from utils.config import config
from utils.logger import logger


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()

        # 初始化数据库
        init_database()

        self._setup_window()
        self._setup_ui()
        self._load_icon()

    def _setup_window(self):
        """设置窗口属性"""
        self.setWindowTitle("迅雷去重助手")
        self.setMinimumSize(800, 600)
        self.resize(900, 700)

        # 窗口居中
        screen = self.screen().availableGeometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def _setup_ui(self):
        """设置界面"""
        # 主容器
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题栏
        header = self._create_header()
        layout.addWidget(header)

        # Tab页面
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setStyleSheet("""
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
        """)

        # 主页
        self.home_page = HomePage()
        self.tab_widget.addTab(self.home_page, "主页")

        # 文件列表页
        self.file_list_page = FileListPage()
        self.tab_widget.addTab(self.file_list_page, "文件列表")

        # 重复检测页
        self.duplicate_page = DuplicatePage()
        self.tab_widget.addTab(self.duplicate_page, "重复检测")

        # 配置页
        self.config_page = ConfigPage()
        self.tab_widget.addTab(self.config_page, "配置")

        # 规则页
        self.rule_page = RulePage()
        self.tab_widget.addTab(self.rule_page, "规则")

        # 关于页
        about_widget = self._create_about_page()
        self.tab_widget.addTab(about_widget, "关于")

        layout.addWidget(self.tab_widget)

        # 连接扫描完成信号，刷新其他页面
        self.home_page.scan_completed_signal.connect(self._on_scan_completed)

    def _on_scan_completed(self):
        """扫描完成时刷新其他页面"""
        self.file_list_page.refresh()
        self.duplicate_page.refresh()

    def _create_header(self) -> QWidget:
        """创建标题栏"""
        header = QWidget()
        header.setFixedHeight(60)
        header.setStyleSheet("""
            QWidget {
                background: #2c3e50;
            }
        """)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 10, 20, 10)

        # 标题
        title_label = QLabel("迅雷去重助手")
        title_label.setStyleSheet("""
            QLabel {
                color: #fff;
                font-size: 18px;
                font-weight: bold;
            }
        """)
        layout.addWidget(title_label)

        layout.addStretch()

        # 版本
        version_label = QLabel("v1.0.0")
        version_label.setStyleSheet("""
            QLabel {
                color: #bdc3c7;
                font-size: 12px;
            }
        """)
        layout.addWidget(version_label)

        return header

    def _create_about_page(self) -> QWidget:
        """创建关于页面"""
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
        title.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #2c3e50;
            }
        """)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        layout.addSpacing(20)

        desc = QLabel("一款桌面端下载去重工具，通过番号识别已下载内容")
        desc.setStyleSheet(info_style)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)

        layout.addSpacing(10)

        features = QLabel("避免重复下载，节省时间和带宽")
        features.setStyleSheet(info_style)
        features.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(features)

        layout.addSpacing(30)

        version = QLabel("版本: 1.0.0")
        version.setStyleSheet(info_style)
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        layout.addSpacing(10)

        author = QLabel("本地运行，数据安全")
        author.setStyleSheet(info_style)
        author.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(author)

        return widget

    def _load_icon(self):
        """加载并应用图标"""
        # 获取保存的图标路径
        icon_path = config.get("tray_icon_path", "")

        if icon_path and os.path.exists(icon_path):
            try:
                icon = QIcon(icon_path)
                self.setWindowIcon(icon)

                # 同时设置应用图标
                app = QApplication.instance()
                if app:
                    app.setWindowIcon(icon)

                logger.info(f"已加载自定义图标: {icon_path}")
            except Exception as e:
                logger.warning(f"加载图标失败: {e}")
                self._load_default_icon()
        else:
            self._load_default_icon()

    def _load_default_icon(self):
        """加载默认图标"""
        # 创建一个简单的默认图标
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)

        from PyQt6.QtGui import QPainter, QColor, QFont
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 画圆形背景
        painter.setBrush(QColor(52, 152, 219))  # #3498db
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(4, 4, 56, 56)

        # 画文字
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