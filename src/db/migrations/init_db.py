#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据库迁移脚本
"""
from db.database import db


def init_database():
    """初始化数据库表结构"""
    with db.get_connection() as conn:
        # 配置表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # 扫描目录表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scan_paths (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL UNIQUE,
                enabled INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 解析规则表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS parse_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                pattern TEXT NOT NULL,
                priority INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 番号索引表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS file_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                av_code TEXT NOT NULL,
                original_name TEXT,
                file_path TEXT NOT NULL,
                file_size INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 创建番号索引
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_av_code ON file_index(av_code)
        """)

        # 拦截日志表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS intercept_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                av_code TEXT NOT NULL,
                source TEXT,
                file_name TEXT,
                status TEXT,
                user_action TEXT,
                user_decision INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 创建时间索引
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_intercept_time ON intercept_logs(created_at)
        """)

        conn.commit()

    # 插入默认解析规则
    _insert_default_rules()


def _insert_default_rules():
    """插入默认解析规则"""
    default_rules = [
        ("默认格式", r"[A-Z]{2,6}-\d{3,5}", 100, 1),
        ("无横线格式", r"[A-Z]{2,6}\d{3,5}", 90, 1),
    ]

    with db.get_connection() as conn:
        # 检查是否已有规则
        cursor = conn.execute("SELECT COUNT(*) FROM parse_rules")
        if cursor.fetchone()[0] > 0:
            return

        for name, pattern, priority, enabled in default_rules:
            conn.execute(
                """
                INSERT INTO parse_rules (name, pattern, priority, enabled)
                VALUES (?, ?, ?, ?)
                """,
                (name, pattern, priority, enabled)
            )
        conn.commit()


if __name__ == "__main__":
    init_database()
    print("数据库初始化完成")