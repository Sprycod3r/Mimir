"""
main_interface.py — Mimir Main Interface

Top-level widget shown after services start.

Layout:
  [Sidebar 240px] | [Content Area — QStackedWidget]

Content area panels:
  "chat"        → ChatPanel (default, full-width)
  "kb"          → KBPanel (file tree + preview)
  "media"       → MediaPanel (embedded Jellyfin web view)
  "emulation"   → EmulationPanel (ROM browser + RetroArch launcher)
  "downloader"  → DownloaderPanel (yt-dlp GUI)
  "logs"        → LogsPanel (session log browser)
  "settings"    → SettingsPanel (theme, model, service toggles)

Side-by-side mode:
  Triggered by the toolbar split button in ChatPanel.
  Replaces the "chat" stack entry with a QSplitter:
    left: KBPanel
    right: ChatPanel
  KB panel's context_requested is wired to ChatPanel.inject_context().

Floating chat bubble:
  ChatBubble is overlaid on this widget (not in the stack).
  Always visible regardless of active panel.

Public API:
  set_service_health(service_id, healthy, error)
  set_model(model_id, display_name, tier_label)
  get_chat_panel() → ChatPanel
"""

from pathlib import Path
from typing import List

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget, QSplitter,
    QPushButton, QLabel, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from ui.sidebar import Sidebar
from ui.chat_panel import ChatPanel
from ui.kb_panel import KBPanel
from ui.chat_bubble import ChatBubble
from ui.vault_panel import VaultPanel
# MediaPanel imported lazily in _load_media_panel() — defers WebEngine init
from ui.emulation_panel import EmulationPanel
from ui.downloader_panel import DownloaderPanel


# ============================================================
# Logs Panel
# ============================================================

class _LogsPanel(QWidget):
    """
    Browse and view conversation log files.
    Accepts vault_key_ref: list — if set and encrypt_logs is enabled,
    decrypts logs before displaying them.
    """

    def __init__(self, paths, vault_key_ref: list = None, parent=None):
        super().__init__(parent)
        self._paths = paths
        self._vault_key_ref = vault_key_ref  # [Optional[bytes]]
        from PyQt6.QtWidgets import (
            QListWidget, QListWidgetItem, QTextEdit, QSplitter
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._list = QListWidget()
        self._list.setObjectName("logs-list")
        self._list.setMinimumWidth(200)
        self._list.setMaximumWidth(320)
        self._list.currentItemChanged.connect(self._on_select)

        self._viewer = QTextEdit()
        self._viewer.setObjectName("logs-viewer")
        self._viewer.setReadOnly(True)

        splitter.addWidget(self._list)
        splitter.addWidget(self._viewer)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)
        self._refresh_list()

    def _refresh_list(self):
        self._list.clear()
        if not self._paths:
            return
        log_dir = self._paths.conversation_logs
        if not log_dir.exists():
            return
        logs = sorted(log_dir.glob("*.json"), reverse=True)
        for log in logs:
            self._list.addItem(log.name)
        if logs:
            self._list.setCurrentRow(0)

    def _on_select(self, current, _previous):
        if not current or not self._paths:
            return
        import json
        from security import is_encrypted_log, decrypt_log
        log_path = self._paths.conversation_logs / current.text()
        try:
            raw = log_path.read_text(encoding="utf-8")

            # Decrypt if encrypted and we have a key
            vault_key = self._vault_key_ref[0] if self._vault_key_ref else None
            if is_encrypted_log(raw):
                if vault_key is None:
                    self._viewer.setPlainText(
                        "[This log is encrypted.]\n\n"
                        "Unlock the vault to read encrypted conversation logs."
                    )
                    return
                try:
                    raw = decrypt_log(raw, vault_key)
                except ValueError:
                    self._viewer.setPlainText(
                        "[Decryption failed — wrong key or corrupted log.]"
                    )
                    return

            data = json.loads(raw)
            lines = []
            for msg in data:
                role = msg.get("role", "?").upper()
                ts = msg.get("timestamp", "")[:16].replace("T", " ")
                content = msg.get("content", "")
                lines.append(f"[{ts}] {role}:\n{content}\n")
            self._viewer.setPlainText("\n---\n".join(lines))
        except Exception as e:
            self._viewer.setPlainText(f"[Could not load log: {e}]")

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_list()


# ============================================================
# Settings Panel
# ============================================================

