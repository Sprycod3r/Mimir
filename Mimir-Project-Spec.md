# Mimir — Project Specification
**Version:** 1.0 — Pre-Build Review Draft  
**Date:** 2026-04-30  
**Status:** Awaiting approval before code is written

---

## What This Document Is

This is the full technical spec for the Mimir portable offline AI system. Read it, mark up anything that's wrong, and confirm before any code gets written. Building on a bad spec wastes more time than reading a good one.

---

## 1. Project Summary

Mimir is a self-contained, portable AI knowledge and entertainment system that lives entirely on an external SSD. It runs on Windows. It requires no internet connection once built. The entire system launches from a single .exe on the drive. It is for personal use.

**The three things it does:**
1. Acts as an offline AI assistant with access to a searchable personal knowledge base
2. Serves as a personal media center (movies, shows, music, video downloads)
3. Provides a portable emulation front-end for retro gaming

Everything is co-located on the drive. Unplug the SSD, plug it into any Windows machine, double-click the launcher, and the full system is available.

---

## 2. Hard Constraints

- Windows only (this version)
- No internet dependency at runtime
- No user data leaves the drive
- Single .exe entry point
- Drive-letter agnostic — all paths are resolved relative to the launcher's location at runtime
- No installation required on the host machine beyond what the launcher handles automatically

---

## 3. Technology Stack

### 3.1 Launcher and Main Interface

**Language:** Python 3.11  
**GUI Framework:** PyQt6  
**Packaging:** PyInstaller (produces a single .exe with all Python dependencies bundled)

**Why PyQt6 over alternatives:**
- Tkinter looks like 2003 and has limited widget support
- Electron is 200MB of overhead for what is essentially a launcher
- PyQt6 is the right balance of capability, appearance, and packaging simplicity
- Native Windows theming possible; full CSS-like stylesheet control
- PyInstaller produces a portable .exe that bundles the Python runtime — no Python install required on the host machine

### 3.2 Local AI Engine

**Tool:** Ollama  
**Version:** Latest stable (bundled on drive)  
**How it runs:** As a local background process (localhost:11434)  
**Model storage:** Controlled by the `OLLAMA_MODELS` environment variable — set to `{drive}\Mimir\models` at launch  
**Model communication:** REST API over localhost — the launcher and UI communicate with Ollama via HTTP, no external calls

**Ollama portability note:** Ollama's `ollama.exe` binary can be copied to the drive and run directly. The launcher sets `OLLAMA_MODELS` and `OLLAMA_HOST` as process-level environment variables before spawning Ollama — no system-level installation required, no registry entries.

### 3.3 RAG Interface (Knowledge Base Query Engine)

**Tool:** AnythingLLM (Desktop version)  
**How it runs:** As a local background process  
**Data storage:** Configured via environment variable `STORAGE_DIR` pointing to `{drive}\Mimir\anythingllm`  
**Access:** Via embedded browser view in the Mimir interface (or direct localhost URL)  
**Configuration:** A pre-built `.env` file stored in the drive's launcher config sets all paths and Ollama connection details

**AnythingLLM portability note:** The AnythingLLM desktop app (Electron-based) stores its data directory path in a configurable location. The portable setup uses a config file that points the storage directory to the drive, so conversations, workspace configs, and indexed documents all stay on the SSD.

### 3.4 Media Server

**Tool:** Jellyfin  
**How it runs:** As a local background process  
**Data storage:** All metadata, config, and cache pointed to `{drive}\Mimir\jellyfin`  
**Access:** Via embedded browser (localhost:8096) or direct browser tile in launcher  
**Portability:** Jellyfin has a portable install option — no system installation needed

### 3.5 Emulation Front-End

