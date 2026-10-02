#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Runtime overrides for DecodePage.
"""
from __future__ import annotations

import codecs
import locale
import subprocess
import tempfile
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from db.database import db
from ui.decode_page import DecodePage
from ui.dual_video_window import DualVideoCompareWindow
from utils.utils import format_file_size
from utils.logger import logger

_OVERRIDES_APPLIED = False
_ORIGINAL_INIT = DecodePage.__init__


class _QueueImportWorker(QObject):
    started = pyqtSignal(str)
    progress = pyqtSignal(int, int, str)
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, page: DecodePage, import_root: str | None = None, file_paths: list[str] | None = None):
        super().__init__()
        self._page = page
        self._import_root = (import_root or "").strip()
        self._file_paths = list(file_paths or [])

    def run(self):
        try:
            files, source_root_resolver = self._prepare_files()
            if not files:
                self.failed.emit("没有找到可导入的视频文件。")
                return

            self.started.emit("正在建立导入索引...")

            configured_decoded_paths = self._page._get_enabled_compare_paths("decoded")
            use_configured_paths = bool(configured_decoded_paths)
            decoded_compare_index = self._page._build_decoded_compare_index() if use_configured_paths else {}
            task_compare_index = {} if use_configured_paths else self._page._build_decode_task_compare_index()

            inserted_count = 0
            low_resolution_count = 0
            suspected_count = 0
            existing_count = 0
            total_files = len(files)

            for index, file_path in enumerate(files, start=1):
                self.progress.emit(index - 1, total_files, file_path.name)

                source_root = str(source_root_resolver(file_path))
                linked_decoded_path = self._page._resolve_compare_match(
                    file_path,
                    decoded_compare_index,
                    task_compare_index,
                    use_configured_paths,
                )
                width, height, resolution = _get_task_resolution(self._page, file_path)
                is_low_resolution = self._page._is_low_resolution(height)
                db_record_path, db_record_source = self._page._lookup_database_record(file_path)
                next_status = _determine_queue_status(self._page, linked_decoded_path, is_low_resolution)

                existing_by_path = db.query_one(
                    """
                    SELECT id
                    FROM decode_tasks
                    WHERE file_path = ?
                    """,
                    (str(file_path),),
                )
                if existing_by_path:
                    db.execute(
                        """
                        UPDATE decode_tasks
                        SET file_name = ?,
                            file_size = ?,
                            resolution = ?,
                            width = ?,
                            height = ?,
                            source_root = ?,
                            status = ?,
                            output_path = NULL,
                            compare_decoded_path = ?,
                            db_record_path = ?,
                            db_record_source = ?,
                            force_pending = 0,
                            is_visible = 1,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (
                            file_path.name,
                            file_path.stat().st_size,
                            resolution,
                            width,
                            height,
                            source_root,
                            next_status,
                            linked_decoded_path,
                            db_record_path,
                            db_record_source,
                            existing_by_path["id"],
                        ),
                    )
                    existing_count += 1
                    self.progress.emit(index, total_files, file_path.name)
                    continue

                if next_status == self._page.STATUS_SUSPECTED:
                    suspected_count += 1
                elif next_status == self._page.STATUS_LOW_RESOLUTION:
                    low_resolution_count += 1
                else:
                    inserted_count += 1

                db.execute(
                    """
                    INSERT INTO decode_tasks (
                        file_name,
                        file_path,
                        file_size,
                        resolution,
                        width,
                        height,
                        source_root,
                        status,
                        compare_decoded_path,
                        db_record_path,
                        db_record_source,
                        force_pending,
                        is_visible
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1)
                    """,
                    (
                        file_path.name,
                        str(file_path),
                        file_path.stat().st_size,
                        resolution,
                        width,
                        height,
                        source_root,
                        next_status,
                        linked_decoded_path,
                        db_record_path,
                        db_record_source,
                    ),
                )
                self.progress.emit(index, total_files, file_path.name)

            summary = {
                "total_files": total_files,
                "inserted_count": inserted_count,
                "low_resolution_count": low_resolution_count,
                "suspected_count": suspected_count,
                "existing_count": existing_count,
            }
            logger.info(
                "Lada解码任务导入完成: "
                f"inserted={inserted_count}, low_resolution={low_resolution_count}, "
                f"suspected={suspected_count}, existing={existing_count}"
            )
            self.completed.emit(summary)
        except Exception as exc:
            logger.exception(f"后台导入解码任务失败: {exc}")
            self.failed.emit(str(exc))

    def _prepare_files(self) -> tuple[list[Path], callable]:
        if self._import_root:
            import_path = Path(self._import_root)
            self.started.emit("正在扫描导入路径...")
            files = self._page._collect_video_files(import_path)
            return files, (lambda file_path: import_path if import_path.is_dir() else file_path.parent)

        self.started.emit("正在整理导入文件...")
        files: list[Path] = []
        for path_str in self._file_paths:
            path = Path(path_str)
            if path.exists() and path.is_file() and path.suffix.lower() in self._page.VIDEO_EXTENSIONS:
                files.append(path)
        return files, (lambda file_path: file_path.parent)


def _safe_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _normalize_status(self, status: str | None) -> str:
    aliases = {
        self.STATUS_PENDING: self.STATUS_PENDING,
        "待解码": self.STATUS_PENDING,
        self.STATUS_DECODED: self.STATUS_DECODED,
        "已经解码": self.STATUS_DECODED,
        self.STATUS_SUSPECTED: self.STATUS_SUSPECTED,
        "疑已解码": self.STATUS_SUSPECTED,
        self.STATUS_LOW_RESOLUTION: self.STATUS_LOW_RESOLUTION,
        "低分辨率": self.STATUS_LOW_RESOLUTION,
    }
    if status is None:
        return self.STATUS_PENDING
    return aliases.get(str(status), str(status))


def _get_task_resolution(self, file_path: Path, row=None) -> tuple[int, int, str]:
    resolution = ""
    width = 0
    height = 0

    if row is not None:
        try:
            resolution = str(row["resolution"] or "").strip()
        except (KeyError, IndexError, TypeError):
            resolution = ""
        try:
            width = _safe_int(row["width"])
        except (KeyError, IndexError, TypeError):
            width = 0
        try:
            height = _safe_int(row["height"])
        except (KeyError, IndexError, TypeError):
            height = 0

    if width > 0 and height > 0:
        if not resolution:
            resolution = f"{width}x{height}"
        return width, height, resolution

    detected_width, detected_height, detected_resolution = self._detect_video_resolution(str(file_path))
    if detected_width > 0 and detected_height > 0:
        return detected_width, detected_height, detected_resolution

    return width, height, resolution


def _determine_queue_status(self, linked_decoded_path: str | None, is_low_resolution: bool) -> str:
    if linked_decoded_path:
        return self.STATUS_SUSPECTED
    if is_low_resolution:
        return self.STATUS_LOW_RESOLUTION
    return self.STATUS_PENDING


def _lock_badge_width(widget: QLabel):
    widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    widget.setMinimumWidth(widget.sizeHint().width())


def _subprocess_windowless_kwargs() -> dict:
    if not hasattr(subprocess, "CREATE_NO_WINDOW"):
        return {}

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


def _detect_video_resolution(self, file_path: str) -> tuple[int, int, str]:
    try:
        import json

        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                "-select_streams",
                "v:0",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            **_subprocess_windowless_kwargs(),
        )
        if result.returncode != 0:
            return 0, 0, "未知"

        data = json.loads(result.stdout or "{}")
        streams = data.get("streams") or []
        if not streams:
            return 0, 0, "未知"

        stream = streams[0]
        width = _safe_int(stream.get("width"))
        height = _safe_int(stream.get("height"))
        if width > 0 and height > 0:
            return width, height, f"{width}x{height}"
    except Exception as exc:
        logger.warning(f"ffprobe resolution probe failed: {file_path}, {exc}")

    return 0, 0, "未知"


def _preferred_process_encodings() -> list[str]:
    encodings: list[str] = []
    seen: set[str] = set()
    for encoding in ("utf-8", locale.getpreferredencoding(False), "gb18030", "cp936"):
        if not encoding:
            continue
        normalized = encoding.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        encodings.append(encoding)
    return encodings


def _reset_process_text_state(self):
    self._process_text_state = {
        "stdout": {"encoding": None, "decoder": None, "pending": b""},
        "stderr": {"encoding": None, "decoder": None, "pending": b""},
    }