class _SettingsPanel(QWidget):
    """Settings panel — theme, service toggles, PIN/security configuration."""

    def __init__(self, settings, theme_manager, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._theme = theme_manager

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(24)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel("Settings")
        title.setObjectName("settings-title")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setWeight(QFont.Weight.Bold)
        title.setFont(title_font)
        layout.addWidget(title)

        layout.addWidget(self._separator())

        # Theme selection
        theme_label = QLabel("Theme")
        theme_label.setObjectName("settings-section-label")
        layout.addWidget(theme_label)

        from PyQt6.QtWidgets import QComboBox
        self._theme_combo = QComboBox()
        self._theme_combo.setObjectName("settings-combo")
        self._theme_combo.setFixedWidth(240)

        if theme_manager:
            for tid in sorted(theme_manager.available_themes()):
                self._theme_combo.addItem(tid, tid)
            current_idx = self._theme_combo.findData(settings.theme)
            if current_idx >= 0:
                self._theme_combo.setCurrentIndex(current_idx)
            self._theme_combo.currentIndexChanged.connect(self._on_theme_change)

        layout.addWidget(self._theme_combo)

        layout.addWidget(self._separator())

        # Service toggles
        svc_label = QLabel("Services")
        svc_label.setObjectName("settings-section-label")
        layout.addWidget(svc_label)

        from PyQt6.QtWidgets import QCheckBox
        self._atllm_toggle = QCheckBox("Start AnythingLLM on launch")
        self._atllm_toggle.setChecked(
            settings.get_nested("services", "start_anythingllm_on_launch", default=True)
        )
        self._atllm_toggle.toggled.connect(
            lambda v: settings.set_nested("services", "start_anythingllm_on_launch", value=v)
        )

        self._jellyfin_toggle = QCheckBox("Start Jellyfin on launch")
        self._jellyfin_toggle.setChecked(
            settings.get_nested("services", "start_jellyfin_on_launch", default=True)
        )
        self._jellyfin_toggle.toggled.connect(
            lambda v: settings.set_nested("services", "start_jellyfin_on_launch", value=v)
        )

        layout.addWidget(self._atllm_toggle)
        layout.addWidget(self._jellyfin_toggle)

        layout.addWidget(self._separator())

        # ── Security ──
        sec_label = QLabel("Security")
        sec_label.setObjectName("settings-section-label")
        layout.addWidget(sec_label)

        from PyQt6.QtWidgets import QCheckBox

        # Launcher PIN
        self._launcher_pin_chk = QCheckBox("Enable startup PIN lock")
        self._launcher_pin_chk.setChecked(settings.launcher_pin_enabled)
        self._launcher_pin_chk.toggled.connect(self._on_launcher_pin_toggle)
        layout.addWidget(self._launcher_pin_chk)

        self._set_launcher_pin_btn = QPushButton("Set / Change Startup PIN")
        self._set_launcher_pin_btn.setObjectName("settings-btn")
        self._set_launcher_pin_btn.setFixedWidth(240)
        self._set_launcher_pin_btn.setFixedHeight(34)
        self._set_launcher_pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._set_launcher_pin_btn.clicked.connect(
            lambda: self._set_pin("launcher_pin_hash")
        )
        layout.addWidget(self._set_launcher_pin_btn)

        # Vault PIN
        self._vault_pin_chk = QCheckBox("Enable vault PIN lock")
        self._vault_pin_chk.setChecked(settings.vault_pin_enabled)
        self._vault_pin_chk.toggled.connect(self._on_vault_pin_toggle)
        layout.addWidget(self._vault_pin_chk)

        self._vault_same_chk = QCheckBox("Use same PIN as startup lock")
        self._vault_same_chk.setChecked(settings.vault_uses_launcher_pin)
        self._vault_same_chk.toggled.connect(self._on_vault_same_toggle)
        self._vault_same_chk.setVisible(settings.vault_pin_enabled)
        layout.addWidget(self._vault_same_chk)

        self._set_vault_pin_btn = QPushButton("Set / Change Vault PIN")
        self._set_vault_pin_btn.setObjectName("settings-btn")
        self._set_vault_pin_btn.setFixedWidth(220)
        self._set_vault_pin_btn.setFixedHeight(34)
        self._set_vault_pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._set_vault_pin_btn.clicked.connect(
            lambda: self._set_pin("vault_pin_hash")
        )
        self._set_vault_pin_btn.setVisible(
            settings.vault_pin_enabled and not settings.vault_uses_launcher_pin
        )
        layout.addWidget(self._set_vault_pin_btn)

        # Log encryption
        self._encrypt_logs_chk = QCheckBox("Encrypt conversation logs (AES-256)")
        self._encrypt_logs_chk.setChecked(settings.encrypt_logs)
        self._encrypt_logs_chk.setToolTip(
            "Encrypts log JSON files at rest using AES-256-GCM.\n"
            "Key is derived from the vault PIN. Requires vault lock to be enabled.\n"
            "Unlock the vault at session start for full coverage."
        )
        self._encrypt_logs_chk.toggled.connect(self._on_encrypt_logs_toggle)
        self._encrypt_logs_chk.setVisible(settings.vault_pin_enabled)
        layout.addWidget(self._encrypt_logs_chk)

        sec_note = QLabel("PIN and encryption changes take effect on next launch.")
        sec_note.setObjectName("sidebar-status")
        sec_note.setWordWrap(True)
        layout.addWidget(sec_note)

        layout.addWidget(self._separator())

        # Reset intro
        intro_label = QLabel("Onboarding")
        intro_label.setObjectName("settings-section-label")
        layout.addWidget(intro_label)

        reset_btn = QPushButton("Show Intro Screen on Next Launch")
        reset_btn.setObjectName("settings-btn")
        reset_btn.setFixedWidth(280)
        reset_btn.setFixedHeight(36)
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.clicked.connect(self._reset_intro)
        layout.addWidget(reset_btn)

        layout.addStretch()

    def _separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("settings-separator")
        return line

    def _on_theme_change(self):
        theme_id = self._theme_combo.currentData()
        if theme_id and self._theme:
            self._settings.theme = theme_id
            self._settings.save()
            # Full restart required for theme change — inform user
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "Theme Changed",
                f"Theme set to '{theme_id}'.\nRestart Mimir to apply the new theme."
            )

    def _reset_intro(self):
        self._settings.skip_intro = False
        self._settings.save()
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(
            self, "Done",
            "Intro screen will show on next launch."
        )

    # ── Security handlers ─────────────────────────────────────────────────────

    def _set_pin(self, hash_key: str) -> bool:
        """
        Interactive PIN setup / change flow.
        If a hash exists: verifies the current PIN first.
        Returns True if a new PIN was saved, False if cancelled.
        """
        from PyQt6.QtWidgets import QInputDialog, QLineEdit, QMessageBox
        from security import hash_pin, verify_pin

        existing_hash = self._settings.get_nested("security", hash_key, default=None)
        if existing_hash:
            current, ok = QInputDialog.getText(
                self, "Current PIN", "Enter current PIN:",
                QLineEdit.EchoMode.Password
            )
            if not ok:
                return False
            if not verify_pin(current, existing_hash):
                QMessageBox.warning(self, "PIN Error", "Incorrect current PIN.")
                return False

        new_pin, ok = QInputDialog.getText(
            self, "New PIN", "Enter new PIN (minimum 4 characters):",
            QLineEdit.EchoMode.Password
        )
        if not ok or not new_pin:
            return False
        if len(new_pin) < 4:
            QMessageBox.warning(self, "PIN Error", "PIN must be at least 4 characters.")
            return False

        confirm, ok = QInputDialog.getText(
            self, "Confirm PIN", "Confirm new PIN:",
            QLineEdit.EchoMode.Password
        )
        if not ok or new_pin != confirm:
            QMessageBox.warning(self, "PIN Error", "PINs do not match.")
            return False

        self._settings.set_nested("security", hash_key, value=hash_pin(new_pin))
        QMessageBox.information(self, "PIN Saved", "PIN updated. Takes effect on next launch.")
        return True

    def _on_launcher_pin_toggle(self, enabled: bool):
        if enabled and not self._settings.launcher_pin_hash:
            # Must set a PIN before enabling
            if not self._set_pin("launcher_pin_hash"):
                self._launcher_pin_chk.setChecked(False)
                return
        self._settings.set_nested("security", "launcher_pin_enabled", value=enabled)

    def _on_vault_pin_toggle(self, enabled: bool):
        uses_same = self._settings.vault_uses_launcher_pin
        if enabled and not uses_same and not self._settings.vault_pin_hash:
            if not self._set_pin("vault_pin_hash"):
                self._vault_pin_chk.setChecked(False)
                return
        self._settings.set_nested("security", "vault_pin_enabled", value=enabled)
        self._vault_same_chk.setVisible(enabled)
        self._set_vault_pin_btn.setVisible(enabled and not uses_same)
        self._encrypt_logs_chk.setVisible(enabled)

    def _on_vault_same_toggle(self, same: bool):
        self._settings.set_nested("security", "vault_uses_launcher_pin", value=same)
        self._set_vault_pin_btn.setVisible(
            self._settings.vault_pin_enabled and not same
        )

    def _on_encrypt_logs_toggle(self, enabled: bool):
        if enabled and not self._settings.log_key_salt:
            from security import new_salt
            self._settings.set_nested("security", "log_key_salt", value=new_salt())
        self._settings.set_nested("security", "encrypt_logs", value=enabled)


