#Requires -Version 5.1
<#
.SYNOPSIS
    Mimir first-run setup verifier and directory scaffolder.

.DESCRIPTION
    Checks that all required tools, binaries, and directories are present on
    the Mimir drive. Reports the status of each component and offers to create
    any missing directories.

    Run this script once after copying Mimir onto a new drive, and any time
    something isn't working and you want a quick health snapshot.

.EXAMPLE
    .\Mimir-Setup.ps1
    .\Mimir-Setup.ps1 -AutoFix        # Create missing dirs without prompting
    .\Mimir-Setup.ps1 -SkipDirCheck   # Only verify binaries
#>

[CmdletBinding()]
param(
    [switch]$AutoFix,
    [switch]$SkipDirCheck
)

Set-StrictMode -Off
$ErrorActionPreference = "Stop"

# ============================================================
# Helpers
# ============================================================

function Write-Header {
    param([string]$Text)
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor DarkGray
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor DarkGray
}

function Write-Check {
    param(
        [string]$Label,
        [bool]$Pass,
        [string]$Detail = ""
    )
    $icon  = if ($Pass) { "[OK]" } else { "[!!]" }
    $color = if ($Pass) { "Green" } else { "Red" }
    $line  = "  $icon  $Label"
    if ($Detail) { $line += "  ($Detail)" }
    Write-Host $line -ForegroundColor $color
}

function Write-Info {
    param([string]$Text)
    Write-Host "       $Text" -ForegroundColor DarkGray
}

function Resolve-RelativePath {
    param([string]$Relative)
    return Join-Path $MimirRoot $Relative
}

# ============================================================
# Drive root
# ============================================================

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$MimirRoot  = $ScriptDir  # Script lives at Mimir root

Write-Host ""
Write-Host "  MIMIR SETUP CHECK" -ForegroundColor White
Write-Host "  Drive root: $MimirRoot" -ForegroundColor DarkGray

# ============================================================
# 1. Launcher binary
# ============================================================

Write-Header "Launcher"

$LauncherExe = Resolve-RelativePath "launcher\Mimir.exe"
$LauncherExists = Test-Path $LauncherExe
Write-Check "Mimir.exe"           $LauncherExists    $LauncherExe

$LauncherConfig = Resolve-RelativePath "launcher\config\mimir.json"
$OllamaModels   = Resolve-RelativePath "launcher\config\ollama-models.json"
$SystemPrompt   = Resolve-RelativePath "launcher\config\mimir-system-prompt.txt"
Write-Check "config\mimir.json"              (Test-Path $LauncherConfig) $LauncherConfig
Write-Check "config\ollama-models.json"      (Test-Path $OllamaModels)   $OllamaModels
Write-Check "config\mimir-system-prompt.txt" (Test-Path $SystemPrompt)   $SystemPrompt

# ============================================================
# 2. AI tools
# ============================================================

Write-Header "AI Engine (required)"

$OllamaExe     = Resolve-RelativePath "tools\ollama\ollama.exe"
$AtllmExe      = Resolve-RelativePath "tools\anythingllm\AnythingLLM.exe"
$OllamaExists  = Test-Path $OllamaExe
$AtllmExists   = Test-Path $AtllmExe

Write-Check "ollama.exe"        $OllamaExists  $OllamaExe
Write-Check "AnythingLLM.exe"   $AtllmExists   $AtllmExe

if (-not $OllamaExists) {
    Write-Info "Download from https://ollama.com/download"
    Write-Info "Extract ollama.exe into tools\ollama\"
}
if (-not $AtllmExists) {
    Write-Info "Download AnythingLLM Desktop from https://useanything.com/"
    Write-Info "Extract into tools\anythingllm\"
}

# ============================================================
# 3. Optional tools
# ============================================================

Write-Header "Optional Tools"

$JellyfinExe    = Resolve-RelativePath "tools\jellyfin\jellyfin.exe"
$RetroArchExe   = Resolve-RelativePath "emulation\retroarch\retroarch.exe"
$YtdlpExe       = Resolve-RelativePath "tools\ytdlp\yt-dlp.exe"
$FfmpegExe      = Resolve-RelativePath "tools\ffmpeg\ffmpeg.exe"

$JellyfinExists  = Test-Path $JellyfinExe
$RetroArchExists = Test-Path $RetroArchExe
$YtdlpExists     = Test-Path $YtdlpExe
$FfmpegExists    = Test-Path $FfmpegExe

Write-Check "jellyfin.exe (media server)"    $JellyfinExists  $JellyfinExe
Write-Check "retroarch.exe (emulation)"      $RetroArchExists $RetroArchExe
Write-Check "yt-dlp.exe (video downloads)"   $YtdlpExists     $YtdlpExe
Write-Check "ffmpeg.exe (audio conversion)"  $FfmpegExists    $FfmpegExe

if (-not $JellyfinExists) {
    Write-Info "Download from https://jellyfin.org/downloads/ — use the portable build"
    Write-Info "Extract into tools\jellyfin\"
}
if (-not $RetroArchExists) {
    Write-Info "Download RetroArch portable from https://www.retroarch.com/"
    Write-Info "Extract into emulation\retroarch\"
}
if (-not $YtdlpExists) {
    Write-Info "Download yt-dlp.exe from https://github.com/yt-dlp/yt-dlp/releases"
    Write-Info "Place in tools\ytdlp\"
}
if (-not $FfmpegExists) {
    Write-Info "Download ffmpeg from https://ffmpeg.org/download.html"
    Write-Info "Place ffmpeg.exe in tools\ffmpeg\  (needed for MP3 conversion)"
}