def _decode_process_chunk(self, stream_name: str, payload: bytes) -> str:
    if not payload:
        return ""

    state = getattr(self, "_process_text_state", None)
    if not isinstance(state, dict):
        _reset_process_text_state(self)
        state = self._process_text_state

    stream_state = state.setdefault(stream_name, {"encoding": None, "decoder": None, "pending": b""})
    decoder = stream_state.get("decoder")
    if decoder is not None:
        return decoder.decode(payload, final=False)

    pending = bytes(stream_state.get("pending") or b"")
    data = pending + payload
    if not data:
        return ""

    if data.isascii():
        stream_state["pending"] = b""
        return data.decode("ascii", errors="ignore")

    for encoding in _preferred_process_encodings():
        probe = codecs.getincrementaldecoder(encoding)("strict")
        try:
            probe.decode(data, final=False)
        except UnicodeDecodeError:
            continue

        decoder = codecs.getincrementaldecoder(encoding)("replace")
        stream_state["encoding"] = encoding
        stream_state["decoder"] = decoder
        stream_state["pending"] = b""
        return decoder.decode(data, final=False)

    if len(data) <= 8:
        stream_state["pending"] = data
        return ""

    fallback_encoding = _preferred_process_encodings()[-1]
    decoder = codecs.getincrementaldecoder(fallback_encoding)("replace")
    stream_state["encoding"] = fallback_encoding
    stream_state["decoder"] = decoder
    stream_state["pending"] = b""
    return decoder.decode(data, final=False)


def _flush_process_text_stream(self, stream_name: str) -> str:
    state = getattr(self, "_process_text_state", None)
    if not isinstance(state, dict):
        return ""

    stream_state = state.get(stream_name)
    if not isinstance(stream_state, dict):
        return ""

    decoder = stream_state.get("decoder")
    if decoder is not None:
        try:
            text = decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            text = ""
    else:
        pending = bytes(stream_state.get("pending") or b"")
        if not pending:
            text = ""
        else:
            encoding = stream_state.get("encoding") or _preferred_process_encodings()[-1]
            text = pending.decode(encoding, errors="replace")

    stream_state["decoder"] = None
    stream_state["pending"] = b""
    return text


def _flush_process_text_output(self):
    for stream_name in ("stdout", "stderr"):
        text = _flush_process_text_stream(self, stream_name)
        if not text:
            continue
        self._update_task_progress_from_output(text)
        self._append_log(text)


def _hide_visible_queue_items(self):
    visible_row = db.query_one(
        "SELECT COUNT(*) AS total FROM decode_tasks WHERE COALESCE(is_visible, 1) = 1"
    )
    visible_count = int(visible_row["total"]) if visible_row else 0
    if visible_count <= 0:
        return

    db.execute(
        """
        UPDATE decode_tasks
        SET is_visible = 0,
            updated_at = CURRENT_TIMESTAMP
        WHERE COALESCE(is_visible, 1) = 1
        """
    )
    if hasattr(self, "_selected_task_ids"):
        self._selected_task_ids.clear()
    logger.info(f"Lada解码启动时已隐藏上一轮队列项目: {visible_count}")


def _init_with_clean_queue(self, *args, **kwargs):
    _ORIGINAL_INIT(self, *args, **kwargs)
    _reset_process_text_state(self)
    self._import_running = False
    self._import_worker = None
    self._import_thread = None
    _hide_visible_queue_items(self)
    self._skip_next_queue_sync = True
    self._refresh_task_table()


def _setup_ui(self):
    self.setObjectName("decodePage")
    self.setStyleSheet("QWidget#decodePage { background: #f3f5f9; }")

    main_layout = QVBoxLayout(self)
    main_layout.setContentsMargins(0, 0, 0, 0)

    page_scroll = QScrollArea()
    page_scroll.setWidgetResizable(True)
    page_scroll.setFrameShape(QFrame.Shape.NoFrame)
    page_scroll.setStyleSheet(
        """
        QScrollArea {
            border: none;
            background: #f3f5f9;
        }
        QScrollBar:vertical {
            background: #eef2f7;
            width: 10px;
            border-radius: 5px;
            margin: 4px;
        }
        QScrollBar::handle:vertical {
            background: #b7c4d8;
            border-radius: 5px;
            min-height: 30px;
        }
        """
    )

    container = QWidget()
    container.setStyleSheet("background: #f3f5f9;")

    page_layout = QVBoxLayout(container)
    page_layout.setContentsMargins(18, 16, 18, 18)
    page_layout.setSpacing(14)
    page_layout.addWidget(self._create_page_header())

    top_section = QHBoxLayout()
    top_section.setSpacing(14)

    left_panel = QWidget()
    left_panel.setMinimumWidth(520)
    left_panel.setMaximumWidth(580)
    left_layout = QVBoxLayout(left_panel)
    left_layout.setContentsMargins(0, 0, 0, 0)
    left_layout.setSpacing(14)
    left_layout.addWidget(self._create_import_card())
    left_layout.addWidget(self._create_task_card())
    left_layout.addStretch(1)

    right_panel = QWidget()
    right_layout = QVBoxLayout(right_panel)
    right_layout.setContentsMargins(0, 0, 0, 0)
    right_layout.setSpacing(14)
    right_layout.addWidget(self._create_option_card())
    right_layout.addWidget(self._create_stats_card())
    right_layout.addStretch(1)

    top_section.addWidget(left_panel, 0, Qt.AlignmentFlag.AlignTop)
    top_section.addWidget(right_panel, 1, Qt.AlignmentFlag.AlignTop)
    page_layout.addLayout(top_section)

    bottom_section = QHBoxLayout()
    bottom_section.setSpacing(14)

    path_card = self._create_path_card()
    path_card.setMinimumWidth(520)
    path_card.setMaximumWidth(580)
    bottom_section.addWidget(path_card, 0, Qt.AlignmentFlag.AlignTop)

    log_card = self._create_log_card()
    log_card.setMinimumHeight(470)
    bottom_section.addWidget(log_card, 1)

    page_layout.addLayout(bottom_section)
    page_layout.addStretch(1)

    page_scroll.setWidget(container)
    main_layout.addWidget(page_scroll)


def _create_import_card(self) -> QFrame:
    card = self._create_card()
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(12)

    title = QLabel("导入队列")
    title.setStyleSheet(self._title_style())
    layout.addWidget(title)

    hint = QLabel("选择单个视频或整个目录，目录会递归读取所有视频并写入解码数据库。")
    hint.setWordWrap(True)
    hint.setStyleSheet(self._muted_text_style())
    layout.addWidget(hint)

    self.import_path_edit = QLineEdit()
    self.import_path_edit.setPlaceholderText("选择待解码的视频文件或目录")
    self.import_path_edit.returnPressed.connect(self._import_from_manual_path)
    self.import_path_edit.textChanged.connect(self._update_command_preview)

    import_row = self._build_form_row("解码视频位置", self.import_path_edit, label_min_width=112)
    self.import_file_btn = self._create_button("文件", "#3b82f6", min_width=76, min_height=42)
    self.import_file_btn.clicked.connect(self._select_import_file)
    import_row.addWidget(self.import_file_btn)

    self.import_dir_btn = self._create_button("目录", "#22c55e", min_width=76, min_height=42)
    self.import_dir_btn.clicked.connect(self._select_import_dir)
    import_row.addWidget(self.import_dir_btn)
    layout.addLayout(import_row)

    self.import_progress_label = QLabel("导入状态：空闲")
    self.import_progress_label.setWordWrap(True)
    self.import_progress_label.setStyleSheet("QLabel { color: #5f718d; font-size: 11px; }")
    layout.addWidget(self.import_progress_label)

    tips = QLabel("文件名重复会标记为“疑已解码”，分辨率低于 1080p 会标记为“低分辨率”，均可手动改为待解码。")
    tips.setWordWrap(True)
    tips.setStyleSheet("QLabel { color: #f59e0b; font-size: 11px; }")
    layout.addWidget(tips)
    return card


def _set_import_busy(self, busy: bool, message: str | None = None):
    self._import_running = bool(busy)
    status_text = message or ("导入状态：后台处理中" if busy else "导入状态：空闲")

    if hasattr(self, "import_path_edit"):
        self.import_path_edit.setEnabled(not busy)
    if hasattr(self, "import_file_btn"):
        self.import_file_btn.setEnabled(not busy)
    if hasattr(self, "import_dir_btn"):
        self.import_dir_btn.setEnabled(not busy)
    if hasattr(self, "refresh_btn"):
        self.refresh_btn.setEnabled(not busy and not self._queue_running)
    if hasattr(self, "start_btn") and self._process.state() == QProcess.ProcessState.NotRunning:
        self.start_btn.setEnabled(not busy and not self._queue_running)
    if hasattr(self, "import_progress_label"):
        self.import_progress_label.setText(status_text)

    if hasattr(self, "status_label") and self._process.state() == QProcess.ProcessState.NotRunning and not self._queue_running:
        if busy:
            self.status_label.setText("后台导入中")
            self.status_label.setStyleSheet(
                "QLabel { color: #5b4dff; font-size: 12px; font-weight: bold; padding-left: 8px; }"
            )
        else:
            self.status_label.setText("队列空闲")
            self.status_label.setStyleSheet(
                "QLabel { color: #70809a; font-size: 12px; font-weight: bold; padding-left: 8px; }"
            )

    if hasattr(self, "current_task_label") and self._process.state() == QProcess.ProcessState.NotRunning and not self._queue_running:
        self.current_task_label.setText("当前任务: 后台导入中" if busy else "当前任务: 队列空闲")

    self._update_task_action_buttons()


def _cleanup_import_worker(self):
    self._import_worker = None
    self._import_thread = None


