"""
model_pull_dialog.py — Mimir Model Download Dialog

Shown when the selected model is not present on the drive.
Streams Ollama's pull progress and displays it clearly.

Features:
  - Layer-by-layer download progress
  - Overall progress bar (estimated from completed/total across layers)
  - Speed estimate and ETA
  - Cancel button (stops the download, cleans up)
  - Emits pull_complete or pull_failed on finish
"""

import time
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QFrame, QScrollArea, QWidget, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer
from PyQt6.QtGui import QFont

from ollama_client import OllamaClient, PullProgress, OllamaError, OllamaConnectionError


# ============================================================
# Pull Worker Thread
# ============================================================

class PullWorker(QThread):
    """Runs the model pull in a background thread."""
    progress_update = pyqtSignal(object)   # PullProgress
    finished = pyqtSignal()
    failed = pyqtSignal(str)               # error message

    def __init__(self, client: OllamaClient, model_name: str, parent=None):
        super().__init__(parent)
        self._client = client
        self._model_name = model_name
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            for progress in self._client.pull_model(self._model_name):
                if self._cancelled:
                    self.failed.emit("Download cancelled.")
                    return
                self.progress_update.emit(progress)
            if not self._cancelled:
                self.finished.emit()
        except OllamaConnectionError as e:
            self.failed.emit(f"Ollama is not running: {e}")
        except OllamaError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f"Unexpected error: {e}")


# ============================================================
# Dialog
# ============================================================

