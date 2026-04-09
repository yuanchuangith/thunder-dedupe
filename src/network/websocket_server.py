#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
WebSocket server used by the browser extensions.
"""
import asyncio
import json
from concurrent.futures import Future
from typing import Optional, Set

from PyQt6.QtCore import QThread, pyqtSignal

from core.av_parser import AVParser
from core.index_manager import index_manager
from utils.config import config
from utils.logger import logger


class WebSocketServer(QThread):
    """Background thread that hosts the local WebSocket server."""

    client_connected = pyqtSignal()
    client_disconnected = pyqtSignal()
    message_received = pyqtSignal(dict)
    intercept_request = pyqtSignal(dict)
    server_started = pyqtSignal(int)
    server_error = pyqtSignal(str)

    DEFAULT_PORT = 9876

    def __init__(self, port: int = None):
        super().__init__()
        # 如果未指定端口，从配置读取，否则使用默认端口
        if port is None:
            port = config.get("ws_port", self.DEFAULT_PORT)
        self._port = port
        self._running = False
        self._server = None
        self._clients: Set = set()
        self._parser = AVParser()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def run(self):
        self._running = True
        try:
            asyncio.run(self._start_server())
        except Exception as exc:
            logger.error(f"WebSocket server error: {exc}")
            self.server_error.emit(str(exc))

    async def _start_server(self):
        try:
            import websockets

            self._loop = asyncio.get_running_loop()

            async def handle_client(websocket):
                self._clients.add(websocket)
                logger.info(f"Browser extension connected: {websocket.remote_address}")
                self.client_connected.emit()

                try:
                    async for message in websocket:
                        try:
                            data = json.loads(message)
                            await self._handle_message(websocket, data)
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON message: {message}")
                except websockets.exceptions.ConnectionClosed:
                    logger.info("Browser extension disconnected")
                finally:
                    self._clients.discard(websocket)
                    self.client_disconnected.emit()

            self._server = await websockets.serve(handle_client, "localhost", self._port)
            logger.info(f"WebSocket server started on port {self._port}")
            self.server_started.emit(self._port)

            while self._running:
                await asyncio.sleep(1)
        except Exception as exc:
            logger.error(f"Failed to start WebSocket server: {exc}")
            self.server_error.emit(str(exc))
        finally:
            self._loop = None

    async def _handle_message(self, websocket, message: dict):
        msg_type = message.get("type")
        payload = message.get("data", {}) or {}

        logger.debug(f"Received websocket message: {msg_type}")

        if msg_type == "heartbeat":
            await websocket.send(json.dumps({"type": "heartbeat_ack"}))

        elif msg_type == "check_av":
            resolved_av_code = self._resolve_av_code(payload)
            if payload.get("intercept"):
                self.intercept_request.emit(
                    {
                        "source": payload.get("source", "chrome"),
                        "link_content": payload.get("link_content", ""),
                        "av_code": resolved_av_code or "",
                    }
                )

            result = self._build_check_result(resolved_av_code)
            await websocket.send(json.dumps(result))

        elif msg_type == "get_status":
            status = {
                "type": "status",
                "data": {
                    "intercept_enabled": config.intercept_enabled,
                    "index_count": index_manager.get_stats()["total_files"],
                    "connected_clients": len(self._clients),
                },
            }
            await websocket.send(json.dumps(status))

        self.message_received.emit(message)

    def _resolve_av_code(self, data: dict) -> Optional[str]:
        av_code = data.get("av_code")
        if av_code:
            return av_code

        link_content = data.get("link_content", "")
        if not link_content:
            return None

        return self._parser.parse(link_content)

    def _build_check_result(self, av_code: Optional[str]) -> dict:
        if not av_code:
            return {
                "type": "check_result",
                "data": {
                    "av_code": None,
                    "exists": False,
                    "error": "无法解析番号",
                },
            }

        result = index_manager.search(av_code)
        if result:
            return {
                "type": "check_result",
                "data": {
                    "av_code": av_code,
                    "exists": True,
                    "file_path": result["file_path"],
                    "file_name": result["original_name"],
                    "file_size": result["file_size_display"],
                    "match_source": result.get("match_source", "file_index"),
                    "history_status": result.get("history_status", "normal"),
                    "is_deleted": result.get("is_deleted", False),
                },
            }

        return {
            "type": "check_result",
            "data": {
                "av_code": av_code,
                "exists": False,
            },
        }

    def stop(self):
        self._running = False
        if self._server and self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._server.close)
        logger.info("WebSocket server stopped")

    def send_to_all(self, message: dict):
        if not self._clients or not self._loop or not self._loop.is_running():
            return

        async def broadcast():
            message_text = json.dumps(message)
            stale_clients = []
            for client in list(self._clients):
                try:
                    await client.send(message_text)
                except Exception:
                    stale_clients.append(client)

            for client in stale_clients:
                self._clients.discard(client)

        future: Future = asyncio.run_coroutine_threadsafe(broadcast(), self._loop)
        try:
            future.result(timeout=2)
        except Exception:
            logger.debug("Broadcast skipped or timed out")

    def is_running(self) -> bool:
        return self._running

    def client_count(self) -> int:
        return len(self._clients)

    def get_port(self) -> int:
        """获取当前端口"""
        return self._port

    def reload_port(self):
        """
        从配置重新加载端口
        注意：需要停止并重新启动服务器才能生效
        """
        self._port = config.get("ws_port", self.DEFAULT_PORT)
        logger.info(f"WebSocket 端口已更新为: {self._port}")
        return self._port


ws_server = WebSocketServer()
