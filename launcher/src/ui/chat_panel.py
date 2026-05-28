"""
chat_panel.py — Mimir Chat Panel

Full chat interface. Two modes:
  - Ask Mimir  → RAG query via AnythingLLM REST API
  - Talk to Mimir → Direct streaming chat via Ollama

Layout:
  [Mode toggle bar]
  [Message scroll area]
  [Context injection banner] (shown when a document is injected)
  [Input bar: textarea + Send button]

Streaming:
  OllamaStreamWorker runs stream_chat() in a QThread.
  Emits token(str) for each token; finished() when done.

Conversation logging:
  Each session starts a JSON log at logs/conversations/YYYY-MM-DD_HHMMSS.json.
  Messages are appended on every send/receive.

Public API:
  inject_context(text, title)   — injects document text as system context
  clear_context()               — removes injected context
  set_mode(mode)                — "ask" or "talk"
  is_streaming → bool
"""

import json
import datetime
from pathlib import Path
from typing import List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QTextEdit, QFrame, QSizePolicy, QSpacerItem
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QFont, QKeyEvent

from ui.chat_message import ChatMessage


# ============================================================
# Streaming Worker — Ollama
# ============================================================

class OllamaStreamWorker(QThread):
    """
    Runs ollama_client.stream_chat() in a background thread.
    Emits token(str) for each streamed token, finished() when done,
    error(str) on failure.
    """
    token = pyqtSignal(str)
    finished = pyqtSignal(str)   # full accumulated response
    error = pyqtSignal(str)

    def __init__(self, client, model_name: str, messages: list,
                 system_prompt: str = "", context_window: int = 8192, parent=None):
        super().__init__(parent)
        self._client = client
        self._model = model_name
        self._messages = messages
        self._system_prompt = system_prompt
        self._context_window = context_window
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        full_response = ""
        try:
            for tok in self._client.stream_chat(
                model=self._model,
                messages=self._messages,
                system_prompt=self._system_prompt,
                context_window=self._context_window,
            ):
                if self._cancelled:
                    break
                full_response += tok
                self.token.emit(tok)
        except Exception as e:
            self.error.emit(str(e))
            return
        self.finished.emit(full_response)


# ============================================================
# Mode Toggle Bar
# ============================================================

class _ModeToggle(QWidget):
    """
    Two-button toggle: Ask Mimir | Talk to Mimir
    """
    mode_changed = pyqtSignal(str)  # "ask" or "talk"

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._ask_btn = QPushButton("Ask Mimir")
        self._ask_btn.setObjectName("mode-toggle-btn")
        self._ask_btn.setProperty("active", True)
        self._ask_btn.setCheckable(False)
        self._ask_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ask_btn.setFixedHeight(32)
        self._ask_btn.clicked.connect(lambda: self._set("ask"))

        self._talk_btn = QPushButton("Talk to Mimir")
        self._talk_btn.setObjectName("mode-toggle-btn")
        self._talk_btn.setProperty("active", False)
        self._talk_btn.setCheckable(False)
        self._talk_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._talk_btn.setFixedHeight(32)
        self._talk_btn.clicked.connect(lambda: self._set("talk"))

        layout.addStretch()
        layout.addWidget(self._ask_btn)
        layout.addWidget(self._talk_btn)
        layout.addStretch()

        self._mode = "ask"

    def _set(self, mode: str):
        self._mode = mode
        self._ask_btn.setProperty("active", mode == "ask")
        self._talk_btn.setProperty("active", mode == "talk")
        for btn in (self._ask_btn, self._talk_btn):
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.mode_changed.emit(mode)

    @property
    def mode(self) -> str:
        return self._mode


# ============================================================
# Context Injection Banner
# ============================================================

