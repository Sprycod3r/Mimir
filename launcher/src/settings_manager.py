"""
settings_manager.py — Mimir User Settings
Reads and writes mimir.json. Provides defaults if the file doesn't exist.
"""

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS = {
    "theme": "mimir-dark",
    "selected_model": None,          # None = show model selector on next launch
    "skip_intro": False,
    "last_model_override": False,    # True if user manually overrode the recommendation
    "window": {
        "width": 1280,
        "height": 800,
        "maximized": False
    },
    "services": {
        "start_jellyfin_on_launch": True,
        "start_anythingllm_on_launch": True,
        "ollama_port": 11434,
        "anythingllm_port": 3001,
        "jellyfin_port": 8096
    },
    "chat": {
        "default_mode": "ask",       # "ask" (RAG) or "talk" (open chat)
        "bubble_position": "bottom-right"
    },
    "downloader": {
        "default_quality": "best",
        "output_subfolder": ""       # Relative to media/videos/ — blank = root
    },
    "security": {
        "launcher_pin_enabled": False,
        "launcher_pin_hash": None,         # bcrypt hash str or None
        "vault_pin_enabled": False,
        "vault_uses_launcher_pin": False,  # True → vault PIN = launcher PIN
        "vault_pin_hash": None,            # bcrypt hash str or None (ignored if vault_uses_launcher_pin)
        "encrypt_logs": False,             # True → encrypt conversation log JSON at rest
        "log_key_salt": None,              # Base64-encoded 16-byte PBKDF2 salt
    }
}


class SettingsManager:
    def __init__(self, settings_path: Path):
        self._path = settings_path
        self._data = {}
        self.load()

    def load(self):
        """Load settings from disk. Falls back to defaults for any missing keys."""
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                # Deep merge: loaded values override defaults, but missing keys get defaults
                self._data = _deep_merge(DEFAULT_SETTINGS, loaded)
            except (json.JSONDecodeError, IOError):
                # Corrupt or unreadable — start with defaults and note the issue
                self._data = dict(DEFAULT_SETTINGS)
        else:
            self._data = dict(DEFAULT_SETTINGS)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self.save()

    def save(self):
        """Write current settings to disk."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except IOError as e:
            # Non-fatal — settings just won't persist
            print(f"[Settings] Could not save settings: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a top-level setting value."""
        return self._data.get(key, default)

    def set(self, key: str, value: Any):
        """Set a top-level setting value and save."""
        self._data[key] = value
        self.save()

    def get_nested(self, *keys, default: Any = None) -> Any:
        """Get a nested setting value. E.g. get_nested('services', 'ollama_port')."""
        d = self._data
        for key in keys:
            if not isinstance(d, dict):
                return default
            d = d.get(key, default)
        return d

    def set_nested(self, *keys, value: Any):
        """Set a nested setting value and save. E.g. set_nested('services', 'ollama_port', value=11435)."""
        d = self._data
        for key in keys[:-1]:
            d = d.setdefault(key, {})
        d[keys[-1]] = value
        self.save()

    @property
    def theme(self) -> str:
        return self._data.get("theme", "mimir-dark")

    @theme.setter
    def theme(self, value: str):
        self._data["theme"] = value
        self.save()

    @property
    def selected_model(self):
        return self._data.get("selected_model")

    @selected_model.setter
    def selected_model(self, value):
        self._data["selected_model"] = value
        self.save()

    @property
    def skip_intro(self) -> bool:
        return self._data.get("skip_intro", False)

    @skip_intro.setter
    def skip_intro(self, value: bool):
        self._data["skip_intro"] = value
        self.save()

    @property
    def ollama_port(self) -> int:
        return self.get_nested("services", "ollama_port", default=11434)

    @property
    def anythingllm_port(self) -> int:
        return self.get_nested("services", "anythingllm_port", default=3001)

    @property
    def jellyfin_port(self) -> int:
        return self.get_nested("services", "jellyfin_port", default=8096)

    # ── Security shortcuts ────────────────────────────────────────────────────

    @property
    def launcher_pin_enabled(self) -> bool:
        return bool(self.get_nested("security", "launcher_pin_enabled", default=False))

    @property
    def launcher_pin_hash(self):
        return self.get_nested("security", "launcher_pin_hash", default=None)

    @property
    def vault_pin_enabled(self) -> bool:
        return bool(self.get_nested("security", "vault_pin_enabled", default=False))

    @property
    def vault_uses_launcher_pin(self) -> bool:
        return bool(self.get_nested("security", "vault_uses_launcher_pin", default=False))

    @property
    def vault_pin_hash(self):
        return self.get_nested("security", "vault_pin_hash", default=None)

    @property
    def encrypt_logs(self) -> bool:
        return bool(self.get_nested("security", "encrypt_logs", default=False))

    @property
    def log_key_salt(self):
        return self.get_nested("security", "log_key_salt", default=None)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. Returns a new dict."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