# ============================================================
# Main Interface
# ============================================================

class MainInterface(QWidget):
    """
    Top-level main application widget.
    Replaces MainPlaceholderScreen when Phase 5 is active.
    """

    def __init__(self, ollama_client, anythingllm_client,
                 model_data: dict, paths, settings, theme_manager,
                 system_prompt: str = "", vault_key_ref: list = None,
                 parent=None):
        super().__init__(parent)
        self._ollama = ollama_client
        self._atllm = anythingllm_client
        self._model_data = model_data
        self._paths = paths
        self._settings = settings
        self._theme = theme_manager
        self._system_prompt = system_prompt
        # Mutable key container shared with MimirWindow. [None] if vault locked,
        # [bytes] after vault PIN verified. ChatPanel and _LogsPanel read it at use time.
        self._vault_key_ref: list = vault_key_ref if vault_key_ref is not None else [None]

        self._split_mode = False
        self._current_nav = "chat"
        self._chat_panel: ChatPanel = None
        self._kb_panel: KBPanel = None
        self._media_panel = None        # lazy-loaded on first nav to "media"
        self._vault_panel: VaultPanel = None
        self._pending_jellyfin_health = None  # stored until MediaPanel exists
        # Two separate histories: Ask Mimir + bubble share one, Talk to Mimir owns the other.
        self._shared_ask_history: List[dict] = []
        self._shared_talk_history: List[dict] = []
        print(f"[MAIN] created ask_history id={id(self._shared_ask_history)} talk_history id={id(self._shared_talk_history)}")

        self.setObjectName("main-interface")
        self._setup_ui()

    # ----------------------------------------------------------------- layout

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar
        self._sidebar = Sidebar()
        self._sidebar.nav_changed.connect(self._on_nav_changed)

        # Populate sidebar model info
        model_id = self._model_data.get("id", "lite")
        display_name = self._model_data.get("display_name", model_id)
        tier_label = self._model_data.get("label", "Lite")
        self._sidebar.set_model(model_id, display_name, tier_label)
        self._sidebar.set_all_services_starting()

        # Content stack
        self._stack = QStackedWidget()
        self._stack.setObjectName("content-stack")

        # Build all panels
        self._chat_panel = ChatPanel(
            ollama_client=self._ollama,
            anythingllm_client=self._atllm,
            model_data=self._model_data,
            paths=self._paths,
            system_prompt=self._system_prompt,
            shared_ask_history=self._shared_ask_history,
            shared_talk_history=self._shared_talk_history,
            vault_key_ref=self._vault_key_ref,
            encrypt_logs=self._settings.encrypt_logs,
        )

        manifest_path = (
            self._paths.anythingllm_data / "kb-manifest.json"
            if self._paths else None
        )
        self._kb_panel = KBPanel(
            knowledge_dir=self._paths.knowledge if self._paths else Path("."),
            anythingllm_client=self._atllm,
            manifest_path=manifest_path,
            workspace_slug="mimir",
        )
        self._kb_panel.context_requested.connect(self._on_kb_context_requested)
        self._kb_panel.reindex_complete.connect(self._on_kb_reindex_complete)

        # MediaPanel is created lazily on first nav click — see _load_media_panel()
        self._emulation_panel = EmulationPanel(paths=self._paths)
        self._downloader_panel = DownloaderPanel(paths=self._paths)
        self._vault_panel = VaultPanel(paths=self._paths)
        self._logs_panel = _LogsPanel(paths=self._paths, vault_key_ref=self._vault_key_ref)
        self._settings_panel = _SettingsPanel(
            settings=self._settings,
            theme_manager=self._theme,
        )

        # Register panels by nav id.
        # "media" is absent here — added lazily via _load_media_panel().
        self._panels = {
            "chat": self._chat_panel,
            "kb": self._kb_panel,
            "emulation": self._emulation_panel,
            "downloader": self._downloader_panel,
            "vault": self._vault_panel,
            "logs": self._logs_panel,
            "settings": self._settings_panel,
        }
        for panel in self._panels.values():
            self._stack.addWidget(panel)

        # Separator line between sidebar and content
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setObjectName("sidebar-separator")

        root.addWidget(self._sidebar)
        root.addWidget(sep)
        root.addWidget(self._stack, stretch=1)

        # Floating chat bubble — overlaid after layout is set
        # Must be created after self has a size
        QTimer.singleShot(100, self._create_bubble)

        # Default nav
        self._sidebar.set_active_nav("chat")

    def _create_bubble(self):
        # ChatBubble is a QObject — no show()/raise_()/resize() needed.
        # It positions the button and popup as direct children of self.
        print(f"[MAIN] creating bubble with shared_ask_history id={id(self._shared_ask_history)}")
        self._bubble = ChatBubble(
            ollama_client=self._ollama,
            anythingllm_client=self._atllm,
            model_data=self._model_data,
            paths=self._paths,
            system_prompt=self._system_prompt,
            shared_ask_history=self._shared_ask_history,
            vault_key_ref=self._vault_key_ref,
            encrypt_logs=self._settings.encrypt_logs,
            parent=self,
        )
        # Hide immediately if we're already on chat
        self._bubble.set_visible(self._current_nav != "chat")

    # ----------------------------------------------------------------- resize

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # ChatBubble repositions its button via its own eventFilter on parent resize.
        # No explicit call needed here.

    # ----------------------------------------------------------------- nav

    def _on_nav_changed(self, section_id: str):
        self._current_nav = section_id

        # Lazy-load MediaPanel (and WebEngine) on first visit to Media
        if section_id == "media" and self._media_panel is None:
            self._load_media_panel()

        # Vault PIN gate: verify before showing vault contents
        if section_id == "vault":
            if not self._vault_unlocked():
                self._prompt_vault_pin()
                return  # _prompt_vault_pin navigates on success

        panel = self._panels.get(section_id)
        if panel:
            self._stack.setCurrentWidget(panel)

        # Hide bubble on chat, show it everywhere else
        if hasattr(self, '_bubble'):
            self._bubble.set_visible(section_id != "chat")

    # ----------------------------------------------------------------- vault PIN

    def _vault_unlocked(self) -> bool:
        """
        Returns True if the vault should be shown without a PIN prompt.
        True when: vault lock is disabled, OR vault key is already derived this session.
        """
        if not self._settings.vault_pin_enabled:
            return True
        # Check whether there's an actual hash configured
        if self._settings.vault_uses_launcher_pin:
            pin_hash = self._settings.launcher_pin_hash
        else:
            pin_hash = self._settings.vault_pin_hash
        if not pin_hash:
            return True  # PIN enabled but no hash set yet — treat as unlocked
        return self._vault_key_ref[0] is not None

    def _prompt_vault_pin(self):
        """
        Show a modal PIN dialog. On success: derive key, navigate to vault.
        On cancel / wrong PIN: stay on current panel.
        """
        from PyQt6.QtWidgets import QDialog, QVBoxLayout
        from PyQt6.QtCore import Qt
        from ui.pin_screen import PinEntryWidget
        from security import verify_pin, derive_key

        if self._settings.vault_uses_launcher_pin:
            pin_hash = self._settings.launcher_pin_hash
        else:
            pin_hash = self._settings.vault_pin_hash

        dlg = QDialog(self)
        dlg.setWindowTitle("Vault — PIN Required")
        dlg.setModal(True)
        dlg.setFixedWidth(380)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 16, 0, 16)

        entry = PinEntryWidget("Enter vault PIN", parent=dlg)
        layout.addWidget(entry, alignment=Qt.AlignmentFlag.AlignCenter)

        def _on_pin(pin: str):
            if not verify_pin(pin, pin_hash):
                entry.show_error("Incorrect PIN — try again.")
                return
            # Derive and store the encryption key
            salt = self._settings.log_key_salt
            if salt:
                self._vault_key_ref[0] = derive_key(pin, salt)
            dlg.accept()
            # Navigate to vault now that it's unlocked
            panel = self._panels.get("vault")
            if panel:
                self._stack.setCurrentWidget(panel)
            if hasattr(self, '_bubble'):
                self._bubble.set_visible(True)

        entry.pin_submitted.connect(_on_pin)
        entry.focus_input()
        dlg.exec()
        # If dialog was rejected (closed without correct PIN), revert sidebar highlight
        if self._vault_key_ref[0] is None:
            self._sidebar.set_active_nav(
                self._current_nav if self._current_nav != "vault" else "chat"
            )

    def _load_media_panel(self):
        """
        Import MediaPanel (and therefore PyQt6-WebEngine) only now — deferred
        from startup so Chromium doesn't initialize until actually needed.
        """
        from ui.media_panel import MediaPanel  # deferred import
        jellyfin_port = self._settings.jellyfin_port if self._settings else 8096
        self._media_panel = MediaPanel(jellyfin_port=jellyfin_port, paths=self._paths)
        self._stack.addWidget(self._media_panel)
        self._panels["media"] = self._media_panel

        # Apply any Jellyfin health state that arrived before we existed
        if self._pending_jellyfin_health is not None:
            healthy, error = self._pending_jellyfin_health
            self._media_panel.set_jellyfin_status(healthy, error)
            self._pending_jellyfin_health = None

    # ----------------------------------------------------------------- side-by-side

    def enter_split_mode(self):
        """Replace the chat panel in the stack with a split view."""
        if self._split_mode:
            return
        self._split_mode = True

        # Remove the standalone chat panel from the stack
        self._stack.removeWidget(self._chat_panel)

        # Create splitter with KB on left, chat on right
        self._split_widget = QSplitter(Qt.Orientation.Horizontal)
        self._split_widget.setObjectName("split-view")
        self._split_widget.setHandleWidth(2)

        kb_clone = self._kb_panel
        self._split_widget.addWidget(kb_clone)
        self._split_widget.addWidget(self._chat_panel)
        self._split_widget.setSizes([340, 660])
        self._split_widget.setStretchFactor(0, 0)
        self._split_widget.setStretchFactor(1, 1)

        self._stack.addWidget(self._split_widget)
        self._panels["chat"] = self._split_widget
        self._stack.setCurrentWidget(self._split_widget)

    def exit_split_mode(self):
        """Return to single-panel chat view."""
        if not self._split_mode:
            return
        self._split_mode = False

        # Reparent chat panel out of splitter, back to stack
        self._chat_panel.setParent(None)
        self._stack.removeWidget(self._split_widget)
        self._split_widget.deleteLater()
        self._split_widget = None

        self._stack.addWidget(self._chat_panel)
        self._panels["chat"] = self._chat_panel
        self._stack.setCurrentWidget(self._chat_panel)

        # Re-add KB panel to stack
        self._stack.addWidget(self._kb_panel)
        self._panels["kb"] = self._kb_panel

    # ----------------------------------------------------------------- KB context

    def _on_kb_context_requested(self, text: str, title: str):
        """Wire KB panel's Ask Mimir button to the chat panel."""
        self._chat_panel.inject_context(text, title)
        # Switch to chat view so user sees the injection
        self._sidebar.set_active_nav("chat")
        self._on_nav_changed("chat")

    # ----------------------------------------------------------------- public API

    def set_service_health(self, service_id: str, healthy: bool, error: str = None):
        self._sidebar.set_service_health(service_id, healthy, error)
        # Forward Jellyfin health to MediaPanel if it's been loaded yet;
        # otherwise cache the state so _load_media_panel() can apply it later.
        if service_id == "jellyfin":
            if self._media_panel is not None:
                self._media_panel.set_jellyfin_status(healthy, error)
            else:
                self._pending_jellyfin_health = (healthy, error)

    def set_model(self, model_id: str, display_name: str, tier_label: str):
        self._sidebar.set_model(model_id, display_name, tier_label)

    def get_chat_panel(self) -> ChatPanel:
        return self._chat_panel

    def notify_kb_indexed(self, new_files: int, total_files: int):
        """
        Called by main.py when startup indexing completes.
        Updates sidebar count and KB panel status bar.
        """
        from kb_scanner import KBScanner
        # Update KB panel status bar
        self._kb_panel.update_index_status(new_files, total_files)
        # Update sidebar
        if total_files == 0:
            self._sidebar.set_kb_status("")
        else:
            self._sidebar.set_kb_status(f"📚 {total_files} docs indexed")

    def _on_kb_reindex_complete(self, new_files: int, total_files: int):
        """KB panel completed an on-demand re-index."""
        self._sidebar.set_kb_status(f"📚 {total_files} docs indexed")
        # Notify chat panel
        if new_files > 0:
            self._chat_panel._add_system_message(
                f"Knowledge base re-indexed: {new_files} new documents added ({total_files} total)."
            )
        else:
            self._chat_panel._add_system_message(
                f"Knowledge base is up to date — {total_files} documents indexed."
            )
