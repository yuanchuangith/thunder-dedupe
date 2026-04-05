#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据模型
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ScanPath:
    """扫描目录"""
    id: Optional[int] = None
    path: str = ""
    enabled: bool = True
    created_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row) -> 'ScanPath':
        """从数据库行创建"""
        return cls(
            id=row['id'],
            path=row['path'],
            enabled=bool(row['enabled']),
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
        )


@dataclass
class ParseRule:
    """解析规则"""
    id: Optional[int] = None
    name: str = ""
    pattern: str = ""
    priority: int = 0
    enabled: bool = True
    created_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row) -> 'ParseRule':
        """从数据库行创建"""
        return cls(
            id=row['id'],
            name=row['name'],
            pattern=row['pattern'],
            priority=row['priority'],
            enabled=bool(row['enabled']),
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
        )


@dataclass
class FileIndex:
    """文件索引"""
    id: Optional[int] = None
    av_code: str = ""
    original_name: str = ""
    file_path: str = ""
    file_size: int = 0
    created_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row) -> 'FileIndex':
        """从数据库行创建"""
        return cls(
            id=row['id'],
            av_code=row['av_code'],
            original_name=row['original_name'],
            file_path=row['file_path'],
            file_size=row['file_size'] or 0,
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
        )


@dataclass
class InterceptLog:
    """拦截日志"""
    id: Optional[int] = None
    av_code: str = ""
    source: str = ""
    file_name: str = ""
    status: str = ""
    user_action: str = ""
    user_decision: bool = False
    created_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row) -> 'InterceptLog':
        """从数据库行创建"""
        return cls(
            id=row['id'],
            av_code=row['av_code'],
            source=row['source'],
            file_name=row['file_name'],
            status=row['status'],
            user_action=row['user_action'],
            user_decision=bool(row['user_decision']),
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
        )