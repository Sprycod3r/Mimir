"""
kb_indexer.py — Mimir Knowledge Base Indexer

Scans the knowledge/ directory for .md files, compares against a manifest
of previously indexed documents, and uploads new or changed files to
AnythingLLM for RAG indexing.

Manifest format (kb-manifest.json):
  {
    "indexed": {
      "relative/path/to/file.md": {
        "mtime": 1234567890.0,
        "location": "custom-documents/file-abc123.json",
        "title": "Human-readable title"
      }
    },
    "last_full_index": "2026-04-30T00:00:00"
  }

Runs in a QThread with progress signals.
"""

import os
import json
import time
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime, timezone

from PyQt6.QtCore import QThread, pyqtSignal

from anythingllm_client import AnythingLLMClient, AnythingLLMError


# ============================================================
# Manifest
# ============================================================

class KBManifest:
    """
    Tracks which files have been indexed and when.
    Stored as JSON in the AnythingLLM data directory.
    """

    def __init__(self, manifest_path: Path):
        self._path = manifest_path
        self._data = {"indexed": {}, "last_full_index": None}
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self._data = loaded
            except (json.JSONDecodeError, IOError):
                pass

    def save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    def is_indexed(self, rel_path: str, mtime: float) -> bool:
        """Return True if this file has been indexed at this exact mtime."""
        entry = self._data["indexed"].get(rel_path)
        if not entry:
            return False
        return abs(entry.get("mtime", 0) - mtime) < 0.01

    def get_location(self, rel_path: str) -> Optional[str]:
        """Return the AnythingLLM document location for an indexed file."""
        entry = self._data["indexed"].get(rel_path)
        return entry.get("location") if entry else None

    def mark_indexed(self, rel_path: str, mtime: float,
                     location: str, title: str):
        self._data["indexed"][rel_path] = {
            "mtime": mtime,
            "location": location,
            "title": title
        }

    def remove(self, rel_path: str):
        self._data["indexed"].pop(rel_path, None)

    def all_indexed_paths(self) -> List[str]:
        return list(self._data["indexed"].keys())

    def all_locations(self) -> List[str]:
        return [e.get("location", "") for e in self._data["indexed"].values() if e.get("location")]

    def set_last_full_index(self):
        self._data["last_full_index"] = datetime.now(timezone.utc).isoformat()
        self.save()


# ============================================================
# Indexer
# ============================================================

