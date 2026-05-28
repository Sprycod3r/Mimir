"""
main.py — Mimir Launcher Entry Point

Launch sequence:
  1.  QApplication starts
  2.  Paths resolved from exe location
  3.  Settings loaded
  4.  Theme applied
  5.  Hardware detection runs (background thread, splash shown)
  6.  Model selection screen displayed (skipped if saved preference exists)
  7.  On model selection: Ollama, AnythingLLM, and Jellyfin started in sequence
  8.  Ollama readiness polled; model availability verified
  9.  Pull dialog shown if selected model is not downloaded
  10. Health monitor (Ollama) + service pollers (Jellyfin, AnythingLLM) attached
  11. AnythingLLM first-run setup runs (skipped if already configured)
  12. Knowledge base scaffolded; KB indexer runs in background
  13. Intro screen shown (or skipped if user dismissed permanently)
  14. Main interface displayed — all panels active

Key threads started at runtime:
  OllamaHealthMonitor  — polls Ollama every 15s, restarts on failure
  ServiceHealthPoller  — polls Jellyfin /health every 20s
  ServiceHealthPoller  — polls AnythingLLM /api/ping every 20s
  KBIndexer            — indexes new .md files on launch (one-shot)
  AnythingLLMSetupWorker — first-run config only (one-shot)
"""

import sys
import os
import json
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QStackedWidget
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QIcon

# Ensure src/ is on the path when running from source
if not getattr(sys, 'frozen', False):
    src_dir = Path(__file__).parent
    sys.path.insert(0, str(src_dir))

from path_resolver import MimirPaths
from settings_manager import SettingsManager
from theme_manager import ThemeManager
from hardware_detect import detect_hardware, HardwareProfile
from service_manager import ServiceManager
from ollama_client import OllamaClient
from ollama_health_monitor import OllamaHealthMonitor
from service_health import ServiceHealthPoller
from anythingllm_client import AnythingLLMClient
from anythingllm_setup import AnythingLLMSetupWorker, AnythingLLMSetupState
from kb_indexer import KBIndexer, get_manifest_summary
from kb_scaffold import scaffold_knowledge_base
from ui.model_selector import ModelSelectorScreen
from ui.model_pull_dialog import ModelPullDialog
from ui.intro_screen import IntroScreen
from ui.tutorial_overlay import TutorialOverlay, TUTORIAL_STEPS
from ui.main_interface import MainInterface


# ============================================================
# Hardware Detection Worker Thread
# ============================================================

class HardwareDetectWorker(QThread):
    """Runs hardware detection off the main thread."""
    finished = pyqtSignal(object)  # Emits HardwareProfile

    def run(self):
        profile = detect_hardware()
        self.finished.emit(profile)


class OllamaReadyWaiter(QThread):
    """
    Polls Ollama until it responds or a timeout is hit.
    Used after starting the Ollama process to confirm it's actually ready.
    """
    ready = pyqtSignal()
    timed_out = pyqtSignal()

    def __init__(self, client: OllamaClient, timeout: int = 30, parent=None):
        super().__init__(parent)
        self._client = client
        self._timeout = timeout

    def run(self):
        import time
        deadline = time.time() + self._timeout
        while time.time() < deadline:
            if self._client.is_running():
                self.ready.emit()
                return
            time.sleep(0.75)
        self.timed_out.emit()


# ============================================================
# Splash / Loading Screen
# ============================================================

class SplashScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        wordmark = QLabel("MIMIR")
        wordmark.setProperty("class", "title")
        wordmark.setAlignment(Qt.AlignmentFlag.AlignCenter)

        status = QLabel("Detecting hardware...")
        status.setProperty("class", "subtitle")
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status.setObjectName("splash_status")

        layout.addStretch()
        layout.addWidget(wordmark)
        layout.addWidget(status)
        layout.addStretch()

    def set_status(self, text: str):
        label = self.findChild(QLabel, "splash_status")
        if label:
            label.setText(text)


# ============================================================
# Service Start Screen
# ============================================================

