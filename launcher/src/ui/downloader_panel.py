"""
downloader_panel.py — Mimir Video Downloader Panel

PyQt6 GUI wrapper around yt-dlp. Downloads videos and audio to
{drive}/Mimir/media/videos/ — which is pre-configured as a Jellyfin library,
so content appears in the media center automatically after a Jellyfin scan.

Layout (top to bottom):
  Toolbar        — title + Open Output Folder button
  Warning banner — shown if yt-dlp.exe is missing
  Input row      — URL field + Paste button
  Options row    — Quality dropdown + output folder display + Change button
  Action row     — Download / Cancel button
  Progress row   — QProgressBar + status label (speed / ETA)
  Log area       — scrolling monospace window showing yt-dlp stdout
  History        — session download history (cleared on app restart)

One download at a time. Download button disabled while a download is running.
Cancel terminates the subprocess immediately.

Signals: none (self-contained)
Public API:
  set_paths(paths)  — wire MimirPaths after construction
"""

import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QProgressBar, QTextEdit,
    QFrame, QScrollArea, QSizePolicy, QFileDialog, QApplication
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QTextCursor

from ytdlp_worker import YtdlpWorker, QUALITY_LABELS


# ---- Download history record --------------------------------------------

@dataclass
class _DownloadRecord:
    title: str
    file_path: str
    quality: str
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%H:%M"))


# ---- History item widget ------------------------------------------------

class _HistoryItem(QWidget):
    """Single row in the download history list."""

    def __init__(self, record: _DownloadRecord, parent=None):
        super().__init__(parent)
        self._record = record
        self.setObjectName("dl-history-item")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        time_lbl = QLabel(record.timestamp)
        time_lbl.setObjectName("dl-history-time")
        time_lbl.setFixedWidth(42)

        title_lbl = QLabel(record.title)
        title_lbl.setObjectName("dl-history-title")
        title_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        title_lbl.setWordWrap(False)

        quality_lbl = QLabel(record.quality)
        quality_lbl.setObjectName("dl-history-quality")
        quality_lbl.setFixedWidth(80)

        open_file_btn = QPushButton("Open File")
        open_file_btn.setObjectName("dl-history-btn")
        open_file_btn.setFixedHeight(24)
        open_file_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_file_btn.clicked.connect(self._open_file)

        open_folder_btn = QPushButton("Folder")
        open_folder_btn.setObjectName("dl-history-btn")
        open_folder_btn.setFixedHeight(24)
        open_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_folder_btn.clicked.connect(self._open_folder)

        # Disable file buttons if path is unknown
        has_path = bool(record.file_path and Path(record.file_path).exists())
        open_file_btn.setEnabled(has_path)

        layout.addWidget(time_lbl)
        layout.addWidget(title_lbl)
        layout.addWidget(quality_lbl)
        layout.addWidget(open_file_btn)
        layout.addWidget(open_folder_btn)

    def _open_file(self):
        path = Path(self._record.file_path)
        if path.exists():
            os.startfile(str(path))

    def _open_folder(self):
        path = Path(self._record.file_path)
        folder = path.parent if path.exists() else Path(self._record.file_path).parent
        try:
            subprocess.Popen(["explorer", str(folder)])
        except Exception:
            pass


# ---- Warning banner -----------------------------------------------------

