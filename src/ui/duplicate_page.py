#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
重复检测模块 - 列出重复番号及对应文件
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QMessageBox, QTextEdit,
    QDialog
)
from PyQt6.QtCore import Qt

from db.database import db
from utils.utils import format_file_size


class FileDetailDialog(QDialog):
    """文件详情对话框"""

    def __init__(self, parent, av_code: str, files: list):
        super().__init__(parent)
        self.setWindowTitle(f"番号: {av_code}")
        self.setFixedSize(600, 400)

        layout = QVBoxLayout(self)

        # 标题
        title = QLabel(f"番号 {av_code} 共有 {len(files)} 个文件")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title)

        # 文件列表
        text = QTextEdit()
        text.setReadOnly(True)
        text.setStyleSheet("""
            QTextEdit {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
                background: #f8f9fa;
            }
        """)

        content = ""
        for i, f in enumerate(files, 1):
            size = format_file_size(f['file_size'] or 0)
            content += f"{i}. {f['original_name']}\n"
            content += f"   大小: {size}\n"
            content += f"   路径: {f['file_path']}\n\n"

        text.setText(content)
        layout.addWidget(text)

        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class DuplicatePage(QWidget):
    """重复检测页面"""

    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        """设置界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 标题栏
        title_frame = self._create_title_frame()
        layout.addWidget(title_frame)

        # 统计信息
        self.stats_label = QLabel("加载中...")
        self.stats_label.setStyleSheet("color: #555; font-size: 13px;")
        layout.addWidget(self.stats_label)

        # 重复列表表格
        self.dup_table = self._create_table()
        layout.addWidget(self.dup_table)

        # 初始加载
        self._load_data()

    def _create_title_frame(self) -> QFrame:
        """创建标题栏"""
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
        title = QLabel("重复番号检测")
        title.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #2c3e50;
            }
        """)
        layout.addWidget(title)

        layout.addStretch()

        # 刷新按钮
        refresh_btn = QPushButton("刷新")
        refresh_btn.setFixedHeight(32)
        refresh_btn.setToolTip("重新检测重复番号")
        refresh_btn.setStyleSheet("""
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
        refresh_btn.clicked.connect(self._load_data)
        layout.addWidget(refresh_btn)

        return frame

    def _create_table(self) -> QTableWidget:
        """创建表格"""
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["番号", "文件数", "总大小", "操作"])

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
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)

        table.setColumnWidth(1, 80)
        table.setColumnWidth(2, 100)
        table.setColumnWidth(3, 80)

        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)

        return table

    def _load_data(self):
        """加载数据"""
        # 查询重复番号（文件数>1的）
        rows = db.query("""
            SELECT
                av_code,
                COUNT(*) as file_count,
                SUM(file_size) as total_size
            FROM file_index
            GROUP BY av_code
            HAVING COUNT(*) > 1
            ORDER BY file_count DESC, av_code
        """)

        # 统计信息
        total_files = db.query_one("SELECT COUNT(*) as count FROM file_index")
        unique_codes = db.query_one("SELECT COUNT(DISTINCT av_code) as count FROM file_index")
        dup_codes = len(rows)

        if rows:
            dup_files = sum(r['file_count'] for r in rows)
            self.stats_label.setText(
                f"共 {unique_codes['count']} 个番号，{total_files['count']} 个文件 | "
                f"重复番号: {dup_codes} 个，涉及 {dup_files} 个文件"
            )
        else:
            self.stats_label.setText(
                f"共 {unique_codes['count']} 个番号，{total_files['count']} 个文件 | 无重复"
            )

        # 填充表格
        self.dup_table.setRowCount(len(rows))

        for i, row in enumerate(rows):
            # 番号
            code_item = QTableWidgetItem(row['av_code'])
            code_item.setForeground(Qt.GlobalColor.darkBlue)
            self.dup_table.setItem(i, 0, code_item)

            # 文件数
            count_item = QTableWidgetItem(str(row['file_count']))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            count_item.setForeground(Qt.GlobalColor.red)
            self.dup_table.setItem(i, 1, count_item)

            # 总大小
            size_item = QTableWidgetItem(format_file_size(row['total_size'] or 0))
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.dup_table.setItem(i, 2, size_item)

            # 操作按钮
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 2, 4, 2)

            detail_btn = QPushButton("详情")
            detail_btn.setFixedHeight(26)
            detail_btn.setStyleSheet("""
                QPushButton {
                    background: #27ae60;
                    color: white;
                    border: none;
                    border-radius: 3px;
                    padding: 4px 8px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background: #2ecc71;
                }
            """)
            detail_btn.clicked.connect(lambda checked, c=row['av_code']: self._show_detail(c))
            btn_layout.addWidget(detail_btn)

            self.dup_table.setCellWidget(i, 3, btn_widget)

    def _show_detail(self, av_code: str):
        """显示详情"""
        # 查询该番号的所有文件
        files = db.query("""
            SELECT original_name, file_path, file_size
            FROM file_index
            WHERE av_code = ?
            ORDER BY file_size DESC
        """, (av_code,))

        dialog = FileDetailDialog(self, av_code, files)
        dialog.exec()

    def refresh(self):
        """公开的刷新方法，供外部调用"""
        self._load_data()