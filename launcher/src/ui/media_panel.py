"""
media_panel.py — Mimir Media Center Panel

When Jellyfin is responding, shows three launch options:
  1. Open in Browser — system default browser at http://localhost:{port}
  2. Open in VLC     — VLC media player with Jellyfin URL (if VLC is installed)
  3. Open in App     — embedded QWebEngineView (if PyQt6-WebEngine is installed)

States:
  waiting  — Jellyfin has been started, not yet responding to HTTP
  ready    — Jellyfin is up; showing the three launch-option tiles
  webview  — user clicked "Open in App"; embedded view is loaded
  error    — Jellyfin failed to start or timed out

VLC detection:
  C:\\Program Files\\VideoLAN\\VLC\\vlc.exe
  C:\\Program Files (x86)\\VideoLAN\\VLC\\vlc.exe

Public API:
  set_jellyfin_status(healthy: bool, error: str = None)
      Called by main_interface.py when service health changes.
"""

import subprocess
import time
import urllib.request
import urllib.error
import webbrowser
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QStackedWidget
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QFont

# Optional WebEngine import — graceful fallback if not installed
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    _WEBENGINE_AVAILABLE = True
except ImportError:
    _WEBENGINE_AVAILABLE = False


_POLL_INTERVAL_S = 2
_MAX_POLLS = 90  # 2s × 90 = 3 minutes

_VLC_PATHS = [
    Path(r"C:\Program Files\VideoLAN\VLC\vlc.exe"),
    Path(r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"),
]


def _find_vlc() -> Optional[Path]:
    for p in _VLC_PATHS:
        if p.exists():
            return p
    return None


# ============================================================
# Poller Thread
# ============================================================

class _JellyfinPoller(QThread):
    """
    Background thread that HTTP-polls Jellyfin without blocking the UI.

    Signals:
      ready()    — Jellyfin responded successfully
      tick(int)  — fired each poll cycle; -1 means timeout
    """
    ready = pyqtSignal()
    tick  = pyqtSignal(int)

    def __init__(self, url: str, interval: int = _POLL_INTERVAL_S,
                 max_polls: int = _MAX_POLLS, parent=None):
        super().__init__(parent)
        self._url = url
        self._interval = interval
        self._max_polls = max_polls
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        count = 0
        while self._running and count < self._max_polls:
            count += 1
            if self._check():
                self.ready.emit()
                return
            self.tick.emit(count)
            self._sleep(self._interval)
        if count >= self._max_polls:
            self.tick.emit(-1)

    def _check(self) -> bool:
        for url, ok_codes in (
            (f"{self._url}/health", {200, 401, 403}),
            (self._url,             None),
        ):
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=1) as resp:
                    if ok_codes is None:
                        if resp.status < 500:
                            return True
                    elif resp.status in ok_codes:
                        return True
            except Exception:
                pass
        return False

    def _sleep(self, seconds: float):
        elapsed = 0.0
        while elapsed < seconds and self._running:
            time.sleep(0.5)
            elapsed += 0.5


# ============================================================
# Waiting Overlay
# ============================================================

