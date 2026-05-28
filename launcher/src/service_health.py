"""
service_health.py — Mimir Generic Service Health Poller

A lightweight QThread that HTTP-polls any localhost service URL on a fixed
interval and emits status_changed(bool, str) whenever the health state flips.

Used for Jellyfin and AnythingLLM. Unlike OllamaHealthMonitor, this poller
does NOT attempt restarts — it just reports what it sees and lets the UI
respond. Restart logic for those services can be added later.

A 2xx response OR a 401/403 (auth required, server is up) counts as healthy.
Connection refused, timeout, or 5xx counts as unhealthy.

Signals:
  status_changed(bool, str)  — (healthy, human-readable detail)

Public API:
  ServiceHealthPoller(name, url, interval=20, timeout=5)
  stop()   — signal the thread to exit cleanly
"""

import time
import urllib.request
import urllib.error
from urllib.parse import urlparse

from PyQt6.QtCore import QThread, pyqtSignal


# HTTP status codes that mean "server is up, just auth-gated"
_AUTH_CODES = {401, 403}

# Default poll cadence in seconds — generous enough to not spam localhost
DEFAULT_INTERVAL = 20

# Request timeout in seconds — keep short so a hung server doesn't stall the thread
DEFAULT_TIMEOUT = 5


class ServiceHealthPoller(QThread):
    """
    Background poller for a single service URL.

    Create one instance per service. Connect status_changed, then call start().
    Call stop() before the application closes.
    """

    status_changed = pyqtSignal(bool, str)  # (healthy, detail)

    def __init__(
        self,
        name: str,
        url: str,
        interval: int = DEFAULT_INTERVAL,
        timeout: int = DEFAULT_TIMEOUT,
        parent=None,
    ):
        super().__init__(parent)
        self._name = name
        self._url = url
        self._interval = interval
        self._timeout = timeout
        self._running = True
        self._last_healthy: bool | None = None  # None = never emitted yet

    def stop(self):
        """Signal the thread to exit on its next sleep tick."""
        self._running = False

    # ---------------------------------------------------------------- run

    def run(self):
        # Small initial delay so the service has a moment to start before
        # the first poll fires — avoids a guaranteed false-negative on launch.
        self._sleep(3)

        while self._running:
            healthy, detail = self._check()
            # Only emit when state flips (or on the very first check)
            if healthy != self._last_healthy:
                self._last_healthy = healthy
                self.status_changed.emit(healthy, detail)
            self._sleep(self._interval)

    # ---------------------------------------------------------------- helpers

    def _check(self) -> tuple[bool, str]:
        """
        Perform a single HTTP GET and return (healthy, detail).
        healthy=True  → 2xx or 401/403
        healthy=False → connection error, timeout, or 5xx
        """
        try:
            req = urllib.request.Request(self._url, method="GET")
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                code = resp.status
                if 200 <= code < 400:
                    return True, f"HTTP {code}"
                if code in _AUTH_CODES:
                    return True, f"HTTP {code} (auth required — service is up)"
                return False, f"HTTP {code}"
        except urllib.error.HTTPError as e:
            if e.code in _AUTH_CODES:
                return True, f"HTTP {e.code} (auth required — service is up)"
            return False, f"HTTP {e.code}: {e.reason}"
        except urllib.error.URLError as e:
            reason = str(e.reason)
            if "refused" in reason.lower():
                return False, "Connection refused — service not running"
            return False, f"Unreachable: {reason}"
        except TimeoutError:
            return False, f"Timed out after {self._timeout}s"
        except Exception as e:
            return False, f"Poll error: {e}"

    def _sleep(self, seconds: float):
        """
        Sleep in 0.5s increments so stop() is responsive within half a second.
        """
        elapsed = 0.0
        while elapsed < seconds and self._running:
            time.sleep(0.5)
            elapsed += 0.5
