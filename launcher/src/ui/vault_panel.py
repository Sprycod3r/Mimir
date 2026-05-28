"""
vault_panel.py — Mimir Personal Vault

Displays files stored in Mimir/vault/. Access is gated by PIN verification
in MainInterface before this panel is ever shown — the panel itself has no
knowledge of PINs or encryption keys. Vault files are not encrypted at rest
(the PIN is an access gate, not a file cipher). Conversation log encryption
is handled separately in chat_panel.py.

Usage:
  Treated like any other panel in MainInterface's QStackedWidget.
  MainInterface calls VaultPanel.refresh() if needed when navigating to it.
"""

import os
import subprocess

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class VaultPanel(QWidget):
    """
    File browser for the vault directory.
    Double-click a file to open it with the system default app.
    """

    def __init__(self, paths, parent=None):
        super().__init__(parent)
        self._paths = paths
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # ── Header ──
        header_row = QHBoxLayout()
        title = QLabel("Personal Vault")
        title.setObjectName("settings-title")
        tf = QFont()
        tf.setPointSize(18)
        tf.setWeight(QFont.Weight.Bold)
        title.setFont(tf)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("settings-btn")
        refresh_btn.setFixedSize(80, 32)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh)

        open_btn = QPushButton("Open Folder")
        open_btn.setObjectName("settings-btn")
        open_btn.setFixedSize(110, 32)
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(self._open_folder)

        header_row.addWidget(title)
        header_row.addStretch()
        header_row.addWidget(refresh_btn)
        header_row.addWidget(open_btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("settings-separator")

        note = QLabel(
            "Files placed in Mimir/vault/ appear here. "
            "Access requires your vault PIN each session."
        )
        note.setObjectName("sidebar-status")
        note.setWordWrap(True)

        self._file_list = QListWidget()
        self._file_list.setObjectName("logs-list")
        self._file_list.itemDoubleClicked.connect(self._on_open_file)

        layout.addLayout(header_row)
        layout.addWidget(sep)
        layout.addWidget(note)
        layout.addWidget(self._file_list, stretch=1)

        self.refresh()

    def refresh(self):
        """Reload the file list from disk."""
        self._file_list.clear()
        if not self._paths:
            return
        vault_dir = self._paths.vault
        if not vault_dir.exists():
            return
        items = sorted(vault_dir.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        for item in items:
            if item.name.startswith("."):
                continue
            prefix = "📁 " if item.is_dir() else "📄 "
            list_item = QListWidgetItem(prefix + item.name)
            list_item.setData(Qt.ItemDataRole.UserRole, str(item))
            self._file_list.addItem(list_item)

    def _on_open_file(self, item: QListWidgetItem):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            try:
                os.startfile(path)
            except Exception:
                pass

    def _open_folder(self):
        if self._paths and self._paths.vault.exists():
            subprocess.Popen(["explorer", str(self._paths.vault)])

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
