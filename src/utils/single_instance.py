#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
单实例检测 - 确保应用只能运行一个实例
"""
import sys
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication


class SingleInstance:
    """单实例检测类"""

    def __init__(self, app: QApplication, server_name: str = "ThunderDedupeApp"):
        self.app = app
        self.server_name = server_name
        self.server = None
        self.socket = None
        self.main_window = None

    def is_running(self) -> bool:
        """检查是否已有实例运行"""
        # 尝试连接已有实例
        self.socket = QLocalSocket()
        self.socket.connectToServer(self.server_name)

        # 如果能连接成功，说明已有实例
        if self.socket.waitForConnected(500):
            # 发送消息让已有实例激活窗口
            self.socket.write(b"SHOW_WINDOW")
            self.socket.flush()
            self.socket.waitForBytesWritten(500)
            self.socket.disconnectFromServer()
            return True

        # 没有已有实例，创建本地服务器监听后续连接
        self.socket = None

        # 清理可能残留的服务器（上次异常退出）
        QLocalServer.removeServer(self.server_name)

        self.server = QLocalServer()
        if not self.server.listen(self.server_name):
            print(f"无法创建本地服务器: {self.server.errorString()}")
            return False

        # 监听新连接
        self.server.newConnection.connect(self._on_new_connection)
        return False

    def set_main_window(self, window):
        """设置主窗口引用"""
        self.main_window = window

    def _on_new_connection(self):
        """处理新连接（第二个实例尝试启动）"""
        socket = self.server.nextPendingConnection()
        if socket:
            # 读取消息
            socket.waitForReadyRead(500)
            message = socket.readAll().data()

            # 如果收到显示窗口的消息，激活主窗口
            if message == b"SHOW_WINDOW" and self.main_window:
                self.main_window.show()
                self.main_window.activateWindow()
                self.main_window.raise_()

            socket.disconnectFromServer()
            socket.deleteLater()