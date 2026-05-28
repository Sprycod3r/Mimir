"""
intro_screen.py — Mimir Identity Intro Screen

Full-window animated intro. Shows on first launch (or when skip_intro is False).
Particle field runs in the background. Content is layered on top.

Signals:
  continue_to_main  — user clicked "Let's Go" or already has skip_intro=True
  start_tutorial    — user clicked "Show Me Around"

Both signals carry no payload. The caller decides what screen to load next.

skip_intro logic:
  - If "Don't show again" is checked on dismiss, settings.skip_intro is set True
  - Main never calls this screen if skip_intro is already True (caller's responsibility)
  - This screen does not read skip_intro itself — it always shows if instantiated
"""

from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QSizePolicy, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QColor, QFont

from ui.particle_animation import ParticleField


INTRO_LINES = [
    "I'm Mimir.",
    "I live on this drive.",
    "No cloud. No phone-home. No one watching over your shoulder.",
    "Everything here — your files, your questions, your knowledge base — stays with you.",
    "I'm not a product. I'm a tool. Your tool.",
    "Let me show you around, or just get out of your way.",
]


class IntroScreen(QWidget):
    """
    Animated intro screen with particle field background.
    Emits continue_to_main or start_tutorial on dismiss.
    """

    continue_to_main = pyqtSignal()
    start_tutorial = pyqtSignal()

    def __init__(self, settings, theme_manager, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._theme = theme_manager

        self._setup_ui()
        self._apply_colors()
        self._start_fade_in()

    # ------------------------------------------------------------------ layout

    def _setup_ui(self):
        # Particle field fills the whole widget — it's the background
        self._particles = ParticleField(self)
        self._particles.setGeometry(0, 0, self.width(), self.height())

        # Content panel — centered, fixed width, transparent bg (no card border)
        self._content = QWidget(self)
        self._content.setObjectName("intro-content")
        self._content.setFixedWidth(560)
        self._content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Wordmark
        self._wordmark = QLabel("MIMIR")
        self._wordmark.setObjectName("intro-wordmark")
        self._wordmark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wordmark_font = QFont()
        wordmark_font.setPointSize(52)
        wordmark_font.setWeight(QFont.Weight.Bold)
        wordmark_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 12.0)
        self._wordmark.setFont(wordmark_font)
        content_layout.addWidget(self._wordmark)

        content_layout.addSpacing(6)

        # Tagline
        self._tagline = QLabel("Offline Intelligence. Your Rules.")
        self._tagline.setObjectName("intro-tagline")
        self._tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline_font = QFont()
        tagline_font.setPointSize(11)
        tagline_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3.5)
        self._tagline.setFont(tagline_font)
        content_layout.addWidget(self._tagline)

        content_layout.addSpacing(48)

        # Intro text block
        self._intro_label = QLabel()
        self._intro_label.setObjectName("intro-text")
        self._intro_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._intro_label.setWordWrap(True)
        intro_font = QFont()
        intro_font.setPointSize(12)
        intro_font.setWeight(QFont.Weight.Normal)
        self._intro_label.setFont(intro_font)
        self._intro_label.setText(
            "No cloud. No phone-home. No one watching over your shoulder.\n\n"
            "Everything here — your files, your questions, your knowledge base — "
            "stays with you.\n\n"
            "I'm not a product. I'm a tool. Your tool."
        )
        content_layout.addWidget(self._intro_label)

        content_layout.addSpacing(52)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._btn_tour = QPushButton("Show Me Around")
        self._btn_tour.setObjectName("intro-btn-tour")
        self._btn_tour.setFixedSize(200, 48)
        self._btn_tour.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_tour.clicked.connect(self._on_tour)

        self._btn_go = QPushButton("Let's Go")
        self._btn_go.setObjectName("intro-btn-go")
        self._btn_go.setFixedSize(160, 48)
        self._btn_go.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_go.clicked.connect(self._on_go)

        btn_row.addWidget(self._btn_tour)
        btn_row.addWidget(self._btn_go)
        content_layout.addLayout(btn_row)

        content_layout.addSpacing(24)

        # Don't show again link
        self._dont_show = QPushButton("Don't show this again")
        self._dont_show.setObjectName("intro-link")
        self._dont_show.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dont_show.setFlat(True)
        self._dont_show.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self._dont_show.clicked.connect(self._on_dont_show)
        link_row = QHBoxLayout()
        link_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        link_row.addWidget(self._dont_show)
        content_layout.addLayout(link_row)

        # Initial opacity — will fade in
        self._content.setWindowOpacity(0.0)
        self._opacity = 0.0

    # -------------------------------------------------- positioning / resize

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Keep particle field filling the whole widget
        self._particles.setGeometry(0, 0, self.width(), self.height())
        # Keep content panel centered
        self._center_content()

    def _center_content(self):
        w = self.width()
        h = self.height()
        cw = self._content.width()
        ch = self._content.sizeHint().height()
        # Slight vertical offset upward from true center for visual balance
        x = (w - cw) // 2
        y = max(40, (h - ch) // 2 - 20)
        self._content.move(x, y)
        self._content.adjustSize()

    # ---------------------------------------------------------- fade in

    def _start_fade_in(self):
        """Step the content panel from invisible to visible over ~600ms."""
        self._fade_step = 0
        self._fade_timer = QTimer(self)
        self._fade_timer.timeout.connect(self._tick_fade)
        self._fade_timer.start(20)  # 20ms ticks → 30 steps → ~600ms

    def _tick_fade(self):
        self._fade_step += 1
        t = min(self._fade_step / 30.0, 1.0)
        # Ease out cubic
        t_eased = 1.0 - (1.0 - t) ** 3
        self._set_content_opacity(t_eased)
        if self._fade_step >= 30:
            self._fade_timer.stop()
            self._set_content_opacity(1.0)

    def _set_content_opacity(self, value: float):
        """
        PyQt6 doesn't support per-widget opacity outside QGraphicsEffect,
        so we simulate it by adjusting label/button colors on the fly.
        For a clean result we use a stylesheet alpha approach on the content
        widget's children.
        """
        self._opacity = value
        alpha = int(value * 255)
        self._apply_colors(alpha)

    # ---------------------------------------------------------- colors / theme

    def _apply_colors(self, alpha: int = 255):
        theme = self._theme.current_theme() if self._theme else {}

        accent = theme.get("accent_primary", "#8B5CF6")
        accent2 = theme.get("accent_secondary", "#22D3A5")
        text_primary = theme.get("text_primary", "#E8E8F0")
        text_muted = theme.get("text_muted", "#6B7280")
        surface = theme.get("surface", "#1A1A26")

        # Convert hex to rgba for stylesheet
        def hex_to_rgba(hex_color: str, a: int) -> str:
            c = QColor(hex_color)
            return f"rgba({c.red()},{c.green()},{c.blue()},{a})"

        wm_color = hex_to_rgba(accent, alpha)
        tag_color = hex_to_rgba(accent2, min(alpha, 200))
        text_color = hex_to_rgba(text_primary, alpha)
        muted_color = hex_to_rgba(text_muted, alpha)

        # Button background (slightly transparent surface)
        surf_color = hex_to_rgba(surface, min(alpha, 220))

        self._content.setStyleSheet(f"""
            QLabel#intro-wordmark {{
                color: {wm_color};
                background: transparent;
            }}
            QLabel#intro-tagline {{
                color: {tag_color};
                background: transparent;
            }}
            QLabel#intro-text {{
                color: {text_color};
                background: transparent;
                line-height: 1.6;
            }}
            QPushButton#intro-btn-tour {{
                background-color: {hex_to_rgba(accent, min(alpha, 230))};
                color: rgba(255,255,255,{alpha});
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 600;
                padding: 0 20px;
            }}
            QPushButton#intro-btn-tour:hover {{
                background-color: {hex_to_rgba(accent, 255)};
            }}
            QPushButton#intro-btn-go {{
                background-color: transparent;
                color: {text_color};
                border: 1px solid {hex_to_rgba(accent, min(alpha, 140))};
                border-radius: 6px;
                font-size: 13px;
                font-weight: 500;
                padding: 0 20px;
            }}
            QPushButton#intro-btn-go:hover {{
                border-color: {wm_color};
                color: {wm_color};
            }}
            QPushButton#intro-link {{
                color: {muted_color};
                background: transparent;
                border: none;
                font-size: 11px;
                text-decoration: underline;
                padding: 0;
            }}
            QPushButton#intro-link:hover {{
                color: {text_color};
            }}
        """)

        self._center_content()

    # ---------------------------------------------------------- button actions

    def _on_tour(self):
        self.start_tutorial.emit()

    def _on_go(self):
        self.continue_to_main.emit()

    def _on_dont_show(self):
        self._settings.skip_intro = True
        self._settings.save()
        self.continue_to_main.emit()

    # ---------------------------------------------------------- public API

    def set_colors(self, bg_color: str, particle_color: str, line_color: str = None):
        """Relay theme color update to the particle field."""
        self._particles.set_colors(bg_color, particle_color, line_color)
        self._apply_colors(int(self._opacity * 255))

    def stop_animation(self):
        """Pause particle field when screen is not visible — saves CPU."""
        self._particles.stop()

    def start_animation(self):
        """Resume particle field."""
        self._particles.start()
