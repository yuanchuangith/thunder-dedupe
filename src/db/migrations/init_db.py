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

        # 统一搜索索引表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS search_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                av_code TEXT NOT NULL,
                original_name TEXT,
                file_path TEXT NOT NULL,
                file_size INTEGER,
                source TEXT NOT NULL,
                status TEXT DEFAULT 'normal',
                priority INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_search_index_av_code ON search_index(av_code)
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

        # 文件历史表 - 先删除旧表（可能有错误的 UNIQUE 约束）
        # 检查是否有旧的 UNIQUE 约束在 av_code 上
        try:
            # 检查表是否存在且有错误的约束
            result = conn.execute("PRAGMA table_info(file_history)").fetchall()
            if result:
                # 表存在，检查是否有数据
                count = conn.execute("SELECT COUNT(*) FROM file_history").fetchone()[0]
                if count > 0:
                    # 有数据，先备份
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS file_history_backup AS
                        SELECT * FROM file_history
                    """)
                # 删除旧表
                conn.execute("DROP TABLE IF EXISTS file_history")
        except:
            pass

        # 重新创建文件历史表（正确的结构）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS file_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                av_code TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL UNIQUE,
                file_size INTEGER,
                ext TEXT,
                status TEXT DEFAULT 'normal',
                first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                deleted_at DATETIME
            )
        """)

        # 恢复备份数据（如果有）
        try:
            conn.execute("""
                INSERT OR IGNORE INTO file_history
                SELECT * FROM file_history_backup
            """)
            conn.execute("DROP TABLE IF EXISTS file_history_backup")
        except:
            pass

        # 创建番号索引（用于分组查询）
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_file_history_av ON file_history(av_code)
        """)

        # 创建状态索引
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_file_history_status ON file_history(status)
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
