"""
anythingllm_client.py — Mimir AnythingLLM REST Client

Wraps AnythingLLM's local HTTP API (default: localhost:3001).
Handles auth token management, workspace operations, document indexing,
RAG queries, and system configuration.

No external dependencies — pure urllib.
"""

import json
import urllib.request
import urllib.error
from typing import Optional, List, Dict, Any


# ============================================================
# Exceptions
# ============================================================

class AnythingLLMError(Exception):
    pass

class AnythingLLMConnectionError(AnythingLLMError):
    """Server not reachable."""
    pass

class AnythingLLMAuthError(AnythingLLMError):
    """Auth token missing, invalid, or not yet set up."""
    pass

class AnythingLLMNotReadyError(AnythingLLMError):
    """Server is running but not yet initialized."""
    pass


# ============================================================
# Data classes (lightweight — no dataclass deps needed)
# ============================================================

class WorkspaceInfo:
    def __init__(self, data: dict):
        self.id: int = data.get("id", 0)
        self.name: str = data.get("name", "")
        self.slug: str = data.get("slug", "")
        self.system_prompt: str = data.get("openAiPrompt") or data.get("prompt") or ""
        self.doc_count: int = len(data.get("documents", []))
        self.chat_model: str = data.get("chatModel") or ""
        self.raw = data

    def __repr__(self):
        return f"WorkspaceInfo(name={self.name!r}, slug={self.slug!r}, docs={self.doc_count})"


class DocumentInfo:
    def __init__(self, data: dict):
        self.id: int = data.get("id", 0)
        self.name: str = data.get("name", "")
        self.location: str = data.get("location", "")
        self.token_count: int = data.get("token_count_estimate", 0)
        self.raw = data


class QueryResult:
    def __init__(self, data: dict):
        self.answer: str = data.get("textResponse", "")
        self.sources: List[dict] = data.get("sources", [])
        self.error: Optional[str] = data.get("error")
        self.close: bool = data.get("close", False)
        print(f"[ATLLM DEBUG] QueryResult keys={list(data.keys())} answer={self.answer[:120]!r} error={self.error!r}")

    @property
    def has_sources(self) -> bool:
        return len(self.sources) > 0


# ============================================================
# Client
# ============================================================