def _on_import_worker_started(self, message: str):
    if hasattr(self, "import_progress_label"):
        self.import_progress_label.setText(f"导入状态：{message}")


def _on_import_worker_progress(self, processed: int, total: int, current_name: str):
    total = max(total, 1)
    progress_text = f"导入状态：{processed}/{total}"
    if current_name:
        progress_text = f"{progress_text} {current_name}"
    if hasattr(self, "import_progress_label"):
        self.import_progress_label.setText(progress_text)


def _on_import_worker_completed(self, summary):
    self._set_import_busy(False, "导入状态：导入完成")
    self._skip_next_queue_sync = True
    self._refresh_task_table()
    QMessageBox.information(
        self,
        "导入完成",
        (
            f"共处理 {summary['total_files']} 个文件。\n"
            f"新增待解码：{summary['inserted_count']}\n"
            f"新增低分辨率：{summary['low_resolution_count']}\n"
            f"新增疑已解码：{summary['suspected_count']}\n"
            f"数据库已有记录：{summary['existing_count']}"
        ),
    )


def _on_import_worker_failed(self, message: str):
    self._set_import_busy(False, "导入状态：导入失败")
    QMessageBox.warning(self, "导入失败", message or "后台导入过程中发生未知错误。")


def _begin_background_import(self, import_root: str | None = None, file_paths: list[str] | None = None):
    if self._queue_running or self._process.state() != QProcess.ProcessState.NotRunning:
        QMessageBox.information(self, "提示", "请先等待当前解码任务完成或停止。")
        return

    if getattr(self, "_import_running", False):
        QMessageBox.information(self, "提示", "后台导入仍在进行中，请稍候。")
        return

    worker = _QueueImportWorker(self, import_root=import_root, file_paths=file_paths)
    worker.started.connect(self._on_import_worker_started)
    worker.progress.connect(self._on_import_worker_progress)
    worker.completed.connect(self._on_import_worker_completed)
    worker.failed.connect(self._on_import_worker_failed)
    thread = QThread(self)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.completed.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.finished.connect(self._cleanup_import_worker)

    self._import_worker = worker
    self._import_thread = thread
    self._set_import_busy(True, "导入状态：正在准备导入...")
    self._import_thread.start()


