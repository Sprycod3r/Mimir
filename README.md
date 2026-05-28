# Mimir

A portable, self-contained AI assistant and media system designed to run entirely from an external drive — no cloud dependency, no installation required on the host machine.

## What It Does

Mimir integrates several open-source tools into a single launcher with a unified PyQt6 interface:

- **Local LLM chat** — runs Ollama models (Mistral, LLaMA, Gemma) directly on your hardware, offline
- **Knowledge base** — indexes local documents via AnythingLLM and answers questions using RAG (Retrieval-Augmented Generation)
- **Media server** — embeds Jellyfin for local movie, TV, and music playback
- **Emulation** — launches RetroArch with a ROM browser organized by platform
- **Downloader** — yt-dlp integration for saving video and audio from the web
- **Conversation logging** — every chat session is saved locally as JSON

## Architecture

```
Mimir/
├── launcher/          # PyQt6 desktop application (entry point: src/main.py)
│   ├── src/           # Application source code
│   │   ├── main.py
│   │   ├── hardware_detect.py
│   │   ├── service_manager.py
│   │   ├── theme_manager.py
│   │   └── ui/        # All UI panels and widgets
│   ├── config/        # User settings, model definitions, system prompt
│   └── assets/        # Themes (JSON-based color/font definitions)
├── knowledge/         # Document store for RAG indexing
├── tools/             # External binaries (Ollama, AnythingLLM, Jellyfin, yt-dlp, ffmpeg)
├── models/            # Ollama model storage
├── emulation/         # RetroArch and ROM library
└── media/             # Local media library
```

## Key Technical Details

- Built with **Python 3.11** and **PyQt6**
- Background service health monitoring via `QThread` pollers — non-blocking UI
- Hardware detection (GPU, VRAM, RAM) to recommend appropriate model tier
- Drive-relative path resolution — works from any drive letter
- Theme system via JSON config files — hot-swappable without rebuilding
- Lazy loading of `QtWebEngineWidgets` to defer Chromium initialization

## Running from Source

```bash
cd launcher
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python src\main.py
```

## Building the Executable

```bash
cd launcher
build.bat
```

Output lands in `dist\Mimir\`. See `README-BUILD.md` for full deployment instructions.

## Tools Required (not included in repo)

The following binaries are excluded from this repository due to file size. Download and place them in the indicated directories:

| Tool | Directory | Source |
|------|-----------|--------|
| Ollama | `tools/ollama/` | https://ollama.com/download |
| AnythingLLM Desktop | `tools/anythingllm/` | https://useanything.com/ |
| Jellyfin | `tools/jellyfin/` | https://jellyfin.org/downloads/ |
| yt-dlp | `tools/ytdlp/` | https://github.com/yt-dlp/yt-dlp/releases |
| ffmpeg | `tools/ffmpeg/` | https://ffmpeg.org/download.html |
| RetroArch | `emulation/retroarch/` | https://www.retroarch.com/ |

Run `Mimir-Setup.ps1` after placing tools to verify your installation.

## Development Note

Mimir was built using AI-assisted development with Claude (Anthropic). Architecture decisions, feature design, requirements, and project direction are my own. The project represents applied learning in Python, PyQt6, service orchestration, and systems design.
