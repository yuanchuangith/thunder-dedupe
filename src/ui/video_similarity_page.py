#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
视频相似度检测页面 - 扫描视频、计算相似度、展示结果
"""
import os
import threading
from pathlib import Path
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QProgressBar, QFileDialog,
    QListWidget, QMessageBox, QSlider, QSpinBox,
    QDialog, QTextEdit
)

from db.database import db
from core.video_similarity import (
    video_similarity_scanner,
    format_duration,
    format_file_size
)
from ui.dual_video_window import DualVideoCompareWindow
from utils.logger import logger
from utils.utils import format_file_size as utils_format_file_size


class VideoSimilarityPage(QWidget):
    """视频相似度检测页面"""

    def __init__(self):
        super().__init__()
        self._scanning = False
        self._similarity_data = []
        self._current_threshold = 50  # 默认阈值50%
        self._setup_ui()
        self._load_paths()
        self._load_data()

    @staticmethod
    def _get_similarity_judgment(score: float, status: str = "pending"):
        """Return a user-facing judgment label for the similarity score."""
        if status == "confirmed_duplicate":
            return "已标记重复", QColor(192, 57, 43), "这对视频已经人工标记为重复。"
        if status == "kept":
            return "已确认保留", QColor(39, 174, 96), "这对视频已经人工确认保留。"
        if score >= 95:
            return "重复候选", QColor(192, 57, 43), "相似度极高，优先作为重复视频复核。"
        if score >= 85:
            return "高度相似", QColor(230, 126, 34), "内容非常接近，建议重点比对。"
        if score >= 70:
            return "明显相似", QColor(41, 128, 185), "大概率为同源素材或轻度改版。"
        return "一般相似", QColor(127, 140, 141), "建议人工复核后再决定。"

    def _setup_ui(self):
        """设置界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 说明区域
        desc_frame = self._create_desc_frame()
        layout.addWidget(desc_frame)

        # 路径配置区域
        path_frame = self._create_path_frame()
        layout.addWidget(path_frame)

        # 操作按钮区域
        action_frame = self._create_action_frame()
        layout.addWidget(action_frame)

        # 阈值设置区域
        threshold_frame = self._create_threshold_frame()
        layout.addWidget(threshold_frame)

        # 统计信息区域
        stats_frame = self._create_stats_frame()
        layout.addWidget(stats_frame)

        # 结果表格
        self.result_table = self._create_result_table()
        layout.addWidget(self.result_table)

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

        # 连接扫描器信号
        video_similarity_scanner.scan_started.connect(self._on_scan_started)
        video_similarity_scanner.scan_progress.connect(self._on_scan_progress)
        video_similarity_scanner.similarity_progress.connect(self._on_similarity_progress)
        video_similarity_scanner.scan_completed.connect(self._on_scan_completed)
        video_similarity_scanner.scan_error.connect(self._on_scan_error)

    def _create_desc_frame(self) -> QFrame:
        """创建说明区域"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: #fff3cd;
                border: 1px solid #ffc107;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 10, 15, 10)

        desc_label = QLabel(
            "视频相似度检测：扫描文件夹内的视频，通过视觉特征分析识别相似/重复视频。\n"
            "功能：特征提取(pHash+CLIP) → 相似度计算 → 结果展示 → 视频预览 → 安全删除"
        )
        desc_label.setStyleSheet("color: #856404; font-size: 13px;")
        layout.addWidget(desc_label)

        return frame

    def _create_path_frame(self) -> QFrame:
        """创建路径配置区域"""
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

        # 标题
        title = QLabel("扫描路径:")
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(title)

        # 路径列表
        self.path_list = QListWidget()
        self.path_list.setMaximumHeight(60)
        self.path_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #dee2e6;
                background: #fff;
                border-radius: 4px;
                font-size: 12px;
            }
        """)
        layout.addWidget(self.path_list, 1)

        # 添加按钮
        add_btn = QPushButton("添加")
        add_btn.setFixedHeight(28)
        add_btn.setStyleSheet("""
            QPushButton {
                background: #27ae60;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background: #2ecc71; }
        """)
        add_btn.clicked.connect(self._add_path)
        layout.addWidget(add_btn)

        # 删除按钮
        remove_btn = QPushButton("删除")
        remove_btn.setFixedHeight(28)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background: #c0392b; }
        """)
        remove_btn.clicked.connect(self._remove_path)
        layout.addWidget(remove_btn)

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

        # 开始扫描按钮
        self.scan_btn = QPushButton("开始扫描")
        self.scan_btn.setFixedHeight(36)
        self.scan_btn.setStyleSheet("""
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
        self.scan_btn.clicked.connect(self._start_scan)
        layout.addWidget(self.scan_btn)

        # 刷新结果按钮
        refresh_btn = QPushButton("刷新结果")
        refresh_btn.setFixedHeight(36)
        refresh_btn.setStyleSheet("""
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
        refresh_btn.clicked.connect(self._load_data)
        layout.addWidget(refresh_btn)

        # 清空数据按钮
        clear_btn = QPushButton("清空数据")
        clear_btn.setFixedHeight(36)
        clear_btn.setStyleSheet("""
            QPushButton {
                background: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 14px;
            }
            QPushButton:hover { background: #c0392b; }
        """)
        clear_btn.clicked.connect(self._clear_data)
        layout.addWidget(clear_btn)

        layout.addStretch()

        return frame

    def _create_threshold_frame(self) -> QFrame:
        """创建阈值设置区域"""
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

        # 标题
        title = QLabel("相似度阈值:")
        title.setStyleSheet("font-size: 13px;")
        layout.addWidget(title)

        # 滑块
        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setRange(0, 100)
        self.threshold_slider.setValue(self._current_threshold)
        self.threshold_slider.setFixedWidth(200)
        self.threshold_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 8px;
                background: #ddd;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #3498db;
                width: 16px;
                margin: -4px 0;
                border-radius: 8px;
            }
        """)
        self.threshold_slider.valueChanged.connect(self._on_threshold_changed)
        layout.addWidget(self.threshold_slider)

        # 数值显示
        self.threshold_label = QLabel(f"{self._current_threshold}%")
        self.threshold_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #3498db;")
        layout.addWidget(self.threshold_label)

        layout.addStretch()

        return frame

    def _create_stats_frame(self) -> QFrame:
        """创建统计信息区域"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: #d4edda;
                border: 1px solid #28a745;
                border-radius: 8px;
            }
        """)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(15, 10, 15, 10)

        self.video_count_label = QLabel("视频数: 0")
        self.video_count_label.setStyleSheet("font-size: 13px; color: #155724;")
        layout.addWidget(self.video_count_label)

        layout.addStretch()

        self.similarity_count_label = QLabel("相似对数: 0")
        self.similarity_count_label.setStyleSheet("font-size: 13px; color: #155724;")
        layout.addWidget(self.similarity_count_label)

        layout.addStretch()

        self.pending_count_label = QLabel("待处理: 0")
        self.pending_count_label.setStyleSheet("font-size: 13px; color: #f39c12;")
        layout.addWidget(self.pending_count_label)

        layout.addStretch()

        self.duplicate_count_label = QLabel("已标记重复: 0")
        self.duplicate_count_label.setStyleSheet("font-size: 13px; color: #e74c3c;")
        layout.addWidget(self.duplicate_count_label)

        return frame

    def _create_result_table(self) -> QTableWidget:
        """创建结果表格"""
        table = QTableWidget()
        table.setColumnCount(7)
        """
        table.setHorizontalHeaderLabels([
            "视频A", "视频B", "相似度", "时长A", "大小A", "操作"
        ])
        table.setHorizontalHeaderLabels([
            "视频A", "视频B", "准确率", "判断", "时长A", "大小A", "操作"
        ])

        """
        table.setHorizontalHeaderLabels([
            "Video A", "Video B", "Score", "Decision", "Duration A", "Size A", "Actions"
        ])
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
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)

        table.setColumnWidth(2, 90)
        table.setColumnWidth(3, 110)
        table.setColumnWidth(4, 80)
        table.setColumnWidth(5, 80)
        table.setColumnWidth(6, 150)

        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)

        # 双击播放
        table.cellDoubleClicked.connect(self._on_table_double_click)

        return table

    def _load_paths(self):
        """加载扫描路径"""
        rows = db.query("SELECT path FROM video_similarity_paths WHERE enabled = 1")
        for row in rows:
            self.path_list.addItem(row['path'])

    def _load_data(self):
        """加载相似度数据"""
        # 更新统计
        video_count = video_similarity_scanner.get_video_count()
        similarity_count = video_similarity_scanner.get_similarity_count()

        self.video_count_label.setText(f"视频数: {video_count}")
        self.similarity_count_label.setText(f"相似对数: {similarity_count}")

        # 获取结果
        self._similarity_data = video_similarity_scanner.get_similarity_results(self._current_threshold)

        # 统计状态
        pending = sum(1 for d in self._similarity_data if d['status'] == 'pending')
        duplicate = sum(1 for d in self._similarity_data if d['status'] == 'confirmed_duplicate')

        self.pending_count_label.setText(f"待处理: {pending}")
        self.duplicate_count_label.setText(f"已标记重复: {duplicate}")

        # 更新表格
        self._update_table()

    def _update_table(self):
        """更新结果表格"""
        data = self._similarity_data
        self.result_table.setRowCount(len(data))

        for i, row in enumerate(data):
            # 视频A文件名
            a_name = Path(row['video_a_path']).name
            a_item = QTableWidgetItem(a_name)
            a_item.setToolTip(row['video_a_path'])
            a_item.setForeground(QColor(41, 128, 185))
            self.result_table.setItem(i, 0, a_item)

            # 视频B文件名
            b_name = Path(row['video_b_path']).name
            b_item = QTableWidgetItem(b_name)
            b_item.setToolTip(row['video_b_path'])
            b_item.setForeground(QColor(41, 128, 185))
            self.result_table.setItem(i, 1, b_item)

            # 相似度
            score = row['similarity_score']
            score_item = QTableWidgetItem(f"{score:.1f}%")
            score_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            judgment_text, judgment_color, judgment_tip = self._get_similarity_judgment(
                score, row['status']
            )

            # 根据相似度设置颜色
            if score >= 90:
                score_item.setForeground(QColor(231, 76, 60))  # 红色
            elif score >= 70:
                score_item.setForeground(QColor(243, 156, 18))  # 橙色
            else:
                score_item.setForeground(QColor(52, 152, 219))  # 蓝色

            score_item.setForeground(judgment_color)
            score_item.setToolTip(judgment_tip)
            self.result_table.setItem(i, 2, score_item)

            judgment_item = QTableWidgetItem(judgment_text)
            judgment_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            judgment_item.setForeground(judgment_color)
            judgment_item.setToolTip(judgment_tip)
            self.result_table.setItem(i, 3, judgment_item)

            # 时长A
            duration_a = format_duration(row['video_a_duration'] or 0)
            self.result_table.setItem(i, 4, QTableWidgetItem(duration_a))

            # 大小A
            size_a = utils_format_file_size(row['video_a_size'] or 0)
            self.result_table.setItem(i, 5, QTableWidgetItem(size_a))

            # 操作按钮
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 2, 4, 2)
            btn_layout.setSpacing(4)

            # 预览按钮
            preview_btn = QPushButton("预览")
            preview_btn.setFixedSize(50, 26)
            preview_btn.setStyleSheet("""
                QPushButton {
                    background: #3498db;
                    color: white;
                    border: none;
                    border-radius: 3px;
                    font-size: 11px;
                }
                QPushButton:hover { background: #2980b9; }
            """)
            preview_btn.clicked.connect(
                lambda checked, result=row: self._show_preview(result)
            )
            btn_layout.addWidget(preview_btn)

            # 标记重复按钮（如果状态是pending）
            if row['status'] == 'pending':
                mark_btn = QPushButton("标记重复")
                mark_btn.setFixedSize(60, 26)
                mark_btn.setStyleSheet("""
                    QPushButton {
                        background: #e74c3c;
                        color: white;
                        border: none;
                        border-radius: 3px;
                        font-size: 11px;
                    }
                    QPushButton:hover { background: #c0392b; }
                """)
                mark_btn.clicked.connect(
                    lambda checked, sid=row['id']:
                    self._mark_duplicate(sid)
                )
                btn_layout.addWidget(mark_btn)

            btn_layout.addStretch()
            self.result_table.setCellWidget(i, 6, btn_widget)

            self.result_table.setRowHeight(i, 35)

    def _add_path(self):
        """添加扫描路径"""
        path = QFileDialog.getExistingDirectory(self, "选择视频文件夹")
        if path:
            items = [self.path_list.item(i).text() for i in range(self.path_list.count())]
            if path in items:
                QMessageBox.warning(self, "提示", "该路径已添加")
                return

            self.path_list.addItem(path)
            db.execute(
                "INSERT OR IGNORE INTO video_similarity_paths (path, enabled) VALUES (?, 1)",
                (path,)
            )

    def _remove_path(self):
        """删除扫描路径"""
        current = self.path_list.currentItem()
        if current:
            path = current.text()
            self.path_list.takeItem(self.path_list.row(current))
            db.execute("DELETE FROM video_similarity_paths WHERE path = ?", (path,))

    def _start_scan(self):
        """开始扫描"""
        if self._scanning:
            return

        paths = [self.path_list.item(i).text() for i in range(self.path_list.count())]

        if not paths:
            QMessageBox.warning(self, "提示", "请先添加扫描路径")
            return

        self._scanning = True
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("扫描中...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        video_similarity_scanner.scan_folders(paths)

    def _on_scan_started(self):
        """扫描开始"""
        logger.info("扫描开始")

    def _on_scan_progress(self, processed: int, total: int, filename: str):
        """扫描进度"""
        progress = int(processed / total * 50)  # 扫描占50%
        self.progress_bar.setValue(progress)
        self.progress_bar.setFormat(f"扫描: {processed}/{total} - {filename}")

    def _on_similarity_progress(self, processed: int, total: int):
        """相似度计算进度"""
        progress = 50 + int(processed / total * 50)  # 计算占50%
        self.progress_bar.setValue(progress)
        self.progress_bar.setFormat(f"计算相似度: {processed}/{total}")

    def _on_scan_completed(self, new_videos: int, total_similarities: int):
        """扫描完成"""
        self._scanning = False
        self.progress_bar.setVisible(False)
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("开始扫描")

        QMessageBox.information(
            self,
            "扫描完成",
            f"新增视频: {new_videos} 个\n"
            f"相似度对数: {total_similarities} 对"
        )

        self._load_data()

    def _on_scan_error(self, error_msg: str):
        """扫描出错"""
        self._scanning = False
        self.progress_bar.setVisible(False)
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("开始扫描")

        QMessageBox.warning(self, "扫描出错", error_msg)

    def _on_threshold_changed(self, value: int):
        """阈值改变"""
        self._current_threshold = value
        self.threshold_label.setText(f"{value}%")
        self._load_data()

    def _on_table_double_click(self, row: int, col: int):
        """表格双击事件"""
        if row < len(self._similarity_data):
            data = self._similarity_data[row]
            self._show_preview(data)

    def _play_file(self, file_path: str):
        """播放文件"""
        try:
            path = Path(file_path)
            if not path.exists():
                QMessageBox.warning(self, "提示", "文件不存在")
                return

            import subprocess
            import platform

            if platform.system() == "Windows":
                subprocess.run(['start', '', file_path], shell=True, check=False)
            elif platform.system() == "Darwin":
                subprocess.run(['open', file_path], check=False)
            else:
                subprocess.run(['xdg-open', file_path], check=False)

            logger.info(f"播放文件: {file_path}")

        except Exception as e:
            logger.error(f"播放文件失败: {e}")
            QMessageBox.warning(self, "播放失败", f"无法播放文件:\n{str(e)}")

    def _show_preview(self, result: dict):
        """显示双视频预览窗口"""
        try:
            video_a_path = result['video_a_path']
            video_b_path = result['video_b_path']
            judgment_text, judgment_color, _ = self._get_similarity_judgment(
                result['similarity_score'],
                result['status']
            )
            self.dual_video_window = DualVideoCompareWindow(
                video_a_path,
                video_b_path,
                self,
                compare_mode=False,
                similarity_score=result['similarity_score'],
                judgment_text=judgment_text,
                judgment_color=judgment_color.name(),
                result_status=result['status']
            )
            self.dual_video_window.show()
            logger.info(f"打开预览窗口: {video_a_path} vs {video_b_path}")

        except Exception as e:
            logger.error(f"打开预览窗口失败: {e}")
            QMessageBox.warning(self, "预览失败", f"无法打开预览窗口:\n{str(e)}")

    def _mark_duplicate(self, similarity_id: int):
        """标记为重复"""
        reply = QMessageBox.question(
            self,
            "标记重复",
            "确认标记这对视频为重复？\n标记后可在删除操作中处理。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            video_similarity_scanner.update_similarity_status(similarity_id, 'confirmed_duplicate')
            self._load_data()

    def _clear_data(self):
        """清空所有数据"""
        reply = QMessageBox.warning(
            self,
            "清空数据",
            "确认清空所有视频相似度数据？\n此操作不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            video_similarity_scanner.clear_all_data()
            self._load_data()
            QMessageBox.information(self, "完成", "数据已清空")

    def refresh(self):
        """刷新页面"""
        self._load_data()
