#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test AV code parsing
"""
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.av_parser import AVParser
from utils.utils import normalize_av_code


def test_parse():
    """Test AV code parsing"""
    parser = AVParser()

    test_cases = [
        "MOOC-018",
        "MOOC018",
        "SXMA-016-HD.mp4",
        "TOTK015.mkv",
        "thunder://QUFodHRwOi8vZG93bmxvYWQvU1hNQS0wMTYubXA0Wlo=",
    ]

    print("=" * 50)
    print("AV Code Parsing Test")
    print("=" * 50)

    for case in test_cases:
        result = parser.parse(case)
        print(f"Input: {case}")
        print(f"Output: {result}")
        print("-" * 30)


def test_normalize():
    """Test normalization"""
    test_cases = [
        "mooc018",
        "MOOC-018",
        "MOOC018",
        "sxma-016",
        "SXMA016",
    ]

    print("\n" + "=" * 50)
    print("Normalization Test")
    print("=" * 50)

    for case in test_cases:
        result = normalize_av_code(case)
        print(f"{case} -> {result}")


if __name__ == "__main__":
    test_normalize()
    print("\n")
    test_parse()