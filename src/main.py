#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
迅雷去重助手 - 应用入口
"""
import sys
import os
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

from ui.main_window import MainWindow
from utils.single_instance import SingleInstance
from utils.config import config


def setup_windows_taskbar():
    """设置 Windows 任务栏图标"""
    try:
        import ctypes
        # 设置 AppUserModelID，让 Windows 任务栏正确显示图标
        app_id = "ThunderDedupe.App.1.0"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def load_app_icon(app: QApplication):
    """从配置加载并应用应用图标"""
    icon_path = config.get("tray_icon_path", "")
    if icon_path and os.path.exists(icon_path):
        try:
            icon = QIcon(icon_path)
            if not icon.isNull():
                app.setWindowIcon(icon)
        except Exception:
            pass


def main():
    """应用主入口"""
    # Windows 任务栏设置
    setup_windows_taskbar()

    # 高DPI支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("迅雷去重助手")
    app.setApplicationVersion("1.0.0")

    # 设置应用样式
    app.setStyle("Fusion")

    # 加载配置的图标
    load_app_icon(app)

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