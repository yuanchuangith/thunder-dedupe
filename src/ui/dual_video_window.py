#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
双视频对比窗口 - 左右两个嵌入式播放器同时播放对比
"""
import os
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QAction, QMouseEvent, QShortcut, QKeySequence
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QFrame, QSplitter, QWidget,
    QMessageBox, QApplication, QStyle, QStyleOptionSlider
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

from utils.logger import logger

try:
    from send2trash import send2trash
    HAS_SEND2TRASH = True
except ImportError:
    HAS_SEND2TRASH = False


class ClickSeekSlider(QSlider):
    """支持点击轨道直接跳转到目标位置的进度条。"""

    seekRequested = pyqtSignal(int)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        if self._handle_rect().contains(event.position().toPoint()):
            super().mousePressEvent(event)
            return

        point = event.position().toPoint()
        value = self._value_from_position(point)
        self.setValue(value)
        self.seekRequested.emit(value)
        event.accept()

    def _handle_rect(self):
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        return self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            option,
            QStyle.SubControl.SC_SliderHandle,
            self,
        )

    def _value_from_position(self, point) -> int:
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        if self.orientation() == Qt.Orientation.Horizontal:
            position = point.x()
            span = self.width()
        else:
            position = point.y()
            span = self.height()
        return QStyle.sliderValueFromPosition(
            self.minimum(),
            self.maximum(),
            position,
            max(1, span),
            option.upsideDown,
        )


class VideoPlayerWidget(QWidget):
    """单个视频播放器组件"""

    SEEK_STEP_MS = 3000

    def __init__(
        self,
        title: str,
        color: str,
        parent=None,
        file_path: Optional[str] = None,
        can_delete: bool = False,
        delete_callback=None,
        show_header: bool = True,
    ):
        super().__init__(parent)
        self._title = title
        self._color = color
        self._file_path: Optional[str] = file_path
        self._can_delete = can_delete
        self._delete_callback = delete_callback
        self._show_header = show_header
        self._sync_player: Optional['VideoPlayerWidget'] = None  # 同步播放器
        self._setup_ui()
        self._setup_player()

    def set_sync_player(self, player: 'VideoPlayerWidget'):
        """设置同步播放器"""
        self._sync_player = player

    def _setup_ui(self):
        """设置界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 标题栏
        title_frame = QFrame()
        title_frame.setStyleSheet(f"""
            QFrame {{
                background: {self._color};
                border-radius: 6px;
            }}
        """)
        title_layout = QHBoxLayout(title_frame)
        title_layout.setContentsMargins(10, 5, 10, 5)
        self.title_frame = title_frame

        title_label = QLabel(self._title)
        title_label.setStyleSheet("color: white; font-size: 14px; font-weight: bold;")
        title_layout.addWidget(title_label)

        self.file_name_label = QLabel("未加载文件")
        self.file_name_label.setStyleSheet("color: white; font-size: 12px;")
        title_layout.addWidget(self.file_name_label, 1)

        # 删除按钮（如果允许删除）
        if self._can_delete and self._show_header:
            self.delete_btn = QPushButton("删除文件")
            self.delete_btn.setFixedHeight(28)
            self.delete_btn.setStyleSheet("""
                QPushButton {
                    background: #c0392b;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-size: 11px;
                    padding: 4px 10px;
                }
                QPushButton:hover { background: #a93226; }
            """)
            self.delete_btn.clicked.connect(self._on_delete_clicked)
            title_layout.addWidget(self.delete_btn)

        layout.addWidget(title_frame)
        if not self._show_header:
            title_frame.hide()

        # 视频显示区域
        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(300)
        self.video_widget.setStyleSheet("""
            QVideoWidget {
                background: #2c3e50;
                border: 2px solid #34495e;
                border-radius: 8px;
            }
        """)
        layout.addWidget(self.video_widget, 1)

        # 控制区域
        control_frame = QFrame()
        control_frame.setStyleSheet("""
            QFrame {
                background: #34495e;
                border-radius: 6px;
            }
        """)
        control_layout = QHBoxLayout(control_frame)
        control_layout.setContentsMargins(10, 8, 10, 8)
        control_layout.setSpacing(8)

        # 播放/暂停按钮
        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedSize(40, 40)
        self.play_btn.setStyleSheet("""
            QPushButton {
                background: #27ae60;
                color: white;
                border: none;
                border-radius: 20px;
                font-size: 16px;
            }
            QPushButton:hover { background: #2ecc71; }
            QPushButton:pressed { background: #1e8449; }
        """)
        self.play_btn.clicked.connect(self._toggle_play)
        control_layout.addWidget(self.play_btn)

        # 停止按钮
        self.stop_btn = QPushButton("⬛")
        self.stop_btn.setFixedSize(40, 40)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background: #e74c3c;
                color: white;
                border: none;
                border-radius: 20px;
                font-size: 16px;
            }
            QPushButton:hover { background: #c0392b; }
            QPushButton:pressed { background: #922b21; }
        """)
        self.stop_btn.clicked.connect(self._stop)
        control_layout.addWidget(self.stop_btn)

        # 快退 3 秒按钮
        self.seek_back_btn = QPushButton("-3s")
        self.seek_back_btn.setFixedSize(52, 32)
        self.seek_back_btn.setAutoRepeat(True)
        self.seek_back_btn.setAutoRepeatDelay(320)
        self.seek_back_btn.setAutoRepeatInterval(120)
        self.seek_back_btn.setStyleSheet("""
            QPushButton {
                background: #5d6d7e;
                color: white;
                border: none;
                border-radius: 16px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover { background: #6c7a89; }
            QPushButton:pressed { background: #4b5968; }
        """)
        self.seek_back_btn.setToolTip("后退 3 秒，按住可连续后退")
        self.seek_back_btn.clicked.connect(lambda: self.seek_by(-self.SEEK_STEP_MS))
        control_layout.addWidget(self.seek_back_btn)

        # 快进 3 秒按钮
        self.seek_forward_btn = QPushButton("+3s")
        self.seek_forward_btn.setFixedSize(52, 32)
        self.seek_forward_btn.setAutoRepeat(True)
        self.seek_forward_btn.setAutoRepeatDelay(320)
        self.seek_forward_btn.setAutoRepeatInterval(120)
        self.seek_forward_btn.setStyleSheet("""
            QPushButton {
                background: #5d6d7e;
                color: white;
                border: none;
                border-radius: 16px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover { background: #6c7a89; }
            QPushButton:pressed { background: #4b5968; }
        """)
        self.seek_forward_btn.setToolTip("前进 3 秒，按住可连续前进")
        self.seek_forward_btn.clicked.connect(lambda: self.seek_by(self.SEEK_STEP_MS))
        control_layout.addWidget(self.seek_forward_btn)

        # 进度条
        self.progress_slider = ClickSeekSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setRange(0, 0)
        self.progress_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #7f8c8d;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #3498db;
                width: 16px;
                margin: -4px 0;
                border-radius: 8px;
            }
            QSlider::sub-page:horizontal {
                background: #3498db;
                border-radius: 4px;
            }
        """)
        self.progress_slider.sliderMoved.connect(self._seek)
        self.progress_slider.seekRequested.connect(self._seek)
        control_layout.addWidget(self.progress_slider, 1)

        # 时间显示
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("color: white; font-size: 12px;")
        control_layout.addWidget(self.time_label)

        # 音量控制
        volume_label = QLabel("🔊")
        volume_label.setStyleSheet("color: white; font-size: 14px;")
        control_layout.addWidget(volume_label)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(0)  # 默认静音
        self.volume_slider.setFixedWidth(80)
        self.volume_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #7f8c8d;
                height: 6px;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #f39c12;
                width: 12px;
                margin: -3px 0;
                border-radius: 6px;
            }
        """)
        self.volume_slider.valueChanged.connect(self._set_volume)
        control_layout.addWidget(self.volume_slider)

        layout.addWidget(control_frame)

        # 状态提示
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #bdc3c7; font-size: 11px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

    def _setup_player(self):
        """设置播放器"""
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setVideoOutput(self.video_widget)
        self.player.setAudioOutput(self.audio_output)

        # 设置初始音量为静音
        self.audio_output.setVolume(0.0)

        # 连接信号
        self.player.positionChanged.connect(self._update_position)
        self.player.durationChanged.connect(self._update_duration)
        self.player.playbackStateChanged.connect(self._update_state)
        self.player.errorOccurred.connect(self._handle_error)

    def load_file(self, file_path: str) -> bool:
        """加载文件"""
        if not file_path or not Path(file_path).exists():
            self.status_label.setText("文件不存在")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
            return False

        self._file_path = file_path
        file_name = Path(file_path).name

        # 如果文件名太长，截断显示
        if len(file_name) > 40:
            display_name = file_name[:37] + "..."
        else:
            display_name = file_name

        self.file_name_label.setText(display_name)
        self.file_name_label.setToolTip(file_name)

        # 加载媒体
        media_source = QUrl.fromLocalFile(file_path)
        self.player.setSource(media_source)

        self.status_label.setText("已加载，点击播放")
        self.status_label.setStyleSheet("color: #27ae60; font-size: 11px;")

        logger.info(f"[{self._title}] 加载文件: {file_path}")
        return True

    def _toggle_play(self):
        """切换播放/暂停"""
        state = self.player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _stop(self):
        """停止播放"""
        self.player.stop()
        self.progress_slider.setValue(0)

    def seek_by(self, delta_ms: int):
        """按指定毫秒数快进或快退。"""
        duration = self.player.duration()
        if duration <= 0:
            return

        current_position = self.player.position()
        target_position = max(0, min(duration, current_position + delta_ms))
        if target_position != current_position:
            self._seek(target_position)

    def _seek(self, position: int):
        """跳转到指定位置 - 同时同步另一个播放器"""
        self.player.setPosition(position)
        # 同步另一个播放器
        if self._sync_player:
            # 计算同步位置（基于比例）
            my_duration = self.player.duration()
            other_duration = self._sync_player.player.duration()
            if my_duration > 0 and other_duration > 0:
                # 按比例计算另一个播放器的位置
                ratio = position / my_duration
                sync_position = int(ratio * other_duration)
                self._sync_player.player.setPosition(sync_position)
                # 更新另一个播放器的进度条
                if not self._sync_player.progress_slider.isSliderDown():
                    self._sync_player.progress_slider.setValue(sync_position)

    def _set_volume(self, value: int):
        """设置音量"""
        self.audio_output.setVolume(value / 100.0)

    def _update_position(self, position: int):
        """更新播放位置"""
        if not self.progress_slider.isSliderDown():
            self.progress_slider.setValue(position)

        # 更新时间显示
        duration = self.player.duration()
        current_time = self._format_time(position)
        total_time = self._format_time(duration)
        self.time_label.setText(f"{current_time} / {total_time}")

    def _update_duration(self, duration: int):
        """更新总时长"""
        self.progress_slider.setRange(0, duration)

    def _update_state(self, state: QMediaPlayer.PlaybackState):
        """更新播放状态"""
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_btn.setText("⏸")
            self.play_btn.setStyleSheet("""
                QPushButton {
                    background: #f39c12;
                    color: white;
                    border: none;
                    border-radius: 20px;
                    font-size: 16px;
                }
                QPushButton:hover { background: #e67e22; }
            """)
            self.status_label.setText("播放中...")
            self.status_label.setStyleSheet("color: #3498db; font-size: 11px;")
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.play_btn.setText("▶")
            self.play_btn.setStyleSheet("""
                QPushButton {
                    background: #27ae60;
                    color: white;
                    border: none;
                    border-radius: 20px;
                    font-size: 16px;
                }
                QPushButton:hover { background: #2ecc71; }
            """)
            self.status_label.setText("已暂停")
            self.status_label.setStyleSheet("color: #f39c12; font-size: 11px;")
        else:  # StoppedState
            self.play_btn.setText("▶")
            self.play_btn.setStyleSheet("""
                QPushButton {
                    background: #27ae60;
                    color: white;
                    border: none;
                    border-radius: 20px;
                    font-size: 16px;
                }
                QPushButton:hover { background: #2ecc71; }
            """)
            self.status_label.setText("已停止")
            self.status_label.setStyleSheet("color: #bdc3c7; font-size: 11px;")

    def _handle_error(self, error: QMediaPlayer.Error, error_string: str):
        """处理播放错误"""
        if error != QMediaPlayer.Error.NoError:
            logger.error(f"[{self._title}] 播放错误: {error_string}")
            self.status_label.setText(f"播放错误: {error_string}")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")

    def _format_time(self, ms: int) -> str:
        """格式化时间"""
        seconds = ms // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    def play(self):
        """开始播放"""
        self.player.play()

    def pause(self):
        """暂停播放"""
        self.player.pause()

    def stop(self):
        """停止播放"""
        self.player.stop()

    def is_playing(self) -> bool:
        """是否正在播放"""
        return self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def cleanup(self):
        """清理资源"""
        self.player.stop()
        self.player.setSource(QUrl())

    def _on_delete_clicked(self):
        """删除按钮点击"""
        if self._delete_callback and self._file_path:
            self._delete_callback(self._file_path)

    def get_file_path(self) -> Optional[str]:
        """获取当前文件路径"""
        return self._file_path


class DualVideoCompareWindow(QDialog):
    """双视频对比窗口 - 全屏展示两个播放器"""

    def __init__(
        self,
        undecoded_path: str,
        decoded_path: str,
        parent=None,
        delete_callback=None,
        compare_mode: bool = True,
        similarity_score: Optional[float] = None,
        judgment_text: str = "",
        judgment_color: str = "#3498db",
        result_status: str = "pending",
    ):
        super().__init__(parent)
        self._undecoded_path = undecoded_path
        self._decoded_path = decoded_path
        self._delete_callback = delete_callback
        self._parent = parent
        self._compare_mode = compare_mode
        self._similarity_score = similarity_score
        self._judgment_text = judgment_text
        self._judgment_color = judgment_color
        self._result_status = result_status
        self._seek_shortcut_step_ms = VideoPlayerWidget.SEEK_STEP_MS

        self.setWindowTitle("视频对比播放")
        self.setMinimumSize(1200, 700)
        if not self._compare_mode:
            self.setWindowTitle("双视频播放")

        # 设置窗口样式
        self.setStyleSheet("""
            QDialog {
                background: #1a252f;
            }
        """)

        self._setup_ui()
        self._setup_shortcuts()
        self._load_files()

        # 尝试最大化窗口并自动播放
        QTimer.singleShot(100, self._maximize_window)
        QTimer.singleShot(300, self._auto_play)

    @staticmethod
    def _get_result_status_display(result_status: str) -> tuple[str, str]:
        if result_status == "confirmed_duplicate":
            return "已标记重复", "#c0392b"
        if result_status == "kept":
            return "已确认保留", "#27ae60"
        return "待人工确认", "#7f8c8d"

    def _get_recommendation_text(self) -> str:
        if self._result_status == "confirmed_duplicate":
            return "这对视频已经人工标记为重复，建议同步预览后删除不需要的版本。"
        if self._similarity_score is None:
            return "建议同步播放关键片段，确认是否为同源素材或重复版本。"
        if self._similarity_score >= 95:
            return "分数极高，通常是重复视频或仅存在轻微封装差异。"
        if self._similarity_score >= 85:
            return "内容高度接近，建议重点核对字幕、水印、裁剪和片头片尾。"
        return "分数已达到筛选阈值，但仍建议以人工复核为准。"

    def _maximize_window(self):
        """最大化窗口"""
        # 获取屏幕尺寸，设置窗口为屏幕的90%
        screen = QApplication.primaryScreen().availableGeometry()
        width = int(screen.width() * 0.9)
        height = int(screen.height() * 0.9)
        self.resize(width, height)

        # 居中显示
        x = (screen.width() - width) // 2
        y = (screen.height() - height) // 2
        self.move(x, y)

    def _setup_ui(self):
        """设置界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # 顶部标题栏
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: #2c3e50;
                border-radius: 8px;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(20, 10, 20, 10)

        title_label = QLabel("🎬 双视频对比播放 - 左侧未解码 vs 右侧已解码")
        title_label.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        header_layout.addWidget(title_label, 1)
        if not self._compare_mode:
            title_label.setText("双视频播放")

        # 同时播放按钮
        sync_play_btn = QPushButton("⏯ 同时播放")
        sync_play_btn.setFixedHeight(35)
        sync_play_btn.setStyleSheet("""
            QPushButton {
                background: #27ae60;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover { background: #2ecc71; }
        """)
        sync_play_btn.clicked.connect(self._sync_play)
        header_layout.addWidget(sync_play_btn)

        # 同时暂停按钮
        sync_pause_btn = QPushButton("⏸ 同时暂停")
        sync_pause_btn.setFixedHeight(35)
        sync_pause_btn.setStyleSheet("""
            QPushButton {
                background: #f39c12;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover { background: #e67e22; }
        """)
        sync_pause_btn.clicked.connect(self._sync_pause)
        header_layout.addWidget(sync_pause_btn)

        # 同时停止按钮
        sync_stop_btn = QPushButton("⬛ 同时停止")
        sync_stop_btn.setFixedHeight(35)
        sync_stop_btn.setStyleSheet("""
            QPushButton {
                background: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover { background: #c0392b; }
        """)
        sync_stop_btn.clicked.connect(self._sync_stop)
        header_layout.addWidget(sync_stop_btn)

        # 关闭按钮
        close_btn = QPushButton("✕ 关闭")
        close_btn.setFixedHeight(35)
        close_btn.setStyleSheet("""
            QPushButton {
                background: #7f8c8d;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover { background: #95a5a6; }
        """)
        close_btn.clicked.connect(self.close)
        header_layout.addWidget(close_btn)

        layout.addWidget(header_frame)

        if self._similarity_score is not None or self._judgment_text:
            status_text, status_color = self._get_result_status_display(self._result_status)

            summary_frame = QFrame()
            summary_frame.setStyleSheet("""
                QFrame {
                    background: #24323d;
                    border: 1px solid #3d566e;
                    border-radius: 8px;
                }
                QLabel {
                    color: white;
                }
            """)
            summary_layout = QVBoxLayout(summary_frame)
            summary_layout.setContentsMargins(16, 12, 16, 12)
            summary_layout.setSpacing(10)

            badge_row = QHBoxLayout()
            badge_row.setSpacing(8)

            score_label = QLabel(
                f"准确率 {self._similarity_score:.1f}%"
                if self._similarity_score is not None else "准确率 --"
            )
            score_label.setStyleSheet(
                "background: #1f618d; color: white; border-radius: 12px; "
                "padding: 4px 12px; font-weight: bold;"
            )
            badge_row.addWidget(score_label)

            judgment_label = QLabel(self._judgment_text or "待确认")
            judgment_label.setStyleSheet(
                f"background: {self._judgment_color}; color: white; border-radius: 12px; "
                "padding: 4px 12px; font-weight: bold;"
            )
            badge_row.addWidget(judgment_label)

            status_label = QLabel(status_text)
            status_label.setStyleSheet(
                f"background: {status_color}; color: white; border-radius: 12px; "
                "padding: 4px 12px; font-weight: bold;"
            )
            badge_row.addWidget(status_label)
            badge_row.addStretch()
            summary_layout.addLayout(badge_row)

            recommendation_label = QLabel(self._get_recommendation_text())
            recommendation_label.setWordWrap(True)
            recommendation_label.setStyleSheet("color: #d5d8dc; font-size: 12px;")
            summary_layout.addWidget(recommendation_label)

            layout.addWidget(summary_frame)

        # 视频播放区域 - 使用分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background: #3498db;
                width: 4px;
            }
        """)
        """

        # 左侧播放器（未解码）- 允许删除
        left_title = "未解码" if self._compare_mode else "候选视频 A"
        right_title = "已解码" if self._compare_mode else "候选视频 B"

        self.left_player = VideoPlayerWidget(
            "未解码", "#e74c3c",
            can_delete=True,
            delete_callback=self._delete_undecoded_file
        )
        splitter.addWidget(self.left_player)

        # 右侧播放器（已解码）- 不允许删除
        self.right_player = VideoPlayerWidget("已解码", "#27ae60")
        splitter.addWidget(self.right_player)
        if not self._compare_mode:
            self.left_player.title_frame.hide()
            self.right_player.title_frame.hide()

        # 设置进度条同步 - 互相同步
        """
        left_title = "Source" if self._compare_mode else "Video A"
        right_title = "Target" if self._compare_mode else "Video B"

        self.left_player = VideoPlayerWidget(
            left_title, "#e74c3c",
            can_delete=True,
            delete_callback=self._delete_undecoded_file
        )
        splitter.addWidget(self.left_player)

        self.right_player = VideoPlayerWidget(right_title, "#27ae60")
        splitter.addWidget(self.right_player)

        self.left_player.set_sync_player(self.right_player)
        self.right_player.set_sync_player(self.left_player)

        # 设置分割比例 50:50
        splitter.setSizes([splitter.width() // 2, splitter.width() // 2])

        layout.addWidget(splitter, 1)

        # 底部提示
        tip_frame = QFrame()
        tip_frame.setStyleSheet("""
            QFrame {
                background: #34495e;
                border-radius: 6px;
            }
        """)
        tip_layout = QHBoxLayout(tip_frame)
        tip_layout.setContentsMargins(15, 8, 15, 8)

        tip_label = QLabel(
            "提示: 拖动任意一个进度条会同步另一个播放器到相同比例位置。"
            "可使用各自的播放控制按钮独立控制，或使用顶部按钮同时控制。"
            "控制条里的 -3s / +3s 按钮点击一次跳 3 秒，按住可连续跳转；"
            "左右方向键也可按 3 秒步进。"
        )
        tip_label.setStyleSheet("color: #bdc3c7; font-size: 12px;")
        tip_layout.addWidget(tip_label, 1)

        # 全屏按钮
        fullscreen_btn = QPushButton("🖥 全屏")
        fullscreen_btn.setFixedSize(80, 30)
        fullscreen_btn.setStyleSheet("""
            QPushButton {
                background: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background: #2980b9; }
        """)
        fullscreen_btn.clicked.connect(self._toggle_fullscreen)
        tip_layout.addWidget(fullscreen_btn)

        layout.addWidget(tip_frame)

    def _load_files(self):
        """加载视频文件"""
        undecoded_loaded = self.left_player.load_file(self._undecoded_path)
        decoded_loaded = self.right_player.load_file(self._decoded_path)

        if not undecoded_loaded and not decoded_loaded:
            QMessageBox.warning(self, "加载失败", "两个文件都不存在，无法播放")
            QTimer.singleShot(100, self.close)
        elif not undecoded_loaded:
            QMessageBox.warning(
                self, "提示",
                f"未解码文件不存在:\n{self._undecoded_path}\n\n将只播放已解码文件"
            )
        elif not decoded_loaded:
            QMessageBox.warning(
                self, "提示",
                f"已解码文件不存在:\n{self._decoded_path}\n\n将只播放未解码文件"
            )

    def _setup_shortcuts(self):
        """注册窗口级快捷键。"""
        self.seek_backward_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Left), self)
        self.seek_backward_shortcut.setAutoRepeat(True)
        self.seek_backward_shortcut.activated.connect(
            lambda: self._sync_seek_by(-self._seek_shortcut_step_ms)
        )

        self.seek_forward_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Right), self)
        self.seek_forward_shortcut.setAutoRepeat(True)
        self.seek_forward_shortcut.activated.connect(
            lambda: self._sync_seek_by(self._seek_shortcut_step_ms)
        )

    def _sync_seek_by(self, delta_ms: int):
        """同步快进或快退两个播放器。"""
        primary_player = self.left_player
        if primary_player.player.duration() <= 0 and self.right_player.player.duration() > 0:
            primary_player = self.right_player

        primary_player.seek_by(delta_ms)

    def _sync_play(self):
        """同时播放"""
        self.left_player.play()
        self.right_player.play()
        logger.info("同时播放两个视频")

    def _sync_pause(self):
        """同时暂停"""
        self.left_player.pause()
        self.right_player.pause()
        logger.info("同时暂停两个视频")

    def _sync_stop(self):
        """同时停止"""
        self.left_player.stop()
        self.right_player.stop()
        logger.info("同时停止两个视频")

    def _auto_play(self):
        """自动播放"""
        self._sync_play()
        logger.info("自动开始播放两个视频")

    def _delete_undecoded_file(self, file_path: str):
        """删除未解码文件"""
        if not file_path:
            return

        delete_action = "移入回收站" if HAS_SEND2TRASH else "永久删除"

        # 二次确认
        msg = (
            f"⚠️ 确认将该文件{delete_action}？\n\n"
            f"文件: {Path(file_path).name}\n\n"
            "请确认当前选择的是需要移除的版本。"
        )
        reply = QMessageBox.warning(
            self,
            "删除确认",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                # 停止播放
                self.left_player.stop()

                # 删除文件
                path = Path(file_path)
                if path.exists():
                    if HAS_SEND2TRASH:
                        send2trash(str(path))
                    else:
                        path.unlink()
                    logger.info(f"已处理未解码文件: {file_path}")

                    # 关闭窗口
                    QMessageBox.information(self, "处理成功", f"文件已{delete_action}:\n{Path(file_path).name}")
                    self.close()

                    # 如果有父窗口的删除回调，调用它
                    if self._delete_callback:
                        self._delete_callback(file_path)
                else:
                    QMessageBox.warning(self, "删除失败", "文件不存在")

            except Exception as e:
                logger.error(f"删除文件失败: {e}")
                QMessageBox.warning(self, "删除失败", f"删除文件时出错:\n{str(e)}")

    def _toggle_fullscreen(self):
        """切换全屏"""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def closeEvent(self, event):
        """关闭事件 - 清理资源"""
        self.left_player.cleanup()
        self.right_player.cleanup()
        logger.info("双视频对比窗口已关闭")
        event.accept()

    def keyPressEvent(self, event):
        """按键事件"""
        # ESC 键退出全屏或关闭窗口
        if event.key() == Qt.Key.Key_Escape:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.close()
        # 空格键同时播放/暂停
        elif event.key() == Qt.Key.Key_Space:
            if self.left_player.is_playing() or self.right_player.is_playing():
                self._sync_pause()
            else:
                self._sync_play()
        else:
            super().keyPressEvent(event)
