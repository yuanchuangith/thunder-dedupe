#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
视频扫描器 - 扫描文件夹、提取特征、计算相似度
"""
import os
import threading
from pathlib import Path
from typing import List, Callable, Optional, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt6.QtCore import QObject, pyqtSignal

from db.database import db
from db.models import VideoSimilarityVideo
from core.video_similarity.video_utils import get_video_files, get_video_info, sample_frames
from core.video_similarity.feature_extractor import FeatureExtractor, feature_extractor
from core.video_similarity.similarity_calc import similarity_calculator
from utils.logger import logger


class VideoSimilarityScanner(QObject):
    """视频相似度扫描器"""

    # 信号定义
    scan_started = pyqtSignal()
    scan_progress = pyqtSignal(int, int, str)  # 已扫描, 总文件, 当前文件名
    scan_completed = pyqtSignal(int, int)  # 新增视频数, 总相似度对数
    similarity_progress = pyqtSignal(int, int)  # 已计算, 总对数
    scan_error = pyqtSignal(str)

    # 采样帧数配置
    DEFAULT_MAX_FRAMES = 20

    def __init__(self):
        super().__init__()
        self._scanning = False
        self._calculating = False
        self._stop_flag = False
        self._lock = threading.Lock()

        # 初始化CLIP模型
        self._clip_initialized = False

    def init_clip(self, device: Optional[str] = None) -> bool:
        """
        初始化CLIP模型

        Args:
            device: 运行设备 (cpu/cuda)，为空时自动选择

        Returns:
            是否成功初始化
        """
        if self._clip_initialized:
            return True

        self._clip_initialized = FeatureExtractor.init_clip(device=device)
        return self._clip_initialized

    def is_scanning(self) -> bool:
        """是否正在扫描"""
        return self._scanning

    def is_calculating(self) -> bool:
        """是否正在计算相似度"""
        return self._calculating

    def stop_scan(self):
        """停止扫描"""
        self._stop_flag = True

    def scan_folder(self, folder_path: str, callback: Optional[Callable] = None):
        """
        扫描单个文件夹

        Args:
            folder_path: 文件夹路径
            callback: 完成回调函数
        """
        self.scan_folders([folder_path], callback)

    def scan_folders(self, folder_paths: List[str], callback: Optional[Callable] = None):
        """
        扫描多个文件夹

        Args:
            folder_paths: 文件夹路径列表
            callback: 完成回调函数
        """
        if self._scanning or self._calculating:
            logger.warning("已有任务在进行")
            self.scan_error.emit("已有扫描任务在进行")
            return

        # 初始化CLIP
        if not self._clip_initialized:
            self.init_clip()

        # 在后台线程执行扫描
        thread = threading.Thread(
            target=self._scan_worker,
            args=(folder_paths, callback),
            daemon=True
        )
        thread.start()

    def _scan_worker(self, folder_paths: List[str], callback: Optional[Callable]):
        """扫描工作线程"""
        self._scanning = True
        self._stop_flag = False
        self.scan_started.emit()

        try:
            existing_videos = self._get_existing_videos()

            # 收集所有视频文件
            all_files = []
            for folder_path in folder_paths:
                if self._stop_flag:
                    break

                logger.info(f"正在扫描目录: {folder_path}")
                files = get_video_files(folder_path)
                logger.info(f"目录 {folder_path} 找到 {len(files)} 个视频文件")
                all_files.extend(files)

            # 去重，避免父子目录或重复路径导致同一文件被重复处理
            all_files = list(dict.fromkeys(all_files))

            total_files = len(all_files)
            logger.info(f"总计找到 {total_files} 个视频文件待处理")

            if total_files == 0:
                self._scanning = False
                self.scan_completed.emit(0, 0)
                if callback:
                    callback(0, 0)
                return

            # 并行处理视频
            new_videos = []
            processed = 0

            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {
                    executor.submit(self._process_video, f): f
                    for f in all_files
                }

                for future in as_completed(futures):
                    if self._stop_flag:
                        break

                    file_path = futures[future]
                    processed += 1

                    try:
                        video = future.result()
                        if video:
                            new_videos.append(video)
                    except Exception as e:
                        logger.warning(f"处理视频失败 {file_path}: {e}")

                    # 发送进度信号
                    filename = Path(file_path).name
                    self.scan_progress.emit(processed, total_files, filename)

            logger.info(f"扫描完成，新增 {len(new_videos)} 个视频，总计 {len(existing_videos) + len(new_videos)} 个")

            # 计算相似度
            self._scanning = False
            self._calculating = True

            total_similarities = self._calculate_and_save_similarities(existing_videos, new_videos)

            self._calculating = False

            # 发送完成信号
            self.scan_completed.emit(len(new_videos), total_similarities)

            if callback:
                callback(len(new_videos), total_similarities)

        except Exception as e:
            logger.error(f"扫描出错: {e}")
            self._scanning = False
            self._calculating = False
            self.scan_error.emit(str(e))

    def _process_video(self, video_path: str) -> Optional[VideoSimilarityVideo]:
        """
        处理单个视频：提取特征并保存到数据库

        Args:
            video_path: 视频文件路径

        Returns:
            视频对象
        """
        try:
            # 检查是否已存在
            existing = db.query_one(
                "SELECT id FROM video_similarity_videos WHERE path = ?",
                (video_path,)
            )

            if existing:
                # 已存在，跳过
                return None

            # 获取视频信息
            info = get_video_info(video_path)
            if not info:
                logger.warning(f"无法获取视频信息: {video_path}")
                return None

            # 采样帧
            frames = sample_frames(video_path, self.DEFAULT_MAX_FRAMES)
            if not frames:
                logger.warning(f"无法采样帧: {video_path}")
                return None

            # 提取特征
            phashes = FeatureExtractor.extract_phash_batch(frames)
            clip_feature = None

            if self._clip_initialized:
                clip_feature = FeatureExtractor.extract_clip_features(frames)

            # 序列化特征
            feature_data = FeatureExtractor.serialize_features(phashes, clip_feature)

            # 保存到数据库
            video_id = db.execute("""
                INSERT INTO video_similarity_videos
                (path, filename, duration, file_size, format, frame_count, phash_features, clip_features, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')
            """, (
                video_path,
                info['filename'],
                info['duration'],
                info['file_size'],
                info['format'],
                info['frame_count'],
                feature_data,
                feature_data  # clip_features存储在同一blob中
            ))

            # 创建视频对象
            video = VideoSimilarityVideo(
                id=video_id,
                path=video_path,
                filename=info['filename'],
                duration=info['duration'],
                file_size=info['file_size'],
                format=info['format'],
                frame_count=info['frame_count'],
                phash_features=feature_data,
                clip_features=feature_data,
                status='active'
            )

            return video

        except Exception as e:
            logger.warning(f"处理视频出错 {video_path}: {e}")
            return None

    def _get_existing_videos(self) -> List[VideoSimilarityVideo]:
        """获取数据库中已存在的视频"""
        rows = db.query("SELECT * FROM video_similarity_videos WHERE status = 'active'")
        return [VideoSimilarityVideo.from_row(row) for row in rows]

    def _calculate_and_save_similarities(
        self,
        existing_videos: List[VideoSimilarityVideo],
        new_videos: List[VideoSimilarityVideo]
    ) -> int:
        """
        计算相似度并保存到数据库

        Args:
            existing_videos: 已存在的视频列表
            new_videos: 新增的视频列表

        Returns:
            新增的相似度对数
        """
        if not new_videos:
            return 0

        total_pairs = len(existing_videos) * len(new_videos)
        total_pairs += len(new_videos) * (len(new_videos) - 1) // 2
        if total_pairs <= 0:
            return 0

        results = []
        processed_pairs = 0
        comparison_pool = list(existing_videos)

        for video in new_videos:
            results.extend(
                similarity_calculator.calculate_incremental(
                    comparison_pool,
                    video,
                    min_score=50.0
                )
            )
            processed_pairs += len(comparison_pool)
            self.similarity_progress.emit(processed_pairs, total_pairs)
            comparison_pool.append(video)

        # 清空旧的相似度结果（可选，根据需求调整）
        # db.execute("DELETE FROM video_similarity_results")

        # 保存结果
        saved_count = 0
        for result in results:
            try:
                video_a_id, video_b_id = sorted((result['video_a_id'], result['video_b_id']))
                if video_a_id == video_b_id:
                    continue

                # 检查是否已存在
                existing = db.query_one("""
                    SELECT id FROM video_similarity_results
                    WHERE video_a_id = ? AND video_b_id = ?
                """, (video_a_id, video_b_id))

                if not existing:
                    db.execute("""
                        INSERT INTO video_similarity_results
                        (video_a_id, video_b_id, similarity_score, status)
                        VALUES (?, ?, ?, 'pending')
                    """, (
                        video_a_id,
                        video_b_id,
                        result['similarity_score']
                    ))
                    saved_count += 1

            except Exception as e:
                logger.warning(f"保存相似度结果失败: {e}")

        logger.info(f"保存了 {saved_count} 条相似度结果")

        return saved_count

    def get_similarity_results(self, min_score: float = 0.0) -> List[Dict]:
        """
        获取相似度结果

        Args:
            min_score: 最小相似度阈值

        Returns:
            相似度结果列表
        """
        rows = db.query("""
            SELECT
                r.id, r.video_a_id, r.video_b_id, r.similarity_score, r.status,
                a.path as video_a_path, a.filename as video_a_filename,
                a.duration as video_a_duration, a.file_size as video_a_size,
                b.path as video_b_path, b.filename as video_b_filename,
                b.duration as video_b_duration, b.file_size as video_b_size
            FROM video_similarity_results r
            JOIN video_similarity_videos a ON r.video_a_id = a.id
            JOIN video_similarity_videos b ON r.video_b_id = b.id
            WHERE r.similarity_score >= ?
              AND r.video_a_id != r.video_b_id
              AND a.status = 'active'
              AND b.status = 'active'
            ORDER BY r.similarity_score DESC
        """, (min_score,))

        return [dict(row) for row in rows]

    def get_video_count(self) -> int:
        """获取视频总数"""
        result = db.query_one("SELECT COUNT(*) as count FROM video_similarity_videos WHERE status = 'active'")
        return result['count'] if result else 0

    def get_similarity_count(self) -> int:
        """获取相似度对总数"""
        result = db.query_one("SELECT COUNT(*) as count FROM video_similarity_results")
        return result['count'] if result else 0

    def update_similarity_status(self, similarity_id: int, status: str):
        """
        更新相似度状态

        Args:
            similarity_id: 相似度记录ID
            status: 新状态 (pending/confirmed_duplicate/kept)
        """
        db.execute(
            "UPDATE video_similarity_results SET status = ? WHERE id = ?",
            (status, similarity_id)
        )
        logger.info(f"更新相似度状态: ID={similarity_id}, status={status}")

    def delete_video(self, video_id: int) -> bool:
        """
        删除视频（标记为deleted）

        Args:
            video_id: 视频ID

        Returns:
            是否成功
        """
        try:
            # 获取视频路径
            video = db.query_one("SELECT path FROM video_similarity_videos WHERE id = ?", (video_id,))
            if not video:
                return False

            # 删除文件（可选）
            # path = Path(video['path'])
            # if path.exists():
            #     path.unlink()

            # 更新状态为deleted
            db.execute("UPDATE video_similarity_videos SET status = 'deleted' WHERE id = ?", (video_id,))
            db.execute("DELETE FROM video_similarity_results WHERE video_a_id = ? OR video_b_id = ?", (video_id, video_id))

            logger.info(f"删除视频: ID={video_id}")
            return True

        except Exception as e:
            logger.error(f"删除视频失败: {e}")
            return False

    def clear_all_data(self):
        """清空所有数据"""
        db.execute("DELETE FROM video_similarity_results")
        db.execute("DELETE FROM video_similarity_videos")
        db.execute("DELETE FROM video_similarity_paths")
        logger.info("已清空所有视频相似度数据")


# 全局扫描器实例
video_similarity_scanner = VideoSimilarityScanner()