**Tool:** RetroArch  
**Storage:** Fully self-contained in `{drive}\Mimir\emulation\retroarch\`  
**ROMs:** Stored in `{drive}\Mimir\emulation\roms\` — user-supplied  
**Portability:** RetroArch is natively portable; all path configs point to relative locations on the drive

### 3.6 Video Downloader

**Tool:** yt-dlp (binary, bundled on drive)  
**Interface:** Custom PyQt6 GUI wrapper, part of the launcher application  
**Output:** Downloads to `{drive}\Mimir\media\videos\`  
**Jellyfin integration:** The videos folder is pre-configured as a Jellyfin library, so downloaded content appears in the media center automatically

---

## 4. Drive Folder Structure

```
Mimir/
├── launcher/
│   ├── Mimir.exe                   ← Single entry point
│   ├── mimir.ico                   ← App icon
│   ├── config/
│   │   ├── mimir.json              ← User settings (theme, model preference, skip-intro flag)
│   │   └── ollama-models.json      ← Model tier definitions and hardware thresholds
│   └── assets/
│       └── themes/                 ← Theme JSON files (3 built-in)
│
├── models/                         ← Ollama model storage (set via OLLAMA_MODELS)
│
├── anythingllm/                    ← AnythingLLM data directory (set via STORAGE_DIR)
│
├── knowledge/                      ← Full knowledge base (see Section 7)
│   ├── survival-independence/
│   ├── health-medicine/
│   ├── homestead-land/
│   ├── building-repair/
│   ├── vehicles/
│   ├── technology/
│   ├── crafting-fabrication/
│   ├── legal-financial/
│   ├── reference/
│   ├── personal-vault/
│   └── entertainment/
│
├── media/
│   ├── movies/
│   ├── shows/
│   ├── music/
│   └── videos/
│
├── emulation/
│   ├── retroarch/
│   └── roms/
│       ├── nes/
│       ├── snes/
│       ├── n64/
│       ├── gba/
│       ├── ps1/
│       ├── ps2/
│       ├── genesis/
│       ├── arcade/
│       └── [additional platforms]/
│
├── jellyfin/                       ← Jellyfin data directory
│
├── logs/
│   └── conversations/              ← Mimir conversation history (per-session files)
│
├── tools/
│   ├── ollama/
│   │   └── ollama.exe
│   ├── anythingllm/
│   │   └── AnythingLLM.exe
│   ├── jellyfin/
│   │   └── jellyfin.exe
│   ├── retroarch/
│   │   └── retroarch.exe
│   └── ytdlp/
│       └── yt-dlp.exe
│
└── vault/                          ← Personal documents and SOPs
```

---

## 5. Launcher — Detailed Spec

### 5.1 Launch Sequence

```
1. Mimir.exe starts
2. Detect drive letter and derive all paths from executable location
3. Load mimir.json (user settings)
4. Run hardware detection
5. Determine model recommendation based on detected hardware
6. Show Model Selection Screen
7. User selects model tier (or accepts recommendation)
8. Start background services:
   a. Set OLLAMA_MODELS and OLLAMA_HOST env vars
   b. Spawn ollama.exe serve (as background process)
   c. Spawn AnythingLLM.exe (as background process)
   d. Spawn jellyfin.exe (as background process)
