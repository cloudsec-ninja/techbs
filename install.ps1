#Requires -Version 5.1
<#
.SYNOPSIS
    TechBS installer for Windows.
.DESCRIPTION
    Sets up the Python virtual environment, installs dependencies, downloads
    model weights and verifies their integrity.
.NOTES
    If execution policy blocks this script, run once from an admin PowerShell:
        Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
#>

# ── Azure model storage ───────────────────────────────────────────────────────
# Replace the value below with your full Azure Blob container URL including
# the embedded SAS token before distributing.
$AzureModelUrl = "https://ddffrrrsseee.blob.core.windows.net/models?sp=r&st=2026-03-14T18:13:10Z&se=2026-04-01T02:28:10Z&spr=https&sv=2024-11-04&sr=c&sig=E0TDvGmNUYCNW9MeW8KgAsI6JMk9BmI66EkisaIQIFQ%3D"
# ─────────────────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot

Write-Host "=== TechBS Installer ===" -ForegroundColor Cyan

# ── Python 3.10+ ─────────────────────────────────────────────────────────────
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python not found. Install Python 3.10+ from https://www.python.org/downloads/"
    exit 1
}

$pyVersion = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$pyParts   = $pyVersion -split '\.'
if ([int]$pyParts[0] -lt 3 -or ([int]$pyParts[0] -eq 3 -and [int]$pyParts[1] -lt 10)) {
    Write-Error "Python 3.10+ required. Found $pyVersion."
    exit 1
}
Write-Host "Python $pyVersion found."

# ── ffmpeg ───────────────────────────────────────────────────────────────────
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host "ERROR: ffmpeg not found. TechBS requires ffmpeg to decode audio." -ForegroundColor Red
    Write-Host "  1. Download: https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    Write-Host "  2. Extract ffmpeg.exe to e.g. C:\ffmpeg\bin\"
    Write-Host "  3. Add that folder to your system PATH"
    Write-Host "  4. Re-run this installer."
    Read-Host "Press Enter to exit"
    exit 1
}

# ── Virtual environment ───────────────────────────────────────────────────────
Write-Host "Creating virtual environment..."
if (-not (Test-Path "$ScriptDir\venv")) {
    & python -m venv "$ScriptDir\venv"
}

$pip  = "$ScriptDir\venv\Scripts\pip.exe"
$pyEx = "$ScriptDir\venv\Scripts\python.exe"

# ── Dependencies ──────────────────────────────────────────────────────────────
Write-Host "Installing dependencies (this may take several minutes)..."
& $pyEx -m pip install --upgrade pip --quiet

# PyTorch: CUDA build if NVIDIA GPU present, otherwise CPU-only
$nvSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if (-not $nvSmi -and (Test-Path "C:\Windows\System32\nvidia-smi.exe")) {
    $nvSmi = "C:\Windows\System32\nvidia-smi.exe"
}
if ($nvSmi) {
    Write-Host "NVIDIA GPU detected -- installing CUDA-enabled PyTorch..."
    & $pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128 --quiet
} else {
    Write-Host "No NVIDIA GPU detected -- installing CPU-only PyTorch..."
    & $pip install torch torchvision --quiet
}

& $pip install -r "$ScriptDir\requirements.txt" --quiet

# ── Whisper base model ────────────────────────────────────────────────────────
Write-Host "Downloading Whisper base model..."
& $pyEx -c "import whisper; whisper.load_model('base'); print('Whisper model cached.')"

# ── TechBS model weights ──────────────────────────────────────────────────────
if ($AzureModelUrl -eq "REPLACE_WITH_AZURE_URL") {
    Write-Host ""
    Write-Warning "Azure model URL not configured. Place model weights in models\ manually."
} else {
    Write-Host "Downloading TechBS models from Azure..."
    & $pyEx "$ScriptDir\app\model_downloader.py" --url $AzureModelUrl --models-dir "$ScriptDir\models"
}

Write-Host ""
Write-Host "Installation complete. Run the app with: .\techbs.ps1" -ForegroundColor Green
Read-Host "Press Enter to exit"
