#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
视频工具模块 - 帧采样、元信息提取等
"""
import os
import subprocess
import json
from pathlib import Path
from typing import List, Optional, Dict, Tuple

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

from utils.logger import logger


# 支持的视频格式
VIDEO_EXTENSIONS = {
    '.mp4', '.mkv', '.avi', '.wmv', '.flv', '.mov',
    '.mpg', '.mpeg', '.m4v', '.rm', '.rmvb', '.ts', '.m2ts',
    '.webm', '.ogv', '.3gp', '.f4v'
}


def is_video_file(file_path: str) -> bool:
    """判断是否为视频文件"""
    ext = Path(file_path).suffix.lower()
    return ext in VIDEO_EXTENSIONS


def get_video_files(folder_path: str) -> List[str]:
    """
    获取文件夹下所有视频文件

    Args:
        folder_path: 文件夹路径

    Returns:
        视频文件路径列表
    """
    files = []
    try:
        p = Path(folder_path)
        if not p.exists():
            logger.warning(f"目录不存在: {folder_path}")
            return files

        for file_path in p.rglob('*'):
            if file_path.is_file() and is_video_file(str(file_path)):
                files.append(str(file_path))

    except Exception as e:
        logger.warning(f"遍历目录出错 {folder_path}: {e}")

    return files


def get_video_info(video_path: str) -> Optional[Dict]:
    """
    获取视频元信息

    Args:
        video_path: 视频文件路径

    Returns:
        包含时长、大小、格式等信息的字典
    """
    info = {
        'path': video_path,
        'filename': Path(video_path).name,
        'format': Path(video_path).suffix.lower(),
        'file_size': 0,
        'duration': 0.0,
        'frame_count': 0,
        'fps': 0.0,
        'width': 0,
        'height': 0
    }

    try:
        # 获取文件大小
        info['file_size'] = os.path.getsize(video_path)
    except:
        pass

    if not HAS_CV2:
        # 尝试使用 ffprobe
        return _get_video_info_ffprobe(video_path, info)

    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.warning(f"无法打开视频: {video_path}")
            return _get_video_info_ffprobe(video_path, info)

        # 获取基本信息
        info['frame_count'] = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        info['fps'] = cap.get(cv2.CAP_PROP_FPS)
        info['width'] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        info['height'] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # 计算时长
        if info['fps'] > 0 and info['frame_count'] > 0:
            info['duration'] = info['frame_count'] / info['fps']

        cap.release()

    except Exception as e:
        logger.warning(f"获取视频信息失败 {video_path}: {e}")
        return _get_video_info_ffprobe(video_path, info)

    return info


def _get_video_info_ffprobe(video_path: str, info: Dict) -> Optional[Dict]:
    """使用 ffprobe 获取视频信息"""
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            video_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return info

        data = json.loads(result.stdout)

        # 从 format 获取时长
        if 'format' in data:
            info['duration'] = float(data['format'].get('duration', 0))

        # 从 streams 获取帧数和分辨率
        if 'streams' in data:
            for stream in data['streams']:
                if stream.get('codec_type') == 'video':
                    info['width'] = int(stream.get('width', 0))
                    info['height'] = int(stream.get('height', 0))
                    info['fps'] = eval(stream.get('r_frame_rate', '0/1'))
                    if 'nb_frames' in stream:
                        info['frame_count'] = int(stream['nb_frames'])
                    break

    except Exception as e:
        logger.warning(f"ffprobe获取信息失败 {video_path}: {e}")

    return info


def sample_frames(video_path: str, max_frames: int = 20) -> List:
    """
    从视频中均匀采样帧

    Args:
        video_path: 视频文件路径
        max_frames: 最大采样帧数

    Returns:
        帧图像列表 (RGB格式 numpy数组，如果没有numpy则返回原始帧)
    """
    frames = []

    if not HAS_CV2:
        logger.warning("cv2未安装，无法采样帧")
        return frames

    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.warning(f"无法打开视频: {video_path}")
            return frames

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if total_frames <= 0:
            cap.release()
            return frames

        # 计算采样索引
        if total_frames <= max_frames:
            # 短视频：采样所有帧
            sample_indices = list(range(total_frames))
        else:
            # 长视频：均匀采样，确保覆盖开头、中间、结尾
            if HAS_NUMPY:
                sample_indices = np.linspace(0, total_frames - 1, max_frames, dtype=int)
            else:
                # 手动计算均匀采样索引
                step = total_frames / max_frames
                sample_indices = [int(i * step) for i in range(max_frames)]

        for idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ret, frame = cap.read()
            if ret:
                # 转换为RGB格式
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frames.append(frame_rgb)

        cap.release()

    except Exception as e:
        logger.warning(f"采样帧失败 {video_path}: {e}")

    return frames


def sample_frames_by_interval(video_path: str, interval_seconds: float = 5.0) -> List[np.ndarray]:
    """
    按时间间隔采样帧

    Args:
        video_path: 视频文件路径
        interval_seconds: 采样间隔（秒）

    Returns:
        帧图像列表
    """
    frames = []

    if not HAS_CV2:
        logger.warning("cv2未安装，无法采样帧")
        return frames

    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.warning(f"无法打开视频: {video_path}")
            return frames

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if fps <= 0 or total_frames <= 0:
            cap.release()
            return frames

        # 计算采样帧间隔
        frame_interval = int(fps * interval_seconds)

        for pos in range(0, total_frames, frame_interval):
            cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
            ret, frame = cap.read()
            if ret:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frames.append(frame_rgb)

        cap.release()

    except Exception as e:
        logger.warning(f"按间隔采样帧失败 {video_path}: {e}")

    return frames


def resize_frame(frame, target_size: Tuple[int, int] = (256, 256)):
    """
    缩放帧到目标大小

    Args:
        frame: 原始帧
        target_size: 目标大小

    Returns:
        缩放后的帧
    """
    if not HAS_CV2:
        # 使用 numpy 简单缩放
        if HAS_NUMPY:
            h, w = frame.shape[:2]
            target_h, target_w = target_size
            # 简单的最近邻插值
            ratio_h = h / target_h
            ratio_w = w / target_w
            indices_h = (np.arange(target_h) * ratio_h).astype(int)
            indices_w = (np.arange(target_w) * ratio_w).astype(int)
            return frame[indices_h][:, indices_w]
        else:
            # 无法缩放，返回原始帧
            return frame

    return cv2.resize(frame, target_size, interpolation=cv2.INTER_AREA)


def format_duration(seconds: float) -> str:
    """格式化时长显示"""
    if seconds <= 0:
        return "未知"

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小显示"""
    if size_bytes <= 0:
        return "未知"

    units = ['B', 'KB', 'MB', 'GB', 'TB']
    size = float(size_bytes)
    unit_index = 0

    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    if unit_index >= 2:  # MB及以上保留两位小数
        return f"{size:.2f} {units[unit_index]}"
    else:
        return f"{size:.1f} {units[unit_index]}"
