#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
文件历史页 - 增量扫描、状态追踪、番号分组显示
"""
import os
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QLineEdit, QComboBox,
    QMessageBox, QProgressBar, QDialog
)

from db.database import db
from core.file_history_scanner import file_history_scanner
from utils.logger import logger
from utils.utils import format_file_size


class FileDetailDialog(QDialog):
    """番号详情弹窗 - 显示该番号的所有文件，支持删除操作"""

    def __init__(self, parent, av_code: str):
        super().__init__(parent)
        self._av_code = av_code
        self._parent_page = parent
        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        self.setWindowTitle(f"番号: {self._av_code}")
        self.setMinimumSize(800, 450)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # 标题行
        title_layout = QHBoxLayout()
        title = QLabel(f"番号: {self._av_code}")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50;")
        title_layout.addWidget(title)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        # 文件表格
        self.file_table = QTableWidget()
        self.file_table.setColumnCount(6)
        self.file_table.setHorizontalHeaderLabels(["文件名", "大小", "状态", "路径", "磁盘", "操作"])

        self.file_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #dee2e6;
                background: #fff;
                gridline-color: #dee2e6;
            }
            QHeaderView::section {
                background: #f8f9fa;
                border: 1px solid #dee2e6;
                padding: 6px;
                font-weight: bold;
            }
        """)

        header = self.file_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)

        self.file_table.setColumnWidth(1, 90)
        self.file_table.setColumnWidth(2, 70)
        self.file_table.setColumnWidth(4, 60)
        self.file_table.setColumnWidth(5, 100)
        self.file_table.verticalHeader().setVisible(False)

        layout.addWidget(self.file_table)

        # 按钮行
        btn_layout = QHBoxLayout()

        # 批量删除按钮
        self.batch_delete_btn = QPushButton("删除选中记录")
        self.batch_delete_btn.setFixedHeight(36)
        self.batch_delete_btn.setStyleSheet("""
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
        self.batch_delete_btn.clicked.connect(self._batch_delete_records)
        btn_layout.addWidget(self.batch_delete_btn)

        # 刷新按钮
        refresh_btn = QPushButton("刷新")
        refresh_btn.setFixedHeight(36)
        refresh_btn.setStyleSheet("""
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
        refresh_btn.clicked.connect(self._load_data)
        btn_layout.addWidget(refresh_btn)

        btn_layout.addStretch()

        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.setFixedHeight(36)
        close_btn.setStyleSheet("""
            QPushButton {
                background: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
            }
            QPushButton:hover {
                background: #2980b9;
            }
        """)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _load_data(self):
        """加载该番号的所有文件"""
        rows = db.query("""
            SELECT id, filename, file_size, status, file_path
            FROM file_history
            WHERE av_code = ?
            ORDER BY status = 'normal' DESC, file_size DESC
        """, (self._av_code,))

        self.file_table.setRowCount(len(rows))

        for i, row in enumerate(rows):
            is_deleted = row['status'] == 'deleted'
            file_path = row['file_path']
            file_exists = os.path.exists(file_path) if file_path else False
            record_id = row['id']

            # 文件名
            name_item = QTableWidgetItem(row['filename'])
            if is_deleted:
                name_item.setForeground(Qt.GlobalColor.gray)
            self.file_table.setItem(i, 0, name_item)

            # 大小
            size_item = QTableWidgetItem(format_file_size(row['file_size'] or 0))
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.file_table.setItem(i, 1, size_item)

            # 状态
            status_item = QTableWidgetItem("已删除" if is_deleted else "正常")
            status_item.setForeground(Qt.GlobalColor.red if is_deleted else Qt.GlobalColor.darkGreen)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.file_table.setItem(i, 2, status_item)

            # 路径
            path_item = QTableWidgetItem(file_path)
            path_item.setToolTip(file_path)
            if is_deleted or not file_exists:
                path_item.setForeground(Qt.GlobalColor.gray)
            self.file_table.setItem(i, 3, path_item)

            # 磁盘状态
            disk_item = QTableWidgetItem("存在" if file_exists else "不存在")
            disk_item.setForeground(Qt.GlobalColor.darkGreen if file_exists else Qt.GlobalColor.red)
            disk_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.file_table.setItem(i, 4, disk_item)

            # 操作按钮
            op_widget = QWidget()
            op_layout = QHBoxLayout(op_widget)
            op_layout.setContentsMargins(4, 2, 4, 2)
            op_layout.setSpacing(4)

            # 删除记录按钮
            del_record_btn = QPushButton("删记录")
            del_record_btn.setFixedSize(50, 26)
            del_record_btn.setStyleSheet("""
                QPushButton {
                    background: #e74c3c;
                    color: white;
                    border: none;
                    border-radius: 3px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background: #c0392b;
                }
            """)
            del_record_btn.clicked.connect(lambda checked, rid=record_id: self._delete_record(rid))
            op_layout.addWidget(del_record_btn)

            # 删除文件按钮（如果文件存在）
            if file_exists:
                del_file_btn = QPushButton("删文件")
                del_file_btn.setFixedSize(50, 26)
                del_file_btn.setStyleSheet("""
                    QPushButton {
                        background: #c0392b;
                        color: white;
                        border: none;
                        border-radius: 3px;
                        font-size: 11px;
                    }
                    QPushButton:hover {
                        background: #922b21;
                    }
                """)
                del_file_btn.clicked.connect(lambda checked, fp=file_path, rid=record_id: self._delete_file(fp, rid))
                op_layout.addWidget(del_file_btn)

            self.file_table.setCellWidget(i, 5, op_widget)

            # 存储记录ID到行
            name_item.setData(Qt.ItemDataRole.UserRole, record_id)

        for i in range(len(rows)):
            self.file_table.setRowHeight(i, 32)

    def _delete_record(self, record_id: int):
        """标记记录为已删除（不真正删除）- 需要两次确认"""
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 第一次确认
        reply1 = QMessageBox.question(
            self, "确认删除",
            "确定要将该记录标记为已删除吗？\n此操作不会删除磁盘上的文件，只是标记状态。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply1 != QMessageBox.StandardButton.Yes:
            return

        # 第二次确认
        reply2 = QMessageBox.warning(
            self, "再次确认",
            "请再次确认是否要将该记录标记为已删除？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply2 == QMessageBox.StandardButton.Yes:
            db.execute("""
                UPDATE file_history SET status = 'deleted', deleted_at = ? WHERE id = ?
            """, (now, record_id))
            from core.index_manager import index_manager
            index_manager.refresh_search_index()
            logger.info(f"已标记记录为删除: id={record_id}")
            self._load_data()
            self._parent_page.refresh()

    def _delete_file(self, file_path: str, record_id: int):
        """删除磁盘文件并标记记录为已删除 - 需要两次确认"""
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 第一次确认
        reply1 = QMessageBox.question(
            self, "确认删除文件",
            f"确定要删除磁盘上的文件吗？\n\n{file_path}\n\n此操作不可撤销！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply1 != QMessageBox.StandardButton.Yes:
            return

        # 第二次确认
        reply2 = QMessageBox.warning(
            self, "危险操作",
            f"即将删除文件，此操作不可撤销！\n\n{file_path}\n\n确定要继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply2 == QMessageBox.StandardButton.Yes:
            try:
                # 删除文件
                os.remove(file_path)
                logger.info(f"已删除文件: {file_path}")

                # 标记记录为已删除
                db.execute("""
                    UPDATE file_history SET status = 'deleted', deleted_at = ? WHERE id = ?
                """, (now, record_id))
                from core.index_manager import index_manager
                index_manager.refresh_search_index()

                QMessageBox.information(self, "成功", "文件已删除")
                self._load_data()
                self._parent_page.refresh()

            except Exception as e:
                QMessageBox.warning(self, "删除失败", f"删除文件失败:\n{str(e)}")
                logger.error(f"删除文件失败: {e}")

    def _batch_delete_records(self):
        """批量标记选中的记录为已删除 - 需要两次确认"""
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        selected_rows = set()
        for item in self.file_table.selectedItems():
            selected_rows.add(item.row())

        if not selected_rows:
            QMessageBox.warning(self, "提示", "请先选择要删除的记录")
            return

        # 第一次确认
        reply1 = QMessageBox.question(
            self, "确认批量删除",
            f"确定要将选中的 {len(selected_rows)} 条记录标记为已删除吗？\n此操作不会删除磁盘上的文件。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply1 != QMessageBox.StandardButton.Yes:
            return

        # 第二次确认
        reply2 = QMessageBox.warning(
            self, "再次确认",
            f"请再次确认是否要将选中的 {len(selected_rows)} 条记录标记为已删除？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply2 == QMessageBox.StandardButton.Yes:
            for row in selected_rows:
                name_item = self.file_table.item(row, 0)
                if name_item:
                    record_id = name_item.data(Qt.ItemDataRole.UserRole)
                    db.execute("""
                        UPDATE file_history SET status = 'deleted', deleted_at = ? WHERE id = ?
                    """, (now, record_id))

            from core.index_manager import index_manager
            index_manager.refresh_search_index()
            logger.info(f"已批量标记 {len(selected_rows)} 条记录为删除")
            self._load_data()
            self._parent_page.refresh()


class FileHistoryPage(QWidget):
    """文件历史页面 - 按番号分组显示"""

    def __init__(self):
        super().__init__()
        self._setup_ui()
        self._init_table()
        self._connect_signals()
        self._load_data()

    def _setup_ui(self):
        """设置界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 操作栏
        action_frame = self._create_action_frame()
        layout.addWidget(action_frame)

        # 筛选栏
        filter_frame = self._create_filter_frame()
        layout.addWidget(filter_frame)

        # 统计栏
        stats_frame = self._create_stats_frame()
        layout.addWidget(stats_frame)

        # 文件表格
        self.file_table = self._create_file_table()
        layout.addWidget(self.file_table)

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
        layout.setSpacing(10)

        # 扫描按钮
        self.scan_btn = QPushButton("扫描目录")
        self.scan_btn.setFixedHeight(36)
        self.scan_btn.setToolTip("扫描配置的目录，增量更新文件历史")
        self.scan_btn.setStyleSheet("""
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
            QPushButton:disabled {
                background: #bdc3c7;
            }
        """)
        self.scan_btn.clicked.connect(self._start_scan)
        layout.addWidget(self.scan_btn)

        # 清理已删除按钮
        cleanup_btn = QPushButton("清理已删除记录")
        cleanup_btn.setFixedHeight(36)
        cleanup_btn.setToolTip("从数据库中移除已标记删除的记录")
        cleanup_btn.setStyleSheet("""
            QPushButton {
                background: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #c0392b;
            }
        """)
        cleanup_btn.clicked.connect(self._cleanup_deleted)
        layout.addWidget(cleanup_btn)

        # 清空全部按钮
        clear_btn = QPushButton("清空历史")
        clear_btn.setFixedHeight(36)
        clear_btn.setToolTip("清空所有文件历史记录")
        clear_btn.setStyleSheet("""
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
        clear_btn.clicked.connect(self._clear_all)
        layout.addWidget(clear_btn)

        layout.addStretch()

        return frame

    def _create_filter_frame(self) -> QFrame:
        """创建筛选栏"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: #ffffff;
                border: 1px solid #dee2e6;
                border-radius: 8px;
            }
        """)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(15)

        # 搜索框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索番号...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px 12px;
                background: #f8f9fa;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #3498db;
            }
        """)
        self.search_input.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search_input, 1)

        # 状态筛选
        layout.addWidget(QLabel("状态:"))
        self.status_filter = QComboBox()
        self.status_filter.addItems(["全部", "有正常文件", "全部已删除"])
        self.status_filter.setFixedWidth(120)
        self.status_filter.setStyleSheet("""
            QComboBox {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 6px 10px;
                background: #fff;
            }
        """)
        self.status_filter.currentIndexChanged.connect(self._apply_filter)
        layout.addWidget(self.status_filter)

        return frame

    def _create_stats_frame(self) -> QFrame:
        """创建统计栏"""
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

        self.total_label = QLabel("总番号: 0")
        self.total_label.setStyleSheet("color: #2c3e50; font-size: 13px;")
        layout.addWidget(self.total_label)

        layout.addStretch()

        self.normal_label = QLabel("有正常文件: 0")
        self.normal_label.setStyleSheet("color: #27ae60; font-size: 13px;")
        layout.addWidget(self.normal_label)

        layout.addStretch()

        self.files_label = QLabel("总文件数: 0")
        self.files_label.setStyleSheet("color: #3498db; font-size: 13px;")
        layout.addWidget(self.files_label)

        return frame

    def _create_file_table(self) -> QTableWidget:
        """创建番号表格（按番号分组）"""
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["番号", "文件数", "状态", "首次发现", "最后发现"])

        table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #dee2e6;
                background: #fff;
                gridline-color: #dee2e6;
            }
            QTableWidget::item {
                padding: 6px;
            }
            QTableWidget::item:selected {
                background: #e3f2fd;
                color: #2c3e50;
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
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        table.setColumnWidth(0, 120)
        table.setColumnWidth(1, 80)
        table.setColumnWidth(2, 100)
        table.setColumnWidth(3, 140)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)

        # 双击查看详情
        table.cellDoubleClicked.connect(self._on_double_click)

        return table

    def _init_table(self):
        """初始化数据库表"""
        db.execute("""
            CREATE TABLE IF NOT EXISTS file_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                av_code TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL UNIQUE,
                file_size INTEGER,
                ext TEXT,
                status TEXT DEFAULT 'normal',
                first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                deleted_at DATETIME
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_file_history_av ON file_history(av_code)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_file_history_status ON file_history(status)")

    def _connect_signals(self):
        """连接扫描器信号"""
        file_history_scanner.scan_started.connect(self._on_scan_started)
        file_history_scanner.scan_progress.connect(self._on_scan_progress)
        file_history_scanner.scan_completed.connect(self._on_scan_completed)
        file_history_scanner.scan_error.connect(self._on_scan_error)

    def _start_scan(self):
        """开始扫描"""
        if file_history_scanner.is_scanning():
            QMessageBox.warning(self, "警告", "已有扫描任务在进行中")
            return

        paths = db.query("SELECT path FROM scan_paths WHERE enabled = 1")
        if not paths:
            QMessageBox.warning(self, "警告", "请先在配置页添加扫描目录")
            return

        file_history_scanner.scan_all_paths()

    def _on_scan_started(self):
        """扫描开始"""
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("扫描中...")

    def _on_scan_progress(self, processed: int, total: int, current_file: str):
        """扫描进度"""
        self.progress_bar.setValue(int(processed / total * 100))

    def _on_scan_completed(self, new_count: int, restored_count: int, deleted_count: int):
        """扫描完成"""
        self.progress_bar.setVisible(False)
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("扫描目录")

        self._load_data()

        # 同步到 file_index
        file_history_scanner.sync_to_file_index()

        QMessageBox.information(
            self,
            "扫描完成",
            f"新增: {new_count} 条\n恢复: {restored_count} 条\n删除: {deleted_count} 条"
        )

    def _on_scan_error(self, error_msg: str):
        """扫描错误"""
        self.progress_bar.setVisible(False)
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("扫描目录")
        QMessageBox.warning(self, "扫描错误", error_msg)

    def _load_data(self):
        """加载数据"""
        self._apply_filter()
        self._update_stats()

    def _apply_filter(self):
        """应用筛选 - 按番号分组显示"""
        keyword = self.search_input.text().strip()
        status_filter = self.status_filter.currentText()

        # 按番号分组查询
        sql = """
            SELECT
                av_code,
                COUNT(*) as file_count,
                SUM(CASE WHEN status = 'normal' THEN 1 ELSE 0 END) as normal_count,
                SUM(CASE WHEN status = 'deleted' THEN 1 ELSE 0 END) as deleted_count,
                MIN(first_seen_at) as first_seen_at,
                MAX(last_seen_at) as last_seen_at
            FROM file_history
            WHERE 1=1
        """
        params = []

        if keyword:
            sql += " AND av_code LIKE ?"
            params.append(f"%{keyword}%")

        sql += " GROUP BY av_code"

        if status_filter == "有正常文件":
            sql += " HAVING normal_count > 0"
        elif status_filter == "全部已删除":
            sql += " HAVING normal_count = 0"

        sql += " ORDER BY last_seen_at DESC LIMIT 500"

        rows = db.query(sql, params)

        self.file_table.setRowCount(len(rows))

        for i, row in enumerate(rows):
            normal_count = row['normal_count'] or 0
            deleted_count = row['deleted_count'] or 0
            file_count = row['file_count'] or 0

            # 番号
            av_item = QTableWidgetItem(row['av_code'])
            av_item.setForeground(Qt.GlobalColor.blue)
            av_item.setData(Qt.ItemDataRole.UserRole, row['av_code'])
            self.file_table.setItem(i, 0, av_item)

            # 文件数
            count_item = QTableWidgetItem(str(file_count))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if file_count > 1:
                count_item.setForeground(Qt.GlobalColor.darkGreen)
                font = QFont()
                font.setBold(True)
                count_item.setFont(font)
            self.file_table.setItem(i, 1, count_item)

            # 状态
            if normal_count > 0:
                status_text = f"正常({normal_count})"
                status_item = QTableWidgetItem(status_text)
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            else:
                status_text = f"已删除({deleted_count})"
                status_item = QTableWidgetItem(status_text)
                status_item.setForeground(Qt.GlobalColor.red)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.file_table.setItem(i, 2, status_item)

            # 首次发现
            first_seen = row['first_seen_at'] or ''
            if first_seen:
                try:
                    dt = datetime.fromisoformat(str(first_seen).replace("T", " "))
                    first_seen = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    pass
            self.file_table.setItem(i, 3, QTableWidgetItem(first_seen))

            # 最后发现
            last_seen = row['last_seen_at'] or ''
            if last_seen:
                try:
                    dt = datetime.fromisoformat(str(last_seen).replace("T", " "))
                    last_seen = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    pass
            self.file_table.setItem(i, 4, QTableWidgetItem(last_seen))

        for i in range(len(rows)):
            self.file_table.setRowHeight(i, 32)

    def _on_double_click(self, row: int, column: int):
        """双击查看详情"""
        av_item = self.file_table.item(row, 0)
        if av_item:
            av_code = av_item.data(Qt.ItemDataRole.UserRole)
            dialog = FileDetailDialog(self, av_code)
            dialog.exec()

    def _update_stats(self):
        """更新统计信息"""
        total_av = db.query_one("SELECT COUNT(DISTINCT av_code) as count FROM file_history")
        normal_av = db.query_one("""
            SELECT COUNT(DISTINCT av_code) as count FROM file_history WHERE status = 'normal'
        """)
        total_files = db.query_one("SELECT COUNT(*) as count FROM file_history")

        self.total_label.setText(f"总番号: {total_av['count'] if total_av else 0}")
        self.normal_label.setText(f"有正常文件: {normal_av['count'] if normal_av else 0}")
        self.files_label.setText(f"总文件数: {total_files['count'] if total_files else 0}")

    def _cleanup_deleted(self):
        """清理已删除记录"""
        reply = QMessageBox.question(
            self, "确认清理",
            "确定要从数据库中移除所有已删除的记录吗？\n此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            db.execute("DELETE FROM file_history WHERE status = 'deleted'")
            from core.index_manager import index_manager
            index_manager.refresh_search_index()
            self._load_data()
            QMessageBox.information(self, "完成", "已清理所有删除记录")

    def _clear_all(self):
        """清空历史"""
        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空所有文件历史记录吗？\n此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            db.execute("DELETE FROM file_history")
            from core.index_manager import index_manager
            index_manager.refresh_search_index()
            self._load_data()
            QMessageBox.information(self, "完成", "已清空所有历史记录")

    def refresh(self):
        """刷新页面"""
        self._load_data()
