#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
番号解析引擎 - 完整版
"""
import re
from typing import Optional, List, Tuple
from pathlib import Path

from db.database import db
from utils.utils import normalize_av_code
from utils.logger import logger


class AVParser:
    """番号解析器"""

    # 迅雷链接格式
    THUNDER_LINK_PATTERNS = [
        r'^thunder://[A-Za-z0-9+/=]+',  # 迅雷专用链
        r'^magnet:\?xt=urn:btih:[A-Za-z0-9]+',  # 磁力链
        r'^ed2k://\|file\|[^|]+\|\d+\|[A-Za-z0-9]+\|/',  # ed2k链
    ]

    def __init__(self):
        self._rules = self._load_rules()

    def _load_rules(self) -> List[Tuple[str, int]]:
        """加载解析规则"""
        rows = db.query("""
            SELECT pattern, priority, enabled
            FROM parse_rules
            WHERE enabled = 1
            ORDER BY priority DESC
        """)
        return [(row['pattern'], row['priority']) for row in rows]

    def parse(self, text: str) -> Optional[str]:
        """
        从文本中解析番号

        Args:
            text: 输入文本（文件名、链接等）

        Returns:
            标准化后的番号，未匹配返回None
        """
        if not text:
            return None

        # 如果是迅雷链接，先解码获取文件名
        decoded_text = self._decode_thunder_link(text)
        if decoded_text:
            text = decoded_text

        # 按优先级尝试每个规则
        for pattern, _ in self._rules:
            try:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    raw_code = match.group(0)
                    return normalize_av_code(raw_code)
            except re.error as e:
                logger.warning(f"正则规则错误: {pattern}, {e}")
                continue

        # 使用内置规则作为后备
        builtin_patterns = [
            r'[A-Z]{2,6}-\d{3,5}',      # 标准格式: ABC-123
            r'[A-Z]{2,6}\d{3,5}',       # 无横线格式: ABC123
            r'[A-Z]{3,6}-\d{2,4}',      # 短编号格式: ABC-12
            r'[A-Z]{2,5}[-_]?\d{3,4}',  # 兼容下划线: ABC_123
        ]

        for pattern in builtin_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                raw_code = match.group(0)
                return normalize_av_code(raw_code)

        return None

    def _decode_thunder_link(self, link: str) -> Optional[str]:
        """
        解码迅雷链接获取文件名

        Args:
            link: 迅雷链接

        Returns:
            解码后的文件名，解码失败返回None
        """
        import base64

        # 检查是否是迅雷链接
        for pattern in self.THUNDER_LINK_PATTERNS:
            if re.match(pattern, link):
                try:
                    if link.startswith('thunder://'):
                        # 迅雷专用链是base64编码
                        encoded = link.replace('thunder://', '')
                        # 迅雷链接前后有特殊标记
                        decoded = base64.b64decode(encoded).decode('utf-8', errors='ignore')
                        # 去除迅雷的AA和ZZ标记
                        decoded = decoded.replace('AA', '').replace('ZZ', '')
                        return decoded
                    elif link.startswith('magnet:'):
                        # 磁力链从dn参数获取名称
                        dn_match = re.search(r'dn=([^&]+)', link)
                        if dn_match:
                            from urllib.parse import unquote
                            return unquote(dn_match.group(1))
                    elif link.startswith('ed2k://'):
                        # ed2k链从文件名部分获取
                        parts = link.split('|')
                        if len(parts) >= 4:
                            return parts[2]
                except Exception as e:
                    logger.warning(f"解码链接失败: {e}")
                return None

        return None

    def is_download_link(self, text: str) -> bool:
        """
        判断是否是下载链接（仅限迅雷/磁力/ed2k）

        Args:
            text: 输入文本

        Returns:
            是否是下载链接
        """
        # 只匹配迅雷链接、磁力链接、ed2k链接
        for pattern in self.THUNDER_LINK_PATTERNS:
            if re.match(pattern, text):
                return True

        return False

    def parse_from_filename(self, filename: str) -> Optional[str]:
        """
        从文件名解析番号

        Args:
            filename: 文件名（包含扩展名）

        Returns:
            标准化后的番号
        """
        # 去除扩展名
        name = Path(filename).stem

        # 常见的干扰词和前缀
        # 1. 先去除常见的网站前缀 (如 hhd800.com@, 77vr.com@ 等)
        name = re.sub(r'^[a-z0-9.-]+@', '', name, flags=re.IGNORECASE)

        # 2. 去除常见的干扰词
        noise_words = [
            'uncensored', 'hd', 'fhd', '4k', '1080p', '720p',
            'subtitle', 'sub', 'chs', 'cht', 'jpn',
            'torrent', 'download', 'preview', 'sample', 'restored'
        ]

        clean_name = name
        for word in noise_words:
            clean_name = re.sub(r'\b' + word + r'\b', '', clean_name, flags=re.IGNORECASE)

        # 3. 清理多余的点和下划线
        clean_name = re.sub(r'[._]+', ' ', clean_name)

        return self.parse(clean_name)

    def refresh_rules(self):
        """刷新规则"""
        self._rules = self._load_rules()
        logger.info("解析规则已刷新")

    def check_exists(self, av_code: str) -> Optional[dict]:
        """
        检查番号是否已存在于索引中

        Args:
            av_code: 标准化番号

        Returns:
            存在时返回文件信息字典，不存在返回None
        """
        normalized = normalize_av_code(av_code)
        row = db.query_one(
            "SELECT av_code, original_name, file_path, file_size FROM file_index WHERE av_code = ?",
            (normalized,)
        )
        if row:
            return {
                'av_code': row['av_code'],
                'original_name': row['original_name'],
                'file_path': row['file_path'],
                'file_size': row['file_size']
            }
        return None