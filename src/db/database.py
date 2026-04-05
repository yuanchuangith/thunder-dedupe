#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据库连接管理
"""
import sqlite3
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

from utils.config import get_data_dir


class Database:
    """数据库管理类"""

    _instance: Optional['Database'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.db_path = get_data_dir() / "thunder_dedupe.db"
        self._ensure_db()

    def _ensure_db(self):
        """确保数据库文件存在"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def get_connection(self):
        """获取数据库连接上下文管理器"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def execute(self, sql: str, params: tuple = ()):
        """执行SQL语句"""
        with self.get_connection() as conn:
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor.lastrowid

    def query(self, sql: str, params: tuple = ()) -> list:
        """查询数据"""
        with self.get_connection() as conn:
            cursor = conn.execute(sql, params)
            return cursor.fetchall()

    def query_one(self, sql: str, params: tuple = ()):
        """查询单条数据"""
        with self.get_connection() as conn:
            cursor = conn.execute(sql, params)
            return cursor.fetchone()


# 全局数据库实例
db = Database()