"""
model_selector.py — Mimir Model Selection Screen
Full-window screen shown after hardware detection.
Displays three model cards with the recommended one highlighted.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QSpacerItem
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QFont

from .model_card import ModelCard
from hardware_detect import HardwareProfile, format_hardware_summary


class ModelSelectorScreen(QWidget):
    """
    Shown after hardware detection.
    Emits model_selected(model_id) when the user confirms a choice.
    """
    model_selected = pyqtSignal(str)

    def __init__(self, models: list, hardware: HardwareProfile, parent=None):
        super().__init__(parent)
        self._models = models
        self._hardware = hardware
        self._recommended = hardware.recommend_tier()
        self._current_selection = self._recommended
        self._cards = {}

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(48, 40, 48, 40)
        root.setSpacing(0)

        # ---- Header ----
        header_layout = QVBoxLayout()
        header_layout.setSpacing(8)

        wordmark = QLabel("MIMIR")
        wordmark.setProperty("class", "title")
        wordmark.setAlignment(Qt.AlignmentFlag.AlignLeft)
        header_layout.addWidget(wordmark)

        tagline = QLabel("Select a model to continue")
        tagline.setProperty("class", "subtitle")
        header_layout.addWidget(tagline)

        root.addLayout(header_layout)
        root.addSpacing(20)

        # ---- Hardware summary bar ----
        hw_summary_text = format_hardware_summary(self._hardware)
        hw_label = QLabel(f"Detected hardware:   {hw_summary_text}")
        hw_label.setProperty("class", "hardware-summary")
        hw_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(hw_label)

        # Show any detection errors as a subtle note
        if self._hardware.detection_errors:
            err_note = QLabel("Some hardware could not be detected — see below for details.")
            err_note.setProperty("class", "status-warn")
            root.addSpacing(6)
            root.addWidget(err_note)

        root.addSpacing(32)

        # ---- Cards row ----
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(20)
        cards_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        for model_data in self._models:
            mid = model_data["id"]
            perf_note = self._hardware.get_performance_note(mid)
            is_recommended = (mid == self._recommended)

            card = ModelCard(
                model_data=model_data,
                performance_note=perf_note,
                is_recommended=is_recommended
            )
            card.selected.connect(self._on_model_selected)
            cards_layout.addWidget(card)
            self._cards[mid] = card

        root.addLayout(cards_layout)
        root.addSpacing(28)

        # ---- Override note ----
        override_note = QLabel(
            f"Recommended for your hardware: {self._recommended.upper()}  ·  "
            "You can select any tier manually."
        )
        override_note.setProperty("class", "subtitle")
        override_note.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(override_note)

        root.addSpacing(8)

        # ---- Detection error detail (collapsible in future; inline for now) ----
        if self._hardware.detection_errors:
            err_detail = QLabel(
                "Detection notes: " + " | ".join(self._hardware.detection_errors)
            )
            err_detail.setProperty("class", "status-warn")
            err_detail.setWordWrap(True)
            err_detail.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            root.addWidget(err_detail)

        root.addStretch()

        # ---- Bottom: version note ----
        ver_label = QLabel("Mimir — Offline AI System")
        ver_label.setProperty("class", "subtitle")
        ver_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        root.addWidget(ver_label)

        # Highlight the default/recommended card
        self._update_card_states(self._recommended)

    def _on_model_selected(self, model_id: str):
        """Called when any card's SELECT button is clicked."""
        self._current_selection = model_id
        self._update_card_states(model_id)
        # Slight delay so the user sees the selection state before transition
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(180, lambda: self.model_selected.emit(model_id))

    def _update_card_states(self, selected_id: str):
        for mid, card in self._cards.items():
            card.set_selected_state(mid == selected_id)