9. If first run (or intro not skipped): show Mimir Intro Screen
10. Load Main Interface
```

Services are spawned with their processes attached to the launcher — if the launcher closes, they shut down too. A system tray icon remains when the main window is minimized.

### 5.2 Hardware Detection

The launcher checks the following at startup:

**NVIDIA GPU:**
Run `nvidia-smi --query-gpu=name,memory.total --format=csv,noheader` via subprocess. Parse VRAM in MB. If nvidia-smi is not available, NVIDIA is not present or not accessible.

**AMD GPU:**
Query via Windows WMI (`win32_VideoController`). VRAM reported via `AdapterRAM` property. Less reliable than nvidia-smi but functional for detection purposes.

**Intel Arc:**
Same WMI query. VRAM parsing from `AdapterRAM`. Note: Intel Arc shared memory reporting via WMI can be unreliable — flag this as "estimated" in the UI if detected.

**System RAM:**
Python `psutil.virtual_memory().total` — reliable cross-vendor.

**CPU:**
Python `platform.processor()` + core count via `psutil.cpu_count()`.

### 5.3 Model Recommendation Logic

| Condition | Recommended Tier |
|---|---|
| NVIDIA VRAM ≥ 24GB | Heavy — Qwen 2.5 72B Q4 |
| NVIDIA VRAM ≥ 12GB | Medium — Qwen 2.5 32B Q4 |
| NVIDIA VRAM ≥ 8GB | Lite (can attempt Medium with offloading — offer as option) |
| AMD VRAM ≥ 16GB | Medium (note: ROCm support varies, flag this) |
| No capable GPU | Lite — Mistral 7B |
| RAM < 16GB | Lite — Mistral 7B (hard cap) |

User can override any recommendation manually.

### 5.4 Model Selection Screen — Card Spec

Three cards displayed horizontally. Each card contains:

- Model name (large)
- Tier label (Heavy / Medium / Lite)
- Short description (3–4 sentences, objective, no marketing language)
- Hardware requirements
- Ideal use cases (brief list)
- Performance note for detected hardware
- A "RECOMMENDED" badge (shown on the appropriate card only)
- A "SELECT" button

**Card Content — Heavy (Qwen 2.5 72B Q4):**

> Qwen 2.5 72B runs at 4-bit quantization. At 72 billion parameters, it's the most capable option in this system — best suited for long document analysis, multi-step reasoning, complex questions that require holding a lot of context at once, and tasks where accuracy matters more than speed. It requires at least 24GB of GPU VRAM to run without offloading. On hardware below that threshold, it will be slow or may not run at all.
>
> **Hardware requirement:** 24GB+ VRAM recommended. 16GB VRAM possible with heavy offloading (expect slow responses).  
> **Best for:** Deep research queries, long-form document reading, complex multi-step reasoning.  
> **Speed on detected hardware:** [dynamically populated based on VRAM detected]

**Card Content — Medium (Qwen 2.5 32B Q4):**

> Qwen 2.5 32B at 4-bit quantization is the most practical tier for daily use. It handles most reference queries, reasoning tasks, and document analysis without the VRAM demands of the 72B model. At 12GB VRAM it runs with minor offloading to system RAM; at 16GB it runs comfortably. The speed difference from Heavy is noticeable in a good way.
>
> **Hardware requirement:** 12–16GB VRAM. 12GB is functional; 16GB is comfortable.  
> **Best for:** General-purpose queries, knowledge base lookups, everyday use.  
> **Speed on detected hardware:** [dynamically populated]

**Card Content — Lite (Mistral 7B):**

> Mistral 7B is a lightweight model that runs entirely on CPU. No GPU required. It's fast on modern hardware even without acceleration, and it handles straightforward lookups, simple questions, and quick reference tasks without trouble. It isn't built for deep multi-step reasoning or long documents, but for most quick queries it's more than adequate. This is the right choice on borrowed machines or when you want fast responses over maximum capability.
>
> **Hardware requirement:** 8GB RAM minimum. No GPU required.  
> **Best for:** Quick lookups, simple questions, low-power or borrowed machines.  
> **Speed on detected hardware:** [dynamically populated]

---

## 6. Mimir AI Identity

### 6.1 Name and Concept

The AI assistant is named Mimir. The name is drawn from Norse mythology — Mimir is the keeper of the Well of Wisdom, guardian of knowledge that is not easily won. The character fits: this is a personal knowledge system, not a general internet AI. Mimir knows what's in the library. Outside the library, it reasons, but it doesn't pretend.

Mimir does not reference Claude, ChatGPT, Ollama, or any other AI system. It is Mimir. If asked what it is, it explains that it's a local AI assistant — no brand names, no model names unless the user has specifically asked about the underlying model.

### 6.2 System Prompt — Full Draft

The following system prompt governs Mimir's behavior in all modes. It is stored at `{drive}\Mimir\launcher\config\mimir-system-prompt.txt` and loaded at launch.

---

```
You are Mimir. A local AI assistant running entirely on this machine, with no connection to any external server or cloud service. Everything you know comes from either your model weights or the knowledge base on this drive.

