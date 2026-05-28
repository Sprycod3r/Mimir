"""
ollama_health_monitor.py — Mimir Ollama Health Monitor

A QThread that periodically checks whether Ollama is still responding.
If Ollama dies unexpectedly, it attempts to restart it via ServiceManager.
Emits signals the UI can connect to for live status indicators.

Design:
  - Polls every POLL_INTERVAL_SECONDS
  - On failure: waits FAILURE_BACKOFF_SECONDS before retrying
  - After MAX_RESTART_ATTEMPTS failures, stops trying and emits gave_up signal
  - Can be paused during intentional restarts to avoid false alarms
"""

import time
from PyQt6.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker


POLL_INTERVAL_SECONDS = 15
FAILURE_BACKOFF_SECONDS = 5
MAX_RESTART_ATTEMPTS = 3


class OllamaHealthMonitor(QThread):
    """
    Background thread monitoring Ollama's health.

    Signals:
      status_changed(bool)  — True = healthy, False = not responding
      restarting()          — emitted when a restart is being attempted
      restart_succeeded()   — emitted when Ollama comes back up after a restart
      restart_failed(int)   — emitted with the attempt number that failed
      gave_up()             — emitted after MAX_RESTART_ATTEMPTS all fail
      response_time_ms(float) — current ping time in milliseconds
    """

    status_changed = pyqtSignal(bool)
    restarting = pyqtSignal()
    restart_succeeded = pyqtSignal()
    restart_failed = pyqtSignal(int)
    gave_up = pyqtSignal()
    response_time_ms = pyqtSignal(float)

    def __init__(self, ollama_client, service_manager,
                 model_id: str, model_name: str, parent=None):
        super().__init__(parent)
        self._client = ollama_client
        self._service_manager = service_manager
        self._model_id = model_id
        self._model_name = model_name

        self._running = True
        self._paused = False
        self._last_known_healthy = False
        self._consecutive_failures = 0
        self._restart_attempts = 0
        self._mutex = QMutex()

    def pause(self):
        """Pause monitoring (e.g. during an intentional restart)."""
        with QMutexLocker(self._mutex):
            self._paused = True

    def resume(self):
        """Resume monitoring after a pause."""
        with QMutexLocker(self._mutex):
            self._paused = False
            self._consecutive_failures = 0

    def stop(self):
        """Signal the thread to stop cleanly."""
        self._running = False

    def run(self):
        while self._running:
            with QMutexLocker(self._mutex):
                paused = self._paused

            if not paused:
                self._check_health()

            # Sleep in small increments so stop() is responsive
            elapsed = 0
            while elapsed < POLL_INTERVAL_SECONDS and self._running:
                time.sleep(0.5)
                elapsed += 0.5

    def _check_health(self):
        ms = self._client.ping()
        healthy = ms >= 0

        if healthy:
            self.response_time_ms.emit(ms)
            if not self._last_known_healthy:
                self._last_known_healthy = True
                self._consecutive_failures = 0
                self.status_changed.emit(True)
        else:
            self._consecutive_failures += 1

            if self._last_known_healthy:
                self._last_known_healthy = False
                self.status_changed.emit(False)

            # Wait a moment before deciding it's really dead
            if self._consecutive_failures >= 2:
                self._attempt_restart()

    def _attempt_restart(self):
        if self._restart_attempts >= MAX_RESTART_ATTEMPTS:
            self.gave_up.emit()
            self._running = False
            return

        self._restart_attempts += 1
        self.restarting.emit()

        # Stop the old process if it's still lingering
        try:
            old_status = self._service_manager.get_status("ollama")
            if old_status.pid:
                import subprocess
                try:
                    subprocess.run(
                        ["taskkill", "/PID", str(old_status.pid), "/F"],
                        capture_output=True, timeout=5
                    )
                except Exception:
                    pass
        except Exception:
            pass

        time.sleep(FAILURE_BACKOFF_SECONDS)

        # Restart Ollama
        self._service_manager.start_ollama(self._model_name)

        # Wait up to 30s for it to come back
        deadline = time.time() + 30
        while time.time() < deadline:
            ms = self._client.ping()
            if ms >= 0:
                self._last_known_healthy = True
                self._consecutive_failures = 0
                self._restart_attempts = 0
                self.restart_succeeded.emit()
                self.status_changed.emit(True)
                return
            time.sleep(1)

        # Still dead after restart attempt
        self.restart_failed.emit(self._restart_attempts)