class AnythingLLMClient:
    """
    REST client for AnythingLLM's local API.
    Call set_token() after obtaining an auth token.
    """

    WORKSPACE_SLUG = "mimir"      # The slug for the Mimir workspace
    WORKSPACE_NAME = "Mimir"

    def __init__(self, host: str = "127.0.0.1", port: int = 3001, timeout: int = 120):
        self._host = host
        self._port = port
        self._timeout = timeout
        self._base_url = f"http://{host}:{port}"
        self._token: Optional[str] = None

    @property
    def base_url(self) -> str:
        return self._base_url

    def set_token(self, token: str):
        self._token = token

    def has_token(self) -> bool:
        return bool(self._token)

    # ---- Internal helpers ----

    def _headers(self, extra: Optional[dict] = None) -> dict:
        h = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        if extra:
            h.update(extra)
        return h

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _request(self, method: str, path: str,
                 payload: Optional[dict] = None,
                 timeout: Optional[int] = None) -> dict:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            self._url(path),
            data=body,
            headers=self._headers(),
            method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout or self._timeout) as resp:
                raw = resp.read().decode("utf-8")
                if not raw.strip():
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace")
            try:
                err_data = json.loads(body_text)
                msg = err_data.get("message") or err_data.get("error") or body_text
            except Exception:
                msg = body_text
            if e.code == 401 or e.code == 403:
                raise AnythingLLMAuthError(f"Auth failed ({e.code}): {msg}") from e
            raise AnythingLLMError(f"{method} {path} HTTP {e.code}: {msg}") from e
        except urllib.error.URLError as e:
            raise AnythingLLMConnectionError(
                f"Cannot reach AnythingLLM at {self._base_url}: {e.reason}"
            ) from e

    def _get(self, path: str) -> dict:
        return self._request("GET", path)

    def _post(self, path: str, payload: dict = None, timeout: int = None) -> dict:
        return self._request("POST", path, payload, timeout)

    def _delete(self, path: str) -> dict:
        return self._request("DELETE", path)

    # ---- Health / Connectivity ----

    def is_running(self) -> bool:
        """Returns True if AnythingLLM is reachable."""
        try:
            self._get("/api/ping")
            return True
        except (AnythingLLMConnectionError, AnythingLLMError):
            return False

    def ping(self) -> float:
        """Returns response time in ms, or -1.0 if unreachable."""
        import time
        start = time.monotonic()
        try:
            self._get("/api/ping")
            return round((time.monotonic() - start) * 1000, 1)
        except Exception:
            return -1.0

    def is_setup_complete(self) -> bool:
        """
        Returns True if AnythingLLM has completed its initial setup
        (i.e., an admin user exists / single-user mode is active).
        """
        try:
            data = self._get("/api/auth")
            # If multi_user_mode is False, single-user mode is active
            return not data.get("requiresAuth", True) or data.get("isSetup", False)
        except Exception:
            return False

    # ---- Authentication ----

    def request_token_single_user(self, password: str = "") -> Optional[str]:
        """
        Obtain an auth token in single-user (no-auth) mode.
        In desktop/local mode, AnythingLLM can operate without a password.
        Returns the token string, or None on failure.
        """
        try:
            data = self._post("/api/request-token", {"password": password})
            token = data.get("token")
            if token:
                self._token = token
            return token
        except AnythingLLMAuthError:
            return None
        except Exception:
            return None

    def validate_token(self) -> bool:
        """Returns True if the current token is valid."""
        if not self._token:
            return False
        try:
            self._get("/api/auth")
            return True
        except AnythingLLMAuthError:
            return False
        except Exception:
            return False

    # ---- System Preferences ----

    def get_system_preferences(self) -> dict:
        """Returns the current system configuration."""
        data = self._get("/api/system-preferences")
        return data.get("settings", data)

    def update_system_preferences(self, prefs: dict) -> bool:
        """
        Update system settings (LLM provider, embedding model, etc.).
        Returns True on success.
        """
        try:
            self._post("/api/system-preferences", prefs)
            return True
        except AnythingLLMError:
            return False

    def configure_ollama_llm(self, base_url: str, model: str,
                              token_limit: int = 8192, temperature: float = 0.7) -> bool:
        """Configure Ollama as the LLM provider."""
        return self.update_system_preferences({
            "LLMProvider": "ollama",
            "OllamaLLMBasePath": base_url,
            "OllamaLLMModelPref": model,
            "OllamaLLMTokenLimit": token_limit,
            "OllamaLLMPerformancePref": "max",
        })

    def configure_ollama_embedding(self, base_url: str,
                                    model: str = "nomic-embed-text") -> bool:
        """Configure Ollama as the embedding engine."""
        return self.update_system_preferences({
            "EmbeddingEngine": "ollama",
            "EmbeddingBasePath": base_url,
            "EmbeddingModelPref": model,
        })

    def configure_vector_db(self, engine: str = "lancedb") -> bool:
        """Set the vector database. lancedb is built-in and requires no extra setup."""
        return self.update_system_preferences({"vectorDB": engine})

    # ---- Workspaces ----

    def list_workspaces(self) -> List[WorkspaceInfo]:
        try:
            data = self._get("/api/workspaces")
            return [WorkspaceInfo(w) for w in data.get("workspaces", [])]
        except Exception:
            return []

    def get_workspace(self, slug: str) -> Optional[WorkspaceInfo]:
        """Returns the workspace with the given slug, or None if not found."""
        workspaces = self.list_workspaces()
        for ws in workspaces:
            if ws.slug == slug:
                return ws
        return None

    def mimir_workspace_exists(self) -> bool:
        return self.get_workspace(self.WORKSPACE_SLUG) is not None

    def create_workspace(self, name: str) -> Optional[WorkspaceInfo]:
        """Create a new workspace. Returns WorkspaceInfo on success."""
        try:
            data = self._post("/api/workspace/new", {"name": name})
            ws_data = data.get("workspace", data)
            return WorkspaceInfo(ws_data)
        except AnythingLLMError:
            return None

    def update_workspace(self, slug: str, updates: dict) -> bool:
        """Update workspace settings (system prompt, model, etc.)."""
        try:
            self._post(f"/api/workspace/{slug}/update", updates)
            return True
        except AnythingLLMError:
            return False

    def set_workspace_system_prompt(self, slug: str, prompt: str) -> bool:
        """Set the system prompt for a workspace."""
        return self.update_workspace(slug, {"openAiPrompt": prompt})

    def set_workspace_chat_model(self, slug: str, model: str) -> bool:
        """
        Set the LLM model for a specific workspace.
        If blank/None, the workspace uses the system-wide model setting.
        """
        return self.update_workspace(slug, {"chatModel": model or ""})

    def ensure_mimir_workspace(self, system_prompt: str) -> Optional[WorkspaceInfo]:
        """
        Create the Mimir workspace if it doesn't exist, or return the existing one.
        Sets the system prompt either way.
        """
        ws = self.get_workspace(self.WORKSPACE_SLUG)

        if ws is None:
            ws = self.create_workspace(self.WORKSPACE_NAME)
            if ws is None:
                return None

        # Always (re)apply the system prompt to catch any updates
        self.set_workspace_system_prompt(ws.slug, system_prompt)
        return ws

    # ---- Documents ----

    def upload_text_document(self, content: str, title: str,
                              metadata: Optional[dict] = None) -> Optional[DocumentInfo]:
        """
        Upload a plain-text document to AnythingLLM's document store.
        Returns DocumentInfo with the document's location for workspace embedding.
        """
        payload = {
            "textContent": content,
            "metadata": {
                "title": title,
                "docSource": "mimir-knowledge-base",
                **(metadata or {})
            }
        }
        try:
            data = self._post("/api/v1/document/raw-text", payload, timeout=60)
            doc_data = data.get("documents", [{}])[0] if data.get("documents") else data
            return DocumentInfo(doc_data)
        except AnythingLLMError:
            return None

    def list_documents(self) -> List[DocumentInfo]:
        """List all documents in AnythingLLM's document store."""
        try:
            data = self._get("/api/v1/documents")
            items = data.get("localFiles", {}).get("items", [])
            docs = []
            for folder in items:
                for item in folder.get("items", []):
                    docs.append(DocumentInfo(item))
            return docs
        except Exception:
            return []

    def add_documents_to_workspace(self, slug: str,
                                    doc_locations: List[str]) -> bool:
        """
        Add documents (by their location strings) to a workspace's vector index.
        This triggers the embedding process.
        """
        if not doc_locations:
            return True
        try:
            self._post(
                f"/api/workspace/{slug}/update-embeddings",
                {"adds": doc_locations, "deletes": []},
                timeout=300
            )
            return True
        except AnythingLLMError:
            return False

    def remove_documents_from_workspace(self, slug: str,
                                         doc_locations: List[str]) -> bool:
        if not doc_locations:
            return True
        try:
            self._post(
                f"/api/workspace/{slug}/update-embeddings",
                {"adds": [], "deletes": doc_locations},
                timeout=60
            )
            return True
        except AnythingLLMError:
            return False

    # ---- Querying ----

    def query(self, slug: str, question: str, mode: str = "query") -> QueryResult:
        """
        Send a RAG query to a workspace.
        mode: "query" (RAG only) or "chat" (RAG + conversation history)
        """
        try:
            data = self._post(
                f"/api/workspace/{slug}/query",
                {"message": question, "mode": mode},
                timeout=300
            )
            return QueryResult(data)
        except AnythingLLMError as e:
            return QueryResult({"textResponse": "", "error": str(e)})

    def chat(self, slug: str, message: str,
             history: Optional[List[dict]] = None) -> QueryResult:
        """
        Chat with a workspace (supports conversation history for multi-turn).
        """
        payload: Dict[str, Any] = {"message": message, "mode": "chat"}
        if history:
            payload["history"] = history
        try:
            data = self._post(
                f"/api/workspace/{slug}/chat",
                payload,
                timeout=300
            )
            return QueryResult(data)
        except AnythingLLMError as e:
            return QueryResult({"textResponse": "", "error": str(e)})

    def get_workspace_chats(self, slug: str) -> List[dict]:
        """Returns the chat history for a workspace."""
        try:
            data = self._get(f"/api/workspace/{slug}/chats")
            return data.get("history", [])
        except Exception:
            return []

    # ---- Utility ----

    def version(self) -> Optional[str]:
        try:
            data = self._get("/api/system-preferences")
            return data.get("version")
        except Exception:
            return None
