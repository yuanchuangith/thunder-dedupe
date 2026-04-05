#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test specific file names from user
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.av_parser import AVParser

def test_user_files():
    parser = AVParser()

    test_files = [
        "hhd800.com@MOOC-018.mp4",
        "hhd800.com@APPT-003.mp4",
        "hhd800.com@SAL-262.mp4",
        "TCD-318.mp4",
        "77vr.com@lulu-330.restored.mp4",
        "ADHN-021.restored.mp4",
        "BOKD-093.1080p.restored.mp4",
        "BOKD-196.restored.mp4",
        "77vr.com@lulu-330.mp4",
        "ADHN-021.mp4",
        "BOKD-093.1080p.mkv",
    ]

    print("=" * 60)
    print("Testing user file names")
    print("=" * 60)

    for filename in test_files:
        result = parser.parse_from_filename(filename)
        print(f"{filename}")
        print(f"  -> {result}")
        print()

if __name__ == "__main__":
    test_user_files()