def _ensure_decode_tables(self):
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS decode_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL UNIQUE,
            file_size INTEGER,
            resolution TEXT,
            width INTEGER,
            height INTEGER,
            source_root TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            output_path TEXT,
            compare_decoded_path TEXT,
            db_record_path TEXT,
            db_record_source TEXT,
            force_pending INTEGER NOT NULL DEFAULT 0,
            is_visible INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            decoded_at DATETIME
        )
        """
    )
    with db.get_connection() as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(decode_tasks)").fetchall()}
        if "compare_decoded_path" not in columns:
            conn.execute("ALTER TABLE decode_tasks ADD COLUMN compare_decoded_path TEXT")
        if "db_record_path" not in columns:
            conn.execute("ALTER TABLE decode_tasks ADD COLUMN db_record_path TEXT")
        if "db_record_source" not in columns:
            conn.execute("ALTER TABLE decode_tasks ADD COLUMN db_record_source TEXT")
        if "resolution" not in columns:
            conn.execute("ALTER TABLE decode_tasks ADD COLUMN resolution TEXT")
        if "width" not in columns:
            conn.execute("ALTER TABLE decode_tasks ADD COLUMN width INTEGER")
        if "height" not in columns:
            conn.execute("ALTER TABLE decode_tasks ADD COLUMN height INTEGER")
        if "force_pending" not in columns:
            conn.execute("ALTER TABLE decode_tasks ADD COLUMN force_pending INTEGER NOT NULL DEFAULT 0")
        if "is_visible" not in columns:
            conn.execute("ALTER TABLE decode_tasks ADD COLUMN is_visible INTEGER NOT NULL DEFAULT 1")
        conn.commit()

    db.execute("CREATE INDEX IF NOT EXISTS idx_decode_tasks_status ON decode_tasks(status)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_decode_tasks_file_name ON decode_tasks(file_name)")


def _create_stats_card(self) -> QFrame:
    card = self._create_card()
    layout = QHBoxLayout(card)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(12)

    pending_tile, self.pending_count_label = self._create_stat_tile("待解码", "#f59e0b")
    low_resolution_tile, self.low_resolution_count_label = self._create_stat_tile("低分辨率", "#6495ed")
    decoded_tile, self.decoded_count_label = self._create_stat_tile("已经解码", "#18e0b5")
    suspected_tile, self.suspected_count_label = self._create_stat_tile("疑已解码", "#f87171")

    layout.addWidget(pending_tile)
    layout.addWidget(low_resolution_tile)
    layout.addWidget(decoded_tile)
    layout.addWidget(suspected_tile)
    return card


def _create_action_card(self) -> QFrame:
    card = QFrame()
    card.setStyleSheet("QFrame { background: transparent; border: none; }")

    layout = QHBoxLayout(card)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)

    preset_btn = self._create_button("常用预设", "#5865f2")
    preset_btn.clicked.connect(self._apply_common_preset)
    layout.addWidget(preset_btn)

    save_btn = self._create_button("保存配置", "#64748b")
    save_btn.clicked.connect(self._save_config)
    layout.addWidget(save_btn)

    self.refresh_btn = self._create_button("刷新列表", "#64748b")
    self.refresh_btn.clicked.connect(self._refresh_task_table)
    layout.addWidget(self.refresh_btn)

    layout.addStretch()

    clear_log_btn = self._create_button("清空日志", "#94a3b8")
    clear_log_btn.clicked.connect(self._clear_log)
    layout.addWidget(clear_log_btn)

    self.stop_btn = self._create_button("停止", "#ef4444", min_width=88)
    self.stop_btn.setEnabled(False)
    self.stop_btn.clicked.connect(self._stop_decode)
    layout.addWidget(self.stop_btn)

    self.start_btn = self._create_button("开始解码", "#4f7cff", min_width=120)
    self.start_btn.clicked.connect(self._start_decode_queue)
    layout.addWidget(self.start_btn)

    self.status_label = QLabel("队列空闲")
    self.status_label.setStyleSheet("QLabel { color: #70809a; font-size: 12px; font-weight: bold; padding-left: 8px; }")
    layout.addWidget(self.status_label)
    return card


def _create_path_card(self) -> QFrame:
    card = self._create_card()
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(12)

    title = QLabel("输出与运行")
    title.setStyleSheet(self._title_style())
    layout.addWidget(title)

    desc = QLabel("这里设置解码输出目录、输出模板、缓存目录、CLI 路径，以及手动对比视频入口。")
    desc.setWordWrap(True)
    desc.setStyleSheet(self._muted_text_style())
    layout.addWidget(desc)

    self.output_path_edit = QLineEdit()
    self.output_path_edit.setPlaceholderText("选择解码后的输出目录")
    self.output_path_edit.textChanged.connect(self._update_command_preview)
    layout.addLayout(
        self._build_form_row(
            "输出目录",
            self.output_path_edit,
            [("浏览", self._select_output_dir, "#253554")],
        )
    )

    self.output_pattern_edit = QLineEdit()
    self.output_pattern_edit.setPlaceholderText("{orig_file_name}.restored.mp4")
    self.output_pattern_edit.textChanged.connect(self._update_command_preview)
    layout.addLayout(self._build_form_row("输出模板", self.output_pattern_edit))

    pattern_hint = QLabel("模板必须带 `{orig_file_name}`，例如 `{orig_file_name}.restored.mp4`。")
    pattern_hint.setStyleSheet(self._muted_text_style())
    layout.addWidget(pattern_hint)

    self.temp_dir_edit = QLineEdit()
    self.temp_dir_edit.setPlaceholderText("留空时默认使用系统缓存目录")
    self.temp_dir_edit.textChanged.connect(self._update_command_preview)
    layout.addLayout(
        self._build_form_row(
            "缓存目录",
            self.temp_dir_edit,
            [("浏览", self._select_temp_dir, "#253554")],
        )
    )

    self.cli_path_edit = QLineEdit()
    self.cli_path_edit.setPlaceholderText("lada-cli 或 D:/lada/lada-cli.exe")
    self.cli_path_edit.textChanged.connect(self._update_command_preview)
    layout.addLayout(
        self._build_form_row(
            "CLI 路径",
            self.cli_path_edit,
            [("浏览", self._select_cli_path, "#253554")],
        )
    )

    layout.addSpacing(4)
    layout.addWidget(self._create_subsection_label("手动对比视频"))

    compare_hint = QLabel("分别选择左半视频和右半视频，每个输入框只能选择一个视频文件。")
    compare_hint.setWordWrap(True)
    compare_hint.setStyleSheet(self._muted_text_style())
    layout.addWidget(compare_hint)

    self.manual_compare_left_edit = QLineEdit()
    self.manual_compare_left_edit.setPlaceholderText("选择左半视频文件")
    layout.addLayout(
        self._build_form_row(
            "左半视频",
            self.manual_compare_left_edit,
            [("浏览", self._select_manual_compare_left_file, "#253554")],
        )
    )

    self.manual_compare_right_edit = QLineEdit()
    self.manual_compare_right_edit.setPlaceholderText("选择右半视频文件")
    layout.addLayout(
        self._build_form_row(
            "右半视频",
            self.manual_compare_right_edit,
            [("浏览", self._select_manual_compare_right_file, "#253554")],
        )
    )

    compare_button_row = QHBoxLayout()
    compare_button_row.setContentsMargins(0, 0, 0, 0)
    compare_button_row.addStretch()
    open_compare_btn = self._create_button("打开对比视频", "#9b59b6", min_width=136, min_height=40)
    open_compare_btn.clicked.connect(self._open_manual_compare_from_inputs)
    compare_button_row.addWidget(open_compare_btn)
    layout.addLayout(compare_button_row)

    return card


def _select_manual_compare_left_file(self):
    path, _ = QFileDialog.getOpenFileName(
        self,
        "选择左半视频",
        self._dialog_start_dir(getattr(self, "manual_compare_left_edit", QLineEdit()).text()),
        "视频文件 (*.mp4 *.mkv *.avi *.wmv *.flv *.mov *.mpg *.mpeg *.m4v *.ts *.webm);;所有文件 (*)",
    )
    if path and hasattr(self, "manual_compare_left_edit"):
        self.manual_compare_left_edit.setText(path)


def _select_manual_compare_right_file(self):
    path, _ = QFileDialog.getOpenFileName(
        self,
        "选择右半视频",
        self._dialog_start_dir(getattr(self, "manual_compare_right_edit", QLineEdit()).text()),
        "视频文件 (*.mp4 *.mkv *.avi *.wmv *.flv *.mov *.mpg *.mpeg *.m4v *.ts *.webm);;所有文件 (*)",
    )
    if path and hasattr(self, "manual_compare_right_edit"):
        self.manual_compare_right_edit.setText(path)


def _open_manual_compare_from_inputs(self):
    left_path = self.manual_compare_left_edit.text().strip() if hasattr(self, "manual_compare_left_edit") else ""
    right_path = self.manual_compare_right_edit.text().strip() if hasattr(self, "manual_compare_right_edit") else ""

    if not left_path:
        QMessageBox.information(self, "提示", "请先选择左半视频。")
        return
    if not right_path:
        QMessageBox.information(self, "提示", "请先选择右半视频。")
        return

    self._open_task_compare_preview(left_path, right_path)


def _open_single_task_preview(self, file_path: str):
    try:
        path = Path(file_path)
        if not path.exists():
            QMessageBox.warning(self, "提示", f"文件不存在，无法预览：\n{file_path}")
            return

        subprocess.run(["cmd", "/c", "start", "", str(path)], check=False, **_subprocess_windowless_kwargs())
        logger.info(f"打开 Lada 解码页单视频预览: {file_path}")
    except Exception as exc:
        logger.error(f"打开 Lada 解码页单视频预览失败: {exc}")
        QMessageBox.warning(self, "预览失败", f"无法打开视频预览：\n{exc}")


def _open_task_compare_preview(self, undecoded_path: str, decoded_path: str):
    try:
        undecoded_exists = Path(undecoded_path).exists()
        decoded_exists = Path(decoded_path).exists()

        if not undecoded_exists and not decoded_exists:
            QMessageBox.warning(self, "提示", "左半视频和右半视频都不存在，无法预览。")
            return
        if not undecoded_exists:
            QMessageBox.warning(self, "提示", f"未找到左半视频：\n{undecoded_path}")
            return
        if not decoded_exists:
            QMessageBox.warning(self, "提示", f"未找到右半视频：\n{decoded_path}")
            return

        window = DualVideoCompareWindow(
            undecoded_path,
            decoded_path,
            self,
            compare_mode=False,
        )
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        window.destroyed.connect(lambda *_args, current=window: self._remove_preview_window(current))
        self._preview_windows.append(window)
        window.show()
        window.raise_()
        window.activateWindow()
        logger.info(f"打开 Lada 解码页双视频预览: 左半={undecoded_path}, 右半={decoded_path}")
    except Exception as exc:
        logger.error(f"打开 Lada 解码页双视频预览失败: {exc}")
        QMessageBox.warning(self, "预览失败", f"无法打开双视频预览：\n{exc}")


def _validate_global_options(self):
    cli_path = self.cli_path_edit.text().strip() or "lada-cli"
    output_path = self.output_path_edit.text().strip()
    temp_dir = self.temp_dir_edit.text().strip() or tempfile.gettempdir()
    output_pattern = self.output_pattern_edit.text().strip() or "{orig_file_name}.restored.mp4"

    errors: list[str] = []
    if self._resolve_cli_path(cli_path) is None:
        errors.append("找不到 `lada-cli`。请填写 `lada-cli` 或 `lada-cli.exe` 的完整路径。")
    if not output_path:
        errors.append("请先选择解码输出目录。")
    elif Path(output_path).suffix:
        errors.append("输出位置请填写目录，不要填写单个文件名。")
    if "{orig_file_name}" not in output_pattern or "." not in output_pattern:
        errors.append("输出模板必须包含 `{orig_file_name}`，并且要带扩展名。")
    if errors:
        raise ValueError("\n".join(errors))

    try:
        Path(output_path).mkdir(parents=True, exist_ok=True)
        Path(temp_dir).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValueError(f"无法创建输出或缓存目录：{exc}") from exc


def _build_command(self, task_input_path: str | None, strict: bool) -> list[str]:
    cli_path = self.cli_path_edit.text().strip() or "lada-cli"
    resolved_cli_path = self._resolve_cli_path(cli_path) or cli_path
    input_path = task_input_path or self._current_task_path or self._get_next_pending_input_path()
    output_path = self.output_path_edit.text().strip()
    temp_dir = self.temp_dir_edit.text().strip() or tempfile.gettempdir()
    output_pattern = self.output_pattern_edit.text().strip() or "{orig_file_name}.restored.mp4"

    if strict:
        self._validate_global_options()
        if not input_path:
            raise ValueError("当前没有可执行的待解码任务。")
        if not Path(input_path).exists():
            raise ValueError(f"待解码文件不存在：{input_path}")

    return [
        resolved_cli_path,
        "--input",
        input_path or "<待解码任务>",
        "--output",
        output_path or "<输出目录>",
        "--temporary-directory",
        temp_dir,
        "--output-file-pattern",
        output_pattern,
        "--device",
        self._get_combo_value(self.device_combo),
        "--mosaic-detection-model",
        self._get_combo_value(self.detection_model_combo),
        "--mosaic-restoration-model",
        self._get_combo_value(self.restoration_model_combo),
        "--max-clip-length",
        str(self.max_clip_spin.value()),
        "--encoding-preset",
        self._get_combo_value(self.encoding_preset_combo),
        "--fp16" if self.fp16_cb.isChecked() else "--no-fp16",
        "--detect-face-mosaics" if self.detect_face_cb.isChecked() else "--no-detect-face-mosaics",
        "--mp4-fast-start" if self.mp4_fast_start_cb.isChecked() else "--no-mp4-fast-start",
    ]


def _append_log(self, text: str):
    if not text or not hasattr(self, "log_view"):
        return

    normalized = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if line:
            self.log_view.appendPlainText(line)


def _read_stdout(self):
    payload = bytes(self._process.readAllStandardOutput())
    text = _decode_process_chunk(self, "stdout", payload)
    if not text:
        return
    self._update_task_progress_from_output(text)
    self._append_log(text)


def _read_stderr(self):
    payload = bytes(self._process.readAllStandardError())
    text = _decode_process_chunk(self, "stderr", payload)
    if not text:
        return
    self._update_task_progress_from_output(text)
    self._append_log(text)


def _update_queue_overview(self, total_count: int, pending_count: int, decoded_count: int):
    if self._process.state() != QProcess.ProcessState.NotRunning:
        if hasattr(self, "queue_meta_label"):
            if self._current_task_progress is None:
                self.queue_meta_label.setText("处理中")
            else:
                self.queue_meta_label.setText(self._format_progress_text(self._current_task_progress))
        return

    if hasattr(self, "queue_meta_label"):
        self.queue_meta_label.setText(f"已完成 {decoded_count} / {total_count}")

    if hasattr(self, "queue_progress_bar"):
        self.queue_progress_bar.setRange(0, 1000)
        self.queue_progress_bar.setValue(0)

    if hasattr(self, "current_task_label") and not self._queue_running and self._current_task_path is None:
        if pending_count > 0:
            self.current_task_label.setText("当前任务: 等待开始")
        else:
            self.current_task_label.setText("当前任务: 队列空闲")


def _start_decode_queue(self):
    if getattr(self, "_import_running", False):
        QMessageBox.information(self, "提示", "请等待后台导入完成。")
        return

    if self._process.state() != QProcess.ProcessState.NotRunning:
        QMessageBox.information(self, "提示", "当前已经有解码任务在运行。")
        return

    self._save_config(show_message=False)

    try:
        self._validate_global_options()
    except ValueError as exc:
        QMessageBox.warning(self, "参数不完整", str(exc))
        return

    self._queue_running = True
    self._stop_requested = False
    _reset_process_text_state(self)
    self.log_view.clear()
    self.status_label.setText("准备开始")
    self.status_label.setStyleSheet("QLabel { color: #5b4dff; font-size: 12px; font-weight: bold; padding-left: 8px; }")
    self.current_task_label.setText("当前任务: 正在读取队列")
    self._append_log("开始读取待解码任务队列...")
    self._start_next_pending_task(
        empty_message="当前没有待解码任务。",
        completed_message=None,
    )


def _stop_decode(self):
    if self._process.state() == QProcess.ProcessState.NotRunning:
        return

    self._queue_running = False
    self._stop_requested = True
    self.status_label.setText("正在停止")
    self.status_label.setStyleSheet("QLabel { color: #f59e0b; font-size: 12px; font-weight: bold; padding-left: 8px; }")
    self._append_log("正在停止当前 lada-cli 任务...")
    logger.info("请求停止 lada-cli 队列")
    self._process.terminate()
    if not self._process.waitForFinished(2000):
        self._append_log("进程未及时退出，执行强制结束。")
        self._process.kill()


def _on_process_started(self):
    current_name = Path(self._current_task_path).name if self._current_task_path else "未知文件"
    self.start_btn.setEnabled(False)
    self.stop_btn.setEnabled(True)
    self.status_label.setText(f"解码中: {current_name}")
    self.status_label.setStyleSheet(
        "QLabel { color: #18e0b5; font-size: 12px; font-weight: bold; padding-left: 8px; }"
    )
    self.current_task_label.setText(f"当前任务: {current_name}")
    self._reset_task_progress_ui("0%")
    self._refresh_task_table()


def _on_process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus):
    _flush_process_text_output(self)
    current_name = Path(self._current_task_path).name if self._current_task_path else "当前文件"

    if self._stop_requested:
        self._append_log('lada-cli 已停止，当前任务保持为“待解码”。')
        self.status_label.setText("已停止")
        self.status_label.setStyleSheet(
            "QLabel { color: #f59e0b; font-size: 12px; font-weight: bold; padding-left: 8px; }"
        )
        self._reset_current_task_context()
        _reset_process_text_state(self)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._stop_requested = False
        self._refresh_task_table()
        return

    if exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0:
        self._set_current_task_progress(100.0)
        self._mark_current_task_decoded()
        self._append_log(f"解码完成: {current_name}")
        logger.info(f"lada-cli 解码完成: {current_name}")
        self._reset_current_task_context()
        _reset_process_text_state(self)
        self._refresh_task_table()

        if self._queue_running:
            self._start_next_pending_task(
                empty_message=None,
                completed_message="待解码队列已经全部完成。",
            )
        return

    self._append_log(f"解码失败: {current_name}，退出码 {exit_code}")
    logger.warning(f"lada-cli 解码失败: {current_name}, exit_code={exit_code}")
    self.status_label.setText(f"失败: {current_name}")
    self.status_label.setStyleSheet(
        "QLabel { color: #f87171; font-size: 12px; font-weight: bold; padding-left: 8px; }"
    )
    self.start_btn.setEnabled(True)
    self.stop_btn.setEnabled(False)
    self._queue_running = False
    self._reset_current_task_context()
    _reset_process_text_state(self)
    self._refresh_task_table()
    QMessageBox.warning(
        self,
        "解码失败",
        f'文件解码失败，任务保留为“待解码”。\n退出码: {exit_code}',
    )


def _on_process_error(self, error: QProcess.ProcessError):
    _flush_process_text_output(self)
    message = self._process.errorString() or str(error)
    if self._stop_requested:
        logger.info(f"lada-cli 停止过程中收到进程事件: {message}")
        return
    self.start_btn.setEnabled(True)
    self.stop_btn.setEnabled(False)
    self._queue_running = False
    self._append_log(f"启动 lada-cli 失败: {message}")
    logger.error(f"启动 lada-cli 失败: {message}")
    self.status_label.setText("启动失败")
    self.status_label.setStyleSheet(
        "QLabel { color: #f87171; font-size: 12px; font-weight: bold; padding-left: 8px; }"
    )
    self._reset_current_task_context()
    _reset_process_text_state(self)
    self._refresh_task_table()
    QMessageBox.warning(self, "启动失败", f"无法启动 lada-cli：\n{message}")


def _start_next_pending_task(self, empty_message: str | None, completed_message: str | None):
    task = self._get_next_pending_task()
    if not task:
        self._queue_running = False
        self._stop_requested = False
        self._reset_current_task_context()
        _reset_process_text_state(self)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("队列空闲")
        self.status_label.setStyleSheet(
            "QLabel { color: #70809a; font-size: 12px; font-weight: bold; padding-left: 8px; }"
        )
        self._refresh_task_table()
        if completed_message:
            QMessageBox.information(self, "完成", completed_message)
        elif empty_message:
            QMessageBox.information(self, "提示", empty_message)
        return

    self._current_task_id = task["id"]
    self._current_task_path = task["file_path"]
    self._current_output_path = self._guess_output_path(task["file_path"])
    self.current_task_label.setText(f"当前任务: {Path(self._current_task_path).name}")
    self._reset_task_progress_ui("0%")
    _reset_process_text_state(self)

    command = self._build_command(task["file_path"], strict=True)
    preview = subprocess.list2cmdline(command)
    self._append_log(f"$ {preview}")
    logger.info(f"启动 lada-cli 解码任务 {task['id']}: {preview}")

    self._process.setProgram(command[0])
    self._process.setArguments(command[1:])
    self._process.start()


def _get_next_pending_task(self):
    return db.query_one(
        """
        SELECT id, file_name, file_path
        FROM decode_tasks
        WHERE COALESCE(is_visible, 1) = 1
          AND status IN (?, ?)
        ORDER BY created_at ASC, id ASC
        LIMIT 1
        """,
        (self.STATUS_PENDING, "待解码"),
    )


def _get_next_pending_input_path(self) -> str:
    row = db.query_one(
        """
        SELECT file_path
        FROM decode_tasks
        WHERE COALESCE(is_visible, 1) = 1
          AND status IN (?, ?)
        ORDER BY created_at ASC, id ASC
        LIMIT 1
        """,
        (self.STATUS_PENDING, "待解码"),
    )
    return row["file_path"] if row else self.import_path_edit.text().strip()


def _refresh_task_table(self):
    if getattr(self, "_skip_next_queue_sync", False):
        self._skip_next_queue_sync = False
    else:
        self._sync_pending_tasks_with_compare_paths()

    rows = db.query(
        """
        SELECT
            id,
            file_name,
            file_path,
            file_size,
            status,
            output_path,
            compare_decoded_path,
            db_record_path,
            db_record_source,
            resolution,
            width,
            height,
            force_pending
        FROM decode_tasks
        WHERE COALESCE(is_visible, 1) = 1
        ORDER BY
            CASE status
                WHEN ? THEN 0
                WHEN ? THEN 1
                WHEN ? THEN 2
                WHEN ? THEN 3
                ELSE 4
            END,
            updated_at DESC,
            id DESC
        """,
        (self.STATUS_PENDING, self.STATUS_SUSPECTED, self.STATUS_LOW_RESOLUTION, self.STATUS_DECODED),
    )

    if not hasattr(self, "_selected_task_ids"):
        self._selected_task_ids = set()
    visible_ids = {row["id"] for row in rows}
    self._selected_task_ids.intersection_update(visible_ids)

    pending_count = 0
    low_resolution_count = 0
    decoded_count = 0
    suspected_count = 0

    self._clear_task_cards()

    for row in rows:
        status = _normalize_status(self, row["status"])
        if status == self.STATUS_PENDING:
            pending_count += 1
        elif status == self.STATUS_LOW_RESOLUTION:
            low_resolution_count += 1
        elif status == self.STATUS_DECODED:
            decoded_count += 1
        elif status == self.STATUS_SUSPECTED:
            suspected_count += 1
        self.task_list_layout.addWidget(self._create_task_item_card(row))

    self.task_list_layout.addStretch(1)

    self.pending_count_label.setText(str(pending_count))
    if hasattr(self, "low_resolution_count_label"):
        self.low_resolution_count_label.setText(str(low_resolution_count))
    self.decoded_count_label.setText(str(decoded_count))
    self.suspected_count_label.setText(str(suspected_count))
    self.task_queue_count_label.setText(f"{len(rows)} 项")
    self._update_task_action_buttons(len(rows), decoded_count)
    self._update_queue_overview(len(rows), pending_count, decoded_count)
    self._update_command_preview()


def _mark_task_pending(self, task_id: int):
    if getattr(self, "_import_running", False):
        QMessageBox.information(self, "提示", "后台导入进行中时不能修改任务状态。")
        return

    db.execute(
        """
        UPDATE decode_tasks
        SET status = ?,
            output_path = NULL,
            force_pending = 1,
            is_visible = 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (self.STATUS_PENDING, task_id),
    )
    logger.info(f"Lada解码任务改为待解码: {task_id}")
    self._refresh_task_table()


