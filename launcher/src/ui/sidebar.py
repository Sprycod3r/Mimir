"""
sidebar.py — Mimir Persistent Left Sidebar

Fixed-width (240px) navigation panel. Always visible.

Sections (top to bottom):
  - MIMIR wordmark + active model name + tier badge
  - Service health row (Ollama / AnythingLLM / Jellyfin dots)
  - Navigation buttons
  - Spacer
  - Bottom status strip (theme name, version stub)

Signals:
  nav_changed(str)  — emitted when user clicks a nav button
                      values: "chat", "kb", "media", "emulation",
                               "downloader", "logs", "settings"

Public API:
  set_model(model_id, display_name, tier_label)
  set_service_health(service_id, healthy, error=None)
  set_active_nav(section_id)
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QSpacerItem
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont


# Nav item definitions: (id, display label, icon char)
NAV_ITEMS = [
    ("chat",        "Chat",           "⌨"),
    ("kb",          "Knowledge Base", "📚"),
    ("media",       "Media",          "▶"),
    ("emulation",   "Emulation",      "🎮"),
    ("downloader",  "Downloader",     "⬇"),
    ("vault",       "Vault",          "🔒"),
    ("logs",        "Logs",           "📋"),
    ("settings",    "Settings",       "⚙"),
]

SERVICE_IDS = ["ollama", "anythingllm", "jellyfin"]
SERVICE_LABELS = {"ollama": "Ollama", "anythingllm": "AnythingLLM", "jellyfin": "Jellyfin"}


class _HealthDot(QWidget):
    """Single colored dot + label for a service."""

    def __init__(self, service_id: str, parent=None):
        super().__init__(parent)
        self._id = service_id
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        self._dot = QLabel("●")
        self._dot.setObjectName("health-dot-unknown")
        self._dot.setFixedWidth(14)

        self._label = QLabel(SERVICE_LABELS.get(service_id, service_id))
        self._label.setObjectName("health-dot-label")

        layout.addWidget(self._dot)
        layout.addWidget(self._label)
        layout.addStretch()

    def set_health(self, healthy: bool, error: str = None):
        if error:
            self._dot.setObjectName("health-dot-error")
        elif healthy:
            self._dot.setObjectName("health-dot-ok")
        else:
            self._dot.setObjectName("health-dot-warn")

        # Force style refresh
        self._dot.style().unpolish(self._dot)
        self._dot.style().polish(self._dot)

    def set_unknown(self):
        self._dot.setObjectName("health-dot-unknown")
        self._dot.style().unpolish(self._dot)
        self._dot.style().polish(self._dot)


class _NavButton(QPushButton):
    """Single sidebar navigation button."""

    def __init__(self, section_id: str, icon: str, label: str, parent=None):
        super().__init__(parent)
        self.section_id = section_id
        self.setObjectName("nav-button")
        self.setProperty("active", False)
        self.setCheckable(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(10)

        icon_label = QLabel(icon)
        icon_label.setObjectName("nav-icon")
        icon_label.setFixedWidth(20)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Pass mouse events through to the parent button so clicks register
        icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        text_label = QLabel(label)
        text_label.setObjectName("nav-text")
        text_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        layout.addWidget(icon_label)
        layout.addWidget(text_label)
        layout.addStretch()

        # Disable default button text (we use label child widgets)
        self.setFlat(True)

    def set_active(self, active: bool):
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)


class Sidebar(QWidget):
    """
    Persistent left navigation sidebar.
    Fixed width 240px. Transparent to resize events from parent.
    """

    nav_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(240)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        self._nav_buttons: dict[str, _NavButton] = {}
        self._health_dots: dict[str, _HealthDot] = {}
        self._active_nav = "chat"

        self._setup_ui()

    # ----------------------------------------------------------------- layout

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ---- Header ----
        header = QWidget()
        header.setObjectName("sidebar-header")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 20, 16, 16)
        header_layout.setSpacing(4)

        wordmark = QLabel("MIMIR")
        wordmark.setObjectName("sidebar-wordmark")
        wm_font = QFont()
        wm_font.setPointSize(18)
        wm_font.setWeight(QFont.Weight.Bold)
        wm_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 4.0)
        wordmark.setFont(wm_font)

        self._model_name_label = QLabel("No model selected")
        self._model_name_label.setObjectName("sidebar-model-name")

        self._tier_badge = QLabel("—")
        self._tier_badge.setObjectName("sidebar-tier-badge")
        self._tier_badge.setFixedHeight(18)

        model_row = QHBoxLayout()
        model_row.setSpacing(6)
        model_row.addWidget(self._model_name_label)
        model_row.addWidget(self._tier_badge)
        model_row.addStretch()

        header_layout.addWidget(wordmark)
        header_layout.addLayout(model_row)
        layout.addWidget(header)

        # ---- Separator ----
        layout.addWidget(self._separator())

        # ---- Service health ----
        health_widget = QWidget()
        health_widget.setObjectName("sidebar-health")
        health_layout = QVBoxLayout(health_widget)
        health_layout.setContentsMargins(16, 10, 16, 10)
        health_layout.setSpacing(5)

        health_title = QLabel("SERVICES")
        health_title.setObjectName("sidebar-section-label")

        health_layout.addWidget(health_title)
        for svc_id in SERVICE_IDS:
            dot = _HealthDot(svc_id)
            self._health_dots[svc_id] = dot
            health_layout.addWidget(dot)

        # KB doc count line
        self._kb_status_label = QLabel()
        self._kb_status_label.setObjectName("sidebar-kb-status")
        self._kb_status_label.setVisible(False)
        health_layout.addWidget(self._kb_status_label)

        layout.addWidget(health_widget)

        # ---- Separator ----
        layout.addWidget(self._separator())

        # ---- Navigation ----
        nav_widget = QWidget()
        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setContentsMargins(8, 8, 8, 8)
        nav_layout.setSpacing(2)

        for section_id, label, icon in NAV_ITEMS:
            btn = _NavButton(section_id, icon, label)
            btn.clicked.connect(lambda checked, sid=section_id: self._on_nav_clicked(sid))
            self._nav_buttons[section_id] = btn
            nav_layout.addWidget(btn)

        layout.addWidget(nav_widget)

        # ---- Spacer ----
        layout.addStretch()

        # ---- Bottom strip ----
        layout.addWidget(self._separator())
        bottom = QWidget()
        bottom.setObjectName("sidebar-bottom")
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(16, 8, 16, 12)
        bottom_layout.setSpacing(2)

        self._status_label = QLabel("Mimir — Phase 5")
        self._status_label.setObjectName("sidebar-status")

        bottom_layout.addWidget(self._status_label)
        layout.addWidget(bottom)

        # Set initial active state
        self.set_active_nav("chat")

    def _separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("sidebar-separator")
        return line

    # ----------------------------------------------------------------- slots

    def _on_nav_clicked(self, section_id: str):
        self.set_active_nav(section_id)
        self.nav_changed.emit(section_id)

    # ----------------------------------------------------------------- public API

    def set_model(self, model_id: str, display_name: str, tier_label: str):
        """Update the model name and tier badge in the header."""
        self._model_name_label.setText(display_name)
        self._tier_badge.setText(tier_label.upper())

    def set_service_health(self, service_id: str, healthy: bool, error: str = None):
        """Update the health dot for a specific service."""
        dot = self._health_dots.get(service_id)
        if dot:
            dot.set_health(healthy, error)

    def set_all_services_starting(self):
        """Put all dots in 'unknown' state while services start."""
        for dot in self._health_dots.values():
            dot.set_unknown()

    def set_active_nav(self, section_id: str):
        """Highlight the active navigation button."""
        self._active_nav = section_id
        for sid, btn in self._nav_buttons.items():
            btn.set_active(sid == section_id)

    def set_status(self, text: str):
        self._status_label.setText(text)

    def set_kb_status(self, text: str):
        """Update the KB doc count shown under service health."""
        if not hasattr(self, "_kb_status_label"):
            return
        self._kb_status_label.setText(text)
        self._kb_status_label.setVisible(bool(text))