class ModelPullDialog(QDialog):
    """
    Dialog for downloading a missing Ollama model.
    Shown automatically when the selected model isn't present.

    Signals:
      pull_complete — model is downloaded and ready
      pull_failed(str) — download failed with message
    """

    pull_complete = pyqtSignal()
    pull_failed = pyqtSignal(str)

    def __init__(self, client: OllamaClient, model_name: str,
                 model_display_name: str, model_size_gb: float, parent=None):
        super().__init__(parent)
        self._client = client
        self._model_name = model_name
        self._model_display_name = model_display_name
        self._model_size_gb = model_size_gb

        self._worker: PullWorker = None
        self._start_time: float = 0
        self._bytes_at_last_speed_check: int = 0
        self._speed_check_time: float = 0
        self._current_speed_mbps: float = 0
        self._total_bytes_downloaded: int = 0
        self._total_bytes_overall: int = 0
        self._layer_totals: dict = {}   # digest → total bytes
        self._layer_completed: dict = {}  # digest → completed bytes

        self.setWindowTitle("Mimir — Download Model")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setMinimumHeight(360)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.CustomizeWindowHint
        )

        self._build_ui()
        self._start_pull()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # ---- Header ----
        title = QLabel(f"Downloading {self._model_display_name}")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setWeight(QFont.Weight.Bold)
        title.setFont(title_font)
        layout.addWidget(title)

        size_note = QLabel(
            f"Model: {self._model_name}   ·   "
            f"Approximate size: ~{self._model_size_gb}GB\n"
            "This is a one-time download. The model stays on the drive."
        )
        size_note.setProperty("class", "subtitle")
        size_note.setWordWrap(True)
        layout.addWidget(size_note)

        # ---- Status line ----
        self._status_label = QLabel("Connecting to Ollama registry...")
        self._status_label.setProperty("class", "subtitle")
        layout.addWidget(self._status_label)

        # ---- Overall progress bar ----
        overall_header = QLabel("Overall Progress")
        overall_header.setProperty("class", "section-header")
        layout.addWidget(overall_header)

        self._overall_bar = QProgressBar()
        self._overall_bar.setRange(0, 100)
        self._overall_bar.setValue(0)
        self._overall_bar.setFixedHeight(12)
        self._overall_bar.setTextVisible(False)
        layout.addWidget(self._overall_bar)

        self._overall_pct_label = QLabel("0%")
        self._overall_pct_label.setProperty("class", "subtitle")
        layout.addWidget(self._overall_pct_label)

        # ---- Speed and ETA ----
        stats_row = QHBoxLayout()
        self._speed_label = QLabel("Speed: —")
        self._speed_label.setProperty("class", "subtitle")
        self._eta_label = QLabel("ETA: —")
        self._eta_label.setProperty("class", "subtitle")
        stats_row.addWidget(self._speed_label)
        stats_row.addStretch()
        stats_row.addWidget(self._eta_label)
        layout.addLayout(stats_row)

        # ---- Layer detail (scrollable) ----
        layer_header = QLabel("Layers")
        layer_header.setProperty("class", "section-header")
        layout.addWidget(layer_header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(120)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._layers_container = QWidget()
        self._layers_layout = QVBoxLayout(self._layers_container)
        self._layers_layout.setContentsMargins(4, 4, 4, 4)
        self._layers_layout.setSpacing(4)
        self._layers_layout.addStretch()
        scroll.setWidget(self._layers_container)
        layout.addWidget(scroll)

        self._layer_bars: dict = {}  # digest → (bar_widget, label_widget)

        # ---- Cancel / Done buttons ----
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._cancel_btn = QPushButton("Cancel Download")
        self._cancel_btn.setProperty("class", "primary")
        self._cancel_btn.setFixedHeight(38)
        self._cancel_btn.clicked.connect(self._cancel)
        btn_row.addWidget(self._cancel_btn)

        layout.addLayout(btn_row)

    def _start_pull(self):
        self._start_time = time.monotonic()
        self._worker = PullWorker(self._client, self._model_name)
        self._worker.progress_update.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, progress: PullProgress):
        self._status_label.setText(progress.status.capitalize())

        # Track bytes
        if progress.digest and progress.total > 0:
            self._layer_totals[progress.digest] = progress.total
            self._layer_completed[progress.digest] = progress.completed
            self._update_layer_bar(progress)

        # Compute overall progress
        total = sum(self._layer_totals.values())
        completed = sum(self._layer_completed.values())

        if total > 0:
            pct = int((completed / total) * 100)
            self._overall_bar.setValue(pct)
            self._overall_pct_label.setText(
                f"{pct}%   ({self._fmt_bytes(completed)} / {self._fmt_bytes(total)})"
            )
            self._total_bytes_downloaded = completed
            self._total_bytes_overall = total

        # Speed and ETA (update every ~2 seconds)
        now = time.monotonic()
        if now - self._speed_check_time >= 2.0 and self._total_bytes_downloaded > 0:
            elapsed = now - self._start_time
            if elapsed > 0:
                avg_speed = self._total_bytes_downloaded / elapsed
                self._current_speed_mbps = avg_speed / (1024 ** 2)
                self._speed_label.setText(f"Speed: {self._current_speed_mbps:.1f} MB/s")

                remaining = self._total_bytes_overall - self._total_bytes_downloaded
                if avg_speed > 0 and remaining > 0:
                    eta_sec = remaining / avg_speed
                    self._eta_label.setText(f"ETA: {self._fmt_duration(eta_sec)}")
                else:
                    self._eta_label.setText("ETA: —")

            self._speed_check_time = now

    def _update_layer_bar(self, progress: PullProgress):
        digest = progress.digest
        short_digest = digest.split(":")[-1][:12] if ":" in digest else digest[:12]

        if digest not in self._layer_bars:
            # Create a new row for this layer
            row_widget = QFrame()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)

            dig_label = QLabel(short_digest)
            dig_label.setProperty("class", "subtitle")
            dig_label.setFixedWidth(100)

            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setFixedHeight(8)
            bar.setTextVisible(False)

            size_label = QLabel("")
            size_label.setProperty("class", "subtitle")
            size_label.setFixedWidth(100)
            size_label.setAlignment(Qt.AlignmentFlag.AlignRight)

            row_layout.addWidget(dig_label)
            row_layout.addWidget(bar, 1)
            row_layout.addWidget(size_label)

            # Insert before the stretch
            idx = self._layers_layout.count() - 1
            self._layers_layout.insertWidget(idx, row_widget)
            self._layer_bars[digest] = (bar, size_label)

        bar, size_label = self._layer_bars[digest]
        if progress.total > 0:
            bar.setValue(int(progress.percent))
            size_label.setText(
                f"{self._fmt_bytes(progress.completed)} / {self._fmt_bytes(progress.total)}"
            )
        else:
            bar.setRange(0, 0)  # Indeterminate
            size_label.setText(progress.status[:20] if progress.status else "")

    def _on_finished(self):
        self._overall_bar.setValue(100)
        self._status_label.setText("Download complete.")
        self._speed_label.setText("Speed: —")
        elapsed = time.monotonic() - self._start_time
        self._eta_label.setText(f"Completed in {self._fmt_duration(elapsed)}")

        self._cancel_btn.setText("Continue")
        self._cancel_btn.clicked.disconnect()
        self._cancel_btn.clicked.connect(self.accept)

        self.pull_complete.emit()

    def _on_failed(self, error_msg: str):
        self._status_label.setText(f"Failed: {error_msg}")
        self._cancel_btn.setText("Close")
        self._cancel_btn.clicked.disconnect()
        self._cancel_btn.clicked.connect(self.reject)
        self.pull_failed.emit(error_msg)

    def _cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
        self.reject()

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
        event.accept()

    # ---- Formatting helpers ----

    @staticmethod
    def _fmt_bytes(n: int) -> str:
        if n >= 1024 ** 3:
            return f"{n / 1024**3:.1f}GB"
        elif n >= 1024 ** 2:
            return f"{n / 1024**2:.0f}MB"
        elif n >= 1024:
            return f"{n / 1024:.0f}KB"
        return f"{n}B"

    @staticmethod
    def _fmt_duration(seconds: float) -> str:
        s = int(seconds)
        if s < 60:
            return f"{s}s"
        elif s < 3600:
            m, sec = divmod(s, 60)
            return f"{m}m {sec}s"
        else:
            h, remainder = divmod(s, 3600)
            m = remainder // 60
            return f"{h}h {m}m"
