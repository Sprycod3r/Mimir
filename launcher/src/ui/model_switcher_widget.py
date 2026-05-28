"""
model_switcher_widget.py — In-App Model Switcher

Compact panel for switching between the three model tiers after initial launch.
Lives in the sidebar or settings panel (Phase 5 wires it into the full UI).

Shows:
  - Current active model
  - Status dot (green = healthy, yellow = loading, red = error)
  - Three tier buttons for quick switching
  - Confirmation before switching (switching unloads the current model)
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont


class ModelStatusDot(QLabel):
    """Small colored dot indicating model/Ollama health status."""

    def __init__(self, parent=None):
        super().__init__("●", parent)
        self.setFixedSize(14, 14)
        self.set_healthy()

    def set_healthy(self):
        self.setProperty("class", "status-ok")
        self._refresh()

    def set_warning(self):
        self.setProperty("class", "status-warn")
        self._refresh()

    def set_error(self):
        self.setProperty("class", "status-error")
        self._refresh()

    def _refresh(self):
        self.style().unpolish(self)
        self.style().polish(self)


class ModelSwitcherWidget(QWidget):
    """
    Compact model switcher panel.

    Signals:
      model_switch_requested(str) — emits model_id when user confirms a switch
    """

    model_switch_requested = pyqtSignal(str)

    TIER_LABELS = {
        "heavy": "Heavy  —  Qwen 2.5 72B",
        "medium": "Medium  —  Qwen 2.5 32B",
        "lite": "Lite  —  Mistral 7B",
    }
    TIER_BADGE_CLASSES = {
        "heavy": "badge-tier-heavy",
        "medium": "badge-tier-medium",
        "lite": "badge-tier-lite",
    }

    def __init__(self, current_model_id: str, models: list, parent=None):
        super().__init__(parent)
        self._current_model_id = current_model_id
        self._models = {m["id"]: m for m in models}
        self._ollama_healthy = True

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # ---- Header ----
        header = QLabel("ACTIVE MODEL")
        header.setProperty("class", "section-header")
        layout.addWidget(header)

        # ---- Current model display ----
        current_row = QHBoxLayout()
        current_row.setSpacing(8)

        self._status_dot = ModelStatusDot()
        current_row.addWidget(self._status_dot)

        model_data = self._models.get(self._current_model_id, {})
        self._current_label = QLabel(model_data.get("display_name", self._current_model_id))
        font = QFont()
        font.setPointSize(13)
        font.setWeight(QFont.Weight.DemiBold)
        self._current_label.setFont(font)
        current_row.addWidget(self._current_label, 1)

        # Tier badge
        self._tier_badge = QLabel(model_data.get("tier_display", ""))
        badge_class = self.TIER_BADGE_CLASSES.get(self._current_model_id, "badge-tier-lite")
        self._tier_badge.setProperty("class", badge_class)
        self._tier_badge.setFixedHeight(20)
        current_row.addWidget(self._tier_badge)

        layout.addLayout(current_row)

        # ---- Separator ----
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        # ---- Switch buttons ----
        switch_header = QLabel("SWITCH MODEL")
        switch_header.setProperty("class", "section-header")
        layout.addWidget(switch_header)

        self._tier_buttons: dict = {}

        for tier_id in ["heavy", "medium", "lite"]:
            model = self._models.get(tier_id, {})
            if not model:
                continue

            btn = QPushButton(self.TIER_LABELS.get(tier_id, tier_id))
            btn.setProperty("class", "nav-button")
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setFixedHeight(36)

            if tier_id == self._current_model_id:
                btn.setEnabled(False)
                btn.setToolTip("This model is already active")
            else:
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setToolTip(
                    f"Switch to {model.get('display_name', tier_id)}\n"
                    f"Size on disk: ~{model.get('approx_size_gb', '?')}GB"
                )
                btn.clicked.connect(lambda checked, tid=tier_id: self._request_switch(tid))

            layout.addWidget(btn)
            self._tier_buttons[tier_id] = btn

        layout.addStretch()

    def _request_switch(self, target_model_id: str):
        """Asks for confirmation before switching models."""
        model = self._models.get(target_model_id, {})
        display = model.get("display_name", target_model_id)

        reply = QMessageBox.question(
            self,
            "Switch Model?",
            f"Switch to {display}?\n\n"
            "The current model will be unloaded from memory. "
            "Any active conversation will continue with the new model.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.model_switch_requested.emit(target_model_id)

    def update_active_model(self, model_id: str):
        """Call this after a switch completes to refresh the display."""
        self._current_model_id = model_id
        model_data = self._models.get(model_id, {})

        self._current_label.setText(model_data.get("display_name", model_id))

        badge_class = self.TIER_BADGE_CLASSES.get(model_id, "badge-tier-lite")
        self._tier_badge.setText(model_data.get("tier_display", ""))
        self._tier_badge.setProperty("class", badge_class)
        self._tier_badge.style().unpolish(self._tier_badge)
        self._tier_badge.style().polish(self._tier_badge)

        for tid, btn in self._tier_buttons.items():
            is_active = (tid == model_id)
            btn.setEnabled(not is_active)

    def set_ollama_healthy(self, healthy: bool):
        """Update the status dot based on Ollama health."""
        self._ollama_healthy = healthy
        if healthy:
            self._status_dot.set_healthy()
        else:
            self._status_dot.set_error()

    def set_ollama_loading(self):
        """Show loading/connecting state."""
        self._status_dot.set_warning()
