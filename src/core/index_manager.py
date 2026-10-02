#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Index manager for current files and file history lookups.
"""
from pathlib import Path
from typing import Dict, List, Optional

from core.av_parser import AVParser
from db.database import db
from utils.logger import logger
from utils.utils import format_file_size, normalize_av_code


class IndexManager:
    """Manage search/index operations for file_index and file_history."""

    def __init__(self):
        self._parser = AVParser()

    def search(self, av_code: str) -> Optional[Dict]:
        """
        Search an AV code.

        Lookup order:
        1. file_index: current files only, and only when the path still exists
        2. file_history: fallback for history-only results
        """
        normalized = normalize_av_code(av_code)

        index_result = self._find_active_index_result(normalized)
        if index_result:
            logger.debug(f"AV code {normalized} found in file_index")
            return index_result

        history_result = self._find_history_result(normalized)
        if history_result:
            logger.debug(
                f"AV code {normalized} found in file_history, "
                f"status={history_result.get('history_status')}"
            )
            return history_result

        logger.debug(f"AV code {normalized} not found")
        return None

    def refresh_search_index(self):
        """Rebuild the derived search_index table."""
        self._ensure_search_index_table()
        db.execute("DELETE FROM search_index")

        db.execute(
            """
            INSERT INTO search_index (
                av_code, original_name, file_path, file_size,
                source, status, priority, created_at
            )
            SELECT
                av_code,
                original_name,
                file_path,
                file_size,
                'file_index',
                'normal',
                300,
                created_at
            FROM file_index
            """
        )

        db.execute(
            """
            INSERT INTO search_index (
                av_code, original_name, file_path, file_size,
                source, status, priority, created_at
            )
            SELECT
                fh.av_code,
                fh.filename,
                fh.file_path,
                fh.file_size,
                'file_history',
                fh.status,
                CASE WHEN fh.status = 'normal' THEN 200 ELSE 100 END,
                COALESCE(fh.last_seen_at, fh.first_seen_at)
            FROM file_history fh
            WHERE NOT EXISTS (
                SELECT 1
                FROM file_index fi
                WHERE fi.av_code = fh.av_code
                  AND fi.file_path = fh.file_path
            )
            """
        )

        total = db.query_one("SELECT COUNT(*) as count FROM search_index")
        total_count = total["count"] if total else 0
        logger.info(f"Search index refreshed, total={total_count}")

    def search_all_matches(self, av_code: str) -> List[Dict]:
        """Return all file_index matches for an AV code."""
        normalized = normalize_av_code(av_code)

        rows = db.query(
            """
            SELECT id, av_code, original_name, file_path, file_size, created_at
            FROM file_index
            WHERE av_code = ?
            ORDER BY file_size DESC
            """,
            (normalized,),
        )

        results = []
        for row in rows:
            results.append(
                {
                    "id": row["id"],
                    "av_code": row["av_code"],
                    "original_name": row["original_name"],
                    "file_path": row["file_path"],
                    "file_size": row["file_size"],
                    "file_size_display": format_file_size(row["file_size"] or 0),
                    "created_at": row["created_at"],
                }
            )

        return results

    def _ensure_search_index_table(self):
        """Create search_index for legacy databases that do not have it yet."""
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS search_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                av_code TEXT NOT NULL,
                original_name TEXT,
                file_path TEXT NOT NULL,
                file_size INTEGER,
                source TEXT NOT NULL,
                status TEXT DEFAULT 'normal',
                priority INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_search_index_av_code
            ON search_index(av_code)
            """
        )

    def _find_active_index_result(self, normalized: str) -> Optional[Dict]:
        """
        Return the best live file_index match.

        Stale file_index rows are ignored so history can still be returned.
        """
        rows = db.query(
            """
            SELECT id, av_code, original_name, file_path, file_size, created_at
            FROM file_index
            WHERE av_code = ?
            ORDER BY file_size DESC, created_at DESC
            """,
            (normalized,),
        )

        stale_count = 0
        for row in rows:
            file_path = row["file_path"]
            if file_path and Path(file_path).exists():
                return self._build_index_result(row)
            stale_count += 1

        if stale_count:
            logger.debug(
                f"AV code {normalized} has {stale_count} stale file_index rows; "
                "falling back to file_history"
            )

        return None

    def _find_history_result(self, normalized: str) -> Optional[Dict]:
        """Return the best file_history match for an AV code."""
        row = db.query_one(
            """
            SELECT id, av_code, filename, file_path, file_size, status,
                   first_seen_at, last_seen_at, deleted_at
            FROM file_history
            WHERE av_code = ?
            ORDER BY status = 'normal' DESC,
                     file_size DESC,
                     COALESCE(last_seen_at, first_seen_at) DESC
            LIMIT 1
            """,
            (normalized,),
        )

        if not row:
            return None

        return self._build_history_result(row)

    def _build_index_result(self, row) -> Dict:
        """Build a normalized search result from file_index."""
        return {
            "id": row["id"],
            "av_code": row["av_code"],
            "original_name": row["original_name"],
            "file_path": row["file_path"],
            "file_size": row["file_size"],
            "file_size_display": format_file_size(row["file_size"] or 0),
            "created_at": row["created_at"],
            "match_source": "file_index",
            "history_status": "normal",
            "is_deleted": False,
        }

    def _build_search_index_result(self, row) -> Dict:
        """Build a normalized search result from search_index."""
        history_status = row["status"] or "normal"
        match_source = row["source"] or "file_index"
        return {
            "id": row["id"],
            "av_code": row["av_code"],
            "original_name": row["original_name"],
            "file_path": row["file_path"],
            "file_size": row["file_size"],
            "file_size_display": format_file_size(row["file_size"] or 0),
            "created_at": row["created_at"],
            "match_source": match_source,
            "history_status": history_status,
            "is_deleted": match_source == "file_history"
            and history_status == "deleted",
        }

    def _build_history_result(self, row) -> Dict:
        """Build a normalized search result from file_history."""
        history_status = row["status"] or "normal"
        return {
            "id": row["id"],
            "av_code": row["av_code"],
            "original_name": row["filename"],
            "file_path": row["file_path"],
            "file_size": row["file_size"],
            "file_size_display": format_file_size(row["file_size"] or 0),
            "created_at": row["last_seen_at"] or row["first_seen_at"],
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
            "deleted_at": row["deleted_at"],
            "match_source": "file_history",
            "history_status": history_status,
            "is_deleted": history_status == "deleted",
        }

    def add_index(self, file_path: str) -> bool:
        """Add one file into file_index."""
        try:
            path = Path(file_path)
            if not path.exists():
                logger.warning(f"File does not exist: {file_path}")
                return False

            filename = path.name
            av_code = self._parser.parse_from_filename(filename)
            if not av_code:
                logger.debug(f"Unable to parse AV code: {filename}")
                return False

            file_size = path.stat().st_size
            existing = db.query_one(
                "SELECT id FROM file_index WHERE av_code = ? AND file_path = ?",
                (av_code, file_path),
            )

            if existing:
                logger.debug(f"Index already exists: {av_code}")
                return False

            db.execute(
                """
                INSERT INTO file_index (av_code, original_name, file_path, file_size)
                VALUES (?, ?, ?, ?)
                """,
                (av_code, filename, file_path, file_size),
            )

            self.refresh_search_index()
            logger.info(f"Index added: {av_code} -> {filename}")
            return True

        except Exception as exc:
            logger.error(f"Failed to add index: {exc}")
            return False

    def remove_index(self, index_id: int) -> bool:
        """Remove a file_index row by id."""
        try:
            db.execute("DELETE FROM file_index WHERE id = ?", (index_id,))
            self.refresh_search_index()
            return True
        except Exception as exc:
            logger.error(f"Failed to remove index: {exc}")
            return False

    def remove_by_path(self, file_path: str) -> bool:
        """Remove a file_index row by file path."""
        try:
            db.execute("DELETE FROM file_index WHERE file_path = ?", (file_path,))
            self.refresh_search_index()
            return True
        except Exception as exc:
            logger.error(f"Failed to remove index by path: {exc}")
            return False

    def update_index(self, file_path: str) -> bool:
        """Refresh a file_index row when the file changes."""
        self.remove_by_path(file_path)
        return self.add_index(file_path)

    def clear_all(self):
        """Clear all current indexes."""
        db.execute("DELETE FROM file_index")
        self.refresh_search_index()
        logger.info("All indexes cleared")

    def get_stats(self) -> Dict:
        """Return file_index statistics."""
        total = db.query_one("SELECT COUNT(*) as count FROM file_index")
        unique_codes = db.query_one("SELECT COUNT(DISTINCT av_code) as count FROM file_index")
        recent = db.query(
            """
            SELECT av_code, original_name, created_at
            FROM file_index
            ORDER BY created_at DESC
            LIMIT 10
            """
        )

        return {
            "total_files": total["count"] if total else 0,
            "unique_codes": unique_codes["count"] if unique_codes else 0,
            "recent": recent,
        }

    def check_file_exists(self, file_path: str) -> bool:
        """Return whether a file still exists on disk."""
        return Path(file_path).exists()

    def verify_indexes(self) -> Dict:
        """Validate file_index paths against the filesystem."""
        rows = db.query("SELECT id, file_path FROM file_index")

        valid_count = 0
        invalid_count = 0
        invalid_ids = []

        for row in rows:
            if Path(row["file_path"]).exists():
                valid_count += 1
            else:
                invalid_count += 1
                invalid_ids.append(row["id"])

        return {
            "valid": valid_count,
            "invalid": invalid_count,
            "invalid_ids": invalid_ids,
        }

    def cleanup_invalid(self) -> int:
        """Delete invalid file_index rows."""
        result = self.verify_indexes()

        for index_id in result["invalid_ids"]:
            db.execute("DELETE FROM file_index WHERE id = ?", (index_id,))

        self.refresh_search_index()
        logger.info(f"Cleaned up {result['invalid']} invalid indexes")
        return result["invalid"]


index_manager = IndexManager()
