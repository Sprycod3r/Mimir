"""
tutorial_overlay.py — Mimir First-Run Tutorial Overlay

A 7-step guided tour rendered as a floating panel over the main interface.
Does NOT use a spotlight in Phase 4 — spotlight highlighting is stubbed and
wired up in Phase 5 when the main UI elements exist to point at.

Steps are defined as data (title + body + optional target_widget_name).
The overlay moves/resizes to sit near the target widget when one is named.
If no target is named (or target not found), the panel centers on screen.

Signals:
  finished  — user completed all steps or clicked Skip at any point

Usage:
  overlay = TutorialOverlay(steps=TUTORIAL_STEPS, parent=main_window)
  overlay.finished.connect(on_tutorial_done)
  overlay.show()
"""

from dataclasses import dataclass, field
from typing import Optional, List

from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout,
    QSizePolicy, QApplication, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QTimer, QPoint, QSize
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QFont


# ---------------------------------------------------------------- step data


@dataclass
class TutorialStep:
    title: str
    body: str
    target_widget_name: Optional[str] = None   # objectName of widget to point near
    panel_side: str = "bottom"                  # preferred side: top / bottom / left / right


TUTORIAL_STEPS: List[TutorialStep] = [
    TutorialStep(
        title="Your Model",
        body=(
            "You chose a model tier at launch. You can switch tiers any time "
            "from the model switcher in the toolbar — Mimir will reload with "
            "the new model automatically."
        ),
        target_widget_name="model-switcher-widget",
        panel_side="bottom",
    ),
    TutorialStep(
        title="Talking to Mimir",
        body=(
            "Type a question or command in the chat bar at the bottom. "
            "Mimir responds in the main panel. Responses stream in live — "
            "no waiting for the full reply before you start reading."
        ),
        target_widget_name="chat-input",
        panel_side="top",
    ),
    TutorialStep(
        title="Knowledge Base",
        body=(
            "The KB panel on the left shows your personal knowledge base — "
            "organized folders where you can drop .md files. Mimir reads them "
            "and can reference them when you ask questions."
        ),
        target_widget_name="kb-panel",
        panel_side="right",
    ),
    TutorialStep(
        title="Side-by-Side Mode",
        body=(
            "Hit the split-view button in the toolbar to open a second chat "
            "panel. Useful for comparing responses, keeping reference material "
            "visible, or running two threads at once."
        ),
        target_widget_name="split-view-btn",
        panel_side="bottom",
    ),
    TutorialStep(
        title="Context Injection",
        body=(
            "Drag a file from the KB panel into the chat area to inject its "
            "contents directly into the conversation. Mimir will read it as "
            "part of your next message."
        ),
    ),
    TutorialStep(
        title="Entertainment",
        body=(
            "The sidebar gives you access to media (Jellyfin) and emulation "
            "(RetroArch). Both run locally — no internet required. "
            "Use yt-dlp from the Tools menu to download video to the drive."
        ),
        target_widget_name="sidebar",
        panel_side="right",
    ),
    TutorialStep(
        title="That's It",
        body=(
            "Mimir is yours now. Everything stays on the drive. "
            "You can revisit this tour from Help → Show Tutorial any time."
        ),
    ),
]


# ---------------------------------------------------------------- overlay widget


class _DimLayer(QWidget):
    """
    Semi-transparent full-screen dim layer. Sits between the main UI and the
    tutorial panel. Catches clicks so they don't fall through to the app.
    """

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setStyleSheet("background: rgba(0, 0, 0, 0);")  # start transparent
        self._target_alpha = 120
        self._current_alpha = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def _tick(self):
        if self._current_alpha < self._target_alpha:
            self._current_alpha = min(self._current_alpha + 8, self._target_alpha)
            self.setStyleSheet(f"background: rgba(0, 0, 0, {self._current_alpha});")
        else:
            self._timer.stop()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.parent():
            self.resize(self.parent().size())

    def mousePressEvent(self, event):
        # Absorb clicks — don't let them pass through to the main UI
        event.accept()


