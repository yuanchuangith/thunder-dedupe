#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
文件列表模块 - SQLite存储、模糊查询
"""
import threading
from pathlib import Path
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtCore import QObject, pyqtSignal, Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame
)

from db.database import db
from utils.logger import logger
from utils.utils import format_file_size


class FileListPage(QWidget):
    """文件列表页面"""

    # 支持的视频文件扩展名
    VIDEO_EXTENSIONS = {
        '.mp4', '.mkv', '.avi', '.wmv', '.flv', '.mov',
        '.mpg', '.mpeg', '.m4v', '.rm', '.rmvb', '.ts', '.m2ts'
    }

    def __init__(self):
        super().__init__()
        self._scanning = False
        self._scan_count = 0
        self._setup_ui()

        # 搜索防抖定时器
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._do_search)

        # 初始加载
        QTimer.singleShot(500, self._initial_load)

    def _setup_ui(self):
        """设置界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 搜索栏
        search_frame = self._create_search_frame()
        layout.addWidget(search_frame)

        # 文件表格
        self.file_table = self._create_file_table()
        layout.addWidget(self.file_table)

        # 状态栏
        self.status_label = QLabel("文件数量: 0")
        self.status_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        layout.addWidget(self.status_label)

    def _create_search_frame(self) -> QFrame:
        """创建搜索栏"""
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

        # 搜索输入框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入关键词搜索文件名...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px 12px;
                background: #fff;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #3498db;
            }
        """)
        self.search_input.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.search_input, 1)

        # 扫描按钮
        self.scan_btn = QPushButton("扫描目录")
        self.scan_btn.setFixedHeight(36)
        self.scan_btn.setToolTip("扫描配置的目录，更新文件列表")
        self.scan_btn.setStyleSheet("""
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
        self.scan_btn.clicked.connect(self._start_scan)
        layout.addWidget(self.scan_btn)

        # 清空按钮
        clear_btn = QPushButton("清空搜索")
        clear_btn.setFixedHeight(36)
        clear_btn.setToolTip("清空搜索框，显示全部文件")
        clear_btn.setStyleSheet("""
            QPushButton {
                background: #7f8c8d;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background: #95a5a6;
            }
        """)
        clear_btn.clicked.connect(self._clear_search)
        layout.addWidget(clear_btn)

        return frame

    def _create_file_table(self) -> QTableWidget:
        """创建文件表格"""
        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["文件名", "大小", "路径"])

        table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #dee2e6;
                background: #fff;
                gridline-color: #dee2e6;
            }
            QTableWidget::item {
                padding: 6px;
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
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        table.setColumnWidth(1, 100)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)

        return table

    def _init_table(self):
        """初始化文件列表表"""
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
        # 创建索引加速搜索
        db.execute("CREATE INDEX IF NOT EXISTS idx_file_list_name ON file_list(name)")

    def _initial_load(self):
        """初始加载"""
        self._init_table()

        # 检查 file_index 表是否有数据（主页扫描的结果）
        index_count = db.query_one("SELECT COUNT(*) as count FROM file_index")

        if index_count and index_count['count'] > 0:
            # 有索引数据，同步到文件列表表
            self._sync_from_index()

        self._refresh_table()

    def _sync_from_index(self):
        """从 file_index 表同步数据到 file_list 表"""
        # 清空 file_list
        db.execute("DELETE FROM file_list")

        # 从 file_index 复制数据
        db.execute("""
            INSERT INTO file_list (name, path, size, ext)
            SELECT original_name, file_path, file_size, '.mp4'
            FROM file_index
        """)

        count = db.query_one("SELECT COUNT(*) as count FROM file_list")
        logger.info(f"从索引同步 {count['count']} 个文件到文件列表")

    def _start_scan(self):
        """开始扫描"""
        if self._scanning:
            return

        self._scanning = True
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("扫描中...")
        self.status_label.setText("正在扫描...")

        self._scan_count = 0

        thread = threading.Thread(target=self._scan_worker, daemon=True)
        thread.start()

        # 定时检查扫描状态
        self._check_scan_timer = QTimer()
        self._check_scan_timer.timeout.connect(self._check_scan_status)
        self._check_scan_timer.start(500)

    def _scan_worker(self):
        """扫描工作线程"""
        try:
            # 获取配置的扫描路径
            paths = db.query("SELECT path FROM scan_paths WHERE enabled = 1")

            # 删除旧数据
            db.execute("DELETE FROM file_list")

            total_files = 0

            for row in paths:
                path = row['path']
                logger.info(f"扫描目录: {path}")

                try:
                    p = Path(path)
                    if not p.exists():
                        continue

                    # 批量插入
                    batch = []
                    for file_path in p.rglob('*'):
                        if file_path.is_file():
                            ext = file_path.suffix.lower()
                            if ext in self.VIDEO_EXTENSIONS:
                                batch.append((
                                    file_path.name,
                                    str(file_path),
                                    file_path.stat().st_size,
                                    ext
                                ))

                                # 每500个文件批量插入一次
                                if len(batch) >= 500:
                                    self._insert_batch(batch)
                                    total_files += len(batch)
                                    batch = []

                    # 插入剩余的
                    if batch:
                        self._insert_batch(batch)
                        total_files += len(batch)

                except Exception as e:
                    logger.warning(f"扫描目录出错 {path}: {e}")

            logger.info(f"文件列表扫描完成，共 {total_files} 个文件")
            self._scan_count = total_files

        except Exception as e:
            logger.error(f"扫描出错: {e}")

        self._scanning = False

    def _insert_batch(self, batch: List):
        """批量插入文件"""
        with db.get_connection() as conn:
            conn.executemany(
                "INSERT INTO file_list (name, path, size, ext) VALUES (?, ?, ?, ?)",
                batch
            )
            conn.commit()

    def _check_scan_status(self):
        """检查扫描状态"""
        if not self._scanning:
            self._check_scan_timer.stop()
            self._on_scan_completed(self._scan_count)

    def _on_scan_completed(self, count: int):
        """扫描完成"""
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("扫描目录")
        self.status_label.setText(f"文件数量: {count}")
        self._refresh_table()

    def _on_search_changed(self, text: str):
        """搜索内容变化"""
        self._search_timer.start(300)

    def _do_search(self):
        """执行搜索"""
        self._refresh_table()

    def _clear_search(self):
        """清空搜索"""
        self.search_input.clear()
        self._refresh_table()

    def _refresh_table(self):
        """刷新表格"""
        keyword = self.search_input.text().strip()

        if keyword:
            # 模糊搜索
            rows = db.query("""
                SELECT name, path, size FROM file_list
                WHERE name LIKE ?
                ORDER BY name
                LIMIT 500
            """, (f"%{keyword}%",))
        else:
            # 显示全部
            rows = db.query("""
                SELECT name, path, size FROM file_list
                ORDER BY name
                LIMIT 500
            """)

        self.file_table.setRowCount(len(rows))

        for i, row in enumerate(rows):
            # 文件名
            name_item = QTableWidgetItem(row['name'])
            self.file_table.setItem(i, 0, name_item)

            # 大小
            size_item = QTableWidgetItem(format_file_size(row['size'] or 0))
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.file_table.setItem(i, 1, size_item)

            # 路径
            path_item = QTableWidgetItem(row['path'])
            path_item.setToolTip(row['path'])
            self.file_table.setItem(i, 2, path_item)

        # 更新状态
        count_row = db.query_one("SELECT COUNT(*) as count FROM file_list")
        total_count = count_row['count'] if count_row else 0

        if keyword:
            self.status_label.setText(f"搜索结果: {len(rows)} 条 (共 {total_count} 个文件)")
        else:
            self.status_label.setText(f"文件数量: {total_count}")

    def refresh(self):
        """公开的刷新方法，供外部调用"""
        self._refresh_table()