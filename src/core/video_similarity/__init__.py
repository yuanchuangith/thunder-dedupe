#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
视频相似度检测核心模块
"""
from core.video_similarity.video_utils import (
    get_video_files,
    get_video_info,
    sample_frames,
    is_video_file,
    VIDEO_EXTENSIONS,
    format_duration,
    format_file_size
)
from core.video_similarity.feature_extractor import (
    FeatureExtractor,
    feature_extractor
)
from core.video_similarity.similarity_calc import (
    SimilarityCalculator,
    similarity_calculator
)
from core.video_similarity.scanner import (
    VideoSimilarityScanner,
    video_similarity_scanner
)

__all__ = [
    'get_video_files',
    'get_video_info',
    'sample_frames',
    'is_video_file',
    'VIDEO_EXTENSIONS',
    'format_duration',
    'format_file_size',
    'FeatureExtractor',
    'feature_extractor',
    'SimilarityCalculator',
    'similarity_calculator',
    'VideoSimilarityScanner',
    'video_similarity_scanner'
]