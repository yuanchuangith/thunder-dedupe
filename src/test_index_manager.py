#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Focused tests for IndexManager search behavior.
"""
import os
import sys
import unittest
from uuid import uuid4
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.index_manager import index_manager
from db.database import db
from db.migrations import init_database


class IndexManagerSearchTests(unittest.TestCase):
    def setUp(self):
        self._original_db_path = db.db_path
        self._workspace_root = Path(__file__).resolve().parent.parent
        self._db_path = self._workspace_root / f"tmp_test_index_manager_{uuid4().hex}.db"
        self._live_file = None
        db.db_path = self._db_path
        init_database()

    def tearDown(self):
        db.db_path = self._original_db_path
        if self._live_file and self._live_file.exists():
            self._live_file.unlink()
        if self._db_path.exists():
            self._db_path.unlink()

    def test_search_returns_history_deleted_when_only_history_exists(self):
        db.execute(
            """
            INSERT INTO file_history (
                av_code, filename, file_path, file_size, status,
                first_seen_at, last_seen_at, deleted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "WAAA-177",
                "waaa-177.mp4",
                "Z:\\missing\\waaa-177.mp4",
                123,
                "deleted",
                "2026-04-08 20:46:57",
                "2026-04-09 19:39:12",
                "2026-04-09 19:39:12",
            ),
        )

        result = index_manager.search("waaa177")

        self.assertIsNotNone(result)
        self.assertEqual(result["match_source"], "file_history")
        self.assertEqual(result["history_status"], "deleted")
        self.assertTrue(result["is_deleted"])

    def test_search_ignores_stale_file_index_and_falls_back_to_history(self):
        db.execute(
            """
            INSERT INTO file_index (av_code, original_name, file_path, file_size)
            VALUES (?, ?, ?, ?)
            """,
            ("WAAA-177", "waaa-177.mp4", "Z:\\missing\\waaa-177.mp4", 456),
        )
        db.execute(
            """
            INSERT INTO file_history (
                av_code, filename, file_path, file_size, status,
                first_seen_at, last_seen_at, deleted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "WAAA-177",
                "waaa-177.mp4",
                "Z:\\missing\\waaa-177.mp4",
                456,
                "deleted",
                "2026-04-08 20:46:57",
                "2026-04-09 19:39:12",
                "2026-04-09 19:39:12",
            ),
        )

        result = index_manager.search("WAAA-177")

        self.assertIsNotNone(result)
        self.assertEqual(result["match_source"], "file_history")
        self.assertTrue(result["is_deleted"])

    def test_search_prefers_live_file_index_entries(self):
        self._live_file = self._workspace_root / f"tmp_live_{uuid4().hex}.mp4"
        self._live_file.write_text("ok", encoding="utf-8")

        db.execute(
            """
            INSERT INTO file_index (av_code, original_name, file_path, file_size)
            VALUES (?, ?, ?, ?)
            """,
            ("WAAA-177", self._live_file.name, str(self._live_file), 789),
        )
        db.execute(
            """
            INSERT INTO file_history (
                av_code, filename, file_path, file_size, status,
                first_seen_at, last_seen_at, deleted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "WAAA-177",
                "waaa-177-old.mp4",
                "Z:\\missing\\waaa-177-old.mp4",
                123,
                "deleted",
                "2026-04-08 20:46:57",
                "2026-04-09 19:39:12",
                "2026-04-09 19:39:12",
            ),
        )

        result = index_manager.search("WAAA-177")

        self.assertIsNotNone(result)
        self.assertEqual(result["match_source"], "file_index")
        self.assertEqual(result["file_path"], str(self._live_file))
        self.assertFalse(result["is_deleted"])

    def test_refresh_search_index_recreates_missing_table(self):
        db.execute("DROP TABLE search_index")
        db.execute(
            """
            INSERT INTO file_index (av_code, original_name, file_path, file_size)
            VALUES (?, ?, ?, ?)
            """,
            ("WAAA-177", "waaa-177.mp4", "Z:\\missing\\waaa-177.mp4", 456),
        )

        index_manager.refresh_search_index()

        count_row = db.query_one("SELECT COUNT(*) as count FROM search_index")
        self.assertIsNotNone(count_row)
        self.assertEqual(count_row["count"], 1)


if __name__ == "__main__":
    unittest.main()