class _WarningBanner(QWidget):
    """Shown when yt-dlp.exe is not found."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dl-warning-banner")
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        icon = QLabel("⚠")
        icon.setObjectName("dl-warning-icon")
        icon.setFixedWidth(18)

        self._text = QLabel()
        self._text.setObjectName("dl-warning-text")

        layout.addWidget(icon)
        layout.addWidget(self._text)
        layout.addStretch()

    def set_message(self, msg: str):
        self._text.setText(msg)


# ---- Main panel ---------------------------------------------------------

class DownloaderPanel(QWidget):
    """yt-dlp GUI downloader panel."""

    def __init__(self, paths=None, parent=None):
        super().__init__(parent)
        self._paths = paths
        self._worker: Optional[YtdlpWorker] = None
        self._history: list[_DownloadRecord] = []
        self._output_dir: Optional[Path] = None

        self.setObjectName("dl-panel")
        self._setup_ui()

        if paths:
            self._configure_paths()

    # ----------------------------------------------------------------- layout

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Toolbar ----
        toolbar = QWidget()
        toolbar.setObjectName("dl-toolbar")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(16, 10, 16, 10)
        tb.setSpacing(10)

        title = QLabel("Downloader")
        title.setObjectName("dl-title")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setWeight(QFont.Weight.Bold)
        title.setFont(title_font)

        self._open_folder_btn = QPushButton("Open Output Folder")
        self._open_folder_btn.setObjectName("dl-toolbar-btn")
        self._open_folder_btn.setFixedHeight(28)
        self._open_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_folder_btn.clicked.connect(self._open_output_folder)

        tb.addWidget(title)
        tb.addStretch()
        tb.addWidget(self._open_folder_btn)
        root.addWidget(toolbar)

        # ---- Warning banner (hidden initially) ----
        self._warning = _WarningBanner()
        self._warning.setVisible(False)
        root.addWidget(self._warning)

        # ---- Separator ----
        root.addWidget(self._make_sep())

        # ---- Scrollable body ----
        scroll = QScrollArea()
        scroll.setObjectName("dl-scroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        body = QWidget()
        body.setObjectName("dl-body")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 24, 24, 24)
        body_layout.setSpacing(16)

        # ---- URL row ----
        url_label = QLabel("URL")
        url_label.setObjectName("dl-field-label")
        body_layout.addWidget(url_label)

        url_row = QHBoxLayout()
        url_row.setSpacing(8)

        self._url_input = QLineEdit()
        self._url_input.setObjectName("dl-url-input")
        self._url_input.setPlaceholderText("https://www.youtube.com/watch?v=...")
        self._url_input.setFixedHeight(36)
        self._url_input.returnPressed.connect(self._on_download_clicked)

        paste_btn = QPushButton("📋 Paste")
        paste_btn.setObjectName("dl-paste-btn")
        paste_btn.setFixedHeight(36)
        paste_btn.setFixedWidth(80)
        paste_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        paste_btn.clicked.connect(self._paste_url)

        url_row.addWidget(self._url_input)
        url_row.addWidget(paste_btn)
        body_layout.addLayout(url_row)

        # ---- Options row ----
        options_row = QHBoxLayout()
        options_row.setSpacing(16)

        # Quality
        quality_col = QVBoxLayout()
        quality_col.setSpacing(4)
        quality_label = QLabel("Quality")
        quality_label.setObjectName("dl-field-label")
        self._quality_combo = QComboBox()
        self._quality_combo.setObjectName("dl-quality-combo")
        self._quality_combo.setFixedHeight(36)
        self._quality_combo.setFixedWidth(200)
        for label in QUALITY_LABELS:
            self._quality_combo.addItem(label)
        quality_col.addWidget(quality_label)
        quality_col.addWidget(self._quality_combo)
        options_row.addLayout(quality_col)

        # Output folder
        folder_col = QVBoxLayout()
        folder_col.setSpacing(4)
        folder_label = QLabel("Output Folder")
        folder_label.setObjectName("dl-field-label")
        folder_row = QHBoxLayout()
        folder_row.setSpacing(6)
        self._folder_display = QLabel("—")
        self._folder_display.setObjectName("dl-folder-display")
        self._folder_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        change_btn = QPushButton("Change")
        change_btn.setObjectName("dl-change-btn")
        change_btn.setFixedHeight(36)
        change_btn.setFixedWidth(72)
        change_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        change_btn.clicked.connect(self._choose_output_dir)
        folder_row.addWidget(self._folder_display)
        folder_row.addWidget(change_btn)
        folder_col.addWidget(folder_label)
        folder_col.addLayout(folder_row)
        options_row.addLayout(folder_col, stretch=1)

        body_layout.addLayout(options_row)

        # ---- MP3 ffmpeg notice ----
        self._ffmpeg_notice = QLabel(
            "⚠  Audio only (MP3) requires ffmpeg.exe in tools/ffmpeg/. "
            "Without it, audio will download in the source format (webm/m4a)."
        )
        self._ffmpeg_notice.setObjectName("dl-ffmpeg-notice")
        self._ffmpeg_notice.setWordWrap(True)
        self._ffmpeg_notice.setVisible(False)
        body_layout.addWidget(self._ffmpeg_notice)
        self._quality_combo.currentTextChanged.connect(self._on_quality_changed)

        # ---- Download button ----
        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._download_btn = QPushButton("Download")
        self._download_btn.setObjectName("dl-download-btn")
        self._download_btn.setFixedHeight(44)
        self._download_btn.setFixedWidth(180)
        self._download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_font = QFont()
        btn_font.setPointSize(12)
        btn_font.setWeight(QFont.Weight.Bold)
        self._download_btn.setFont(btn_font)
        self._download_btn.clicked.connect(self._on_download_clicked)
        btn_row.addWidget(self._download_btn)
        body_layout.addLayout(btn_row)

        # ---- Progress ----
        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("dl-progress-bar")
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setVisible(False)
        body_layout.addWidget(self._progress_bar)

        self._status_label = QLabel("")
        self._status_label.setObjectName("dl-status-label")
        self._status_label.setVisible(False)
        body_layout.addWidget(self._status_label)

        # ---- Log area ----
        log_label = QLabel("OUTPUT LOG")
        log_label.setObjectName("dl-section-label")
        body_layout.addWidget(log_label)

        self._log = QTextEdit()
        self._log.setObjectName("dl-log")
        self._log.setReadOnly(True)
        self._log.setFixedHeight(180)
        log_font = QFont("Courier New", 9)
        if not log_font.exactMatch():
            log_font = QFont("Consolas", 9)
        self._log.setFont(log_font)
        self._log.setPlaceholderText("yt-dlp output will appear here during download...")
        body_layout.addWidget(self._log)

        # ---- History ----
        self._history_label = QLabel("DOWNLOAD HISTORY  (this session)")
        self._history_label.setObjectName("dl-section-label")
        body_layout.addWidget(self._history_label)

        self._history_container = QWidget()
        self._history_container.setObjectName("dl-history-container")
        self._history_layout = QVBoxLayout(self._history_container)
        self._history_layout.setContentsMargins(0, 0, 0, 0)
        self._history_layout.setSpacing(1)

        self._empty_history_label = QLabel("No downloads yet this session.")
        self._empty_history_label.setObjectName("dl-empty-history")
        self._history_layout.addWidget(self._empty_history_label)

        body_layout.addWidget(self._history_container)
        body_layout.addStretch()

        scroll.setWidget(body)
        root.addWidget(scroll, stretch=1)

    def _make_sep(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("kb-separator")
        return sep

    # ----------------------------------------------------------------- path wiring

    def _configure_paths(self):
        if not self._paths:
            return

        # Default output to videos dir
        self._output_dir = self._paths.videos
        self._folder_display.setText(str(self._output_dir))

        # Check yt-dlp presence
        if not self._paths.ytdlp_exe.exists():
            self._warning.set_message(
                f"yt-dlp.exe not found at {self._paths.ytdlp_exe}  —  "
                "download yt-dlp from https://github.com/yt-dlp/yt-dlp/releases and place it there."
            )
            self._warning.setVisible(True)
            self._download_btn.setEnabled(False)

    def set_paths(self, paths):
        self._paths = paths
        self._configure_paths()

    # ----------------------------------------------------------------- slots

    def _paste_url(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if text:
            self._url_input.setText(text)
            self._url_input.setFocus()

    def _on_quality_changed(self, quality: str):
        needs_ffmpeg = quality == "Audio only (MP3)"
        if needs_ffmpeg and self._paths:
            ffmpeg_present = self._paths.ffmpeg_exe.exists()
            self._ffmpeg_notice.setVisible(not ffmpeg_present)
        else:
            self._ffmpeg_notice.setVisible(False)

    def _choose_output_dir(self):
        start = str(self._output_dir or Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Select Output Folder", start)
        if chosen:
            self._output_dir = Path(chosen)
            self._folder_display.setText(chosen)

    def _open_output_folder(self):
        folder = self._output_dir or (self._paths.videos if self._paths else None)
        if folder:
            try:
                subprocess.Popen(["explorer", str(folder)])
            except Exception:
                pass

    def _on_download_clicked(self):
        if self._worker and self._worker.isRunning():
            self._cancel_download()
            return

        url = self._url_input.text().strip()
        if not url:
            self._url_input.setFocus()
            return

        if not self._paths or not self._paths.ytdlp_exe.exists():
            return

        quality = self._quality_combo.currentText()
        output_dir = self._output_dir or self._paths.videos

        ffmpeg_exe = self._paths.ffmpeg_exe if self._paths.ffmpeg_exe.exists() else None

        self._start_download(url, quality, output_dir, ffmpeg_exe)

    def _start_download(self, url: str, quality: str, output_dir: Path, ffmpeg_exe):
        # Clear log
        self._log.clear()

        # Show progress widgets
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(True)
        self._status_label.setText("Starting download...")
        self._status_label.setVisible(True)

        # Switch button to Cancel
        self._download_btn.setText("Cancel")
        self._download_btn.setObjectName("dl-cancel-btn")
        self._download_btn.style().unpolish(self._download_btn)
        self._download_btn.style().polish(self._download_btn)

        # Disable URL and quality while running
        self._url_input.setEnabled(False)
        self._quality_combo.setEnabled(False)

        # Create and start worker
        self._worker = YtdlpWorker(
            url=url,
            quality=quality,
            output_dir=output_dir,
            ytdlp_exe=self._paths.ytdlp_exe,
            ffmpeg_exe=ffmpeg_exe,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.log_line.connect(self._on_log_line)
        self._worker.download_complete.connect(self._on_download_complete)
        self._worker.download_failed.connect(self._on_download_failed)
        self._worker.start()

    def _cancel_download(self):
        if self._worker:
            self._worker.cancel()

    # ----------------------------------------------------------------- worker signals

    def _on_progress(self, percent: int, status: str):
        self._progress_bar.setValue(percent)
        self._status_label.setText(status)

    def _on_log_line(self, line: str):
        self._log.append(line)
        # Auto-scroll to bottom
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._log.setTextCursor(cursor)

    def _on_download_complete(self, title: str, file_path: str):
        self._reset_ui()
        self._status_label.setText(f"✓  {title}")
        self._progress_bar.setValue(100)

        # Add to history
        quality = self._quality_combo.currentText()
        record = _DownloadRecord(title=title, file_path=file_path, quality=quality)
        self._history.append(record)
        self._add_history_item(record)

        # Clear URL field ready for next download
        QTimer.singleShot(1500, lambda: self._url_input.clear())

    def _on_download_failed(self, error: str):
        self._reset_ui()
        self._status_label.setText(f"✗  {error}")
        self._progress_bar.setValue(0)

    def _reset_ui(self):
        """Restore UI to idle state after download ends."""
        self._download_btn.setText("Download")
        self._download_btn.setObjectName("dl-download-btn")
        self._download_btn.style().unpolish(self._download_btn)
        self._download_btn.style().polish(self._download_btn)
        self._url_input.setEnabled(True)
        self._quality_combo.setEnabled(True)

    def _add_history_item(self, record: _DownloadRecord):
        # Remove empty-history placeholder on first real item
        if self._empty_history_label.isVisible():
            self._empty_history_label.setVisible(False)

        item = _HistoryItem(record)
        # Insert at top
        self._history_layout.insertWidget(0, item)
