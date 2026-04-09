#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AV code parsing engine.
"""
import re
from typing import List, Optional, Tuple

from db.database import db
from utils.config import config
from utils.logger import logger
from utils.utils import normalize_av_code


class AVParser:
    """AV code parser."""

    THUNDER_LINK_PATTERNS = [
        r"^thunder://[A-Za-z0-9+/=]+",
        r"^magnet:\?xt=urn:btih:[A-Za-z0-9]+",
        r"^ed2k://\|file\|[^|]+\|\d+\|[A-Za-z0-9]+\|/",
    ]

    def __init__(self):
        self._rules = self._load_rules()

    def _load_rules(self) -> List[Tuple[str, int]]:
        """Load parse rules from the database."""
        rows = db.query(
            """
            SELECT pattern, priority, enabled
            FROM parse_rules
            WHERE enabled = 1
            ORDER BY priority DESC
            """
        )
        return [(row["pattern"], row["priority"]) for row in rows]

    def parse(self, text: str) -> Optional[str]:
        """Parse an AV code from free text."""
        if not text:
            return None

        decoded_text = self._decode_thunder_link(text)
        if decoded_text:
            text = decoded_text

        for pattern, _ in self._rules:
            try:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return normalize_av_code(match.group(0))
            except re.error as exc:
                logger.warning(f"正则规则错误: {pattern}, {exc}")

        builtin_patterns = [
            r"[A-Z]{2,6}-\d{3,5}",
            r"[A-Z]{2,6}\d{3,5}",
            r"[A-Z]{3,6}-\d{2,4}",
            r"[A-Z]{2,5}[-_]?\d{3,4}",
        ]

        for pattern in builtin_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return normalize_av_code(match.group(0))

        return None

    def _decode_thunder_link(self, link: str) -> Optional[str]:
        """Decode thunder/magnet/ed2k links into filenames when possible."""
        import base64

        for pattern in self.THUNDER_LINK_PATTERNS:
            if not re.match(pattern, link):
                continue

            try:
                if link.startswith("thunder://"):
                    encoded = link.replace("thunder://", "")
                    decoded = base64.b64decode(encoded).decode("utf-8", errors="ignore")
                    return decoded.replace("AA", "").replace("ZZ", "")

                if link.startswith("magnet:"):
                    dn_match = re.search(r"dn=([^&]+)", link)
                    if dn_match:
                        from urllib.parse import unquote

                        return unquote(dn_match.group(1))

                if link.startswith("ed2k://"):
                    parts = link.split("|")
                    if len(parts) >= 4:
                        return parts[2]
            except Exception as exc:
                logger.warning(f"解码链接失败: {exc}")
            return None

        return None

    def is_download_link(self, text: str) -> bool:
        """Return whether the text is a supported download link."""
        return any(re.match(pattern, text) for pattern in self.THUNDER_LINK_PATTERNS)

    def parse_from_filename(self, filename: str) -> Optional[str]:
        """Parse an AV code from a filename."""
        name = filename
        temp_exts = [ext.lstrip(".") for ext in config.get_temp_extensions()]
        video_exts = [ext.lstrip(".") for ext in config.get_video_extensions()]

        if temp_exts:
            temp_pattern = r"\.(" + "|".join(temp_exts) + r")(\.\w+)?$"
            name = re.sub(temp_pattern, "", name, flags=re.IGNORECASE)

        if video_exts:
            video_pattern = r"\.(" + "|".join(video_exts) + r")$"
            name = re.sub(video_pattern, "", name, flags=re.IGNORECASE)

        preserved_prefixes = []
        while True:
            bracket_match = re.match(r"^\[([^\]]+)\]\s*", name)
            if not bracket_match:
                break

            bracket_content = bracket_match.group(1).strip()
            parsed_bracket_code = self.parse(bracket_content)
            if parsed_bracket_code:
                preserved_prefixes.append(parsed_bracket_code)

            name = name[bracket_match.end() :]

        if preserved_prefixes:
            name = " ".join(preserved_prefixes + [name]).strip()

        name = re.sub(r"^[a-z0-9.-]+@", "", name, flags=re.IGNORECASE)

        noise_words = [
            "uncensored",
            "hd",
            "fhd",
            "4k",
            "1080p",
            "720p",
            "subtitle",
            "sub",
            "chs",
            "cht",
            "jpn",
            "torrent",
            "download",
            "preview",
            "sample",
            "restored",
        ]

        clean_name = name
        for word in noise_words:
            clean_name = re.sub(r"\b" + word + r"\b", "", clean_name, flags=re.IGNORECASE)

        clean_name = re.sub(r"[._]+", " ", clean_name)
        return self.parse(clean_name)

    def refresh_rules(self):
        """Reload rules from the database."""
        self._rules = self._load_rules()
        logger.info("解析规则已刷新")

    def check_exists(self, av_code: str) -> Optional[dict]:
        """Return the indexed file for an AV code if present."""
        normalized = normalize_av_code(av_code)
        row = db.query_one(
            "SELECT av_code, original_name, file_path, file_size FROM file_index WHERE av_code = ?",
            (normalized,),
        )
        if not row:
            return None

        return {
            "av_code": row["av_code"],
            "original_name": row["original_name"],
            "file_path": row["file_path"],
            "file_size": row["file_size"],
        }
