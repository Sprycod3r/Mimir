"""
chat_message.py — Mimir Chat Message Bubble Widget

Individual message bubble. Role determines visual alignment:
  - "user"      → right-aligned, accent-color left border
  - "assistant" → left-aligned, surface background
  - "system"    → centered, muted, smaller text (for status/info messages)

Streaming support:
  Call append_token(str) to add tokens as they arrive.
  The widget expands in place — no flicker, no relayout cascade.

Copy button appears on mouse hover (top-right of the bubble).
"""

import datetime
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
    QSizePolicy, QApplication, QFrame
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QGuiApplication


class ChatMessage(QFrame):
    """
    A single rendered message in the chat log.

    role: "user" | "assistant" | "system"
    content: initial text (may be empty for streaming messages)
    timestamp: datetime — defaults to now
    """

    def __init__(self, role: str, content: str = "",
                 timestamp: datetime.datetime = None, parent=None):
        super().__init__(parent)
        self._role = role
        self._content = content
        self._timestamp = timestamp or datetime.datetime.now()

        self.setObjectName(f"chat-message-{role}")
        _sp = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        _sp.setHeightForWidth(True)
        self.setSizePolicy(_sp)

        self._setup_ui()
        if content:
            self._text_label.setText(content)

    # ----------------------------------------------------------------- layout

    def _setup_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 4)
        outer.setSpacing(0)

        if self._role == "user":
            outer.addStretch()
            bubble = self._make_bubble()
            outer.addWidget(bubble)
            outer.setContentsMargins(60, 4, 0, 4)  # indent from left
        elif self._role == "system":
            outer.addStretch()
            bubble = self._make_system_label()
            outer.addWidget(bubble)
            outer.addStretch()
        else:  # assistant
            bubble = self._make_bubble()
            outer.addWidget(bubble)
            outer.addStretch()
            outer.setContentsMargins(0, 4, 60, 4)  # indent from right

    def _make_bubble(self) -> QWidget:
        container = QWidget()
        container.setObjectName(f"bubble-container-{self._role}")
        _csp = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        _csp.setHeightForWidth(True)
        container.setSizePolicy(_csp)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Role row + timestamp + copy button
        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)
        meta_row.setContentsMargins(2, 0, 2, 0)

        role_label = QLabel("You" if self._role == "user" else "Mimir")
        role_label.setObjectName(f"msg-role-{self._role}")
        role_font = QFont()
        role_font.setPointSize(9)
        role_font.setWeight(QFont.Weight.Bold)
        role_label.setFont(role_font)

        ts_label = QLabel(self._timestamp.strftime("%H:%M"))
        ts_label.setObjectName("msg-timestamp")
        ts_font = QFont()
        ts_font.setPointSize(8)
        ts_label.setFont(ts_font)

        self._copy_btn = QPushButton("Copy")
        self._copy_btn.setObjectName("msg-copy-btn")
        self._copy_btn.setFlat(True)
        self._copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_btn.setFixedHeight(18)
        self._copy_btn.setVisible(False)
        self._copy_btn.clicked.connect(self._copy_to_clipboard)

        if self._role == "user":
            meta_row.addStretch()
            meta_row.addWidget(ts_label)
            meta_row.addWidget(role_label)
            meta_row.addWidget(self._copy_btn)
        else:
            meta_row.addWidget(role_label)
            meta_row.addWidget(ts_label)
            meta_row.addStretch()
            meta_row.addWidget(self._copy_btn)

        layout.addLayout(meta_row)

        # Bubble frame
        bubble_frame = QFrame()
        bubble_frame.setObjectName(f"bubble-{self._role}")
        bubble_layout = QVBoxLayout(bubble_frame)
        bubble_layout.setContentsMargins(14, 10, 14, 10)

        self._text_label = QLabel()
        self._text_label.setObjectName(f"bubble-text-{self._role}")
        self._text_label.setWordWrap(True)
        self._text_label.setTextFormat(Qt.TextFormat.PlainText)
        _lsp = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        _lsp.setHeightForWidth(True)
        self._text_label.setSizePolicy(_lsp)
        self._text_label.setMinimumWidth(200)
        self._text_label.setMaximumWidth(700)

        text_font = QFont()
        text_font.setPointSize(11)
        self._text_label.setFont(text_font)

        bubble_layout.addWidget(self._text_label)
        layout.addWidget(bubble_frame)

        # Streaming indicator (three dots — shown while streaming)
        self._streaming_label = QLabel("●●●")
        self._streaming_label.setObjectName("msg-streaming")
        self._streaming_label.setVisible(False)
        layout.addWidget(self._streaming_label)

        return container

    def _make_system_label(self) -> QWidget:
        label = QLabel(self._content)
        label.setObjectName("bubble-system")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._text_label = label
        self._copy_btn = None
        self._streaming_label = None
        return label

    # ----------------------------------------------------------------- mouse events

    def enterEvent(self, event):
        super().enterEvent(event)
        if self._copy_btn:
            self._copy_btn.setVisible(True)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if self._copy_btn:
            self._copy_btn.setVisible(False)

    # ----------------------------------------------------------------- streaming

    def start_streaming(self):
        """Show the streaming dots indicator."""
        if self._streaming_label:
            self._streaming_label.setVisible(True)

    def append_token(self, token: str):
        """Add a token to the message content (streaming mode)."""
        self._content += token
        self._text_label.setText(self._content)
        self._text_label.updateGeometry()
        self.updateGeometry()
        # Hide streaming indicator once content arrives
        if self._streaming_label and self._streaming_label.isVisible():
            self._streaming_label.setVisible(False)

    def finish_streaming(self):
        """Mark streaming as done, hide the indicator."""
        if self._streaming_label:
            self._streaming_label.setVisible(False)

    # ----------------------------------------------------------------- public

    def set_content(self, text: str):
        print(f"[SET_CONTENT] role={self._role} len={len(text)} preview={text[:120]!r}")
        self._content = text
        self._text_label.setText(text)
        self._text_label.updateGeometry()
        self.updateGeometry()

    @property
    def content(self) -> str:
        return self._content

    @property
    def role(self) -> str:
        return self._role

    @property
    def timestamp(self) -> datetime.datetime:
        return self._timestamp

    def to_log_dict(self) -> dict:
        return {
            "role": self._role,
            "content": self._content,
            "timestamp": self._timestamp.isoformat(),
        }

    # ----------------------------------------------------------------- copy

    def _copy_to_clipboard(self):
        QGuiApplication.clipboard().setText(self._content)
        if self._copy_btn:
            self._copy_btn.setText("✓")
            QTimer.singleShot(1200, lambda: self._copy_btn.setText("Copy") if self._copy_btn else None)
