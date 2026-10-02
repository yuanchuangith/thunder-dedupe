#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Focused tests for video similarity core behavior.
"""
import os
import sys
import unittest
import types
from uuid import uuid4
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault(
    "HF_HOME",
    str(Path(__file__).resolve().parent.parent / ".hf-cache"),
)

try:
    from PyQt6.QtCore import QObject, pyqtSignal  # type: ignore
except ModuleNotFoundError:
    class _DummySignal:
        def connect(self, *args, **kwargs):
            return None

        def emit(self, *args, **kwargs):
            return None

    qtcore_module = types.ModuleType("PyQt6.QtCore")
    qtcore_module.QObject = object
    qtcore_module.pyqtSignal = lambda *args, **kwargs: _DummySignal()

    pyqt6_module = types.ModuleType("PyQt6")
    pyqt6_module.QtCore = qtcore_module

    sys.modules["PyQt6"] = pyqt6_module
    sys.modules["PyQt6.QtCore"] = qtcore_module

from core.video_similarity.feature_extractor import FeatureExtractor
from core.video_similarity.similarity_calc import similarity_calculator
from core.video_similarity.scanner import VideoSimilarityScanner
from db.database import db
from db.migrations import init_database
from db.models import VideoSimilarityVideo


class VideoSimilarityTests(unittest.TestCase):
    def setUp(self):
        self._original_db_path = db.db_path
        self._workspace_root = Path(__file__).resolve().parent.parent
        self._db_path = self._workspace_root / f"tmp_test_video_similarity_{uuid4().hex}.db"
        db.db_path = self._db_path
        init_database()

    def tearDown(self):
        db.db_path = self._original_db_path
        if self._db_path.exists():
            self._db_path.unlink()

    def _create_video(self, path: str, hashes=None, clip=None) -> VideoSimilarityVideo:
        hashes = hashes or ["0" * 64]
        clip = clip if clip is not None else np.array([1.0, 0.0], dtype=np.float32)
        feature_data = FeatureExtractor.serialize_features(hashes, clip)
        video_id = db.execute(
            """
            INSERT INTO video_similarity_videos
            (path, filename, duration, file_size, format, frame_count, phash_features, clip_features, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')
            """,
            (path, Path(path).name, 60.0, 1024, ".mp4", 100, feature_data, feature_data),
        )
        return VideoSimilarityVideo(
            id=video_id,
            path=path,
            filename=Path(path).name,
            duration=60.0,
            file_size=1024,
            format=".mp4",
            frame_count=100,
            phash_features=feature_data,
            clip_features=feature_data,
            status="active",
        )

    def test_phash_similarity_respects_hash_length(self):
        hash1 = "0" * 64
        hash2 = "f" * 64

        similarity = FeatureExtractor.compute_phash_similarity(hash1, hash2)

        self.assertEqual(similarity, 0.0)

    def test_calculate_all_similarities_deduplicates_same_video(self):
        video = self._create_video("E:/videos/sample.mp4")
        duplicate_reference = VideoSimilarityVideo(
            id=video.id,
            path=video.path,
            filename=video.filename,
            duration=video.duration,
            file_size=video.file_size,
            format=video.format,
            frame_count=video.frame_count,
            phash_features=video.phash_features,
            clip_features=video.clip_features,
            status=video.status,
        )

        results = similarity_calculator.calculate_all_similarities(
            [video, duplicate_reference],
            min_score=0.0,
        )

        self.assertEqual(results, [])

    def test_scanner_saves_incremental_pairs_without_self_pairs(self):
        existing = self._create_video("E:/videos/existing.mp4")
        new_a = self._create_video("E:/videos/new_a.mp4")
        new_b = self._create_video("E:/videos/new_b.mp4")
        scanner = VideoSimilarityScanner()

        saved_count = scanner._calculate_and_save_similarities([existing], [new_a, new_b])

        rows = db.query(
            """
            SELECT video_a_id, video_b_id
            FROM video_similarity_results
            ORDER BY video_a_id, video_b_id
            """
        )

        self.assertEqual(saved_count, 3)
        self.assertEqual([(row["video_a_id"], row["video_b_id"]) for row in rows], [
            (existing.id, new_a.id),
            (existing.id, new_b.id),
            (new_a.id, new_b.id),
        ])


if __name__ == "__main__":
    unittest.main()