# ============================================================
# 4. Ollama model check
# ============================================================

Write-Header "Ollama Models"

$ModelsDir    = Resolve-RelativePath "models"
$ModelsExist  = Test-Path $ModelsDir

if ($ModelsExist) {
    # Ollama stores models as blobs in models\blobs\ — count them as a proxy
    $BlobsDir   = Join-Path $ModelsDir "blobs"
    $ManifestDir = Join-Path $ModelsDir "manifests"

    $HasBlobs     = (Test-Path $BlobsDir)     -and ((Get-ChildItem $BlobsDir     -File -ErrorAction SilentlyContinue).Count -gt 0)
    $HasManifests = (Test-Path $ManifestDir)  -and ((Get-ChildItem $ManifestDir  -Recurse -File -ErrorAction SilentlyContinue).Count -gt 0)

    if ($HasBlobs -and $HasManifests) {
        $BlobCount = (Get-ChildItem $BlobsDir -File).Count
        Write-Check "Ollama models present" $true  "$BlobCount blob(s) in models\blobs\"
    }
    else {
        Write-Check "Ollama models" $false "No models found in $ModelsDir"
        Write-Info "Launch Mimir and it will prompt you to download a model"
        Write-Info "Or run:  ollama pull mistral:7b  (requires Ollama in PATH or run ollama.exe directly)"
    }
}
else {
    Write-Check "models\ directory" $false "Missing — will be created below"
}

# ============================================================
# 5. Directory structure
# ============================================================

if (-not $SkipDirCheck) {
    Write-Header "Directory Structure"

    $RequiredDirs = @(
        "models",
        "knowledge",
        "anythingllm",
        "jellyfin",
        "media",
        "media\movies",
        "media\shows",
        "media\music",
        "media\videos",
        "emulation",
        "emulation\roms",
        "emulation\retroarch",
        "emulation\retroarch\cores",
        "emulation\retroarch\system",
        "emulation\retroarch\saves",
        "emulation\retroarch\states",
        "emulation\retroarch\screenshots",
        "logs",
        "logs\conversations",
        "vault",
        "tools\ollama",
        "tools\anythingllm",
        "tools\jellyfin",
        "tools\ytdlp",
        "tools\ffmpeg",
        "launcher\config",
        "launcher\assets\themes"
    )

    $MissingDirs = @()

    foreach ($Rel in $RequiredDirs) {
        $Full = Resolve-RelativePath $Rel
        $Exists = Test-Path $Full
        Write-Check $Rel $Exists
        if (-not $Exists) {
            $MissingDirs += $Full
        }
    }

    # ---- Offer to create missing dirs ----
    if ($MissingDirs.Count -gt 0) {
        Write-Host ""
        Write-Host ("  " + $MissingDirs.Count + " director" + $(if ($MissingDirs.Count -eq 1) { "y is" } else { "ies are" }) + " missing.") -ForegroundColor Yellow

        $DoCreate = $AutoFix
        if (-not $AutoFix) {
            $Answer = Read-Host "  Create them now? [Y/n]"
            $DoCreate = ($Answer -eq "" -or $Answer -match "^[Yy]")
        }

        if ($DoCreate) {
            Write-Host ""
            foreach ($Dir in $MissingDirs) {
                try {
                    New-Item -ItemType Directory -Path $Dir -Force | Out-Null
                    Write-Host "  [+] Created: $Dir" -ForegroundColor Green
                }
                catch {
                    Write-Host "  [!] Failed:  $Dir  ($_)" -ForegroundColor Red
                }
            }
            Write-Host ""
            Write-Host "  Done. Re-run this script to confirm all directories now exist." -ForegroundColor Cyan
        }
        else {
            Write-Host "  Skipped. Mimir will create directories it needs on first launch." -ForegroundColor DarkGray
        }
    }
    else {
        Write-Host ""
        Write-Host "  All directories present." -ForegroundColor Green
    }
}

# ============================================================
# 6. Summary
# ============================================================

Write-Header "Summary"

$CoreOk     = $OllamaExists -and $AtllmExists
$LaunchOk   = $LauncherExists
$AllToolsOk = $JellyfinExists -and $RetroArchExists -and $YtdlpExists

if ($LaunchOk -and $CoreOk) {
    Write-Host "  Mimir is ready to launch." -ForegroundColor Green
    Write-Host ""
    Write-Host "  Run: launcher\Mimir.exe" -ForegroundColor White
}
elseif ($LaunchOk -and -not $CoreOk) {
    Write-Host "  Launcher present but one or more required AI tools are missing." -ForegroundColor Yellow
    Write-Host "  Install the missing tools above, then re-run this script." -ForegroundColor DarkGray
}
else {
    Write-Host "  Mimir.exe not found. Build the launcher first:" -ForegroundColor Yellow
    Write-Host "    cd launcher" -ForegroundColor DarkGray
    Write-Host "    pip install -r requirements.txt" -ForegroundColor DarkGray
    Write-Host "    pyinstaller Mimir.spec" -ForegroundColor DarkGray
}

if (-not $AllToolsOk) {
    Write-Host ""
    Write-Host "  Optional tools missing — media, emulation, or download features" -ForegroundColor DarkGray
    Write-Host "  will show a 'not installed' state in the UI until they're added." -ForegroundColor DarkGray
}

Write-Host ""