class KBIndexer(QThread):
    """
    Scans the knowledge base directory and indexes new/changed files
    into AnythingLLM.

    Signals:
      progress(int, int, str)  — (indexed_so_far, total_to_index, current_file)
      file_indexed(str)        — relative path of a newly indexed file
      file_skipped(str)        — relative path skipped (already current)
      indexing_complete(int, int)  — (new_files_indexed, total_files_in_kb)
      indexing_failed(str)     — error message
    """

    progress = pyqtSignal(int, int, str)
    file_indexed = pyqtSignal(str)
    file_skipped = pyqtSignal(str)
    indexing_complete = pyqtSignal(int, int)
    indexing_failed = pyqtSignal(str)

    def __init__(self, client: AnythingLLMClient,
                 knowledge_dir: Path,
                 manifest_path: Path,
                 workspace_slug: str,
                 force_reindex: bool = False,
                 parent=None):
        super().__init__(parent)
        self._client = client
        self._knowledge_dir = knowledge_dir
        self._manifest = KBManifest(manifest_path)
        self._workspace_slug = workspace_slug
        self._force = force_reindex

    def run(self):
        try:
            self._run_indexing()
        except AnythingLLMError as e:
            self.indexing_failed.emit(f"AnythingLLM error during indexing: {e}")
        except Exception as e:
            self.indexing_failed.emit(f"Indexing error: {e}")

    def _run_indexing(self):
        if not self._knowledge_dir.exists():
            self.indexing_complete.emit(0, 0)
            return

        # Discover all .md files
        all_files = self._scan_knowledge_dir()
        total = len(all_files)

        if total == 0:
            self.indexing_complete.emit(0, 0)
            return

        # Determine which files need indexing
        to_index: List[Tuple[Path, str, float]] = []  # (path, rel_path, mtime)
        for abs_path, rel_path in all_files:
            mtime = abs_path.stat().st_mtime
            if self._force or not self._manifest.is_indexed(rel_path, mtime):
                to_index.append((abs_path, rel_path, mtime))
            else:
                self.file_skipped.emit(rel_path)

        # Remove any manifest entries for files that no longer exist
        current_rel_paths = {rp for _, rp in all_files}
        for old_path in self._manifest.all_indexed_paths():
            if old_path not in current_rel_paths:
                old_location = self._manifest.get_location(old_path)
                if old_location:
                    self._client.remove_documents_from_workspace(
                        self._workspace_slug, [old_location]
                    )
                self._manifest.remove(old_path)

        if not to_index:
            self._manifest.set_last_full_index()
            self.indexing_complete.emit(0, total)
            return

        # Upload and index new/changed files
        indexed_count = 0
        new_locations: List[str] = []

        for i, (abs_path, rel_path, mtime) in enumerate(to_index):
            self.progress.emit(i, len(to_index), rel_path)

            title = self._derive_title(abs_path, rel_path)
            content = self._read_file(abs_path)
            if content is None:
                continue

            # Extract frontmatter tags if present
            tags, clean_content = self._extract_frontmatter(content)

            doc = self._client.upload_text_document(
                content=clean_content,
                title=title,
                metadata={
                    "domain": self._derive_domain(rel_path),
                    "path": rel_path,
                    "tags": ", ".join(tags),
                }
            )

            if doc and doc.location:
                self._manifest.mark_indexed(rel_path, mtime, doc.location, title)
                new_locations.append(doc.location)
                indexed_count += 1
                self.file_indexed.emit(rel_path)

            # Save manifest periodically to survive interruption
            if indexed_count % 10 == 0:
                self._manifest.save()

            # Small delay to avoid hammering AnythingLLM
            time.sleep(0.05)

        # Add all new documents to the workspace embedding index at once
        if new_locations:
            self.progress.emit(len(to_index), len(to_index), "Embedding new documents...")
            self._client.add_documents_to_workspace(self._workspace_slug, new_locations)

        self._manifest.set_last_full_index()
        self.indexing_complete.emit(indexed_count, total)

    def _scan_knowledge_dir(self) -> List[Tuple[Path, str]]:
        """Returns list of (absolute_path, relative_path) for all .md files."""
        results = []
        for root, dirs, files in os.walk(self._knowledge_dir):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for filename in sorted(files):
                if filename.lower().endswith(".md"):
                    abs_path = Path(root) / filename
                    rel_path = str(abs_path.relative_to(self._knowledge_dir))
                    results.append((abs_path, rel_path))
        return results

    def _read_file(self, path: Path) -> Optional[str]:
        try:
            return path.read_text(encoding="utf-8")
        except (IOError, UnicodeDecodeError):
            return None

    def _derive_title(self, abs_path: Path, rel_path: str) -> str:
        """
        Derive a human-readable title from the file.
        First checks for a 'title:' line in frontmatter, then falls back
        to the filename with dashes converted to spaces.
        """
        try:
            first_lines = abs_path.read_text(encoding="utf-8")[:500]
            for line in first_lines.splitlines():
                line = line.strip()
                if line.lower().startswith("title:"):
                    title = line[6:].strip().strip('"').strip("'")
                    if title:
                        return title
        except Exception:
            pass
        # Fallback: filename → human string
        stem = abs_path.stem  # e.g. "water-purification-basics"
        return stem.replace("-", " ").replace("_", " ").title()

    def _derive_domain(self, rel_path: str) -> str:
        """Returns the top-level domain folder from the relative path."""
        parts = Path(rel_path).parts
        return parts[0] if parts else "general"

    def _extract_frontmatter(self, content: str) -> Tuple[List[str], str]:
        """
        Parse YAML frontmatter (--- delimited) from a markdown file.
        Returns (tags_list, content_without_frontmatter).
        """
        tags = []
        if not content.startswith("---"):
            return tags, content

        lines = content.splitlines()
        end_idx = None
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                end_idx = i
                break

        if end_idx is None:
            return tags, content

        frontmatter_lines = lines[1:end_idx]
        clean_content = "\n".join(lines[end_idx + 1:]).strip()

        for line in frontmatter_lines:
            if line.lower().startswith("tags:"):
                raw_tags = line[5:].strip()
                tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
                break

        return tags, clean_content


# ============================================================
# Convenience: get indexer status summary
# ============================================================

def get_manifest_summary(manifest_path: Path) -> dict:
    """Returns a quick summary of the knowledge base index state."""
    if not manifest_path.exists():
        return {"indexed_count": 0, "last_index": None}
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "indexed_count": len(data.get("indexed", {})),
            "last_index": data.get("last_full_index")
        }
    except Exception:
        return {"indexed_count": 0, "last_index": None}
