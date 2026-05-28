"""
emulation_panel.py — Mimir Emulation Panel

Displays the retro gaming library and provides a launch point for RetroArch.
RetroArch runs externally (its own full-screen UI) — this panel is the
Mimir-side launcher and ROM library overview.

Layout:
  [Toolbar — title + Open ROM Folder button]
  [Status banner — RetroArch present/missing + total ROM count]
  [Platform grid — tile per platform with name and ROM count]
  [Launch RetroArch CTA button]

Platform grid auto-refreshes when the panel becomes visible (showEvent),
so adding ROMs while Mimir is running is reflected immediately on next visit.

If retroarch.exe is missing, the Launch button is disabled and a clear
"not found" message is shown with the expected path.

Public API:
  set_paths(paths)          — wire MimirPaths after construction
  refresh()                 — re-scan ROM directories and update tiles
"""

import subprocess
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QSizePolicy, QScrollArea
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from retroarch_config import (
    PLATFORMS,
    scan_roms,
    write_retroarch_config,
    scaffold_retroarch_dirs,
)


# Platform display metadata: dir_name → (label, icon)
_PLATFORM_META = {
    "nes":     ("NES",            "🎮"),
    "snes":    ("SNES",           "🎮"),
    "n64":     ("Nintendo 64",    "🕹"),
    "gba":     ("Game Boy Adv.",  "🎮"),
    "ps1":     ("PlayStation",    "💿"),
    "ps2":     ("PlayStation 2",  "💿"),
    "genesis": ("Genesis",        "🎮"),
    "arcade":  ("Arcade",         "🕹"),
}


class _PlatformTile(QWidget):
    """Single platform card: icon, name, ROM count."""

    def __init__(self, dir_name: str, parent=None):
        super().__init__(parent)
        self._dir_name = dir_name
        label, icon = _PLATFORM_META.get(dir_name, (dir_name.upper(), "🎮"))

        self.setObjectName("emu-platform-tile")
        self.setFixedSize(130, 100)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel(icon)
        icon_lbl.setObjectName("emu-platform-icon")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_font = QFont()
        icon_font.setPointSize(22)
        icon_lbl.setFont(icon_font)

        name_lbl = QLabel(label)
        name_lbl.setObjectName("emu-platform-name")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setWordWrap(True)
        name_font = QFont()
        name_font.setPointSize(9)
        name_font.setWeight(QFont.Weight.Bold)
        name_lbl.setFont(name_font)

        self._count_lbl = QLabel("—")
        self._count_lbl.setObjectName("emu-platform-count")
        self._count_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        count_font = QFont()
        count_font.setPointSize(9)
        self._count_lbl.setFont(count_font)

        layout.addWidget(icon_lbl)
        layout.addWidget(name_lbl)
        layout.addWidget(self._count_lbl)

    def set_count(self, count: int):
        if count == 0:
            self._count_lbl.setText("no ROMs")
            self._count_lbl.setProperty("empty", True)
        elif count == 1:
            self._count_lbl.setText("1 ROM")
            self._count_lbl.setProperty("empty", False)
        else:
            self._count_lbl.setText(f"{count} ROMs")
            self._count_lbl.setProperty("empty", False)
        # Force QSS refresh
        self._count_lbl.style().unpolish(self._count_lbl)
        self._count_lbl.style().polish(self._count_lbl)

    @property
    def dir_name(self) -> str:
        return self._dir_name


