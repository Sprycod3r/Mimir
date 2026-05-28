"""
theme_manager.py — Mimir Theme System
Loads theme JSON files and generates PyQt6 QSS (stylesheet) strings.
Supports the three built-in themes plus any custom themes dropped into the themes/ directory.
"""

import json
from pathlib import Path
from typing import Optional


class ThemeManager:
    def __init__(self, themes_dir: Path):
        self._themes_dir = themes_dir
        self._themes: dict = {}
        self._active_theme_id: str = "mimir-dark"
        self._load_all()

    def _load_all(self):
        """Load all .json files from the themes directory."""
        if not self._themes_dir.exists():
            return
        for path in self._themes_dir.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                theme_id = data.get("id", path.stem)
                self._themes[theme_id] = data
            except (json.JSONDecodeError, IOError):
                continue

    def available_themes(self) -> list:
        """Returns list of theme IDs."""
        return list(self._themes.keys())

    def available_themes_with_names(self) -> list:
        """Returns list of (id, display_name) tuples."""
        return [(tid, t.get("display_name", tid)) for tid, t in self._themes.items()]

    def current_theme(self) -> dict:
        """Returns the flat color dict for the active theme (for widget-level use)."""
        return self.get_colors()

    def set_theme(self, theme_id: str) -> bool:
        """Set the active theme. Returns False if theme_id not found."""
        if theme_id in self._themes:
            self._active_theme_id = theme_id
            return True
        return False

    def get_colors(self) -> dict:
        """Returns the color dict for the active theme."""
        theme = self._themes.get(self._active_theme_id, {})
        return theme.get("colors", {})

    def get_color(self, key: str, fallback: str = "#FFFFFF") -> str:
        return self.get_colors().get(key, fallback)

    def stylesheet(self) -> str:
        """
        Generates a PyQt6-compatible QSS stylesheet string for the active theme.
        Applied to the QApplication to style all widgets globally.
        """
        c = self.get_colors()

        def col(key: str, fallback: str = "#FFFFFF") -> str:
            return c.get(key, fallback)

        return f"""
/* ============================================================
   Mimir Global Stylesheet — Theme: {self._active_theme_id}
   ============================================================ */

QWidget {{
    background-color: {col('bg_primary')};
    color: {col('text_primary')};
    font-family: "Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}}

QMainWindow {{
    background-color: {col('bg_primary')};
}}

/* ---- Frames / Panels ---- */
QFrame {{
    background-color: transparent;
    border: none;
}}

QFrame[frameShape="4"],
QFrame[frameShape="5"] {{
    color: {col('border')};
}}

/* ---- Labels ---- */
QLabel {{
    background-color: transparent;
    color: {col('text_primary')};
}}

QLabel[class="title"] {{
    font-size: 28px;
    font-weight: 700;
    color: {col('text_primary')};
    letter-spacing: 2px;
}}

QLabel[class="subtitle"] {{
    font-size: 14px;
    color: {col('text_secondary')};
}}

QLabel[class="hardware-summary"] {{
    font-size: 12px;
    color: {col('text_secondary')};
    padding: 8px 16px;
    background-color: {col('bg_surface')};
    border: 1px solid {col('border')};
    border-radius: 6px;
}}

QLabel[class="section-header"] {{
    font-size: 11px;
    font-weight: 600;
    color: {col('text_muted')};
    letter-spacing: 1.5px;
    text-transform: uppercase;
}}

/* ---- Buttons ---- */
QPushButton {{
    background-color: {col('bg_surface')};
    color: {col('text_primary')};
    border: 1px solid {col('border')};
    border-radius: 6px;
    padding: 8px 20px;
    font-size: 13px;
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: {col('bg_elevated')};
    border-color: {col('accent_primary')};
    color: {col('text_primary')};
}}

QPushButton:pressed {{
    background-color: {col('accent_primary_muted')};
}}

QPushButton[class="primary"] {{
    background-color: {col('accent_primary')};
    color: {col('text_on_accent')};
    border: none;
    font-weight: 600;
    font-size: 14px;
    padding: 10px 28px;
}}

QPushButton[class="primary"]:hover {{
    background-color: {col('accent_primary_hover')};
}}

QPushButton[class="select-model"] {{
    background-color: {col('accent_primary')};
    color: {col('text_on_accent')};
    border: none;
    border-radius: 6px;
    padding: 10px 0px;
    font-size: 14px;
    font-weight: 600;
    min-width: 120px;
}}

QPushButton[class="select-model"]:hover {{
    background-color: {col('accent_primary_hover')};
}}

QPushButton[class="select-model"]:disabled {{
    background-color: {col('bg_elevated')};
    color: {col('text_muted')};
}}

QPushButton[class="link"] {{
    background-color: transparent;
    border: none;
    color: {col('accent_secondary')};
    padding: 4px 0px;
    text-decoration: underline;
    font-size: 12px;
}}

QPushButton[class="link"]:hover {{
    color: {col('accent_secondary_hover')};
}}

/* ---- Model Card ---- */
QFrame[class="model-card"] {{
    background-color: {col('bg_surface')};
    border: 1px solid {col('border')};
    border-radius: 12px;
    padding: 0px;
}}

QFrame[class="model-card-selected"] {{
    background-color: {col('bg_surface')};
    border: 2px solid {col('accent_primary')};
    border-radius: 12px;
}}

QFrame[class="model-card"]:hover {{
    border-color: {col('accent_primary_muted')};
}}

/* ---- Badges ---- */
QLabel[class="badge-recommended"] {{
    background-color: {col('badge_recommended_bg')};
    color: {col('badge_recommended_text')};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.5px;
    padding: 3px 10px;
    border-radius: 4px;
}}

QLabel[class="badge-tier-heavy"] {{
    background-color: {col('badge_tier_heavy_bg')};
    color: {col('badge_tier_heavy_text')};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 3px 10px;
    border-radius: 4px;
}}

QLabel[class="badge-tier-medium"] {{
    background-color: {col('badge_tier_medium_bg')};
    color: {col('badge_tier_medium_text')};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 3px 10px;
    border-radius: 4px;
}}

QLabel[class="badge-tier-lite"] {{
    background-color: {col('badge_tier_lite_bg')};
    color: {col('badge_tier_lite_text')};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 3px 10px;
    border-radius: 4px;
}}

/* ---- Scrollbars ---- */
QScrollBar:vertical {{
    background: {col('scrollbar_bg')};
    width: 8px;
    border: none;
}}

QScrollBar::handle:vertical {{
    background: {col('scrollbar_handle')};
    border-radius: 4px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background: {col('scrollbar_handle_hover')};
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background: {col('scrollbar_bg')};
    height: 8px;
    border: none;
}}

QScrollBar::handle:horizontal {{
    background: {col('scrollbar_handle')};
    border-radius: 4px;
    min-width: 30px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {col('scrollbar_handle_hover')};
}}

/* ---- Input Fields ---- */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {col('input_bg')};
    color: {col('text_primary')};
    border: 1px solid {col('input_border')};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
    selection-background-color: {col('accent_primary_muted')};
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {col('input_border_focus')};
    outline: none;
}}

/* ---- ComboBox ---- */
QComboBox {{
    background-color: {col('input_bg')};
    color: {col('text_primary')};
    border: 1px solid {col('input_border')};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
}}

QComboBox:focus {{
    border-color: {col('input_border_focus')};
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

QComboBox QAbstractItemView {{
    background-color: {col('bg_elevated')};
    color: {col('text_primary')};
    border: 1px solid {col('border')};
    selection-background-color: {col('accent_primary_muted')};
    outline: none;
}}

/* ---- Progress Bar ---- */
QProgressBar {{
    background-color: {col('bg_surface')};
    border: 1px solid {col('border')};
    border-radius: 4px;
    height: 8px;
    text-align: center;
    font-size: 11px;
    color: {col('text_secondary')};
}}

QProgressBar::chunk {{
    background-color: {col('accent_primary')};
    border-radius: 3px;
}}

/* ---- Sidebar Navigation ---- */
QFrame[class="sidebar"] {{
    background-color: {col('bg_surface')};
    border-right: 1px solid {col('border')};
}}

QPushButton[class="nav-button"] {{
    background-color: transparent;
    color: {col('text_secondary')};
    border: none;
    border-radius: 6px;
    padding: 10px 14px;
    text-align: left;
    font-size: 13px;
    font-weight: 500;
}}

QPushButton[class="nav-button"]:hover {{
    background-color: {col('bg_elevated')};
    color: {col('text_primary')};
}}

QPushButton[class="nav-button-active"] {{
    background-color: {col('accent_primary_muted')};
    color: {col('accent_primary')};
    border: none;
    border-radius: 6px;
    padding: 10px 14px;
    text-align: left;
    font-size: 13px;
    font-weight: 600;
}}

/* ---- Status Dots ---- */
QLabel[class="status-ok"] {{
    color: {col('status_ok')};
    font-size: 11px;
}}

QLabel[class="status-warn"] {{
    color: {col('status_warn')};
    font-size: 11px;
}}

QLabel[class="status-error"] {{
    color: {col('status_error')};
    font-size: 11px;
}}

/* ---- Tooltips ---- */
QToolTip {{
    background-color: {col('bg_elevated')};
    color: {col('text_primary')};
    border: 1px solid {col('border')};
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
}}

/* ============================================================
   Phase 5 — Main Interface Styles
   ============================================================ */

/* ---- Sidebar ---- */
QWidget#sidebar {{
    background-color: {col('bg_surface')};
    border-right: 1px solid {col('border')};
}}
QWidget#sidebar-header {{
    background-color: {col('bg_surface')};
}}
QLabel#sidebar-wordmark {{
    color: {col('accent_primary')};
    background: transparent;
}}
QLabel#sidebar-model-name {{
    color: {col('text_secondary')};
    font-size: 11px;
    background: transparent;
}}
QLabel#sidebar-tier-badge {{
    color: {col('accent_secondary')};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    background: transparent;
}}
QLabel#sidebar-section-label {{
    color: {col('text_muted')};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.5px;
    background: transparent;
}}
QLabel#sidebar-status {{
    color: {col('text_muted')};
    font-size: 10px;
    background: transparent;
}}
QWidget#sidebar-bottom, QWidget#sidebar-health {{
    background: transparent;
}}
QFrame#sidebar-separator {{
    color: {col('border')};
}}

/* ---- Health Dots ---- */
QLabel#health-dot-ok    {{ color: {col('status_ok')};   font-size: 11px; background: transparent; }}
QLabel#health-dot-warn  {{ color: {col('status_warn')};  font-size: 11px; background: transparent; }}
QLabel#health-dot-error {{ color: {col('status_error')}; font-size: 11px; background: transparent; }}
QLabel#health-dot-unknown {{ color: {col('text_muted')}; font-size: 11px; background: transparent; }}
QLabel#health-dot-label {{ color: {col('text_secondary')}; font-size: 11px; background: transparent; }}

/* ---- Nav Buttons ---- */
QPushButton#nav-button {{
    background-color: {col('bg_surface')};
    color: {col('text_primary')};
    border: none;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    text-align: left;
}}
QPushButton#nav-button:hover {{
    background-color: {col('bg_elevated')};
    color: {col('text_primary')};
}}
QPushButton#nav-button[active="true"] {{
    background-color: {col('accent_primary_muted')};
    color: {col('accent_primary')};
    font-weight: 600;
}}
/* Child labels inherit button state via descendant selectors — "inherit"
   is unreliable in Qt QSS and falls back to the OS default text color. */
QPushButton#nav-button QLabel#nav-icon,
QPushButton#nav-button QLabel#nav-text {{
    color: {col('text_primary')};
    background: transparent;
}}
QPushButton#nav-button:hover QLabel#nav-icon,
QPushButton#nav-button:hover QLabel#nav-text {{
    color: {col('text_primary')};
}}
QPushButton#nav-button[active="true"] QLabel#nav-icon,
QPushButton#nav-button[active="true"] QLabel#nav-text {{
    color: {col('accent_primary')};
}}

/* ---- Content Stack ---- */
QStackedWidget#content-stack {{
    background-color: {col('bg_primary')};
}}

/* ---- Mode Toggle Bar ---- */
QWidget#mode-toggle-bar {{
    background-color: {col('bg_surface')};
    border-bottom: 1px solid {col('border')};
}}
QPushButton#mode-toggle-btn {{
    background-color: {col('bg_surface')};
    color: {col('text_muted')};
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    padding: 6px 20px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.5px;
}}
QPushButton#mode-toggle-btn[active="true"] {{
    color: {col('accent_primary')};
    border-bottom-color: {col('accent_primary')};
}}
QPushButton#mode-toggle-btn:hover {{
    color: {col('text_primary')};
}}

/* ---- Message List ---- */
QScrollArea#message-list {{
    background-color: {col('bg_primary')};
    border: none;
}}
QWidget#message-list-container {{
    background-color: {col('bg_primary')};
}}

/* ---- Chat Bubbles ---- */
QFrame#bubble-user {{
    background-color: {col('accent_primary_muted')};
    border: 1px solid {col('accent_primary')};
    border-radius: 10px;
    border-bottom-right-radius: 3px;
}}
QFrame#bubble-assistant {{
    background-color: {col('bg_surface')};
    border: 1px solid {col('border')};
    border-radius: 10px;
    border-bottom-left-radius: 3px;
}}
QLabel#bubble-text-user, QLabel#bubble-text-assistant {{
    background: transparent;
    color: {col('text_primary')};
    line-height: 1.5;
}}
QLabel#bubble-system {{
    color: {col('text_muted')};
    font-size: 11px;
    font-style: italic;
    background: transparent;
}}
QLabel#msg-role-user {{
    color: {col('accent_primary')};
    background: transparent;
}}
QLabel#msg-role-assistant {{
    color: {col('accent_secondary')};
    background: transparent;
}}
QLabel#msg-timestamp {{
    color: {col('text_muted')};
    background: transparent;
}}
QLabel#msg-streaming {{
    color: {col('text_muted')};
    font-size: 14px;
    letter-spacing: 4px;
    background: transparent;
}}
QPushButton#msg-copy-btn {{
    background: transparent;
    border: none;
    color: {col('text_muted')};
    font-size: 10px;
    padding: 0 4px;
}}
QPushButton#msg-copy-btn:hover {{
    color: {col('text_primary')};
}}

/* ---- Context Injection Banner ---- */
QFrame#context-banner {{
    background-color: {col('bg_elevated')};
    border-top: 1px solid {col('accent_secondary')};
}}
QLabel#context-banner-label {{
    color: {col('accent_secondary')};
    font-size: 11px;
    background: transparent;
}}
QPushButton#context-banner-clear {{
    background: transparent;
    border: none;
    color: {col('text_muted')};
    font-size: 11px;
    padding: 0;
}}
QPushButton#context-banner-clear:hover {{
    color: {col('text_primary')};
}}

/* ---- Chat Input Bar ---- */
QWidget#chat-input-bar {{
    background-color: {col('bg_surface')};
    border-top: 1px solid {col('border')};
}}
QWidget#chat-input-inner {{
    background: transparent;
}}
QTextEdit#chat-input-editor {{
    background-color: {col('input_bg')};
    border: 1px solid {col('input_border')};
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
}}
QTextEdit#chat-input-editor:focus {{
    border-color: {col('input_border_focus')};
}}
QPushButton#chat-send-btn {{
    background-color: {col('accent_primary')};
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    padding: 0;
    image: none;
}}
QPushButton#chat-send-btn::menu-indicator {{
    image: none;
    width: 0;
    height: 0;
}}
QPushButton#chat-send-btn:hover {{
    background-color: {col('accent_primary_hover')};
}}
QPushButton#chat-send-btn:disabled {{
    background-color: {col('status_error')};
    color: white;
    image: none;
}}

/* ---- Chat Separator ---- */
QFrame#chat-separator {{
    color: {col('border')};
}}

/* ---- KB Panel ---- */
QWidget#kb-panel, QWidget#kb-toolbar {{
    background-color: {col('bg_primary')};
}}
QLabel#kb-toolbar-title {{
    color: {col('text_primary')};
    background: transparent;
}}
QPushButton#kb-open-btn {{
    background-color: transparent;
    color: {col('accent_secondary')};
    border: 1px solid {col('border')};
    border-radius: 5px;
    font-size: 11px;
    padding: 3px 10px;
}}
QPushButton#kb-open-btn:hover {{
    border-color: {col('accent_secondary')};
}}
QTreeView#kb-tree {{
    background-color: {col('bg_surface')};
    border: none;
    border-right: 1px solid {col('border')};
    color: {col('text_primary')};
    font-size: 12px;
    selection-background-color: {col('accent_primary_muted')};
    selection-color: {col('accent_primary')};
    outline: none;
}}
QTreeView#kb-tree::item:hover {{
    background-color: {col('bg_elevated')};
}}
QWidget#kb-preview-pane {{
    background-color: {col('bg_primary')};
}}
QWidget#kb-preview-title-bar {{
    background-color: {col('bg_surface')};
    border-bottom: 1px solid {col('border')};
}}
QLabel#kb-preview-title {{
    color: {col('text_primary')};
    background: transparent;
}}
QPushButton#kb-ask-btn {{
    background-color: {col('accent_primary')};
    color: white;
    border: none;
    border-radius: 5px;
    font-size: 12px;
    font-weight: 600;
    padding: 5px 14px;
}}
QPushButton#kb-ask-btn:hover {{
    background-color: {col('accent_primary_hover')};
}}
QPushButton#kb-ask-btn:disabled {{
    background-color: {col('bg_elevated')};
    color: {col('text_muted')};
}}
QTextEdit#kb-content-view {{
    background-color: {col('bg_primary')};
    border: none;
    color: {col('text_primary')};
    padding: 16px;
    font-size: 12px;
    line-height: 1.5;
}}
QFrame#kb-separator {{
    color: {col('border')};
}}

/* ---- Floating Chat Bubble ---- */
QPushButton#bubble-btn {{
    background-color: {col('accent_primary')};
    color: white;
    border: none;
    border-radius: 26px;
    font-size: 20px;
}}
QPushButton#bubble-btn:hover {{
    background-color: {col('accent_primary_hover')};
}}
QPushButton#bubble-btn[open="true"] {{
    background-color: {col('text_muted')};
}}
QFrame#bubble-popup {{
    background-color: {col('bg_surface')};
    border: 1px solid {col('border')};
    border-radius: 10px;
}}

/* ---- Tile Panels ---- */
QLabel#tile-title {{
    color: {col('text_primary')};
    background: transparent;
}}
QLabel#tile-description {{
    color: {col('text_secondary')};
    background: transparent;
}}
QPushButton#primary {{
    background-color: {col('accent_primary')};
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 600;
    padding: 10px 28px;
}}
QPushButton#primary:hover {{
    background-color: {col('accent_primary_hover')};
}}

/* ---- Logs Panel ---- */
QListWidget#logs-list {{
    background-color: {col('bg_surface')};
    border: none;
    border-right: 1px solid {col('border')};
    color: {col('text_primary')};
    font-size: 12px;
    outline: none;
}}
QListWidget#logs-list::item:selected {{
    background-color: {col('accent_primary_muted')};
    color: {col('accent_primary')};
}}
QTextEdit#logs-viewer {{
    background-color: {col('bg_primary')};
    border: none;
    color: {col('text_secondary')};
    font-size: 12px;
    padding: 16px;
}}

/* ---- Settings Panel ---- */
QLabel#settings-title {{
    color: {col('text_primary')};
    background: transparent;
}}
QLabel#settings-section-label {{
    color: {col('text_muted')};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.5px;
    background: transparent;
}}
QFrame#settings-separator {{
    color: {col('border')};
}}
QComboBox#settings-combo {{
    background-color: {col('input_bg')};
    border: 1px solid {col('input_border')};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
    color: {col('text_primary')};
}}
QPushButton#settings-btn {{
    background-color: {col('bg_surface')};
    color: {col('text_primary')};
    border: 1px solid {col('border')};
    border-radius: 6px;
    font-size: 13px;
    padding: 8px 20px;
}}
QPushButton#settings-btn:hover {{
    border-color: {col('accent_primary')};
    color: {col('accent_primary')};
}}
QCheckBox {{
    color: {col('text_primary')};
    background: transparent;
    font-size: 13px;
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {col('border')};
    border-radius: 3px;
    background: {col('input_bg')};
}}
QCheckBox::indicator:checked {{
    background-color: {col('accent_primary')};
    border-color: {col('accent_primary')};
}}

/* ============================================================
   Phase 6 — KB Index Status Styles
   ============================================================ */

QWidget#kb-status-bar {{
    background-color: {col('bg_elevated')};
    border-bottom: 1px solid {col('border')};
}}
QLabel#kb-status-dot-ok    {{ color: {col('status_ok')};   font-size: 12px; background: transparent; }}
QLabel#kb-status-dot-warn  {{ color: {col('status_warn')};  font-size: 12px; background: transparent; }}
QLabel#kb-status-dot-error {{ color: {col('status_error')}; font-size: 12px; background: transparent; }}
QLabel#kb-status-dot-empty {{ color: {col('text_muted')};   font-size: 12px; background: transparent; }}
QLabel#kb-status-text {{
    color: {col('text_secondary')};
    font-size: 11px;
    background: transparent;
}}
QLabel#kb-stale-badge {{
    color: {col('status_warn')};
    background-color: rgba(251,191,36,20);
    border: 1px solid rgba(251,191,36,60);
    border-radius: 4px;
    font-size: 10px;
    font-weight: 600;
    padding: 1px 8px;
}}
QPushButton#kb-reindex-btn {{
    background-color: transparent;
    color: {col('accent_secondary')};
    border: 1px solid {col('border')};
    border-radius: 5px;
    font-size: 11px;
    font-weight: 600;
    padding: 3px 12px;
}}
QPushButton#kb-reindex-btn:hover {{
    border-color: {col('accent_secondary')};
    background-color: {col('bg_surface')};
}}
QPushButton#kb-reindex-btn:disabled {{
    color: {col('text_muted')};
    border-color: {col('border')};
}}
QPushButton#kb-force-btn {{
    background-color: transparent;
    color: {col('text_muted')};
    border: 1px solid {col('border')};
    border-radius: 5px;
    font-size: 10px;
}}
QPushButton#kb-force-btn:hover {{
    color: {col('text_primary')};
    border-color: {col('accent_primary')};
}}
QProgressBar#kb-progress-bar {{
    background-color: {col('bg_surface')};
    border: none;
    border-radius: 4px;
    height: 8px;
}}
QProgressBar#kb-progress-bar::chunk {{
    background-color: {col('accent_secondary')};
    border-radius: 4px;
}}
QLabel#kb-progress-label {{
    color: {col('text_muted')};
    font-size: 11px;
    background: transparent;
}}
QLabel#kb-progress-file {{
    color: {col('text_secondary')};
    font-size: 11px;
    background: transparent;
}}
QPushButton#kb-cancel-btn {{
    background: transparent;
    color: {col('status_error')};
    border: 1px solid {col('status_error')};
    border-radius: 4px;
    font-size: 10px;
    padding: 2px 8px;
}}
QLabel#sidebar-kb-status {{
    color: {col('text_muted')};
    font-size: 10px;
    background: transparent;
    padding-top: 4px;
}}

/* ============================================================
   Phase 7 — Media Panel (Jellyfin embedded view)
   ============================================================ */

QWidget#media-panel {{
    background-color: {col('bg_primary')};
}}
QWidget#media-toolbar {{
    background-color: {col('bg_elevated')};
    border-bottom: 1px solid {col('border')};
    min-height: 44px;
    max-height: 44px;
}}
QLabel#media-title {{
    color: {col('text_primary')};
    font-weight: bold;
    font-size: 13px;
    background: transparent;
}}
QPushButton#media-open-btn {{
    background-color: transparent;
    color: {col('text_muted')};
    border: 1px solid {col('border')};
    border-radius: 4px;
    padding: 0 10px;
    font-size: 11px;
}}
QPushButton#media-open-btn:hover {{
    background-color: {col('bg_surface')};
    color: {col('text_primary')};
    border-color: {col('accent_primary')};
}}
QPushButton#media-reload-btn {{
    background-color: transparent;
    color: {col('text_muted')};
    border: 1px solid {col('border')};
    border-radius: 4px;
    padding: 0 10px;
    font-size: 11px;
}}
QPushButton#media-reload-btn:hover {{
    background-color: {col('bg_surface')};
    color: {col('text_primary')};
    border-color: {col('accent_primary')};
}}

/* Waiting overlay */
QWidget#media-waiting {{
    background-color: {col('bg_primary')};
}}
QLabel#media-waiting-icon {{
    color: {col('accent_primary')};
    background: transparent;
}}
QLabel#media-status-text {{
    color: {col('text_primary')};
    font-size: 14px;
    background: transparent;
}}
QLabel#media-status-sub {{
    color: {col('text_muted')};
    font-size: 11px;
    background: transparent;
}}

/* Error overlay */
QWidget#media-error {{
    background-color: {col('bg_primary')};
}}
QLabel#media-error-icon {{
    color: {col('status_warn')};
    background: transparent;
}}
QLabel#media-error-title {{
    color: {col('text_primary')};
    font-weight: bold;
    background: transparent;
}}
QLabel#media-error-detail {{
    color: {col('text_muted')};
    font-size: 12px;
    background: transparent;
}}
QLabel#media-error-hint {{
    color: {col('text_muted')};
    font-size: 11px;
    background: transparent;
}}

/* Fallback tile (no WebEngine) */
QWidget#media-fallback {{
    background-color: {col('bg_primary')};
}}

/* ============================================================
   Phase 8 — Emulation Panel
   ============================================================ */

QWidget#emu-panel {{
    background-color: {col('bg_primary')};
}}
QWidget#emu-toolbar {{
    background-color: {col('bg_elevated')};
    border-bottom: 1px solid {col('border')};
    min-height: 44px;
    max-height: 44px;
}}
QLabel#emu-title {{
    color: {col('text_primary')};
    font-weight: bold;
    font-size: 13px;
    background: transparent;
}}
QPushButton#emu-open-btn, QPushButton#emu-refresh-btn {{
    background-color: transparent;
    color: {col('text_muted')};
    border: 1px solid {col('border')};
    border-radius: 4px;
    padding: 0 10px;
    font-size: 11px;
}}
QPushButton#emu-open-btn:hover, QPushButton#emu-refresh-btn:hover {{
    background-color: {col('bg_surface')};
    color: {col('text_primary')};
    border-color: {col('accent_primary')};
}}

/* Status banner */
QWidget#emu-status-banner {{
    background-color: {col('bg_elevated')};
    border-bottom: 1px solid {col('border')};
}}
QLabel#emu-status-dot-ok {{
    color: {col('status_ok')};
    font-size: 12px;
    background: transparent;
}}
QLabel#emu-status-dot-warn {{
    color: {col('status_warn')};
    font-size: 12px;
    background: transparent;
}}
QLabel#emu-status-text {{
    color: {col('text_muted')};
    font-size: 11px;
    background: transparent;
}}

/* Body and scroll */
QWidget#emu-body {{
    background-color: {col('bg_primary')};
}}
QScrollArea#emu-scroll {{
    background-color: {col('bg_primary')};
    border: none;
}}
QLabel#emu-section-label {{
    color: {col('text_muted')};
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 1px;
    background: transparent;
}}
QLabel#emu-bios-hint {{
    color: {col('text_muted')};
    font-size: 11px;
    background: rgba(255,255,255,4);
    border: 1px solid {col('border')};
    border-radius: 6px;
    padding: 8px 12px;
}}

/* Platform tile */
QWidget#emu-platform-tile {{
    background-color: {col('bg_elevated')};
    border: 1px solid {col('border')};
    border-radius: 8px;
}}
QWidget#emu-platform-tile:hover {{
    border-color: {col('accent_primary')};
    background-color: {col('bg_surface')};
}}
QLabel#emu-platform-icon {{
    color: {col('accent_primary')};
    background: transparent;
}}
QLabel#emu-platform-name {{
    color: {col('text_primary')};
    background: transparent;
}}
QLabel#emu-platform-count {{
    color: {col('accent_secondary')};
    background: transparent;
}}
QLabel#emu-platform-count[empty="true"] {{
    color: {col('text_muted')};
}}

/* Launch button */
QPushButton#emu-launch-btn {{
    background-color: {col('accent_primary')};
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    font-weight: bold;
    font-size: 13px;
}}
QPushButton#emu-launch-btn:hover {{
    background-color: {col('accent_primary_hover')};
}}
QPushButton#emu-launch-btn:pressed {{
    background-color: {col('accent_primary_muted')};
}}
QPushButton#emu-launch-btn[disabled_look="true"] {{
    background-color: {col('bg_elevated')};
    color: {col('text_muted')};
    border: 1px solid {col('border')};
}}

/* ============================================================
   Phase 9 — Downloader Panel
   ============================================================ */

QWidget#dl-panel {{
    background-color: {col('bg_primary')};
}}
QWidget#dl-toolbar {{
    background-color: {col('bg_elevated')};
    border-bottom: 1px solid {col('border')};
    min-height: 44px;
    max-height: 44px;
}}
QLabel#dl-title {{
    color: {col('text_primary')};
    font-weight: bold;
    font-size: 13px;
    background: transparent;
}}
QPushButton#dl-toolbar-btn {{
    background-color: transparent;
    color: {col('text_muted')};
    border: 1px solid {col('border')};
    border-radius: 4px;
    padding: 0 10px;
    font-size: 11px;
}}
QPushButton#dl-toolbar-btn:hover {{
    background-color: {col('bg_surface')};
    color: {col('text_primary')};
    border-color: {col('accent_primary')};
}}

/* Warning banner */
QWidget#dl-warning-banner {{
    background-color: rgba(251, 191, 36, 15);
    border-bottom: 1px solid {col('status_warn')};
}}
QLabel#dl-warning-icon {{
    color: {col('status_warn')};
    font-size: 13px;
    background: transparent;
}}
QLabel#dl-warning-text {{
    color: {col('status_warn')};
    font-size: 11px;
    background: transparent;
}}

/* Body */
QWidget#dl-body {{
    background-color: {col('bg_primary')};
}}
QScrollArea#dl-scroll {{
    background-color: {col('bg_primary')};
    border: none;
}}
QLabel#dl-field-label {{
    color: {col('text_muted')};
    font-size: 11px;
    font-weight: bold;
    background: transparent;
}}
QLabel#dl-section-label {{
    color: {col('text_muted')};
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 1px;
    background: transparent;
}}

/* URL input */
QLineEdit#dl-url-input {{
    background-color: {col('input_bg')};
    color: {col('text_primary')};
    border: 1px solid {col('input_border')};
    border-radius: 6px;
    padding: 0 12px;
    font-size: 12px;
}}
QLineEdit#dl-url-input:focus {{
    border-color: {col('input_border_focus')};
}}
QPushButton#dl-paste-btn {{
    background-color: {col('bg_elevated')};
    color: {col('text_muted')};
    border: 1px solid {col('border')};
    border-radius: 6px;
    font-size: 11px;
}}
QPushButton#dl-paste-btn:hover {{
    background-color: {col('bg_surface')};
    color: {col('text_primary')};
    border-color: {col('accent_primary')};
}}

/* Quality combo */
QComboBox#dl-quality-combo {{
    background-color: {col('input_bg')};
    color: {col('text_primary')};
    border: 1px solid {col('input_border')};
    border-radius: 6px;
    padding: 0 12px;
    font-size: 12px;
}}
QComboBox#dl-quality-combo::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox#dl-quality-combo QAbstractItemView {{
    background-color: {col('bg_elevated')};
    color: {col('text_primary')};
    border: 1px solid {col('border')};
    selection-background-color: {col('accent_primary')};
}}

/* Output folder display */
QLabel#dl-folder-display {{
    background-color: {col('input_bg')};
    color: {col('text_secondary')};
    border: 1px solid {col('input_border')};
    border-radius: 6px;
    padding: 0 10px;
    font-size: 11px;
    min-height: 36px;
}}
QPushButton#dl-change-btn {{
    background-color: {col('bg_elevated')};
    color: {col('text_muted')};
    border: 1px solid {col('border')};
    border-radius: 6px;
    font-size: 11px;
}}
QPushButton#dl-change-btn:hover {{
    border-color: {col('accent_primary')};
    color: {col('text_primary')};
}}

/* ffmpeg notice */
QLabel#dl-ffmpeg-notice {{
    background-color: rgba(251, 191, 36, 10);
    color: {col('status_warn')};
    border: 1px solid rgba(251, 191, 36, 40);
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 11px;
}}

/* Download / Cancel buttons */
QPushButton#dl-download-btn {{
    background-color: {col('accent_primary')};
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    font-weight: bold;
    font-size: 12px;
}}
QPushButton#dl-download-btn:hover {{
    background-color: {col('accent_primary_hover')};
}}
QPushButton#dl-download-btn:disabled {{
    background-color: {col('bg_elevated')};
    color: {col('text_muted')};
}}
QPushButton#dl-cancel-btn {{
    background-color: {col('status_error')};
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    font-weight: bold;
    font-size: 12px;
}}
QPushButton#dl-cancel-btn:hover {{
    background-color: #E05050;
}}

/* Progress bar */
QProgressBar#dl-progress-bar {{
    background-color: {col('bg_elevated')};
    border: none;
    border-radius: 4px;
}}
QProgressBar#dl-progress-bar::chunk {{
    background-color: {col('accent_primary')};
    border-radius: 4px;
}}
QLabel#dl-status-label {{
    color: {col('text_muted')};
    font-size: 11px;
    background: transparent;
}}

/* Log area */
QTextEdit#dl-log {{
    background-color: {col('bg_surface')};
    color: {col('text_secondary')};
    border: 1px solid {col('border')};
    border-radius: 6px;
    padding: 8px;
    font-size: 9pt;
}}

/* History */
QWidget#dl-history-container {{
    background-color: {col('bg_surface')};
    border: 1px solid {col('border')};
    border-radius: 6px;
}}
QWidget#dl-history-item {{
    background-color: transparent;
    border-bottom: 1px solid {col('border_subtle')};
}}
QWidget#dl-history-item:last-child {{
    border-bottom: none;
}}
QLabel#dl-history-time {{
    color: {col('text_muted')};
    font-size: 10px;
    background: transparent;
}}
QLabel#dl-history-title {{
    color: {col('text_primary')};
    font-size: 11px;
    background: transparent;
}}
QLabel#dl-history-quality {{
    color: {col('text_muted')};
    font-size: 10px;
    background: transparent;
}}
QPushButton#dl-history-btn {{
    background-color: transparent;
    color: {col('accent_secondary')};
    border: 1px solid {col('border')};
    border-radius: 3px;
    padding: 0 6px;
    font-size: 10px;
}}
QPushButton#dl-history-btn:hover {{
    background-color: {col('bg_elevated')};
    border-color: {col('accent_secondary')};
}}
QLabel#dl-empty-history {{
    color: {col('text_muted')};
    font-size: 11px;
    background: transparent;
    padding: 12px;
}}
"""
