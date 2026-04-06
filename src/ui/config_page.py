#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置页 - 扫描目录和设置项（美化版）
"""
import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QFrame, QCheckBox, QSpinBox, QFileDialog,
    QMessageBox, QLineEdit, QScrollArea, QSizePolicy, QApplication
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap, QFont

from utils.config import config
from db.database import db
from utils.logger import logger


class ConfigPage(QWidget):
    """配置页"""

    # 统一的样式常量
    CARD_STYLE = """
        QFrame {
            background: #ffffff;
            border: 1px solid #e1e5e9;
            border-radius: 12px;
        }
    """

    TITLE_STYLE = """
        QLabel {
            font-size: 15px;
            font-weight: bold;
            color: #2c3e50;
            padding: 5px 0px;
        }
    """

    SECTION_BG = "#f5f7fa"
    CARD_BG = "#ffffff"
    PRIMARY_COLOR = "#3498db"
    SUCCESS_COLOR = "#27ae60"
    DANGER_COLOR = "#e74c3c"
    TEXT_COLOR = "#2c3e50"
    BORDER_COLOR = "#e1e5e9"

    def __init__(self):
        super().__init__()
        self._setup_ui()
        self._load_paths()

    def _setup_ui(self):
        """设置界面"""
        # 使用滚动区域作为主容器
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: #f5f7fa;
            }
            QScrollBar:vertical {
                background: #f0f0f0;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::vertical::handle {
                background: #c0c0c0;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::vertical::handle:hover {
                background: #a0a0a0;
            }
        """)

        # 内容容器
        container = QWidget()
        container.setStyleSheet("background: #f5f7fa;")

        layout = QVBoxLayout(container)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(20)

        # 页面标题
        page_title = QLabel("系统配置")
        page_title.setStyleSheet("""
            QLabel {
                font-size: 20px;
                font-weight: bold;
                color: #2c3e50;
                padding: 10px 0px 15px 0px;
            }
        """)
        layout.addWidget(page_title)

        # 扫描目录区域
        paths_card = self._create_paths_card()
        layout.addWidget(paths_card)

        # 图标设置区域
        icon_card = self._create_icon_card()
        layout.addWidget(icon_card)

        # 其他设置区域
        settings_card = self._create_settings_card()
        layout.addWidget(settings_card)

        layout.addStretch(1)

        # 底部按钮区域
        buttons_card = self._create_buttons_card()
        layout.addWidget(buttons_card)

        scroll.setWidget(container)

        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def _create_paths_card(self) -> QFrame:
        """创建扫描目录卡片"""
        card = QFrame()
        card.setStyleSheet(self.CARD_STYLE)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        # 标题行（带图标指示）
        title_row = QHBoxLayout()
        title_icon = QLabel("📁")
        title_icon.setStyleSheet("font-size: 18px;")
        title_row.addWidget(title_icon)

        title = QLabel("扫描目录")
        title.setStyleSheet(self.TITLE_STYLE)
        title_row.addWidget(title)
        title_row.addStretch()

        # 统计标签
        self.path_count_label = QLabel("已添加 0 个目录")
        self.path_count_label.setStyleSheet("""
            QLabel {
                color: #7f8c8d;
                font-size: 12px;
            }
        """)
        title_row.addWidget(self.path_count_label)

        layout.addLayout(title_row)

        # 目录列表 - 高度足以显示5项（每项约45px）
        self.path_list = QListWidget()
        self.path_list.setMinimumHeight(250)  # 5项 * 50px
        self.path_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.path_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #e1e5e9;
                background: #f8f9fa;
                border-radius: 8px;
                font-size: 13px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 14px 12px;
                border-bottom: 1px solid #e1e5e9;
                background: #ffffff;
                margin: 2px;
                border-radius: 6px;
            }
            QListWidget::item:hover {
                background: #f0f7ff;
            }
            QListWidget::item:selected {
                background: #e3f2fd;
                border: 1px solid #3498db;
            }
        """)
        layout.addWidget(self.path_list)

        # 操作按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        add_btn = QPushButton("  + 添加目录")
        add_btn.setMinimumSize(140, 40)
        add_btn.setStyleSheet("""
            QPushButton {
                background: #27ae60;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background: #2ecc71;
            }
            QPushButton:pressed {
                background: #1e8449;
            }
        """)
        add_btn.clicked.connect(self._add_path)
        btn_row.addWidget(add_btn)

        remove_btn = QPushButton("  - 删除选中")
        remove_btn.setMinimumSize(140, 40)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: #e74c3c;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background: #ec7063;
            }
            QPushButton:pressed {
                background: #c0392b;
            }
        """)
        remove_btn.clicked.connect(self._remove_selected_path)
        btn_row.addWidget(remove_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        # 提示信息
        tip = QLabel("提示：添加目录后，请返回主页点击「扫描目录」按钮建立文件索引")
        tip.setStyleSheet("""
            QLabel {
                color: #95a5a6;
                font-size: 12px;
                padding: 8px 0px 0px 0px;
            }
        """)
        layout.addWidget(tip)

        return card

    def _create_icon_card(self) -> QFrame:
        """创建图标设置卡片"""
        card = QFrame()
        card.setStyleSheet(self.CARD_STYLE)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(15)

        # 标题行
        title_row = QHBoxLayout()
        title_icon = QLabel("🎨")
        title_icon.setStyleSheet("font-size: 18px;")
        title_row.addWidget(title_icon)

        title = QLabel("图标设置")
        title.setStyleSheet(self.TITLE_STYLE)
        title_row.addWidget(title)
        title_row.addStretch()
        layout.addLayout(title_row)

        # 任务栏图标
        tray_row = QHBoxLayout()
        tray_row.setSpacing(12)

        tray_label = QLabel("任务栏图标")
        tray_label.setMinimumWidth(100)
        tray_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: #2c3e50;
            }
        """)
        tray_row.addWidget(tray_label)

        self.tray_icon_edit = QLineEdit()
        self.tray_icon_edit.setPlaceholderText("选择图标文件 (.ico / .png)")
        self.tray_icon_edit.setText(config.get("tray_icon_path", ""))
        self.tray_icon_edit.setMinimumHeight(36)
        self.tray_icon_edit.setStyleSheet("""
            QLineEdit {
                border: 1px solid #e1e5e9;
                border-radius: 8px;
                padding: 8px 12px;
                background: #f8f9fa;
                font-size: 13px;
                color: #2c3e50;
            }
            QLineEdit:focus {
                border: 2px solid #3498db;
                background: #ffffff;
            }
        """)
        tray_row.addWidget(self.tray_icon_edit, 1)

        tray_btn = QPushButton("浏览")
        tray_btn.setMinimumSize(80, 36)
        tray_btn.setStyleSheet("""
            QPushButton {
                background: #3498db;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #5dade2;
            }
        """)
        tray_btn.clicked.connect(self._select_tray_icon)
        tray_row.addWidget(tray_btn)

        layout.addLayout(tray_row)

        # 桌面图标
        desktop_row = QHBoxLayout()
        desktop_row.setSpacing(12)

        desktop_label = QLabel("桌面图标")
        desktop_label.setMinimumWidth(100)
        desktop_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: #2c3e50;
            }
        """)
        desktop_row.addWidget(desktop_label)

        self.desktop_icon_edit = QLineEdit()
        self.desktop_icon_edit.setPlaceholderText("选择图标文件 (.ico)")
        self.desktop_icon_edit.setText(config.get("desktop_icon_path", ""))
        self.desktop_icon_edit.setMinimumHeight(36)
        self.desktop_icon_edit.setStyleSheet("""
            QLineEdit {
                border: 1px solid #e1e5e9;
                border-radius: 8px;
                padding: 8px 12px;
                background: #f8f9fa;
                font-size: 13px;
                color: #2c3e50;
            }
            QLineEdit:focus {
                border: 2px solid #3498db;
                background: #ffffff;
            }
        """)
        desktop_row.addWidget(self.desktop_icon_edit, 1)

        desktop_btn = QPushButton("浏览")
        desktop_btn.setMinimumSize(80, 36)
        desktop_btn.setStyleSheet("""
            QPushButton {
                background: #3498db;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #5dade2;
            }
        """)
        desktop_btn.clicked.connect(self._select_desktop_icon)
        desktop_row.addWidget(desktop_btn)

        layout.addLayout(desktop_row)

        # 提示
        tip = QLabel("💡 支持 .ico 和 .png 格式，推荐使用 .ico 格式以获得最佳显示效果")
        tip.setStyleSheet("""
            QLabel {
                color: #95a5a6;
                font-size: 12px;
                padding: 5px 0px;
            }
        """)
        layout.addWidget(tip)

        return card

    def _create_settings_card(self) -> QFrame:
        """创建其他设置卡片"""
        card = QFrame()
        card.setStyleSheet(self.CARD_STYLE)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(15)

        # 标题行
        title_row = QHBoxLayout()
        title_icon = QLabel("⚙️")
        title_icon.setStyleSheet("font-size: 18px;")
        title_row.addWidget(title_icon)

        title = QLabel("其他设置")
        title.setStyleSheet(self.TITLE_STYLE)
        title_row.addWidget(title)
        title_row.addStretch()
        layout.addLayout(title_row)

        # 开机自启动
        auto_row = QHBoxLayout()
        self.auto_start_cb = QCheckBox("开机自启动")
        self.auto_start_cb.setMinimumHeight(32)
        self.auto_start_cb.setStyleSheet("""
            QCheckBox {
                font-size: 13px;
                color: #2c3e50;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 2px solid #bdc3c7;
                background: #ffffff;
            }
            QCheckBox::indicator:checked {
                background: #3498db;
                border: 2px solid #3498db;
            }
            QCheckBox::indicator:hover {
                border: 2px solid #3498db;
            }
        """)
        self.auto_start_cb.setChecked(config.get("auto_start", False))
        auto_row.addWidget(self.auto_start_cb)
        auto_row.addStretch()
        layout.addLayout(auto_row)

        # 最小化到托盘
        tray_row = QHBoxLayout()
        self.tray_cb = QCheckBox("最小化到托盘")
        self.tray_cb.setMinimumHeight(32)
        self.tray_cb.setStyleSheet("""
            QCheckBox {
                font-size: 13px;
                color: #2c3e50;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 2px solid #bdc3c7;
                background: #ffffff;
            }
            QCheckBox::indicator:checked {
                background: #3498db;
                border: 2px solid #3498db;
            }
            QCheckBox::indicator:hover {
                border: 2px solid #3498db;
            }
        """)
        self.tray_cb.setChecked(config.get("minimize_to_tray", False))
        tray_row.addWidget(self.tray_cb)
        tray_row.addStretch()
        layout.addLayout(tray_row)

        # 弹窗通知时长
        duration_row = QHBoxLayout()
        duration_row.setSpacing(12)

        duration_label = QLabel("弹窗通知时长")
        duration_label.setMinimumWidth(100)
        duration_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: #2c3e50;
            }
        """)
        duration_row.addWidget(duration_label)

        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(1, 30)
        self.duration_spin.setValue(config.get("notification_duration", 5))
        self.duration_spin.setSuffix(" 秒")
        self.duration_spin.setMinimumSize(120, 36)
        self.duration_spin.setStyleSheet("""
            QSpinBox {
                border: 1px solid #e1e5e9;
                border-radius: 8px;
                padding: 6px 10px;
                background: #f8f9fa;
                font-size: 13px;
                color: #2c3e50;
            }
            QSpinBox:focus {
                border: 2px solid #3498db;
                background: #ffffff;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                width: 20px;
                border-radius: 4px;
                background: #e1e5e9;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background: #3498db;
            }
        """)
        duration_row.addWidget(self.duration_spin)
        duration_row.addStretch()
        layout.addLayout(duration_row)

        # 自动扫描间隔
        auto_scan_row = QHBoxLayout()
        auto_scan_row.setSpacing(12)

        auto_scan_label = QLabel("自动扫描间隔")
        auto_scan_label.setMinimumWidth(100)
        auto_scan_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: #2c3e50;
            }
        """)
        auto_scan_row.addWidget(auto_scan_label)

        self.auto_scan_interval_spin = QSpinBox()
        self.auto_scan_interval_spin.setRange(1, 1440)
        self.auto_scan_interval_spin.setValue(config.get("auto_scan_interval_minutes", 10))
        self.auto_scan_interval_spin.setSuffix(" 分钟")
        self.auto_scan_interval_spin.setMinimumSize(120, 36)
        self.auto_scan_interval_spin.setStyleSheet("""
            QSpinBox {
                border: 1px solid #e1e5e9;
                border-radius: 8px;
                padding: 6px 10px;
                background: #f8f9fa;
                font-size: 13px;
                color: #2c3e50;
            }
            QSpinBox:focus {
                border: 2px solid #3498db;
                background: #ffffff;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                width: 20px;
                border-radius: 4px;
                background: #e1e5e9;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background: #3498db;
            }
        """)
        auto_scan_row.addWidget(self.auto_scan_interval_spin)

        auto_scan_tip = QLabel("（监控运行时会按这个间隔自动扫描已配置目录）")
        auto_scan_tip.setStyleSheet("""
            QLabel {
                color: #95a5a6;
                font-size: 12px;
            }
        """)
        auto_scan_row.addWidget(auto_scan_tip)

        auto_scan_row.addStretch()
        layout.addLayout(auto_scan_row)

        # WebSocket 端口
        ws_port_row = QHBoxLayout()
        ws_port_row.setSpacing(12)

        ws_port_label = QLabel("WebSocket 端口")
        ws_port_label.setMinimumWidth(100)
        ws_port_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: #2c3e50;
            }
        """)
        ws_port_row.addWidget(ws_port_label)

        self.ws_port_spin = QSpinBox()
        self.ws_port_spin.setRange(1024, 65535)
        self.ws_port_spin.setValue(config.get("ws_port", 9876))
        self.ws_port_spin.setMinimumSize(120, 36)
        self.ws_port_spin.setStyleSheet("""
            QSpinBox {
                border: 1px solid #e1e5e9;
                border-radius: 8px;
                padding: 6px 10px;
                background: #f8f9fa;
                font-size: 13px;
                color: #2c3e50;
            }
            QSpinBox:focus {
                border: 2px solid #3498db;
                background: #ffffff;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                width: 20px;
                border-radius: 4px;
                background: #e1e5e9;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background: #3498db;
            }
        """)
        ws_port_row.addWidget(self.ws_port_spin)

        # 端口说明
        ws_port_tip = QLabel("（浏览器扩展连接端口，修改后需重启监控）")
        ws_port_tip.setStyleSheet("""
            QLabel {
                color: #95a5a6;
                font-size: 12px;
            }
        """)
        ws_port_row.addWidget(ws_port_tip)

        ws_port_row.addStretch()
        layout.addLayout(ws_port_row)

        return card

    def _create_buttons_card(self) -> QFrame:
        """创建底部按钮卡片"""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: #ffffff;
                border: 1px solid #e1e5e9;
                border-radius: 12px;
            }
        """)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(15)

        save_btn = QPushButton("✓ 保存配置")
        save_btn.setMinimumSize(140, 42)
        save_btn.setStyleSheet("""
            QPushButton {
                background: #3498db;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #5dade2;
            }
            QPushButton:pressed {
                background: #2980b9;
            }
        """)
        save_btn.clicked.connect(self._save_config)
        layout.addWidget(save_btn)

        reset_btn = QPushButton("↺ 重置配置")
        reset_btn.setMinimumSize(140, 42)
        reset_btn.setStyleSheet("""
            QPushButton {
                background: #e74c3c;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #ec7063;
            }
            QPushButton:pressed {
                background: #c0392b;
            }
        """)
        reset_btn.clicked.connect(self._reset_config)
        layout.addWidget(reset_btn)

        layout.addStretch()
        return card

    def _load_paths(self):
        """加载扫描目录"""
        rows = db.query("SELECT id, path, enabled FROM scan_paths WHERE enabled = 1")

        self.path_list.clear()
        for row in rows:
            item = QListWidgetItem(row['path'])
            item.setData(Qt.ItemDataRole.UserRole, row['id'])
            self.path_list.addItem(item)

        # 更新统计标签
        self.path_count_label.setText(f"已添加 {len(rows)} 个目录")

    def _add_path(self):
        """添加扫描目录"""
        path = QFileDialog.getExistingDirectory(
            self,
            "选择扫描目录",
            "",
            QFileDialog.Option.ShowDirsOnly
        )

        if path:
            existing = db.query_one(
                "SELECT id FROM scan_paths WHERE path = ?",
                (path,)
            )

            if existing:
                QMessageBox.warning(self, "警告", "该目录已添加")
                return

            db.execute(
                "INSERT INTO scan_paths (path, enabled) VALUES (?, 1)",
                (path,)
            )

            self._load_paths()

            QMessageBox.information(
                self,
                "成功",
                f"已添加目录:\n{path}\n\n请返回主页点击「扫描目录」按钮建立索引"
            )

    def _remove_selected_path(self):
        """删除选中的目录"""
        current = self.path_list.currentItem()
        if current:
            path_id = current.data(Qt.ItemDataRole.UserRole)
            db.execute("DELETE FROM scan_paths WHERE id = ?", (path_id,))
            self._load_paths()
        else:
            QMessageBox.warning(self, "提示", "请先选择要删除的目录")

    def _select_tray_icon(self):
        """选择任务栏图标"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择任务栏图标",
            "",
            "图标文件 (*.ico *.png);;所有文件 (*.*)"
        )
        if path:
            self.tray_icon_edit.setText(path)

    def _select_desktop_icon(self):
        """选择桌面图标"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择桌面图标",
            "",
            "图标文件 (*.ico);;所有文件 (*.*)"
        )
        if path:
            self.desktop_icon_edit.setText(path)

    def _save_config(self):
        """保存配置"""
        config.set("auto_start", self.auto_start_cb.isChecked())
        config.set("minimize_to_tray", self.tray_cb.isChecked())
        config.set("notification_duration", self.duration_spin.value())
        config.set("auto_scan_interval_minutes", self.auto_scan_interval_spin.value())
        config.set("ws_port", self.ws_port_spin.value())

        tray_icon_path = self.tray_icon_edit.text().strip()
        desktop_icon_path = self.desktop_icon_edit.text().strip()

        config.set("tray_icon_path", tray_icon_path)
        config.set("desktop_icon_path", desktop_icon_path)

        if tray_icon_path and os.path.exists(tray_icon_path):
            self._apply_tray_icon(tray_icon_path)

        self._apply_runtime_settings()

        QMessageBox.information(
            self,
            "成功",
            "配置已保存\n\n自动扫描间隔会立即生效；WebSocket 端口修改后需要重启监控才能生效",
        )

    def _apply_runtime_settings(self):
        """将可热更新的配置立即同步到运行中的界面。"""
        app = QApplication.instance()
        if not app:
            return

        for widget in app.topLevelWidgets():
            home_page = getattr(widget, "home_page", None)
            if home_page and hasattr(home_page, "reload_auto_scan_interval"):
                home_page.reload_auto_scan_interval()
                break

    def _apply_tray_icon(self, icon_path: str):
        """应用任务栏图标"""
        try:
            from PyQt6.QtGui import QIcon

            app = QApplication.instance()
            if app:
                icon = QIcon(icon_path)
                app.setWindowIcon(icon)

                for widget in app.topLevelWidgets():
                    widget.setWindowIcon(icon)

                logger.info(f"已应用任务栏图标: {icon_path}")
        except Exception as e:
            logger.error(f"应用图标失败: {e}")

    def _reset_config(self):
        """重置配置"""
        reply = QMessageBox.question(
            self,
            "确认重置",
            "确定要重置所有配置吗？\n这将清空所有扫描目录和文件索引。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            db.execute("DELETE FROM scan_paths")
            self._load_paths()

            self.auto_start_cb.setChecked(False)
            self.tray_cb.setChecked(False)
            self.duration_spin.setValue(5)
            self.auto_scan_interval_spin.setValue(10)
            self.ws_port_spin.setValue(9876)

            self.tray_icon_edit.clear()
            self.desktop_icon_edit.clear()

            config.set("auto_start", False, auto_save=False)
            config.set("minimize_to_tray", False, auto_save=False)
            config.set("notification_duration", 5, auto_save=False)
            config.set("auto_scan_interval_minutes", 10, auto_save=False)
            config.set("ws_port", 9876, auto_save=False)
            config.set("tray_icon_path", "", auto_save=False)
            config.set("desktop_icon_path", "", auto_save=False)
            config.save()

            db.execute("DELETE FROM file_index")
            self._apply_runtime_settings()

            QMessageBox.information(self, "成功", "配置已重置")
