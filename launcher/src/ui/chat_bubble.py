"""
chat_bubble.py — Mimir Floating Chat Bubble

A circular floating button anchored to the bottom-right of its parent widget.
Clicking it toggles a compact popup overlay containing a mini ChatPanel.

Architecture note:
  ChatBubble is a QObject (not a QWidget) so it does not cover the parent
  widget and cannot accidentally intercept mouse events. The button and popup
  are direct children of the parent widget (MainInterface), positioned via
  geometry calls. ChatBubble just manages their lifecycle.

Behavior:
  - Button stays anchored to bottom-right as parent resizes
  - Popup is 400px wide, max 600px tall, sits above the button
  - Popup dismisses on Escape key or clicking outside it
  - Session persists — chat history is NOT reset on open/close
  - Independent from the main chat panel session

Usage:
  bubble = ChatBubble(ollama_client, atllm_client, model_data, paths,
                      system_prompt, parent=main_interface_widget)
  # No further wiring needed
"""

from typing import List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QFrame, QApplication
)
from PyQt6.QtCore import Qt, QObject, QEvent
from PyQt6.QtGui import QFont


BUBBLE_SIZE = 52          # px diameter of the floating button
BUBBLE_MARGIN = 20        # px from right edge
BUBBLE_BOTTOM_MARGIN = 108  # px from bottom — clears the ~92px chat input bar + 16px gap
POPUP_WIDTH = 400
POPUP_MAX_HEIGHT = 580