def _mark_current_task_decoded(self):
    if self._current_task_id is None:
        return

    db.execute(
        """
        UPDATE decode_tasks
        SET status = ?,
            output_path = ?,
            compare_decoded_path = ?,
            force_pending = 0,
            is_visible = 1,
            decoded_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            self.STATUS_DECODED,
            self._current_output_path,
            self._current_output_path,
            self._current_task_id,
        ),
    )


def _lookup_database_record(self, source_file: Path) -> tuple[str | None, str | None]:
    source_path = str(source_file)

    row = db.query_one(
        "SELECT file_path FROM file_index WHERE file_path = ? LIMIT 1",
        (source_path,),
    )
    if row:
        return row["file_path"], "file_index"

    row = db.query_one(
        "SELECT file_path FROM file_history WHERE file_path = ? LIMIT 1",
        (source_path,),
    )
    if row:
        return row["file_path"], "file_history"

    av_code = self._parser.parse_from_filename(source_file.name)
    if not av_code:
        return None, None

    row = db.query_one(
        "SELECT file_path FROM file_index WHERE av_code = ? ORDER BY id DESC LIMIT 1",
        (av_code,),
    )
    if row:
        return row["file_path"], "file_index"

    row = db.query_one(
        """
        SELECT file_path
        FROM file_history
        WHERE av_code = ?
        ORDER BY COALESCE(last_seen_at, first_seen_at) DESC, id DESC
        LIMIT 1
        """,
        (av_code,),
    )
    if row:
        return row["file_path"], "file_history"

    return None, None


def _resolve_compare_match(
    self,
    source_file: Path,
    decoded_compare_index: dict[str, str],
    task_compare_index: dict[str, str],
    use_configured_paths: bool,
) -> str | None:
    av_code = self._parser.parse_from_filename(source_file.name)
    if not av_code:
        return None
    if use_configured_paths:
        return decoded_compare_index.get(av_code)
    return task_compare_index.get(av_code)


def _sync_pending_tasks_with_compare_paths(self):
    candidates = db.query(
        """
        SELECT
            id,
            file_path,
            status,
            compare_decoded_path,
            db_record_path,
            db_record_source,
            resolution,
            width,
            height,
            force_pending
        FROM decode_tasks
        WHERE COALESCE(is_visible, 1) = 1
          AND status != ?
        ORDER BY id DESC
        """,
        (self.STATUS_DECODED,),
    )
    if not candidates:
        return

    configured_decoded_paths = self._get_enabled_compare_paths("decoded")
    use_configured_paths = bool(configured_decoded_paths)
    decoded_compare_index = self._build_decoded_compare_index() if use_configured_paths else {}
    task_compare_index = {} if use_configured_paths else self._build_decode_task_compare_index()
    updated_count = 0

    for row in candidates:
        source_file = Path(row["file_path"])
        current_status = _normalize_status(self, row["status"])
        db_record_path, db_record_source = self._lookup_database_record(source_file)
        width, height, resolution = _get_task_resolution(self, source_file, row)
        is_low_resolution = self._is_low_resolution(height) or current_status == self.STATUS_LOW_RESOLUTION
        resolved_compare_path = self._resolve_compare_match(
            source_file,
            decoded_compare_index,
            task_compare_index,
            use_configured_paths,
        )

        if current_status == self.STATUS_DECODED:
            next_compare_path = row["compare_decoded_path"] or resolved_compare_path
            next_status = self.STATUS_DECODED
        elif _safe_int(row["force_pending"]):
            next_compare_path = resolved_compare_path or row["compare_decoded_path"]
            next_status = self.STATUS_PENDING
        elif current_status == self.STATUS_PENDING and row["compare_decoded_path"]:
            next_compare_path = row["compare_decoded_path"]
            next_status = self.STATUS_PENDING
        else:
            next_compare_path = resolved_compare_path
            next_status = _determine_queue_status(self, next_compare_path, is_low_resolution)

        if (
            row["compare_decoded_path"] == next_compare_path
            and row["db_record_path"] == db_record_path
            and row["db_record_source"] == db_record_source
            and current_status == next_status
            and _safe_int(row["width"]) == width
            and _safe_int(row["height"]) == height
            and (row["resolution"] or "") == (resolution or "")
        ):
            continue

        db.execute(
            """
            UPDATE decode_tasks
            SET compare_decoded_path = ?,
                db_record_path = ?,
                db_record_source = ?,
                status = ?,
                resolution = ?,
                width = ?,
                height = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                next_compare_path,
                db_record_path,
                db_record_source,
                next_status,
                resolution,
                width,
                height,
                row["id"],
            ),
        )
        updated_count += 1

    if updated_count:
        logger.info(f"Lada解码队列已同步 {updated_count} 条匹配记录")


