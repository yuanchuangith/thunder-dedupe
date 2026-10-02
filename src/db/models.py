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


@dataclass
class VideoSimilarityVideo:
    """视频相似度检测 - 视频信息"""
    id: Optional[int] = None
    path: str = ""
    filename: str = ""
    duration: float = 0.0
    file_size: int = 0
    format: str = ""
    frame_count: int = 0
    phash_features: Optional[bytes] = None
    clip_features: Optional[bytes] = None
    status: str = "active"
    scan_time: Optional[datetime] = None

    @classmethod
    def from_row(cls, row) -> 'VideoSimilarityVideo':
        """从数据库行创建"""
        return cls(
            id=row['id'],
            path=row['path'],
            filename=row['filename'],
            duration=row['duration'] or 0.0,
            file_size=row['file_size'] or 0,
            format=row['format'] or "",
            frame_count=row['frame_count'] or 0,
            phash_features=row['phash_features'],
            clip_features=row['clip_features'],
            status=row['status'] or "active",
            scan_time=datetime.fromisoformat(row['scan_time']) if row['scan_time'] else None
        )


@dataclass
class VideoSimilarityResult:
    """视频相似度检测 - 相似度结果"""
    id: Optional[int] = None
    video_a_id: int = 0
    video_b_id: int = 0
    similarity_score: float = 0.0
    status: str = "pending"  # pending/confirmed_duplicate/kept
    created_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row) -> 'VideoSimilarityResult':
        """从数据库行创建"""
        return cls(
            id=row['id'],
            video_a_id=row['video_a_id'],
            video_b_id=row['video_b_id'],
            similarity_score=row['similarity_score'] or 0.0,
            status=row['status'] or "pending",
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
        )


@dataclass
class VideoSimilarityPath:
    """视频相似度检测 - 扫描路径配置"""
    id: Optional[int] = None
    path: str = ""
    enabled: bool = True
    created_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row) -> 'VideoSimilarityPath':
        """从数据库行创建"""
        return cls(
            id=row['id'],
            path=row['path'],
            enabled=bool(row['enabled']),
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
        )