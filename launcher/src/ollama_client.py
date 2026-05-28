"""
ollama_client.py — Mimir Ollama REST API Client

Wraps Ollama's local HTTP API (default: localhost:11434).
No external dependencies — uses Python's built-in urllib and http.client only.

Key capabilities:
  - list_models()             — what's installed on this machine
  - model_is_available()      — is a specific model ready to use
  - get_model_info()          — size, parameters, quantization metadata
  - chat()                    — blocking multi-turn chat completion
  - stream_chat()             — streaming chat (yields token chunks)
  - generate()                — blocking single-turn completion
  - stream_generate()         — streaming single-turn (yields token chunks)
  - pull_model()              — download a model (yields progress updates)
  - embed()                   — generate embeddings (for RAG)
"""

import json
import urllib.request
import urllib.error
import http.client
from typing import Generator, Optional, Callable, List, Dict, Any
from dataclasses import dataclass, field


# ============================================================
# Data Classes
# ============================================================

@dataclass
class ModelInfo:
    name: str
    size_bytes: int = 0
    parameter_size: str = ""
    quantization: str = ""
    family: str = ""
    digest: str = ""

    @property
    def size_gb(self) -> float:
        return round(self.size_bytes / (1024 ** 3), 2)


@dataclass
class ChatMessage:
    role: str   # "system", "user", "assistant"
    content: str

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class ChatResponse:
    content: str
    model: str
    done: bool = True
    total_duration_ns: int = 0
    prompt_eval_count: int = 0
    eval_count: int = 0

    @property
    def tokens_per_second(self) -> float:
        if self.total_duration_ns > 0 and self.eval_count > 0:
            return round(self.eval_count / (self.total_duration_ns / 1e9), 1)
        return 0.0


@dataclass
class PullProgress:
    status: str             # e.g. "pulling manifest", "downloading", "verifying"
    digest: str = ""        # layer digest
    total: int = 0          # total bytes for this layer
    completed: int = 0      # bytes downloaded so far
    layer_index: int = 0
    layer_count: int = 0

    @property
    def percent(self) -> float:
        if self.total > 0:
            return round((self.completed / self.total) * 100, 1)
        return 0.0

    @property
    def completed_mb(self) -> float:
        return round(self.completed / (1024 ** 2), 1)

    @property
    def total_mb(self) -> float:
        return round(self.total / (1024 ** 2), 1)


class OllamaError(Exception):
    """Raised when Ollama returns an error or is unreachable."""
    pass


class OllamaConnectionError(OllamaError):
    """Ollama server is not running or not reachable."""
    pass


class OllamaModelNotFoundError(OllamaError):
    """The requested model is not available."""
    pass


# ============================================================
# Client
# ============================================================

