#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
主页 - 拦截状态和日志展示（完整版）
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QMessageBox, QProgressBar
)
from PyQt6.QtCore import Qt, QTimer, QDateTime, pyqtSignal

from utils.config import config
from db.database import db
from db.models import InterceptLog
from core.directory_scanner import scanner
from core.index_manager import index_manager
from core.clipboard_monitor import clipboard_monitor
from network.websocket_server import ws_server
from ui.dialogs.decision_popup import show_decision_popup
from utils.logger import logger


class HomePage(QWidget):
    """主页"""

    # 自动扫描间隔（毫秒）：10分钟
    AUTO_SCAN_INTERVAL = 10 * 60 * 1000

    # 扫描完成信号
    scan_completed_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._auto_scan_silent = False  # 静默扫描标志
        self._setup_ui()
        self._load_logs()
        self._update_stats()

        # 定时刷新日志
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._load_logs)
        self.refresh_timer.start(2000)

        # 自动扫描定时器（每10分钟）
        self.auto_scan_timer = QTimer()
        self.auto_scan_timer.timeout.connect(self._auto_scan)

        # 连接扫描器信号
        scanner.scan_started.connect(self._on_scan_started)
        scanner.scan_progress.connect(self._on_scan_progress)
        scanner.scan_completed.connect(self._on_scan_completed)
        scanner.scan_error.connect(self._on_scan_error)

        # 连接剪贴板监听器信号
        clipboard_monitor.link_detected.connect(self._on_link_detected)

        # 连接WebSocket服务器信号
        ws_server.client_connected.connect(self._on_ws_client_connected)
        ws_server.client_disconnected.connect(self._on_ws_client_disconnected)
        ws_server.intercept_request.connect(self._on_browser_intercept_request)
        ws_server.server_started.connect(self._on_ws_server_started)
        ws_server.server_error.connect(self._on_ws_server_error)

        # 延迟启动自动扫描（等待UI加载完成）
        QTimer.singleShot(2000, self._startup_scan)

    def _setup_ui(self):
        """设置界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # 状态栏
        status_frame = self._create_status_frame()
        layout.addWidget(status_frame)

        # 统计信息栏
        stats_frame = self._create_stats_frame()
        layout.addWidget(stats_frame)

        # 操作栏
        action_frame = self._create_action_frame()
        layout.addWidget(action_frame)

        # 日志标题
        log_title = QLabel("拦截日志")
        log_title.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #2c3e50;
            }
        """)
        layout.addWidget(log_title)

        # 日志表格
        self.log_table = self._create_log_table()
        layout.addWidget(self.log_table)

    def _create_status_frame(self) -> QFrame:
        """创建状态栏"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                padding: 10px;
            }
        """)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(15, 10, 15, 10)

        # 状态图标
        status_icon = QLabel("🔍")
        status_icon.setStyleSheet("font-size: 20px;")
        layout.addWidget(status_icon)

        # 状态文字
        self.status_label = QLabel("拦截状态：已开启")
        self.status_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                color: #2c3e50;
            }
        """)
        layout.addWidget(self.status_label)

        layout.addStretch()

        # 监听状态
        self.monitor_status = QLabel("监听：未启动")
        self.monitor_status.setStyleSheet("""
            QLabel {
                font-size: 12px;
                color: #7f8c8d;
            }
        """)
        layout.addWidget(self.monitor_status)

        layout.addStretch()

        # WebSocket状态
        self.ws_status = QLabel("WS服务：未启动")
        self.ws_status.setStyleSheet("""
            QLabel {
                font-size: 12px;
                color: #7f8c8d;
            }
        """)
        layout.addWidget(self.ws_status)

        # 开关按钮
        self.toggle_button = QPushButton("关闭拦截")
        self.toggle_button.setFixedHeight(32)
        self.toggle_button.setToolTip("开启/关闭拦截功能\n关闭后复制链接不会弹窗提示")
        self.toggle_button.setStyleSheet("""
            QPushButton {
                background: #27ae60;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #2ecc71;
            }
        """)
        self.toggle_button.clicked.connect(self._toggle_intercept)
        layout.addWidget(self.toggle_button)

        # 根据当前状态设置按钮
        if config.intercept_enabled:
            self.toggle_button.setText("关闭拦截")
            self.status_label.setText("拦截状态：已开启")
        else:
            self.toggle_button.setText("开启拦截")
            self.toggle_button.setStyleSheet("""
                QPushButton {
                    background: #7f8c8d;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background: #95a5a6;
                }
            """)
            self.status_label.setText("拦截状态：已关闭")

        return frame

    def _create_stats_frame(self) -> QFrame:
        """创建统计信息栏"""
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

        # 文件数量
        self.files_label = QLabel("索引文件: 0")
        self.files_label.setStyleSheet("color: #2c3e50;")
        layout.addWidget(self.files_label)

        layout.addStretch()

        # 番号数量
        self.codes_label = QLabel("番号数量: 0")
        self.codes_label.setStyleSheet("color: #2c3e50;")
        layout.addWidget(self.codes_label)

        layout.addStretch()

        # 扫描进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(150)
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

        return frame

    def _create_action_frame(self) -> QFrame:
        """创建操作栏"""
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

        # 启动监听按钮
        self.start_monitor_btn = QPushButton("启动监听")
        self.start_monitor_btn.setFixedHeight(32)
        self.start_monitor_btn.setToolTip("开启后监听剪贴板\n复制磁力链接/迅雷链接时自动检测番号\n启动时会自动扫描目录")
        self.start_monitor_btn.setStyleSheet("""
            QPushButton {
                background: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background: #2980b9;
            }
        """)
        self.start_monitor_btn.clicked.connect(self._toggle_monitor)
        layout.addWidget(self.start_monitor_btn)

        # WebSocket服务按钮
        self.ws_btn = QPushButton("启动WS服务")
        self.ws_btn.setFixedHeight(32)
        self.ws_btn.setToolTip("启动WebSocket服务器\n用于浏览器扩展与桌面应用通信\n如果不用浏览器扩展可以不启动")
        self.ws_btn.setStyleSheet("""
            QPushButton {
                background: #9b59b6;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background: #8e44ad;
            }
        """)
        self.ws_btn.clicked.connect(self._toggle_ws_server)
        layout.addWidget(self.ws_btn)

        # 扫描按钮
        scan_btn = QPushButton("扫描目录")
        scan_btn.setFixedHeight(32)
        scan_btn.setToolTip("扫描配置的目录\n建立番号索引\n用于检测是否已下载")
        scan_btn.setStyleSheet("""
            QPushButton {
                background: #27ae60;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background: #2ecc71;
            }
        """)
        scan_btn.clicked.connect(self._start_scan)
        layout.addWidget(scan_btn)

        # 清理无效按钮
        cleanup_btn = QPushButton("清理无效索引")
        cleanup_btn.setFixedHeight(32)
        cleanup_btn.setToolTip("清理已删除文件的索引记录\n保持索引与实际文件一致")
        cleanup_btn.setStyleSheet("""
            QPushButton {
                background: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background: #c0392b;
            }
        """)
        cleanup_btn.clicked.connect(self._cleanup_invalid)
        layout.addWidget(cleanup_btn)

        layout.addStretch()

        return frame

    def _create_log_table(self) -> QTableWidget:
        """创建日志表格"""
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["时间", "番号", "状态", "来源", "操作"])

        table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #dee2e6;
                background: #fff;
                gridline-color: #dee2e6;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QHeaderView::section {
                background: #f8f9fa;
                border: 1px solid #dee2e6;
                padding: 8px;
                font-weight: bold;
                color: #2c3e50;
            }
        """)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)

        table.setColumnWidth(0, 100)
        table.setColumnWidth(2, 100)
        table.setColumnWidth(3, 100)
        table.setColumnWidth(4, 100)

        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)

        return table

    def _toggle_intercept(self):
        """切换拦截状态"""
        config.intercept_enabled = not config.intercept_enabled

        if config.intercept_enabled:
            self.toggle_button.setText("关闭拦截")
            self.toggle_button.setStyleSheet("""
                QPushButton {
                    background: #27ae60;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background: #2ecc71;
                }
            """)
            self.status_label.setText("拦截状态：已开启")
        else:
            self.toggle_button.setText("开启拦截")
            self.toggle_button.setStyleSheet("""
                QPushButton {
                    background: #7f8c8d;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background: #95a5a6;
                }
            """)
            self.status_label.setText("拦截状态：已关闭")

    def _toggle_monitor(self):
        """切换监听状态"""
        if clipboard_monitor.is_running():
            clipboard_monitor.stop()
            self.start_monitor_btn.setText("启动监听")
            self.start_monitor_btn.setStyleSheet("""
                QPushButton {
                    background: #3498db;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                }
                QPushButton:hover {
                    background: #2980b9;
                }
            """)
            self.monitor_status.setText("监听：已停止")
            self.monitor_status.setStyleSheet("color: #7f8c8d;")

            # 停止自动扫描
            self.auto_scan_timer.stop()
        else:
            clipboard_monitor.start()
            self.start_monitor_btn.setText("停止监听")
            self.start_monitor_btn.setStyleSheet("""
                QPushButton {
                    background: #9b59b6;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                }
                QPushButton:hover {
                    background: #8e44ad;
                }
            """)
            self.monitor_status.setText("监听：运行中")
            self.monitor_status.setStyleSheet("color: #27ae60;")

            # 启动监听时扫描一次
            self._auto_scan_silent = True
            self._start_scan_internal()

            # 启动定时自动扫描
            self.auto_scan_timer.start(self.AUTO_SCAN_INTERVAL)
            logger.info("已启动定时自动扫描（每10分钟）")

    def _start_scan(self):
        """手动开始扫描"""
        if scanner.is_scanning():
            QMessageBox.warning(self, "警告", "已有扫描任务在进行中")
            return

        self._auto_scan_silent = False
        self._start_scan_internal()

    def _start_scan_internal(self):
        """内部扫描方法"""
        # 检查是否有配置的扫描路径
        paths = db.query("SELECT path FROM scan_paths WHERE enabled = 1")
        if not paths:
            if not self._auto_scan_silent:
                QMessageBox.warning(self, "警告", "请先在配置页添加扫描目录")
            return

        scanner.scan_all_paths()

    def _startup_scan(self):
        """启动时自动扫描"""
        logger.info("启动时自动扫描")
        self._auto_scan_silent = True
        self._start_scan_internal()

    def _auto_scan(self):
        """定时自动扫描"""
        logger.info("定时自动扫描")
        self._auto_scan_silent = True
        self._start_scan_internal()

    def _cleanup_invalid(self):
        """清理无效索引"""
        count = index_manager.cleanup_invalid()
        QMessageBox.information(self, "完成", f"清理了 {count} 条无效索引")
        self._update_stats()

    def _on_scan_started(self):
        """扫描开始"""
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

    def _on_scan_progress(self, processed: int, total: int, current_file: str):
        """扫描进度"""
        self.progress_bar.setValue(int(processed / total * 100))
        self.files_label.setText(f"扫描中: {processed}/{total}")

    def _on_scan_completed(self, new_count: int, total_count: int):
        """扫描完成"""
        self.progress_bar.setVisible(False)
        self._update_stats()

        # 同步数据到文件列表表
        self._sync_to_file_list()

        # 只在非静默模式时显示提示
        if not self._auto_scan_silent:
            QMessageBox.information(
                self,
                "扫描完成",
                f"新增 {new_count} 条索引，总计 {total_count} 条"
            )

        self._auto_scan_silent = False
        logger.info(f"扫描完成: 新增={new_count}, 总计={total_count}")

        # 发送扫描完成信号
        self.scan_completed_signal.emit()

    def _sync_to_file_list(self):
        """同步file_index到file_list表"""
        try:
            # 初始化file_list表
            db.execute("""
                CREATE TABLE IF NOT EXISTS file_list (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL,
                    size INTEGER DEFAULT 0,
                    ext TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS idx_file_list_name ON file_list(name)")

            # 清空并重新插入
            db.execute("DELETE FROM file_list")

            db.execute("""
                INSERT INTO file_list (name, path, size, ext)
                SELECT original_name, file_path, file_size, '.mp4'
                FROM file_index
            """)

            count = db.query_one("SELECT COUNT(*) as count FROM file_list")
            logger.info(f"已同步 {count['count']} 条记录到文件列表")

        except Exception as e:
            logger.error(f"同步文件列表失败: {e}")

    def _on_scan_error(self, error_msg: str):
        """扫描错误"""
        self.progress_bar.setVisible(False)
        self._auto_scan_silent = False
        QMessageBox.warning(self, "扫描错误", error_msg)

    def _on_link_detected(self, link_content: str, av_code: str):
        """检测到下载链接"""
        logger.info(f"处理检测到的链接: {av_code}")

        # 显示决策弹窗
        result = show_decision_popup(
            parent=self,
            link_content=link_content,
            av_code=av_code,
            source="clipboard"
        )

        # 刷新日志
        self._load_logs()

    def _on_browser_intercept_request(self, data: dict):
        """Handle browser-origin intercept requests before Thunder reads the real link."""
        if not config.intercept_enabled:
            return

        link_content = data.get("link_content", "")
        if not link_content:
            return

        av_code = data.get("av_code", "")
        source = data.get("source", "chrome")
        logger.info(f"Received browser intercept request: source={source}, av_code={av_code}")
        clipboard_monitor.stage_link(link_content, av_code)

        result = show_decision_popup(
            parent=self,
            link_content=link_content,
            av_code=av_code,
            source=source
        )

        ws_server.send_to_all({
            "type": "intercept_decision",
            "data": {
                "action": result,
                "av_code": av_code or None,
                "source": source
            }
        })

        self._load_logs()

    def _update_stats(self):
        """更新统计信息"""
        stats = index_manager.get_stats()
        self.files_label.setText(f"索引文件: {stats['total_files']}")
        self.codes_label.setText(f"番号数量: {stats['unique_codes']}")

    def _load_logs(self):
        """加载拦截日志"""
        rows = db.query("""
            SELECT id, av_code, source, status, user_action, created_at
            FROM intercept_logs
            ORDER BY created_at DESC
            LIMIT 50
        """)

        self.log_table.setRowCount(len(rows))

        for i, row in enumerate(rows):
            # 时间
            time_str = row['created_at']
            if time_str:
                try:
                    dt = QDateTime.fromString(time_str, Qt.DateFormat.ISODate)
                    time_display = dt.toString("HH:mm")
                except:
                    time_display = time_str[:5] if len(time_str) >= 5 else time_str
            else:
                time_display = ""
            self.log_table.setItem(i, 0, QTableWidgetItem(time_display))

            # 番号
            self.log_table.setItem(i, 1, QTableWidgetItem(row['av_code'] or ""))

            # 状态
            status = row['status'] or ""
            status_item = QTableWidgetItem(status)
            if status == "found":
                status_item.setText("已存在")
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            elif status == "not_found":
                status_item.setText("未下载")
                status_item.setForeground(Qt.GlobalColor.darkBlue)
            self.log_table.setItem(i, 2, status_item)

            # 来源
            source = row['source'] or ""
            source_map = {
                "clipboard": "剪贴板",
                "chrome": "Chrome",
                "edge": "Edge"
            }
            self.log_table.setItem(i, 3, QTableWidgetItem(source_map.get(source, source)))

            # 操作
            action = row['user_action'] or ""
            action_map = {
                "allow": "放行",
                "block": "拦截",
                "ignore": "忽略"
            }
            self.log_table.setItem(i, 4, QTableWidgetItem(action_map.get(action, action)))

        for i in range(len(rows)):
            self.log_table.setRowHeight(i, 35)

    def _toggle_ws_server(self):
        """切换WebSocket服务器"""
        if ws_server.is_running():
            ws_server.stop()
            self.ws_btn.setText("启动WS服务")
            self.ws_btn.setStyleSheet("""
                QPushButton {
                    background: #9b59b6;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                }
                QPushButton:hover {
                    background: #8e44ad;
                }
            """)
            self.ws_status.setText("WS服务：已停止")
            self.ws_status.setStyleSheet("color: #7f8c8d;")
        else:
            # 启动前重新加载端口配置
            ws_server.reload_port()
            ws_server.start()
            self.ws_btn.setText("停止WS服务")
            self.ws_btn.setStyleSheet("""
                QPushButton {
                    background: #16a085;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                }
                QPushButton:hover {
                    background: #1abc9c;
                }
            """)

    def _on_ws_client_connected(self):
        """WebSocket客户端连接"""
        self.ws_status.setText(f"WS服务：运行中 ({ws_server.client_count()}个客户端)")
        self.ws_status.setStyleSheet("color: #27ae60;")
        logger.info("浏览器扩展已连接")

    def _on_ws_client_disconnected(self):
        """WebSocket客户端断开"""
        self.ws_status.setText(f"WS服务：运行中 ({ws_server.client_count()}个客户端)")

    def _on_ws_server_started(self, port: int):
        """WebSocket服务器启动"""
        self.ws_status.setText(f"WS服务：端口{port}")
        self.ws_status.setStyleSheet("color: #27ae60;")

    def _on_ws_server_error(self, error_msg: str):
        """WebSocket服务器错误"""
        self.ws_status.setText("WS服务：错误")
        self.ws_status.setStyleSheet("color: #e74c3c;")
        QMessageBox.warning(self, "WebSocket错误", error_msg)
