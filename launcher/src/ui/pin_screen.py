"""
pin_screen.py — Mimir PIN Entry UI

Two classes:
  PinEntryWidget — compact form, embeddable anywhere (dialogs, panel overlays).
  PinScreen      — full-screen startup gate with MIMIR wordmark.

Both emit pin_submitted(pin: str). The caller owns verification logic.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QLineEdit, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont


class PinEntryWidget(QFrame):
    """
    Compact PIN entry form: title + masked input + error label + submit button.
    Emits pin_submitted(pin) when the user presses Enter or clicks Unlock.
    The widget never verifies — the caller does that and calls show_error() if wrong.
    """
    pin_submitted = pyqtSignal(str)

    def __init__(self, title: str = "Enter PIN", parent=None):
        super().__init__(parent)
        self.setObjectName("pin-entry-widget")
        self.setFixedWidth(320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_label = QLabel(title)
        title_label.setObjectName("pin-title")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tf = QFont()
        tf.setPointSize(14)
        tf.setWeight(QFont.Weight.Medium)
        title_label.setFont(tf)

        self._input = QLineEdit()
        self._input.setObjectName("pin-input")
        self._input.setEchoMode(QLineEdit.EchoMode.Password)
        self._input.setPlaceholderText("Enter PIN")
        self._input.setFixedHeight(44)
        self._input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._input.returnPressed.connect(self._on_submit)

        self._error_label = QLabel()
        self._error_label.setObjectName("pin-error")
        self._error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)

        submit_btn = QPushButton("Unlock")
        submit_btn.setObjectName("pin-submit-btn")
        submit_btn.setFixedHeight(40)
        submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        submit_btn.clicked.connect(self._on_submit)

        layout.addWidget(title_label)
        layout.addWidget(self._input)
        layout.addWidget(self._error_label)
        layout.addWidget(submit_btn)

    def _on_submit(self):
        pin = self._input.text().strip()
        if pin:
            self._input.clear()
            self.pin_submitted.emit(pin)

    def show_error(self, message: str):
        self._error_label.setText(message)
        self._error_label.setVisible(True)

    def clear_error(self):
        self._error_label.setVisible(False)

    def focus_input(self):
        self._input.setFocus()


class PinScreen(QWidget):
    """
    Full-screen PIN entry for the startup gate.
    Shows MIMIR wordmark above the PinEntryWidget.
    Emits pin_submitted(pin) — MimirWindow owns the verification.
    """
    pin_submitted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("pin-screen")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(32)

        wordmark = QLabel("MIMIR")
        wordmark.setProperty("class", "title")
        wordmark.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("This device is locked")
        subtitle.setProperty("class", "subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._entry = PinEntryWidget("Enter PIN to unlock", parent=self)
        self._entry.pin_submitted.connect(self.pin_submitted)

        layout.addStretch()
        layout.addWidget(wordmark)
        layout.addWidget(subtitle)
        layout.addWidget(self._entry, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()

    def show_error(self, message: str):
        self._entry.show_error(message)

    def clear_error(self):
        self._entry.clear_error()

    def showEvent(self, event):
        super().showEvent(event)
        self._entry.focus_input()