class OllamaClient:
    """
    HTTP client for Ollama's local REST API.
    Thread-safe for read operations. Pull operations should not be
    run concurrently for the same model.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 11434, timeout: int = 30):
        self._host = host
        self._port = port
        self._timeout = timeout
        self._base_url = f"http://{host}:{port}"

    @property
    def base_url(self) -> str:
        return self._base_url

    # ---- Internal helpers ----

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _get(self, path: str) -> dict:
        """Make a GET request, return parsed JSON."""
        try:
            with urllib.request.urlopen(
                self._url(path), timeout=self._timeout
            ) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise OllamaConnectionError(
                f"Cannot reach Ollama at {self._base_url}: {e.reason}"
            ) from e
        except Exception as e:
            raise OllamaError(f"GET {path} failed: {e}") from e

    def _post(self, path: str, payload: dict, timeout: Optional[int] = None) -> dict:
        """Make a non-streaming POST request, return parsed JSON."""
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._url(path),
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(
                req, timeout=timeout or self._timeout
            ) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            try:
                error_data = json.loads(error_body)
                msg = error_data.get("error", error_body)
            except Exception:
                msg = error_body
            if "not found" in msg.lower() or e.code == 404:
                raise OllamaModelNotFoundError(msg) from e
            raise OllamaError(f"POST {path} HTTP {e.code}: {msg}") from e
        except urllib.error.URLError as e:
            raise OllamaConnectionError(
                f"Cannot reach Ollama at {self._base_url}: {e.reason}"
            ) from e

    def _post_stream(self, path: str, payload: dict) -> Generator[dict, None, None]:
        """
        Make a streaming POST request.
        Yields parsed JSON objects for each line received.
        Ollama streams NDJSON (newline-delimited JSON).
        """
        payload["stream"] = True
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._url(path),
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            try:
                msg = json.loads(error_body).get("error", error_body)
            except Exception:
                msg = error_body
            if "not found" in msg.lower():
                raise OllamaModelNotFoundError(msg) from e
            raise OllamaError(f"Stream POST {path} HTTP {e.code}: {msg}") from e
        except urllib.error.URLError as e:
            raise OllamaConnectionError(
                f"Cannot reach Ollama at {self._base_url}: {e.reason}"
            ) from e

    # ---- Connectivity ----

    def is_running(self) -> bool:
        """Quick check — returns True if Ollama is responding."""
        try:
            self._get("/api/tags")
            return True
        except (OllamaError, Exception):
            return False

    def ping(self) -> float:
        """
        Returns response time in milliseconds, or -1 if unreachable.
        """
        import time
        start = time.monotonic()
        try:
            self._get("/api/tags")
            return round((time.monotonic() - start) * 1000, 1)
        except Exception:
            return -1.0

    # ---- Model Management ----

    def list_models(self) -> List[ModelInfo]:
        """Returns a list of all models installed on this machine."""
        try:
            data = self._get("/api/tags")
        except OllamaConnectionError:
            return []

        models = []
        for m in data.get("models", []):
            details = m.get("details", {})
            models.append(ModelInfo(
                name=m.get("name", ""),
                size_bytes=m.get("size", 0),
                parameter_size=details.get("parameter_size", ""),
                quantization=details.get("quantization_level", ""),
                family=details.get("family", ""),
                digest=m.get("digest", ""),
            ))
        return models

    def model_is_available(self, model_name: str) -> bool:
        """
        Check if a specific model is installed and ready to use.
        Matches on exact name or base name (before the colon).
        """
        installed = self.list_models()
        if not installed:
            return False
        base_name = model_name.split(":")[0].lower()
        for m in installed:
            if m.name.lower() == model_name.lower():
                return True
            if m.name.lower().startswith(base_name + ":") or m.name.lower() == base_name:
                return True
        return False

    def get_model_info(self, model_name: str) -> Optional[ModelInfo]:
        """Returns detailed info about a specific model, or None if not found."""
        installed = self.list_models()
        base_name = model_name.split(":")[0].lower()
        for m in installed:
            if m.name.lower() == model_name.lower():
                return m
            if m.name.lower().startswith(base_name + ":"):
                return m
        return None

    def get_running_model(self) -> Optional[str]:
        """
        Returns the name of the model currently loaded in memory, if any.
        Uses /api/ps (available in Ollama 0.1.33+).
        """
        try:
            data = self._get("/api/ps")
            models = data.get("models", [])
            if models:
                return models[0].get("name")
        except Exception:
            pass
        return None

    # ---- Chat API ----

    def chat(
        self,
        model: str,
        messages: List[ChatMessage],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        context_window: Optional[int] = None,
        timeout: int = 120,
    ) -> ChatResponse:
        """
        Blocking chat completion. Returns a ChatResponse with the full reply.
        Use stream_chat() for token-by-token streaming.
        """
        msg_list = []
        if system_prompt:
            msg_list.append({"role": "system", "content": system_prompt})
        msg_list.extend([m if isinstance(m, dict) else m.to_dict() for m in messages])

        payload: Dict[str, Any] = {
            "model": model,
            "messages": msg_list,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if context_window:
            payload["options"]["num_ctx"] = context_window

        data = self._post("/api/chat", payload, timeout=timeout)

        msg = data.get("message", {})
        return ChatResponse(
            content=msg.get("content", ""),
            model=data.get("model", model),
            done=data.get("done", True),
            total_duration_ns=data.get("total_duration", 0),
            prompt_eval_count=data.get("prompt_eval_count", 0),
            eval_count=data.get("eval_count", 0),
        )

    def stream_chat(
        self,
        model: str,
        messages: List[ChatMessage],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        context_window: Optional[int] = None,
    ) -> Generator[str, None, None]:
        """
        Streaming chat completion.
        Yields each token string as it arrives from Ollama.
        The final yielded value will be an empty string (the done=True packet).

        Usage:
            for token in client.stream_chat(model, messages, system_prompt):
                print(token, end="", flush=True)
        """
        msg_list = []
        if system_prompt:
            msg_list.append({"role": "system", "content": system_prompt})
        msg_list.extend([m if isinstance(m, dict) else m.to_dict() for m in messages])

        payload: Dict[str, Any] = {
            "model": model,
            "messages": msg_list,
            "options": {"temperature": temperature},
        }
        if context_window:
            payload["options"]["num_ctx"] = context_window

        for chunk in self._post_stream("/api/chat", payload):
            msg = chunk.get("message", {})
            content = msg.get("content", "")
            if content:
                yield content
            if chunk.get("done", False):
                break

    # ---- Generate API (single-turn, no history) ----

    def generate(
        self,
        model: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        timeout: int = 120,
    ) -> str:
        """
        Blocking single-turn completion. Returns the response string.
        For multi-turn with history, use chat() instead.
        """
        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if system_prompt:
            payload["system"] = system_prompt

        data = self._post("/api/generate", payload, timeout=timeout)
        return data.get("response", "")

    def stream_generate(
        self,
        model: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
    ) -> Generator[str, None, None]:
        """Streaming single-turn completion. Yields token strings."""
        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "options": {"temperature": temperature},
        }
        if system_prompt:
            payload["system"] = system_prompt

        for chunk in self._post_stream("/api/generate", payload):
            token = chunk.get("response", "")
            if token:
                yield token
            if chunk.get("done", False):
                break

    # ---- Pull (Download) ----

    def pull_model(
        self,
        model_name: str,
        progress_callback: Optional[Callable[[PullProgress], None]] = None,
    ) -> Generator[PullProgress, None, None]:
        """
        Pull (download) a model from the Ollama registry.
        Yields PullProgress objects as download proceeds.
        Optionally calls progress_callback(progress) for each update.

        The generator is exhausted when the pull is complete.
        Raises OllamaError if the pull fails.

        Usage:
            for progress in client.pull_model("mistral:7b"):
                print(f"{progress.status}: {progress.percent}%")
        """
        payload = {"name": model_name, "stream": True}
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._url("/api/pull"),
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        layer_digests = {}   # digest → index
        layer_counter = [0]

        try:
            # Long timeout — pulls can take a while
            with urllib.request.urlopen(req, timeout=3600) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if "error" in data:
                        raise OllamaError(f"Pull failed: {data['error']}")

                    status = data.get("status", "")
                    digest = data.get("digest", "")
                    total = data.get("total", 0)
                    completed = data.get("completed", 0)

                    # Track layer index for display
                    if digest and digest not in layer_digests:
                        layer_digests[digest] = layer_counter[0]
                        layer_counter[0] += 1

                    progress = PullProgress(
                        status=status,
                        digest=digest,
                        total=total,
                        completed=completed,
                        layer_index=layer_digests.get(digest, 0),
                        layer_count=len(layer_digests),
                    )

                    if progress_callback:
                        progress_callback(progress)

                    yield progress

        except urllib.error.URLError as e:
            raise OllamaConnectionError(
                f"Cannot reach Ollama for pull: {e.reason}"
            ) from e

    # ---- Embeddings ----

    def embed(
        self,
        model: str,
        text: str,
    ) -> List[float]:
        """
        Generate an embedding vector for the given text.
        Used by the RAG system for semantic search.
        Returns a list of floats.
        """
        data = self._post("/api/embed", {"model": model, "input": text})
        # Ollama 0.1.26+ returns {"embeddings": [[...]]}
        embeddings = data.get("embeddings", [])
        if embeddings and isinstance(embeddings[0], list):
            return embeddings[0]
        # Older API: {"embedding": [...]}
        return data.get("embedding", [])

    # ---- Utility ----

    def load_model(self, model: str) -> bool:
        """
        Pre-load a model into GPU/RAM without generating anything.
        Sends a generation request with an empty prompt and keep_alive set.
        Returns True if successful.
        """
        try:
            self._post("/api/generate", {
                "model": model,
                "prompt": "",
                "keep_alive": "10m",
                "stream": False
            }, timeout=60)
            return True
        except OllamaError:
            return False

    def unload_model(self, model: str) -> bool:
        """Unload a model from GPU/RAM to free VRAM."""
        try:
            self._post("/api/generate", {
                "model": model,
                "prompt": "",
                "keep_alive": 0,
                "stream": False
            }, timeout=15)
            return True
        except OllamaError:
            return False

    def version(self) -> Optional[str]:
        """Returns the Ollama version string, or None if unreachable."""
        try:
            data = self._get("/api/version")
            return data.get("version")
        except Exception:
            return None
