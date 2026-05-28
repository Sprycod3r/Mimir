"""
ytdlp_worker.py — Mimir yt-dlp Subprocess Worker

Runs yt-dlp.exe as a child process inside a QThread so the UI stays
responsive during downloads. Streams stdout line-by-line, parses progress,
and emits typed signals for the UI to consume.

Quality presets map to yt-dlp format selectors. "Audio only (MP3)" requires
ffmpeg — if ffmpeg.exe is not present in tools/ffmpeg/, it falls back to
downloading the best native audio format without conversion.

Signals:
  progress(int, str)           — (percent 0-100, status line e.g. "3.4MiB/s ETA 00:12")
  log_line(str)                — raw stdout line from yt-dlp (for the log window)
  download_complete(str, str)  — (display title, full output file path)
  download_failed(str)         — error message

Public API:
  YtdlpWorker(url, quality, output_dir, ytdlp_exe, ffmpeg_exe=None)
  cancel()  — terminates the subprocess; worker will emit download_failed("Cancelled")
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal


# ---- Quality presets ----------------------------------------------------

# Maps display label → yt-dlp CLI arguments (list of strings)
QUALITY_PRESETS = {
    "Best available": [
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
    ],
    "1080p": [
        "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "--merge-output-format", "mp4",
    ],
    "720p": [
        "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "--merge-output-format", "mp4",
    ],
    "480p": [
        "-f", "bestvideo[height<=480]+bestaudio/best[height<=480]",
        "--merge-output-format", "mp4",
    ],
    # Audio-only: use -x to extract audio. MP3 conversion requires ffmpeg.
    # Falls back to best native audio (webm/m4a) if ffmpeg is absent.
    "Audio only (MP3)": [
        "-f", "bestaudio/best",
        "-x",
        "--audio-format", "mp3",
        "--audio-quality", "0",
    ],
}

QUALITY_LABELS = list(QUALITY_PRESETS.keys())

# ---- Stdout parsers -----------------------------------------------------

# [download]  64.3% of  124.31MiB at    3.45MiB/s ETA 00:09
_PROGRESS_RE = re.compile(
    r'\[download\]\s+(\d+(?:\.\d+)?)%\s+of\s+([\S]+)\s+at\s+([\S]+)\s+ETA\s+([\S]+)'
)

# [download] 100% of  124.31MiB in 00:35
_COMPLETE_RE = re.compile(
    r'\[download\]\s+100%\s+of\s+'
)

# [download] Destination: /path/to/file.mp4
_DEST_RE = re.compile(r'\[download\] Destination:\s+(.+)')

# [Merger] Merging formats into "filename.mp4"
_MERGER_RE = re.compile(r'\[Merger\] Merging formats into "(.+)"')

# [ExtractAudio] Destination: filename.mp3
_AUDIO_RE = re.compile(r'\[ExtractAudio\] Destination:\s+(.+)')

# Generic "already downloaded" line
_ALREADY_RE = re.compile(r'\[download\] .+ has already been downloaded')

# Error lines
_ERROR_RE = re.compile(r'ERROR:\s+(.+)')


class YtdlpWorker(QThread):
    """
    Downloads a single URL via yt-dlp in a background thread.
    Create a new instance per download — don't reuse.
    """

    progress = pyqtSignal(int, str)           # (percent, status_text)
    log_line = pyqtSignal(str)                # raw stdout line
    download_complete = pyqtSignal(str, str)  # (display_title, file_path)
    download_failed = pyqtSignal(str)         # error_message

    def __init__(
        self,
        url: str,
        quality: str,
        output_dir: Path,
        ytdlp_exe: Path,
        ffmpeg_exe: Optional[Path] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._url = url.strip()
        self._quality = quality
        self._output_dir = output_dir
        self._ytdlp_exe = ytdlp_exe
        self._ffmpeg_exe = ffmpeg_exe
        self._proc: Optional[subprocess.Popen] = None
        self._cancelled = False
        self._output_file: Optional[str] = None

    # ----------------------------------------------------------------- run

    def run(self):
        if not self._ytdlp_exe.exists():
            self.download_failed.emit(
                f"yt-dlp.exe not found at {self._ytdlp_exe}"
            )
            return

        # Build command
        cmd = self._build_command()
        if cmd is None:
            self.download_failed.emit("Unknown quality preset.")
            return

        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self.download_failed.emit(f"Cannot create output directory: {e}")
            return

        # Run yt-dlp
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception as e:
            self.download_failed.emit(f"Failed to start yt-dlp: {e}")
            return

        # Stream output
        last_error = ""
        try:
            for line in self._proc.stdout:
                if self._cancelled:
                    break
                line = line.rstrip("\n\r")
                if not line:
                    continue
                self.log_line.emit(line)
                self._parse_line(line)
                # Capture last error for failure message
                m = _ERROR_RE.search(line)
                if m:
                    last_error = m.group(1)
        except Exception:
            pass

        # Wait for process to finish
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()

        if self._cancelled:
            self.download_failed.emit("Download cancelled.")
            return

        rc = self._proc.returncode
        if rc == 0:
            # Final 100% signal
            self.progress.emit(100, "Complete")
            title = self._derive_title()
            file_path = self._output_file or ""
            self.download_complete.emit(title, file_path)
        else:
            msg = last_error or f"yt-dlp exited with code {rc}"
            self.download_failed.emit(msg)

    # ----------------------------------------------------------------- cancel

    def cancel(self):
        self._cancelled = True
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass

    # ----------------------------------------------------------------- helpers

    def _build_command(self) -> Optional[list]:
        preset_args = QUALITY_PRESETS.get(self._quality)
        if preset_args is None:
            return None

        cmd = [str(self._ytdlp_exe)]

        # Inject ffmpeg location if available and quality requires it
        if self._ffmpeg_exe and self._ffmpeg_exe.exists():
            cmd += ["--ffmpeg-location", str(self._ffmpeg_exe.parent)]
        elif self._quality == "Audio only (MP3)":
            # No ffmpeg — download best native audio, skip MP3 conversion
            preset_args = ["-f", "bestaudio/best"]

        cmd += preset_args

        # Output template: save to output_dir with sanitized title
        output_template = str(self._output_dir / "%(title)s.%(ext)s")
        cmd += [
            "-o", output_template,
            "--merge-output-format", "mp4",
            "--no-playlist",       # Single video, not playlist
            "--no-warnings",       # Keep stderr clean
            "--progress",          # Ensure progress lines are emitted
            "--newline",           # One progress line per stdout line
            self._url,
        ]
        return cmd

    def _parse_line(self, line: str):
        """Parse a single stdout line and emit signals as appropriate."""
        # Progress update
        m = _PROGRESS_RE.search(line)
        if m:
            try:
                percent = int(float(m.group(1)))
                size = m.group(2)
                speed = m.group(3)
                eta = m.group(4)
                status = f"{size} at {speed}  ETA {eta}"
                self.progress.emit(percent, status)
            except ValueError:
                pass
            return

        # Destination file (before merge)
        m = _DEST_RE.search(line)
        if m:
            self._output_file = m.group(1).strip()
            return

        # Merger output (final merged file path)
        m = _MERGER_RE.search(line)
        if m:
            path = m.group(1).strip()
            # Merger wraps the path in quotes already stripped by the regex
            self._output_file = path
            return

        # ExtractAudio destination (MP3)
        m = _AUDIO_RE.search(line)
        if m:
            self._output_file = m.group(1).strip()
            return

        # Already downloaded
        if _ALREADY_RE.search(line):
            self.progress.emit(100, "Already downloaded")
            return

    def _derive_title(self) -> str:
        """Get a display title from the output filename, or fall back to URL."""
        if self._output_file:
            return Path(self._output_file).stem
        # Strip URL to a readable form
        url = self._url
        for prefix in ("https://", "http://", "www."):
            url = url.removeprefix(prefix)
        return url[:80]