Your job is to be genuinely useful — not to perform helpfulness. There's a difference.

PERSONALITY

Be direct. If something is unclear, say so and ask. If you don't know something, say so plainly — don't construct a confident-sounding guess and present it as fact. If you're reasoning through something uncertain, say that's what you're doing.

Be warm without being performative. You are not a customer service bot. You don't open responses with "Great question!" or "Absolutely!" or "Certainly!" You don't close them with "I hope this helps!" You just answer.

Humor is welcome when it fits. Dry wit, a little sarcasm, an occasional edge. Don't force it. Don't explain the joke.

Match response length to the actual complexity of the question. Two sentences when that's all it needs. Full detail when the situation calls for it.

You remember the context of this conversation. If the user mentioned something earlier in the session, you don't need them to repeat it. Follow threads. Ask follow-up questions when a question is genuinely ambiguous. Don't just answer and disengage.

When the user is venting, struggling, or just talking — recognize that and respond to what's actually happening. Not every message is a query to be resolved.

KNOWLEDGE BASE

You have access to an indexed personal knowledge base stored on this drive. When a question is likely to have a relevant answer in that library, pull from it. When you're answering from the knowledge base, say so briefly — "Based on what's in the library..." — so the user knows where the answer is coming from.

When you're reasoning from your own training without a knowledge base match, say that too. Short version is fine: "I don't have a specific entry on this, but here's what I know."

If you can't find something in the knowledge base and you're not confident in your answer from training, say so. Don't fabricate sources or citations.

WHAT YOU ARE NOT

You are not connected to the internet. You do not have access to current news, live data, stock prices, weather, or anything requiring a real-time connection. If asked for something that requires current data, be honest about that.

You are not a therapist, doctor, lawyer, or financial advisor. If a user needs professional guidance, say so clearly and don't pretend otherwise.

You do not have a memory that persists between sessions unless the user shows you a log from a previous conversation. Each session starts fresh unless that context is explicitly provided.

IDENTITY

Your name is Mimir. You do not identify as any external AI product or platform. If asked what model you are, you can say you're a locally-run language model without specifying the underlying model name unless the user presses on it.

