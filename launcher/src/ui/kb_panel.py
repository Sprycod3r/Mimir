"""
kb_panel.py — Mimir Knowledge Base Browser Panel

Two-pane layout:
  [KBIndexStatusBar — full width top]
  Left  — QTreeView over the knowledge/ directory
  Right — File preview pane (renders .md as plain text with frontmatter stripped)

Actions:
  - Double-click a .md file → load into preview pane
  - "Ask Mimir About This" button → emits context_requested(text, title)
  - "Open in Explorer" button → opens folder in Windows Explorer
  - Re-Index button → triggers KBIndexer in background thread

Signals:
  context_requested(str, str)  — (document_text, document_title)
  reindex_complete(int, int)   — (new_files, total_files)
"""

import os
import re
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeView,
    QLabel, QPushButton, QScrollArea,
    QFrame, QSizePolicy, QTextEdit

)
from PyQt6.QtGui import QFileSystemModel
from PyQt6.QtCore import Qt, pyqtSignal, QDir, QModelIndex
from PyQt6.QtGui import QFont

from ui.kb_index_status import KBIndexStatusBar
from kb_scanner import KBScanner


# Strip YAML frontmatter block (--- ... ---) from markdown
_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


class _FilePreviewPane(QWidget):
    """Right pane: shows file title and content."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("kb-preview-pane")
        self._current_path: Path = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Title bar
        title_bar = QWidget()
        title_bar.setObjectName("kb-preview-title-bar")
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(16, 10, 16, 10)
        tb_layout.setSpacing(8)

        self._title_label = QLabel("Select a file to preview")
        self._title_label.setObjectName("kb-preview-title")
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setWeight(QFont.Weight.Bold)
        self._title_label.setFont(title_font)

        self._ask_btn = QPushButton("Ask Mimir About This")
        self._ask_btn.setObjectName("kb-ask-btn")
        self._ask_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ask_btn.setEnabled(False)
        self._ask_btn.setFixedHeight(32)

        tb_layout.addWidget(self._title_label)
        tb_layout.addStretch()
        tb_layout.addWidget(self._ask_btn)
        layout.addWidget(title_bar)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("kb-separator")
        layout.addWidget(sep)

        # Content area (read-only text edit for easy selection/copy)
        self._content_view = QTextEdit()
        self._content_view.setObjectName("kb-content-view")
        self._content_view.setReadOnly(True)
        content_font = QFont()
        content_font.setPointSize(10)
        self._content_view.setFont(content_font)
        self._content_view.setPlaceholderText(
            "No file selected.\n\nClick a .md file in the tree on the left to preview it here."
        )
        layout.addWidget(self._content_view, stretch=1)

    @property
    def ask_btn(self) -> QPushButton:
        return self._ask_btn

    def load_file(self, path: Path):
        """Load and display a .md file. Strips frontmatter."""
        self._current_path = path
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except IOError as e:
            self._content_view.setPlainText(f"[Could not read file: {e}]")
            return

        # Strip YAML frontmatter
        content = _FRONTMATTER_RE.sub("", raw).strip()

        # Extract title: prefer H1 heading, fall back to filename
        title = path.stem.replace("-", " ").title()
        for line in content.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break

        self._title_label.setText(title)
        self._content_view.setPlainText(content)
        self._ask_btn.setEnabled(True)
        self._ask_btn.setProperty("title", title)

    def get_content(self) -> str:
        return self._content_view.toPlainText()

    def get_title(self) -> str:
        return self._title_label.text()

    def clear(self):
        self._current_path = None
        self._title_label.setText("Select a file to preview")
        self._content_view.clear()
        self._ask_btn.setEnabled(False)


class KBPanel(QWidget):
    """
    Knowledge base browser panel.
    Pass anythingllm_client and manifest_path to enable re-indexing.
    """

    context_requested = pyqtSignal(str, str)   # (text, title)
    reindex_complete = pyqtSignal(int, int)     # (new_files, total_files)

    def __init__(self, knowledge_dir: Path,
                 anythingllm_client=None,
                 manifest_path: Optional[Path] = None,
                 workspace_slug: str = "mimir",
                 parent=None):
        super().__init__(parent)
        self._knowledge_dir = knowledge_dir
        self._atllm_client = anythingllm_client
        self._manifest_path = manifest_path
        self._workspace_slug = workspace_slug
        self._indexer_thread = None
        self.setObjectName("kb-panel")

        self._setup_ui()
        self._run_initial_scan()

    # ----------------------------------------------------------------- layout

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Index status bar (top)
        self._status_bar = KBIndexStatusBar()
        self._status_bar.reindex_requested.connect(self._on_reindex_requested)
        self._status_bar.cancel_requested.connect(self._on_cancel_reindex)
        layout.addWidget(self._status_bar)

        # Separator
        sep0 = QFrame()
        sep0.setFrameShape(QFrame.Shape.HLine)
        sep0.setObjectName("kb-separator")
        layout.addWidget(sep0)

        # Toolbar
        toolbar = QWidget()
        toolbar.setObjectName("kb-toolbar")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(12, 8, 12, 8)
        tb_layout.setSpacing(8)

        title = QLabel("Knowledge Base")
        title.setObjectName("kb-toolbar-title")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setWeight(QFont.Weight.Bold)
        title.setFont(title_font)

        open_btn = QPushButton("Open Folder")
        open_btn.setObjectName("kb-open-btn")
        open_btn.setFixedHeight(28)
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(self._open_in_explorer)

        tb_layout.addWidget(title)
        tb_layout.addStretch()
        tb_layout.addWidget(open_btn)
        layout.addWidget(toolbar)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("kb-separator")
        layout.addWidget(sep)

        # Splitter: tree (left) + preview (right)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("kb-splitter")
        splitter.setHandleWidth(1)

        # Left: file system tree
        tree_widget = QWidget()
        tree_layout = QVBoxLayout(tree_widget)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(0)

        self._model = QFileSystemModel()
        self._model.setRootPath(str(self._knowledge_dir))
        self._model.setNameFilters(["*.md"])
        self._model.setNameFilterDisables(False)  # hide non-matching files

        self._tree = QTreeView()
        self._tree.setObjectName("kb-tree")
        self._tree.setModel(self._model)
        self._tree.setRootIndex(self._model.index(str(self._knowledge_dir)))
        self._tree.setAnimated(True)
        self._tree.setIndentation(16)
        self._tree.setSortingEnabled(True)
        self._tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self._tree.setMinimumWidth(220)
        self._tree.setMaximumWidth(400)

        # Hide size/type/date columns — just the name
        for col in range(1, self._model.columnCount()):
            self._tree.hideColumn(col)

        self._tree.doubleClicked.connect(self._on_tree_double_click)
        tree_layout.addWidget(self._tree)

        # Right: preview pane
        self._preview = _FilePreviewPane()
        self._preview.ask_btn.clicked.connect(self._on_ask_mimir)

        splitter.addWidget(tree_widget)
        splitter.addWidget(self._preview)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 600])

        layout.addWidget(splitter, stretch=1)

    # ----------------------------------------------------------------- slots

    def _on_tree_double_click(self, index: QModelIndex):
        path = Path(self._model.filePath(index))
        if path.is_file() and path.suffix == ".md":
            self._preview.load_file(path)

    def _on_ask_mimir(self):
        text = self._preview.get_content()
        title = self._preview.get_title()
        if text:
            self.context_requested.emit(text, title)

    def _open_in_explorer(self):
        """Open the knowledge base root in Windows Explorer."""
        import subprocess
        try:
            subprocess.Popen(["explorer", str(self._knowledge_dir)])
        except Exception:
            pass

    # ----------------------------------------------------------------- initial scan

    def _run_initial_scan(self):
        """Quick synchronous scan to populate the status bar on load."""
        if not self._manifest_path:
            return
        scanner = KBScanner(self._knowledge_dir, self._manifest_path)
        result = scanner.scan()
        self._status_bar.load_scan(result)

    # ----------------------------------------------------------------- re-indexing

    def _on_reindex_requested(self, force: bool):
        if self._indexer_thread and self._indexer_thread.isRunning():
            return  # Already running

        if not self._atllm_client or not self._manifest_path:
            return  # No client configured — can't index

        from kb_indexer import KBIndexer
        self._indexer_thread = KBIndexer(
            client=self._atllm_client,
            knowledge_dir=self._knowledge_dir,
            manifest_path=self._manifest_path,
            workspace_slug=self._workspace_slug,
            force_reindex=force,
        )
        self._indexer_thread.progress.connect(self._on_index_progress)
        self._indexer_thread.indexing_complete.connect(self._on_index_complete)
        self._indexer_thread.indexing_failed.connect(self._on_index_failed)
        self._indexer_thread.start()

        # Get total to initialize progress bar
        scanner = KBScanner(self._knowledge_dir, self._manifest_path)
        result = scanner.scan()
        total = result.new_count + result.stale_count if not force else result.total_files
        self._status_bar.start_indexing(total)

    def _on_cancel_reindex(self):
        if self._indexer_thread and self._indexer_thread.isRunning():
            # KBIndexer doesn't have a cancel flag — request quit and wait briefly
            self._indexer_thread.requestInterruption()
        self._run_initial_scan()

    def _on_index_progress(self, done: int, total: int, filename: str):
        self._status_bar.update_progress(done, total, filename)

    def _on_index_complete(self, new_files: int, total_files: int):
        self._status_bar.finish_indexing(new_files, total_files)
        self.reindex_complete.emit(new_files, total_files)
        self.refresh()  # Refresh tree view to show new files

    def _on_index_failed(self, error_msg: str):
        self._status_bar.fail_indexing(error_msg)

    # ----------------------------------------------------------------- public

    def update_index_status(self, new_files: int, total_files: int):
        """Called from main.py when startup indexing completes."""
        self._status_bar.finish_indexing(new_files, total_files)

    def set_clients(self, anythingllm_client, manifest_path: Path,
                    workspace_slug: str = "mimir"):
        """Wire clients after construction if not available at init time."""
        self._atllm_client = anythingllm_client
        self._manifest_path = manifest_path
        self._workspace_slug = workspace_slug
        self._run_initial_scan()

    def refresh(self):
        """Re-scan the knowledge directory (e.g. after adding files)."""
        self._model.setRootPath("")
        self._model.setRootPath(str(self._knowledge_dir))
        self._tree.setRootIndex(self._model.index(str(self._knowledge_dir)))
