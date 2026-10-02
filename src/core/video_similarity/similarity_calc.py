#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
相似度计算模块 - 两阶段相似度计算
"""
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None

from typing import List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from db.models import VideoSimilarityVideo
from core.video_similarity.feature_extractor import FeatureExtractor
from utils.logger import logger


class SimilarityCalculator:
    """相似度计算器"""

    # 两阶段计算阈值
    PHASH_THRESHOLD = 0.7  # pHash阈值，高于此值才进行CLIP计算
    PHASH_WEIGHT = 0.4     # pHash权重
    CLIP_WEIGHT = 0.6      # CLIP权重

    def __init__(self):
        self.feature_extractor = FeatureExtractor()

    @staticmethod
    def _video_identity(video: VideoSimilarityVideo):
        """生成视频去重标识，避免同一对象被重复参与计算。"""
        if video.id is not None:
            return ("id", video.id)
        return ("path", video.path)

    def _deduplicate_videos(self, videos: List[VideoSimilarityVideo]) -> List[VideoSimilarityVideo]:
        """按视频 ID/路径去重，避免产生自比对或重复结果。"""
        unique_videos: List[VideoSimilarityVideo] = []
        seen = set()

        for video in videos:
            identity = self._video_identity(video)
            if identity in seen:
                continue
            seen.add(identity)
            unique_videos.append(video)

        return unique_videos

    def calculate_similarity(self, video_a: VideoSimilarityVideo, video_b: VideoSimilarityVideo) -> float:
        """
        计算两个视频的相似度

        Args:
            video_a: 视频A
            video_b: 视频B

        Returns:
            相似度分数 (0-100)
        """
        # 反序列化特征
        hashes_a, clip_a = self._get_features(video_a)
        hashes_b, clip_b = self._get_features(video_b)

        if not hashes_a and not hashes_b:
            # 无法计算
            return 0.0

        # 第一阶段：pHash快速比对
        phash_score = FeatureExtractor.compute_phash_similarity_batch(hashes_a, hashes_b)

        if phash_score < self.PHASH_THRESHOLD:
            # pHash相似度低，直接返回pHash分数
            return phash_score * 100

        # 第二阶段：CLIP精确比对
        clip_score = FeatureExtractor.compute_clip_similarity(clip_a, clip_b)

        # 加权融合
        final_score = self.PHASH_WEIGHT * phash_score + self.CLIP_WEIGHT * clip_score

        return final_score * 100

    def _get_features(self, video: VideoSimilarityVideo) -> Tuple[List[str], Optional[np.ndarray]]:
        """从视频对象获取特征"""
        if video.phash_features is None:
            return [], video.clip_features

        # 如果已经是 numpy 数组，直接返回
        if isinstance(video.phash_features, list):
            return video.phash_features, video.clip_features

        # 反序列化
        try:
            if isinstance(video.phash_features, bytes):
                hashes, clip = FeatureExtractor.deserialize_features(video.phash_features)
                return hashes, clip
            elif video.clip_features is not None and isinstance(video.clip_features, bytes):
                hashes, clip = FeatureExtractor.deserialize_features(video.clip_features)
                return hashes, clip
        except:
            pass

        return [], None

    def calculate_all_similarities(
        self,
        videos: List[VideoSimilarityVideo],
        min_score: float = 0.0,
        max_workers: int = 4,
        progress_callback: Optional[callable] = None
    ) -> List[Dict]:
        """
        批量计算所有视频对的相似度

        Args:
            videos: 视频列表
            min_score: 最小相似度阈值（低于此值不返回）
            max_workers: 并行工作线程数
            progress_callback: 进度回调函数

        Returns:
            相似度结果列表 [{"video_a_id": x, "video_b_id": y, "score": z}]
        """
        videos = self._deduplicate_videos(videos)
        n = len(videos)
        total_pairs = n * (n - 1) // 2
        results = []
        processed = 0

        logger.info(f"开始计算 {n} 个视频的相似度，共 {total_pairs} 对")

        # 先计算所有pHash相似度
        phash_results = []

        for i in range(n):
            for j in range(i + 1, n):
                video_a = videos[i]
                video_b = videos[j]

                if self._video_identity(video_a) == self._video_identity(video_b):
                    continue

                hashes_a, _ = self._get_features(video_a)
                hashes_b, _ = self._get_features(video_b)

                phash_score = FeatureExtractor.compute_phash_similarity_batch(hashes_a, hashes_b)

                phash_results.append({
                    'video_a_id': video_a.id,
                    'video_b_id': video_b.id,
                    'video_a': video_a,
                    'video_b': video_b,
                    'phash_score': phash_score
                })

        # 对pHash相似度高的进行CLIP计算
        high_phash_pairs = [r for r in phash_results if r['phash_score'] >= self.PHASH_THRESHOLD]
        low_phash_pairs = [r for r in phash_results if r['phash_score'] < self.PHASH_THRESHOLD]

        # 处理低pHash相似度的对
        for r in low_phash_pairs:
            score = r['phash_score'] * 100
            if score >= min_score:
                results.append({
                    'video_a_id': r['video_a_id'],
                    'video_b_id': r['video_b_id'],
                    'similarity_score': score,
                    'method': 'phash_only'
                })

            processed += 1
            if progress_callback:
                progress_callback(processed, total_pairs)

        # 并行处理高pHash相似度的对
        def compute_clip_score(pair):
            _, clip_a = self._get_features(pair['video_a'])
            _, clip_b = self._get_features(pair['video_b'])

            clip_score = FeatureExtractor.compute_clip_similarity(clip_a, clip_b)

            final_score = self.PHASH_WEIGHT * pair['phash_score'] + self.CLIP_WEIGHT * clip_score
            return final_score * 100

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(compute_clip_score, pair): pair
                for pair in high_phash_pairs
            }

            for future in as_completed(futures):
                pair = futures[future]
                try:
                    score = future.result()
                    if score >= min_score:
                        results.append({
                            'video_a_id': pair['video_a_id'],
                            'video_b_id': pair['video_b_id'],
                            'similarity_score': score,
                            'method': 'phash_clip'
                        })
                except Exception as e:
                    logger.warning(f"CLIP计算失败: {e}")
                    # 使用pHash分数作为fallback
                    score = pair['phash_score'] * 100
                    if score >= min_score:
                        results.append({
                            'video_a_id': pair['video_a_id'],
                            'video_b_id': pair['video_b_id'],
                            'similarity_score': score,
                            'method': 'phash_fallback'
                        })

                processed += 1
                if progress_callback:
                    progress_callback(processed, total_pairs)

        # 按相似度排序
        results.sort(key=lambda x: x['similarity_score'], reverse=True)

        logger.info(f"相似度计算完成，返回 {len(results)} 对结果")

        return results

    def calculate_incremental(
        self,
        existing_videos: List[VideoSimilarityVideo],
        new_video: VideoSimilarityVideo,
        min_score: float = 0.0
    ) -> List[Dict]:
        """
        增量计算新视频与现有视频的相似度

        Args:
            existing_videos: 现有视频列表
            new_video: 新添加的视频
            min_score: 最小相似度阈值

        Returns:
            相似度结果列表
        """
        results = []

        hashes_new, clip_new = self._get_features(new_video)

        for existing in existing_videos:
            hashes_exist, clip_exist = self._get_features(existing)

            # pHash比对
            phash_score = FeatureExtractor.compute_phash_similarity_batch(hashes_new, hashes_exist)

            if phash_score < self.PHASH_THRESHOLD:
                score = phash_score * 100
            else:
                # CLIP精确比对
                clip_score = FeatureExtractor.compute_clip_similarity(clip_new, clip_exist)
                score = (self.PHASH_WEIGHT * phash_score + self.CLIP_WEIGHT * clip_score) * 100

            if score >= min_score:
                results.append({
                    'video_a_id': new_video.id,
                    'video_b_id': existing.id,
                    'similarity_score': score
                })

        # 排序
        results.sort(key=lambda x: x['similarity_score'], reverse=True)

        return results


# 默认相似度计算器实例
similarity_calculator = SimilarityCalculator()