class ChatBubble(QObject):
    """
    Lifecycle manager for the floating bubble button and popup.
    NOT a widget — button and popup are direct children of parent.
    """

    def __init__(self, ollama_client, anythingllm_client,
                 model_data: dict, paths, system_prompt: str = "",
                 shared_ask_history: Optional[List[dict]] = None,
                 vault_key_ref: list = None,
                 encrypt_logs: bool = False,
                 parent: QWidget = None):
        super().__init__(parent)
        self._ollama = ollama_client
        self._atllm = anythingllm_client
        self._model_data = model_data
        self._paths = paths
        self._system_prompt = system_prompt
        self._shared_ask_history = shared_ask_history
        self._vault_key_ref = vault_key_ref
        self._encrypt_logs = encrypt_logs
        self._parent_widget = parent
        print(f"[BUBBLE] init shared_ask_history id={id(shared_ask_history) if shared_ask_history is not None else None}")
        self._popup_open = False
        self._popup: "_ChatPopup" = None

        # Button and popup are direct children of the parent widget —
        # NOT of this QObject — so they never block the underlying UI.
        self._btn = _BubbleButton(parent=parent)
        self._btn.clicked.connect(self._toggle_popup)
        self._btn.show()
        self._btn.raise_()

        # Watch parent for resize so we can reposition
        if parent:
            parent.installEventFilter(self)

        self._position_button()

    # ----------------------------------------------------------------- event filter

    def eventFilter(self, obj, event):
        # Reposition on parent resize
        if obj is self._parent_widget and event.type() == QEvent.Type.Resize:
            self._position_button()
            if self._popup and self._popup_open:
                self._position_popup()
            return False

        # Outside-click detection — only active when popup is visible.
        # This filter is installed on QApplication during popup open and
        # removed on close, so this branch only ever fires when needed.
        if self._popup_open and event.type() == QEvent.Type.MouseButtonPress:
            try:
                global_pos = event.globalPosition().toPoint()
                clicked_widget = QApplication.widgetAt(global_pos)
                if clicked_widget is not None:
                    # Keep popup open if click is inside the popup or on the button
                    if (clicked_widget is not self._btn
                            and not self._is_descendant(clicked_widget, self._popup)):
                        self._close_popup()
            except Exception:
                pass
            return False  # Never consume — let the click reach its target

        return False

    # ----------------------------------------------------------------- positioning

    def _position_button(self):
        if not self._parent_widget:
            return
        r = self._parent_widget.rect()
        self._btn.move(
            r.width()  - BUBBLE_SIZE - BUBBLE_MARGIN,
            r.height() - BUBBLE_SIZE - BUBBLE_BOTTOM_MARGIN,
        )

    def _position_popup(self):
        if not self._parent_widget or not self._popup:
            return
        r = self._parent_widget.rect()
        pw = POPUP_WIDTH
        ph = min(POPUP_MAX_HEIGHT, r.height() - BUBBLE_SIZE - BUBBLE_BOTTOM_MARGIN - BUBBLE_MARGIN * 2)
        x = r.width()  - pw          - BUBBLE_MARGIN
        y = r.height() - BUBBLE_SIZE - BUBBLE_BOTTOM_MARGIN - BUBBLE_MARGIN - ph
        self._popup.setGeometry(x, y, pw, ph)

    # ----------------------------------------------------------------- toggle

    def _toggle_popup(self):
        if self._popup_open:
            self._close_popup()
        else:
            self._open_popup()

    def _open_popup(self):
        from ui.chat_panel import ChatPanel

        if not self._popup:
            # Popup is a direct child of the parent widget (MainInterface)
            popup = _ChatPopup(parent=self._parent_widget)
            print(f"[BUBBLE POPUP] creating ChatPanel with shared_ask_history id={id(self._shared_ask_history) if self._shared_ask_history is not None else None}")
            panel = ChatPanel(
                ollama_client=self._ollama,
                anythingllm_client=self._atllm,
                model_data=self._model_data,
                paths=self._paths,
                system_prompt=self._system_prompt,
                compact=True,
                shared_ask_history=self._shared_ask_history,
                vault_key_ref=self._vault_key_ref,
                encrypt_logs=self._encrypt_logs,
                parent=popup,
            )
            layout = QVBoxLayout(popup)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(panel)
            popup.escape_pressed.connect(self._close_popup)
            self._popup = popup

        self._position_popup()
        self._popup.show()
        self._popup.raise_()
        self._btn.raise_()  # Keep button above the popup
        self._popup_open = True
        self._btn.set_open(True)

        # Watch ALL events globally so outside-clicks close the popup.
        # Installed here and removed in _close_popup to minimise overhead.
        QApplication.instance().installEventFilter(self)

    def _close_popup(self):
        if self._popup:
            self._popup.hide()
        self._popup_open = False
        self._btn.set_open(False)
        QApplication.instance().removeEventFilter(self)

    # ----------------------------------------------------------------- visibility

    def set_visible(self, visible: bool):
        """Show or hide the bubble button. Closes the popup if hiding."""
        self._btn.setVisible(visible)
        if not visible and self._popup_open:
            self._close_popup()

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _is_descendant(widget: QWidget, ancestor: QWidget) -> bool:
        """Return True if widget is ancestor or any descendant of ancestor."""
        if not widget or not ancestor:
            return False
        current = widget
        while current is not None:
            if current is ancestor:
                return True
            current = current.parentWidget()
        return False


# ============================================================
# Internal Widgets
# ============================================================

class _BubbleButton(QPushButton):
    """Circular floating button."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("bubble-btn")
        self.setFixedSize(BUBBLE_SIZE, BUBBLE_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setText("⌨")
        font = QFont()
        font.setPointSize(18)
        self.setFont(font)
        self.setToolTip("Quick Chat  (Esc to close)")

    def set_open(self, open_state: bool):
        self.setProperty("open", open_state)
        self.style().unpolish(self)
        self.style().polish(self)
        self.setText("✕" if open_state else "⌨")


class _ChatPopup(QFrame):
    """
    Popup container that catches Escape and emits escape_pressed.
    Parented to MainInterface (not to ChatBubble).
    """
    from PyQt6.QtCore import pyqtSignal
    escape_pressed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("bubble-popup")
        self.setFrameShape(QFrame.Shape.StyledPanel)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
        else:
            super().keyPressEvent(event)