class TutorialPanel(QFrame):
    """
    Floating card that shows the current tutorial step.
    Arrow indicator points toward the target widget (stub — visual only for now).
    """

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("tutorial-panel")
        self.setFixedWidth(380)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(0)

        # Step counter (e.g. "3 / 7")
        self._step_label = QLabel()
        self._step_label.setObjectName("tut-step-counter")
        layout.addWidget(self._step_label)

        layout.addSpacing(10)

        # Title
        self._title = QLabel()
        self._title.setObjectName("tut-title")
        self._title.setWordWrap(True)
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setWeight(QFont.Weight.Bold)
        self._title.setFont(title_font)
        layout.addWidget(self._title)

        layout.addSpacing(10)

        # Body
        self._body = QLabel()
        self._body.setObjectName("tut-body")
        self._body.setWordWrap(True)
        body_font = QFont()
        body_font.setPointSize(11)
        self._body.setFont(body_font)
        layout.addWidget(self._body)

        layout.addSpacing(24)

        # Button row
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self._btn_skip = QPushButton("Skip Tour")
        self._btn_skip.setObjectName("tut-btn-skip")
        self._btn_skip.setFlat(True)
        self._btn_skip.setCursor(Qt.CursorShape.PointingHandCursor)

        self._btn_prev = QPushButton("← Previous")
        self._btn_prev.setObjectName("tut-btn-prev")
        self._btn_prev.setFixedHeight(38)
        self._btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)

        self._btn_next = QPushButton("Next →")
        self._btn_next.setObjectName("tut-btn-next")
        self._btn_next.setFixedHeight(38)
        self._btn_next.setCursor(Qt.CursorShape.PointingHandCursor)

        btn_layout.addWidget(self._btn_skip)
        btn_layout.addStretch()
        btn_layout.addWidget(self._btn_prev)
        btn_layout.addWidget(self._btn_next)

        layout.addLayout(btn_layout)

    def update_step(self, step: TutorialStep, index: int, total: int):
        self._step_label.setText(f"Step {index + 1} of {total}")
        self._title.setText(step.title)
        self._body.setText(step.body)
        self._btn_prev.setVisible(index > 0)
        self._btn_next.setText("Finish" if index == total - 1 else "Next →")
        self.adjustSize()

    @property
    def btn_skip(self):
        return self._btn_skip

    @property
    def btn_prev(self):
        return self._btn_prev

    @property
    def btn_next(self):
        return self._btn_next