class _WaitingOverlay(QWidget):
    """Shown while Jellyfin is starting."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("media-waiting")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        icon = QLabel("▶")
        icon.setObjectName("media-waiting-icon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_font = QFont()
        icon_font.setPointSize(36)
        icon.setFont(icon_font)

        self._status_label = QLabel("Starting Jellyfin media server...")
        self._status_label.setObjectName("media-status-text")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setWordWrap(True)

        self._sub_label = QLabel("This usually takes 5–15 seconds on first launch.")
        self._sub_label.setObjectName("media-status-sub")
        self._sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sub_label.setWordWrap(True)

        layout.addStretch()
        layout.addWidget(icon)
        layout.addWidget(self._status_label)
        layout.addWidget(self._sub_label)
        layout.addStretch()

    def set_status(self, text: str, sub: str = ""):
        self._status_label.setText(text)
        self._sub_label.setText(sub)
        self._sub_label.setVisible(bool(sub))


# ============================================================
# Error Overlay
# ============================================================

class _ErrorOverlay(QWidget):
    """Shown when Jellyfin fails to start or times out."""

    setup_requested = pyqtSignal()
    retry_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("media-error")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        icon = QLabel("⚠")
        icon.setObjectName("media-error-icon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_font = QFont()
        icon_font.setPointSize(32)
        icon.setFont(icon_font)

        title = QLabel("Jellyfin Not Available")
        title.setObjectName("media-error-title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setWeight(QFont.Weight.Bold)
        title.setFont(title_font)

        self._detail_label = QLabel("Jellyfin could not be started.")
        self._detail_label.setObjectName("media-error-detail")
        self._detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail_label.setWordWrap(True)

        hint = QLabel(
            "Make sure jellyfin.exe is present in tools/jellyfin/ on your drive.\n"
            "Check the Logs panel for details."
        )
        hint.setObjectName("media-error-hint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)

        self._setup_btn = QPushButton("Launch Jellyfin Setup")
        self._setup_btn.setObjectName("primary")
        self._setup_btn.setFixedHeight(40)
        self._setup_btn.setFixedWidth(220)
        self._setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._setup_btn.clicked.connect(self.setup_requested)

        self._setup_msg = QLabel("")
        self._setup_msg.setObjectName("media-error-hint")
        self._setup_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._setup_msg.setWordWrap(True)
        self._setup_msg.setVisible(False)

        self._retry_btn = QPushButton("Retry Connection")
        self._retry_btn.setObjectName("media-reload-btn")
        self._retry_btn.setFixedHeight(36)
        self._retry_btn.setFixedWidth(180)
        self._retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._retry_btn.clicked.connect(self.retry_requested)
        self._retry_btn.setVisible(False)

        layout.addStretch()
        layout.addWidget(icon)
        layout.addWidget(title)
        layout.addWidget(self._detail_label)
        layout.addSpacing(8)
        layout.addWidget(hint)
        layout.addSpacing(16)
        layout.addWidget(self._setup_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._setup_msg)
        layout.addWidget(self._retry_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()

    def set_error(self, error_msg: str):
        self._detail_label.setText(error_msg or "Jellyfin could not be started.")

    def show_starting(self):
        self._setup_btn.setText("Starting Jellyfin…")
        self._setup_btn.setEnabled(False)
        self._setup_msg.setText("Waiting for Jellyfin to come online…")
        self._setup_msg.setVisible(True)
        self._retry_btn.setVisible(False)

    def show_browser_opened(self):
        self._setup_msg.setText("Complete the setup in your browser, then click Retry.")
        self._retry_btn.setVisible(True)

    def reset_setup_btn(self):
        self._setup_btn.setText("Launch Jellyfin Setup")
        self._setup_btn.setEnabled(True)
        self._setup_msg.setVisible(False)
        self._retry_btn.setVisible(False)


# ============================================================
# Ready Panel — three launch options
# ============================================================

class _ReadyPanel(QWidget):
    """
    Shown when Jellyfin is responding.
    Three buttons: Open in Browser, Open in VLC, Open in App.
    Emits open_app_requested when the user wants the embedded webview.
    """
    open_app_requested = pyqtSignal()

    def __init__(self, jellyfin_url: str, parent=None):
        super().__init__(parent)
        self._url = jellyfin_url
        self._vlc_path = _find_vlc()
        self.setObjectName("media-ready")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)
        layout.setContentsMargins(60, 60, 60, 60)

        icon = QLabel("▶")
        icon.setObjectName("media-waiting-icon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_font = QFont()
        icon_font.setPointSize(36)
        icon.setFont(icon_font)

        title = QLabel("Jellyfin is running")
        title.setObjectName("media-ready-title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setWeight(QFont.Weight.Bold)
        title.setFont(title_font)

        subtitle = QLabel("Choose how to access your media:")
        subtitle.setObjectName("media-status-sub")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Three columns: Browser | VLC | App
        btn_row = QHBoxLayout()
        btn_row.setSpacing(24)
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.addStretch()
        btn_row.addLayout(self._make_browser_col())
        btn_row.addLayout(self._make_vlc_col())
        btn_row.addLayout(self._make_app_col())
        btn_row.addStretch()

        btn_row_widget = QWidget()
        btn_row_widget.setLayout(btn_row)

        layout.addStretch()
        layout.addWidget(icon)
        layout.addSpacing(8)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(24)
        layout.addWidget(btn_row_widget)
        layout.addStretch()

    def _make_button(self, label: str, enabled: bool = True) -> QPushButton:
        btn = QPushButton(label)
        btn.setObjectName("primary" if enabled else "media-open-btn")
        btn.setFixedHeight(52)
        btn.setFixedWidth(200)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setEnabled(enabled)
        return btn

    def _make_col(self, btn: QPushButton, note: str = "") -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(6)
        col.setContentsMargins(0, 0, 0, 0)
        col.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        if note:
            lbl = QLabel(note)
            lbl.setObjectName("media-status-sub")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(lbl)
        return col

    def _make_browser_col(self) -> QVBoxLayout:
        btn = self._make_button("Open in Browser")
        btn.clicked.connect(lambda: webbrowser.open(self._url))
        return self._make_col(btn)

    def _make_vlc_col(self) -> QVBoxLayout:
        if self._vlc_path:
            btn = self._make_button("Open in VLC")
            btn.clicked.connect(self._launch_vlc)
            return self._make_col(btn)
        else:
            btn = self._make_button("Open in VLC", enabled=False)
            btn.setToolTip("VLC not found at standard install paths")
            return self._make_col(btn, "VLC not installed")

    def _make_app_col(self) -> QVBoxLayout:
        if _WEBENGINE_AVAILABLE:
            btn = self._make_button("Open in App")
            btn.clicked.connect(self.open_app_requested)
            return self._make_col(btn)
        else:
            btn = self._make_button("Open in App", enabled=False)
            btn.setToolTip("PyQt6-WebEngine is not installed")
            return self._make_col(btn, "WebEngine not installed")

    def _launch_vlc(self):
        if self._vlc_path:
            subprocess.Popen(
                [str(self._vlc_path), self._url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )


# ============================================================
# Main Media Panel
# ============================================================

class MediaPanel(QWidget):
    """
    Mimir Media Center panel.

    Polls Jellyfin on startup. When it responds, shows _ReadyPanel with three
    launch options. "Open in App" switches to the embedded QWebEngineView.
    """

    def __init__(self, jellyfin_port: int = 8096, paths=None, parent=None):
        super().__init__(parent)
        self._port = jellyfin_port
        self._url = f"http://localhost:{jellyfin_port}"
        self._paths = paths
        self._ready = False
        self._poller: _JellyfinPoller = None
        self._webview = None
        self._setup_pending_browser = False

        self.setObjectName("media-panel")
        self._setup_ui()
        self._start_polling()

    # ----------------------------------------------------------------- layout

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ---- Toolbar ----
        toolbar = QWidget()
        toolbar.setObjectName("media-toolbar")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(16, 10, 16, 10)
        tb_layout.setSpacing(10)

        title = QLabel("Media Center")
        title.setObjectName("media-title")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setWeight(QFont.Weight.Bold)
        title.setFont(title_font)

        self._back_btn = QPushButton("← Back to options")
        self._back_btn.setObjectName("media-open-btn")
        self._back_btn.setFixedHeight(28)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.clicked.connect(self._on_back)
        self._back_btn.setVisible(False)

        self._reload_btn = QPushButton("↺ Reload")
        self._reload_btn.setObjectName("media-reload-btn")
        self._reload_btn.setFixedHeight(28)
        self._reload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reload_btn.clicked.connect(self._on_reload)
        self._reload_btn.setVisible(False)

        tb_layout.addWidget(title)
        tb_layout.addStretch()
        tb_layout.addWidget(self._back_btn)
        tb_layout.addWidget(self._reload_btn)
        layout.addWidget(toolbar)

        # ---- Separator ----
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("kb-separator")
        layout.addWidget(sep)

        # ---- Content stack ----
        self._content_stack = QStackedWidget()
        self._content_stack.setObjectName("media-content-stack")

        self._waiting = _WaitingOverlay()
        self._content_stack.addWidget(self._waiting)

        self._error_overlay = _ErrorOverlay()
        self._error_overlay.setup_requested.connect(self._on_setup_launch)
        self._error_overlay.retry_requested.connect(self._on_retry)
        self._content_stack.addWidget(self._error_overlay)

        self._ready_panel = _ReadyPanel(self._url)
        self._ready_panel.open_app_requested.connect(self._on_open_app)
        self._content_stack.addWidget(self._ready_panel)

        if _WEBENGINE_AVAILABLE:
            self._webview = QWebEngineView()
            self._webview.setObjectName("media-webview")
            settings = self._webview.settings()
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
            )
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False
            )
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.JavascriptEnabled, True
            )
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False
            )
            self._content_stack.addWidget(self._webview)

        layout.addWidget(self._content_stack, stretch=1)
        self._content_stack.setCurrentWidget(self._waiting)

    # ----------------------------------------------------------------- polling

    def _start_polling(self, max_polls: int = _MAX_POLLS):
        self._stop_polling()
        self._poller = _JellyfinPoller(self._url, max_polls=max_polls, parent=self)
        self._poller.ready.connect(self._on_jellyfin_ready)
        self._poller.tick.connect(self._on_poll_tick)
        self._poller.start()

    def _on_poll_tick(self, count: int):
        if self._ready:
            return
        if count == -1:
            if self._setup_pending_browser:
                self._setup_pending_browser = False
                self._error_overlay.set_error(
                    "Jellyfin did not respond within 60 seconds. "
                    "Check that jellyfin.exe started correctly."
                )
                self._error_overlay.reset_setup_btn()
            else:
                self._show_error(
                    f"Jellyfin did not respond after {_MAX_POLLS * _POLL_INTERVAL_S} seconds."
                )
        elif count >= 5:
            elapsed_s = count * _POLL_INTERVAL_S
            self._waiting.set_status(
                "Waiting for Jellyfin...",
                f"Still starting ({elapsed_s}s elapsed). Large libraries can take a moment."
            )

    def _stop_polling(self):
        if self._poller and self._poller.isRunning():
            self._poller.stop()
            self._poller.wait(500)
        self._poller = None

    def _on_jellyfin_ready(self):
        self._stop_polling()

        if self._setup_pending_browser:
            self._setup_pending_browser = False
            webbrowser.open(self._url)
            self._error_overlay.show_browser_opened()
            return

        self._ready = True
        self._content_stack.setCurrentWidget(self._ready_panel)

    def _show_error(self, error_msg: str = ""):
        self._error_overlay.set_error(error_msg)
        self._content_stack.setCurrentWidget(self._error_overlay)

    # ----------------------------------------------------------------- app view

    def _on_open_app(self):
        """User clicked 'Open in App' — load the embedded webview."""
        if _WEBENGINE_AVAILABLE and self._webview:
            if not self._webview.url().isValid() or self._webview.url().isEmpty():
                self._webview.load(QUrl(self._url))
            self._content_stack.setCurrentWidget(self._webview)
            self._back_btn.setVisible(True)
            self._reload_btn.setVisible(True)

    def _on_back(self):
        """Return from webview to the launch options."""
        self._content_stack.setCurrentWidget(self._ready_panel)
        self._back_btn.setVisible(False)
        self._reload_btn.setVisible(False)

    def _on_reload(self):
        if _WEBENGINE_AVAILABLE and self._webview:
            self._webview.reload()

    # ----------------------------------------------------------------- setup / retry

    def _on_setup_launch(self):
        if not self._paths:
            self._error_overlay.set_error("paths not available — cannot launch Jellyfin.")
            return

        jellyfin_exe = self._paths.jellyfin_exe
        if not jellyfin_exe.exists():
            self._error_overlay.set_error(f"jellyfin.exe not found at:\n{jellyfin_exe}")
            return

        try:
            from jellyfin_config import (
                prepare_jellyfin_data_dirs,
                write_jellyfin_config,
                write_logging_config,
            )
            prepare_jellyfin_data_dirs(self._paths.jellyfin_data)
            write_jellyfin_config(self._paths.jellyfin_data, jellyfin_port=self._port)
            write_logging_config(self._paths.jellyfin_data)
        except Exception:
            pass

        try:
            subprocess.Popen(
                [
                    str(jellyfin_exe),
                    f"--datadir={self._paths.jellyfin_data}",
                    f"--cachedir={self._paths.jellyfin_data / 'cache'}",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(jellyfin_exe.parent),
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception as e:
            self._error_overlay.set_error(f"Failed to start Jellyfin: {e}")
            return

        # Poll until Jellyfin responds, then open browser. 30 × 2s = 60s timeout.
        self._setup_pending_browser = True
        self._error_overlay.show_starting()
        self._start_polling(max_polls=30)

    def _on_retry(self):
        self._ready = False
        self._waiting.set_status("Checking for Jellyfin…", "")
        self._content_stack.setCurrentWidget(self._waiting)
        self._start_polling()

    # ----------------------------------------------------------------- public API

    def set_jellyfin_status(self, healthy: bool, error: str = None):
        if healthy and not self._ready:
            self._stop_polling()
            if not self._ready:
                self._start_polling()
        elif not healthy and error:
            self._stop_polling()
            self._show_error(error)

    def get_jellyfin_url(self) -> str:
        return self._url

    def is_ready(self) -> bool:
        return self._ready
