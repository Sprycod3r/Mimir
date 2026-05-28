"""
kb_scanner.py — Mimir Knowledge Base Pre-Flight Scanner

Reads the knowledge/ directory and the KB manifest to produce a snapshot
of index state without making any network calls or AnythingLLM requests.

Fast — runs synchronously in under a second for typical KB sizes.
Safe — read-only; never modifies the manifest or uploads anything.

Usage:
    scanner = KBScanner(knowledge_dir, manifest_path)
    result = scanner.scan()
    print(result.summary_line)

KBScanResult fields:
    total_files         — .md files found on disk (excluding _README.md)
    indexed_count       — files in manifest with matching mtime
    stale_count         — files in manifest whose mtime has changed
    new_count           — files on disk not in manifest at all
    missing_count       — files in manifest no longer on disk
    last_index_ts       — ISO timestamp of last full index, or None
    per_domain          — dict[domain_name, DomainStats]
    needs_reindex       — True if stale_count > 0 or new_count > 0
"""

import os
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class DomainStats:
    total: int = 0
    indexed: int = 0
    stale: int = 0
    new: int = 0


@dataclass
class KBScanResult:
    total_files: int = 0
    indexed_count: int = 0
    stale_count: int = 0
    new_count: int = 0
    missing_count: int = 0
    last_index_ts: Optional[str] = None
    per_domain: Dict[str, DomainStats] = field(default_factory=dict)

    @property
    def needs_reindex(self) -> bool:
        return self.stale_count > 0 or self.new_count > 0

    @property
    def summary_line(self) -> str:
        if self.total_files == 0:
            return "Knowledge base is empty — add .md files to knowledge/"
        if self.indexed_count == self.total_files and not self.needs_reindex:
            ts = self._fmt_ts(self.last_index_ts)
            return f"{self.indexed_count} / {self.total_files} docs indexed{ts}"
        parts = []
        if self.new_count:
            parts.append(f"{self.new_count} new")
        if self.stale_count:
            parts.append(f"{self.stale_count} changed")
        if self.missing_count:
            parts.append(f"{self.missing_count} removed")
        pending = ", ".join(parts)
        return (
            f"{self.indexed_count} / {self.total_files} docs indexed"
            f" — {pending} pending re-index"
        )

    @property
    def status_label(self) -> str:
        """Short status for sidebar display."""
        if self.total_files == 0:
            return "KB empty"
        if not self.needs_reindex:
            return f"{self.indexed_count} docs indexed"
        return f"{self.indexed_count}/{self.total_files} indexed ({self.new_count + self.stale_count} pending)"

    def _fmt_ts(self, ts: Optional[str]) -> str:
        if not ts:
            return ""
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return f" (last indexed {dt.strftime('%b %d %H:%M')})"
        except Exception:
            return ""


class KBScanner:
    """
    Scans knowledge/ dir and compares against the manifest.
    Read-only — makes no network calls.
    """

    def __init__(self, knowledge_dir: Path, manifest_path: Path):
        self._knowledge_dir = knowledge_dir
        self._manifest_path = manifest_path

    def scan(self) -> KBScanResult:
        result = KBScanResult()

        # Load manifest
        manifest_indexed = {}
        if self._manifest_path.exists():
            try:
                data = json.loads(self._manifest_path.read_text(encoding="utf-8"))
                manifest_indexed = data.get("indexed", {})
                result.last_index_ts = data.get("last_full_index")
            except Exception:
                pass

        if not self._knowledge_dir.exists():
            return result

        # Walk knowledge dir
        seen_paths = set()
        for root, dirs, files in os.walk(self._knowledge_dir):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            for filename in sorted(files):
                if not filename.lower().endswith(".md"):
                    continue
                if filename == "_README.md":
                    continue  # scaffold readmes are not content

                abs_path = Path(root) / filename
                rel_path = str(abs_path.relative_to(self._knowledge_dir))
                domain = Path(rel_path).parts[0] if Path(rel_path).parts else "general"

                # Ensure domain entry exists
                if domain not in result.per_domain:
                    result.per_domain[domain] = DomainStats()
                ds = result.per_domain[domain]

                result.total_files += 1
                ds.total += 1
                seen_paths.add(rel_path)

                try:
                    mtime = abs_path.stat().st_mtime
                except OSError:
                    mtime = 0.0

                if rel_path in manifest_indexed:
                    manifest_mtime = manifest_indexed[rel_path].get("mtime", 0)
                    if abs(manifest_mtime - mtime) < 0.01:
                        result.indexed_count += 1
                        ds.indexed += 1
                    else:
                        result.stale_count += 1
                        ds.stale += 1
                else:
                    result.new_count += 1
                    ds.new += 1

        # Count manifest entries whose files are gone
        for rel_path in manifest_indexed:
            if rel_path not in seen_paths:
                result.missing_count += 1

        return result

    def quick_count(self) -> int:
        """Just return the total number of indexed files from the manifest."""
        if not self._manifest_path.exists():
            return 0
        try:
            data = json.loads(self._manifest_path.read_text(encoding="utf-8"))
            return len(data.get("indexed", {}))
        except Exception:
            return 0