class ServiceStartScreen(QWidget):
    """
    Shown briefly while services are starting after model selection.
    """
    def __init__(self, model_label: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        wordmark = QLabel("MIMIR")
        wordmark.setProperty("class", "title")
        wordmark.setAlignment(Qt.AlignmentFlag.AlignCenter)

        model_note = QLabel(f"Starting services — {model_label} model selected")
        model_note.setProperty("class", "subtitle")
        model_note.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._status_label = QLabel("Starting Ollama...")
        self._status_label.setProperty("class", "subtitle")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()
        layout.addWidget(wordmark)
        layout.addSpacing(8)
        layout.addWidget(model_note)
        layout.addSpacing(4)
        layout.addWidget(self._status_label)
        layout.addStretch()

    def set_status(self, text: str):
        self._status_label.setText(text)


# ============================================================
# Placeholder Main Window (Phase 5 builds this out fully)
# ============================================================

class MainPlaceholderScreen(QWidget):
    """
    Temporary placeholder shown after services start.
    Phase 5 replaces this with the full Mimir interface.
    """
    def __init__(self, model_id: str, hardware: HardwareProfile,
                 service_manager: ServiceManager, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)
        layout.setContentsMargins(48, 48, 48, 48)

        wordmark = QLabel("MIMIR")
        wordmark.setProperty("class", "title")
        wordmark.setAlignment(Qt.AlignmentFlag.AlignCenter)

        active_note = QLabel(f"Active model: {model_id.upper()}")
        active_note.setProperty("class", "subtitle")
        active_note.setAlignment(Qt.AlignmentFlag.AlignCenter)

        statuses = service_manager.get_all_statuses()
        status_lines = []
        for sid, status in statuses.items():
            icon = "●" if status.running else "○"
            note = status.error or status.status_label
            status_lines.append(f"{icon}  {status.name}  —  {note}")

        status_label = QLabel("\n".join(status_lines))
        status_label.setProperty("class", "subtitle")
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        phase_note = QLabel(
            "Phase 1 complete.\n"
            "Launcher running. Services started. Model selected.\n"
            "Full interface builds in Phase 5."
        )
        phase_note.setProperty("class", "subtitle")
        phase_note.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()
        layout.addWidget(wordmark)
        layout.addSpacing(8)
        layout.addWidget(active_note)
        layout.addSpacing(16)
        layout.addWidget(status_label)
        layout.addSpacing(24)
        layout.addWidget(phase_note)
        layout.addStretch()


# ============================================================
# Main Window
# ============================================================

class MimirWindow(QMainWindow):
    def __init__(self, paths: MimirPaths, settings: SettingsManager,
                 theme: ThemeManager, models: list):
        super().__init__()
        self._paths = paths
        self._settings = settings
        self._theme = theme
        self._models = models
        self._hardware: HardwareProfile = None
        self._service_manager: ServiceManager = None
        self._ollama_client: OllamaClient = None
        self._atllm_client: AnythingLLMClient = None
        self._health_monitor: OllamaHealthMonitor = None
        self._jellyfin_poller: ServiceHealthPoller = None
        self._atllm_poller: ServiceHealthPoller = None
        self._atllm_setup_state: AnythingLLMSetupState = None
        self._main_screen = None
        self._intro_screen = None
        self._tutorial_overlay = None
        # Mutable key container: [bytes|None]. Set when a PIN is verified.
        # Passed by reference so ChatPanel / LogsPanel pick up the key automatically
        # the moment the vault is unlocked, without needing a re-build.
        self._vault_key_ref: list = [None]

        self.setWindowTitle("Mimir")
        self.setMinimumSize(900, 640)

        w = settings.get_nested("window", "width", default=1280)
        h = settings.get_nested("window", "height", default=800)
        self.resize(w, h)

        if settings.get_nested("window", "maximized", default=False):
            self.showMaximized()

        # Central stacked widget — manages screen transitions
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        # Start with splash
        self._splash = SplashScreen()
        self._stack.addWidget(self._splash)

        # Begin hardware detection
        self._detect_worker = HardwareDetectWorker()
        self._detect_worker.finished.connect(self._on_hardware_detected)
        self._detect_worker.start()

    def _on_hardware_detected(self, profile: HardwareProfile):
        self._hardware = profile

        # Startup PIN gate: verify before any content is shown
        if self._settings.launcher_pin_enabled and self._settings.launcher_pin_hash:
            self._show_startup_pin_screen()
            return

        self._after_pin_gate()

    def _show_startup_pin_screen(self):
        from ui.pin_screen import PinScreen
        screen = PinScreen()
        screen.pin_submitted.connect(self._on_startup_pin_submitted)
        self._stack.addWidget(screen)
        self._stack.setCurrentWidget(screen)
        self._pin_screen = screen

    def _on_startup_pin_submitted(self, pin: str):
        from security import verify_pin, derive_key
        if not verify_pin(pin, self._settings.launcher_pin_hash):
            self._pin_screen.show_error("Incorrect PIN — try again.")
            return

        # If the vault uses the same PIN, derive the vault key now so the
        # user is never prompted again this session.
        if (self._settings.vault_pin_enabled
                and self._settings.vault_uses_launcher_pin
                and self._settings.log_key_salt):
            self._vault_key_ref[0] = derive_key(pin, self._settings.log_key_salt)

        self._after_pin_gate()

    def _after_pin_gate(self):
        """Continue the normal startup flow after the PIN check passes (or is skipped)."""
        saved_model = self._settings.selected_model
        if saved_model and any(m["id"] == saved_model for m in self._models):
            self._start_services(saved_model)
            return

        selector = ModelSelectorScreen(
            models=self._models,
            hardware=self._hardware
        )
        selector.model_selected.connect(self._on_model_selected)
        self._stack.addWidget(selector)
        self._stack.setCurrentWidget(selector)

    def _on_model_selected(self, model_id: str):
        # Save the selection
        self._settings.selected_model = model_id
        was_recommendation = (model_id == self._hardware.recommend_tier())
        self._settings.set("last_model_override", not was_recommendation)

        self._start_services(model_id)

    def _start_services(self, model_id: str):
        # Find the display label for the selected model
        model_data = next((m for m in self._models if m["id"] == model_id), {})
        model_label = model_data.get("display_name", model_id)

        # Show service start screen
        svc_screen = ServiceStartScreen(model_label)
        self._stack.addWidget(svc_screen)
        self._stack.setCurrentWidget(svc_screen)

        # Create service manager
        self._service_manager = ServiceManager(self._paths, self._settings)

        # Start services in sequence with status updates
        QTimer.singleShot(100, lambda: self._start_ollama_step(model_id, model_data, svc_screen))

    def _start_ollama_step(self, model_id, model_data, svc_screen):
        svc_screen.set_status("Starting Ollama inference server...")
        ollama_model = model_data.get("ollama_model", "mistral:7b")
        self._service_manager.start_ollama(ollama_model)

        # Build Ollama client — used for health checks and model verification
        self._ollama_client = OllamaClient(
            port=self._settings.ollama_port
        )
        QTimer.singleShot(400, lambda: self._start_anythingllm_step(model_id, model_data, svc_screen))

    def _start_anythingllm_step(self, model_id, model_data, svc_screen):
        svc_screen.set_status("Starting AnythingLLM...")
        self._service_manager.start_anythingllm()
        QTimer.singleShot(400, lambda: self._start_jellyfin_step(model_id, model_data, svc_screen))

    def _start_jellyfin_step(self, model_id, model_data, svc_screen):
        svc_screen.set_status("Starting Jellyfin media server...")
        self._service_manager.start_jellyfin()
        QTimer.singleShot(600, lambda: self._verify_ollama_ready(model_id, model_data, svc_screen))

    def _verify_ollama_ready(self, model_id, model_data, svc_screen):
        """
        Wait for Ollama to be ready, then verify the selected model is downloaded.
        If the model is missing, show the pull dialog before continuing.
        """
        svc_screen.set_status("Waiting for Ollama to be ready...")

        # Use a worker thread so the UI stays responsive during the wait
        waiter = OllamaReadyWaiter(self._ollama_client, timeout=30)
        waiter.ready.connect(
            lambda: self._check_model_availability(model_id, model_data, svc_screen)
        )
        waiter.timed_out.connect(
            lambda: self._on_ollama_timeout(model_id, svc_screen)
        )
        waiter.start()
        self._ollama_waiter = waiter  # Keep reference alive

    def _on_ollama_timeout(self, model_id, svc_screen):
        svc_screen.set_status(
            "Ollama is taking longer than expected to start. "
            "Continuing anyway — it may still be loading."
        )
        QTimer.singleShot(2000, lambda: self._load_main_interface(model_id))

    def _check_model_availability(self, model_id, model_data, svc_screen):
        ollama_model = model_data.get("ollama_model", "mistral:7b")
        svc_screen.set_status(f"Checking for {model_data.get('display_name', model_id)}...")

        if self._ollama_client.model_is_available(ollama_model):
            # Model is ready — start health monitor, then AnythingLLM setup
            self._attach_health_monitor(model_id, model_data)
            QTimer.singleShot(300, lambda: self._run_anythingllm_setup(model_id, model_data))
        else:
            # Model not downloaded — show pull dialog
            svc_screen.set_status(f"{model_data.get('display_name', model_id)} not found. Download required.")
            QTimer.singleShot(400, lambda: self._show_pull_dialog(model_id, model_data))

    def _show_pull_dialog(self, model_id, model_data):
        ollama_model = model_data.get("ollama_model", "mistral:7b")
        dialog = ModelPullDialog(
            client=self._ollama_client,
            model_name=ollama_model,
            model_display_name=model_data.get("display_name", model_id),
            model_size_gb=model_data.get("approx_size_gb", 0),
            parent=self
        )
        dialog.pull_complete.connect(
            lambda: self._on_pull_complete(model_id, model_data)
        )
        dialog.pull_failed.connect(
            lambda err: self._on_pull_failed(model_id, err)
        )
        dialog.exec()

    def _on_pull_complete(self, model_id, model_data):
        self._attach_health_monitor(model_id, model_data)
        self._run_anythingllm_setup(model_id, model_data)

    def _on_pull_failed(self, model_id, error_msg):
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.warning(
            self,
            "Download Failed",
            f"Could not download the model:\n{error_msg}\n\n"
            "You can try again from the settings panel, or switch to a different model tier."
        )
        # Fall back to model selection screen so user can pick a different tier
        self._settings.selected_model = None
        self._on_hardware_detected(self._hardware)

    def _attach_health_monitor(self, model_id, model_data):
        """Start the Ollama health monitor and service pollers."""
        if self._health_monitor:
            self._health_monitor.stop()
            self._health_monitor.wait()

        ollama_model = model_data.get("ollama_model", "mistral:7b")
        self._health_monitor = OllamaHealthMonitor(
            ollama_client=self._ollama_client,
            service_manager=self._service_manager,
            model_id=model_id,
            model_name=ollama_model,
        )
        self._health_monitor.status_changed.connect(self._on_ollama_health_changed)
        self._health_monitor.gave_up.connect(self._on_health_monitor_gave_up)
        self._health_monitor.start()

        self._attach_service_pollers()

    def _attach_service_pollers(self):
        """Start lightweight health pollers for Jellyfin and AnythingLLM."""
        # Stop any existing pollers (shouldn't happen, but be safe on re-entry)
        for poller in (self._jellyfin_poller, self._atllm_poller):
            if poller:
                poller.stop()
                poller.wait(1000)

        jellyfin_port = self._settings.jellyfin_port
        atllm_port = self._settings.anythingllm_port

        self._jellyfin_poller = ServiceHealthPoller(
            name="jellyfin",
            url=f"http://localhost:{jellyfin_port}/health",
            interval=20,
        )
        self._jellyfin_poller.status_changed.connect(
            lambda healthy, detail: self._on_service_health_changed("jellyfin", healthy, detail)
        )
        self._jellyfin_poller.start()

        self._atllm_poller = ServiceHealthPoller(
            name="anythingllm",
            url=f"http://localhost:{atllm_port}/api/ping",
            interval=20,
        )
        self._atllm_poller.status_changed.connect(
            lambda healthy, detail: self._on_service_health_changed("anythingllm", healthy, detail)
        )
        self._atllm_poller.start()

    def _on_service_health_changed(self, service_id: str, healthy: bool, detail: str):
        print(f"[Health] {service_id}: {'up' if healthy else 'down'} — {detail}")
        if hasattr(self, "_main_screen") and self._main_screen:
            self._main_screen.set_service_health(
                service_id, healthy, None if healthy else detail
            )

    def _run_anythingllm_setup(self, model_id, model_data):
        """
        Run AnythingLLM first-run setup if not yet completed,
        then trigger KB scaffold and indexing.
        """
        # Build the AnythingLLM client
        self._atllm_client = AnythingLLMClient(
            port=self._settings.anythingllm_port
        )
        self._atllm_setup_state = AnythingLLMSetupState(self._settings)

        # Restore token from settings if we have one
        saved_token = self._atllm_setup_state.get_token()
        if saved_token:
            self._atllm_client.set_token(saved_token)

        ollama_model = model_data.get("ollama_model", "mistral:7b")
        ctx_window = model_data.get("context_window", 8192)
        ollama_base_url = f"http://127.0.0.1:{self._settings.ollama_port}"

        # Read system prompt from disk
        system_prompt = ""
        try:
            system_prompt = self._paths.system_prompt.read_text(encoding="utf-8")
        except IOError:
            pass

        if self._atllm_setup_state.is_setup_complete() and self._atllm_client.has_token():
            # Already configured — jump straight to KB indexing
            QTimer.singleShot(200, lambda: self._run_kb_scaffold_and_index())
            return

        # First-run: write the .env, then run setup
        self._service_manager.prepare_anythingllm_env(ollama_model, ctx_window)

        worker = AnythingLLMSetupWorker(
            atllm_client=self._atllm_client,
            ollama_client=self._ollama_client,
            ollama_base_url=ollama_base_url,
            ollama_model_name=ollama_model,
            system_prompt=system_prompt,
            ollama_context_window=ctx_window,
        )
        worker.step.connect(lambda msg: print(f"[AnythingLLM Setup] {msg}"))
        worker.token_acquired.connect(self._on_atllm_token_acquired)
        worker.setup_complete.connect(
            lambda: self._on_atllm_setup_complete(model_id, model_data)
        )
        worker.setup_failed.connect(self._on_atllm_setup_failed)
        worker.start()
        self._atllm_setup_worker = worker  # Keep alive

    def _on_atllm_token_acquired(self, token: str):
        self._atllm_client.set_token(token)
        if self._atllm_setup_state:
            ws_slug = AnythingLLMClient.WORKSPACE_SLUG
            self._atllm_setup_state.mark_complete(token, ws_slug)

    def _on_atllm_setup_complete(self, model_id, model_data):
        # Make sure token is saved
        if self._atllm_setup_state and not self._atllm_setup_state.is_setup_complete():
            self._atllm_setup_state.mark_complete(
                self._atllm_client._token or "",
                AnythingLLMClient.WORKSPACE_SLUG
            )
        self._run_kb_scaffold_and_index()

    def _on_atllm_setup_failed(self, error_msg: str):
        # Non-fatal: AnythingLLM setup failure doesn't block the main UI.
        # User can retry from settings in Phase 5.
        print(f"[AnythingLLM Setup] Failed: {error_msg}")
        self._load_main_interface(
            self._settings.selected_model or "lite"
        )

    def _run_kb_scaffold_and_index(self):
        """
        Ensure KB folder structure exists, then index any .md files
        that haven't been embedded yet.
        """
        # Step 1: scaffold folder structure (instant — no-op if already done)
        scaffold_knowledge_base(self._paths.knowledge)

        # Step 2: run indexer in background
        ws_slug = (
            self._atllm_setup_state.get_workspace_slug()
            if self._atllm_setup_state else AnythingLLMClient.WORKSPACE_SLUG
        )
        manifest_path = self._paths.anythingllm_data / "kb-manifest.json"

        indexer = KBIndexer(
            client=self._atllm_client,
            knowledge_dir=self._paths.knowledge,
            manifest_path=manifest_path,
            workspace_slug=ws_slug,
        )
        indexer.indexing_complete.connect(
            lambda new_files, total: self._on_kb_indexed(new_files, total)
        )
        indexer.indexing_failed.connect(
            lambda err: print(f"[KB Index] Failed: {err}")
        )
        indexer.start()
        self._kb_indexer = indexer  # Keep alive

        # Load the main interface now — indexing runs in background
        QTimer.singleShot(
            200,
            lambda: self._load_main_interface(self._settings.selected_model or "lite")
        )

    def _on_kb_indexed(self, new_files: int, total: int):
        print(f"[KB Index] Complete: {new_files} new files indexed, {total} total in knowledge base.")
        # Surface result to the main interface if it's loaded
        if hasattr(self, "_main_screen") and self._main_screen:
            self._main_screen.notify_kb_indexed(new_files, total)
            # Post a system message to chat panel summarizing the result
            chat = self._main_screen.get_chat_panel()
            if chat:
                if total == 0:
                    msg = "Knowledge base is empty. Add .md files to the knowledge/ folder to get started."
                elif new_files == 0:
                    msg = f"Knowledge base ready — {total} documents indexed."
                else:
                    msg = (
                        f"Knowledge base indexed: {new_files} new document"
                        f"{'s' if new_files != 1 else ''} added ({total} total). "
                        "Ask Mimir mode will search these automatically."
                    )
                chat._add_system_message(msg)

    def _on_ollama_health_changed(self, healthy: bool):
        if hasattr(self, "_main_screen") and self._main_screen:
            self._main_screen.set_service_health("ollama", healthy)

    def _on_health_monitor_gave_up(self):
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(
            self,
            "Ollama Stopped",
            "Ollama has stopped responding and could not be restarted after multiple attempts.\n\n"
            "Try closing and relaunching Mimir. If the issue persists, check that "
            f"ollama.exe is present at:\n{self._paths.ollama_exe}"
        )

    def _load_main_interface(self, model_id: str):
        """
        Build the main interface, then decide whether to show
        the intro screen first or jump straight in.
        """
        # Find model data for the selected tier
        model_data = next(
            (m for m in self._models if m["id"] == model_id), {}
        ) or {"id": model_id, "display_name": model_id, "label": "Lite",
               "ollama_model": "mistral:7b", "context_window": 8192}

        # Load system prompt from disk
        system_prompt = ""
        try:
            system_prompt = self._paths.system_prompt.read_text(encoding="utf-8")
        except IOError:
            pass

        self._main_screen = MainInterface(
            ollama_client=self._ollama_client,
            anythingllm_client=self._atllm_client,
            model_data=model_data,
            paths=self._paths,
            settings=self._settings,
            theme_manager=self._theme,
            system_prompt=system_prompt,
            vault_key_ref=self._vault_key_ref,
        )
        self._stack.addWidget(self._main_screen)

        # Mark all services healthy/unhealthy based on current status
        statuses = self._service_manager.get_all_statuses() if self._service_manager else {}
        for svc_id, status in statuses.items():
            self._main_screen.set_service_health(svc_id, status.running, status.error)

        if self._settings.skip_intro:
            # User has dismissed intro permanently — go straight to main
            self._stack.setCurrentWidget(self._main_screen)
        else:
            self._show_intro_screen()

    def _show_intro_screen(self):
        """Build and display the animated intro screen."""
        intro = IntroScreen(settings=self._settings, theme_manager=self._theme)

        # Apply current theme colors to particle field
        t = self._theme.current_theme() if self._theme else {}
        intro.set_colors(
            bg_color=t.get("bg_primary", "#0E0E14"),
            particle_color=t.get("accent_primary", "#8B5CF6"),
        )

        intro.continue_to_main.connect(self._on_intro_continue)
        intro.start_tutorial.connect(self._on_intro_start_tutorial)

        self._stack.addWidget(intro)
        self._stack.setCurrentWidget(intro)
        self._intro_screen = intro  # Keep reference

    def _on_intro_continue(self):
        """User clicked Let's Go or Don't show again — go to main."""
        self._stack.setCurrentWidget(self._main_screen)
        if hasattr(self, "_intro_screen"):
            self._intro_screen.stop_animation()

    def _on_intro_start_tutorial(self):
        """User clicked Show Me Around — go to main then overlay the tutorial."""
        self._stack.setCurrentWidget(self._main_screen)
        if hasattr(self, "_intro_screen"):
            self._intro_screen.stop_animation()
        # Brief delay so main screen renders before overlay appears
        QTimer.singleShot(120, self._show_tutorial)

    def _show_tutorial(self):
        """Create and show the tutorial overlay on top of the main screen."""
        overlay = TutorialOverlay(steps=TUTORIAL_STEPS, parent=self._main_screen)
        overlay.resize(self._main_screen.size())
        overlay.finished.connect(overlay.deleteLater)

        # Apply current theme colors
        t = self._theme.current_theme() if self._theme else {}
        overlay.set_theme_colors(
            accent=t.get("accent_primary", "#8B5CF6"),
            accent2=t.get("accent_secondary", "#22D3A5"),
            bg=t.get("surface", "#1A1A26"),
            text=t.get("text_primary", "#E8E8F0"),
            muted=t.get("text_muted", "#6B7280"),
        )
        overlay.show()
        self._tutorial_overlay = overlay  # Keep reference

    def closeEvent(self, event):
        # Save window state
        self._settings.set_nested("window", "width", value=self.width())
        self._settings.set_nested("window", "height", value=self.height())
        self._settings.set_nested("window", "maximized", value=self.isMaximized())

        # Stop health monitor
        if self._health_monitor:
            self._health_monitor.stop()
            self._health_monitor.wait(2000)

        # Stop service pollers
        for poller in (self._jellyfin_poller, self._atllm_poller):
            if poller:
                poller.stop()
                poller.wait(1000)

        # Shut down services
        if self._service_manager:
            self._service_manager.shutdown()

        event.accept()


# ============================================================
# Entry Point
# ============================================================

def load_models(paths: MimirPaths) -> list:
    """Load model definitions from ollama-models.json."""
    try:
        with open(paths.ollama_models_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("models", [])
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[Mimir] Could not load model config: {e}")
        return []


def main():
    # High-DPI support
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    app = QApplication(sys.argv)
    app.setApplicationName("Mimir")
    app.setOrganizationName("Mimir")

    # Resolve all paths from exe location
    paths = MimirPaths()
    paths.ensure_dirs()

    # Load settings
    settings = SettingsManager(paths.mimir_json)

    # Load theme
    theme = ThemeManager(paths.themes)
    if not theme.set_theme(settings.theme):
        theme.set_theme("mimir-dark")  # Fallback

    # Apply global stylesheet
    app.setStyleSheet(theme.stylesheet())

    # Load model definitions
    models = load_models(paths)
    if not models:
        # Bail out gracefully — can't proceed without model config
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(
            None, "Mimir — Startup Error",
            f"Could not load model configuration.\n\nExpected file:\n{paths.ollama_models_json}\n\n"
            "Make sure the Mimir drive structure is intact."
        )
        sys.exit(1)

    # Launch main window
    window = MimirWindow(paths=paths, settings=settings, theme=theme, models=models)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