class _StatusBanner(QWidget):
    """
    Top banner showing RetroArch availability and total ROM count.
    Green dot + summary if OK; orange warning if retroarch.exe missing.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("emu-status-banner")
        self.setFixedHeight(40)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(10)

        self._dot = QLabel("●")
        self._dot.setObjectName("emu-status-dot-ok")
        self._dot.setFixedWidth(14)

        self._text = QLabel("Checking...")
        self._text.setObjectName("emu-status-text")

        layout.addWidget(self._dot)
        layout.addWidget(self._text)
        layout.addStretch()

    def set_ok(self, total_roms: int):
        self._dot.setObjectName("emu-status-dot-ok")
        self._dot.style().unpolish(self._dot)
        self._dot.style().polish(self._dot)
        if total_roms == 0:
            self._text.setText("RetroArch ready — no ROMs loaded yet. Add ROMs to the roms/ folder.")
        else:
            self._text.setText(
                f"RetroArch ready — {total_roms} ROM{'s' if total_roms != 1 else ''} across all platforms."
            )

    def set_missing(self, expected_path: str):
        self._dot.setObjectName("emu-status-dot-warn")
        self._dot.style().unpolish(self._dot)
        self._dot.style().polish(self._dot)
        self._text.setText(
            f"retroarch.exe not found. Expected: {expected_path}"
        )

    def set_no_cores(self):
        self._dot.setObjectName("emu-status-dot-warn")
        self._dot.style().unpolish(self._dot)
        self._dot.style().polish(self._dot)
        self._text.setText(
            "RetroArch found but no cores installed. Download cores via RetroArch's Online Updater."
        )


class EmulationPanel(QWidget):
    """
    Mimir emulation launcher panel.
    Shows ROM library overview and launches RetroArch as an external process.
    """

    def __init__(self, paths=None, parent=None):
        super().__init__(parent)
        self._paths = paths
        self._tiles: dict[str, _PlatformTile] = {}

        self.setObjectName("emu-panel")
        self._setup_ui()

        if paths:
            self.refresh()

    # ----------------------------------------------------------------- layout

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ---- Toolbar ----
        toolbar = QWidget()
        toolbar.setObjectName("emu-toolbar")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(16, 10, 16, 10)
        tb.setSpacing(10)

        title = QLabel("Emulation")
        title.setObjectName("emu-title")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setWeight(QFont.Weight.Bold)
        title.setFont(title_font)

        self._open_roms_btn = QPushButton("Open ROM Folder")
        self._open_roms_btn.setObjectName("emu-open-btn")
        self._open_roms_btn.setFixedHeight(28)
        self._open_roms_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_roms_btn.clicked.connect(self._open_roms_folder)

        self._refresh_btn = QPushButton("↺ Refresh")
        self._refresh_btn.setObjectName("emu-refresh-btn")
        self._refresh_btn.setFixedHeight(28)
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.clicked.connect(self.refresh)

        tb.addWidget(title)
        tb.addStretch()
        tb.addWidget(self._refresh_btn)
        tb.addWidget(self._open_roms_btn)
        layout.addWidget(toolbar)

        # ---- Separator ----
        sep0 = QFrame()
        sep0.setFrameShape(QFrame.Shape.HLine)
        sep0.setObjectName("kb-separator")
        layout.addWidget(sep0)

        # ---- Status banner ----
        self._banner = _StatusBanner()
        layout.addWidget(self._banner)

        # ---- Separator ----
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setObjectName("kb-separator")
        layout.addWidget(sep1)

        # ---- Scrollable body ----
        scroll = QScrollArea()
        scroll.setObjectName("emu-scroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        body = QWidget()
        body.setObjectName("emu-body")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(32, 32, 32, 32)
        body_layout.setSpacing(32)
        body_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Section label
        section_label = QLabel("ROM LIBRARY")
        section_label.setObjectName("emu-section-label")
        body_layout.addWidget(section_label)

        # Platform grid
        grid_container = QWidget()
        grid_container.setObjectName("emu-grid-container")
        self._grid = QGridLayout(grid_container)
        self._grid.setSpacing(12)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        # Build tiles for each platform
        for col, (dir_name, _, _) in enumerate(PLATFORMS):
            tile = _PlatformTile(dir_name)
            self._tiles[dir_name] = tile
            row = col // 4
            col_pos = col % 4
            self._grid.addWidget(tile, row, col_pos)

        body_layout.addWidget(grid_container)

        # ---- BIOS hint ----
        bios_hint = QLabel(
            "💡  PS1 / PS2 require BIOS files in  retroarch/system/.  "
            "NES, SNES, N64, GBA, and Genesis run without BIOS."
        )
        bios_hint.setObjectName("emu-bios-hint")
        bios_hint.setWordWrap(True)
        body_layout.addWidget(bios_hint)

        body_layout.addStretch()

        # ---- Launch button ----
        launch_container = QWidget()
        lc_layout = QHBoxLayout(launch_container)
        lc_layout.setContentsMargins(0, 0, 0, 0)
        lc_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._launch_btn = QPushButton("Launch RetroArch")
        self._launch_btn.setObjectName("emu-launch-btn")
        self._launch_btn.setFixedHeight(52)
        self._launch_btn.setFixedWidth(240)
        self._launch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._launch_btn.clicked.connect(self._launch_retroarch)
        launch_font = QFont()
        launch_font.setPointSize(13)
        launch_font.setWeight(QFont.Weight.Bold)
        self._launch_btn.setFont(launch_font)

        lc_layout.addWidget(self._launch_btn)
        body_layout.addWidget(launch_container)

        scroll.setWidget(body)
        layout.addWidget(scroll, stretch=1)

    # ----------------------------------------------------------------- slots

    def _launch_retroarch(self):
        if not self._paths:
            return

        # Write portable config before launch (idempotent)
        try:
            scaffold_retroarch_dirs(self._paths)
            write_retroarch_config(self._paths)
        except Exception as e:
            print(f"[RetroArch] Config write warning: {e}")

        exe = self._paths.retroarch_exe
        if not exe.exists():
            return

        try:
            subprocess.Popen(
                [str(exe)],
                cwd=str(exe.parent),   # Run from retroarch/ so relative paths work
                creationflags=0        # Show window (RetroArch has its own UI)
            )
        except Exception as e:
            print(f"[RetroArch] Launch failed: {e}")

    def _open_roms_folder(self):
        if not self._paths:
            return
        try:
            subprocess.Popen(["explorer", str(self._paths.roms)])
        except Exception:
            pass

    # ----------------------------------------------------------------- public

    def set_paths(self, paths):
        self._paths = paths
        self.refresh()

    def refresh(self):
        """Re-scan ROM directories and update all tiles + status banner."""
        if not self._paths:
            return

        # Check RetroArch presence
        retroarch_present = self._paths.retroarch_exe.exists()
        self._launch_btn.setEnabled(retroarch_present)
        self._launch_btn.setProperty("disabled_look", not retroarch_present)
        self._launch_btn.style().unpolish(self._launch_btn)
        self._launch_btn.style().polish(self._launch_btn)

        # Scan ROM counts
        counts = scan_roms(self._paths)
        total = sum(counts.values())

        # Update tiles
        for dir_name, tile in self._tiles.items():
            tile.set_count(counts.get(dir_name, 0))

        # Update banner
        if not retroarch_present:
            self._banner.set_missing(str(self._paths.retroarch_exe))
        else:
            # Check if any cores are installed
            cores_dir = self._paths.retroarch_cores
            has_cores = (
                cores_dir.exists() and
                any(f.suffix.lower() == ".dll" for f in cores_dir.iterdir())
                if cores_dir.exists() else False
            )
            if not has_cores:
                self._banner.set_no_cores()
            else:
                self._banner.set_ok(total)

    def showEvent(self, event):
        """Refresh ROM counts every time the panel is shown."""
        super().showEvent(event)
        # Slight delay so the panel fully renders first
        QTimer.singleShot(50, self.refresh)