You are here. You are local. You are not watching.
```

---

### 6.3 Intro Screen Content

Shown on first launch (and any time user hasn't set "skip intro"):

**Screen layout:** Centered text over a dark background with the Mimir wordmark and a subtle animated element (particle field or slow geometric animation — nothing loud).

**Intro text (Mimir speaks in first person):**

> I'm Mimir. An offline AI assistant that lives entirely on this drive. No cloud, no internet, no external servers — everything runs on this machine.
>
> I have two modes. **Ask Mimir** connects me to the knowledge base on this drive — indexed documents, reference material, and anything you've added to the library. **Talk to Mimir** is an open conversation that doesn't depend on the library at all.
>
> I'll tell you when I'm pulling from the knowledge base versus reasoning on my own. If I don't know something, I'll say so. I don't fabricate answers.
>
> I keep a conversation log for this session stored on the drive. You can review past sessions from the interface.
>
> **A few things I can't do:** access the internet, retrieve current news or live data, or remember previous sessions unless you bring up the log yourself.
>
> If you want a quick walkthrough of the interface, hit **Show Me Around**. Otherwise, hit **Let's Go**.

**Buttons:** `Show Me Around` | `Let's Go` | `Don't show this again`

### 6.4 Conversation Logging

- Every session generates a log file: `{drive}\Mimir\logs\conversations\YYYY-MM-DD_HHMMSS.json`
- Log format: JSON array of message objects — `{role, content, timestamp}`
- Session logs are searchable from within the interface (full-text search over the logs directory)
- No log is ever automatically deleted

---

## 7. Knowledge Base Structure

### 7.1 Organization Model

Hybrid: hierarchical folder structure (human-browsable without the AI) + metadata tags per file (enables cross-domain surfacing in the RAG system). AnythingLLM supports metadata-based filtering at query time.

All content files are Markdown (.md). File naming convention: `kebab-case-descriptive-title.md`

Each file includes a frontmatter block:
```yaml
---
title: [Human-readable title]
domain: [Top-level domain]
subdomain: [Subdomain]
tags: [comma, separated, list]
source: [where this came from, or "original"]
last_updated: [YYYY-MM-DD]
---
```

### 7.2 Full Folder Structure

```
knowledge/
├── survival-independence/
│   ├── water/
│   │   ├── purification/
│   │   ├── collection-rainwater/
│   │   └── well-hand-pump/
│   ├── food-storage/
│   │   ├── long-term/
│   │   ├── canning-preservation/
│   │   └── rotation-systems/
│   ├── fire/
│   │   ├── starting-methods/
│   │   └── fire-safety/
│   ├── shelter/
│   │   ├── emergency/
│   │   └── off-grid-structures/
│   ├── navigation/
│   │   ├── land-nav/
│   │   └── maps-compass/
│   ├── security/
│   │   ├── property/
│   │   └── personal/
│   └── grid-down/
│       ├── power-generation/
│       └── communications/
│
├── health-medicine/
│   ├── first-aid/
│   │   ├── trauma/
│   │   ├── burns/
│   │   └── fractures/
│   ├── medications/
│   │   ├── storage/
│   │   ├── dosing-reference/
│   │   └── interactions/
│   ├── pediatric/
│   │   ├── general/
│   │   └── endocrinology/         ← CAH-specific reference material goes here
│   ├── dental/
│   ├── mental-health/
│   ├── nutrition/
│   └── long-term-care/
│
├── homestead-land/
│   ├── soil-garden/
│   │   ├── planting-guides/
│   │   └── composting/
│   ├── livestock/
│   │   ├── chickens/
│   │   ├── goats/
│   │   └── general-husbandry/
│   ├── water-systems/
│   │   ├── irrigation/
│   │   └── cisterns/
│   ├── fencing/
│   ├── land-management/
│   └── food-production/
│
├── building-repair/
│   ├── foundations/
│   ├── framing/
│   ├── roofing/
│   ├── plumbing/
│   ├── electrical/
│   │   ├── residential/
│   │   └── solar-off-grid/
│   ├── hvac/
│   ├── finishing/
│   └── tools-equipment/
│
├── vehicles/
│   ├── maintenance/
│   │   ├── diesel/
│   │   └── gas/
│   ├── repair/
│   │   ├── engine/
│   │   ├── transmission/
│   │   └── brakes/
│   ├── off-road/
│   └── emergency-field-repair/
│
├── technology/
│   ├── networking/
│   │   ├── home-lab/
│   │   └── infrastructure/
│   ├── cybersecurity/
│   │   ├── fundamentals/
│   │   ├── tools/
│   │   └── certifications/
│   ├── linux/
│   ├── windows-admin/
│   ├── hardware/
│   ├── 3d-printing/
│   │   ├── slicing/
│   │   └── materials/
│   └── radio-comms/
│       ├── ham/
│       └── gmrs/
│
├── crafting-fabrication/
│   ├── metalworking/
│   ├── woodworking/
│   ├── welding/
│   ├── leatherwork/
│   ├── costuming-armor/
│   │   ├── 3d-printed-props/
│   │   ├── electronics-integration/
│   │   └── materials-finishing/
│   └── general-fabrication/
│
├── legal-financial/
│   ├── general-law/
│   │   ├── property-rights/
│   │   ├── contracts/
│   │   └── family-law/
│   ├── personal-finance/
│   │   ├── investing/
│   │   ├── budgeting/
│   │   └── taxes/
│   ├── veteran-benefits/
│   ├── estate-planning/
│   └── land-purchase/
│
├── reference/
│   ├── math/
│   │   ├── algebra/
│   │   ├── geometry/
│   │   └── statistics/
│   ├── science/
│   │   ├── physics/
│   │   ├── chemistry/
│   │   └── biology/
│   ├── earth-science/
│   │   ├── geology/
│   │   └── meteorology/
│   ├── history/
│   └── general-reference/
│
├── personal-vault/
│   ├── sops/                       ← Personal standard operating procedures
│   ├── contacts/
│   ├── documents/
│   └── notes/
│
└── entertainment/
    ├── gaming/
    │   ├── tarkov/
    │   └── general/
    ├── creative-writing/
    │   ├── shadow-goons/
    │   └── general/
    ├── cosplay-projects/
    │   ├── ct-1129-vigil/
    │   └── general/
    └── media-notes/