class _ContextBanner(QFrame):
    """Shown when a document is injected into chat context."""
    cleared = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("context-banner")
        self.setVisible(False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        self._label = QLabel()
        self._label.setObjectName("context-banner-label")
        self._label.setWordWrap(False)

        clear_btn = QPushButton("✕ Clear")
        clear_btn.setObjectName("context-banner-clear")
        clear_btn.setFlat(True)
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.clicked.connect(self._on_clear)

        layout.addWidget(self._label)
        layout.addStretch()
        layout.addWidget(clear_btn)

    def set_context(self, title: str):
        self._label.setText(f"📄 Context: {title}")
        self.setVisible(True)

    def _on_clear(self):
        self.setVisible(False)
        self.cleared.emit()


# ============================================================
# Chat Input Bar
# ============================================================

class _ChatInput(QWidget):
    """
    Multi-line text input with Send button.
    Enter sends; Shift+Enter inserts newline.
    """
    submitted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("chat-input-inner")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._editor = _SubmitOnEnterTextEdit()
        self._editor.setObjectName("chat-input-editor")
        self._editor.setPlaceholderText("Message Mimir…  (Shift+Enter for new line)")
        self._editor.setFixedHeight(72)
        self._editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._editor.submitted.connect(self._on_submit)

        self._send_btn = QPushButton("Send")
        self._send_btn.setObjectName("chat-send-btn")
        self._send_btn.setFixedSize(72, 72)
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.clicked.connect(self._on_submit)

        layout.addWidget(self._editor)
        layout.addWidget(self._send_btn)

    def _on_submit(self):
        text = self._editor.toPlainText().strip()
        if text:
            self._editor.clear()
            self.submitted.emit(text)

    def set_enabled(self, enabled: bool):
        self._editor.setEnabled(enabled)
        self._send_btn.setEnabled(enabled)
        self._send_btn.setText("Stop" if not enabled else "Send")

    def set_placeholder(self, text: str):
        self._editor.setPlaceholderText(text)


class _SubmitOnEnterTextEdit(QTextEdit):
    """QTextEdit that emits submitted() on Enter (not Shift+Enter)."""
    submitted = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)  # newline
            else:
                self.submitted.emit()
        else:
            super().keyPressEvent(event)


# ============================================================
# Message Scroll Area
# ============================================================

