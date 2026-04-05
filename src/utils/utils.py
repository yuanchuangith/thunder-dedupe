#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
通用工具函数
"""
import re
from typing import Optional


def normalize_av_code(code: str) -> str:
    """
    标准化番号格式

    将各种格式的番号统一为大写带横线的格式
    例如: "sxma016" -> "SXMA-016", "TOTK-015" -> "TOTK-015"
    """
    if not code:
        return ""

    code = code.upper().strip()

    # 如果已经有横线，直接返回
    if '-' in code:
        return code

    # 尝试在字母和数字之间插入横线
    match = re.match(r'^([A-Z]+)(\d+)$', code)
    if match:
        return f"{match.group(1)}-{match.group(2)}"

    return code


def format_file_size(size_bytes: int) -> str:
    """
    格式化文件大小

    Args:
        size_bytes: 字节数

    Returns:
        人类可读的大小字符串
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def format_duration(seconds: int) -> str:
    """
    格式化持续时间

    Args:
        seconds: 秒数

    Returns:
        格式化的时间字符串
    """
    if seconds < 60:
        return f"{seconds}秒"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes}分钟"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}小时{minutes}分钟"