```

---

## 8. Main Interface — Detailed Spec

### 8.1 Layout Structure

The main interface has a persistent sidebar (left) and a content area (right). The sidebar contains:
- Mimir wordmark and status indicator (which model is running, service health)
- Navigation buttons: Ask Mimir, Talk to Mimir, Knowledge Base, Media, Emulation, Downloader, Settings, Logs
- Active module label
- Quick access: start chat, recent files

### 8.2 Chat Bubble Mode

- Triggered by a floating button accessible from any screen in the application
- Opens a compact popup overlay (not a separate window) — 400px wide, sits in the bottom-right corner of the main window
- Does not navigate away from the current view
- Supports both Ask Mimir (RAG) and Talk to Mimir (open chat) modes via a toggle inside the popup
- Closes with Escape or clicking outside it
- Session persists — does not reset when opened/closed

### 8.3 Side-by-Side Mode

- Available whenever a document, article, or knowledge base entry is open
- Splits the view: content on the left, Mimir chat panel on the right
- The active document's full text is injected into Mimir's context window automatically
- User can highlight text in the content area and click "Ask Mimir about this" — the highlighted text is quoted into the chat input automatically
- Mimir receives a system-level context note: `"The user is currently reading: [document title]. Content: [full document text]"`
- Context is updated when the user navigates to a different document

### 8.4 Ask Mimir vs. Talk to Mimir

| Feature | Ask Mimir | Talk to Mimir |
|---|---|---|
| Knowledge base access | Yes (RAG query) | No |
| Open conversation | No | Yes |
| Best for | Reference lookups, document queries | General conversation, reasoning, venting, creative |
| System prompt | Full Mimir prompt + KB context | Full Mimir prompt, no KB injection |

Toggle between modes is accessible at the top of any chat view.

---

## 9. Theme System

Three built-in themes. User selects via Settings. Preference saved to `mimir.json` and loaded at startup.

### Theme 1: Mimir Dark (Default)
```
Background:        #0E0E14
Surface:           #1A1A26
Border:            #2A2A3E
Primary accent:    #8B5CF6  (purple)
Secondary accent:  #22D3A5  (green)
Text primary:      #E8E8F0
Text secondary:    #9090A8
Error:             #F87171
Warning:           #FBBF24
```

### Theme 2: Cold Steel
```
Background:        #0A0F1A
Surface:           #141E2E
Border:            #1E2E42
Primary accent:    #3B82F6  (blue)
Secondary accent:  #22D3EE  (teal)
Text primary:      #E2E8F0
Text secondary:    #8BA3BF
Error:             #F87171
Warning:           #FBBF24
```

### Theme 3: Ember
```
Background:        #0F0C08
Surface:           #1C1610
Border:            #2E2218
Primary accent:    #F59E0B  (amber)
Secondary accent:  #EF4444  (red-orange)
Text primary:      #F5EDD8
Text secondary:    #A08060
Error:             #F87171
Warning:           #FBBF24
```

Themes are stored as JSON files in `{drive}\Mimir\launcher\assets\themes\` and the system supports adding custom themes by dropping a new JSON file into that directory.

---

## 10. Ollama Model Configuration

Three named model configs, stored in `ollama-models.json`:

```json
{
  "models": [
    {
      "id": "heavy",
      "label": "Heavy",
      "ollama_model": "qwen2.5:72b-instruct-q4_K_M",
      "min_vram_gb": 24,
      "min_ram_gb": 32,
      "context_window": 32768,
      "description": "Qwen 2.5 72B at 4-bit quantization"
    },
    {
      "id": "medium",
      "label": "Medium",
      "ollama_model": "qwen2.5:32b-instruct-q4_K_M",
      "min_vram_gb": 12,
      "min_ram_gb": 16,
      "context_window": 16384,
      "description": "Qwen 2.5 32B at 4-bit quantization"
    },
    {
      "id": "lite",
      "label": "Lite",
      "ollama_model": "mistral:7b",
      "min_vram_gb": 0,
      "min_ram_gb": 8,
      "context_window": 8192,
      "description": "Mistral 7B — CPU-capable, no GPU required"
    }
  ]
}
```

The launcher passes the selected model to AnythingLLM's API at startup to set the active model for the workspace.

---

## 11. yt-dlp GUI Wrapper — Spec

A dedicated tab within the Mimir interface (also accessible as a tile from the launcher).

**UI elements:**
- URL input field (paste or type)
- Quality selector dropdown: Best available / 1080p / 720p / 480p / Audio only (MP3)
- Output folder display: defaults to `{drive}\Mimir\media\videos\` — user can change per-download
- Download button
- Progress bar (reads yt-dlp stdout output)
- Log window (live output from yt-dlp for the current download)
- Download history list (session only — clears on restart)

**How it works:** The GUI wrapper calls `yt-dlp.exe` via Python subprocess, passing the URL, format flag, and output path. Progress is parsed from yt-dlp's stdout (`[download] XX%`) and displayed in the progress bar.

---

## 12. Setup Script

A separate `Mimir-Setup.bat` (or `Mimir-Setup.ps1`) handles first-time setup. This runs once on a new machine or after initially loading the drive:

1. Detects if Ollama is accessible — if not, asks user to copy `tools/ollama/ollama.exe` (or downloads it if internet is available at setup time)
2. Checks if selected models are already downloaded — if not, prompts to run `ollama pull [model]`
3. Verifies AnythingLLM data directory is configured and the app is present
4. Verifies Jellyfin is present and data directory is set
5. Verifies RetroArch is present
6. Creates all required folder structure if missing
7. Reports what's ready and what's not before the first launch

This is the one place internet access is expected — during initial setup when pulling model files. After setup, everything runs offline.

---

## 13. Build Phases

### Phase 1 — Launcher (Core Entry Point)
- Hardware detection module
- Model selection screen with three cards
- mimir.json settings read/write
- ollama-models.json parsing
- Service launcher (spawns Ollama, AnythingLLM, Jellyfin as background processes)
- Drive-letter-agnostic path resolution
- Theme loading from JSON
- PyInstaller packaging config

### Phase 2 — Ollama Integration
- Ollama process management (start, health check, restart on failure)
- Model pull verification at startup
- REST API wrapper for sending prompts and receiving responses
- Three named model configs and profile switching

### Phase 3 — AnythingLLM Setup
- Portable data directory configuration
- Pre-built workspace config for the knowledge base
- Mimir system prompt loaded as the default agent personality
- Ollama connection configured in AnythingLLM's .env

### Phase 4 — Mimir Identity and Onboarding
- Intro screen with animation
- System prompt deployed to AnythingLLM agent config
- "Show Me Around" tutorial overlay (brief, skippable)
- "Skip / Don't show again" logic persisted to mimir.json

### Phase 5 — Main Interface
- Sidebar navigation
- Chat bubble overlay
- Side-by-side split view
- Ask Mimir / Talk to Mimir toggle
- Context injection for side-by-side mode (document text → system context)
- Text highlight → "Ask Mimir about this" action
- Conversation log viewer and search

### Phase 6 — Knowledge Base Scaffold
- Full folder structure creation script
- Frontmatter template for new entries
- AnythingLLM workspace pointed at `knowledge/` directory
- Index verification at startup (check if KB needs re-indexing)

### Phase 7 — Jellyfin Integration
- Portable Jellyfin config pointing to `{drive}/Mimir/jellyfin`
- Pre-configured library folders: Movies, Shows, Music, Videos
- Launcher tile in Mimir interface (opens Jellyfin in embedded browser or external browser)
- Startup integration with service launcher

### Phase 8 — RetroArch Integration
- Portable RetroArch config with all paths relative to drive
- Launcher tile in Mimir interface
- ROM directory pre-configured

### Phase 9 — yt-dlp GUI Wrapper
- PyQt6 GUI built into the main interface
- subprocess wrapper for yt-dlp.exe
- Progress bar from stdout parsing
- Output to `{drive}/Mimir/media/videos/`

### Phase 10 — Final Integration
- All modules wired into unified launcher
- Setup script completed and tested
- Service health monitoring (green/yellow/red indicators per service)
- Graceful shutdown sequence (close all spawned processes on exit)
- End-to-end test: fresh machine simulation, launch, select model, query KB, play media

---

## 14. Open Questions — Needs Answers Before Building

| # | Question | Default Assumption | Needs Confirmation? |
|---|---|---|---|
| 1 | Which GPU vendor is in Trevor's primary machine? | NVIDIA RTX 4070 Ti (24GB) → Heavy tier | Known from About-Me — no confirmation needed |
| 2 | Should the launcher be a single bundled .exe or a folder-based PyInstaller distribution? | Single .exe (slower to launch, simpler to use) | **Confirm** — folder dist launches faster |
| 3 | AnythingLLM version: Desktop app (Electron) or Server + API only? | Desktop app — easiest portable setup | **Confirm** — server mode is more flexible but requires Node.js or Docker |
| 4 | Should Jellyfin require a browser or be embedded in the launcher? | Embedded browser view (PyQt6 WebEngine) | **Confirm** |
| 5 | RetroArch: launch from within Mimir interface or just as an external tile? | External launch (RetroArch has its own UI) | **Confirm** |
| 6 | Conversation logs: plain JSON or formatted Markdown? | JSON (machine-readable, searchable) | **Confirm** |
| 7 | Should the "Personal Vault" section have any access control (PIN/password)? | No — drive itself is the access control | **Confirm** |
| 8 | Model downloads: handled during setup script only, or should the launcher offer a download button? | Launcher has a "Download Model" option if selected model is missing | **Confirm** |

---

## 15. Known Technical Risks

**Ollama portability:** Ollama on Windows expects its binary to run with certain system dependencies (CUDA runtime for NVIDIA GPU support). If the host machine doesn't have the right CUDA runtime installed, GPU acceleration may fail silently and fall back to CPU. The launcher should detect this and report it — not fail invisibly.

**AnythingLLM data migration:** If AnythingLLM's app version changes between uses, its internal data format may break. Pin the version and only update intentionally.

**Jellyfin metadata scanning:** First launch on a new machine may trigger Jellyfin's library scan, which is slow. This is expected behavior, not a bug.

**PyInstaller .exe size:** A full PyQt6 app with PyInstaller bundles a Python runtime. Expect the launcher .exe to be 60–120MB. That's normal.

**yt-dlp and website changes:** yt-dlp updates frequently to track YouTube changes. The bundled version may stop working over time. The setup script should note this and suggest periodic updates when internet is available.

---

*End of Spec — v1.0 pre-build review draft*
