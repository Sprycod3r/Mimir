"""
anythingllm_setup.py — Mimir AnythingLLM First-Run Setup

Runs after AnythingLLM starts for the first time.
Handles:
  1. Waiting for AnythingLLM to be ready
  2. Auth token acquisition (single-user / no-auth mode)
  3. System-wide LLM provider config → Ollama
  4. Embedding engine config → Ollama + nomic-embed-text
  5. Vector DB config → LanceDB (built-in, no extra setup)
  6. Mimir workspace creation
  7. System prompt deployment
  8. Embedding model pull check (nomic-embed-text via Ollama)

Runs in a QThread so it doesn't block the UI.
Emits granular progress signals the service start screen can display.
"""

# Satisfy type checker for Optional import used in AnythingLLMSetupState
from typing import Optional, Any

import time
from PyQt6.QtCore import QThread, pyqtSignal

from anythingllm_client import (
    AnythingLLMClient, AnythingLLMConnectionError,
    AnythingLLMAuthError, AnythingLLMError
)
from ollama_client import OllamaClient


EMBEDDING_MODEL = "nomic-embed-text"
SETUP_TIMEOUT_SECONDS = 60


class AnythingLLMSetupWorker(QThread):
    """
    Runs AnythingLLM first-run setup off the main thread.

    Signals:
      step(str)               — description of current step
      token_acquired(str)     — emits the auth token when obtained
      setup_complete()        — all steps done, workspace ready
      setup_failed(str)       — error message, setup could not complete
      embedding_model_missing()  — nomic-embed-text needs to be pulled
    """

    step = pyqtSignal(str)
    token_acquired = pyqtSignal(str)
    setup_complete = pyqtSignal()
    setup_failed = pyqtSignal(str)
    embedding_model_missing = pyqtSignal()

    def __init__(self, atllm_client: AnythingLLMClient,
                 ollama_client: OllamaClient,
                 ollama_base_url: str,
                 ollama_model_name: str,
                 system_prompt: str,
                 ollama_context_window: int = 8192,
                 parent=None):
        super().__init__(parent)
        self._atllm = atllm_client
        self._ollama = ollama_client
        self._ollama_base_url = ollama_base_url
        self._ollama_model = ollama_model_name
        self._ollama_ctx = ollama_context_window
        self._system_prompt = system_prompt

    def run(self):
        try:
            self._run_setup()
        except AnythingLLMConnectionError as e:
            self.setup_failed.emit(f"Cannot reach AnythingLLM: {e}")
        except AnythingLLMAuthError as e:
            self.setup_failed.emit(f"AnythingLLM auth error: {e}")
        except AnythingLLMError as e:
            self.setup_failed.emit(f"AnythingLLM error: {e}")
        except Exception as e:
            self.setup_failed.emit(f"Unexpected error during setup: {e}")

    def _run_setup(self):
        # ---- Step 1: Wait for AnythingLLM ----
        self.step.emit("Waiting for AnythingLLM to start...")
        if not self._wait_for_ready():
            self.setup_failed.emit(
                "AnythingLLM did not respond within the expected time. "
                "Check that AnythingLLM.exe is present and functional."
            )
            return

        # ---- Step 2: Auth token ----
        self.step.emit("Acquiring auth token...")
        if not self._acquire_token():
            self.setup_failed.emit(
                "Could not obtain an auth token from AnythingLLM. "
                "It may require manual setup at http://localhost:3001."
            )
            return

        # ---- Step 3: Configure LLM provider ----
        self.step.emit(f"Configuring Ollama as LLM provider ({self._ollama_model})...")
        ok = self._atllm.configure_ollama_llm(
            base_url=self._ollama_base_url,
            model=self._ollama_model,
            token_limit=self._ollama_ctx,
        )
        if not ok:
            # Non-fatal — log and continue
            self.step.emit("Warning: could not set LLM provider. May need manual config.")

        # ---- Step 4: Configure embedding model ----
        self.step.emit(f"Configuring embedding engine ({EMBEDDING_MODEL})...")
        ok = self._atllm.configure_ollama_embedding(
            base_url=self._ollama_base_url,
            model=EMBEDDING_MODEL,
        )
        if not ok:
            self.step.emit("Warning: could not configure embedding engine.")

        # ---- Step 5: Check embedding model is downloaded ----
        self.step.emit(f"Checking for {EMBEDDING_MODEL}...")
        if not self._ollama.model_is_available(EMBEDDING_MODEL):
            self.step.emit(
                f"{EMBEDDING_MODEL} not found — pulling it now..."
            )
            self._pull_embedding_model()

        # ---- Step 6: Vector DB ----
        self.step.emit("Configuring vector database (LanceDB)...")
        self._atllm.configure_vector_db("lancedb")

        # ---- Step 7: Create / verify Mimir workspace ----
        self.step.emit("Setting up Mimir workspace...")
        ws = self._atllm.ensure_mimir_workspace(self._system_prompt)
        if ws is None:
            self.setup_failed.emit(
                "Could not create the Mimir workspace in AnythingLLM. "
                "Check the AnythingLLM logs for details."
            )
            return

        self.step.emit(f"Workspace ready: '{ws.name}' (slug: {ws.slug})")
        self.setup_complete.emit()

    def _wait_for_ready(self) -> bool:
        deadline = time.time() + SETUP_TIMEOUT_SECONDS
        while time.time() < deadline:
            if self._atllm.is_running():
                return True
            time.sleep(1.0)
        return False

    def _acquire_token(self) -> bool:
        """
        Try to get an auth token. AnythingLLM Desktop in single-user mode
        accepts an empty password by default.
        """
        # First check if we already have a valid token
        if self._atllm.has_token() and self._atllm.validate_token():
            return True

        # Try single-user mode with no password
        token = self._atllm.request_token_single_user(password="")
        if token:
            self.token_acquired.emit(token)
            return True

        # Try with a check — some versions don't require auth at all
        if self._atllm.is_running():
            # Attempt a basic API call without auth
            try:
                self._atllm.list_workspaces()
                return True
            except AnythingLLMAuthError:
                return False
            except Exception:
                return False

        return False

    def _pull_embedding_model(self):
        """Pull the embedding model via Ollama if it's not present."""
        try:
            self.step.emit(f"Downloading {EMBEDDING_MODEL} — this may take a few minutes...")
            # Pull synchronously from the worker thread
            for progress in self._ollama.pull_model(EMBEDDING_MODEL):
                if progress.total > 0 and progress.percent > 0:
                    self.step.emit(
                        f"Downloading {EMBEDDING_MODEL}: {progress.percent:.0f}%"
                    )
            self.step.emit(f"{EMBEDDING_MODEL} downloaded successfully.")
        except Exception as e:
            self.step.emit(
                f"Warning: could not pull {EMBEDDING_MODEL}: {e}. "
                "Document search may not work until it's downloaded."
            )
            self.embedding_model_missing.emit()


# ============================================================
# Setup State Manager
# Tracks whether first-run setup has already been completed
# so we don't re-run it on every launch.
# ============================================================

class AnythingLLMSetupState:
    """
    Persists setup completion state to avoid re-running every launch.
    Stored in mimir.json under the 'anythingllm' key.
    """

    def __init__(self, settings_manager):
        self._settings = settings_manager

    def is_setup_complete(self) -> bool:
        return bool(
            self._settings.get_nested("anythingllm", "setup_complete", default=False)
        )

    def mark_complete(self, token: str, workspace_slug: str):
        self._settings.set_nested("anythingllm", "setup_complete", value=True)
        self._settings.set_nested("anythingllm", "token", value=token)
        self._settings.set_nested("anythingllm", "workspace_slug", value=workspace_slug)

    def get_token(self) -> Optional[str]:
        return self._settings.get_nested("anythingllm", "token", default=None)

    def get_workspace_slug(self) -> str:
        return self._settings.get_nested(
            "anythingllm", "workspace_slug",
            default=AnythingLLMClient.WORKSPACE_SLUG
        )

    def reset(self):
        """Force re-run of setup on next launch."""
        self._settings.set_nested("anythingllm", "setup_complete", value=False)



