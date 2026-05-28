"""
service_manager.py — Mimir Service Lifecycle Manager
Starts, monitors, and shuts down background services:
  - Ollama (AI inference server)
  - AnythingLLM (RAG interface)
  - Jellyfin (media server)

All processes are attached to this manager. When the launcher exits,
they are shut down cleanly.
"""

import subprocess
import os
import sys
import time
import json
import secrets
import threading
import ctypes
import ctypes.wintypes
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field


def _hide_window_by_title(title_fragment: str, timeout: int = 10) -> None:
    """
    Polls the Windows desktop for a visible top-level window whose title contains
    `title_fragment`, then hides it with ShowWindow(hwnd, SW_HIDE).

    Runs in a daemon thread. Polls every 250 ms for up to `timeout` seconds.
    Silently exits if the window never appears (process crashed, etc.).
    """
    user32 = ctypes.windll.user32
    SW_HIDE = 0

    WNDENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.c_bool,
        ctypes.wintypes.HWND,
        ctypes.wintypes.LPARAM,
    )

    deadline = time.time() + timeout
    while time.time() < deadline:
        found = []

        def _cb(hwnd, _lparam, _found=found):
            if user32.IsWindowVisible(hwnd):
                buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, buf, 256)
                if title_fragment in buf.value:
                    _found.append(hwnd)
            return True  # keep enumerating

        user32.EnumWindows(WNDENUMPROC(_cb), 0)

        if found:
            for hwnd in found:
                user32.ShowWindow(hwnd, SW_HIDE)
            return

        time.sleep(0.25)


@dataclass
class ServiceStatus:
    name: str
    running: bool = False
    pid: Optional[int] = None
    error: Optional[str] = None
    port: Optional[int] = None

    @property
    def status_label(self) -> str:
        if self.error:
            return f"Error: {self.error}"
        return "Running" if self.running else "Stopped"