class _MessageList(QScrollArea):
    """
    Scrollable container for ChatMessage widgets.
    New messages are added at the bottom; scroll auto-follows.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setObjectName("message-list")

        self._container = QWidget()
        self._container.setObjectName("message-list-container")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(16, 16, 16, 8)
        self._layout.setSpacing(8)
        self._layout.addStretch()  # pushes messages to bottom initially

        self.setWidget(self._container)

    def add_message(self, message: ChatMessage):
        # Insert before the trailing stretch
        count = self._layout.count()
        self._layout.insertWidget(count - 1, message)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())


# ============================================================
# Main Chat Panel
# ============================================================

class ChatPanel(QWidget):
    """
    Full chat interface widget.

    Pass ollama_client, anythingllm_client, model_data, paths, and system_prompt
    at construction.

    shared_ask_history:  shared list for Ask Mimir (AnythingLLM RAG) messages.
                         Also used by the chat bubble (which is always in ask mode).
    shared_talk_history: shared list for Talk to Mimir (direct Ollama) messages.
                         Kept separate so RAG context and direct-chat context don't bleed.
    """

    def __init__(self, ollama_client, anythingllm_client,
                 model_data: dict, paths, system_prompt: str = "",
                 compact: bool = False,
                 shared_ask_history: Optional[List[dict]] = None,
                 shared_talk_history: Optional[List[dict]] = None,
                 vault_key_ref: list = None,
                 encrypt_logs: bool = False,
                 parent=None):
        super().__init__(parent)
        self._ollama = ollama_client
        self._atllm = anythingllm_client
        self._model_data = model_data
        self._paths = paths
        self._system_prompt = system_prompt
        self._compact = compact  # True for chat bubble popup
        # [Optional[bytes]] — mutable container; key is set when vault is unlocked.
        self._vault_key_ref = vault_key_ref
        self._encrypt_logs = encrypt_logs

        self._mode = "ask"
        self._ask_messages: List[dict] = shared_ask_history if shared_ask_history is not None else []
        self._talk_messages: List[dict] = shared_talk_history if shared_talk_history is not None else []
        self._pending_mode: str = "ask"  # which history to update in _finish_response
        print(f"[CHAT PANEL] init compact={compact} ask_messages id={id(self._ask_messages)} talk_messages id={id(self._talk_messages)}")
        self._log_messages: List[dict] = []      # {role, content, timestamp} for file
        self._injected_context: Optional[str] = None
        self._injected_title: Optional[str] = None
        self._current_stream_worker: Optional[OllamaStreamWorker] = None
        self._current_assistant_bubble: Optional[ChatMessage] = None
        self._is_streaming = False

        # Start session log file
        self._log_path = self._init_log_file()

        self._setup_ui()

    # ----------------------------------------------------------- setup

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Mode toggle (skip in compact bubble mode)
        if not self._compact:
            self._mode_toggle = _ModeToggle()
            self._mode_toggle.mode_changed.connect(self._on_mode_changed)
            toggle_wrap = QWidget()
            toggle_wrap.setObjectName("mode-toggle-bar")
            tw_layout = QHBoxLayout(toggle_wrap)
            tw_layout.setContentsMargins(16, 10, 16, 10)
            tw_layout.addWidget(self._mode_toggle)
            layout.addWidget(toggle_wrap)
            layout.addWidget(self._h_separator())
        else:
            self._mode_toggle = None

        # Message list
        self._message_list = _MessageList()
        layout.addWidget(self._message_list, stretch=1)

        # Context banner
        self._context_banner = _ContextBanner()
        self._context_banner.cleared.connect(self.clear_context)
        layout.addWidget(self._context_banner)

        # Input bar
        input_wrap = QWidget()
        input_wrap.setObjectName("chat-input-bar")
        iw_layout = QHBoxLayout(input_wrap)
        iw_layout.setContentsMargins(12, 8, 12, 12)
        self._input = _ChatInput()
        self._input.submitted.connect(self._on_user_submit)
        iw_layout.addWidget(self._input)
        layout.addWidget(input_wrap)

        # Welcome message
        self._add_system_message(
            "Session started. Ask me anything, or switch to Talk mode for an open conversation."
        )

    def _h_separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("chat-separator")
        return line

    # ----------------------------------------------------------- mode

    def _on_mode_changed(self, mode: str):
        self._mode = mode
        if mode == "ask":
            self._input.set_placeholder("Ask the knowledge base…  (Shift+Enter for new line)")
        else:
            self._input.set_placeholder("Talk to Mimir…  (Shift+Enter for new line)")

    def set_mode(self, mode: str):
        self._mode = mode
        if self._mode_toggle:
            self._mode_toggle._set(mode)

    # ----------------------------------------------------------- send/receive

    def _on_user_submit(self, text: str):
        if self._is_streaming:
            self._cancel_stream()
            return

        # Add user bubble
        user_msg = ChatMessage("user", text)
        self._message_list.add_message(user_msg)

        # Build message log entry
        self._log_messages.append(user_msg.to_log_dict())
        self._append_to_log(user_msg.to_log_dict())

        # Route: talk mode (or no atllm) → Ollama; ask mode with atllm → AnythingLLM RAG.
        will_use_ollama = (self._mode == "talk" or not self._atllm)
        self._pending_mode = "talk" if will_use_ollama else "ask"

        # Append user message to the appropriate history.
        active = self._talk_messages if will_use_ollama else self._ask_messages
        print(f"[HISTORY] send mode={self._mode!r} pending={self._pending_mode!r} "
              f"writing user msg to {'talk' if will_use_ollama else 'ask'}_messages id={id(active)}")
        active.append({"role": "user", "content": text})

        # Disable input while streaming
        self._input.set_enabled(False)
        self._is_streaming = True

        if will_use_ollama:
            self._send_to_ollama()
        else:
            self._send_to_atllm(text)

    def _send_to_atllm(self, query: str):
        """
        Send to AnythingLLM RAG endpoint.
        Times out after 30 seconds and falls back to Ollama automatically.
        Empty responses also trigger the fallback.
        """
        from PyQt6.QtCore import QTimer

        atllm = self._atllm
        self._atllm_fell_back = False

        class _ATLLMWorker(QThread):
            reply = pyqtSignal(str)
            error = pyqtSignal(str)

            def run(self_inner):
                try:
                    from anythingllm_client import AnythingLLMClient
                    result = atllm.query(
                        AnythingLLMClient.WORKSPACE_SLUG, query, mode="query"
                    )
                    answer = result.answer if result else ""
                    print(f"[ATLLM WORKER] answer len={len(answer)} preview={answer[:120]!r}")
                    self_inner.reply.emit(answer)
                except Exception as e:
                    print(f"[ATLLM WORKER] exception: {e}")
                    self_inner.error.emit(str(e))

        worker = _ATLLMWorker()
        self._atllm_worker = worker

        def _do_fallback(reason: str):
            if self._atllm_fell_back:
                return
            self._atllm_fell_back = True
            try:
                worker.reply.disconnect()
                worker.error.disconnect()
            except Exception:
                pass
            print(f"[ASK FALLBACK] {reason} — falling back to Ollama with ask_messages id={id(self._ask_messages)}")
            self._add_system_message(f"AnythingLLM {reason} — answering directly from model…")
            self._send_to_ollama(messages=list(self._ask_messages))

        def _on_timeout():
            _do_fallback("timed out after 30s")

        self._atllm_timeout_timer = QTimer(self)
        self._atllm_timeout_timer.setSingleShot(True)
        self._atllm_timeout_timer.timeout.connect(_on_timeout)
        self._atllm_timeout_timer.start(30_000)

        def _on_reply(text: str):
            if self._atllm_fell_back:
                return
            self._atllm_timeout_timer.stop()
            if not text.strip():
                _do_fallback("returned empty response")
                return
            self._on_atllm_reply(text)

        def _on_error(error_msg: str):
            if self._atllm_fell_back:
                return
            self._atllm_timeout_timer.stop()
            _do_fallback(f"error ({error_msg})")

        worker.reply.connect(_on_reply)
        worker.error.connect(_on_error)
        worker.start()

        # Show streaming indicator
        bubble = ChatMessage("assistant")
        bubble.start_streaming()
        self._message_list.add_message(bubble)
        self._current_assistant_bubble = bubble

    def _on_atllm_reply(self, text: str):
        print(f"[ATLLM REPLY SLOT] received text len={len(text)} bubble={self._current_assistant_bubble is not None}")
        if self._current_assistant_bubble:
            self._current_assistant_bubble.set_content(text)
            self._current_assistant_bubble.finish_streaming()
        self._finish_response(text)

    def _send_to_ollama(self, messages: list = None):
        """
        Send to Ollama via streaming chat.

        messages: history to send. Defaults to self._talk_messages (normal talk flow).
                  Pass self._ask_messages when falling back from a failed ATLLM request.
        """
        ollama_model = self._model_data.get("ollama_model", "mistral:7b")
        ctx_window = self._model_data.get("context_window", 8192)

        if messages is None:
            messages = list(self._talk_messages)

        print(f"[OLLAMA SEND] pending_mode={self._pending_mode!r} messages_len={len(messages)}")

        # Build effective system prompt (base + injected context if any)
        effective_prompt = self._system_prompt
        if self._injected_context:
            effective_prompt += (
                f"\n\nThe user is currently reading: {self._injected_title}\n"
                f"Content:\n{self._injected_context[:8000]}"
            )

        # Reuse the existing bubble when called as an ATLLM fallback;
        # create a new one for normal talk-mode sends.
        if not self._current_assistant_bubble:
            bubble = ChatMessage("assistant")
            bubble.start_streaming()
            self._message_list.add_message(bubble)
            self._current_assistant_bubble = bubble

        worker = OllamaStreamWorker(
            client=self._ollama,
            model_name=ollama_model,
            messages=messages,
            system_prompt=effective_prompt,
            context_window=ctx_window,
        )
        worker.token.connect(self._on_stream_token)
        worker.finished.connect(self._on_stream_finished)
        worker.error.connect(self._on_stream_error)
        worker.start()
        self._current_stream_worker = worker

    def _on_stream_token(self, token: str):
        if self._current_assistant_bubble:
            self._current_assistant_bubble.append_token(token)

    def _on_stream_finished(self, full_response: str):
        if self._current_assistant_bubble:
            if not self._current_assistant_bubble.content and full_response:
                self._current_assistant_bubble.set_content(full_response)
            self._current_assistant_bubble.finish_streaming()
        self._finish_response(full_response)

    def _on_stream_error(self, error_msg: str):
        if self._current_assistant_bubble:
            self._current_assistant_bubble.set_content(
                f"[Error communicating with Mimir: {error_msg}]"
            )
            self._current_assistant_bubble.finish_streaming()
        self._finish_response("")
        self._add_system_message(f"Connection error: {error_msg}")

    def _finish_response(self, response: str):
        self._is_streaming = False
        self._input.set_enabled(True)
        self._current_stream_worker = None
        self._current_assistant_bubble = None

        if response:
            active = self._talk_messages if self._pending_mode == "talk" else self._ask_messages
            print(f"[HISTORY] finish pending_mode={self._pending_mode!r} "
                  f"writing assistant reply to {'talk' if self._pending_mode == 'talk' else 'ask'}_messages id={id(active)}")
            active.append({"role": "assistant", "content": response})
            entry = {
                "role": "assistant",
                "content": response,
                "timestamp": datetime.datetime.now().isoformat(),
            }
            self._log_messages.append(entry)
            self._append_to_log(entry)

    def _cancel_stream(self):
        if self._current_stream_worker:
            self._current_stream_worker.cancel()
        self._is_streaming = False
        self._input.set_enabled(True)

    # ----------------------------------------------------------- context injection

    def inject_context(self, text: str, title: str):
        """
        Inject document text as system-level context.
        Shows the context banner. Context is appended to system prompt
        on next Ollama send.
        """
        self._injected_context = text
        self._injected_title = title
        self._context_banner.set_context(title)
        self._add_system_message(f"📄 Context loaded: {title}")

    def clear_context(self):
        self._injected_context = None
        self._injected_title = None
        self._context_banner.setVisible(False)

    # ----------------------------------------------------------- system messages

    def _add_system_message(self, text: str):
        msg = ChatMessage("system", text)
        self._message_list.add_message(msg)

    # ----------------------------------------------------------- conversation log

    def _init_log_file(self) -> Optional[Path]:
        """Create the session log file. Returns path or None on failure."""
        try:
            if not self._paths:
                return None
            log_dir = self._paths.conversation_logs
            log_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
            path = log_dir / f"{ts}.json"
            path.write_text("[]", encoding="utf-8")
            return path
        except Exception:
            return None

    def _append_to_log(self, entry: dict):
        """
        Append a single message entry to the JSON log file.
        If encrypt_logs is enabled and vault key is available, the file is
        written as AES-256-GCM ciphertext; otherwise plain JSON.
        """
        if not self._log_path:
            return
        try:
            vault_key = self._vault_key_ref[0] if self._vault_key_ref else None
            raw = self._log_path.read_text(encoding="utf-8")

            # If the file is currently encrypted, decrypt before appending
            if vault_key is not None:
                from security import is_encrypted_log, decrypt_log
                if is_encrypted_log(raw):
                    try:
                        raw = decrypt_log(raw, vault_key)
                    except ValueError:
                        raw = "[]"  # Unrecoverable — start fresh for this session

            existing = json.loads(raw)
            existing.append(entry)
            content = json.dumps(existing, indent=2, ensure_ascii=False)

            # Encrypt the whole file if key is available and encryption is enabled
            if self._encrypt_logs and vault_key is not None:
                from security import encrypt_log
                content = encrypt_log(content, vault_key)

            self._log_path.write_text(content, encoding="utf-8")
        except Exception:
            pass

    # ----------------------------------------------------------- public

    @property
    def is_streaming(self) -> bool:
        return self._is_streaming

    def get_log_path(self) -> Optional[Path]:
        return self._log_path
