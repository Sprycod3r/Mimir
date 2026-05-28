"""
path_resolver.py — Mimir Drive-Relative Path Resolution
All paths are derived from the executable's location at runtime.
Works whether running as a PyInstaller folder dist or a raw .py script.
"""

import os
import sys
from pathlib import Path


def get_launcher_dir() -> Path:
    """
    Returns the directory containing Mimir.exe (or main.py during development).
    This is Mimir/launcher/ on the drive.
    """
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller packaged exe
        return Path(sys.executable).parent
    else:
        # Running as script — src/ is one level below launcher/
        return Path(__file__).parent.parent


def get_mimir_root() -> Path:
    """
    Returns the root Mimir/ directory on the drive.
    launcher/ lives one level below this.
    """
    return get_launcher_dir().parent


class MimirPaths:
    """
    Central registry of all significant paths in the Mimir system.
    Instantiate once at startup; pass the instance wherever paths are needed.
    """

    def __init__(self):
        self._root = get_mimir_root()
        self._launcher = get_launcher_dir()

    # ---- Root ----
    @property
    def root(self) -> Path:
        return self._root

    # ---- Launcher internals ----
    @property
    def launcher(self) -> Path:
        return self._launcher

    @property
    def config(self) -> Path:
        return self._launcher / "config"

    @property
    def assets(self) -> Path:
        return self._launcher / "assets"

    @property
    def themes(self) -> Path:
        return self._launcher / "assets" / "themes"

    @property
    def mimir_json(self) -> Path:
        return self.config / "mimir.json"

    @property
    def ollama_models_json(self) -> Path:
        return self.config / "ollama-models.json"

    @property
    def system_prompt(self) -> Path:
        return self.config / "mimir-system-prompt.txt"

    # ---- AI Engine ----
    @property
    def ollama_exe(self) -> Path:
        return self._root / "tools" / "ollama" / "ollama.exe"

    @property
    def models_dir(self) -> Path:
        """Ollama model storage — set via OLLAMA_MODELS env var."""
        return self._root / "models"

    # ---- AnythingLLM ----
    @property
    def anythingllm_exe(self) -> Path:
        return Path(r"C:\Users\Trevor\AppData\Local\Programs\AnythingLLM\AnythingLLM.exe")

    @property
    def anythingllm_data(self) -> Path:
        """AnythingLLM data directory — set via STORAGE_DIR env var."""
        return self._root / "anythingllm"

    # ---- Knowledge Base ----
    @property
    def knowledge(self) -> Path:
        return self._root / "knowledge"

    # ---- Media ----
    @property
    def media(self) -> Path:
        return self._root / "media"

    @property
    def movies(self) -> Path:
        return self.media / "movies"

    @property
    def shows(self) -> Path:
        return self.media / "shows"

    @property
    def music(self) -> Path:
        return self.media / "music"

    @property
    def videos(self) -> Path:
        return self.media / "videos"

    # ---- Jellyfin ----
    @property
    def jellyfin_exe(self) -> Path:
        return self._root / "tools" / "jellyfin" / "jellyfin.exe"

    @property
    def jellyfin_data(self) -> Path:
        return self._root / "jellyfin"

    # ---- Emulation ----
    @property
    def retroarch_exe(self) -> Path:
        return self._root / "emulation" / "retroarch" / "retroarch.exe"

    @property
    def retroarch_dir(self) -> Path:
        """Root RetroArch directory — retroarch.exe lives here."""
        return self._root / "emulation" / "retroarch"

    @property
    def retroarch_config(self) -> Path:
        """Portable retroarch.cfg — same directory as retroarch.exe."""
        return self.retroarch_dir / "retroarch.cfg"

    @property
    def retroarch_cores(self) -> Path:
        return self.retroarch_dir / "cores"

    @property
    def retroarch_system(self) -> Path:
        """BIOS / system files directory."""
        return self.retroarch_dir / "system"

    @property
    def retroarch_saves(self) -> Path:
        return self.retroarch_dir / "saves"

    @property
    def retroarch_states(self) -> Path:
        return self.retroarch_dir / "states"

    @property
    def retroarch_screenshots(self) -> Path:
        return self.retroarch_dir / "screenshots"

    @property
    def retroarch_playlists(self) -> Path:
        return self.retroarch_dir / "playlists"

    @property
    def retroarch_thumbnails(self) -> Path:
        return self.retroarch_dir / "thumbnails"

    @property
    def retroarch_assets(self) -> Path:
        return self.retroarch_dir / "assets"

    @property
    def roms(self) -> Path:
        return self._root / "emulation" / "roms"

    # ---- yt-dlp / ffmpeg ----
    @property
    def ytdlp_exe(self) -> Path:
        return self._root / "tools" / "ytdlp" / "yt-dlp.exe"

    @property
    def ffmpeg_exe(self) -> Path:
        return self._root / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"

    # ---- Logs ----
    @property
    def logs(self) -> Path:
        return self._root / "logs"

    @property
    def conversation_logs(self) -> Path:
        return self._root / "logs" / "conversations"

    # ---- Vault ----
    @property
    def vault(self) -> Path:
        return self._root / "vault"

    def ensure_dirs(self):
        """Create any missing directories that should exist before launch."""
        dirs = [
            self.config,
            self.assets,
            self.themes,
            self.models_dir,
            self.anythingllm_data,
            self.knowledge,
            self.movies,
            self.shows,
            self.music,
            self.videos,
            self.jellyfin_data,
            # RetroArch subdirs — scaffold_retroarch_dirs() handles the full
            # set (including per-platform ROM dirs), but create the top-level
            # dirs here so the rest of the launcher can reference them safely.
            self.retroarch_dir,
            self.retroarch_cores,
            self.retroarch_system,
            self.retroarch_saves,
            self.retroarch_states,
            self.retroarch_screenshots,
            self.retroarch_playlists,
            self.retroarch_thumbnails,
            self.retroarch_assets,
            self.roms,
            self.conversation_logs,
            self.vault,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    def verify(self) -> dict:
        """
        Check which tools are present on the drive.
        Returns dict of {tool_name: bool}.
        """
        return {
            "ollama": self.ollama_exe.exists(),
            "anythingllm": self.anythingllm_exe.exists(),
            "jellyfin": self.jellyfin_exe.exists(),
            "retroarch": self.retroarch_exe.exists(),
            "ytdlp": self.ytdlp_exe.exists(),
            "ffmpeg": self.ffmpeg_exe.exists(),
        }

    def __repr__(self):
        return f"MimirPaths(root={self._root})"