def _create_task_card(self) -> QFrame:
    self._selected_task_ids = set()

    card = self._create_card()
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(10)

    header = QHBoxLayout()
    header.setSpacing(10)

    title = QLabel("解码队列")
    title.setStyleSheet(self._title_style())
    header.addWidget(title)

    header.addStretch()

    self.task_queue_count_label = QLabel("0 项")
    self.task_queue_count_label.setStyleSheet("QLabel { color: #91a3c7; font-size: 12px; }")
    header.addWidget(self.task_queue_count_label)
    layout.addLayout(header)

    self.task_scroll = QScrollArea()
    self.task_scroll.setWidgetResizable(True)
    self.task_scroll.setMinimumHeight(360)
    self.task_scroll.setFrameShape(QFrame.Shape.NoFrame)
    self.task_scroll.setStyleSheet(
        """
        QScrollArea {
            border: 1px solid #d9dfeb;
            border-radius: 12px;
            background: #f8fafc;
        }
        QScrollBar:vertical {
            background: #eef2f7;
            width: 10px;
            border-radius: 5px;
            margin: 4px;
        }
        QScrollBar::handle:vertical {
            background: #b7c4d8;
            border-radius: 5px;
            min-height: 30px;
        }
        QScrollBar::handle:vertical:hover {
            background: #8ea2bf;
        }
        """
    )

    self.task_list_container = QWidget()
    self.task_list_container.setStyleSheet("background: #f8fafc;")
    self.task_list_layout = QVBoxLayout(self.task_list_container)
    self.task_list_layout.setContentsMargins(8, 8, 8, 8)
    self.task_list_layout.setSpacing(8)
    self.task_scroll.setWidget(self.task_list_container)
    layout.addWidget(self.task_scroll, 1)

    footer = QHBoxLayout()
    footer.setSpacing(8)

    self.remove_selected_btn = self._create_button("移除选中", "#94a3b8", min_width=126, min_height=34)
    self.remove_selected_btn.clicked.connect(self._remove_selected_tasks)
    footer.addWidget(self.remove_selected_btn)

    self.clear_completed_btn = self._create_button("清除已完成", "#94a3b8", min_width=118, min_height=34)
    self.clear_completed_btn.clicked.connect(self._clear_completed_tasks)
    footer.addWidget(self.clear_completed_btn)

    self.clear_all_btn = self._create_button("清空列表", "#94a3b8", min_width=98, min_height=34)
    self.clear_all_btn.clicked.connect(self._clear_all_tasks)
    footer.addWidget(self.clear_all_btn)

    footer.addStretch()
    layout.addLayout(footer)
    return card


def _update_task_action_buttons(self, total_count: int | None = None, decoded_count: int | None = None):
    selected_count = len(getattr(self, "_selected_task_ids", set()))
    busy = self._queue_running or getattr(self, "_import_running", False)
    if hasattr(self, "remove_selected_btn"):
        self.remove_selected_btn.setText(
            "移除选中" if selected_count == 0 else f"移除选中({selected_count})"
        )
        self.remove_selected_btn.setEnabled(selected_count > 0 and not busy)

    if total_count is not None and hasattr(self, "clear_all_btn"):
        self.clear_all_btn.setEnabled(total_count > 0 and not busy)

    if decoded_count is not None and hasattr(self, "clear_completed_btn"):
        self.clear_completed_btn.setEnabled(decoded_count > 0 and not busy)


def _toggle_task_selected(self, task_id: int, checked: bool):
    if not hasattr(self, "_selected_task_ids"):
        self._selected_task_ids = set()
    if checked:
        self._selected_task_ids.add(task_id)
    else:
        self._selected_task_ids.discard(task_id)
    self._update_task_action_buttons()


def _archive_task_ids(self, task_ids: list[int]):
    if getattr(self, "_import_running", False):
        QMessageBox.information(self, "提示", "后台导入进行中时不能移除队列项目。")
        return

    if self._queue_running:
        QMessageBox.information(self, "提示", "解码进行中时不能移除队列项目。")
        return

    ids = [int(task_id) for task_id in task_ids if task_id is not None]
    ids = [task_id for task_id in ids if task_id != self._current_task_id]
    if not ids:
        return

    placeholders = ",".join("?" for _ in ids)
    with db.get_connection() as conn:
        conn.execute(
            f"""
            UPDATE decode_tasks
            SET is_visible = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE id IN ({placeholders})
            """,
            tuple(ids),
        )
        conn.commit()

    if hasattr(self, "_selected_task_ids"):
        self._selected_task_ids.difference_update(ids)
    logger.info(f"Lada解码队列已隐藏 {len(ids)} 个项目")
    self._refresh_task_table()


