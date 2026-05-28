"""
model_card.py — Mimir Model Selection Card Widget
Individual card displaying one model tier with all relevant info.
"""

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont


class ModelCard(QFrame):
    """
    Displays a single model tier card in the model selection screen.
    Emits selected(model_id) when the SELECT button is clicked.
    """
    selected = pyqtSignal(str)  # Emits model_id

    TIER_BADGE_CLASSES = {
        "heavy": "badge-tier-heavy",
        "medium": "badge-tier-medium",
        "lite": "badge-tier-lite",
    }

    def __init__(self, model_data: dict, performance_note: str,
                 is_recommended: bool = False, parent=None):
        super().__init__(parent)

        self._model_id = model_data["id"]
        self._model_data = model_data
        self._is_recommended = is_recommended

        self.setProperty("class", "model-card")
        self.setMinimumWidth(300)
        self.setMaximumWidth(380)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._build_ui(model_data, performance_note, is_recommended)

    def _build_ui(self, data: dict, perf_note: str, is_recommended: bool):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # ---- Top badges row ----
        badges_row = QHBoxLayout()
        badges_row.setSpacing(8)

        tier_id = data["id"]
        tier_badge = QLabel(data["tier_display"])
        tier_badge.setProperty("class", self.TIER_BADGE_CLASSES.get(tier_id, "badge-tier-lite"))
        tier_badge.setFixedHeight(22)
        badges_row.addWidget(tier_badge)

        if is_recommended:
            rec_badge = QLabel("RECOMMENDED")
            rec_badge.setProperty("class", "badge-recommended")
            rec_badge.setFixedHeight(22)
            badges_row.addWidget(rec_badge)

        badges_row.addStretch()
        layout.addLayout(badges_row)

        # ---- Model display name ----
        name_label = QLabel(data["display_name"])
        name_font = QFont()
        name_font.setPointSize(18)
        name_font.setWeight(QFont.Weight.Bold)
        name_label.setFont(name_font)
        layout.addWidget(name_label)

        # ---- Quantization / param note ----
        param_label = QLabel(f"{data['parameters_b']}B parameters · {data['quantization']}")
        param_label.setProperty("class", "subtitle")
        layout.addWidget(param_label)

        # ---- Separator ----
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setProperty("class", "separator")
        layout.addWidget(sep)

        # ---- Description ----
        desc_label = QLabel(data["description"])
        desc_label.setWordWrap(True)
        desc_label.setProperty("class", "subtitle")
        desc_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(desc_label)

        # ---- Use cases ----
        use_cases = data.get("ideal_use_cases", [])
        if use_cases:
            use_header = QLabel("Best for")
            use_header.setProperty("class", "section-header")
            layout.addWidget(use_header)

            for case in use_cases:
                case_row = QHBoxLayout()
                dot = QLabel("·")
                dot.setFixedWidth(12)
                dot.setProperty("class", "subtitle")
                case_label = QLabel(case)
                case_label.setProperty("class", "subtitle")
                case_label.setWordWrap(True)
                case_row.addWidget(dot)
                case_row.addWidget(case_label, 1)
                layout.addLayout(case_row)

        # ---- Hardware requirement ----
        hw_header = QLabel("Hardware")
        hw_header.setProperty("class", "section-header")
        layout.addWidget(hw_header)

        hw_note = QLabel(data.get("hardware_requirement_note", ""))
        hw_note.setWordWrap(True)
        hw_note.setProperty("class", "subtitle")
        layout.addWidget(hw_note)

        # ---- Performance on this machine ----
        perf_header = QLabel("On your hardware")
        perf_header.setProperty("class", "section-header")
        layout.addWidget(perf_header)

        perf_label = QLabel(perf_note)
        perf_label.setWordWrap(True)
        perf_label.setProperty("class", "subtitle")
        layout.addWidget(perf_label)

        # ---- Approximate size ----
        size_label = QLabel(f"Model size: ~{data.get('approx_size_gb', '?')}GB on disk")
        size_label.setProperty("class", "subtitle")
        layout.addWidget(size_label)

        layout.addStretch()

        # ---- SELECT button ----
        select_btn = QPushButton("SELECT")
        select_btn.setProperty("class", "select-model")
        select_btn.setFixedHeight(42)
        select_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        select_btn.clicked.connect(lambda: self.selected.emit(self._model_id))
        layout.addWidget(select_btn)

    def set_selected_state(self, selected: bool):
        """Visual feedback when this card's model is the active selection."""
        self.setProperty("class", "model-card-selected" if selected else "model-card")
        self.style().unpolish(self)
        self.style().polish(self)
