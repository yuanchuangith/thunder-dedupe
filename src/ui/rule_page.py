#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
规则页 - 解析规则配置和测试
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QLineEdit, QCheckBox,
    QDialog, QFormLayout, QDialogButtonBox,
    QMessageBox
)
from PyQt6.QtCore import Qt

from db.database import db
from db.models import ParseRule
from core.av_parser import AVParser


class RulePage(QWidget):
    """规则页"""

    def __init__(self):
        super().__init__()
        self._setup_ui()
        self._load_rules()

    def _setup_ui(self):
        """设置界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # 解析规则区域
        rules_frame = self._create_rules_frame()
        layout.addWidget(rules_frame)

        # 测试解析区域
        test_frame = self._create_test_frame()
        layout.addWidget(test_frame)

    def _create_rules_frame(self) -> QFrame:
        """创建解析规则区域"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # 标题
        title = QLabel("解析规则")
        title.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #2c3e50;
            }
        """)
        layout.addWidget(title)

        # 规则表格
        self.rule_table = QTableWidget()
        self.rule_table.setColumnCount(4)
        self.rule_table.setHorizontalHeaderLabels(["名称", "正则表达式", "优先级", "状态"])

        self.rule_table.setStyleSheet("""
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

        header = self.rule_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)

        self.rule_table.setColumnWidth(0, 120)
        self.rule_table.setColumnWidth(2, 80)
        self.rule_table.setColumnWidth(3, 80)

        self.rule_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.rule_table.verticalHeader().setVisible(False)
        self.rule_table.setMinimumHeight(150)

        layout.addWidget(self.rule_table)

        # 按钮
        btn_layout = QHBoxLayout()

        add_btn = QPushButton("+ 添加规则")
        add_btn.setStyleSheet("""
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
        add_btn.clicked.connect(self._add_rule)
        btn_layout.addWidget(add_btn)

        edit_btn = QPushButton("编辑")
        edit_btn.setStyleSheet("""
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
        edit_btn.clicked.connect(self._edit_rule)
        btn_layout.addWidget(edit_btn)

        delete_btn = QPushButton("删除")
        delete_btn.setStyleSheet("""
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
        delete_btn.clicked.connect(self._delete_rule)
        btn_layout.addWidget(delete_btn)

        btn_layout.addStretch()

        layout.addLayout(btn_layout)

        return frame

    def _create_test_frame(self) -> QFrame:
        """创建测试解析区域"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # 标题
        title = QLabel("测试解析")
        title.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #2c3e50;
            }
        """)
        layout.addWidget(title)

        # 输入
        input_layout = QHBoxLayout()
        input_label = QLabel("输入文件名:")
        input_layout.addWidget(input_label)

        self.test_input = QLineEdit()
        self.test_input.setPlaceholderText("例如: SXMA-016-HD.mp4")
        self.test_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
                background: #fff;
            }
        """)
        self.test_input.textChanged.connect(self._test_parse)
        input_layout.addWidget(self.test_input)

        layout.addLayout(input_layout)

        # 结果
        result_layout = QHBoxLayout()
        result_label = QLabel("解析结果:")
        result_layout.addWidget(result_label)

        self.test_result = QLineEdit()
        self.test_result.setReadOnly(True)
        self.test_result.setStyleSheet("""
            QLineEdit {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
                background: #fff;
                color: #27ae60;
                font-weight: bold;
            }
        """)
        result_layout.addWidget(self.test_result)

        layout.addLayout(result_layout)

        return frame

    def _load_rules(self):
        """加载解析规则"""
        rows = db.query("""
            SELECT id, name, pattern, priority, enabled
            FROM parse_rules
            ORDER BY priority DESC
        """)

        self.rule_table.setRowCount(len(rows))

        for i, row in enumerate(rows):
            # 名称
            name_item = QTableWidgetItem(row['name'])
            name_item.setData(Qt.ItemDataRole.UserRole, row['id'])
            self.rule_table.setItem(i, 0, name_item)

            # 正则表达式
            self.rule_table.setItem(i, 1, QTableWidgetItem(row['pattern']))

            # 优先级
            priority_item = QTableWidgetItem(str(row['priority']))
            priority_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.rule_table.setItem(i, 2, priority_item)

            # 状态
            status_item = QTableWidgetItem("启用" if row['enabled'] else "禁用")
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if row['enabled']:
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            else:
                status_item.setForeground(Qt.GlobalColor.gray)
            self.rule_table.setItem(i, 3, status_item)

    def _test_parse(self):
        """测试解析"""
        input_text = self.test_input.text()
        if not input_text:
            self.test_result.clear()
            return

        parser = AVParser()
        result = parser.parse(input_text)

        if result:
            self.test_result.setText(result)
        else:
            self.test_result.setText("未匹配到番号")

    def _add_rule(self):
        """添加规则"""
        dialog = RuleDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name, pattern, priority = dialog.get_values()
            db.execute("""
                INSERT INTO parse_rules (name, pattern, priority, enabled)
                VALUES (?, ?, ?, 1)
            """, (name, pattern, priority))
            self._load_rules()
            QMessageBox.information(self, "成功", "规则已添加")

    def _edit_rule(self):
        """编辑规则"""
        current_row = self.rule_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "警告", "请先选择要编辑的规则")
            return

        rule_id = self.rule_table.item(current_row, 0).data(Qt.ItemDataRole.UserRole)
        old_name = self.rule_table.item(current_row, 0).text()
        old_pattern = self.rule_table.item(current_row, 1).text()
        old_priority = int(self.rule_table.item(current_row, 2).text())

        dialog = RuleDialog(self, old_name, old_pattern, old_priority)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name, pattern, priority = dialog.get_values()
            db.execute("""
                UPDATE parse_rules
                SET name = ?, pattern = ?, priority = ?
                WHERE id = ?
            """, (name, pattern, priority, rule_id))
            self._load_rules()
            QMessageBox.information(self, "成功", "规则已更新")

    def _delete_rule(self):
        """删除规则"""
        current_row = self.rule_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "警告", "请先选择要删除的规则")
            return

        reply = QMessageBox.question(
            self,
            "确认删除",
            "确定要删除该规则吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            rule_id = self.rule_table.item(current_row, 0).data(Qt.ItemDataRole.UserRole)
            db.execute("DELETE FROM parse_rules WHERE id = ?", (rule_id,))
            self._load_rules()


class RuleDialog(QDialog):
    """规则编辑对话框"""

    def __init__(self, parent, name="", pattern="", priority=0):
        super().__init__(parent)
        self.setWindowTitle("添加规则")
        self.setFixedSize(400, 200)

        layout = QFormLayout(self)

        self.name_input = QLineEdit(name)
        layout.addRow("名称:", self.name_input)

        self.pattern_input = QLineEdit(pattern)
        layout.addRow("正则表达式:", self.pattern_input)

        self.priority_spin = QSpinBox()
        self.priority_spin.setRange(0, 100)
        self.priority_spin.setValue(priority)
        layout.addRow("优先级:", self.priority_spin)

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_values(self):
        """获取输入值"""
        return (
            self.name_input.text(),
            self.pattern_input.text(),
            self.priority_spin.value()
        )