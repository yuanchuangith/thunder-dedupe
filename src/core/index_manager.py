#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
番号索引管理器 - 增量更新、查询接口
"""
from typing import Optional, List, Dict
from pathlib import Path
import os

from db.database import db
from core.av_parser import AVParser
from utils.logger import logger
from utils.utils import normalize_av_code, format_file_size


class IndexManager:
    """索引管理器"""

    def __init__(self):
        self._parser = AVParser()

    def search(self, av_code: str) -> Optional[Dict]:
        """
        搜索番号索引

        Args:
            av_code: 番号（标准化前后的都可以）

        Returns:
            番号信息字典，未找到返回None
        """
        normalized = normalize_av_code(av_code)

        row = db.query_one("""
            SELECT id, av_code, original_name, file_path, file_size, created_at
            FROM file_index
            WHERE av_code = ?
            ORDER BY file_size DESC
            LIMIT 1
        """, (normalized,))

        if row:
            return {
                'id': row['id'],
                'av_code': row['av_code'],
                'original_name': row['original_name'],
                'file_path': row['file_path'],
                'file_size': row['file_size'],
                'file_size_display': format_file_size(row['file_size'] or 0),
                'created_at': row['created_at']
            }

        return None

    def search_all_matches(self, av_code: str) -> List[Dict]:
        """
        搜索番号的所有匹配记录

        Args:
            av_code: 番号

        Returns:
            匹配记录列表
        """
        normalized = normalize_av_code(av_code)

        rows = db.query("""
            SELECT id, av_code, original_name, file_path, file_size, created_at
            FROM file_index
            WHERE av_code = ?
            ORDER BY file_size DESC
        """, (normalized,))

        results = []
        for row in rows:
            results.append({
                'id': row['id'],
                'av_code': row['av_code'],
                'original_name': row['original_name'],
                'file_path': row['file_path'],
                'file_size': row['file_size'],
                'file_size_display': format_file_size(row['file_size'] or 0),
                'created_at': row['created_at']
            })

        return results

    def add_index(self, file_path: str) -> bool:
        """
        添加单个文件到索引

        Args:
            file_path: 文件路径

        Returns:
            是否成功添加
        """
        try:
            path = Path(file_path)
            if not path.exists():
                logger.warning(f"文件不存在: {file_path}")
                return False

            filename = path.name

            # 解析番号
            av_code = self._parser.parse_from_filename(filename)
            if not av_code:
                logger.debug(f"未能解析番号: {filename}")
                return False

            # 获取文件大小
            file_size = path.stat().st_size

            # 检查是否已存在
            existing = db.query_one(
                "SELECT id FROM file_index WHERE av_code = ? AND file_path = ?",
                (av_code, file_path)
            )

            if existing:
                logger.debug(f"索引已存在: {av_code}")
                return False

            # 添加索引
            db.execute("""
                INSERT INTO file_index (av_code, original_name, file_path, file_size)
                VALUES (?, ?, ?, ?)
            """, (av_code, filename, file_path, file_size))

            logger.info(f"添加索引: {av_code} -> {filename}")
            return True

        except Exception as e:
            logger.error(f"添加索引失败: {e}")
            return False

    def remove_index(self, index_id: int) -> bool:
        """
        删除索引记录

        Args:
            index_id: 索引ID

        Returns:
            是否成功删除
        """
        try:
            db.execute("DELETE FROM file_index WHERE id = ?", (index_id,))
            return True
        except Exception as e:
            logger.error(f"删除索引失败: {e}")
            return False

    def remove_by_path(self, file_path: str) -> bool:
        """
        根据文件路径删除索引

        Args:
            file_path: 文件路径

        Returns:
            是否成功删除
        """
        try:
            db.execute("DELETE FROM file_index WHERE file_path = ?", (file_path,))
            return True
        except Exception as e:
            logger.error(f"删除索引失败: {e}")
            return False

    def update_index(self, file_path: str) -> bool:
        """
        更新索引（文件名可能变了）

        Args:
            file_path: 文件路径

        Returns:
            是否成功更新
        """
        # 先删除旧索引
        self.remove_by_path(file_path)
        # 再添加新索引
        return self.add_index(file_path)

    def clear_all(self):
        """清空所有索引"""
        db.execute("DELETE FROM file_index")
        logger.info("已清空所有索引")

    def get_stats(self) -> Dict:
        """获取索引统计"""
        total = db.query_one("SELECT COUNT(*) as count FROM file_index")
        unique_codes = db.query_one("SELECT COUNT(DISTINCT av_code) as count FROM file_index")

        # 获取最近添加的
        recent = db.query("""
            SELECT av_code, original_name, created_at
            FROM file_index
            ORDER BY created_at DESC
            LIMIT 10
        """)

        return {
            'total_files': total['count'] if total else 0,
            'unique_codes': unique_codes['count'] if unique_codes else 0,
            'recent': recent
        }

    def check_file_exists(self, file_path: str) -> bool:
        """
        检查索引中的文件是否仍然存在

        Args:
            file_path: 文件路径

        Returns:
            文件是否存在
        """
        return Path(file_path).exists()

    def verify_indexes(self) -> Dict:
        """
        验证所有索引文件是否存在

        Returns:
            验证结果统计
        """
        rows = db.query("SELECT id, file_path FROM file_index")

        valid_count = 0
        invalid_count = 0
        invalid_ids = []

        for row in rows:
            if Path(row['file_path']).exists():
                valid_count += 1
            else:
                invalid_count += 1
                invalid_ids.append(row['id'])

        return {
            'valid': valid_count,
            'invalid': invalid_count,
            'invalid_ids': invalid_ids
        }

    def cleanup_invalid(self) -> int:
        """
        清理无效的索引记录

        Returns:
            清理的记录数
        """
        result = self.verify_indexes()

        for id in result['invalid_ids']:
            db.execute("DELETE FROM file_index WHERE id = ?", (id,))

        logger.info(f"清理了 {result['invalid']} 条无效索引")
        return result['invalid']


# 全局索引管理器实例
index_manager = IndexManager()