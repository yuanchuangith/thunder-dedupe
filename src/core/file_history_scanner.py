#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
文件历史扫描器 - 增量扫描、番号分组
"""
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt6.QtCore import QObject, pyqtSignal

from db.database import db
from core.av_parser import AVParser
from utils.config import config
from utils.logger import logger


class FileHistoryScanner(QObject):
    """文件历史扫描器"""

    # 信号
    scan_started = pyqtSignal()
    scan_progress = pyqtSignal(int, int, str)  # 已扫描, 总文件, 当前文件
    scan_completed = pyqtSignal(int, int, int)  # 新增数, 恢复数, 删除数
    scan_error = pyqtSignal(str)

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
        """扫描所有配置的目录"""
        if self._scanning:
            logger.warning("已有扫描任务在进行")
            return

        paths = db.query("SELECT path FROM scan_paths WHERE enabled = 1")
        if not paths:
            logger.warning("没有配置扫描目录")
            self.scan_error.emit("请先添加扫描目录")
            return

        path_list = [row['path'] for row in paths]

        thread = threading.Thread(
            target=self._scan_worker,
            args=(path_list, callback),
            daemon=True
        )
        thread.start()

    def _scan_worker(self, paths: list, callback: Optional[Callable]):
        """扫描工作线程"""
        self._scanning = True
        self._stop_flag = False
        self.scan_started.emit()

        try:
            # 获取扩展名配置
            video_extensions = config.get_video_extensions()
            temp_extensions = config.get_temp_extensions()
            all_extensions = video_extensions | temp_extensions

            # 先收集所有文件
            all_files = []
            for path in paths:
                if self._stop_flag:
                    break

                logger.info(f"正在扫描目录: {path}")
                files = self._collect_files(path, all_extensions)
                logger.info(f"目录 {path} 找到 {len(files)} 个视频文件")
                all_files.extend(files)

            total_files = len(all_files)
            logger.info(f"总计找到 {total_files} 个文件待扫描")

            if total_files == 0:
                self._scanning = False
                self.scan_completed.emit(0, 0, 0)
                if callback:
                    callback(0, 0, 0)
                return

            # 获取数据库现有记录
            existing_records = db.query("SELECT id, file_path, status FROM file_history")
            existing_paths = {row['file_path']: {'id': row['id'], 'status': row['status']} for row in existing_records}

            # 统计
            new_count = 0
            restored_count = 0
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 处理文件
            processed = 0
            batch_data = []

            for file_path in all_files:
                if self._stop_flag:
                    break

                processed += 1
                self.scan_progress.emit(processed, total_files, str(file_path))

                # 解析番号
                filename = Path(file_path).name
                av_code = self._parser.parse_from_filename(filename)

                if not av_code:
                    continue

                # 获取文件信息
                try:
                    file_size = os.path.getsize(file_path)
                    ext = Path(file_path).suffix.lower()
                except:
                    continue

                if file_path in existing_paths:
                    # 已存在
                    existing = existing_paths[file_path]
                    if existing['status'] == 'deleted':
                        # 恢复
                        db.execute("""
                            UPDATE file_history
                            SET status = 'normal', av_code = ?, filename = ?, file_size = ?, ext = ?,
                                last_seen_at = ?, deleted_at = NULL
                            WHERE id = ?
                        """, (av_code, filename, file_size, ext, now, existing['id']))
                        restored_count += 1
                    else:
                        # 更新
                        db.execute("""
                            UPDATE file_history
                            SET av_code = ?, file_size = ?, last_seen_at = ?
                            WHERE id = ?
                        """, (av_code, file_size, now, existing['id']))
                else:
                    # 新文件
                    db.execute("""
                        INSERT INTO file_history (av_code, filename, file_path, file_size, ext, status, first_seen_at, last_seen_at)
                        VALUES (?, ?, ?, ?, ?, 'normal', ?, ?)
                    """, (av_code, filename, file_path, file_size, ext, now, now))
                    new_count += 1

            # 处理删除的文件
            deleted_count = 0
            scanned_paths = set(all_files)
            for file_path, record in existing_paths.items():
                if file_path not in scanned_paths and record['status'] == 'normal':
                    db.execute("""
                        UPDATE file_history SET status = 'deleted', deleted_at = ? WHERE id = ?
                    """, (now, record['id']))
                    deleted_count += 1

            logger.info(f"扫描完成: 新增={new_count}, 恢复={restored_count}, 删除={deleted_count}")

            self._scanning = False
            self.scan_completed.emit(new_count, restored_count, deleted_count)

            if callback:
                callback(new_count, restored_count, deleted_count)

        except Exception as e:
            logger.error(f"扫描出错: {e}")
            self._scanning = False
            self.scan_error.emit(str(e))

    def _collect_files(self, path: str, extensions: set) -> list:
        """收集目录下的所有视频文件"""
        files = []
        try:
            p = Path(path)
            if not p.exists():
                logger.warning(f"目录不存在: {path}")
                return files

            for file_path in p.rglob('*'):
                if self._stop_flag:
                    break

                if file_path.is_file():
                    ext = file_path.suffix.lower()
                    if ext in extensions:
                        files.append(str(file_path))

        except Exception as e:
            logger.warning(f"遍历目录出错 {path}: {e}")

        return files

    def sync_to_file_index(self):
        """同步到 file_index 表"""
        db.execute("DELETE FROM file_index")
        db.execute("""
            INSERT INTO file_index (av_code, original_name, file_path, file_size)
            SELECT av_code, filename, file_path, file_size
            FROM file_history
            WHERE status = 'normal'
        """)
        from core.index_manager import index_manager
        index_manager.refresh_search_index()
        logger.info("已同步到文件索引")


# 全局扫描器实例
file_history_scanner = FileHistoryScanner()
