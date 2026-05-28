"""
kb_index_status.py — KB Index Status Bar Widget

Compact bar displayed at the top of the KB panel.
Shows current index health and provides re-index controls.

Layout:
  [● status text]  [stale badge]  [spacer]  [Re-Index]  [Force Re-Index ▼]

During indexing:
  [■ progress bar]  [N / M files]  [current filename]  [Cancel]

Signals:
  reindex_started()        — emitted when user triggers a re-index
  reindex_complete(int, int)  — (new_files, total_files) when done
  reindex_failed(str)      — error message

Public API:
  load_scan(KBScanResult)   — update display from a scan result
  start_indexing(total)     — switch to progress mode
  update_progress(done, total, filename)
  finish_indexing(new, total)
  fail_indexing(msg)
"""

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QProgressBar, QFrame, QMenu, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction


class KBIndexStatusBar(QWidget):
    """
    KB index status + re-index control bar.
    """

    reindex_requested = pyqtSignal(bool)  # force: bool
    cancel_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("kb-status-bar")
        self.setFixedHeight(44)

        self._is_indexing = False
        self._setup_ui()

    # ----------------------------------------------------------------- layout

    def _setup_ui(self):
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(12, 6, 12, 6)
        self._layout.setSpacing(10)

        # ---- Idle row ----
        self._idle_widget = QWidget()
        idle_layout = QHBoxLayout(self._idle_widget)
        idle_layout.setContentsMargins(0, 0, 0, 0)
        idle_layout.setSpacing(10)

        self._status_dot = QLabel("●")
        self._status_dot.setObjectName("kb-status-dot-ok")
        self._status_dot.setFixedWidth(16)

        self._status_text = QLabel("Scanning…")
        self._status_text.setObjectName("kb-status-text")
        self._status_text.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        self._stale_badge = QLabel()
        self._stale_badge.setObjectName("kb-stale-badge")
        self._stale_badge.setVisible(False)

        self._reindex_btn = QPushButton("Re-Index")
        self._reindex_btn.setObjectName("kb-reindex-btn")
        self._reindex_btn.setFixedHeight(28)
        self._reindex_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reindex_btn.clicked.connect(lambda: self.reindex_requested.emit(False))

        self._force_btn = QPushButton("▼")
        self._force_btn.setObjectName("kb-force-btn")
        self._force_btn.setFixedSize(28, 28)
        self._force_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._force_btn.setToolTip("Force full re-index")
        self._force_btn.clicked.connect(self._show_force_menu)

        idle_layout.addWidget(self._status_dot)
        idle_layout.addWidget(self._status_text)
        idle_layout.addWidget(self._stale_badge)
        idle_layout.addStretch()
        idle_layout.addWidget(self._reindex_btn)
        idle_layout.addWidget(self._force_btn)

        # ---- Progress row ----
        self._progress_widget = QWidget()
        progress_layout = QHBoxLayout(self._progress_widget)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(10)
        self._progress_widget.setVisible(False)

        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("kb-progress-bar")
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setTextVisible(False)

        self._progress_label = QLabel("Indexing…")
        self._progress_label.setObjectName("kb-progress-label")
        self._progress_label.setFixedWidth(80)

        self._progress_file = QLabel()
        self._progress_file.setObjectName("kb-progress-file")
        self._progress_file.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setObjectName("kb-cancel-btn")
        self._cancel_btn.setFixedHeight(24)
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.clicked.connect(self.cancel_requested.emit)

        progress_layout.addWidget(self._progress_bar, stretch=1)
        progress_layout.addWidget(self._progress_label)
        progress_layout.addWidget(self._progress_file, stretch=1)
        progress_layout.addWidget(self._cancel_btn)

        self._layout.addWidget(self._idle_widget, stretch=1)
        self._layout.addWidget(self._progress_widget, stretch=1)

    # ----------------------------------------------------------------- force menu

    def _show_force_menu(self):
        menu = QMenu(self)
        force_action = QAction("Force Full Re-Index", self)
        force_action.triggered.connect(lambda: self.reindex_requested.emit(True))
        menu.addAction(force_action)
        menu.exec(self._force_btn.mapToGlobal(
            self._force_btn.rect().bottomLeft()
        ))

    # ----------------------------------------------------------------- public API

    def load_scan(self, result):
        """Update display from a KBScanResult."""
        self._set_idle_mode()

        if result.total_files == 0:
            self._set_dot("empty")
            self._status_text.setText("Knowledge base is empty — add .md files to knowledge/")
            self._reindex_btn.setEnabled(False)
            self._stale_badge.setVisible(False)
            return

        self._reindex_btn.setEnabled(True)

        if not result.needs_reindex:
            self._set_dot("ok")
            self._status_text.setText(
                f"{result.indexed_count} / {result.total_files} docs indexed"
            )
            self._stale_badge.setVisible(False)
        else:
            self._set_dot("warn")
            self._status_text.setText(
                f"{result.indexed_count} / {result.total_files} docs indexed"
            )
            pending = result.new_count + result.stale_count
            self._stale_badge.setText(f"{pending} pending")
            self._stale_badge.setVisible(True)

    def start_indexing(self, total: int):
        """Switch to progress mode."""
        self._is_indexing = True
        self._idle_widget.setVisible(False)
        self._progress_widget.setVisible(True)
        self._progress_bar.setMinimum(0)
        self._progress_bar.setMaximum(max(total, 1))
        self._progress_bar.setValue(0)
        self._progress_label.setText("0 / ?")
        self._progress_file.setText("Starting…")

    def update_progress(self, done: int, total: int, filename: str):
        self._progress_bar.setMaximum(max(total, 1))
        self._progress_bar.setValue(done)
        self._progress_label.setText(f"{done} / {total}")
        # Truncate long paths
        short = filename.replace("\\", "/").split("/")[-1]
        self._progress_file.setText(short)

    def finish_indexing(self, new_files: int, total_files: int):
        self._is_indexing = False
        self._set_idle_mode()
        self._set_dot("ok")
        if new_files == 0:
            self._status_text.setText(
                f"{total_files} docs indexed — already up to date"
            )
        else:
            self._status_text.setText(
                f"{total_files} docs indexed — {new_files} new this run"
            )
        self._stale_badge.setVisible(False)
        self._reindex_btn.setEnabled(True)

    def fail_indexing(self, msg: str):
        self._is_indexing = False
        self._set_idle_mode()
        self._set_dot("error")
        self._status_text.setText(f"Index error: {msg[:80]}")
        self._reindex_btn.setEnabled(True)

    # ----------------------------------------------------------------- helpers

    def _set_idle_mode(self):
        self._idle_widget.setVisible(True)
        self._progress_widget.setVisible(False)

    def _set_dot(self, state: str):
        # state: ok | warn | error | empty
        obj_names = {
            "ok": "kb-status-dot-ok",
            "warn": "kb-status-dot-warn",
            "error": "kb-status-dot-error",
            "empty": "kb-status-dot-empty",
        }
        self._status_dot.setObjectName(obj_names.get(state, "kb-status-dot-ok"))
        self._status_dot.style().unpolish(self._status_dot)
        self._status_dot.style().polish(self._status_dot)