class TutorialOverlay(QWidget):
    """
    Full-screen overlay widget that walks the user through tutorial steps.
    Parent should be the main window (or any full-size widget).

    Wire finished() to your post-tutorial logic before calling show().
    """

    finished = pyqtSignal()

    def __init__(self, steps: List[TutorialStep] = None, parent: QWidget = None):
        super().__init__(parent)
        self._steps = steps or TUTORIAL_STEPS
        self._current = 0

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

        # Dim layer fills parent
        self._dim = _DimLayer(self)

        # Tutorial panel floats on top
        self._panel = TutorialPanel(self)
        self._panel.btn_skip.clicked.connect(self._finish)
        self._panel.btn_prev.clicked.connect(self._go_prev)
        self._panel.btn_next.clicked.connect(self._go_next)

        self._apply_theme()
        self._show_step(0)

    # --------------------------------------------------------- navigation

    def _show_step(self, index: int):
        self._current = index
        step = self._steps[index]
        self._panel.update_step(step, index, len(self._steps))
        self._position_panel(step)

    def _go_next(self):
        if self._current < len(self._steps) - 1:
            self._show_step(self._current + 1)
        else:
            self._finish()

    def _go_prev(self):
        if self._current > 0:
            self._show_step(self._current - 1)

    def _finish(self):
        self.finished.emit()
        self.hide()
        # Clean up dim layer animation timer if still running
        self._dim._timer.stop()

    # --------------------------------------------------------- positioning

    def _position_panel(self, step: TutorialStep):
        """
        Place the panel near the target widget if found.
        Falls back to centered if target not found or not yet in the DOM.
        Phase 5 will wire real widget references — for now this is the stub.
        """
        self._panel.adjustSize()
        panel_size = self._panel.sizeHint()
        parent_rect = self.rect()
        margin = 20

        target_rect: Optional[QRect] = None
        if step.target_widget_name and self.parent():
            target = self.parent().findChild(QWidget, step.target_widget_name)
            if target and target.isVisible():
                # Map widget rect to overlay coordinates
                top_left = target.mapTo(self.parent(), QPoint(0, 0))
                target_rect = QRect(top_left, target.size())

        if target_rect:
            pos = self._best_position(
                panel_size, target_rect, parent_rect, step.panel_side, margin
            )
        else:
            # Center fallback
            pos = QPoint(
                (parent_rect.width() - panel_size.width()) // 2,
                (parent_rect.height() - panel_size.height()) // 2,
            )

        self._panel.move(pos)

    def _best_position(
        self,
        panel_size: QSize,
        target: QRect,
        bounds: QRect,
        preferred_side: str,
        margin: int,
    ) -> QPoint:
        """
        Try preferred_side first. If the panel would clip the bounds,
        try opposite side, then left/right. Final fallback: centered.
        """
        pw, ph = panel_size.width(), panel_size.height()

        def candidate(side) -> Optional[QPoint]:
            if side == "bottom":
                x = target.center().x() - pw // 2
                y = target.bottom() + margin
            elif side == "top":
                x = target.center().x() - pw // 2
                y = target.top() - ph - margin
            elif side == "right":
                x = target.right() + margin
                y = target.center().y() - ph // 2
            elif side == "left":
                x = target.left() - pw - margin
                y = target.center().y() - ph // 2
            else:
                return None

            # Clamp to bounds with margin
            x = max(margin, min(x, bounds.width() - pw - margin))
            y = max(margin, min(y, bounds.height() - ph - margin))
            return QPoint(x, y)

        opposites = {"bottom": "top", "top": "bottom", "left": "right", "right": "left"}
        for side in [preferred_side, opposites.get(preferred_side, "bottom"), "bottom", "top"]:
            p = candidate(side)
            if p:
                return p

        return QPoint(
            (bounds.width() - pw) // 2,
            (bounds.height() - ph) // 2,
        )

    # --------------------------------------------------------- resize

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._dim.resize(self.size())
        # Re-position panel if we have a step loaded
        if self._steps:
            self._position_panel(self._steps[self._current])

    # --------------------------------------------------------- theme

    def _apply_theme(self, accent: str = "#8B5CF6", accent2: str = "#22D3A5",
                     bg: str = "#1A1A26", text: str = "#E8E8F0",
                     muted: str = "#6B7280"):
        self._panel.setStyleSheet(f"""
            QFrame#tutorial-panel {{
                background-color: {bg};
                border: 1px solid {accent};
                border-radius: 10px;
            }}
            QLabel#tut-step-counter {{
                color: {muted};
                font-size: 11px;
                letter-spacing: 1px;
                text-transform: uppercase;
                background: transparent;
            }}
            QLabel#tut-title {{
                color: {text};
                background: transparent;
            }}
            QLabel#tut-body {{
                color: rgba(232,232,240,200);
                background: transparent;
                line-height: 1.5;
            }}
            QPushButton#tut-btn-skip {{
                color: {muted};
                background: transparent;
                border: none;
                font-size: 11px;
                text-decoration: underline;
                padding: 0;
            }}
            QPushButton#tut-btn-skip:hover {{
                color: {text};
            }}
            QPushButton#tut-btn-prev {{
                background: transparent;
                color: {text};
                border: 1px solid rgba(232,232,240,80);
                border-radius: 5px;
                font-size: 12px;
                padding: 0 14px;
            }}
            QPushButton#tut-btn-prev:hover {{
                border-color: {accent};
                color: {accent};
            }}
            QPushButton#tut-btn-next {{
                background: {accent};
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 12px;
                font-weight: 600;
                padding: 0 18px;
            }}
            QPushButton#tut-btn-next:hover {{
                background: {accent2};
            }}
        """)

    def set_theme_colors(self, accent: str, accent2: str, bg: str,
                         text: str, muted: str):
        """Call this after a theme change to re-skin the panel."""
        self._apply_theme(accent, accent2, bg, text, muted)