def _remove_selected_tasks(self):
    self._archive_task_ids(sorted(getattr(self, "_selected_task_ids", set())))


def _remove_single_task(self, task_id: int):
    self._archive_task_ids([task_id])


def _import_files_to_queue(self, files: list[Path], source_root_resolver):
    if not files:
        QMessageBox.warning(self, "提示", "没有找到可导入的视频文件。")
        return

    configured_decoded_paths = self._get_enabled_compare_paths("decoded")
    use_configured_paths = bool(configured_decoded_paths)
    decoded_compare_index = self._build_decoded_compare_index() if use_configured_paths else {}
    task_compare_index = {} if use_configured_paths else self._build_decode_task_compare_index()

    inserted_count = 0
    low_resolution_count = 0
    suspected_count = 0
    existing_count = 0

    for file_path in files:
        source_root = str(source_root_resolver(file_path))
        linked_decoded_path = self._resolve_compare_match(
            file_path,
            decoded_compare_index,
            task_compare_index,
            use_configured_paths,
        )
        width, height, resolution = _get_task_resolution(self, file_path)
        is_low_resolution = self._is_low_resolution(height)
        db_record_path, db_record_source = self._lookup_database_record(file_path)
        next_status = _determine_queue_status(self, linked_decoded_path, is_low_resolution)

        existing_by_path = db.query_one(
            """
            SELECT id
            FROM decode_tasks
            WHERE file_path = ?
            """,
            (str(file_path),),
        )
        if existing_by_path:
            db.execute(
                """
                UPDATE decode_tasks
                SET file_name = ?,
                    file_size = ?,
                    resolution = ?,
                    width = ?,
                    height = ?,
                    source_root = ?,
                    status = ?,
                    output_path = NULL,
                    compare_decoded_path = ?,
                    db_record_path = ?,
                    db_record_source = ?,
                    force_pending = 0,
                    is_visible = 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    file_path.name,
                    file_path.stat().st_size,
                    resolution,
                    width,
                    height,
                    source_root,
                    next_status,
                    linked_decoded_path,
                    db_record_path,
                    db_record_source,
                    existing_by_path["id"],
                ),
            )
            existing_count += 1
            continue

        status = _determine_queue_status(self, linked_decoded_path, is_low_resolution)
        if status == self.STATUS_SUSPECTED:
            suspected_count += 1
        elif status == self.STATUS_LOW_RESOLUTION:
            low_resolution_count += 1
        else:
            inserted_count += 1

        db.execute(
            """
            INSERT INTO decode_tasks (
                file_name,
                file_path,
                file_size,
                resolution,
                width,
                height,
                source_root,
                status,
                compare_decoded_path,
                db_record_path,
                db_record_source,
                force_pending,
                is_visible
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1)
            """,
            (
                file_path.name,
                str(file_path),
                file_path.stat().st_size,
                resolution,
                width,
                height,
                source_root,
                status,
                linked_decoded_path,
                db_record_path,
                db_record_source,
            ),
        )

    logger.info(
        "Lada解码任务导入完成: "
        f"inserted={inserted_count}, low_resolution={low_resolution_count}, "
        f"suspected={suspected_count}, existing={existing_count}"
    )
    self._skip_next_queue_sync = True
    self._refresh_task_table()
    QMessageBox.information(
        self,
        "导入完成",
        (
            f"共选择 {len(files)} 个文件。\n"
            f"新增待解码: {inserted_count}\n"
            f"新增低分辨率: {low_resolution_count}\n"
            f"新增疑已解码: {suspected_count}\n"
            f"已在数据库中: {existing_count}"
        ),
    )


def _import_from_path(self, path_str: str):
    if getattr(self, "_import_running", False):
        QMessageBox.information(self, "提示", "后台导入仍在进行中，请稍候。")
        return

    if not path_str:
        QMessageBox.warning(self, "提示", "请先选择文件或目录。")
        return

    path = Path(path_str)
    if not path.exists():
        QMessageBox.warning(self, "提示", f"路径不存在：\n{path_str}")
        return

    self._begin_background_import(import_root=str(path))


def _import_from_multiple_paths(self, paths: list[str]):
    if getattr(self, "_import_running", False):
        QMessageBox.information(self, "提示", "后台导入仍在进行中，请稍候。")
        return

    self._begin_background_import(file_paths=list(paths))


def _clear_completed_tasks(self):
    if getattr(self, "_import_running", False):
        QMessageBox.information(self, "提示", "后台导入进行中时不能清除已完成任务。")
        return

    if self._queue_running:
        QMessageBox.information(self, "提示", "正在解码时不能清除已完成任务。")
        return

    db.execute(
        """
        UPDATE decode_tasks
        SET is_visible = 0,
            updated_at = CURRENT_TIMESTAMP
        WHERE status = ?
          AND COALESCE(is_visible, 1) = 1
        """,
        (self.STATUS_DECODED,),
    )
    if hasattr(self, "_selected_task_ids"):
        self._selected_task_ids.clear()
    logger.info("Lada解码队列已隐藏所有已完成任务")
    self._refresh_task_table()


def _clear_all_tasks(self):
    if getattr(self, "_import_running", False):
        QMessageBox.information(self, "提示", "后台导入进行中时不能清空列表。")
        return

    if self._queue_running:
        QMessageBox.information(self, "提示", "正在解码时不能清空列表。")
        return

    reply = QMessageBox.question(
        self,
        "确认清空",
        "清空列表只会隐藏当前队列项目，不会删除数据库档案。是否继续？",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if reply != QMessageBox.StandardButton.Yes:
        return

    db.execute(
        """
        UPDATE decode_tasks
        SET is_visible = 0,
            updated_at = CURRENT_TIMESTAMP
        WHERE COALESCE(is_visible, 1) = 1
        """
    )
    if hasattr(self, "_selected_task_ids"):
        self._selected_task_ids.clear()
    logger.info("Lada解码队列已隐藏当前列表中的所有任务")
    self._refresh_task_table()


def _create_task_item_card(self, row) -> QFrame:
    if not hasattr(self, "_selected_task_ids"):
        self._selected_task_ids = set()

    status = _normalize_status(self, row["status"])
    task_id = row["id"]
    is_processing = self._is_processing_task(task_id)
    display_status = "处理中" if is_processing else self.STATUS_LABELS.get(status, status)
    status_color = "#18e0b5" if is_processing else self._color_to_hex(
        self.STATUS_COLORS.get(status, QColor(183, 199, 230))
    )
    resolution = str(row["resolution"] or "").strip() if row["resolution"] else ""
    file_size_value = _safe_int(row["file_size"])
    file_size_display = format_file_size(file_size_value) if file_size_value > 0 else ""
    height = _safe_int(row["height"])
    is_low_resolution = status == self.STATUS_LOW_RESOLUTION or self._is_low_resolution(height)
    if status == self.STATUS_SUSPECTED:
        border_color = "#f1c3c8"
        background = "#fff8f8"
    elif is_low_resolution:
        border_color = "#bfd4ff"
        background = "#f3f8ff"
    else:
        border_color = "#d8e2ef"
        background = "#fbfdff"
    if status == self.STATUS_DECODED:
        preview_decoded_path = row["output_path"] or row["compare_decoded_path"]
    else:
        preview_decoded_path = row["compare_decoded_path"] or row["output_path"]
    can_compare_preview = bool(preview_decoded_path)
    has_database_record = bool(row["db_record_path"] or row["db_record_source"])

    card = QFrame()
    card.setToolTip(row["file_path"])
    card.setStyleSheet(
        f"""
        QFrame {{
            background: {background};
            border: 1px solid {border_color};
            border-radius: 12px;
        }}
        """
    )

    layout = QVBoxLayout(card)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(7)

    top_row = QHBoxLayout()
    top_row.setSpacing(8)

    select_cb = QCheckBox()
    select_cb.setChecked(task_id in self._selected_task_ids)
    select_cb.setEnabled(not self._queue_running and not getattr(self, "_import_running", False) and not is_processing)
    select_cb.stateChanged.connect(
        lambda state, current_id=task_id: self._toggle_task_selected(current_id, bool(state))
    )
    top_row.addWidget(select_cb, 0, Qt.AlignmentFlag.AlignTop)

    if can_compare_preview or is_low_resolution:
        file_label = QPushButton(row["file_name"])
        file_label.setFlat(True)
        file_label.setCursor(Qt.CursorShape.PointingHandCursor)
        file_label.setToolTip(
            "点击打开未解码和已解码文件的对比预览"
            if can_compare_preview
            else "点击使用系统播放器预览该低分辨率视频"
        )
        file_label.setStyleSheet(
            """
            QPushButton {
                text-align: left;
                background: transparent;
                border: none;
                color: #1f4fba;
                font-size: 13px;
                font-weight: bold;
                padding: 0;
            }
            QPushButton:hover {
                color: #2563eb;
                text-decoration: underline;
            }
            """
        )
        if can_compare_preview:
            file_label.clicked.connect(
                lambda checked=False, source=row["file_path"], target=preview_decoded_path:
                self._open_task_compare_preview(source, target)
            )
        else:
            file_label.clicked.connect(
                lambda checked=False, source=row["file_path"]:
                self._open_single_task_preview(source)
            )
        top_row.addWidget(file_label, 1)
    else:
        file_label = QLabel(row["file_name"])
        file_label.setStyleSheet("QLabel { color: #1f2a44; font-size: 13px; font-weight: bold; }")
        file_label.setToolTip(row["file_path"])
        top_row.addWidget(file_label, 1)

    if resolution and resolution != "未知":
        resolution_label = QLabel(resolution)
        resolution_label.setStyleSheet(
            "QLabel { color: #6495ed; font-size: 11px; font-weight: bold; }"
            if is_low_resolution
            else "QLabel { color: #6f7f97; font-size: 11px; }"
        )
        _lock_badge_width(resolution_label)
        top_row.addWidget(resolution_label)

    if file_size_display:
        size_label = QLabel(file_size_display)
        size_label.setToolTip(f"{file_size_value} B")
        size_label.setStyleSheet(
            """
            QLabel {
                color: #5f718d;
                font-size: 11px;
                background: #f4f7fb;
                border: 1px solid #dce5f1;
                border-radius: 7px;
                padding: 2px 8px;
            }
            """
        )
        _lock_badge_width(size_label)
        top_row.addWidget(size_label)

    if status in (self.STATUS_SUSPECTED, self.STATUS_LOW_RESOLUTION):
        action_btn = self._create_button("改为待解码", "#f59e0b", min_width=112, min_height=28)
        action_btn.clicked.connect(lambda checked=False, current_id=task_id: self._mark_task_pending(current_id))
        action_btn.setEnabled(
            not self._queue_running and not getattr(self, "_import_running", False) and not is_processing
        )
        top_row.addWidget(action_btn)

    remove_btn = self._create_button("移除", "#cbd5e1", min_width=74, min_height=28)
    remove_btn.clicked.connect(lambda checked=False, current_id=task_id: self._remove_single_task(current_id))
    remove_btn.setEnabled(not self._queue_running and not getattr(self, "_import_running", False) and not is_processing)
    top_row.addWidget(remove_btn)

    layout.addLayout(top_row)

    path_label = QLabel(row["file_path"])
    path_label.setWordWrap(True)
    path_label.setStyleSheet(
        """
        QLabel {
            color: #6f7f97;
            font-size: 10px;
            background: #f4f7fb;
            border: 1px solid #e4ebf4;
            border-radius: 6px;
            padding: 3px 6px;
        }
        """
    )
    path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    path_label.setToolTip(row["file_path"])
    layout.addWidget(path_label)

    bottom_row = QHBoxLayout()
    bottom_row.setSpacing(8)

    status_badge = QLabel(f"状态：{display_status}")
    status_badge.setStyleSheet(
        f"""
        QLabel {{
            color: {status_color};
            font-size: 11px;
            font-weight: bold;
            background: #ffffff;
            border: 1px solid #dee7f2;
            border-radius: 7px;
            padding: 2px 8px;
        }}
        """
    )
    _lock_badge_width(status_badge)
    bottom_row.addWidget(status_badge)

    if is_low_resolution and status != self.STATUS_LOW_RESOLUTION:
        low_resolution_label = QLabel("低分辨率")
        low_resolution_label.setStyleSheet(
            """
            QLabel {
                color: #4f7fd8;
                font-size: 10px;
                background: #e9f1ff;
                border: 1px solid #cfe0ff;
                border-radius: 7px;
                padding: 2px 8px;
            }
            """
        )
        _lock_badge_width(low_resolution_label)
        bottom_row.addWidget(low_resolution_label)

    bottom_row.addStretch()

    if status == self.STATUS_DECODED and row["output_path"]:
        output_label = QLabel("已生成输出")
        output_label.setToolTip(row["output_path"])
        output_label.setStyleSheet(
            """
            QLabel {
                color: #5f718d;
                font-size: 10px;
                background: #eef4ff;
                border: 1px solid #d7e3fb;
                border-radius: 7px;
                padding: 2px 8px;
            }
            """
        )
        _lock_badge_width(output_label)
        bottom_row.addWidget(output_label)
    elif row["compare_decoded_path"]:
        linked_label = QLabel("已关联旧输出")
        linked_label.setToolTip(row["compare_decoded_path"])
        linked_label.setStyleSheet(
            """
            QLabel {
                color: #8a5a00;
                font-size: 10px;
                background: #fff6df;
                border: 1px solid #f3deb0;
                border-radius: 7px;
                padding: 2px 8px;
            }
            """
        )
        _lock_badge_width(linked_label)
        bottom_row.addWidget(linked_label)

    if has_database_record:
        record_label = QLabel("数据库已有记录")
        tooltip_parts = []
        if row["db_record_source"] == "file_index":
            tooltip_parts.append("来源: 数据库索引")
        elif row["db_record_source"] == "file_history":
            tooltip_parts.append("来源: 数据库历史")
        if row["db_record_path"]:
            tooltip_parts.append(row["db_record_path"])
        if tooltip_parts:
            record_label.setToolTip("\n".join(tooltip_parts))
        record_label.setStyleSheet(
            """
            QLabel {
                color: #475569;
                font-size: 10px;
                background: #f1f5f9;
                border: 1px solid #d8e2ef;
                border-radius: 7px;
                padding: 2px 8px;
            }
            """
        )
        _lock_badge_width(record_label)
        bottom_row.addWidget(record_label)

    layout.addLayout(bottom_row)
    return card


def apply_decode_page_overrides():
    global _OVERRIDES_APPLIED
    if _OVERRIDES_APPLIED:
        return

    DecodePage.__init__ = _init_with_clean_queue
    DecodePage._setup_ui = _setup_ui
    DecodePage._ensure_decode_tables = _ensure_decode_tables
    DecodePage._create_import_card = _create_import_card
    DecodePage._set_import_busy = _set_import_busy
    DecodePage._cleanup_import_worker = _cleanup_import_worker
    DecodePage._on_import_worker_started = _on_import_worker_started
    DecodePage._on_import_worker_progress = _on_import_worker_progress
    DecodePage._on_import_worker_completed = _on_import_worker_completed
    DecodePage._on_import_worker_failed = _on_import_worker_failed
    DecodePage._begin_background_import = _begin_background_import
    DecodePage._create_stats_card = _create_stats_card
    DecodePage._create_action_card = _create_action_card
    DecodePage._create_path_card = _create_path_card
    DecodePage._select_manual_compare_left_file = _select_manual_compare_left_file
    DecodePage._select_manual_compare_right_file = _select_manual_compare_right_file
    DecodePage._open_manual_compare_from_inputs = _open_manual_compare_from_inputs
    DecodePage._open_single_task_preview = _open_single_task_preview
    DecodePage._open_task_compare_preview = _open_task_compare_preview
    DecodePage._validate_global_options = _validate_global_options
    DecodePage._detect_video_resolution = _detect_video_resolution
    DecodePage._build_command = _build_command
    DecodePage._append_log = _append_log
    DecodePage._read_stdout = _read_stdout
    DecodePage._read_stderr = _read_stderr
    DecodePage._update_queue_overview = _update_queue_overview
    DecodePage._start_decode_queue = _start_decode_queue
    DecodePage._stop_decode = _stop_decode
    DecodePage._on_process_started = _on_process_started
    DecodePage._on_process_finished = _on_process_finished
    DecodePage._on_process_error = _on_process_error
    DecodePage._start_next_pending_task = _start_next_pending_task
    DecodePage._get_next_pending_task = _get_next_pending_task
    DecodePage._get_next_pending_input_path = _get_next_pending_input_path
    DecodePage._lookup_database_record = _lookup_database_record
    DecodePage._resolve_compare_match = _resolve_compare_match
    DecodePage._sync_pending_tasks_with_compare_paths = _sync_pending_tasks_with_compare_paths
    DecodePage._create_task_card = _create_task_card
    DecodePage._update_task_action_buttons = _update_task_action_buttons
    DecodePage._toggle_task_selected = _toggle_task_selected
    DecodePage._archive_task_ids = _archive_task_ids
    DecodePage._remove_selected_tasks = _remove_selected_tasks
    DecodePage._remove_single_task = _remove_single_task
    DecodePage._import_files_to_queue = _import_files_to_queue
    DecodePage._refresh_task_table = _refresh_task_table
    DecodePage._mark_task_pending = _mark_task_pending
    DecodePage._mark_current_task_decoded = _mark_current_task_decoded
    DecodePage._import_from_path = _import_from_path
    DecodePage._import_from_multiple_paths = _import_from_multiple_paths
    DecodePage._clear_completed_tasks = _clear_completed_tasks
    DecodePage._clear_all_tasks = _clear_all_tasks
    DecodePage._create_task_item_card = _create_task_item_card
    _OVERRIDES_APPLIED = True


apply_decode_page_overrides()
