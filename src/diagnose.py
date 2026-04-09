#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Diagnostic script for scanning issues
"""
import sys
import os
from pathlib import Path

# Add src directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db.database import db
from db.migrations.init_db import init_database
from utils.config import config


def check_database():
    """Check database status"""
    print("=" * 60)
    print("Database Check")
    print("=" * 60)

    # Initialize database
    init_database()

    # Check scan paths
    print("\nConfigured scan paths:")
    paths = db.query("SELECT id, path, enabled FROM scan_paths")
    if paths:
        for row in paths:
            exists = Path(row['path']).exists()
            status = "EXISTS" if exists else "NOT FOUND"
            print(f"  [{row['id']}] {row['path']} ({status})")
    else:
        print("  No paths configured!")

    # Check file index
    print("\nFile index status:")
    total = db.query_one("SELECT COUNT(*) as count FROM file_index")
    unique = db.query_one("SELECT COUNT(DISTINCT av_code) as count FROM file_index")
    print(f"  Total files: {total['count'] if total else 0}")
    print(f"  Unique codes: {unique['count'] if unique else 0}")

    # Show some indexed files
    print("\nSample indexed files (last 10):")
    samples = db.query("""
        SELECT av_code, original_name, file_path
        FROM file_index
        ORDER BY id DESC
        LIMIT 10
    """)
    for row in samples:
        print(f"  {row['av_code']}: {row['original_name']}")

    # Check parse rules
    print("\nParse rules:")
    rules = db.query("SELECT id, name, pattern, enabled FROM parse_rules")
    for row in rules:
        status = "ENABLED" if row['enabled'] else "DISABLED"
        print(f"  [{row['id']}] {row['name']}: {row['pattern']} ({status})")


def test_scan_path(path_str):
    """Test scanning a specific path"""
    print("\n" + "=" * 60)
    print(f"Testing path: {path_str}")
    print("=" * 60)

    path = Path(path_str)

    if not path.exists():
        print(f"Path does not exist: {path_str}")
        return

    print(f"Path exists: {path_str}")

    extensions = config.get_video_extensions() | config.get_temp_extensions()

    count = 0
    sample_files = []

    for file_path in path.rglob('*'):
        if file_path.is_file():
            ext = file_path.suffix.lower()
            if ext in extensions:
                count += 1
                if len(sample_files) < 5:
                    sample_files.append(str(file_path))

    print(f"Found {count} matching files")

    if sample_files:
        print("\nSample files:")
        for f in sample_files:
            print(f"  {f}")


if __name__ == "__main__":
    check_database()

    # Test some common paths
    test_paths = [
        "H:/迅雷下载",
        "D:/修复Video",
        "G:/迅雷下载/已解码",
    ]

    for p in test_paths:
        test_scan_path(p)
