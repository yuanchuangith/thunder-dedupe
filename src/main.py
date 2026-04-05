#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
迅雷去重助手 - 应用入口
"""
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from ui.main_window import MainWindow
from utils.single_instance import SingleInstance


def main():
    """应用主入口"""
    # 高DPI支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("迅雷去重助手")
    app.setApplicationVersion("1.0.0")

    # 设置应用样式
    app.setStyle("Fusion")

    # 单实例检测
    instance = SingleInstance(app)
    if instance.is_running():
        print("应用已在运行，激活已有实例...")
        sys.exit(0)

    # 创建主窗口
    window = MainWindow()
    window.show()

    # 设置主窗口引用，用于单实例激活
    instance.set_main_window(window)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()