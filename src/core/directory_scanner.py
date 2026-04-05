#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
目录扫描器 - 多目录、递归、异步扫描
"""
import os
import threading
from pathlib import Path
from typing import List, Callable, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt6.QtCore import QObject, pyqtSignal

from db.database import db
from core.av_parser import AVParser
from utils.logger import logger
from utils.utils import format_file_size


class DirectoryScanner(QObject):
    """目录扫描器"""

    # 信号
    scan_started = pyqtSignal()
    scan_progress = pyqtSignal(int, int, str)  # 已扫描, 总文件, 当前文件
    scan_completed = pyqtSignal(int, int)  # 新增索引数, 总索引数
    scan_error = pyqtSignal(str)

    # 支持的视频文件扩展名
    VIDEO_EXTENSIONS = {
        '.mp4', '.mkv', '.avi', '.wmv', '.flv', '.mov',
        '.mpg', '.mpeg', '.m4v', '.rm', '.rmvb', '.ts', '.m2ts'
    }

    def __init__(self):
        super().__init__()
        self._parser = AVParser()
        self._scanning = False
        self._stop_flag = False
        self._lock = threading.Lock()

    def is_scanning(self) -> bool:
        """是否正在扫描"""
        return self._scanning

    def stop_scan(self):
        """停止扫描"""
        self._stop_flag = True

    def scan_all_paths(self, callback: Optional[Callable] = None):
        """
        扫描所有配置的目录

        Args:
            callback: 完成回调函数
        """
        if self._scanning:
            logger.warning("已有扫描任务在进行")
            return

        # 获取配置的扫描路径
        paths = db.query("SELECT path FROM scan_paths WHERE enabled = 1")
        if not paths:
            logger.warning("没有配置扫描目录")
            self.scan_error.emit("请先添加扫描目录")
            return

        path_list = [row['path'] for row in paths]

        # 在后台线程执行扫描
        thread = threading.Thread(
            target=self._scan_worker,
            args=(path_list, callback),
            daemon=True
        )
        thread.start()

    def _scan_worker(self, paths: List[str], callback: Optional[Callable]):
        """扫描工作线程"""
        self._scanning = True
        self._stop_flag = False
        self.scan_started.emit()

        try:
            # 先收集所有文件
            all_files = []
            for path in paths:
                if self._stop_flag:
                    break

                logger.info(f"正在扫描目录: {path}")
                files = self._collect_files(path)
                logger.info(f"目录 {path} 找到 {len(files)} 个视频文件")
                all_files.extend(files)

            total_files = len(all_files)
            logger.info(f"总计找到 {total_files} 个文件待扫描")

            if total_files == 0:
                self._scanning = False
                self.scan_completed.emit(0, 0)
                if callback:
                    callback(0, 0)
                return

            # 清空旧索引
            db.execute("DELETE FROM file_index")

            # 并行解析文件
            new_count = 0
            processed = 0

            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {
                    executor.submit(self._parse_and_index, f): f
                    for f in all_files
                }

                for future in as_completed(futures):
                    if self._stop_flag:
                        break

                    processed += 1
                    result = future.result()
                    if result:
                        new_count += 1

                    # 发送进度信号
                    self.scan_progress.emit(processed, total_files, str(futures[future]))

            # 获取总索引数
            total_index = db.query_one("SELECT COUNT(*) as count FROM file_index")
            total_count = total_index['count'] if total_index else 0

            logger.info(f"扫描完成，新增 {new_count} 条索引，总计 {total_count} 条")

            self._scanning = False
            self.scan_completed.emit(new_count, total_count)

            if callback:
                callback(new_count, total_count)

        except Exception as e:
            logger.error(f"扫描出错: {e}")
            self._scanning = False
            self.scan_error.emit(str(e))

    def _collect_files(self, path: str) -> List[str]:
        """
        收集目录下的所有视频文件

        Args:
            path: 目录路径

        Returns:
            文件路径列表
        """
        files = []
        try:
            p = Path(path)
            if not p.exists():
                logger.warning(f"目录不存在: {path}")
                return files

            # 递归遍历
            for file_path in p.rglob('*'):
                if self._stop_flag:
                    break

                if file_path.is_file():
                    ext = file_path.suffix.lower()
                    if ext in self.VIDEO_EXTENSIONS:
                        files.append(str(file_path))

        except Exception as e:
            logger.warning(f"遍历目录出错 {path}: {e}")

        return files

    def _parse_and_index(self, file_path: str) -> bool:
        """
        解析文件并添加到索引

        Args:
            file_path: 文件路径

        Returns:
            是否成功添加索引
        """
        try:
            filename = Path(file_path).name

            # 解析番号
            av_code = self._parser.parse_from_filename(filename)

            if not av_code:
                return False

            # 获取文件大小
            try:
                file_size = os.path.getsize(file_path)
            except:
                file_size = 0

            # 检查是否已存在
            existing = db.query_one(
                "SELECT id FROM file_index WHERE av_code = ? AND file_path = ?",
                (av_code, file_path)
            )

            if existing:
                return False

            # 添加到索引
            db.execute("""
                INSERT INTO file_index (av_code, original_name, file_path, file_size)
                VALUES (?, ?, ?, ?)
            """, (av_code, filename, file_path, file_size))

            return True

        except Exception as e:
            logger.warning(f"索引文件出错 {file_path}: {e}")
            return False

    def scan_single_path(self, path: str, callback: Optional[Callable] = None):
        """
        扫描单个目录

        Args:
            path: 目录路径
            callback: 完成回调
        """
        if self._scanning:
            return

        thread = threading.Thread(
            target=self._scan_worker,
            args=([path], callback),
            daemon=True
        )
        thread.start()

    def get_index_stats(self) -> dict:
        """获取索引统计信息"""
        total = db.query_one("SELECT COUNT(*) as count FROM file_index")
        unique_codes = db.query_one("SELECT COUNT(DISTINCT av_code) as count FROM file_index")

        return {
            'total_files': total['count'] if total else 0,
            'unique_codes': unique_codes['count'] if unique_codes else 0
        }


# 全局扫描器实例
scanner = DirectoryScanner()