class ServiceManager:
    """
    Manages the lifecycle of Mimir's background services.
    Call start_all() after model selection, shutdown() on app exit.
    """

    def __init__(self, paths, settings):
        self._paths = paths
        self._settings = settings
        self._processes: dict = {}
        self._statuses: dict = {
            "ollama": ServiceStatus("Ollama", port=settings.ollama_port),
            "anythingllm": ServiceStatus("AnythingLLM", port=settings.anythingllm_port),
            "jellyfin": ServiceStatus("Jellyfin", port=settings.jellyfin_port),
        }

    def get_status(self, service_id: str) -> ServiceStatus:
        return self._statuses.get(service_id, ServiceStatus(service_id))

    def get_all_statuses(self) -> dict:
        return dict(self._statuses)

    # ---- Ollama ----

    def start_ollama(self, model_id: str) -> ServiceStatus:
        """
        Starts the Ollama server with the appropriate model configured.
        Sets OLLAMA_MODELS and OLLAMA_HOST environment variables.
        """
        status = self._statuses["ollama"]
        ollama_exe = self._paths.ollama_exe

        if not ollama_exe.exists():
            status.error = f"ollama.exe not found at {ollama_exe}"
            return status

        env = os.environ.copy()
        env["OLLAMA_MODELS"] = str(self._paths.models_dir)
        env["OLLAMA_HOST"] = f"127.0.0.1:{self._settings.ollama_port}"

        try:
            proc = subprocess.Popen(
                [str(ollama_exe), "serve"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW  # Don't show a console window
            )
            self._processes["ollama"] = proc
            status.running = True
            status.pid = proc.pid
            status.error = None
        except Exception as e:
            status.error = str(e)
            status.running = False

        return status

    def wait_for_ollama(self, timeout_seconds: int = 30) -> bool:
        """
        Polls the Ollama API until it responds or times out.
        Returns True if Ollama is ready.
        """
        url = f"http://127.0.0.1:{self._settings.ollama_port}/api/tags"
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    if response.status == 200:
                        return True
            except Exception:
                pass
            time.sleep(0.5)
        return False

    def pull_model_if_missing(self, ollama_model_name: str) -> bool:
        """
        Checks if the specified model is available in Ollama.
        Returns True if present, False if it needs to be downloaded.
        Does NOT trigger a download — that's the user's action.
        """
        url = f"http://127.0.0.1:{self._settings.ollama_port}/api/tags"
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                import json
                data = json.loads(response.read())
                model_names = [m.get("name", "") for m in data.get("models", [])]
                # Match on the base name (before colon) as a fallback
                base_name = ollama_model_name.split(":")[0]
                return any(
                    ollama_model_name in name or base_name in name
                    for name in model_names
                )
        except Exception:
            return False

    # ---- AnythingLLM ----

    def prepare_anythingllm_env(self, ollama_model: str,
                                 context_window: int = 8192) -> bool:
        """
        Write the .env file to the AnythingLLM data directory before launch.
        Reads the template from the launcher config, substitutes runtime values,
        and writes the final .env.
        Returns True on success.
        """
        template_path = (
            self._paths.config / "anythingllm.env.template"
        )
        env_output_path = self._paths.anythingllm_data / ".env"

        if not template_path.exists():
            return False

        try:
            template = template_path.read_text(encoding="utf-8")
        except IOError:
            return False

        # Generate a JWT secret if we don't have one stored yet
        jwt_secret = self._settings.get_nested(
            "anythingllm", "jwt_secret", default=None
        )
        if not jwt_secret:
            jwt_secret = secrets.token_hex(32)
            self._settings.set_nested("anythingllm", "jwt_secret", value=jwt_secret)

        storage_dir = str(self._paths.anythingllm_data).replace("\\", "/")

        env_content = (
            template
            .replace("PLACEHOLDER_STORAGE_DIR", storage_dir)
            .replace("PLACEHOLDER_MODEL", ollama_model)
            .replace("PLACEHOLDER_CONTEXT_WINDOW", str(context_window))
            .replace("PLACEHOLDER_JWT_SECRET", jwt_secret)
        )

        try:
            self._paths.anythingllm_data.mkdir(parents=True, exist_ok=True)
            env_output_path.write_text(env_content, encoding="utf-8")
            return True
        except IOError:
            return False

    def start_anythingllm(self) -> ServiceStatus:
        """
        Starts AnythingLLM Desktop and hides its window immediately after it appears.

        AnythingLLM Desktop (Electron) does not support a headless flag, so we:
          1. Spawn the process with STARTF_USESHOWWINDOW + SW_HIDE to suppress the
             initial window creation hint (Electron may ignore this).
          2. Fire a background thread that polls for the AnythingLLM window by title
             for up to 10 seconds and calls ShowWindow(hwnd, SW_HIDE) the moment it
             appears — guaranteed to hide it even if Electron ignores step 1.
        """
        status = self._statuses["anythingllm"]

        if not self._settings.get_nested("services", "start_anythingllm_on_launch", default=True):
            status.error = "Disabled in settings"
            return status

        anythingllm_exe = self._paths.anythingllm_exe

        if not anythingllm_exe.exists():
            status.error = f"AnythingLLM.exe not found at {anythingllm_exe}"
            return status

        env = os.environ.copy()
        env["STORAGE_DIR"] = str(self._paths.anythingllm_data)

        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE hint to the process
            proc = subprocess.Popen(
                [str(anythingllm_exe)],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self._processes["anythingllm"] = proc
            status.running = True
            status.pid = proc.pid
            status.error = None

            # Belt-and-suspenders: hide the window via Windows API once it appears.
            # Runs in a daemon thread so it never blocks the launcher.
            t = threading.Thread(
                target=_hide_window_by_title,
                args=("AnythingLLM",),
                daemon=True,
            )
            t.start()

        except Exception as e:
            status.error = str(e)
            status.running = False

        return status

    # ---- Jellyfin ----

    def start_jellyfin(self) -> ServiceStatus:
        """Starts Jellyfin media server with data directory on the drive."""
        status = self._statuses["jellyfin"]

        if not self._settings.get_nested("services", "start_jellyfin_on_launch", default=True):
            status.error = "Disabled in settings"
            return status

        jellyfin_exe = self._paths.jellyfin_exe

        if not jellyfin_exe.exists():
            status.error = f"jellyfin.exe not found at {jellyfin_exe}"
            return status

        # Write portable config files before starting (idempotent — no-op if files exist)
        try:
            from jellyfin_config import (
                prepare_jellyfin_data_dirs,
                write_jellyfin_config,
                write_logging_config,
            )
            prepare_jellyfin_data_dirs(self._paths.jellyfin_data)
            write_jellyfin_config(
                self._paths.jellyfin_data,
                jellyfin_port=self._settings.jellyfin_port
            )
            write_logging_config(self._paths.jellyfin_data)
        except Exception as e:
            # Config write failure is non-fatal — Jellyfin will use its own defaults
            print(f"[Jellyfin] Config write warning: {e}")

        try:
            proc = subprocess.Popen(
                [
                    str(jellyfin_exe),
                    f"--datadir={self._paths.jellyfin_data}",
                    f"--cachedir={self._paths.jellyfin_data / 'cache'}",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(jellyfin_exe.parent),
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            self._processes["jellyfin"] = proc
            status.running = True
            status.pid = proc.pid
            status.error = None
        except Exception as e:
            status.error = str(e)
            status.running = False

        return status

    # ---- Lifecycle ----

    def start_all(self, model_id: str) -> dict:
        """Start all configured services. Returns status dict."""
        self.start_ollama(model_id)
        self.start_anythingllm()
        self.start_jellyfin()
        return self.get_all_statuses()

    def check_all(self):
        """Update running status for all managed processes."""
        for service_id, proc in self._processes.items():
            status = self._statuses[service_id]
            if proc.poll() is not None:
                # Process has exited
                status.running = False
                if not status.error:
                    status.error = f"Exited unexpectedly (code {proc.returncode})"

    def shutdown(self):
        """Gracefully terminate all managed services."""
        for service_id, proc in self._processes.items():
            try:
                proc.terminate()
                # Give it 3 seconds to shut down cleanly
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                self._statuses[service_id].running = False
            except Exception:
                pass
        self._processes.clear()

    def __del__(self):
        self.shutdown()
