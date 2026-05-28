# Mimir Launcher — Build & Deploy Guide

## What's in this folder

```
launcher/
├── src/                     ← Python source code
│   ├── main.py              ← Entry point
│   ├── hardware_detect.py   ← GPU/RAM/CPU detection
│   ├── path_resolver.py     ← Drive-relative path logic
│   ├── settings_manager.py  ← mimir.json read/write
│   ├── theme_manager.py     ← Theme loading + QSS generation
│   ├── service_manager.py   ← Ollama / AnythingLLM / Jellyfin process management
│   └── ui/
│       ├── model_card.py    ← Individual model card widget
│       └── model_selector.py ← Model selection screen
├── config/
│   ├── mimir.json           ← User settings (auto-created with defaults if missing)
│   ├── ollama-models.json   ← Model tier definitions
│   └── mimir-system-prompt.txt ← Mimir's personality/system prompt
├── assets/
│   └── themes/
│       ├── mimir-dark.json  ← Default theme (purple/green)
│       ├── cold-steel.json  ← Blue/teal theme
│       └── ember.json       ← Amber/warm theme
├── requirements.txt
├── Mimir.spec               ← PyInstaller build config
└── build.bat                ← One-click build script
```

## Prerequisites

- Python 3.11 or newer
- Windows 10/11
- Internet access during build (to download PyInstaller and PyQt6 — only needed once)

## Build steps

```bat
cd launcher
build.bat
```

That's it. The script creates a venv, installs dependencies, and runs PyInstaller.
Output lands in `dist\Mimir\`.

## Deploy to the drive

After building:

1. Copy the entire `dist\Mimir\` folder to `{drive}\Mimir\launcher\`
2. The final path should be: `{drive}\Mimir\launcher\Mimir.exe`
3. The `_internal\` folder next to the exe contains bundled Python and PyQt6 — don't delete it

The `config\` and `assets\` folders in the launcher root are the live user-facing ones. They take precedence over what's bundled inside `_internal\`.

## Running from source (development)

Install dependencies into a venv:
```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Then run:
```bat
python src\main.py
```

Path resolution works the same whether running from source or as a packaged exe.

## What Phase 1 does

On launch, Mimir:
1. Detects your GPU, VRAM, and RAM
2. Recommends the appropriate model tier (Heavy / Medium / Lite)
3. Shows the model selection screen with all three options
4. On selection: starts Ollama, AnythingLLM, and Jellyfin as background processes
5. Shows a status screen confirming services are running

Phase 5 builds the full interface on top of this foundation.

## Customizing Mimir's personality

Edit `config\mimir-system-prompt.txt`. Changes take effect on next launch.
The system prompt is loaded fresh at startup — no rebuild needed.

## Adding a custom theme

Create a new JSON file in `assets\themes\` following the same structure as `mimir-dark.json`.
Set `"id"` to a unique string and `"display_name"` to what you want shown in Settings.
Mimir picks it up automatically on next launch.

## Known limitations (Phase 1)

- The main interface after service start is a placeholder. Full UI builds in Phase 5.
- AnythingLLM and Jellyfin won't do anything useful until their tools are placed in the
  `tools\` directory on the drive and configured. See setup documentation.
- If a selected model isn't downloaded yet, Ollama will start but the model won't be available
  until you run `ollama pull [model-name]` from a terminal with OLLAMA_MODELS set.
