#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Decode page powered by lada-cli task queue.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PyQt6.QtCore import QProcess, Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.av_parser import AVParser
from db.database import db
from ui.dual_video_window import DualVideoCompareWindow
from utils.config import config
from utils.logger import logger


class DecodePage(QWidget):
    """Import video files into a decode queue and process them with lada-cli."""

    STATUS_PENDING = "pending"
    STATUS_DECODED = "decoded"
    STATUS_SUSPECTED = "suspected_decoded"
    STATUS_LOW_RESOLUTION = "low_resolution"

    STATUS_LABELS = {
        STATUS_PENDING: "待解码",
        STATUS_DECODED: "已经解码",
        STATUS_SUSPECTED: "疑已解码",
        STATUS_LOW_RESOLUTION: "低分辨率",
    }

    STATUS_COLORS = {
        STATUS_PENDING: QColor(243, 156, 18),
        STATUS_DECODED: QColor(39, 174, 96),
        STATUS_SUSPECTED: QColor(192, 57, 43),
        STATUS_LOW_RESOLUTION: QColor(100, 149, 237),  # 蓝色
    }

    # 低分辨率阈值：高度低于 1080p (1080像素) 视为低分辨率
    LOW_RESOLUTION_THRESHOLD = 1080

    VIDEO_EXTENSIONS = {
        ".mp4", ".mkv", ".avi", ".wmv", ".flv", ".mov",
        ".mpeg", ".mpg", ".m4v", ".ts", ".webm",
    }

    DETECTION_MODELS = [
        ("v4-fast", "速度更快，v0.11.0 默认检测模型"),
        ("v4-accurate", "比 v4-fast 更慢，但有时更准确"),
        ("v3.1-fast", "旧版快速检测模型"),
        ("v3.1-accurate", "旧版准确检测模型"),
        ("v3", "旧版检测模型"),
        ("v2", "旧版检测模型"),
    ]

    RESTORATION_MODELS = [
        ("basicvsrpp-v1.2", "最新且推荐的修复模型"),
        ("basicvsrpp-v1.1", "上一版修复模型"),
        ("basicvsrpp-v1.0", "更早期的修复模型"),
        ("deepmosaics", "兼容旧 DeepMosaics 模型"),
    ]

    DEVICE_OPTIONS = [
        ("cuda", "自动使用默认 GPU"),
        ("cuda:0", "指定第一块 GPU"),
        ("cpu", "仅 CPU，速度会很慢"),
    ]

    ENCODING_PRESETS = [
        ("h264-cpu-fast", "H.264 / AVC, x264 software encoder, Fast, Medium File Size"),
        ("h264-cpu-uhq", "H.264 / AVC, x264 software encoder, Indistinguishable Quality, Slow, Very Large File Size"),
        ("h264-nvidia-gpu-fast", "H.264 / AVC, Nvidia hardware encoder, Fast, Medium File Size"),
        ("h264-intel-gpu-fast", "H.264 / AVC, Intel Quick Sync hardware encoder, Fast, Medium File Size"),
        ("hevc-nvidia-gpu-balanced", "H.265 / HEVC, Nvidia hardware encoder, Excellent Quality, Smaller File Size"),
        ("hevc-nvidia-gpu-hq", "H.265 / HEVC, Nvidia hardware encoder, High Quality, Medium File Size"),
        ("hevc-nvidia-gpu-uhq", "H.265 / HEVC, Nvidia hardware encoder, Indistinguishable Quality, Large File Size"),
        ("hevc-intel-gpu-hq", "H.265 / HEVC, Intel Quick Sync hardware encoder, High Quality, Medium File Size"),
        ("av1-cpu-uhq", "AV1, SVT-AV1 software encoder, Indistinguishable Quality, Smaller File Size"),
    ]

    COMMON_PRESET = {
        "detection_model": "v4-accurate",
        "restoration_model": "basicvsrpp-v1.2",
        "detect_face_mosaics": True,
        "max_clip_length": 400,
        "device": "cuda",
        "fp16": True,
        "encoding_preset": "hevc-nvidia-gpu-uhq",
        "output_file_pattern": "{orig_file_name}.restored.mp4",
        "mp4_fast_start": True,
    }

    DETECTION_MODELS = [
        ("v4-fast", "速度更快，v0.11.0 默认检测模型"),
        ("v4-accurate", "比 v4-fast 更慢，但通常更准确"),
        ("v3.1-fast", "旧版快速检测模型"),
        ("v3.1-accurate", "旧版高精度检测模型"),
        ("v3", "旧版检测模型"),
        ("v2", "旧版检测模型"),
    ]

    RESTORATION_MODELS = [
        ("basicvsrpp-v1.2", "最新且推荐的修复模型"),
        ("basicvsrpp-v1.1", "上一版修复模型"),
        ("basicvsrpp-v1.0", "更早期的修复模型"),
        ("deepmosaics", "兼容旧版 DeepMosaics 模型"),
    ]

    DEVICE_OPTIONS = [
        ("cuda", "自动使用默认 GPU"),
        ("cuda:0", "指定第一块 GPU"),
        ("cpu", "使用 CPU，速度会比较慢"),
    ]

    def __init__(self):
        super().__init__()
        self._queue_running = False
        self._stop_requested = False
        self._current_task_id = None
        self._current_task_path = None
        self._current_output_path = None
        self._current_task_progress = None
        self._process_output_buffer = ""
        self._preview_windows = []
        self._parser = AVParser()

        self._ensure_decode_tables()

        self._process = QProcess(self)
        self._process.readyReadStandardOutput.connect(self._read_stdout)
        self._process.readyReadStandardError.connect(self._read_stderr)
        self._process.started.connect(self._on_process_started)
        self._process.finished.connect(self._on_process_finished)
        self._process.errorOccurred.connect(self._on_process_error)

        self._setup_ui()
        self._load_config()
        self._refresh_task_table()
        self._update_command_preview()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #f5f7fa; }")

        container = QWidget()
        container.setStyleSheet("background: #f5f7fa;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        title = QLabel("Lada解码")
        title.setStyleSheet("QLabel { font-size: 20px; font-weight: bold; color: #2c3e50; }")
        layout.addWidget(title)

        desc = QLabel('导入视频后会进入解码列表。真正运行时只会消费数据库里"待解码"的任务。')
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        layout.addWidget(desc)

        command_card = self._create_command_card()
        log_card = self._create_log_card()
        action_card = self._create_action_card()

        layout.addWidget(self._create_path_card())
        layout.addWidget(self._create_option_card())
        layout.addWidget(self._create_stats_card())
        layout.addWidget(action_card)
        layout.addWidget(self._create_task_card())
        layout.addWidget(command_card)
        layout.addWidget(log_card, 1)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def _create_path_card(self) -> QFrame:
        card = self._create_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        title = QLabel("路径设置")
        title.setStyleSheet(self._title_style())
        layout.addWidget(title)

        self.cli_path_edit = QLineEdit()
        self.cli_path_edit.setPlaceholderText("lada-cli 或 D:/lada/lada-cli.exe")
        self.cli_path_edit.textChanged.connect(self._update_command_preview)
        layout.addLayout(self._build_form_row("CLI 程序", self.cli_path_edit, [("浏览", self._select_cli_path, "#3498db")]))

        self.import_path_edit = QLineEdit()
        self.import_path_edit.setPlaceholderText("选择待解码的视频文件或目录")
        self.import_path_edit.returnPressed.connect(self._import_from_manual_path)
        self.import_path_edit.textChanged.connect(self._update_command_preview)
        layout.addLayout(
            self._build_form_row(
                "解码视频位置",
                self.import_path_edit,
                [("文件", self._select_import_file, "#3498db"), ("目录", self._select_import_dir, "#27ae60")],
            )
        )

        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("选择解码后输出目录")
        self.output_path_edit.textChanged.connect(self._update_command_preview)
        layout.addLayout(self._build_form_row("输出目录", self.output_path_edit, [("目录", self._select_output_dir, "#27ae60")]))

        self.temp_dir_edit = QLineEdit()
        self.temp_dir_edit.setPlaceholderText("临时缓存目录，留空时使用系统临时目录")
        self.temp_dir_edit.textChanged.connect(self._update_command_preview)
        layout.addLayout(self._build_form_row("缓存目录", self.temp_dir_edit, [("目录", self._select_temp_dir, "#27ae60")]))

        self.output_pattern_edit = QLineEdit()
        self.output_pattern_edit.setPlaceholderText("{orig_file_name}.restored.mp4")
        self.output_pattern_edit.textChanged.connect(self._update_command_preview)
        layout.addLayout(self._build_form_row("输出模板", self.output_pattern_edit))

        return card

    def _create_option_card(self) -> QFrame:
        card = self._create_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        title = QLabel("常用参数")
        title.setStyleSheet(self._title_style())
        layout.addWidget(title)

        self.detection_model_combo = self._create_select_combo(self.DETECTION_MODELS)
        self.detection_model_combo.currentIndexChanged.connect(self._update_command_preview)
        layout.addLayout(self._build_form_row("检测模型", self.detection_model_combo))

        self.restoration_model_combo = self._create_select_combo(self.RESTORATION_MODELS)
        self.restoration_model_combo.currentIndexChanged.connect(self._update_command_preview)
        layout.addLayout(self._build_form_row("修复模型", self.restoration_model_combo))

        self.device_combo = self._create_select_combo(self.DEVICE_OPTIONS)
        self.device_combo.currentIndexChanged.connect(self._update_command_preview)
        layout.addLayout(self._build_form_row("设备", self.device_combo))

        self.encoding_preset_combo = self._create_select_combo(self.ENCODING_PRESETS)
        self.encoding_preset_combo.currentIndexChanged.connect(self._update_command_preview)
        layout.addLayout(self._build_form_row("编码预设", self.encoding_preset_combo))

        row = QHBoxLayout()
        row.setSpacing(20)
        self.fp16_cb = self._create_checkbox("FP16 半精度")
        self.detect_face_cb = self._create_checkbox("面部检测")
        self.mp4_fast_start_cb = self._create_checkbox("MP4 边传边播")
        self.fp16_cb.toggled.connect(self._update_command_preview)
        self.detect_face_cb.toggled.connect(self._update_command_preview)
        self.mp4_fast_start_cb.toggled.connect(self._update_command_preview)
        row.addWidget(self.fp16_cb)
        row.addWidget(self.detect_face_cb)
        row.addWidget(self.mp4_fast_start_cb)
        row.addStretch()
        layout.addLayout(row)

        clip_row = QHBoxLayout()
        label = QLabel("切片帧数")
        label.setMinimumWidth(90)
        label.setStyleSheet("font-size: 13px; color: #2c3e50;")
        clip_row.addWidget(label)
        self.max_clip_spin = QSpinBox()
        self.max_clip_spin.setRange(30, 2000)
        self.max_clip_spin.setSingleStep(10)
        self.max_clip_spin.setMinimumHeight(34)
        self.max_clip_spin.setStyleSheet(self._input_style())
        self.max_clip_spin.valueChanged.connect(self._update_command_preview)
        clip_row.addWidget(self.max_clip_spin)
        clip_row.addStretch()
        layout.addLayout(clip_row)

        return card

    def _create_stats_card(self) -> QFrame:
        card = self._create_card()
        layout = QHBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        self.pending_count_label = QLabel("待解码: 0")
        self.decoded_count_label = QLabel("已经解码: 0")
        self.suspected_count_label = QLabel("疑已解码: 0")
        self.low_resolution_count_label = QLabel("低分辨率: 0")
        self.pending_count_label.setStyleSheet("color: #f39c12; font-size: 13px; font-weight: bold;")
        self.decoded_count_label.setStyleSheet("color: #27ae60; font-size: 13px; font-weight: bold;")
        self.suspected_count_label.setStyleSheet("color: #c0392b; font-size: 13px; font-weight: bold;")
        self.low_resolution_count_label.setStyleSheet("color: #6495ed; font-size: 13px; font-weight: bold;")
        layout.addWidget(self.pending_count_label)
        layout.addStretch()
        layout.addWidget(self.low_resolution_count_label)
        layout.addStretch()
        layout.addWidget(self.decoded_count_label)
        layout.addStretch()
        layout.addWidget(self.suspected_count_label)
        return card

    def _create_action_card(self) -> QFrame:
        card = self._create_card()
        layout = QHBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        for text, callback, color in [
            ("填入常用预设", self._apply_common_preset, "#8e44ad"),
            ("保存配置", self._save_config, "#3498db"),
            ("刷新列表", self._refresh_task_table, "#7f8c8d"),
        ]:
            btn = self._create_button(text, color)
            btn.clicked.connect(callback)
            layout.addWidget(btn)

        self.start_btn = self._create_button("开始解码", "#27ae60")
        self.start_btn.clicked.connect(self._start_decode_queue)
        layout.addWidget(self.start_btn)

        self.stop_btn = self._create_button("停止", "#e74c3c")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_decode)
        layout.addWidget(self.stop_btn)

        clear_log_btn = self._create_button("清空日志", "#7f8c8d")
        clear_log_btn.clicked.connect(self.log_view.clear)
        layout.addWidget(clear_log_btn)

        manual_compare_btn = self._create_button("手动对比视频", "#9b59b6")
        manual_compare_btn.clicked.connect(self._open_manual_compare)
        layout.addWidget(manual_compare_btn)

        layout.addStretch()
        self.status_label = QLabel("未开始")
        self.status_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        layout.addWidget(self.status_label)
        return card

    def _create_task_card(self) -> QFrame:
        card = self._create_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        title = QLabel("解码列表")
        title.setStyleSheet(self._title_style())
        layout.addWidget(title)

        panel = QFrame()
        panel.setStyleSheet(
            """
            QFrame {
                background: #060b1a;
                border: 1px solid #16233a;
                border-radius: 10px;
            }
            """
        )
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(10, 10, 10, 10)
        panel_layout.setSpacing(10)

        self.task_scroll = QScrollArea()
        self.task_scroll.setWidgetResizable(True)
        self.task_scroll.setMinimumHeight(320)
        self.task_scroll.setStyleSheet(
            """
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: #091223;
                width: 10px;
                border-radius: 5px;
                margin: 2px;
            }
            QScrollBar::handle:vertical {
                background: #31476f;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #3d5a8f;
            }
            """
        )

        self.task_list_container = QWidget()
        self.task_list_container.setStyleSheet("background: transparent;")
        self.task_list_layout = QVBoxLayout(self.task_list_container)
        self.task_list_layout.setContentsMargins(0, 0, 0, 0)
        self.task_list_layout.setSpacing(8)
        self.task_scroll.setWidget(self.task_list_container)
        panel_layout.addWidget(self.task_scroll)

        footer = QHBoxLayout()
        footer.setSpacing(8)

        self.task_queue_count_label = QLabel("队列中有 0 个项目")
        self.task_queue_count_label.setStyleSheet("color: #b7c7e6; font-size: 12px;")
        footer.addWidget(self.task_queue_count_label)

        footer.addStretch()

        self.clear_completed_btn = self._create_button("清除已完成", "#273552", min_width=110, min_height=32)
        self.clear_completed_btn.clicked.connect(self._clear_completed_tasks)
        footer.addWidget(self.clear_completed_btn)

        self.clear_all_btn = self._create_button("清空", "#273552", min_width=80, min_height=32)
        self.clear_all_btn.clicked.connect(self._clear_all_tasks)
        footer.addWidget(self.clear_all_btn)

        panel_layout.addLayout(footer)
        layout.addWidget(panel)
        return card

    def _create_command_card(self) -> QFrame:
        card = self._create_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        title = QLabel("命令预览")
        title.setStyleSheet(self._title_style())
        layout.addWidget(title)
        self.command_preview = QPlainTextEdit()
        self.command_preview.setReadOnly(True)
        self.command_preview.setMaximumHeight(90)
        self.command_preview.setStyleSheet("QPlainTextEdit { background: #111827; color: #d1d5db; border: 1px solid #1f2937; border-radius: 8px; padding: 10px; }")
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.command_preview.setFont(font)
        layout.addWidget(self.command_preview)
        return card

    def _create_log_card(self) -> QFrame:
        card = self._create_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        title = QLabel("运行日志")
        title.setStyleSheet(self._title_style())
        layout.addWidget(title)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log_view.setMinimumHeight(260)
        self.log_view.setStyleSheet("QPlainTextEdit { background: #111827; color: #d1d5db; border: 1px solid #1f2937; border-radius: 8px; padding: 10px; }")
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.log_view.setFont(font)
        layout.addWidget(self.log_view)
        return card

    def _setup_ui(self):
        self.setObjectName("decodePage")
        self.setStyleSheet("QWidget#decodePage { background: #f3f5f9; }")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        page_scroll = QScrollArea()
        page_scroll.setWidgetResizable(True)
        page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        page_scroll.setStyleSheet(
            """
            QScrollArea {
                border: none;
                background: #f3f5f9;
            }
            QScrollBar:vertical {
                background: #eef2f7;
                width: 10px;
                border-radius: 5px;
                margin: 4px;
            }
            QScrollBar::handle:vertical {
                background: #b7c4d8;
                border-radius: 5px;
                min-height: 30px;
            }
            """
        )

        container = QWidget()
        container.setStyleSheet("background: #f3f5f9;")

        page_layout = QVBoxLayout(container)
        page_layout.setContentsMargins(18, 16, 18, 18)
        page_layout.setSpacing(14)

        page_layout.addWidget(self._create_page_header())

        body_layout = QHBoxLayout()
        body_layout.setSpacing(14)

        left_panel = QWidget()
        left_panel.setMinimumWidth(400)
        left_panel.setMaximumWidth(440)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(14)
        left_layout.addWidget(self._create_import_card())
        left_layout.addWidget(self._create_task_card())
        left_layout.addWidget(self._create_path_card())
        left_layout.addStretch(1)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(14)
        right_layout.addWidget(self._create_option_card())
        right_layout.addWidget(self._create_stats_card())
        right_layout.addStretch(1)

        body_layout.addWidget(left_panel, 0, Qt.AlignmentFlag.AlignTop)
        body_layout.addWidget(right_panel, 1, Qt.AlignmentFlag.AlignTop)

        page_layout.addLayout(body_layout)
        page_layout.addWidget(self._create_log_card())
        page_layout.addStretch(1)

        page_scroll.setWidget(container)
        main_layout.addWidget(page_scroll)

    def _create_page_header(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet("QFrame { background: transparent; border: none; }")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(12)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)

        title = QLabel("Lada解码")
        title.setStyleSheet("QLabel { color: #1f2a44; font-size: 24px; font-weight: bold; }")
        text_layout.addWidget(title)

        subtitle = QLabel("左侧导入与队列，右侧参数设置，底部显示命令预览和解码日志。")
        subtitle.setStyleSheet("QLabel { color: #70809a; font-size: 12px; }")
        subtitle.setWordWrap(True)
        text_layout.addWidget(subtitle)

        layout.addLayout(text_layout, 1)

        badge = QLabel('只处理解码队列里"待解码"的任务')
        badge.setStyleSheet(
            """
            QLabel {
                color: #32518a;
                background: #edf3ff;
                border: 1px solid #cfdcf3;
                border-radius: 14px;
                padding: 8px 12px;
                font-size: 12px;
            }
            """
        )
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        return card

    def _create_import_card(self) -> QFrame:
        card = self._create_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("导入队列")
        title.setStyleSheet(self._title_style())
        layout.addWidget(title)

        hint = QLabel("选择单个视频或整个目录，目录会递归读取所有视频并写入解码数据库。")
        hint.setWordWrap(True)
        hint.setStyleSheet(self._muted_text_style())
        layout.addWidget(hint)

        path_title = QLabel("解码视频位置")
        path_title.setStyleSheet("QLabel { color: #31405f; font-size: 12px; font-weight: bold; }")
        layout.addWidget(path_title)

        self.import_path_edit = QLineEdit()
        self.import_path_edit.setPlaceholderText("选择待解码的视频文件或目录")
        self.import_path_edit.returnPressed.connect(self._import_from_manual_path)
        self.import_path_edit.textChanged.connect(self._update_command_preview)
        self.import_path_edit.setStyleSheet(self._input_style())
        self.import_path_edit.setMinimumHeight(42)
        layout.addWidget(self.import_path_edit)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        button_row.addStretch()

        import_file_btn = self._create_button("文件", "#4f7cff", min_width=92, min_height=40)
        import_file_btn.clicked.connect(self._select_import_file)
        button_row.addWidget(import_file_btn)

        import_dir_btn = self._create_button("目录", "#22c55e", min_width=92, min_height=40)
        import_dir_btn.clicked.connect(self._select_import_dir)
        button_row.addWidget(import_dir_btn)

        layout.addLayout(button_row)

        tips = QLabel("文件名重复会标记为「疑已解码」，分辨率低于1080p会标记为「低分辨率」，均可手动改为待解码。")
        tips.setWordWrap(True)
        tips.setStyleSheet("QLabel { color: #d97706; font-size: 11px; }")
        layout.addWidget(tips)
        return card

        card = self._create_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("导入队列")
        title.setStyleSheet(self._title_style())
        layout.addWidget(title)

        hint = QLabel("选择单个视频或整个目录，目录会递归读取所有视频并写入解码数据库。")
        hint.setWordWrap(True)
        hint.setStyleSheet(self._muted_text_style())
        layout.addWidget(hint)

        self.import_path_edit = QLineEdit()
        self.import_path_edit.setPlaceholderText("选择待解码的视频文件或目录")
        self.import_path_edit.returnPressed.connect(self._import_from_manual_path)
        self.import_path_edit.textChanged.connect(self._update_command_preview)
        layout.addLayout(
            self._build_form_row(
                "解码视频位置",
                self.import_path_edit,
                [("文件", self._select_import_file, "#3b82f6"), ("目录", self._select_import_dir, "#22c55e")],
                label_min_width=112,
            )
        )

        tips = QLabel("文件名重复会标记为「疑已解码」，分辨率低于1080p会标记为「低分辨率」，均可手动改为待解码。")
        tips.setWordWrap(True)
        tips.setStyleSheet("QLabel { color: #f59e0b; font-size: 11px; }")
        layout.addWidget(tips)
        return card

    def _create_path_card(self) -> QFrame:
        card = self._create_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("输出与运行")
        title.setStyleSheet(self._title_style())
        layout.addWidget(title)

        desc = QLabel("这里设置解码后的保存位置、输出模板、缓存目录以及 lada-cli 可执行文件。")
        desc.setWordWrap(True)
        desc.setStyleSheet(self._muted_text_style())
        layout.addWidget(desc)

        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("选择解码后输出目录")
        self.output_path_edit.textChanged.connect(self._update_command_preview)
        layout.addLayout(
            self._build_form_row(
                "输出目录",
                self.output_path_edit,
                [("浏览", self._select_output_dir, "#253554")],
            )
        )

        self.output_pattern_edit = QLineEdit()
        self.output_pattern_edit.setPlaceholderText("{orig_file_name}.restored.mp4")
        self.output_pattern_edit.textChanged.connect(self._update_command_preview)
        layout.addLayout(self._build_form_row("输出模板", self.output_pattern_edit))

        pattern_hint = QLabel("模板必须带 `{orig_file_name}`，例如 `{orig_file_name}.restored.mp4`。")
        pattern_hint.setStyleSheet(self._muted_text_style())
        layout.addWidget(pattern_hint)

        self.temp_dir_edit = QLineEdit()
        self.temp_dir_edit.setPlaceholderText("留空时默认使用系统临时目录")
        self.temp_dir_edit.textChanged.connect(self._update_command_preview)
        layout.addLayout(
            self._build_form_row(
                "缓存目录",
                self.temp_dir_edit,
                [("浏览", self._select_temp_dir, "#253554")],
            )
        )

        self.cli_path_edit = QLineEdit()
        self.cli_path_edit.setPlaceholderText("lada-cli 或 D:/lada/lada-cli.exe")
        self.cli_path_edit.textChanged.connect(self._update_command_preview)
        layout.addLayout(
            self._build_form_row(
                "CLI 路径",
                self.cli_path_edit,
                [("浏览", self._select_cli_path, "#253554")],
            )
        )
        return card

    def _create_option_card(self) -> QFrame:
        card = self._create_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("解码参数")
        title.setStyleSheet(self._title_style())
        layout.addWidget(title)

        desc = QLabel("参数仍然按 Lada CLI 的实际选项来配置，这里只是换成更贴近你参考图的展示方式。")
        desc.setWordWrap(True)
        desc.setStyleSheet(self._muted_text_style())
        layout.addWidget(desc)

        self.detection_model_combo = self._create_select_combo(self.DETECTION_MODELS)
        self.detection_model_combo.currentIndexChanged.connect(self._update_command_preview)
        layout.addLayout(self._build_form_row("检测模型", self.detection_model_combo))

        self.restoration_model_combo = self._create_select_combo(self.RESTORATION_MODELS)
        self.restoration_model_combo.currentIndexChanged.connect(self._update_command_preview)
        layout.addLayout(self._build_form_row("修复模型", self.restoration_model_combo))

        self.device_combo = self._create_select_combo(self.DEVICE_OPTIONS)
        self.device_combo.currentIndexChanged.connect(self._update_command_preview)
        layout.addLayout(self._build_form_row("设备", self.device_combo))

        self.encoding_preset_combo = self._create_select_combo(self.ENCODING_PRESETS)
        self.encoding_preset_combo.currentIndexChanged.connect(self._update_command_preview)
        layout.addLayout(self._build_form_row("编码预设", self.encoding_preset_combo))

        self.max_clip_spin = QSpinBox()
        self.max_clip_spin.setRange(30, 2000)
        self.max_clip_spin.setSingleStep(10)
        self.max_clip_spin.valueChanged.connect(self._update_command_preview)
        layout.addLayout(self._build_form_row("切片帧数", self.max_clip_spin))

        layout.addWidget(self._create_subsection_label("开关选项"))

        self.fp16_cb = self._create_checkbox("")
        self.fp16_cb.toggled.connect(self._update_command_preview)
        layout.addWidget(self._create_toggle_row("FP16 半精度", "支持的 GPU 上可能更快，但少数显卡会有质量损失。", self.fp16_cb))

        self.detect_face_cb = self._create_checkbox("")
        self.detect_face_cb.toggled.connect(self._update_command_preview)
        layout.addWidget(self._create_toggle_row("面部检测", "同时尝试检测人脸马赛克，可减少遗漏，但也可能误判。", self.detect_face_cb))

        self.mp4_fast_start_cb = self._create_checkbox("")
        self.mp4_fast_start_cb.toggled.connect(self._update_command_preview)
        layout.addWidget(self._create_toggle_row("MP4 边传边播", "输出时写入 fast start 信息，更适合在线播放。", self.mp4_fast_start_cb))
        return card

    def _create_stats_card(self) -> QFrame:
        card = self._create_card()
        layout = QHBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        pending_tile, self.pending_count_label = self._create_stat_tile("待解码", "#f59e0b")
        decoded_tile, self.decoded_count_label = self._create_stat_tile("已经解码", "#18e0b5")
        suspected_tile, self.suspected_count_label = self._create_stat_tile("疑已解码", "#f87171")

        layout.addWidget(pending_tile)
        layout.addWidget(decoded_tile)
        layout.addWidget(suspected_tile)
        return card

    def _create_action_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet("QFrame { background: transparent; border: none; }")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        preset_btn = self._create_button("常用预设", "#5865f2")
        preset_btn.clicked.connect(self._apply_common_preset)
        layout.addWidget(preset_btn)

        save_btn = self._create_button("保存配置", "#64748b")
        save_btn.clicked.connect(self._save_config)
        layout.addWidget(save_btn)

        refresh_btn = self._create_button("刷新队列", "#64748b")
        refresh_btn.clicked.connect(self._refresh_task_table)
        layout.addWidget(refresh_btn)

        layout.addStretch()

        clear_log_btn = self._create_button("清空日志", "#94a3b8")
        clear_log_btn.clicked.connect(self._clear_log)
        layout.addWidget(clear_log_btn)

        self.stop_btn = self._create_button("停止", "#ef4444", min_width=88)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_decode)
        layout.addWidget(self.stop_btn)

        self.start_btn = self._create_button("开始解码", "#4f7cff", min_width=120)
        self.start_btn.clicked.connect(self._start_decode_queue)
        layout.addWidget(self.start_btn)

        self.status_label = QLabel("队列空闲")
        self.status_label.setStyleSheet("QLabel { color: #70809a; font-size: 12px; font-weight: bold; padding-left: 8px; }")
        layout.addWidget(self.status_label)
        return card

    def _create_task_card(self) -> QFrame:
        card = self._create_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(10)

        title = QLabel("解码队列")
        title.setStyleSheet(self._title_style())
        header.addWidget(title)

        header.addStretch()

        self.task_queue_count_label = QLabel("0 项")
        self.task_queue_count_label.setStyleSheet("QLabel { color: #91a3c7; font-size: 12px; }")
        header.addWidget(self.task_queue_count_label)
        layout.addLayout(header)

        self.task_scroll = QScrollArea()
        self.task_scroll.setWidgetResizable(True)
        self.task_scroll.setMinimumHeight(360)
        self.task_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.task_scroll.setStyleSheet(
            """
            QScrollArea {
                border: 1px solid #d9dfeb;
                border-radius: 12px;
                background: #f8fafc;
            }
            QScrollBar:vertical {
                background: #eef2f7;
                width: 10px;
                border-radius: 5px;
                margin: 4px;
            }
            QScrollBar::handle:vertical {
                background: #b7c4d8;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #8ea2bf;
            }
            """
        )

        self.task_list_container = QWidget()
        self.task_list_container.setStyleSheet("background: #f8fafc;")
        self.task_list_layout = QVBoxLayout(self.task_list_container)
        self.task_list_layout.setContentsMargins(8, 8, 8, 8)
        self.task_list_layout.setSpacing(8)
        self.task_scroll.setWidget(self.task_list_container)
        layout.addWidget(self.task_scroll, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)

        self.clear_completed_btn = self._create_button("清除已完成", "#94a3b8", min_width=118, min_height=34)
        self.clear_completed_btn.clicked.connect(self._clear_completed_tasks)
        footer.addWidget(self.clear_completed_btn)

        self.clear_all_btn = self._create_button("清空", "#94a3b8", min_width=84, min_height=34)
        self.clear_all_btn.clicked.connect(self._clear_all_tasks)
        footer.addWidget(self.clear_all_btn)

        footer.addStretch()
        layout.addLayout(footer)
        return card

    def _create_command_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            """
            QFrame {
                background: #ffffff;
                border: 1px solid #d9dfeb;
                border-radius: 12px;
            }
            """
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        title = QLabel("命令预览")
        title.setStyleSheet("QLabel { color: #1f2a44; font-size: 13px; font-weight: bold; }")
        layout.addWidget(title)

        self.command_preview = QPlainTextEdit()
        self.command_preview.setReadOnly(True)
        self.command_preview.setMaximumHeight(84)
        self.command_preview.setStyleSheet(
            """
            QPlainTextEdit {
                background: #f8fafc;
                color: #334155;
                border: 1px solid #dbe2ee;
                border-radius: 10px;
                padding: 10px;
            }
            """
        )
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.command_preview.setFont(font)
        layout.addWidget(self.command_preview)
        return card

    def _create_log_card(self) -> QFrame:
        card = self._create_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(10)

        title = QLabel("系统输出")
        title.setStyleSheet(self._title_style())
        header.addWidget(title)

        header.addStretch()

        log_hint = QLabel("Lada CLI 的标准输出和错误输出都会显示在这里")
        log_hint.setStyleSheet(self._muted_text_style())
        header.addWidget(log_hint)
        layout.addLayout(header)

        layout.addWidget(self._create_action_card())
        layout.addWidget(self._create_command_card())

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log_view.setMinimumHeight(220)
        self.log_view.setStyleSheet(
            """
            QPlainTextEdit {
                background: #f8fafc;
                color: #334155;
                border: 1px solid #dbe2ee;
                border-radius: 12px;
                padding: 10px;
            }
            QScrollBar:vertical {
                background: #eef2f7;
                width: 10px;
                border-radius: 5px;
                margin: 4px;
            }
            QScrollBar::handle:vertical {
                background: #b7c4d8;
                border-radius: 5px;
                min-height: 30px;
            }
            """
        )
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.log_view.setFont(font)
        layout.addWidget(self.log_view, 1)

        footer = QHBoxLayout()
        footer.setSpacing(12)

        self.current_task_label = QLabel("当前任务: 队列空闲")
        self.current_task_label.setStyleSheet("QLabel { color: #1f2a44; font-size: 13px; font-weight: bold; }")
        footer.addWidget(self.current_task_label)

        self.queue_progress_bar = QProgressBar()
        self.queue_progress_bar.setTextVisible(False)
        self.queue_progress_bar.setFixedHeight(8)
        self.queue_progress_bar.setRange(0, 1)
        self.queue_progress_bar.setValue(0)
        self.queue_progress_bar.setStyleSheet(
            """
            QProgressBar {
                background: #e9edf5;
                border: 1px solid #d9dfeb;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background: #4f7cff;
                border-radius: 4px;
            }
            """
        )
        footer.addWidget(self.queue_progress_bar, 1)

        self.queue_meta_label = QLabel("0 / 0")
        self.queue_meta_label.setStyleSheet("QLabel { color: #70809a; font-size: 12px; }")
        footer.addWidget(self.queue_meta_label)

        layout.addLayout(footer)
        return card

    def _create_toggle_row(self, title_text: str, description: str, checkbox: QCheckBox) -> QFrame:
        row = QFrame()
        row.setStyleSheet(
            """
            QFrame {
                background: #f8fafc;
                border: 1px solid #dbe2ee;
                border-radius: 12px;
            }
            """
        )

        layout = QHBoxLayout(row)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(3)

        title = QLabel(title_text)
        title.setStyleSheet("QLabel { color: #1f2a44; font-size: 13px; font-weight: bold; }")
        text_layout.addWidget(title)

        desc = QLabel(description)
        desc.setWordWrap(True)
        desc.setStyleSheet("QLabel { color: #70809a; font-size: 11px; }")
        text_layout.addWidget(desc)

        layout.addLayout(text_layout, 1)
        layout.addWidget(checkbox, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _create_stat_tile(self, title_text: str, accent_color: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setStyleSheet(
            f"""
            QFrame {{
                background: #ffffff;
                border: 1px solid #dfe6f2;
                border-left: 3px solid {accent_color};
                border-radius: 12px;
            }}
            """
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        title = QLabel(title_text)
        title.setStyleSheet("QLabel { color: #70809a; font-size: 11px; }")
        layout.addWidget(title)

        value_label = QLabel("0")
        value_label.setStyleSheet(f"QLabel {{ color: {accent_color}; font-size: 20px; font-weight: bold; }}")
        layout.addWidget(value_label)
        return card, value_label

    def _clear_log(self):
        if hasattr(self, "log_view"):
            self.log_view.clear()

    def _load_config(self):
        self.cli_path_edit.setText(config.get("lada_cli_path", "lada-cli"))
        self.import_path_edit.setText(config.get("lada_input_path", self._get_compare_default_path("undecoded")))
        self.output_path_edit.setText(config.get("lada_output_path", self._get_compare_default_path("decoded")))
        self.temp_dir_edit.setText(config.get("lada_temp_dir", "") or tempfile.gettempdir())
        self.output_pattern_edit.setText(
            config.get("lada_output_file_pattern", "{orig_file_name}.restored.mp4")
        )
        self._set_combo_value(self.detection_model_combo, config.get("lada_detection_model", "v4-fast"))
        self._set_combo_value(
            self.restoration_model_combo,
            config.get("lada_restoration_model", "basicvsrpp-v1.2"),
        )
        self._set_combo_value(self.device_combo, config.get("lada_device", "cuda"))
        self._set_combo_value(
            self.encoding_preset_combo,
            config.get("lada_encoding_preset", "h264-cpu-fast"),
        )
        self.fp16_cb.setChecked(config.get("lada_fp16", True))
        self.detect_face_cb.setChecked(config.get("lada_detect_face_mosaics", False))
        self.mp4_fast_start_cb.setChecked(config.get("lada_mp4_fast_start", False))
        self.max_clip_spin.setValue(config.get("lada_max_clip_length", 180))

    def _save_config(self, checked=None, show_message: bool = True):
        config.set("lada_cli_path", self.cli_path_edit.text().strip(), auto_save=False)
        config.set("lada_input_path", self.import_path_edit.text().strip(), auto_save=False)
        config.set("lada_output_path", self.output_path_edit.text().strip(), auto_save=False)
        config.set("lada_temp_dir", self.temp_dir_edit.text().strip(), auto_save=False)
        config.set("lada_output_file_pattern", self.output_pattern_edit.text().strip(), auto_save=False)
        config.set("lada_detection_model", self.detection_model_combo.currentText().strip(), auto_save=False)
        config.set(
            "lada_restoration_model",
            self.restoration_model_combo.currentText().strip(),
            auto_save=False,
        )
        config.set("lada_device", self.device_combo.currentText().strip(), auto_save=False)
        config.set(
            "lada_encoding_preset",
            self.encoding_preset_combo.currentText().strip(),
            auto_save=False,
        )
        config.set("lada_fp16", self.fp16_cb.isChecked(), auto_save=False)
        config.set("lada_detect_face_mosaics", self.detect_face_cb.isChecked(), auto_save=False)
        config.set("lada_mp4_fast_start", self.mp4_fast_start_cb.isChecked(), auto_save=False)
        config.set("lada_max_clip_length", self.max_clip_spin.value(), auto_save=False)
        config.save()
        if show_message:
            QMessageBox.information(self, "成功", "Lada 解码配置已保存。")

    def _ensure_decode_tables(self):
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS decode_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL UNIQUE,
                file_size INTEGER,
                resolution TEXT,
                width INTEGER,
                height INTEGER,
                source_root TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                output_path TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                decoded_at DATETIME
            )
            """
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_decode_tasks_status ON decode_tasks(status)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_decode_tasks_file_name ON decode_tasks(file_name)")

        # 添加新字段（如果不存在）
        try:
            db.execute("ALTER TABLE decode_tasks ADD COLUMN resolution TEXT")
        except:
            pass  # 字段已存在
        try:
            db.execute("ALTER TABLE decode_tasks ADD COLUMN width INTEGER")
        except:
            pass  # 字段已存在
        try:
            db.execute("ALTER TABLE decode_tasks ADD COLUMN height INTEGER")
        except:
            pass  # 字段已存在

    def _detect_video_resolution(self, file_path: str) -> tuple[int, int, str]:
        """检测视频分辨率，返回 (width, height, resolution_str)"""
        try:
            import subprocess
            import json

            # 使用 ffprobe 获取视频分辨率
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_streams",
                    "-select_streams", "v:0",
                    file_path
                ],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                data = json.loads(result.stdout)
                if data.get("streams"):
                    stream = data["streams"][0]
                    width = int(stream.get("width", 0))
                    height = int(stream.get("height", 0))

                    # 格式化分辨率字符串
                    if width > 0 and height > 0:
                        resolution_str = f"{width}x{height}"
                        return width, height, resolution_str

        except Exception as e:
            logger.warning(f"检测视频分辨率失败: {file_path}, {e}")

        return 0, 0, "未知"

    def _is_low_resolution(self, height: int) -> bool:
        """判断是否为低分辨率"""
        return height > 0 and height < self.LOW_RESOLUTION_THRESHOLD

    def _refresh_task_table(self):
        rows = db.query(
            """
            SELECT id, file_name, file_path, status, output_path, resolution, width, height
            FROM decode_tasks
            ORDER BY
                CASE status
                    WHEN ? THEN 0
                    WHEN ? THEN 1
                    WHEN ? THEN 2
                    ELSE 3
                END,
                updated_at DESC,
                id DESC
            """,
            (self.STATUS_PENDING, self.STATUS_LOW_RESOLUTION, self.STATUS_SUSPECTED),
        )

        pending_count = 0
        decoded_count = 0
        suspected_count = 0
        low_resolution_count = 0
        self._clear_task_cards()

        for row in rows:
            status = row["status"]
            if status == self.STATUS_PENDING:
                pending_count += 1
            elif status == self.STATUS_DECODED:
                decoded_count += 1
            elif status == self.STATUS_SUSPECTED:
                suspected_count += 1
            elif status == self.STATUS_LOW_RESOLUTION:
                low_resolution_count += 1
            self.task_list_layout.addWidget(self._create_task_item_card(row))

        self.task_list_layout.addStretch(1)

        self.pending_count_label.setText(f"待解码: {pending_count}")
        self.decoded_count_label.setText(f"已经解码: {decoded_count}")
        self.suspected_count_label.setText(f"疑已解码: {suspected_count}")
        self.low_resolution_count_label.setText(f"低分辨率: {low_resolution_count}")
        self.task_queue_count_label.setText(f"队列中有 {len(rows)} 个项目")
        self.clear_completed_btn.setEnabled(decoded_count > 0)
        self.clear_all_btn.setEnabled(len(rows) > 0 and not self._queue_running)
        self._update_command_preview()

    def _mark_task_pending(self, task_id: int):
        db.execute(
            """
            UPDATE decode_tasks
            SET status = ?, output_path = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (self.STATUS_PENDING, task_id),
        )
        logger.info(f"解码任务改为待解码: {task_id}")
        self._refresh_task_table()

    def _clear_task_cards(self):
        while self.task_list_layout.count():
            item = self.task_list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _create_task_item_card(self, row) -> QFrame:
        status = row["status"]
        task_id = row["id"]
        resolution = row.get("resolution", "")
        width = row.get("width", 0)
        height = row.get("height", 0)

        display_status = self.STATUS_LABELS.get(status, status)
        status_color = "#18e0b5" if self._is_processing_task(task_id) else self._color_to_hex(
            self.STATUS_COLORS.get(status, QColor(183, 199, 230))
        )
        if self._is_processing_task(task_id):
            display_status = "处理中"

        card = QFrame()
        # 根据状态设置不同颜色边框和背景
        if status == self.STATUS_SUSPECTED:
            border_color = "#8a2f3f"
            background = "#33222a"
        elif status == self.STATUS_LOW_RESOLUTION:
            border_color = "#4a6fa5"
            background = "#1a2a3a"
        else:
            border_color = "#2a3a57"
            background = "#243044"

        card.setToolTip(row["file_path"])
        card.setStyleSheet(
            f"""
            QFrame {{
                background: {background};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
            """
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        drag_label = QLabel("⋮⋮")
        drag_label.setStyleSheet("color: #7f91b3; font-size: 12px;")
        top_row.addWidget(drag_label)

        file_label = QLabel(row["file_name"])
        file_label.setStyleSheet("color: #e7eefc; font-size: 13px; font-weight: bold;")
        file_label.setToolTip(row["file_path"])
        top_row.addWidget(file_label, 1)

        # 显示分辨率标签
        if resolution and resolution != "未知":
            resolution_label = QLabel(resolution)
            if self._is_low_resolution(height):
                resolution_label.setStyleSheet("color: #6495ed; font-size: 11px; font-weight: bold;")
            else:
                resolution_label.setStyleSheet("color: #90a4c4; font-size: 11px;")
            top_row.addWidget(resolution_label)

        # 根据状态显示不同按钮
        if status == self.STATUS_SUSPECTED:
            action_btn = self._create_button("改成待解码", "#e67e22", min_width=96, min_height=28)
            action_btn.clicked.connect(lambda checked=False, current_id=task_id: self._mark_task_pending(current_id))
            top_row.addWidget(action_btn)
        elif status == self.STATUS_LOW_RESOLUTION:
            action_btn = self._create_button("改成待解码", "#e67e22", min_width=96, min_height=28)
            action_btn.clicked.connect(lambda checked=False, current_id=task_id: self._mark_task_pending(current_id))
            top_row.addWidget(action_btn)

        layout.addLayout(top_row)

        path_label = QLabel(row["file_path"])
        path_label.setStyleSheet("color: #92a6ca; font-size: 11px;")
        path_label.setWordWrap(False)
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path_label.setToolTip(row["file_path"])
        layout.addWidget(path_label)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(6)

        dot = QLabel("○")
        dot.setStyleSheet(f"color: {status_color}; font-size: 12px; font-weight: bold;")
        bottom_row.addWidget(dot)

        status_label = QLabel(display_status)
        status_label.setStyleSheet(f"color: {status_color}; font-size: 12px;")
        bottom_row.addWidget(status_label)

        # 如果是低分辨率（无论什么状态），显示低分辨率标签
        if self._is_low_resolution(height) and status != self.STATUS_LOW_RESOLUTION:
            low_res_tag = QLabel("低分辨率")
            low_res_tag.setStyleSheet("color: #6495ed; font-size: 11px; font-weight: bold;")
            bottom_row.addWidget(low_res_tag)

        bottom_row.addStretch()

        if row["output_path"]:
            output_label = QLabel("已生成输出")
            output_label.setStyleSheet("color: #90a4c4; font-size: 11px;")
            output_label.setToolTip(row["output_path"])
            bottom_row.addWidget(output_label)

        layout.addLayout(bottom_row)
        return card

    def _ensure_decode_tables(self):
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS decode_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL UNIQUE,
                file_size INTEGER,
                source_root TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                output_path TEXT,
                compare_decoded_path TEXT,
                is_visible INTEGER NOT NULL DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                decoded_at DATETIME
            )
            """
        )
        with db.get_connection() as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(decode_tasks)").fetchall()}
            if "compare_decoded_path" not in columns:
                conn.execute("ALTER TABLE decode_tasks ADD COLUMN compare_decoded_path TEXT")
            if "is_visible" not in columns:
                conn.execute("ALTER TABLE decode_tasks ADD COLUMN is_visible INTEGER NOT NULL DEFAULT 1")
            conn.commit()

        db.execute("CREATE INDEX IF NOT EXISTS idx_decode_tasks_status ON decode_tasks(status)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_decode_tasks_file_name ON decode_tasks(file_name)")

    def _detect_video_resolution(self, file_path: str) -> tuple[int, int, str]:
        """检测视频分辨率，返回 (width, height, resolution_str)"""
        try:
            import subprocess
            import json

            # 使用 ffprobe 获取视频分辨率
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_streams",
                    "-select_streams", "v:0",
                    file_path
                ],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                data = json.loads(result.stdout)
                if data.get("streams"):
                    stream = data["streams"][0]
                    width = int(stream.get("width", 0))
                    height = int(stream.get("height", 0))

                    # 格式化分辨率字符串
                    if width > 0 and height > 0:
                        resolution_str = f"{width}x{height}"
                        return width, height, resolution_str

        except Exception as e:
            logger.warning(f"检测视频分辨率失败: {file_path}, {e}")

        return 0, 0, "未知"

    def _is_low_resolution(self, height: int) -> bool:
        """判断是否为低分辨率"""
        return height > 0 and height < self.LOW_RESOLUTION_THRESHOLD

    def _get_enabled_compare_paths(self, path_type: str) -> list[str]:
        try:
            rows = db.query(
                "SELECT path FROM compare_paths WHERE type = ? AND enabled = 1 ORDER BY id ASC",
                (path_type,),
            )
        except Exception:
            return []
        return [row["path"] for row in rows if row["path"]]

    def _build_decoded_compare_index(self) -> dict[str, str]:
        compare_index: dict[str, str] = {}
        for path_str in self._get_enabled_compare_paths("decoded"):
            root = Path(path_str)
            if not root.exists():
                continue
            for file_path in self._collect_video_files(root):
                av_code = self._parser.parse_from_filename(file_path.name)
                if av_code and av_code not in compare_index:
                    compare_index[av_code] = str(file_path)
        return compare_index

    def _build_decode_task_compare_index(self) -> dict[str, str]:
        compare_index: dict[str, str] = {}
        rows = db.query(
            """
            SELECT file_name, output_path, compare_decoded_path
            FROM decode_tasks
            WHERE (output_path IS NOT NULL AND output_path != '')
               OR (compare_decoded_path IS NOT NULL AND compare_decoded_path != '')
            ORDER BY decoded_at DESC, updated_at DESC, id DESC
            """
        )
        for row in rows:
            candidate_path = row["output_path"] or row["compare_decoded_path"]
            if not candidate_path:
                continue
            candidate_names = [Path(candidate_path).name, row["file_name"]]
            for candidate_name in candidate_names:
                av_code = self._parser.parse_from_filename(candidate_name)
                if av_code and av_code not in compare_index:
                    compare_index[av_code] = candidate_path
                    break
        return compare_index

    def _find_related_decoded_path(
        self,
        source_file: Path,
        decoded_compare_index: dict[str, str],
        task_compare_index: dict[str, str],
    ) -> str | None:
        av_code = self._parser.parse_from_filename(source_file.name)
        if not av_code:
            return None
        return task_compare_index.get(av_code) or decoded_compare_index.get(av_code)

    def _sync_pending_tasks_with_compare_paths(self):
        candidates = db.query(
            """
            SELECT id, file_path, status, output_path, compare_decoded_path
            FROM decode_tasks
            WHERE COALESCE(is_visible, 1) = 1
              AND status != ?
              AND (compare_decoded_path IS NULL OR compare_decoded_path = '')
            ORDER BY id DESC
            """,
            (self.STATUS_DECODED,),
        )
        if not candidates:
            return

        decoded_compare_index = self._build_decoded_compare_index()
        task_compare_index = self._build_decode_task_compare_index()
        updated_count = 0

        for row in candidates:
            linked_decoded_path = self._find_related_decoded_path(
                Path(row["file_path"]),
                decoded_compare_index,
                task_compare_index,
            )
            if not linked_decoded_path:
                continue

            next_status = row["status"]
            if row["status"] == self.STATUS_PENDING and not row["output_path"]:
                next_status = self.STATUS_SUSPECTED

            db.execute(
                """
                UPDATE decode_tasks
                SET compare_decoded_path = ?,
                    status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (linked_decoded_path, next_status, row["id"]),
            )
            updated_count += 1

        if updated_count:
            logger.info(f"Lada解码队列已回填 {updated_count} 条旧输出关联记录")

    def _create_task_card(self) -> QFrame:
        self._selected_task_ids = set()

        card = self._create_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(10)

        title = QLabel("解码队列")
        title.setStyleSheet(self._title_style())
        header.addWidget(title)

        header.addStretch()

        self.task_queue_count_label = QLabel("0 项")
        self.task_queue_count_label.setStyleSheet("QLabel { color: #91a3c7; font-size: 12px; }")
        header.addWidget(self.task_queue_count_label)
        layout.addLayout(header)

        self.task_scroll = QScrollArea()
        self.task_scroll.setWidgetResizable(True)
        self.task_scroll.setMinimumHeight(360)
        self.task_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.task_scroll.setStyleSheet(
            """
            QScrollArea {
                border: 1px solid #d9dfeb;
                border-radius: 12px;
                background: #f8fafc;
            }
            QScrollBar:vertical {
                background: #eef2f7;
                width: 10px;
                border-radius: 5px;
                margin: 4px;
            }
            QScrollBar::handle:vertical {
                background: #b7c4d8;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #8ea2bf;
            }
            """
        )

        self.task_list_container = QWidget()
        self.task_list_container.setStyleSheet("background: #f8fafc;")
        self.task_list_layout = QVBoxLayout(self.task_list_container)
        self.task_list_layout.setContentsMargins(8, 8, 8, 8)
        self.task_list_layout.setSpacing(8)
        self.task_scroll.setWidget(self.task_list_container)
        layout.addWidget(self.task_scroll, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)

        self.remove_selected_btn = self._create_button("移除选中", "#94a3b8", min_width=126, min_height=34)
        self.remove_selected_btn.clicked.connect(self._remove_selected_tasks)
        footer.addWidget(self.remove_selected_btn)

        self.clear_completed_btn = self._create_button("清除已完成", "#94a3b8", min_width=118, min_height=34)
        self.clear_completed_btn.clicked.connect(self._clear_completed_tasks)
        footer.addWidget(self.clear_completed_btn)

        self.clear_all_btn = self._create_button("清空列表", "#94a3b8", min_width=98, min_height=34)
        self.clear_all_btn.clicked.connect(self._clear_all_tasks)
        footer.addWidget(self.clear_all_btn)

        footer.addStretch()
        layout.addLayout(footer)
        return card

    def _update_task_action_buttons(self, total_count: int | None = None, decoded_count: int | None = None):
        selected_count = len(getattr(self, "_selected_task_ids", set()))
        if hasattr(self, "remove_selected_btn"):
            self.remove_selected_btn.setText(
                "移除选中" if selected_count == 0 else f"移除选中({selected_count})"
            )
            self.remove_selected_btn.setEnabled(selected_count > 0 and not self._queue_running)

        if total_count is not None and hasattr(self, "clear_all_btn"):
            self.clear_all_btn.setEnabled(total_count > 0 and not self._queue_running)

        if decoded_count is not None and hasattr(self, "clear_completed_btn"):
            self.clear_completed_btn.setEnabled(decoded_count > 0 and not self._queue_running)

    def _toggle_task_selected(self, task_id: int, checked: bool):
        if not hasattr(self, "_selected_task_ids"):
            self._selected_task_ids = set()
        if checked:
            self._selected_task_ids.add(task_id)
        else:
            self._selected_task_ids.discard(task_id)
        self._update_task_action_buttons()

    def _archive_task_ids(self, task_ids: list[int]):
        if self._queue_running:
            QMessageBox.information(self, "提示", "解码进行中时不能移除队列项目。")
            return

        ids = [int(task_id) for task_id in task_ids if task_id is not None]
        ids = [task_id for task_id in ids if task_id != self._current_task_id]
        if not ids:
            return

        placeholders = ",".join("?" for _ in ids)
        with db.get_connection() as conn:
            conn.execute(
                f"""
                UPDATE decode_tasks
                SET is_visible = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id IN ({placeholders})
                """,
                tuple(ids),
            )
            conn.commit()

        if hasattr(self, "_selected_task_ids"):
            self._selected_task_ids.difference_update(ids)
        logger.info(f"Lada解码队列已归档 {len(ids)} 个任务")
        self._refresh_task_table()

    def _remove_selected_tasks(self):
        selected_ids = sorted(getattr(self, "_selected_task_ids", set()))
        if not selected_ids:
            return
        self._archive_task_ids(selected_ids)

    def _remove_single_task(self, task_id: int):
        self._archive_task_ids([task_id])

    def _refresh_task_table(self):
        self._sync_pending_tasks_with_compare_paths()

        rows = db.query(
            """
            SELECT id, file_name, file_path, status, output_path, compare_decoded_path
            FROM decode_tasks
            WHERE COALESCE(is_visible, 1) = 1
            ORDER BY
                CASE status
                    WHEN ? THEN 0
                    WHEN ? THEN 1
                    ELSE 2
                END,
                updated_at DESC,
                id DESC
            """,
            (self.STATUS_PENDING, self.STATUS_SUSPECTED),
        )

        if not hasattr(self, "_selected_task_ids"):
            self._selected_task_ids = set()
        visible_ids = {row["id"] for row in rows}
        self._selected_task_ids.intersection_update(visible_ids)

        pending_count = 0
        decoded_count = 0
        suspected_count = 0

        self._clear_task_cards()

        for row in rows:
            status = row["status"]
            if status == self.STATUS_PENDING:
                pending_count += 1
            elif status == self.STATUS_DECODED:
                decoded_count += 1
            elif status == self.STATUS_SUSPECTED:
                suspected_count += 1
            self.task_list_layout.addWidget(self._create_task_item_card(row))

        self.task_list_layout.addStretch(1)

        self.pending_count_label.setText(str(pending_count))
        self.decoded_count_label.setText(str(decoded_count))
        self.suspected_count_label.setText(str(suspected_count))
        self.task_queue_count_label.setText(f"{len(rows)} 项")
        self._update_task_action_buttons(len(rows), decoded_count)
        self._update_queue_overview(len(rows), pending_count, decoded_count)
        self._update_command_preview()

    def _mark_task_pending(self, task_id: int):
        db.execute(
            """
            UPDATE decode_tasks
            SET status = ?,
                output_path = NULL,
                is_visible = 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (self.STATUS_PENDING, task_id),
        )
        logger.info(f"Lada解码任务改为待解码: {task_id}")
        self._refresh_task_table()

    def _mark_current_task_decoded(self):
        if self._current_task_id is None:
            return

        db.execute(
            """
            UPDATE decode_tasks
            SET status = ?,
                output_path = ?,
                compare_decoded_path = ?,
                is_visible = 1,
                decoded_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                self.STATUS_DECODED,
                self._current_output_path,
                self._current_output_path,
                self._current_task_id,
            ),
        )

    def _import_from_path(self, path_str: str):
        if not path_str:
            QMessageBox.warning(self, "提示", "请先选择文件或目录。")
            return

        path = Path(path_str)
        if not path.exists():
            QMessageBox.warning(self, "提示", f"路径不存在：\n{path_str}")
            return

        files = self._collect_video_files(path)
        if not files:
            QMessageBox.warning(self, "提示", "没有找到可导入的视频文件。")
            return

        decoded_compare_index = self._build_decoded_compare_index()
        task_compare_index = self._build_decode_task_compare_index()

        inserted_count = 0
        suspected_count = 0
        existing_count = 0

        for file_path in files:
            source_root = str(path if path.is_dir() else file_path.parent)
            linked_decoded_path = self._find_related_decoded_path(
                file_path,
                decoded_compare_index,
                task_compare_index,
            )

            existing_by_path = db.query_one(
                """
                SELECT id, status, output_path, compare_decoded_path
                FROM decode_tasks
                WHERE file_path = ?
                """,
                (str(file_path),),
            )
            if existing_by_path:
                existing_compare_path = (
                    existing_by_path["output_path"]
                    or existing_by_path["compare_decoded_path"]
                    or linked_decoded_path
                )
                if existing_by_path["status"] == self.STATUS_DECODED and existing_by_path["output_path"]:
                    next_status = self.STATUS_DECODED
                elif existing_by_path["status"] == self.STATUS_PENDING and existing_by_path["compare_decoded_path"]:
                    next_status = self.STATUS_PENDING
                else:
                    next_status = self.STATUS_SUSPECTED if existing_compare_path else self.STATUS_PENDING

                db.execute(
                    """
                    UPDATE decode_tasks
                    SET file_name = ?,
                        file_size = ?,
                        source_root = ?,
                        status = ?,
                        compare_decoded_path = ?,
                        is_visible = 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        file_path.name,
                        file_path.stat().st_size,
                        source_root,
                        next_status,
                        existing_compare_path,
                        existing_by_path["id"],
                    ),
                )
                existing_count += 1
                continue

            status = self.STATUS_SUSPECTED if linked_decoded_path else self.STATUS_PENDING
            if status == self.STATUS_SUSPECTED:
                suspected_count += 1
            else:
                inserted_count += 1

            db.execute(
                """
                INSERT INTO decode_tasks (
                    file_name,
                    file_path,
                    file_size,
                    source_root,
                    status,
                    compare_decoded_path,
                    is_visible
                )
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    file_path.name,
                    str(file_path),
                    file_path.stat().st_size,
                    source_root,
                    status,
                    linked_decoded_path,
                ),
            )

        logger.info(
            f"Lada解码任务导入完成: inserted={inserted_count}, suspected={suspected_count}, existing={existing_count}"
        )
        self._refresh_task_table()
        QMessageBox.information(
            self,
            "导入完成",
            (
                f"读取到 {len(files)} 个视频文件。\n"
                f"新增待解码: {inserted_count}\n"
                f"新增疑已解码: {suspected_count}\n"
                f"已在数据库中: {existing_count}"
            ),
        )

    def _clear_completed_tasks(self):
        if self._queue_running:
            QMessageBox.information(self, "提示", "正在解码时不能清除已完成任务。")
            return

        db.execute(
            """
            UPDATE decode_tasks
            SET is_visible = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE status = ?
              AND COALESCE(is_visible, 1) = 1
            """,
            (self.STATUS_DECODED,),
        )
        if hasattr(self, "_selected_task_ids"):
            self._selected_task_ids.clear()
        logger.info("Lada解码队列已隐藏所有已完成任务")
        self._refresh_task_table()

    def _clear_all_tasks(self):
        if self._queue_running:
            QMessageBox.information(self, "提示", "正在解码时不能清空列表。")
            return

        reply = QMessageBox.question(
            self,
            "确认清空",
            "清空列表只会隐藏当前队列项目，不会删除数据库档案。是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        db.execute(
            """
            UPDATE decode_tasks
            SET is_visible = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE COALESCE(is_visible, 1) = 1
            """
        )
        if hasattr(self, "_selected_task_ids"):
            self._selected_task_ids.clear()
        logger.info("Lada解码队列已隐藏当前列表中的所有任务")
        self._refresh_task_table()

    def _create_task_item_card(self, row) -> QFrame:
        if not hasattr(self, "_selected_task_ids"):
            self._selected_task_ids = set()

        status = row["status"]
        task_id = row["id"]
        is_processing = self._is_processing_task(task_id)
        display_status = "处理中" if is_processing else self.STATUS_LABELS.get(status, status)
        status_color = "#18e0b5" if is_processing else self._color_to_hex(
            self.STATUS_COLORS.get(status, QColor(183, 199, 230))
        )
        border_color = "#d8e2ef" if status != self.STATUS_SUSPECTED else "#f1c3c8"
        background = "#fbfdff" if status != self.STATUS_SUSPECTED else "#fff8f8"
        preview_decoded_path = row["compare_decoded_path"] or row["output_path"]
        can_compare_preview = bool(preview_decoded_path)

        card = QFrame()
        card.setToolTip(row["file_path"])
        card.setStyleSheet(
            f"""
            QFrame {{
                background: {background};
                border: 1px solid {border_color};
                border-radius: 12px;
            }}
            """
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        select_cb = QCheckBox()
        select_cb.setChecked(task_id in self._selected_task_ids)
        select_cb.setEnabled(not self._queue_running and not is_processing)
        select_cb.stateChanged.connect(
            lambda state, current_id=task_id: self._toggle_task_selected(current_id, bool(state))
        )
        top_row.addWidget(select_cb, 0, Qt.AlignmentFlag.AlignTop)

        if can_compare_preview:
            file_label = QPushButton(row["file_name"])
            file_label.setFlat(True)
            file_label.setCursor(Qt.CursorShape.PointingHandCursor)
            file_label.setToolTip("点击打开未解码和已解码文件的对比预览")
            file_label.setStyleSheet(
                """
                QPushButton {
                    text-align: left;
                    background: transparent;
                    border: none;
                    color: #1f4fba;
                    font-size: 13px;
                    font-weight: bold;
                    padding: 0;
                }
                QPushButton:hover {
                    color: #2563eb;
                    text-decoration: underline;
                }
                """
            )
            file_label.clicked.connect(
                lambda checked=False, source=row["file_path"], target=preview_decoded_path:
                self._open_task_compare_preview(source, target)
            )
            top_row.addWidget(file_label, 1)
        else:
            file_label = QLabel(row["file_name"])
            file_label.setStyleSheet("QLabel { color: #1f2a44; font-size: 13px; font-weight: bold; }")
            file_label.setToolTip(row["file_path"])
            top_row.addWidget(file_label, 1)

        if status == self.STATUS_SUSPECTED:
            action_btn = self._create_button("改为待解码", "#f59e0b", min_width=112, min_height=28)
            action_btn.clicked.connect(lambda checked=False, current_id=task_id: self._mark_task_pending(current_id))
            action_btn.setEnabled(not self._queue_running and not is_processing)
            top_row.addWidget(action_btn)

        remove_btn = self._create_button("移除", "#cbd5e1", min_width=74, min_height=28)
        remove_btn.clicked.connect(lambda checked=False, current_id=task_id: self._remove_single_task(current_id))
        remove_btn.setEnabled(not self._queue_running and not is_processing)
        top_row.addWidget(remove_btn)

        layout.addLayout(top_row)

        path_label = QLabel(row["file_path"])
        path_label.setWordWrap(True)
        path_label.setStyleSheet(
            """
            QLabel {
                color: #6f7f97;
                font-size: 10px;
                background: #f4f7fb;
                border: 1px solid #e4ebf4;
                border-radius: 6px;
                padding: 3px 6px;
            }
            """
        )
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path_label.setToolTip(row["file_path"])
        layout.addWidget(path_label)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)

        status_badge = QLabel(f"● {display_status}")
        status_badge.setStyleSheet(
            f"""
            QLabel {{
                color: {status_color};
                font-size: 11px;
                font-weight: bold;
                background: #ffffff;
                border: 1px solid #dee7f2;
                border-radius: 7px;
                padding: 2px 8px;
            }}
            """
        )
        bottom_row.addWidget(status_badge)

        bottom_row.addStretch()

        if row["output_path"]:
            output_label = QLabel("已生成输出")
            output_label.setToolTip(row["output_path"])
            output_label.setStyleSheet(
                """
                QLabel {
                    color: #5f718d;
                    font-size: 10px;
                    background: #eef4ff;
                    border: 1px solid #d7e3fb;
                    border-radius: 7px;
                    padding: 2px 8px;
                }
                """
            )
            bottom_row.addWidget(output_label)
        elif row["compare_decoded_path"]:
            linked_label = QLabel("已关联旧输出")
            linked_label.setToolTip(row["compare_decoded_path"])
            linked_label.setStyleSheet(
                """
                QLabel {
                    color: #8a5a00;
                    font-size: 10px;
                    background: #fff6df;
                    border: 1px solid #f3deb0;
                    border-radius: 7px;
                    padding: 2px 8px;
                }
                """
            )
            bottom_row.addWidget(linked_label)

        layout.addLayout(bottom_row)
        return card

    def _is_processing_task(self, task_id: int) -> bool:
        return (
            self._current_task_id == task_id
            and self._process.state() != QProcess.ProcessState.NotRunning
        )

    def _color_to_hex(self, color: QColor) -> str:
        return color.name()

    def _clear_completed_tasks(self):
        if self._queue_running:
            QMessageBox.information(self, "提示", "正在解码时不能清除已完成任务。")
            return

        db.execute("DELETE FROM decode_tasks WHERE status = ?", (self.STATUS_DECODED,))
        logger.info("已清除所有已完成的解码任务")
        self._refresh_task_table()

    def _clear_all_tasks(self):
        if self._queue_running:
            QMessageBox.information(self, "提示", "正在解码时不能清空任务列表。")
            return

        reply = QMessageBox.question(
            self,
            "确认清空",
            "确定要清空全部解码任务吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        db.execute("DELETE FROM decode_tasks")
        logger.info("已清空全部解码任务")
        self._refresh_task_table()

    def _start_decode_queue(self):
        if self._process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.information(self, "提示", "当前已有解码任务在运行。")
            return

        self._save_config(show_message=False)

        try:
            self._validate_global_options()
        except ValueError as exc:
            QMessageBox.warning(self, "参数不完整", str(exc))
            return

        self._queue_running = True
        self._stop_requested = False
        self.log_view.clear()
        self._append_log("开始读取待解码任务队列...")
        self._start_next_pending_task(
            empty_message="当前没有待解码任务。",
            completed_message=None,
        )

    def _stop_decode(self):
        if self._process.state() == QProcess.ProcessState.NotRunning:
            return

        self._queue_running = False
        self._stop_requested = True
        self._append_log("正在停止当前 lada-cli 任务...")
        logger.info("请求停止 lada-cli 队列")
        self._process.terminate()
        if not self._process.waitForFinished(2000):
            self._append_log("进程未及时退出，执行强制结束。")
            self._process.kill()

    def _on_process_started(self):
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        current_name = Path(self._current_task_path).name if self._current_task_path else "未知文件"
        self.status_label.setText(f"解码中: {current_name}")
        self.status_label.setStyleSheet("color: #27ae60; font-size: 12px; font-weight: bold;")
        self._refresh_task_table()

    def _on_process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus):
        if self._stop_requested:
            self._append_log('lada-cli 已停止，当前任务保持"待解码"。')
            self.status_label.setText("已停止")
            self.status_label.setStyleSheet("color: #e67e22; font-size: 12px; font-weight: bold;")
            self._reset_current_task_context()
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self._stop_requested = False
            self._refresh_task_table()
            return

        if exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0:
            self._mark_current_task_decoded()
            current_name = Path(self._current_task_path).name if self._current_task_path else "当前文件"
            self._append_log(f"解码完成: {current_name}")
            logger.info(f"lada-cli 解码完成: {current_name}")
            self._reset_current_task_context()
            self._refresh_task_table()

            if self._queue_running:
                self._start_next_pending_task(
                    empty_message=None,
                    completed_message="待解码队列已全部完成。",
                )
            return

        current_name = Path(self._current_task_path).name if self._current_task_path else "当前文件"
        self._append_log(f"解码失败: {current_name}，退出码 {exit_code}")
        logger.warning(f"lada-cli 解码失败: {current_name}, exit_code={exit_code}")
        self.status_label.setText(f"失败: {current_name}")
        self.status_label.setStyleSheet("color: #e74c3c; font-size: 12px; font-weight: bold;")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._queue_running = False
        self._reset_current_task_context()
        self._refresh_task_table()
        QMessageBox.warning(
            self,
            "解码失败",
            f'文件解码失败，任务保留为"待解码"。\n退出码: {exit_code}',
        )

    def _on_process_error(self, error: QProcess.ProcessError):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._queue_running = False

        message = self._process.errorString() or str(error)
        self._append_log(f"启动 lada-cli 失败: {message}")
        logger.error(f"启动 lada-cli 失败: {message}")
        self.status_label.setText("启动失败")
        self.status_label.setStyleSheet("color: #e74c3c; font-size: 12px; font-weight: bold;")
        self._reset_current_task_context()
        self._refresh_task_table()
        QMessageBox.warning(self, "启动失败", f"无法启动 lada-cli：\n{message}")

    def _refresh_task_table(self):
        rows = db.query(
            """
            SELECT id, file_name, file_path, status, output_path
            FROM decode_tasks
            ORDER BY
                CASE status
                    WHEN ? THEN 0
                    WHEN ? THEN 1
                    ELSE 2
                END,
                updated_at DESC,
                id DESC
            """,
            (self.STATUS_PENDING, self.STATUS_SUSPECTED),
        )

        pending_count = 0
        decoded_count = 0
        suspected_count = 0

        self._clear_task_cards()

        for row in rows:
            status = row["status"]
            if status == self.STATUS_PENDING:
                pending_count += 1
            elif status == self.STATUS_DECODED:
                decoded_count += 1
            elif status == self.STATUS_SUSPECTED:
                suspected_count += 1
            self.task_list_layout.addWidget(self._create_task_item_card(row))

        self.task_list_layout.addStretch(1)

        self.pending_count_label.setText(str(pending_count))
        self.decoded_count_label.setText(str(decoded_count))
        self.suspected_count_label.setText(str(suspected_count))
        self.task_queue_count_label.setText(f"{len(rows)} 项")
        self.clear_completed_btn.setEnabled(decoded_count > 0 and not self._queue_running)
        self.clear_all_btn.setEnabled(len(rows) > 0 and not self._queue_running)
        self._update_queue_overview(len(rows), pending_count, decoded_count)
        self._update_command_preview()

    def _mark_task_pending(self, task_id: int):
        db.execute(
            """
            UPDATE decode_tasks
            SET status = ?, output_path = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (self.STATUS_PENDING, task_id),
        )
        logger.info(f"解码任务改为待解码: {task_id}")
        self._refresh_task_table()

    def _clear_task_cards(self):
        while self.task_list_layout.count():
            item = self.task_list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _create_task_item_card(self, row) -> QFrame:
        status = row["status"]
        task_id = row["id"]
        is_processing = self._is_processing_task(task_id)
        display_status = "处理中" if is_processing else self.STATUS_LABELS.get(status, status)
        status_color = "#18e0b5" if is_processing else self._color_to_hex(
            self.STATUS_COLORS.get(status, QColor(183, 199, 230))
        )
        border_color = "#d7e0ec" if status != self.STATUS_SUSPECTED else "#f2b8bf"
        background = "#f9fbff" if status != self.STATUS_SUSPECTED else "#fff6f7"

        card = QFrame()
        card.setToolTip(row["file_path"])
        card.setStyleSheet(
            f"""
            QFrame {{
                background: {background};
                border: 1px solid {border_color};
                border-radius: 10px;
            }}
            """
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        grip = QLabel("⋮⋮")
        grip.setStyleSheet("QLabel { color: #9aa9bf; font-size: 12px; }")
        top_row.addWidget(grip)

        if status == self.STATUS_DECODED and row["output_path"]:
            file_label = QPushButton(row["file_name"])
            file_label.setFlat(True)
            file_label.setCursor(Qt.CursorShape.PointingHandCursor)
            file_label.setToolTip("点击打开未解码 / 已解码双视频对比预览")
            file_label.setStyleSheet(
                """
                QPushButton {
                    text-align: left;
                    background: transparent;
                    border: none;
                    color: #1f4fba;
                    font-size: 14px;
                    font-weight: bold;
                    padding: 0;
                }
                QPushButton:hover {
                    color: #2563eb;
                    text-decoration: underline;
                }
                """
            )
            file_label.clicked.connect(
                lambda checked=False, source=row["file_path"], target=row["output_path"]:
                self._open_task_compare_preview(source, target)
            )
            top_row.addWidget(file_label, 1)
        else:
            file_label = QLabel(row["file_name"])
            file_label.setStyleSheet("QLabel { color: #1f2a44; font-size: 14px; font-weight: bold; }")
            file_label.setToolTip(row["file_path"])
            top_row.addWidget(file_label, 1)

        if status == self.STATUS_SUSPECTED:
            action_btn = self._create_button("改成待解码", "#f59e0b", min_width=108, min_height=30)
            action_btn.clicked.connect(lambda checked=False, current_id=task_id: self._mark_task_pending(current_id))
            top_row.addWidget(action_btn)

        layout.addLayout(top_row)

        path_label = QLabel(row["file_path"])
        path_label.setWordWrap(True)
        path_label.setStyleSheet("QLabel { color: #70809a; font-size: 11px; }")
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path_label.setToolTip(row["file_path"])
        layout.addWidget(path_label)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(6)

        dot = QLabel("●")
        dot.setStyleSheet(f"QLabel {{ color: {status_color}; font-size: 11px; font-weight: bold; }}")
        bottom_row.addWidget(dot)

        status_label = QLabel(display_status)
        status_label.setStyleSheet(f"QLabel {{ color: {status_color}; font-size: 12px; font-weight: bold; }}")
        bottom_row.addWidget(status_label)

        bottom_row.addStretch()

        if row["output_path"]:
            output_label = QLabel("已生成输出")
            output_label.setToolTip(row["output_path"])
            output_label.setStyleSheet("QLabel { color: #70809a; font-size: 11px; }")
            bottom_row.addWidget(output_label)

        layout.addLayout(bottom_row)
        return card

    def _ensure_decode_tables(self):
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS decode_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL UNIQUE,
                file_size INTEGER,
                source_root TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                output_path TEXT,
                compare_decoded_path TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                decoded_at DATETIME
            )
            """
        )
        with db.get_connection() as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(decode_tasks)").fetchall()}
            if "compare_decoded_path" not in columns:
                conn.execute("ALTER TABLE decode_tasks ADD COLUMN compare_decoded_path TEXT")
                conn.commit()

        db.execute("CREATE INDEX IF NOT EXISTS idx_decode_tasks_status ON decode_tasks(status)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_decode_tasks_file_name ON decode_tasks(file_name)")

    def _detect_video_resolution(self, file_path: str) -> tuple[int, int, str]:
        """检测视频分辨率，返回 (width, height, resolution_str)"""
        try:
            import subprocess
            import json

            # 使用 ffprobe 获取视频分辨率
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_streams",
                    "-select_streams", "v:0",
                    file_path
                ],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                data = json.loads(result.stdout)
                if data.get("streams"):
                    stream = data["streams"][0]
                    width = int(stream.get("width", 0))
                    height = int(stream.get("height", 0))

                    # 格式化分辨率字符串
                    if width > 0 and height > 0:
                        resolution_str = f"{width}x{height}"
                        return width, height, resolution_str

        except Exception as e:
            logger.warning(f"检测视频分辨率失败: {file_path}, {e}")

        return 0, 0, "未知"

    def _is_low_resolution(self, height: int) -> bool:
        """判断是否为低分辨率"""
        return height > 0 and height < self.LOW_RESOLUTION_THRESHOLD

    def _refresh_task_table(self):
        rows = db.query(
            """
            SELECT id, file_name, file_path, status, output_path, compare_decoded_path
            FROM decode_tasks
            ORDER BY
                CASE status
                    WHEN ? THEN 0
                    WHEN ? THEN 1
                    ELSE 2
                END,
                updated_at DESC,
                id DESC
            """,
            (self.STATUS_PENDING, self.STATUS_SUSPECTED),
        )

        pending_count = 0
        decoded_count = 0
        suspected_count = 0

        self._clear_task_cards()

        for row in rows:
            status = row["status"]
            if status == self.STATUS_PENDING:
                pending_count += 1
            elif status == self.STATUS_DECODED:
                decoded_count += 1
            elif status == self.STATUS_SUSPECTED:
                suspected_count += 1
            self.task_list_layout.addWidget(self._create_task_item_card(row))

        self.task_list_layout.addStretch(1)

        self.pending_count_label.setText(str(pending_count))
        self.decoded_count_label.setText(str(decoded_count))
        self.suspected_count_label.setText(str(suspected_count))
        self.task_queue_count_label.setText(f"{len(rows)} 项")
        self.clear_completed_btn.setEnabled(decoded_count > 0 and not self._queue_running)
        self.clear_all_btn.setEnabled(len(rows) > 0 and not self._queue_running)
        self._update_queue_overview(len(rows), pending_count, decoded_count)
        self._update_command_preview()

    def _mark_task_pending(self, task_id: int):
        db.execute(
            """
            UPDATE decode_tasks
            SET status = ?, output_path = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (self.STATUS_PENDING, task_id),
        )
        logger.info(f"解码任务改为待解码: {task_id}")
        self._refresh_task_table()

    def _mark_current_task_decoded(self):
        if self._current_task_id is None:
            return

        db.execute(
            """
            UPDATE decode_tasks
            SET status = ?,
                output_path = ?,
                compare_decoded_path = ?,
                decoded_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                self.STATUS_DECODED,
                self._current_output_path,
                self._current_output_path,
                self._current_task_id,
            ),
        )

    def _import_from_path(self, path_str: str):
        if not path_str:
            QMessageBox.warning(self, "提示", "请先选择文件或目录。")
            return

        path = Path(path_str)
        if not path.exists():
            QMessageBox.warning(self, "提示", f"路径不存在：\n{path_str}")
            return

        files = self._collect_video_files(path)
        if not files:
            QMessageBox.warning(self, "提示", "没有找到可导入的视频文件。")
            return

        inserted_count = 0
        suspected_count = 0
        existing_count = 0

        for file_path in files:
            existing_by_path = db.query_one(
                "SELECT id FROM decode_tasks WHERE file_path = ?",
                (str(file_path),),
            )
            if existing_by_path:
                db.execute(
                    """
                    UPDATE decode_tasks
                    SET file_size = ?, source_root = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        file_path.stat().st_size,
                        str(path if path.is_dir() else file_path.parent),
                        existing_by_path["id"],
                    ),
                )
                existing_count += 1
                continue

            duplicate_name = db.query_one(
                """
                SELECT id, output_path, compare_decoded_path
                FROM decode_tasks
                WHERE file_name = ? AND file_path != ?
                ORDER BY
                    CASE
                        WHEN output_path IS NOT NULL AND output_path != '' THEN 0
                        WHEN compare_decoded_path IS NOT NULL AND compare_decoded_path != '' THEN 1
                        ELSE 2
                    END,
                    decoded_at DESC,
                    updated_at DESC,
                    id DESC
                LIMIT 1
                """,
                (file_path.name, str(file_path)),
            )

            linked_decoded_path = None
            if duplicate_name:
                linked_decoded_path = duplicate_name["output_path"] or duplicate_name["compare_decoded_path"]

            status = self.STATUS_SUSPECTED if duplicate_name else self.STATUS_PENDING
            if status == self.STATUS_SUSPECTED:
                suspected_count += 1
            else:
                inserted_count += 1

            db.execute(
                """
                INSERT INTO decode_tasks (
                    file_name,
                    file_path,
                    file_size,
                    source_root,
                    status,
                    compare_decoded_path
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    file_path.name,
                    str(file_path),
                    file_path.stat().st_size,
                    str(path if path.is_dir() else file_path.parent),
                    status,
                    linked_decoded_path,
                ),
            )

        logger.info(
            f"导入解码任务完成: inserted={inserted_count}, suspected={suspected_count}, existing={existing_count}"
        )
        self._refresh_task_table()
        QMessageBox.information(
            self,
            "导入完成",
            (
                f"读取到 {len(files)} 个视频文件。\n"
                f"新增待解码: {inserted_count}\n"
                f"新增疑已解码: {suspected_count}\n"
                f"已在数据库中: {existing_count}"
            ),
        )

    def _create_task_item_card(self, row) -> QFrame:
        status = row["status"]
        task_id = row["id"]
        is_processing = self._is_processing_task(task_id)
        display_status = "处理中" if is_processing else self.STATUS_LABELS.get(status, status)
        status_color = "#18e0b5" if is_processing else self._color_to_hex(
            self.STATUS_COLORS.get(status, QColor(183, 199, 230))
        )
        border_color = "#d8e2ef" if status != self.STATUS_SUSPECTED else "#f1c3c8"
        background = "#fbfdff" if status != self.STATUS_SUSPECTED else "#fff8f8"
        preview_decoded_path = row["compare_decoded_path"] or row["output_path"]
        can_compare_preview = bool(preview_decoded_path)

        card = QFrame()
        card.setToolTip(row["file_path"])
        card.setStyleSheet(
            f"""
            QFrame {{
                background: {background};
                border: 1px solid {border_color};
                border-radius: 12px;
            }}
            """
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        grip = QLabel("◌")
        grip.setStyleSheet("QLabel { color: #c8d3e1; font-size: 13px; font-weight: bold; }")
        top_row.addWidget(grip)

        if can_compare_preview:
            file_label = QPushButton(row["file_name"])
            file_label.setFlat(True)
            file_label.setCursor(Qt.CursorShape.PointingHandCursor)
            file_label.setToolTip("点击打开未解码 / 已解码双视频对比预览")
            file_label.setStyleSheet(
                """
                QPushButton {
                    text-align: left;
                    background: transparent;
                    border: none;
                    color: #1f4fba;
                    font-size: 13px;
                    font-weight: bold;
                    padding: 0;
                }
                QPushButton:hover {
                    color: #2563eb;
                    text-decoration: underline;
                }
                """
            )
            file_label.clicked.connect(
                lambda checked=False, source=row["file_path"], target=preview_decoded_path:
                self._open_task_compare_preview(source, target)
            )
            top_row.addWidget(file_label, 1)
        else:
            file_label = QLabel(row["file_name"])
            file_label.setStyleSheet("QLabel { color: #1f2a44; font-size: 13px; font-weight: bold; }")
            file_label.setToolTip(row["file_path"])
            top_row.addWidget(file_label, 1)

        if status == self.STATUS_SUSPECTED:
            action_btn = self._create_button("改成待解码", "#f59e0b", min_width=112, min_height=28)
            action_btn.clicked.connect(lambda checked=False, current_id=task_id: self._mark_task_pending(current_id))
            top_row.addWidget(action_btn)

        layout.addLayout(top_row)

        path_label = QLabel(row["file_path"])
        path_label.setWordWrap(True)
        path_label.setStyleSheet(
            """
            QLabel {
                color: #6f7f97;
                font-size: 10px;
                background: #f4f7fb;
                border: 1px solid #e4ebf4;
                border-radius: 6px;
                padding: 3px 6px;
            }
            """
        )
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path_label.setToolTip(row["file_path"])
        layout.addWidget(path_label)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)

        status_badge = QLabel(f"●  {display_status}")
        status_badge.setStyleSheet(
            f"""
            QLabel {{
                color: {status_color};
                font-size: 11px;
                font-weight: bold;
                background: #ffffff;
                border: 1px solid #dee7f2;
                border-radius: 7px;
                padding: 2px 8px;
            }}
            """
        )
        bottom_row.addWidget(status_badge)

        bottom_row.addStretch()

        if row["output_path"]:
            output_label = QLabel("已生成输出")
            output_label.setToolTip(row["output_path"])
            output_label.setStyleSheet(
                """
                QLabel {
                    color: #5f718d;
                    font-size: 10px;
                    background: #eef4ff;
                    border: 1px solid #d7e3fb;
                    border-radius: 7px;
                    padding: 2px 8px;
                }
                """
            )
            bottom_row.addWidget(output_label)
        elif row["compare_decoded_path"]:
            output_label = QLabel("已关联旧输出")
            output_label.setToolTip(row["compare_decoded_path"])
            output_label.setStyleSheet(
                """
                QLabel {
                    color: #8a5a1f;
                    font-size: 10px;
                    background: #fff4de;
                    border: 1px solid #f3ddb0;
                    border-radius: 7px;
                    padding: 2px 8px;
                }
                """
            )
            bottom_row.addWidget(output_label)

        layout.addLayout(bottom_row)
        return card

    def _update_queue_overview(self, total_count: int, pending_count: int, decoded_count: int):
        if hasattr(self, "queue_meta_label"):
            self.queue_meta_label.setText(f"已完成 {decoded_count} / {total_count}")

        if hasattr(self, "queue_progress_bar") and self._process.state() == QProcess.ProcessState.NotRunning:
            if total_count == 0:
                self.queue_progress_bar.setRange(0, 1)
                self.queue_progress_bar.setValue(0)
            else:
                self.queue_progress_bar.setRange(0, total_count)
                self.queue_progress_bar.setValue(decoded_count)

        if hasattr(self, "current_task_label") and not self._queue_running and self._current_task_path is None:
            if pending_count > 0:
                self.current_task_label.setText("当前任务: 等待开始")
            else:
                self.current_task_label.setText("当前任务: 队列空闲")

    def _clear_completed_tasks(self):
        if self._queue_running:
            QMessageBox.information(self, "提示", "正在解码时不能清除已完成任务。")
            return

        db.execute("DELETE FROM decode_tasks WHERE status = ?", (self.STATUS_DECODED,))
        logger.info("已清除所有已完成的解码任务")
        self._refresh_task_table()

    def _clear_all_tasks(self):
        if self._queue_running:
            QMessageBox.information(self, "提示", "正在解码时不能清空任务列表。")
            return

        reply = QMessageBox.question(
            self,
            "确认清空",
            "确定要清空全部解码任务吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        db.execute("DELETE FROM decode_tasks")
        logger.info("已清空全部解码任务")
        self._refresh_task_table()

    def _start_decode_queue(self):
        if self._process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.information(self, "提示", "当前已经有解码任务在运行。")
            return

        self._save_config(show_message=False)

        try:
            self._validate_global_options()
        except ValueError as exc:
            QMessageBox.warning(self, "参数不完整", str(exc))
            return

        self._queue_running = True
        self._stop_requested = False
        self.log_view.clear()
        self.status_label.setText("准备开始")
        self.status_label.setStyleSheet("QLabel { color: #5b4dff; font-size: 12px; font-weight: bold; padding-left: 8px; }")
        self.current_task_label.setText("当前任务: 正在读取队列")
        self._append_log("开始读取待解码任务队列...")
        self._start_next_pending_task(
            empty_message="当前没有待解码任务。",
            completed_message=None,
        )

    def _stop_decode(self):
        if self._process.state() == QProcess.ProcessState.NotRunning:
            return

        self._queue_running = False
        self._stop_requested = True
        self.status_label.setText("正在停止")
        self.status_label.setStyleSheet("QLabel { color: #f59e0b; font-size: 12px; font-weight: bold; padding-left: 8px; }")
        self._append_log("正在停止当前 lada-cli 任务...")
        logger.info("请求停止 lada-cli 队列")
        self._process.terminate()
        if not self._process.waitForFinished(2000):
            self._append_log("进程未及时退出，执行强制结束。")
            self._process.kill()

    def _on_process_started(self):
        current_name = Path(self._current_task_path).name if self._current_task_path else "未知文件"
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText(f"解码中: {current_name}")
        self.status_label.setStyleSheet("QLabel { color: #18e0b5; font-size: 12px; font-weight: bold; padding-left: 8px; }")
        self.current_task_label.setText(f"当前任务: {current_name}")
        self.queue_progress_bar.setRange(0, 0)
        self._refresh_task_table()

    def _on_process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus):
        current_name = Path(self._current_task_path).name if self._current_task_path else "当前文件"

        if self._stop_requested:
            self._append_log('lada-cli 已停止，当前任务保持为"待解码"。')
            self.status_label.setText("已停止")
            self.status_label.setStyleSheet("QLabel { color: #f59e0b; font-size: 12px; font-weight: bold; padding-left: 8px; }")
            self._reset_current_task_context()
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self._stop_requested = False
            self._refresh_task_table()
            return

        if exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0:
            self._mark_current_task_decoded()
            self._append_log(f"解码完成: {current_name}")
            logger.info(f"lada-cli 解码完成: {current_name}")
            self._reset_current_task_context()
            self._refresh_task_table()

            if self._queue_running:
                self._start_next_pending_task(
                    empty_message=None,
                    completed_message="待解码队列已经全部完成。",
                )
            return

        self._append_log(f"解码失败: {current_name}，退出码 {exit_code}")
        logger.warning(f"lada-cli 解码失败: {current_name}, exit_code={exit_code}")
        self.status_label.setText(f"失败: {current_name}")
        self.status_label.setStyleSheet("QLabel { color: #f87171; font-size: 12px; font-weight: bold; padding-left: 8px; }")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._queue_running = False
        self._reset_current_task_context()
        self._refresh_task_table()
        QMessageBox.warning(
            self,
            "解码失败",
            f'文件解码失败，任务保留为"待解码"。\n退出码: {exit_code}',
        )

    def _on_process_error(self, error: QProcess.ProcessError):
        message = self._process.errorString() or str(error)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._queue_running = False
        self._append_log(f"启动 lada-cli 失败: {message}")
        logger.error(f"启动 lada-cli 失败: {message}")
        self.status_label.setText("启动失败")
        self.status_label.setStyleSheet("QLabel { color: #f87171; font-size: 12px; font-weight: bold; padding-left: 8px; }")
        self._reset_current_task_context()
        self._refresh_task_table()
        QMessageBox.warning(self, "启动失败", f"无法启动 lada-cli：\n{message}")

    def _start_next_pending_task(self, empty_message: str | None, completed_message: str | None):
        task = self._get_next_pending_task()
        if not task:
            self._queue_running = False
            self._stop_requested = False
            self._reset_current_task_context()
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.status_label.setText("队列空闲")
            self.status_label.setStyleSheet("QLabel { color: #91a3c7; font-size: 12px; font-weight: bold; padding-left: 8px; }")
            self._refresh_task_table()
            if completed_message:
                QMessageBox.information(self, "完成", completed_message)
            elif empty_message:
                QMessageBox.information(self, "提示", empty_message)
            return

        self._current_task_id = task["id"]
        self._current_task_path = task["file_path"]
        self._current_output_path = self._guess_output_path(task["file_path"])

        current_name = Path(self._current_task_path).name
        self.current_task_label.setText(f"当前任务: {current_name}")

        command = self._build_command(task["file_path"], strict=True)
        preview = subprocess.list2cmdline(command)
        self._append_log(f"$ {preview}")
        logger.info(f"启动 lada-cli 解码任务 {task['id']}: {preview}")

        self._process.setProgram(command[0])
        self._process.setArguments(command[1:])
        self._process.start()

    def _read_stdout(self):
        data = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._append_log(data)

    def _read_stderr(self):
        data = bytes(self._process.readAllStandardError()).decode("utf-8", errors="replace")
        self._append_log(data)

    def _append_log(self, text: str):
        if not text:
            return

        normalized = text.replace("\r", "\n")
        for line in normalized.splitlines():
            if line.strip():
                self.log_view.appendPlainText(line)

    def _start_next_pending_task(self, empty_message: str | None, completed_message: str | None):
        task = self._get_next_pending_task()
        if not task:
            self._queue_running = False
            self._stop_requested = False
            self._reset_current_task_context()
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.status_label.setText("队列空闲")
            self.status_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
            self._refresh_task_table()
            if completed_message:
                QMessageBox.information(self, "完成", completed_message)
            elif empty_message:
                QMessageBox.information(self, "提示", empty_message)
            return

        self._current_task_id = task["id"]
        self._current_task_path = task["file_path"]
        self._current_output_path = self._guess_output_path(task["file_path"])

        command = self._build_command(task["file_path"], strict=True)
        preview = subprocess.list2cmdline(command)
        self._append_log(f"$ {preview}")
        logger.info(f"启动 lada-cli 解码任务 {task['id']}: {preview}")

        self._process.setProgram(command[0])
        self._process.setArguments(command[1:])
        self._process.start()

    def _get_next_pending_task(self):
        return db.query_one(
            """
            SELECT id, file_name, file_path
            FROM decode_tasks
            WHERE status = ?
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            """,
            (self.STATUS_PENDING,),
        )

    def _guess_output_path(self, input_path: str) -> str:
        output_dir = self.output_path_edit.text().strip()
        pattern = self.output_pattern_edit.text().strip() or "{orig_file_name}.restored.mp4"
        input_file = Path(input_path)
        guessed_name = pattern.replace("{orig_file_name}", input_file.stem)
        return str(Path(output_dir) / guessed_name)

    def _mark_current_task_decoded(self):
        if self._current_task_id is None:
            return

        db.execute(
            """
            UPDATE decode_tasks
            SET status = ?, output_path = ?, decoded_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (self.STATUS_DECODED, self._current_output_path, self._current_task_id),
        )

    def _reset_current_task_context(self):
        self._current_task_id = None
        self._current_task_path = None
        self._current_output_path = None

    def _import_from_manual_path(self):
        self._import_from_path(self.import_path_edit.text().strip())

    def _select_import_file(self):
        """选择待解码视频文件（支持多选）"""
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择待解码视频文件（可多选）",
            self._dialog_start_dir(self.import_path_edit.text()),
            "Video Files (*.mp4 *.mkv *.avi *.wmv *.flv *.mov *.mpeg *.mpg *.m4v *.ts *.webm);;All Files (*.*)",
        )
        if paths:
            # 显示第一个路径，但导入所有选中的文件
            self.import_path_edit.setText(paths[0])
            self._import_from_multiple_paths(paths)

    def _select_import_dir(self):
        path = QFileDialog.getExistingDirectory(
            self,
            "选择待解码目录",
            self._dialog_start_dir(self.import_path_edit.text()),
        )
        if path:
            self.import_path_edit.setText(path)
            self._import_from_path(path)

    def _select_cli_path(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 lada-cli 程序",
            self._dialog_start_dir(self.cli_path_edit.text()),
            "Executable Files (*.exe);;All Files (*.*)",
        )
        if path:
            self.cli_path_edit.setText(path)

    def _select_output_dir(self):
        path = QFileDialog.getExistingDirectory(
            self,
            "选择输出目录",
            self._dialog_start_dir(self.output_path_edit.text()),
        )
        if path:
            self.output_path_edit.setText(path)

    def _select_temp_dir(self):
        path = QFileDialog.getExistingDirectory(
            self,
            "选择缓存目录",
            self._dialog_start_dir(self.temp_dir_edit.text()),
        )
        if path:
            self.temp_dir_edit.setText(path)

    def _import_from_path(self, path_str: str):
        if not path_str:
            QMessageBox.warning(self, "提示", "请先选择文件或目录。")
            return

        path = Path(path_str)
        if not path.exists():
            QMessageBox.warning(self, "提示", f"路径不存在：\n{path_str}")
            return

        files = self._collect_video_files(path)
        if not files:
            QMessageBox.warning(self, "提示", "没有找到可导入的视频文件。")
            return

        inserted_count = 0
        suspected_count = 0
        low_resolution_count = 0
        updated_count = 0

        for file_path in files:
            # 检测视频分辨率（每次都检测）
            width, height, resolution = self._detect_video_resolution(str(file_path))
            is_low_res = self._is_low_resolution(height)

            # 确定状态：优先检查同名文件（疑已解码），其次检查低分辨率，最后是待解码
            duplicate_name = db.query_one(
                "SELECT id FROM decode_tasks WHERE file_name = ? AND file_path != ? LIMIT 1",
                (file_path.name, str(file_path)),
            )
            if duplicate_name:
                status = self.STATUS_SUSPECTED
                suspected_count += 1
            elif is_low_res:
                status = self.STATUS_LOW_RESOLUTION
                low_resolution_count += 1
            else:
                status = self.STATUS_PENDING
                inserted_count += 1

            existing_by_path = db.query_one(
                "SELECT id FROM decode_tasks WHERE file_path = ?",
                (str(file_path),),
            )
            if existing_by_path:
                # 更新已有记录（包括分辨率）
                db.execute(
                    """
                    UPDATE decode_tasks
                    SET file_size = ?, resolution = ?, width = ?, height = ?, status = ?, source_root = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        file_path.stat().st_size,
                        resolution,
                        width,
                        height,
                        status,
                        str(path if path.is_dir() else file_path.parent),
                        existing_by_path["id"],
                    ),
                )
                updated_count += 1
            else:
                # 插入新记录
                db.execute(
                    """
                    INSERT INTO decode_tasks (file_name, file_path, file_size, resolution, width, height, source_root, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        file_path.name,
                        str(file_path),
                        file_path.stat().st_size,
                        resolution,
                        width,
                        height,
                        str(path if path.is_dir() else file_path.parent),
                        status,
                    ),
                )

        logger.info(
            f"导入解码任务完成: inserted={inserted_count}, updated={updated_count}, suspected={suspected_count}, low_resolution={low_resolution_count}"
        )
        self._refresh_task_table()
        QMessageBox.information(
            self,
            "导入完成",
            (
                f"读取到 {len(files)} 个视频文件。\n"
                f"新增待解码: {inserted_count}\n"
                f"新增低分辨率: {low_resolution_count}\n"
                f"新增疑已解码: {suspected_count}\n"
                f"已更新记录: {updated_count}"
            ),
        )

    def _import_from_multiple_paths(self, paths: list[str]):
        """从多个文件路径导入"""
        if not paths:
            QMessageBox.warning(self, "提示", "没有选择任何文件。")
            return

        inserted_count = 0
        suspected_count = 0
        low_resolution_count = 0
        updated_count = 0
        skipped_count = 0
        total_files = len(paths)

        for path_str in paths:
            path = Path(path_str)
            if not path.exists() or not path.is_file():
                skipped_count += 1
                continue

            if path.suffix.lower() not in self.VIDEO_EXTENSIONS:
                skipped_count += 1
                continue

            # 检测视频分辨率（每次都检测）
            width, height, resolution = self._detect_video_resolution(str(path))
            is_low_res = self._is_low_resolution(height)

            # 确定状态：优先检查同名文件（疑已解码），其次检查低分辨率，最后是待解码
            duplicate_name = db.query_one(
                "SELECT id FROM decode_tasks WHERE file_name = ? AND file_path != ? LIMIT 1",
                (path.name, str(path)),
            )
            if duplicate_name:
                status = self.STATUS_SUSPECTED
                suspected_count += 1
            elif is_low_res:
                status = self.STATUS_LOW_RESOLUTION
                low_resolution_count += 1
            else:
                status = self.STATUS_PENDING
                inserted_count += 1

            existing_by_path = db.query_one(
                "SELECT id FROM decode_tasks WHERE file_path = ?",
                (str(path),),
            )
            if existing_by_path:
                # 更新已有记录（包括分辨率）
                db.execute(
                    """
                    UPDATE decode_tasks
                    SET file_size = ?, resolution = ?, width = ?, height = ?, status = ?, source_root = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        path.stat().st_size,
                        resolution,
                        width,
                        height,
                        status,
                        str(path.parent),
                        existing_by_path["id"],
                    ),
                )
                updated_count += 1
            else:
                # 插入新记录
                db.execute(
                    """
                    INSERT INTO decode_tasks (file_name, file_path, file_size, resolution, width, height, source_root, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        path.name,
                        str(path),
                        path.stat().st_size,
                        resolution,
                        width,
                        height,
                        str(path.parent),
                        status,
                    ),
                )

        logger.info(
            f"批量导入解码任务完成: total={total_files}, inserted={inserted_count}, updated={updated_count}, suspected={suspected_count}, low_resolution={low_resolution_count}"
        )
        self._refresh_task_table()

        detail_msg = f"共选择 {total_files} 个文件。\n"
        if inserted_count > 0:
            detail_msg += f"新增待解码: {inserted_count}\n"
        if low_resolution_count > 0:
            detail_msg += f"新增低分辨率: {low_resolution_count}\n"
        if suspected_count > 0:
            detail_msg += f"新增疑已解码: {suspected_count}\n"
        if updated_count > 0:
            detail_msg += f"已更新记录: {updated_count}\n"
        if skipped_count > 0:
            detail_msg += f"跳过: {skipped_count}\n"

        QMessageBox.information(self, "导入完成", detail_msg)

    def _collect_video_files(self, path: Path) -> list[Path]:
        if path.is_file():
            return [path] if path.suffix.lower() in self.VIDEO_EXTENSIONS else []

        files = []
        for file_path in path.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in self.VIDEO_EXTENSIONS:
                files.append(file_path)
        return sorted(files, key=lambda item: str(item).lower())

    def _validate_global_options(self):
        cli_path = self.cli_path_edit.text().strip() or "lada-cli"
        output_path = self.output_path_edit.text().strip()
        temp_dir = self.temp_dir_edit.text().strip() or tempfile.gettempdir()
        output_pattern = self.output_pattern_edit.text().strip() or "{orig_file_name}.restored.mp4"

        errors = []
        if self._resolve_cli_path(cli_path) is None:
            errors.append("找不到 lada-cli。请填写 `lada-cli` 或 `lada-cli.exe` 的完整路径。")
        if not output_path:
            errors.append("请先选择解码输出目录。")
        elif Path(output_path).suffix:
            errors.append("输出位置请填写目录，不要填写单个文件名。")
        if "{orig_file_name}" not in output_pattern or "." not in output_pattern:
            errors.append("输出模板必须包含 `{orig_file_name}` 且要带扩展名。")
        if errors:
            raise ValueError("\n".join(errors))

        try:
            Path(output_path).mkdir(parents=True, exist_ok=True)
            Path(temp_dir).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ValueError(f"无法创建输出或缓存目录：{exc}") from exc

    def _build_command(self, task_input_path: str | None, strict: bool) -> list[str]:
        cli_path = self.cli_path_edit.text().strip() or "lada-cli"
        resolved_cli_path = self._resolve_cli_path(cli_path) or cli_path
        input_path = task_input_path or self._current_task_path or self._get_next_pending_input_path()
        output_path = self.output_path_edit.text().strip()
        temp_dir = self.temp_dir_edit.text().strip() or tempfile.gettempdir()
        output_pattern = self.output_pattern_edit.text().strip() or "{orig_file_name}.restored.mp4"

        if strict:
            self._validate_global_options()
            if not input_path:
                raise ValueError("当前没有可执行的待解码任务。")
            if not Path(input_path).exists():
                raise ValueError(f"待解码文件不存在：{input_path}")

        return [
            resolved_cli_path,
            "--input",
            input_path or "<待解码任务>",
            "--output",
            output_path or "<输出目录>",
            "--temporary-directory",
            temp_dir,
            "--output-file-pattern",
            output_pattern,
            "--device",
            self.device_combo.currentText().strip(),
            "--mosaic-detection-model",
            self.detection_model_combo.currentText().strip(),
            "--mosaic-restoration-model",
            self.restoration_model_combo.currentText().strip(),
            "--max-clip-length",
            str(self.max_clip_spin.value()),
            "--encoding-preset",
            self.encoding_preset_combo.currentText().strip(),
            "--fp16" if self.fp16_cb.isChecked() else "--no-fp16",
            "--detect-face-mosaics" if self.detect_face_cb.isChecked() else "--no-detect-face-mosaics",
            "--mp4-fast-start" if self.mp4_fast_start_cb.isChecked() else "--no-mp4-fast-start",
        ]

    def _update_command_preview(self):
        self.command_preview.setPlainText(subprocess.list2cmdline(self._build_command(None, False)))

    def _apply_common_preset(self):
        self._set_combo_value(self.detection_model_combo, self.COMMON_PRESET["detection_model"])
        self._set_combo_value(self.restoration_model_combo, self.COMMON_PRESET["restoration_model"])
        self._set_combo_value(self.device_combo, self.COMMON_PRESET["device"])
        self._set_combo_value(self.encoding_preset_combo, self.COMMON_PRESET["encoding_preset"])
        self.detect_face_cb.setChecked(self.COMMON_PRESET["detect_face_mosaics"])
        self.fp16_cb.setChecked(self.COMMON_PRESET["fp16"])
        self.max_clip_spin.setValue(self.COMMON_PRESET["max_clip_length"])
        self.output_pattern_edit.setText(self.COMMON_PRESET["output_file_pattern"])
        self.mp4_fast_start_cb.setChecked(self.COMMON_PRESET["mp4_fast_start"])
        self.status_label.setText("已填入常用 Lada 参数")
        self.status_label.setStyleSheet("color: #8e44ad; font-size: 12px; font-weight: bold;")

    def _get_next_pending_input_path(self) -> str:
        row = db.query_one(
            """
            SELECT file_path
            FROM decode_tasks
            WHERE status = ?
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            """,
            (self.STATUS_PENDING,),
        )
        return row["file_path"] if row else self.import_path_edit.text().strip()

    def _dialog_start_dir(self, current_text: str) -> str:
        current_text = (current_text or "").strip()
        if not current_text:
            return str(Path.home())
        path = Path(current_text)
        if path.is_file():
            return str(path.parent)
        if path.exists():
            return str(path)
        if path.parent.exists():
            return str(path.parent)
        return str(Path.home())

    def _resolve_cli_path(self, cli_path: str) -> str | None:
        if not cli_path:
            return None
        path = Path(cli_path)
        if path.exists():
            return str(path)
        return shutil.which(cli_path)

    def _get_compare_default_path(self, path_type: str) -> str:
        try:
            row = db.query_one(
                "SELECT path FROM compare_paths WHERE type = ? AND enabled = 1 ORDER BY id LIMIT 1",
                (path_type,),
            )
        except Exception:
            return ""
        return row["path"] if row else ""

    def _set_combo_value(self, combo: QComboBox, value: str):
        index = combo.findText(value)
        if index >= 0:
            combo.setCurrentIndex(index)
        elif combo.count() > 0:
            combo.setCurrentIndex(0)

    @staticmethod
    def _create_card() -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            """
            QFrame {
                background: #ffffff;
                border: 1px solid #d9dfeb;
                border-radius: 16px;
            }
            """
        )
        return card

    @staticmethod
    def _title_style() -> str:
        return "QLabel { font-size: 15px; font-weight: bold; color: #1f2a44; padding: 2px 0px; }"

    @staticmethod
    def _muted_text_style() -> str:
        return "QLabel { color: #70809a; font-size: 11px; }"

    def _create_subsection_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(
            """
            QLabel {
                color: #31405f;
                font-size: 12px;
                font-weight: bold;
                background: #f4f6fb;
                border: 1px solid #dde4f0;
                border-radius: 10px;
                padding: 8px 12px;
            }
            """
        )
        return label

    @staticmethod
    def _input_style() -> str:
        return """
            QLineEdit, QComboBox, QSpinBox {
                border: 1px solid #d8e0ed;
                border-radius: 12px;
                padding: 9px 12px;
                background: #f8fafc;
                font-size: 13px;
                color: #1f2a44;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
                border: 1px solid #4f7cff;
                background: #ffffff;
            }
            QComboBox::drop-down {
                border: none;
                width: 28px;
            }
            QComboBox QAbstractItemView {
                background: #ffffff;
                color: #1f2a44;
                border: 1px solid #d8e0ed;
                selection-background-color: #edf3ff;
            }
        """

    def _build_form_row(self, label_text: str, field: QWidget, buttons=None, label_min_width: int = 96) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)

        label = QLabel(label_text)
        label.setMinimumWidth(label_min_width)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            """
            QLabel {
                min-height: 42px;
                color: #31405f;
                background: #f4f6fb;
                border: 1px solid #dde4f0;
                border-radius: 12px;
                padding: 0px 12px;
                font-size: 13px;
                font-weight: bold;
            }
            """
        )
        row.addWidget(label)

        if isinstance(field, (QLineEdit, QComboBox, QSpinBox, QPlainTextEdit)):
            field.setStyleSheet(self._input_style())
        if hasattr(field, "setMinimumHeight") and not isinstance(field, QPlainTextEdit):
            field.setMinimumHeight(42)
        row.addWidget(field, 1)

        for text, callback, color in buttons or []:
            button = self._create_button(text, color, min_width=76, min_height=42)
            button.clicked.connect(callback)
            row.addWidget(button)
        return row

    def _create_select_combo(self, items) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(False)
        combo.setMinimumHeight(42)
        for value, description in items:
            combo.addItem(value)
            combo.setItemData(combo.count() - 1, description, Qt.ItemDataRole.ToolTipRole)
        return combo

    @staticmethod
    def _create_checkbox(text: str) -> QCheckBox:
        checkbox = QCheckBox(text)
        checkbox.setStyleSheet(
            """
            QCheckBox {
                font-size: 12px;
                color: #1f2a44;
                spacing: 0px;
                min-width: 44px;
            }
            QCheckBox::indicator {
                width: 42px;
                height: 24px;
                border-radius: 12px;
                border: 1px solid #cad5e5;
                background: #dde5f0;
            }
            QCheckBox::indicator:checked {
                background: #4f7cff;
                border: 1px solid #4f7cff;
            }
            """
        )
        return checkbox

    @staticmethod
    def _create_button(text: str, color: str, min_width: int = 110, min_height: int = 36) -> QPushButton:
        button = QPushButton(text)
        button.setMinimumSize(min_width, min_height)
        button.setStyleSheet(
            f"""
            QPushButton {{
                background: {color};
                color: #f8fbff;
                border: 1px solid #cfd8e6;
                border-radius: 10px;
                font-size: 13px;
                font-weight: bold;
                padding: 6px 12px;
            }}
            QPushButton:hover {{
                border: 1px solid #8ba2c3;
            }}
            QPushButton:disabled {{
                background: #d9e0eb;
                color: #8a98ad;
                border: 1px solid #d0d8e5;
            }}
            """
        )
        return button

    def _format_progress_text(self, progress: float) -> str:
        progress = max(0.0, min(100.0, progress))
        rounded = round(progress, 1)
        if abs(rounded - round(rounded)) < 0.05:
            return f"{int(round(rounded))}%"
        return f"{rounded:.1f}%"

    def _reset_task_progress_ui(self, meta_text: str | None = None):
        self._current_task_progress = None
        self._process_output_buffer = ""
        if hasattr(self, "queue_progress_bar"):
            self.queue_progress_bar.setRange(0, 1000)
            self.queue_progress_bar.setValue(0)
        if meta_text is not None and hasattr(self, "queue_meta_label"):
            self.queue_meta_label.setText(meta_text)

    def _set_current_task_progress(self, progress: float):
        progress = max(0.0, min(100.0, progress))
        if self._current_task_progress is not None:
            progress = max(self._current_task_progress, progress)

        self._current_task_progress = progress

        if hasattr(self, "queue_progress_bar"):
            self.queue_progress_bar.setRange(0, 1000)
            self.queue_progress_bar.setValue(int(round(progress * 10)))

        if hasattr(self, "queue_meta_label"):
            self.queue_meta_label.setText(self._format_progress_text(progress))

    def _extract_progress_from_text(self, text: str) -> float | None:
        cleaned = (text or "").strip()
        if not cleaned:
            return None

        processed_match = re.search(r"Processed:\s*[^|]*\((\d+)f\)", cleaned, flags=re.IGNORECASE)
        remaining_match = re.search(r"Remaining:\s*[^|]*\((\d+)f\)", cleaned, flags=re.IGNORECASE)
        if processed_match and remaining_match:
            processed_frames = int(processed_match.group(1))
            remaining_frames = int(remaining_match.group(1))
            total_frames = processed_frames + remaining_frames
            if total_frames > 0 and processed_frames >= 0 and remaining_frames >= 0:
                return processed_frames * 100.0 / total_frames

        percent_matches = list(re.finditer(r"(?<!\d)(\d{1,3}(?:\.\d+)?)\s*%(?!\d)", cleaned))
        for match in reversed(percent_matches):
            value = float(match.group(1))
            if 0.0 <= value <= 100.0:
                return value

        ratio_matches = list(re.finditer(r"(?<!\d)(\d{1,7})\s*/\s*(\d{1,7})(?!\d)", cleaned))
        for match in reversed(ratio_matches):
            done = int(match.group(1))
            total = int(match.group(2))
            if total > 0 and 0 <= done <= total:
                return done * 100.0 / total

        return None

    def _update_task_progress_from_output(self, text: str):
        if not text or self._current_task_path is None:
            return

        self._process_output_buffer = (self._process_output_buffer + text)[-4000:]
        parts = re.split(r"[\r\n]+", self._process_output_buffer)

        for part in parts[-12:]:
            progress = self._extract_progress_from_text(part)
            if progress is not None:
                self._set_current_task_progress(progress)

    def _update_queue_overview(self, total_count: int, pending_count: int, decoded_count: int):
        if self._process.state() != QProcess.ProcessState.NotRunning:
            if hasattr(self, "queue_meta_label"):
                if self._current_task_progress is None:
                    self.queue_meta_label.setText("处理中")
                else:
                    self.queue_meta_label.setText(self._format_progress_text(self._current_task_progress))
            return

        if hasattr(self, "queue_meta_label"):
            self.queue_meta_label.setText(f"已完成 {decoded_count} / {total_count}")

        if hasattr(self, "queue_progress_bar"):
            self.queue_progress_bar.setRange(0, 1000)
            self.queue_progress_bar.setValue(0)

        if hasattr(self, "current_task_label") and not self._queue_running and self._current_task_path is None:
            if pending_count > 0:
                self.current_task_label.setText("当前任务: 等待开始")
            else:
                self.current_task_label.setText("当前任务: 队列空闲")

    def _on_process_started(self):
        current_name = Path(self._current_task_path).name if self._current_task_path else "未知文件"
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText(f"解码中: {current_name}")
        self.status_label.setStyleSheet(
            "QLabel { color: #18e0b5; font-size: 12px; font-weight: bold; padding-left: 8px; }"
        )
        self.current_task_label.setText(f"当前任务: {current_name}")
        self._reset_task_progress_ui("0%")
        self._refresh_task_table()

    def _on_process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus):
        current_name = Path(self._current_task_path).name if self._current_task_path else "当前文件"

        if self._stop_requested:
            self._append_log('lada-cli 已停止，当前任务保持为"待解码"。')
            self.status_label.setText("已停止")
            self.status_label.setStyleSheet(
                "QLabel { color: #f59e0b; font-size: 12px; font-weight: bold; padding-left: 8px; }"
            )
            self._reset_current_task_context()
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self._stop_requested = False
            self._refresh_task_table()
            return

        if exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0:
            self._set_current_task_progress(100.0)
            self._mark_current_task_decoded()
            self._append_log(f"解码完成: {current_name}")
            logger.info(f"lada-cli 解码完成: {current_name}")
            self._reset_current_task_context()
            self._refresh_task_table()

            if self._queue_running:
                self._start_next_pending_task(
                    empty_message=None,
                    completed_message="待解码队列已经全部完成。",
                )
            return

        self._append_log(f"解码失败: {current_name}，退出码 {exit_code}")
        logger.warning(f"lada-cli 解码失败: {current_name}, exit_code={exit_code}")
        self.status_label.setText(f"失败: {current_name}")
        self.status_label.setStyleSheet(
            "QLabel { color: #f87171; font-size: 12px; font-weight: bold; padding-left: 8px; }"
        )
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._queue_running = False
        self._reset_current_task_context()
        self._refresh_task_table()
        QMessageBox.warning(
            self,
            "解码失败",
            f'文件解码失败，任务保留为"待解码"。\n退出码: {exit_code}',
        )

    def _on_process_error(self, error: QProcess.ProcessError):
        message = self._process.errorString() or str(error)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._queue_running = False
        self._append_log(f"启动 lada-cli 失败: {message}")
        logger.error(f"启动 lada-cli 失败: {message}")
        self.status_label.setText("启动失败")
        self.status_label.setStyleSheet(
            "QLabel { color: #f87171; font-size: 12px; font-weight: bold; padding-left: 8px; }"
        )
        self._reset_current_task_context()
        self._refresh_task_table()
        QMessageBox.warning(self, "启动失败", f"无法启动 lada-cli：\n{message}")

    def _read_stdout(self):
        data = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._update_task_progress_from_output(data)
        self._append_log(data)

    def _read_stderr(self):
        data = bytes(self._process.readAllStandardError()).decode("utf-8", errors="replace")
        self._update_task_progress_from_output(data)
        self._append_log(data)

    def _append_log(self, text: str):
        if not text:
            return

        normalized = text.replace("\r", "\n")
        for line in normalized.splitlines():
            if line.strip():
                self.log_view.appendPlainText(line)

    def _start_next_pending_task(self, empty_message: str | None, completed_message: str | None):
        task = self._get_next_pending_task()
        if not task:
            self._queue_running = False
            self._stop_requested = False
            self._reset_current_task_context()
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.status_label.setText("队列空闲")
            self.status_label.setStyleSheet(
                "QLabel { color: #70809a; font-size: 12px; font-weight: bold; padding-left: 8px; }"
            )
            self._refresh_task_table()
            if completed_message:
                QMessageBox.information(self, "完成", completed_message)
            elif empty_message:
                QMessageBox.information(self, "提示", empty_message)
            return

        self._current_task_id = task["id"]
        self._current_task_path = task["file_path"]
        self._current_output_path = self._guess_output_path(task["file_path"])
        self.current_task_label.setText(f"当前任务: {Path(self._current_task_path).name}")
        self._reset_task_progress_ui("0%")

        command = self._build_command(task["file_path"], strict=True)
        preview = subprocess.list2cmdline(command)
        self._append_log(f"$ {preview}")
        logger.info(f"启动 lada-cli 解码任务 {task['id']}: {preview}")

        self._process.setProgram(command[0])
        self._process.setArguments(command[1:])
        self._process.start()

    def _reset_current_task_context(self):
        self._current_task_id = None
        self._current_task_path = None
        self._current_output_path = None
        self._current_task_progress = None
        self._process_output_buffer = ""

    def _create_task_item_card(self, row) -> QFrame:
        status = row["status"]
        task_id = row["id"]
        is_processing = self._is_processing_task(task_id)
        display_status = "处理中" if is_processing else self.STATUS_LABELS.get(status, status)
        status_color = "#18e0b5" if is_processing else self._color_to_hex(
            self.STATUS_COLORS.get(status, QColor(183, 199, 230))
        )
        border_color = "#d7e0ec" if status != self.STATUS_SUSPECTED else "#f2b8bf"
        background = "#f9fbff" if status != self.STATUS_SUSPECTED else "#fff6f7"

        card = QFrame()
        card.setToolTip(row["file_path"])
        card.setStyleSheet(
            f"""
            QFrame {{
                background: {background};
                border: 1px solid {border_color};
                border-radius: 10px;
            }}
            """
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        grip = QLabel("⋮⋮")
        grip.setStyleSheet("QLabel { color: #9aa9bf; font-size: 12px; }")
        top_row.addWidget(grip)

        if status == self.STATUS_DECODED and row["output_path"]:
            file_label = QPushButton(row["file_name"])
            file_label.setFlat(True)
            file_label.setCursor(Qt.CursorShape.PointingHandCursor)
            file_label.setToolTip("点击打开未解码 / 已解码双视频对比预览")
            file_label.setStyleSheet(
                """
                QPushButton {
                    text-align: left;
                    background: transparent;
                    border: none;
                    color: #1f4fba;
                    font-size: 14px;
                    font-weight: bold;
                    padding: 0;
                }
                QPushButton:hover {
                    color: #2563eb;
                    text-decoration: underline;
                }
                """
            )
            file_label.clicked.connect(
                lambda checked=False, source=row["file_path"], target=row["output_path"]:
                self._open_task_compare_preview(source, target)
            )
            top_row.addWidget(file_label, 1)
        else:
            file_label = QLabel(row["file_name"])
            file_label.setStyleSheet("QLabel { color: #1f2a44; font-size: 14px; font-weight: bold; }")
            file_label.setToolTip(row["file_path"])
            top_row.addWidget(file_label, 1)

        if status == self.STATUS_SUSPECTED:
            action_btn = self._create_button("改成待解码", "#f59e0b", min_width=108, min_height=30)
            action_btn.clicked.connect(lambda checked=False, current_id=task_id: self._mark_task_pending(current_id))
            top_row.addWidget(action_btn)

        layout.addLayout(top_row)

        path_label = QLabel(row["file_path"])
        path_label.setWordWrap(True)
        path_label.setStyleSheet("QLabel { color: #70809a; font-size: 11px; }")
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path_label.setToolTip(row["file_path"])
        layout.addWidget(path_label)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(6)

        dot = QLabel("●")
        dot.setStyleSheet(f"QLabel {{ color: {status_color}; font-size: 11px; font-weight: bold; }}")
        bottom_row.addWidget(dot)

        status_label = QLabel(display_status)
        status_label.setStyleSheet(f"QLabel {{ color: {status_color}; font-size: 12px; font-weight: bold; }}")
        bottom_row.addWidget(status_label)

        bottom_row.addStretch()

        if row["output_path"]:
            output_label = QLabel("已生成输出")
            output_label.setToolTip(row["output_path"])
            output_label.setStyleSheet("QLabel { color: #70809a; font-size: 11px; }")
            bottom_row.addWidget(output_label)

        layout.addLayout(bottom_row)
        return card

    def _remove_preview_window(self, window: QDialog | None):
        if window in self._preview_windows:
            self._preview_windows.remove(window)

    def _open_manual_compare(self):
        """手动选择两个视频进行对比"""
        # 选择第一个视频（左侧/未解码）
        first_file, _ = QFileDialog.getOpenFileName(
            self,
            "选择第一个视频（左侧 - 未解码/原始）",
            "",
            "视频文件 (*.mp4 *.mkv *.avi *.wmv *.flv *.mov *.mpg *.mpeg *.m4v *.ts *.webm);;所有文件 (*)"
        )
        if not first_file:
            return

        # 选择第二个视频（右侧/已解码）
        second_file, _ = QFileDialog.getOpenFileName(
            self,
            "选择第二个视频（右侧 - 已解码/对比）",
            Path(first_file).parent,
            "视频文件 (*.mp4 *.mkv *.avi *.wmv *.flv *.mov *.mpg *.mpeg *.m4v *.ts *.webm);;所有文件 (*)"
        )
        if not second_file:
            return

        # 打开双视频对比窗口
        try:
            window = DualVideoCompareWindow(first_file, second_file, self)
            window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            window.destroyed.connect(lambda *_args, current=window: self._remove_preview_window(current))
            self._preview_windows.append(window)
            window.show()
            window.raise_()
            window.activateWindow()
            logger.info(f"手动打开双视频对比: 左侧={first_file}, 右侧={second_file}")
        except Exception as exc:
            logger.error(f"打开双视频对比失败: {exc}")
            QMessageBox.warning(self, "打开失败", f"无法打开双视频对比窗口：\n{exc}")

    def _open_task_compare_preview(self, undecoded_path: str, decoded_path: str):
        try:
            undecoded_exists = Path(undecoded_path).exists()
            decoded_exists = Path(decoded_path).exists()

            if not undecoded_exists and not decoded_exists:
                QMessageBox.warning(self, "提示", "原视频和已解码视频都不存在，无法预览。")
                return
            if not undecoded_exists:
                QMessageBox.warning(self, "提示", f"未找到原视频：\n{undecoded_path}")
                return
            if not decoded_exists:
                QMessageBox.warning(self, "提示", f"未找到已解码视频：\n{decoded_path}")
                return

            window = DualVideoCompareWindow(undecoded_path, decoded_path, self)
            window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            window.destroyed.connect(lambda *_args, current=window: self._remove_preview_window(current))
            self._preview_windows.append(window)
            window.show()
            window.raise_()
            window.activateWindow()
            logger.info(f"打开解码任务双视频预览: 未解码={undecoded_path}, 已解码={decoded_path}")
        except Exception as exc:
            logger.error(f"打开解码任务双视频预览失败: {exc}")
            QMessageBox.warning(self, "预览失败", f"无法打开双视频对比预览：\n{exc}")

    def _create_task_item_card(self, row) -> QFrame:
        status = row["status"]
        task_id = row["id"]
        is_processing = self._is_processing_task(task_id)
        display_status = "处理中" if is_processing else self.STATUS_LABELS.get(status, status)
        status_color = "#18e0b5" if is_processing else self._color_to_hex(
            self.STATUS_COLORS.get(status, QColor(183, 199, 230))
        )
        border_color = "#d8e2ef" if status != self.STATUS_SUSPECTED else "#f1c3c8"
        background = "#fbfdff" if status != self.STATUS_SUSPECTED else "#fff8f8"

        card = QFrame()
        card.setToolTip(row["file_path"])
        card.setStyleSheet(
            f"""
            QFrame {{
                background: {background};
                border: 1px solid {border_color};
                border-radius: 12px;
            }}
            """
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        grip = QLabel("◌")
        grip.setStyleSheet("QLabel { color: #c8d3e1; font-size: 13px; font-weight: bold; }")
        top_row.addWidget(grip)

        if status == self.STATUS_DECODED and row["output_path"]:
            file_label = QPushButton(row["file_name"])
            file_label.setFlat(True)
            file_label.setCursor(Qt.CursorShape.PointingHandCursor)
            file_label.setToolTip("点击打开未解码 / 已解码双视频对比预览")
            file_label.setStyleSheet(
                """
                QPushButton {
                    text-align: left;
                    background: transparent;
                    border: none;
                    color: #1f4fba;
                    font-size: 13px;
                    font-weight: bold;
                    padding: 0;
                }
                QPushButton:hover {
                    color: #2563eb;
                    text-decoration: underline;
                }
                """
            )
            file_label.clicked.connect(
                lambda checked=False, source=row["file_path"], target=row["output_path"]:
                self._open_task_compare_preview(source, target)
            )
            top_row.addWidget(file_label, 1)
        else:
            file_label = QLabel(row["file_name"])
            file_label.setStyleSheet("QLabel { color: #1f2a44; font-size: 13px; font-weight: bold; }")
            file_label.setToolTip(row["file_path"])
            top_row.addWidget(file_label, 1)

        if status == self.STATUS_SUSPECTED:
            action_btn = self._create_button("改成待解码", "#f59e0b", min_width=112, min_height=28)
            action_btn.clicked.connect(lambda checked=False, current_id=task_id: self._mark_task_pending(current_id))
            top_row.addWidget(action_btn)

        layout.addLayout(top_row)

        path_label = QLabel(row["file_path"])
        path_label.setWordWrap(True)
        path_label.setStyleSheet(
            """
            QLabel {
                color: #6f7f97;
                font-size: 10px;
                background: #f4f7fb;
                border: 1px solid #e4ebf4;
                border-radius: 6px;
                padding: 3px 6px;
            }
            """
        )
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path_label.setToolTip(row["file_path"])
        layout.addWidget(path_label)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)

        status_badge = QLabel(f"●  {display_status}")
        status_badge.setStyleSheet(
            f"""
            QLabel {{
                color: {status_color};
                font-size: 11px;
                font-weight: bold;
                background: #ffffff;
                border: 1px solid #dee7f2;
                border-radius: 7px;
                padding: 2px 8px;
            }}
            """
        )
        bottom_row.addWidget(status_badge)

        bottom_row.addStretch()

        if row["output_path"]:
            output_label = QLabel("已生成输出")
            output_label.setToolTip(row["output_path"])
            output_label.setStyleSheet(
                """
                QLabel {
                    color: #5f718d;
                    font-size: 10px;
                    background: #eef4ff;
                    border: 1px solid #d7e3fb;
                    border-radius: 7px;
                    padding: 2px 8px;
                }
                """
            )
            bottom_row.addWidget(output_label)

        layout.addLayout(bottom_row)
        return card
