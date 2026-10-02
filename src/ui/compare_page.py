#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
对比页 - 对比未解码和已解码目录的番号
"""
import os
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QLineEdit, QComboBox,
    QMessageBox, QProgressBar, QFileDialog, QTabWidget,
    QListWidget, QListWidgetItem, QSplitter, QDialog,
    QTextEdit, QScrollArea, QMenu
)

from db.database import db
from core.av_parser import AVParser
from utils.logger import logger
from utils.utils import format_file_size
from ui.dual_video_window import DualVideoCompareWindow


class ComparePage(QWidget):
    """对比页面 - 对比未解码和已解码目录"""

    def __init__(self):
        super().__init__()
        self._parser = AVParser()
        self._scanning = False
        self._compare_result = {}
        self._file_data = {}  # 存储文件详细信息用于删除操作
        self._setup_ui()
        self._load_config()

    def _setup_ui(self):
        """设置界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 说明
        desc_frame = QFrame()
        desc_frame.setStyleSheet("""
            QFrame {
                background: #fff3cd;
                border: 1px solid #ffc107;
                border-radius: 8px;
            }
        """)
        desc_layout = QVBoxLayout(desc_frame)
        desc_layout.setContentsMargins(15, 10, 15, 10)
        desc_label = QLabel(
            "功能说明：对比「未解码目录」和「已解码目录」中的番号。\n"
            "未解码文件：如 hhd800.com@WAAA-217-C_X1080X.restored → 番号 WAAA-217\n"
            "已解码文件：如 JUFE-591-C.restored.mp4 → 番号 JUFE-591\n"
            "提示：双击蓝色文件名播放文件，右键点击可打开文件夹定位文件"
        )
        desc_label.setStyleSheet("color: #856404; font-size: 13px;")
        desc_layout.addWidget(desc_label)
        layout.addWidget(desc_frame)

        # 目录配置区域
        config_frame = self._create_config_frame()
        layout.addWidget(config_frame)

        # 操作按钮区域
        action_frame = self._create_action_frame()
        layout.addWidget(action_frame)

        # 统计区域
        stats_frame = self._create_stats_frame()
        layout.addWidget(stats_frame)

        # 状态提示框
        self.status_frame = QFrame()
        self.status_frame.setStyleSheet("""
            QFrame {
                background: #d4edda;
                border: 1px solid #28a745;
                border-radius: 8px;
            }
        """)
        self.status_frame.setVisible(False)  # 默认隐藏

        status_layout = QHBoxLayout(self.status_frame)
        status_layout.setContentsMargins(15, 8, 15, 8)

        self.status_icon_label = QLabel("✓")
        self.status_icon_label.setStyleSheet("font-size: 16px; color: #28a745;")
        status_layout.addWidget(self.status_icon_label)

        self.status_text_label = QLabel("")
        self.status_text_label.setStyleSheet("font-size: 13px; color: #155724;")
        status_layout.addWidget(self.status_text_label, 1)

        # 关闭按钮
        close_status_btn = QPushButton("×")
        close_status_btn.setFixedSize(24, 24)
        close_status_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #6c757d;
                border: none;
                font-size: 16px;
            }
            QPushButton:hover { color: #dc3545; }
        """)
        close_status_btn.clicked.connect(self._hide_status)
        status_layout.addWidget(close_status_btn)

        layout.addWidget(self.status_frame)

        # 结果表格区域（使用TabWidget分类显示）
        self.result_tabs = QTabWidget()
        self.result_tabs.setMinimumHeight(300)  # 设置最小高度
        self.result_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #dee2e6;
                background: #fff;
                min-height: 250px;
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
        """)

        # 两边都有
        self.both_table = self._create_result_table("两边都有")
        self.result_tabs.addTab(self.both_table, "两边都有")

        # 只有未解码有
        self.undecoded_only_table = self._create_result_table("只有未解码有")
        self.result_tabs.addTab(self.undecoded_only_table, "只有未解码有")

        # 只有已解码有
        self.decoded_only_table = self._create_result_table("只有已解码有")
        self.result_tabs.addTab(self.decoded_only_table, "只有已解码有")

        layout.addWidget(self.result_tabs)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                text-align: center;
            }
            QProgressBar::chunk {
                background: #3498db;
            }
        """)
        layout.addWidget(self.progress_bar)

    def _create_config_frame(self) -> QFrame:
        """创建目录配置区域 - 两个目录并排显示"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 8px;
            }
        """)

        main_layout = QHBoxLayout(frame)
        main_layout.setContentsMargins(15, 10, 15, 10)
        main_layout.setSpacing(20)

        # 未解码目录（左侧）
        undecoded_frame = QFrame()
        undecoded_frame.setStyleSheet("""
            QFrame {
                background: #fff;
                border: 1px solid #e74c3c;
                border-radius: 6px;
            }
        """)
        undecoded_layout = QVBoxLayout(undecoded_frame)
        undecoded_layout.setContentsMargins(10, 8, 10, 8)
        undecoded_layout.setSpacing(8)

        undecoded_title = QLabel("未解码目录")
        undecoded_title.setStyleSheet("font-weight: bold; color: #e74c3c; font-size: 13px;")
        undecoded_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        undecoded_layout.addWidget(undecoded_title)

        self.undecoded_list = QListWidget()
        self.undecoded_list.setMaximumHeight(60)  # 限制高度
        self.undecoded_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #dee2e6;
                background: #fff;
                border-radius: 4px;
                font-size: 11px;
            }
        """)
        undecoded_layout.addWidget(self.undecoded_list)

        undecoded_btn_layout = QHBoxLayout()
        add_undecoded_btn = QPushButton("添加")
        add_undecoded_btn.setFixedHeight(28)
        add_undecoded_btn.setStyleSheet("""
            QPushButton {
                background: #27ae60;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background: #2ecc71; }
        """)
        add_undecoded_btn.clicked.connect(self._add_undecoded_path)
        undecoded_btn_layout.addWidget(add_undecoded_btn)

        remove_undecoded_btn = QPushButton("删除")
        remove_undecoded_btn.setFixedHeight(28)
        remove_undecoded_btn.setStyleSheet("""
            QPushButton {
                background: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background: #c0392b; }
        """)
        remove_undecoded_btn.clicked.connect(self._remove_undecoded_path)
        undecoded_btn_layout.addWidget(remove_undecoded_btn)
        undecoded_layout.addLayout(undecoded_btn_layout)

        main_layout.addWidget(undecoded_frame, 1)

        # 已解码目录（右侧）
        decoded_frame = QFrame()
        decoded_frame.setStyleSheet("""
            QFrame {
                background: #fff;
                border: 1px solid #27ae60;
                border-radius: 6px;
            }
        """)
        decoded_layout = QVBoxLayout(decoded_frame)
        decoded_layout.setContentsMargins(10, 8, 10, 8)
        decoded_layout.setSpacing(8)

        decoded_title = QLabel("已解码目录")
        decoded_title.setStyleSheet("font-weight: bold; color: #27ae60; font-size: 13px;")
        decoded_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        decoded_layout.addWidget(decoded_title)

        self.decoded_list = QListWidget()
        self.decoded_list.setMaximumHeight(60)  # 限制高度
        self.decoded_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #dee2e6;
                background: #fff;
                border-radius: 4px;
                font-size: 11px;
            }
        """)
        decoded_layout.addWidget(self.decoded_list)

        decoded_btn_layout = QHBoxLayout()
        add_decoded_btn = QPushButton("添加")
        add_decoded_btn.setFixedHeight(28)
        add_decoded_btn.setStyleSheet("""
            QPushButton {
                background: #27ae60;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background: #2ecc71; }
        """)
        add_decoded_btn.clicked.connect(self._add_decoded_path)
        decoded_btn_layout.addWidget(add_decoded_btn)

        remove_decoded_btn = QPushButton("删除")
        remove_decoded_btn.setFixedHeight(28)
        remove_decoded_btn.setStyleSheet("""
            QPushButton {
                background: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background: #c0392b; }
        """)
        remove_decoded_btn.clicked.connect(self._remove_decoded_path)
        decoded_btn_layout.addWidget(remove_decoded_btn)
        decoded_layout.addLayout(decoded_btn_layout)

        main_layout.addWidget(decoded_frame, 1)

        return frame

    def _create_action_frame(self) -> QFrame:
        """创建操作按钮区域"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 8px;
            }
        """)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(10)

        # 开始对比按钮
        self.compare_btn = QPushButton("开始对比")
        self.compare_btn.setFixedHeight(36)
        self.compare_btn.setStyleSheet("""
            QPushButton {
                background: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 14px;
            }
            QPushButton:hover { background: #2980b9; }
            QPushButton:disabled { background: #bdc3c7; }
        """)
        self.compare_btn.clicked.connect(self._start_compare)
        layout.addWidget(self.compare_btn)

        # 导出结果按钮
        export_btn = QPushButton("导出结果")
        export_btn.setFixedHeight(36)
        export_btn.setStyleSheet("""
            QPushButton {
                background: #9b59b6;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 14px;
            }
            QPushButton:hover { background: #8e44ad; }
        """)
        export_btn.clicked.connect(self._export_result)
        layout.addWidget(export_btn)

        # 一键删除全部（两边都有）
        delete_all_both_btn = QPushButton("一键删除全部（两边都有）")
        delete_all_both_btn.setFixedHeight(36)
        delete_all_both_btn.setStyleSheet("""
            QPushButton {
                background: #c0392b;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background: #a93226; }
        """)
        delete_all_both_btn.clicked.connect(self._delete_all_both)
        layout.addWidget(delete_all_both_btn)

        layout.addStretch()

        return frame

    def _create_stats_frame(self) -> QFrame:
        """创建统计区域"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: #e8f4f8;
                border: 1px solid #b8daff;
                border-radius: 8px;
            }
        """)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(15, 10, 15, 10)

        self.undecoded_count_label = QLabel("未解码: 0 个番号")
        self.undecoded_count_label.setStyleSheet("color: #e74c3c; font-size: 13px;")
        layout.addWidget(self.undecoded_count_label)

        layout.addStretch()

        self.decoded_count_label = QLabel("已解码: 0 个番号")
        self.decoded_count_label.setStyleSheet("color: #27ae60; font-size: 13px;")
        layout.addWidget(self.decoded_count_label)

        layout.addStretch()

        self.both_count_label = QLabel("两边都有: 0 个")
        self.both_count_label.setStyleSheet("color: #3498db; font-size: 13px; font-weight: bold;")
        layout.addWidget(self.both_count_label)

        layout.addStretch()

        self.undecoded_only_label = QLabel("仅未解码: 0 个")
        self.undecoded_only_label.setStyleSheet("color: #f39c12; font-size: 13px;")
        layout.addWidget(self.undecoded_only_label)

        layout.addStretch()

        self.decoded_only_label = QLabel("仅已解码: 0 个")
        self.decoded_only_label.setStyleSheet("color: #16a085; font-size: 13px;")
        layout.addWidget(self.decoded_only_label)

        return frame

    def _create_result_table(self, title: str) -> QTableWidget:
        """创建结果表格"""
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["番号", "未解码文件", "已解码文件", "状态", "操作"])

        table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #dee2e6;
                background: #fff;
                gridline-color: #dee2e6;
            }
            QHeaderView::section {
                background: #f8f9fa;
                border: 1px solid #dee2e6;
                padding: 8px;
                font-weight: bold;
            }
            QHeaderView::section:last {
                background: #e74c3c;
                color: white;
            }
            QTableWidget::item:hover {
                background: #e8f4f8;
            }
        """)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)

        table.setColumnWidth(0, 120)
        table.setColumnWidth(3, 80)
        table.setColumnWidth(4, 160)  # 操作列宽度增加以容纳两个按钮
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.MultiSelection)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(45)  # 设置默认行高

        # 设置表格最小高度
        table.setMinimumHeight(200)

        # 双击播放文件
        table.cellDoubleClicked.connect(lambda row, col: self._on_table_double_click(table, row, col))

        # 单击文件名打开对比窗口
        table.cellClicked.connect(lambda row, col: self._on_table_single_click(table, row, col))

        # 右键菜单
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(lambda pos: self._show_context_menu(table, pos))

        # 表头点击事件 - 点击操作列头部触发全选
        header.sectionClicked.connect(lambda section: self._on_header_clicked(table, section, title))

        return table

    def _on_header_clicked(self, table: QTableWidget, section: int, table_name: str):
        """表头点击事件"""
        # 只有点击操作列（第4列）才触发
        if section == 4:
            # 全选所有行
            table.selectAll()

    def _on_table_single_click(self, table: QTableWidget, row: int, col: int):
        """表格单击事件 - 打开对比视频窗口"""
        # 只有在"两边都有"表格中才有效
        if table != self.both_table:
            return

        # 第1列是未解码文件，第2列是已解码文件
        if col == 1 or col == 2:
            undecoded_item = table.item(row, 1)
            decoded_item = table.item(row, 2)

            if undecoded_item and decoded_item:
                undecoded_path = undecoded_item.toolTip()
                decoded_path = decoded_item.toolTip()

                # 如果tooltip包含多个路径（换行分隔），取第一个
                if decoded_path and "\n" in decoded_path:
                    decoded_path = decoded_path.split("\n")[0]

                if undecoded_path and decoded_path and decoded_path != "-":
                    self._play_files_for_compare(undecoded_path, decoded_path)

    def _on_table_double_click(self, table: QTableWidget, row: int, col: int):
        """表格双击事件 - 播放单个文件"""
        # 第1列是未解码文件，第2列是已解码文件
        if col == 1 or col == 2:
            item = table.item(row, col)
            if item and item.toolTip():
                file_path = item.toolTip()
                self._play_file(file_path)

    def _show_context_menu(self, table: QTableWidget, pos):
        """显示右键菜单"""
        row = table.rowAt(pos.y())
        col = table.columnAt(pos.x())

        if row < 0 or col < 0:
            return

        # 只在文件列显示右键菜单
        if col == 1 or col == 2:
            item = table.item(row, col)
            if item and item.toolTip() and item.toolTip() != "-":
                file_path = item.toolTip()

                menu = QMenu(self)

                # 播放文件
                play_action = menu.addAction("▶ 播放文件")
                play_action.triggered.connect(lambda: self._play_file(file_path))

                # 打开文件目录选中文件
                open_folder_action = menu.addAction("📂 打开文件目录选中文件")
                open_folder_action.triggered.connect(lambda: self._open_file_location(file_path))

                # 在"两边都有"表格中，添加"同时播放对比"选项
                if table == self.both_table:
                    undecoded_item = table.item(row, 1)
                    decoded_item = table.item(row, 2)

                    # 检查是否两边都有文件
                    undecoded_path = undecoded_item.toolTip() if undecoded_item else None
                    decoded_path = decoded_item.toolTip() if decoded_item else None

                    # 如果tooltip包含多个路径（换行分隔），取第一个
                    if decoded_path and "\n" in decoded_path:
                        decoded_path = decoded_path.split("\n")[0]

                    if undecoded_path and decoded_path and decoded_path != "-":
                        menu.addSeparator()
                        compare_play_action = menu.addAction("🎬 打开双视频对比播放窗口")
                        compare_play_action.triggered.connect(
                            lambda: self._play_files_for_compare(undecoded_path, decoded_path)
                        )

                # 已解码文件列(col==2) - 检查是否可以删除
                if col == 2 and table == self.both_table:
                    # 获取该行对应的未解码文件路径
                    undecoded_item = table.item(row, 1)
                    if undecoded_item and undecoded_item.toolTip():
                        undecoded_file = undecoded_item.toolTip()
                        file_data = self._file_data.get(undecoded_file, {})
                        undecoded_count = file_data.get('undecoded_count', 0)

                        # 如果该番号有 >= 2 个未解码文件，允许删除已解码文件
                        if undecoded_count >= 2:
                            menu.addSeparator()
                            delete_decoded_action = menu.addAction("🗑 删除此已解码文件")
                            delete_decoded_action.triggered.connect(lambda: self._delete_decoded_file(file_path))

                menu.exec(table.mapToGlobal(pos))

    def _play_file(self, file_path: str):
        """播放文件（使用系统默认播放器）"""
        try:
            path = Path(file_path)
            if not path.exists():
                QMessageBox.warning(self, "提示", "文件不存在")
                return

            import subprocess
            import platform

            if platform.system() == "Windows":
                # Windows: 使用默认程序打开文件
                subprocess.run(['start', '', file_path], shell=True, check=False)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(['open', file_path], check=False)
            else:  # Linux
                subprocess.run(['xdg-open', file_path], check=False)

            logger.info(f"播放文件: {file_path}")

        except Exception as e:
            logger.error(f"播放文件失败: {e}")
            QMessageBox.warning(self, "播放失败", f"无法播放文件:\n{str(e)}")

    def _play_files_for_compare(self, undecoded_path: str, decoded_path: str):
        """同时播放两个文件进行对比 - 使用嵌入式双视频播放窗口"""
        try:
            # 检查文件是否存在
            undecoded_exists = Path(undecoded_path).exists()
            decoded_exists = Path(decoded_path).exists()

            if not undecoded_exists and not decoded_exists:
                QMessageBox.warning(self, "提示", "两个文件都不存在")
                return

            # 打开双视频对比窗口
            self._show_status("正在打开双视频对比播放窗口...")

            def on_delete_callback(file_path):
                """删除后的回调 - 刷新对比列表"""
                self._show_status(f"文件已删除: {Path(file_path).name}")
                # 重新对比以更新表格（不弹出完成提示）
                self._start_compare(show_complete_msg=False)

            self.dual_video_window = DualVideoCompareWindow(
                undecoded_path, decoded_path, self,
                delete_callback=on_delete_callback
            )
            self.dual_video_window.show()

            self._show_status("双视频对比播放窗口已打开，默认静音播放")

            logger.info(f"打开双视频对比窗口: 未解码={undecoded_path}, 已解码={decoded_path}")

        except Exception as e:
            logger.error(f"打开双视频对比窗口失败: {e}")
            self._show_status(f"打开失败: {str(e)}", success=False)

    def _open_file_location(self, file_path: str):
        """打开文件所在目录"""
        try:
            path = Path(file_path)
            if not path.exists():
                QMessageBox.warning(self, "提示", "文件不存在")
                return

            import subprocess
            import platform

            if platform.system() == "Windows":
                # Windows: 使用 explorer 打开并选中文件
                subprocess.run(['explorer', '/select,', file_path], check=False)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(['open', '-R', file_path], check=False)
            else:  # Linux
                subprocess.run(['xdg-open', str(path.parent)], check=False)

            logger.info(f"打开文件位置: {file_path}")

        except Exception as e:
            logger.error(f"打开文件位置失败: {e}")
            QMessageBox.warning(self, "打开失败", f"无法打开文件位置:\n{str(e)}")

    def _preview_file_with_fallback(self, file_path: str, parent_dialog=None):
        """预览文件：先尝试播放，失败则打开文件夹选中文件"""
        try:
            path = Path(file_path)
            if not path.exists():
                QMessageBox.warning(self, "提示", "文件不存在，无法预览")
                return

            import subprocess
            import platform

            if platform.system() == "Windows":
                # Windows: 先尝试用默认程序打开
                try:
                    # 使用 start 命令打开文件
                    result = subprocess.run(
                        ['start', '', file_path],
                        shell=True,
                        capture_output=True,
                        timeout=5
                    )
                    logger.info(f"预览文件: {file_path}")
                except subprocess.TimeoutExpired:
                    # 超时则打开文件夹
                    subprocess.run(['explorer', '/select,', file_path], check=False)
                    logger.info(f"播放超时，打开文件夹: {file_path}")
                except Exception:
                    # 其他错误则打开文件夹
                    subprocess.run(['explorer', '/select,', file_path], check=False)
                    logger.info(f"播放失败，打开文件夹: {file_path}")

            elif platform.system() == "Darwin":  # macOS
                subprocess.run(['open', file_path], check=False)
            else:  # Linux
                subprocess.run(['xdg-open', file_path], check=False)

        except Exception as e:
            logger.error(f"预览文件失败: {e}")
            # 最终fallback：打开文件夹
            try:
                self._open_file_location(file_path)
            except:
                QMessageBox.warning(self, "预览失败", f"无法预览文件:\n{str(e)}")

    def _load_config(self):
        """加载配置"""
        # 确保表存在
        self._init_tables()

        # 从数据库加载配置
        undecoded_paths = db.query(
            "SELECT path FROM compare_paths WHERE type = 'undecoded' AND enabled = 1"
        )
        for row in undecoded_paths:
            self.undecoded_list.addItem(row['path'])

        decoded_paths = db.query(
            "SELECT path FROM compare_paths WHERE type = 'decoded' AND enabled = 1"
        )
        for row in decoded_paths:
            self.decoded_list.addItem(row['path'])

    def _init_tables(self):
        """初始化数据库表"""
        db.execute("""
            CREATE TABLE IF NOT EXISTS compare_paths (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                path TEXT NOT NULL UNIQUE,
                enabled INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def _add_undecoded_path(self):
        """添加未解码目录"""
        self._init_tables()
        path = QFileDialog.getExistingDirectory(self, "选择未解码目录")
        if path:
            # 检查是否已存在
            items = [self.undecoded_list.item(i).text() for i in range(self.undecoded_list.count())]
            if path in items:
                QMessageBox.warning(self, "提示", "该目录已添加")
                return

            self.undecoded_list.addItem(path)
            db.execute(
                "INSERT OR IGNORE INTO compare_paths (type, path, enabled) VALUES ('undecoded', ?, 1)",
                (path,)
            )

    def _remove_undecoded_path(self):
        """删除未解码目录"""
        current = self.undecoded_list.currentItem()
        if current:
            path = current.text()
            self.undecoded_list.takeItem(self.undecoded_list.row(current))
            db.execute("DELETE FROM compare_paths WHERE type = 'undecoded' AND path = ?", (path,))

    def _add_decoded_path(self):
        """添加已解码目录"""
        self._init_tables()
        path = QFileDialog.getExistingDirectory(self, "选择已解码目录")
        if path:
            items = [self.decoded_list.item(i).text() for i in range(self.decoded_list.count())]
            if path in items:
                QMessageBox.warning(self, "提示", "该目录已添加")
                return

            self.decoded_list.addItem(path)
            db.execute(
                "INSERT OR IGNORE INTO compare_paths (type, path, enabled) VALUES ('decoded', ?, 1)",
                (path,)
            )

    def _remove_decoded_path(self):
        """删除已解码目录"""
        current = self.decoded_list.currentItem()
        if current:
            path = current.text()
            self.decoded_list.takeItem(self.decoded_list.row(current))
            db.execute("DELETE FROM compare_paths WHERE type = 'decoded' AND path = ?", (path,))

    def _start_compare(self, show_complete_msg: bool = True):
        """开始对比"""
        if self._scanning:
            return

        # 保存是否显示完成提示的标志
        self._show_complete_msg = show_complete_msg

        # 获取目录列表
        undecoded_paths = [self.undecoded_list.item(i).text() for i in range(self.undecoded_list.count())]
        decoded_paths = [self.decoded_list.item(i).text() for i in range(self.decoded_list.count())]

        if not undecoded_paths and not decoded_paths:
            QMessageBox.warning(self, "提示", "请先添加要对比的目录")
            return

        self._scanning = True
        self.compare_btn.setEnabled(False)
        self.compare_btn.setText("对比中...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        thread = threading.Thread(
            target=self._compare_worker,
            args=(undecoded_paths, decoded_paths),
            daemon=True
        )
        thread.start()

        self._check_timer = QTimer()
        self._check_timer.timeout.connect(self._check_compare_status)
        self._check_timer.start(500)

    def _compare_worker(self, undecoded_paths: List[str], decoded_paths: List[str]):
        """对比工作线程"""
        try:
            # 收集未解码目录的番号
            undecoded_avs: Dict[str, List[str]] = {}  # av_code -> [file_paths]
            total_undecoded = len(undecoded_paths)

            for i, path_str in enumerate(undecoded_paths):
                logger.info(f"扫描未解码目录: {path_str}")
                path = Path(path_str)
                if not path.exists():
                    logger.warning(f"目录不存在: {path_str}")
                    continue

                for file_path in path.rglob('*'):
                    if file_path.is_file() and file_path.suffix.lower() in {'.mp4', '.mkv', '.avi', '.wmv', '.flv', '.mov', '.restored', '.mpg', '.mpeg'}:
                        av_code = self._parser.parse_from_filename(file_path.name)
                        if av_code:
                            if av_code not in undecoded_avs:
                                undecoded_avs[av_code] = []
                            undecoded_avs[av_code].append(str(file_path))

                progress = int((i + 1) / max(total_undecoded, 1) * 25)
                self._update_progress(progress)

            logger.info(f"未解码目录找到 {len(undecoded_avs)} 个番号")

            # 收集已解码目录的番号
            decoded_avs: Dict[str, List[str]] = {}  # av_code -> [file_paths]
            total_decoded = len(decoded_paths)

            for i, path_str in enumerate(decoded_paths):
                logger.info(f"扫描已解码目录: {path_str}")
                path = Path(path_str)
                if not path.exists():
                    logger.warning(f"目录不存在: {path_str}")
                    continue

                for file_path in path.rglob('*'):
                    if file_path.is_file() and file_path.suffix.lower() in {'.mp4', '.mkv', '.avi', '.wmv', '.flv', '.mov', '.restored', '.mpg', '.mpeg'}:
                        av_code = self._parser.parse_from_filename(file_path.name)
                        if av_code:
                            if av_code not in decoded_avs:
                                decoded_avs[av_code] = []
                            decoded_avs[av_code].append(str(file_path))

                progress = int(25 + (i + 1) / max(total_decoded, 1) * 25)
                self._update_progress(progress)

            logger.info(f"已解码目录找到 {len(decoded_avs)} 个番号")

            # 对比
            undecoded_set = set(undecoded_avs.keys())
            decoded_set = set(decoded_avs.keys())

            both = undecoded_set & decoded_set  # 两边都有
            undecoded_only = undecoded_set - decoded_set  # 只有未解码有
            decoded_only = decoded_set - undecoded_set  # 只有已解码有

            self._compare_result = {
                'undecoded_avs': undecoded_avs,
                'decoded_avs': decoded_avs,
                'both': sorted(list(both)),
                'undecoded_only': sorted(list(undecoded_only)),
                'decoded_only': sorted(list(decoded_only))
            }

            logger.info(f"对比完成: 两边都有={len(both)}, 仅未解码={len(undecoded_only)}, 仅已解码={len(decoded_only)}")

            self._update_progress(100)

        except Exception as e:
            logger.error(f"对比出错: {e}")
            self._scanning = False

        self._scanning = False

    def _update_progress(self, value: int):
        """更新进度条"""
        QTimer.singleShot(0, lambda: self.progress_bar.setValue(value))

    def _check_compare_status(self):
        """检查对比状态"""
        if not self._scanning:
            self._check_timer.stop()
            self._on_compare_completed()

    def _on_compare_completed(self):
        """对比完成"""
        self.progress_bar.setVisible(False)
        self.compare_btn.setEnabled(True)
        self.compare_btn.setText("开始对比")

        self._update_stats()
        self._update_tables()

        # 只有用户手动点击对比时才显示完成提示
        if self._show_complete_msg:
            QMessageBox.information(
                self,
                "对比完成",
                f"未解码目录: {len(self._compare_result.get('undecoded_avs', {}))} 个番号\n"
                f"已解码目录: {len(self._compare_result.get('decoded_avs', {}))} 个番号\n"
                f"两边都有: {len(self._compare_result.get('both', []))} 个\n"
                f"仅未解码有: {len(self._compare_result.get('undecoded_only', []))} 个\n"
                f"仅已解码有: {len(self._compare_result.get('decoded_only', []))} 个"
            )

    def _update_stats(self):
        """更新统计"""
        result = self._compare_result
        self.undecoded_count_label.setText(f"未解码: {len(result.get('undecoded_avs', {}))} 个番号")
        self.decoded_count_label.setText(f"已解码: {len(result.get('decoded_avs', {}))} 个番号")
        self.both_count_label.setText(f"两边都有: {len(result.get('both', []))} 个")
        self.undecoded_only_label.setText(f"仅未解码: {len(result.get('undecoded_only', []))} 个")
        self.decoded_only_label.setText(f"仅已解码: {len(result.get('decoded_only', []))} 个")

    def _update_tables(self):
        """更新结果表格"""
        result = self._compare_result
        undecoded_avs = result.get('undecoded_avs', {})
        decoded_avs = result.get('decoded_avs', {})

        # 清空文件数据缓存
        self._file_data = {}

        # 两边都有 - 展开所有文件
        both_list = result.get('both', [])
        both_rows = []
        for av_code in both_list:
            undecoded_files = undecoded_avs.get(av_code, [])
            decoded_files = decoded_avs.get(av_code, [])
            undecoded_count = len(undecoded_files)  # 该番号的未解码文件总数
            # 为每个未解码文件创建一行
            for u_file in undecoded_files:
                both_rows.append({
                    'av_code': av_code,
                    'undecoded_file': u_file,
                    'decoded_files': decoded_files,
                    'undecoded_count': undecoded_count,  # 记录未解码文件总数
                    'status': '匹配'
                })

        self.both_table.setRowCount(len(both_rows))
        for i, row_data in enumerate(both_rows):
            av_code = row_data['av_code']
            undecoded_file = row_data['undecoded_file']
            decoded_files = row_data['decoded_files']
            undecoded_count = row_data['undecoded_count']

            # 番号列
            av_item = QTableWidgetItem(av_code)
            av_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.both_table.setItem(i, 0, av_item)

            # 显示未解码文件路径（缩短显示）- 可点击样式
            display_path = self._shorten_path(undecoded_file)
            undecoded_item = QTableWidgetItem(display_path)
            undecoded_item.setToolTip(undecoded_file)  # 完整路径作为提示
            undecoded_item.setForeground(QColor(41, 128, 185))  # 蓝色
            undecoded_item.setData(Qt.ItemDataRole.UserRole, "clickable")  # 标记可点击
            self.both_table.setItem(i, 1, undecoded_item)

            # 显示已解码文件 - 根据未解码文件数量决定是否显示删除按钮
            if decoded_files:
                if len(decoded_files) > 1:
                    display_decoded = f"[{len(decoded_files)}个] {self._shorten_path(decoded_files[0])}"
                    decoded_item = QTableWidgetItem(display_decoded)
                    decoded_item.setToolTip("\n".join(decoded_files))
                else:
                    decoded_item = QTableWidgetItem(self._shorten_path(decoded_files[0]))
                    decoded_item.setToolTip(decoded_files[0])
                decoded_item.setForeground(QColor(41, 128, 185))  # 蓝色
                decoded_item.setData(Qt.ItemDataRole.UserRole, "clickable")
                self.both_table.setItem(i, 2, decoded_item)
            else:
                self.both_table.setItem(i, 2, QTableWidgetItem("-"))

            status_item = QTableWidgetItem("匹配")
            status_item.setForeground(Qt.GlobalColor.darkGreen)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.both_table.setItem(i, 3, status_item)

            # 创建操作按钮容器
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 4, 4, 4)
            btn_layout.setSpacing(4)

            # 删除未解码按钮 - 始终显示
            delete_undecoded_btn = QPushButton("删未解码")
            delete_undecoded_btn.setFixedSize(70, 32)
            delete_undecoded_btn.setStyleSheet("""
                QPushButton {
                    background: #e74c3c;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-size: 11px;
                }
                QPushButton:hover { background: #c0392b; }
            """)
            delete_undecoded_btn.clicked.connect(lambda checked, f=undecoded_file: self._delete_undecoded_file(f))
            btn_layout.addWidget(delete_undecoded_btn)

            # 删除已解码按钮 - 仅当未解码文件数>=2时显示
            if decoded_files and undecoded_count >= 2:
                delete_decoded_btn = QPushButton("删已解码")
                delete_decoded_btn.setFixedSize(70, 32)
                delete_decoded_btn.setStyleSheet("""
                    QPushButton {
                        background: #f39c12;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        font-size: 11px;
                    }
                    QPushButton:hover { background: #e67e22; }
                """)
                # 使用第一个已解码文件作为删除目标（如果有多个，让用户选择）
                first_decoded = decoded_files[0]
                delete_decoded_btn.clicked.connect(lambda checked, f=first_decoded: self._delete_decoded_file(f))
                btn_layout.addWidget(delete_decoded_btn)

            btn_layout.addStretch()
            self.both_table.setCellWidget(i, 4, btn_widget)

            # 设置行高
            self.both_table.setRowHeight(i, 45)

            # 存储文件数据
            self._file_data[undecoded_file] = {
                'av_code': av_code,
                'decoded_files': decoded_files,
                'undecoded_count': undecoded_count
            }

        # 只有未解码有 - 展开所有文件
        undecoded_only_list = result.get('undecoded_only', [])
        undecoded_only_rows = []
        for av_code in undecoded_only_list:
            undecoded_files = undecoded_avs.get(av_code, [])
            for u_file in undecoded_files:
                undecoded_only_rows.append({
                    'av_code': av_code,
                    'undecoded_file': u_file,
                    'status': '待解码'
                })

        self.undecoded_only_table.setRowCount(len(undecoded_only_rows))
        for i, row_data in enumerate(undecoded_only_rows):
            av_code = row_data['av_code']
            undecoded_file = row_data['undecoded_file']

            # 番号列
            av_item = QTableWidgetItem(av_code)
            av_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.undecoded_only_table.setItem(i, 0, av_item)

            display_path = self._shorten_path(undecoded_file)
            undecoded_item = QTableWidgetItem(display_path)
            undecoded_item.setToolTip(undecoded_file)
            undecoded_item.setForeground(QColor(41, 128, 185))  # 蓝色可点击
            undecoded_item.setData(Qt.ItemDataRole.UserRole, "clickable")
            self.undecoded_only_table.setItem(i, 1, undecoded_item)

            self.undecoded_only_table.setItem(i, 2, QTableWidgetItem("-"))

            status_item = QTableWidgetItem("待解码")
            status_item.setForeground(Qt.GlobalColor.red)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.undecoded_only_table.setItem(i, 3, status_item)

            # 添加删除按钮
            delete_btn = QPushButton("删未解码")
            delete_btn.setFixedSize(100, 32)
            delete_btn.setStyleSheet("""
                QPushButton {
                    background: #e74c3c;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-size: 11px;
                }
                QPushButton:hover { background: #c0392b; }
            """)
            delete_btn.clicked.connect(lambda checked, f=undecoded_file: self._delete_undecoded_file(f))
            self.undecoded_only_table.setCellWidget(i, 4, delete_btn)

            # 设置行高
            self.undecoded_only_table.setRowHeight(i, 45)

            self._file_data[undecoded_file] = {
                'av_code': av_code,
                'decoded_files': []
            }

        # 只有已解码有
        decoded_only_list = result.get('decoded_only', [])
        decoded_only_rows = []
        for av_code in decoded_only_list:
            decoded_files = decoded_avs.get(av_code, [])
            for d_file in decoded_files:
                decoded_only_rows.append({
                    'av_code': av_code,
                    'decoded_file': d_file,
                    'status': '无原文件'
                })

        self.decoded_only_table.setRowCount(len(decoded_only_rows))
        for i, row_data in enumerate(decoded_only_rows):
            av_code = row_data['av_code']
            decoded_file = row_data['decoded_file']

            # 番号列
            av_item = QTableWidgetItem(av_code)
            av_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.decoded_only_table.setItem(i, 0, av_item)

            self.decoded_only_table.setItem(i, 1, QTableWidgetItem("-"))

            display_path = self._shorten_path(decoded_file)
            decoded_item = QTableWidgetItem(display_path)
            decoded_item.setToolTip(decoded_file)
            decoded_item.setForeground(QColor(41, 128, 185))  # 蓝色可点击
            decoded_item.setData(Qt.ItemDataRole.UserRole, "clickable")
            self.decoded_only_table.setItem(i, 2, decoded_item)

            status_item = QTableWidgetItem("无原文件")
            status_item.setForeground(QColor(230, 126, 34))  # 橙色
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.decoded_only_table.setItem(i, 3, status_item)

            # 已解码文件不显示删除按钮（只删未解码）
            self.decoded_only_table.setItem(i, 4, QTableWidgetItem("-"))

            # 设置行高
            self.decoded_only_table.setRowHeight(i, 45)

    def _export_result(self):
        """导出结果"""
        if not self._compare_result:
            QMessageBox.warning(self, "提示", "请先执行对比")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "导出结果", "", "文本文件 (*.txt);;CSV文件 (*.csv)"
        )

        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write("番号对比结果\n")
                    f.write(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

                    f.write("=" * 50 + "\n")
                    f.write("两边都有 (已匹配)\n")
                    f.write("=" * 50 + "\n")
                    for av_code in self._compare_result.get('both', []):
                        f.write(f"{av_code}\n")

                    f.write("\n" + "=" * 50 + "\n")
                    f.write("只有未解码有 (待解码)\n")
                    f.write("=" * 50 + "\n")
                    for av_code in self._compare_result.get('undecoded_only', []):
                        f.write(f"{av_code}\n")

                    f.write("\n" + "=" * 50 + "\n")
                    f.write("只有已解码有 (无原文件)\n")
                    f.write("=" * 50 + "\n")
                    for av_code in self._compare_result.get('decoded_only', []):
                        f.write(f"{av_code}\n")

                QMessageBox.information(self, "成功", f"结果已导出到:\n{path}")

            except Exception as e:
                QMessageBox.warning(self, "导出失败", str(e))

    def refresh(self):
        """刷新页面"""
        pass

    def _show_status(self, message: str, success: bool = True):
        """显示状态提示"""
        if success:
            self.status_frame.setStyleSheet("""
                QFrame {
                    background: #d4edda;
                    border: 1px solid #28a745;
                    border-radius: 8px;
                }
            """)
            self.status_icon_label.setText("✓")
            self.status_icon_label.setStyleSheet("font-size: 16px; color: #28a745;")
            self.status_text_label.setStyleSheet("font-size: 13px; color: #155724;")
        else:
            self.status_frame.setStyleSheet("""
                QFrame {
                    background: #f8d7da;
                    border: 1px solid #dc3545;
                    border-radius: 8px;
                }
            """)
            self.status_icon_label.setText("⚠")
            self.status_icon_label.setStyleSheet("font-size: 16px; color: #dc3545;")
            self.status_text_label.setStyleSheet("font-size: 13px; color: #721c24;")

        self.status_text_label.setText(message)
        self.status_frame.setVisible(True)

        # 5秒后自动隐藏
        QTimer.singleShot(5000, self._hide_status)

    def _hide_status(self):
        """隐藏状态提示"""
        self.status_frame.setVisible(False)

    def _shorten_path(self, file_path: str) -> str:
        """缩短路径显示"""
        path = Path(file_path)
        # 显示文件名和父目录
        return f".../{path.parent.name}/{path.name}" if path.parent.name else path.name

    def _delete_undecoded_file(self, file_path: str):
        """删除未解码文件（二次确认）"""
        file_data = self._file_data.get(file_path, {})
        av_code = file_data.get('av_code', '未知')
        decoded_files = file_data.get('decoded_files', [])

        # 使用自定义对话框显示详细信息
        dialog = QDialog(self)
        dialog.setWindowTitle("删除确认")
        dialog.setMinimumSize(500, 350)
        dialog.resize(650, 450)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 标题
        title = QLabel("确认删除以下未解码文件？")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #e74c3c;")
        layout.addWidget(title)

        # 文件信息
        info_frame = QFrame()
        info_frame.setStyleSheet("""
            QFrame {
                background: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 8px;
            }
        """)
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(15, 10, 15, 10)
        info_layout.setSpacing(10)

        # 番号
        av_label = QLabel(f"番号: {av_code}")
        av_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        info_layout.addWidget(av_label)

        # 文件名
        name_label = QLabel(f"文件名: {Path(file_path).name}")
        name_label.setStyleSheet("font-size: 13px; color: #c0392b;")
        info_layout.addWidget(name_label)

        # 完整路径 - 可点击预览按钮
        path_layout = QHBoxLayout()
        path_title = QLabel("完整路径:")
        path_title.setStyleSheet("font-size: 12px; color: #7f8c8d;")
        path_layout.addWidget(path_title)

        preview_btn = QPushButton("点击预览")
        preview_btn.setFixedHeight(28)
        preview_btn.setStyleSheet("""
            QPushButton {
                background: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 11px;
                padding: 4px 12px;
            }
            QPushButton:hover { background: #2980b9; }
        """)
        preview_btn.clicked.connect(lambda: self._preview_file_with_fallback(file_path, dialog))
        path_layout.addWidget(preview_btn)

        path_layout.addStretch()
        info_layout.addLayout(path_layout)

        # 显示完整路径（可选中复制）
        path_text = QLabel(file_path)
        path_text.setStyleSheet("font-size: 11px; color: #7f8c8d; background: #ecf0f1; padding: 5px; border-radius: 3px;")
        path_text.setWordWrap(True)
        path_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info_layout.addWidget(path_text)

        # 已解码文件提示
        if decoded_files:
            decoded_label = QLabel(f"✓ 已存在 {len(decoded_files)} 个已解码文件，可安全删除")
            decoded_label.setStyleSheet("font-size: 13px; color: #27ae60; font-weight: bold;")
            info_layout.addWidget(decoded_label)

            # 显示已解码文件路径（可点击预览）
            for df in decoded_files[:3]:  #最多显示3个
                df_layout = QHBoxLayout()
                df_path_label = QLabel(df)
                df_path_label.setStyleSheet("font-size: 11px; color: #27ae60;")
                df_path_label.setWordWrap(True)
                df_layout.addWidget(df_path_label, 1)

                df_preview_btn = QPushButton("预览")
                df_preview_btn.setFixedSize(50, 24)
                df_preview_btn.setStyleSheet("""
                    QPushButton {
                        background: #27ae60;
                        color: white;
                        border: none;
                        border-radius: 3px;
                        font-size: 10px;
                    }
                    QPushButton:hover { background: #2ecc71; }
                """)
                df_preview_btn.clicked.connect(lambda checked, f=df: self._preview_file_with_fallback(f, dialog))
                df_layout.addWidget(df_preview_btn)
                info_layout.addLayout(df_layout)

        layout.addWidget(info_frame)

        # 警告提示
        warning_label = QLabel("⚠️ 注意：文件删除后不可恢复！")
        warning_label.setStyleSheet("font-size: 14px; color: #e74c3c; font-weight: bold;")
        layout.addWidget(warning_label)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        confirm_btn = QPushButton("确认删除")
        confirm_btn.setFixedSize(120, 40)
        confirm_btn.setStyleSheet("""
            QPushButton {
                background: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background: #c0392b; }
        """)
        confirm_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(confirm_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedSize(100, 40)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #bdc3c7;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover { background: #95a5a6; }
        """)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 第二次确认
            msg2 = (
                "⚠️ 最终确认！\n\n"
                f"文件: {Path(file_path).name}\n"
                f"路径: {file_path}\n\n"
                "此操作不可恢复，确定要删除吗？"
            )
            reply2 = QMessageBox.warning(
                self,
                "二次确认",
                msg2,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply2 == QMessageBox.StandardButton.Yes:
                self._do_delete_file(file_path)

    def _delete_decoded_file(self, file_path: str):
        """删除已解码文件（仅当同一番号有>=2个未解码文件时允许）"""
        # 使用自定义对话框显示详细信息
        dialog = QDialog(self)
        dialog.setWindowTitle("删除已解码文件确认")
        dialog.setMinimumSize(500, 350)
        dialog.resize(650, 420)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 标题
        title = QLabel("确认删除以下已解码文件？")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #f39c12;")
        layout.addWidget(title)

        # 文件信息
        info_frame = QFrame()
        info_frame.setStyleSheet("""
            QFrame {
                background: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 8px;
            }
        """)
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(15, 10, 15, 10)
        info_layout.setSpacing(10)

        # 文件名
        name_label = QLabel(f"文件名: {Path(file_path).name}")
        name_label.setStyleSheet("font-size: 14px; color: #e67e22; font-weight: bold;")
        info_layout.addWidget(name_label)

        # 完整路径 - 可点击预览按钮
        path_layout = QHBoxLayout()
        path_title = QLabel("完整路径:")
        path_title.setStyleSheet("font-size: 12px; color: #7f8c8d;")
        path_layout.addWidget(path_title)

        preview_btn = QPushButton("点击预览")
        preview_btn.setFixedHeight(28)
        preview_btn.setStyleSheet("""
            QPushButton {
                background: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 11px;
                padding: 4px 12px;
            }
            QPushButton:hover { background: #2980b9; }
        """)
        preview_btn.clicked.connect(lambda: self._preview_file_with_fallback(file_path, dialog))
        path_layout.addWidget(preview_btn)

        path_layout.addStretch()
        info_layout.addLayout(path_layout)

        # 显示完整路径（可选中复制）
        path_text = QLabel(file_path)
        path_text.setStyleSheet("font-size: 11px; color: #7f8c8d; background: #ecf0f1; padding: 5px; border-radius: 3px;")
        path_text.setWordWrap(True)
        path_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info_layout.addWidget(path_text)

        # 提示
        tip_label = QLabel("此番号有多个未解码文件，删除已解码文件后仍可保留原文件。")
        tip_label.setStyleSheet("font-size: 13px; color: #3498db;")
        info_layout.addWidget(tip_label)

        layout.addWidget(info_frame)

        # 警告提示
        warning_label = QLabel("⚠️ 注意：文件删除后不可恢复！")
        warning_label.setStyleSheet("font-size: 14px; color: #e74c3c; font-weight: bold;")
        layout.addWidget(warning_label)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedSize(100, 40)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #bdc3c7;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover { background: #95a5a6; }
        """)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)

        confirm_btn = QPushButton("确认删除")
        confirm_btn.setFixedSize(120, 40)
        confirm_btn.setStyleSheet("""
            QPushButton {
                background: #f39c12;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background: #e67e22; }
        """)
        confirm_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(confirm_btn)

        layout.addLayout(btn_layout)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 第二次确认
            msg2 = (
                "⚠️ 最终确认！\n\n"
                f"文件: {Path(file_path).name}\n"
                f"路径: {file_path}\n\n"
                "此操作不可恢复，确定要删除吗？"
            )
            reply2 = QMessageBox.warning(
                self,
                "二次确认",
                msg2,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply2 == QMessageBox.StandardButton.Yes:
                self._do_delete_file(file_path)

    def _do_delete_file(self, file_path: str):
        """执行文件删除"""
        try:
            path = Path(file_path)
            if not path.exists():
                QMessageBox.warning(self, "删除失败", "文件不存在")
                return

            # 删除文件
            path.unlink()
            logger.info(f"已删除文件: {file_path}")

            # 从缓存中移除
            if file_path in self._file_data:
                del self._file_data[file_path]

            # 显示状态提示
            self._show_status(f"文件已删除: {Path(file_path).name}")

            # 重新对比以更新表格（不弹出完成提示）
            self._start_compare(show_complete_msg=False)

        except Exception as e:
            logger.error(f"删除文件失败: {e}")
            self._show_status(f"删除失败: {str(e)}", success=False)

    def _do_batch_delete(self, files: List[str]):
        """执行批量删除"""
        deleted_count = 0
        failed_files = []

        for file_path in files:
            try:
                path = Path(file_path)
                if path.exists():
                    path.unlink()
                    logger.info(f"已删除文件: {file_path}")
                    deleted_count += 1
                else:
                    failed_files.append(f"{Path(file_path).name} (不存在)")
            except Exception as e:
                failed_files.append(f"{Path(file_path).name} ({str(e)})")

        # 显示结果
        if failed_files:
            self._show_status(
                f"删除完成: 成功 {deleted_count} 个, 失败 {len(failed_files)} 个",
                success=False
            )
        else:
            self._show_status(f"已成功删除 {deleted_count} 个文件")

        # 重新对比以更新表格（不弹出完成提示）
        if deleted_count > 0:
            self._start_compare(show_complete_msg=False)

    def _delete_all_both(self):
        """一键删除全部两边都有（已匹配）的未解码文件"""
        if not self._compare_result:
            QMessageBox.warning(self, "提示", "请先执行对比")
            return

        result = self._compare_result
        undecoded_avs = result.get('undecoded_avs', {})
        decoded_avs = result.get('decoded_avs', {})
        both_list = result.get('both', [])

        if not both_list:
            QMessageBox.warning(self, "提示", "没有两边都有的文件")
            return

        # 收集所有未解码文件及其对应的已解码文件
        files_info = []
        for av_code in both_list:
            undecoded_files = undecoded_avs.get(av_code, [])
            decoded_files = decoded_avs.get(av_code, [])
            for u_file in undecoded_files:
                files_info.append({
                    'av_code': av_code,
                    'undecoded_file': u_file,
                    'decoded_files': decoded_files
                })

        if not files_info:
            QMessageBox.warning(self, "提示", "没有可删除的文件")
            return

        # 弹出详细对话框显示要删除的文件列表
        self._show_delete_detail_dialog(files_info)

    def _show_delete_detail_dialog(self, files_info: List[Dict]):
        """显示删除详情对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("删除文件详情")
        dialog.setMinimumSize(900, 600)
        dialog.resize(1000, 700)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 标题
        title_label = QLabel(f"以下 {len(files_info)} 个未解码文件将被删除")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #e74c3c;")
        layout.addWidget(title_label)

        # 提示
        tip_label = QLabel("这些番号都有对应的已解码文件，可以安全删除")
        tip_label.setStyleSheet("font-size: 13px; color: #27ae60;")
        layout.addWidget(tip_label)

        # 文件列表表格 - 显示完整路径
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["番号", "待删除文件名", "待删除文件路径", "已解码文件"])

        table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #dee2e6;
                background: #fff;
                gridline-color: #dee2e6;
            }
            QHeaderView::section {
                background: #f8f9fa;
                border: 1px solid #dee2e6;
                padding: 8px;
                font-weight: bold;
            }
        """)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        table.setColumnWidth(0, 100)
        table.setColumnWidth(1, 200)

        table.setRowCount(len(files_info))
        for i, info in enumerate(files_info):
            # 番号
            av_item = QTableWidgetItem(info['av_code'])
            av_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(i, 0, av_item)

            # 待删除文件名
            undecoded_path = info['undecoded_file']
            undecoded_name = Path(undecoded_path).name
            undecoded_name_item = QTableWidgetItem(undecoded_name)
            undecoded_name_item.setForeground(QColor(192, 57, 43))  # 红色
            table.setItem(i, 1, undecoded_name_item)

            # 待删除文件完整路径
            undecoded_path_item = QTableWidgetItem(undecoded_path)
            undecoded_path_item.setForeground(QColor(192, 57, 43))  # 红色
            undecoded_path_item.setToolTip(undecoded_path)
            table.setItem(i, 2, undecoded_path_item)

            # 已存在解码文件 - 显示完整路径
            decoded_files = info['decoded_files']
            if decoded_files:
                # 显示所有已解码文件路径
                decoded_paths_text = "\n".join(decoded_files) if len(decoded_files) > 1 else decoded_files[0]
                decoded_item = QTableWidgetItem(decoded_paths_text)
                decoded_item.setToolTip("\n".join(decoded_files))
                decoded_item.setForeground(QColor(39, 174, 96))  # 绿色
            else:
                decoded_item = QTableWidgetItem("-")
            table.setItem(i, 3, decoded_item)

            table.setRowHeight(i, 45)

        table.verticalHeader().setVisible(False)
        layout.addWidget(table)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        confirm_btn = QPushButton("确认删除")
        confirm_btn.setFixedSize(120, 36)
        confirm_btn.setStyleSheet("""
            QPushButton {
                background: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background: #c0392b; }
        """)
        confirm_btn.clicked.connect(lambda: self._confirm_delete_from_dialog(dialog, files_info))
        btn_layout.addWidget(confirm_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedSize(100, 36)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #bdc3c7;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover { background: #95a5a6; }
        """)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

        dialog.exec()

    def _confirm_delete_from_dialog(self, dialog: QDialog, files_info: List[Dict]):
        """从详情对话框确认删除"""
        files_to_delete = [info['undecoded_file'] for info in files_info]

        # 二次确认
        msg = (
            "⚠️ 此操作不可恢复！\n\n"
            f"确定要删除 {len(files_to_delete)} 个文件吗？\n"
            "文件将永久从磁盘删除。"
        )
        reply = QMessageBox.warning(
            self,
            "最终确认",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            dialog.accept()
            self._do_batch_delete(files_to_delete)