#Requires -Version 5.1
<#
.SYNOPSIS
    TechBS installer for Windows.
.DESCRIPTION
    Sets up the Python virtual environment, installs dependencies, downloads
    model weights from Azure, and optionally configures an LLM provider.
.NOTES
    If execution policy blocks this script, run once from an admin PowerShell:
        Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
#>

# ── Azure model storage ───────────────────────────────────────────────────────
# Replace the value below with your full Azure Blob container URL including
# the embedded SAS token before distributing.
$AzureModelUrl = "REPLACE_WITH_AZURE_URL"
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
& $pip install --upgrade pip --quiet

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

# ── LLM provider (optional) ───────────────────────────────────────────────────
Write-Host ""
$llmChoice = Read-Host "Configure LLM provider for --summarize? (run installer again to change) [y/N]"
if ($llmChoice -imatch '^y') {
    Write-Host ""
    Write-Host "Select LLM provider:"
    Write-Host "  1) Ollama  (local, free -- requires Ollama installed separately)"
    Write-Host "  2) Claude  (cloud  -- requires ANTHROPIC_API_KEY env var)"
    Write-Host "  3) OpenAI  (cloud  -- requires OPENAI_API_KEY env var)"
    Write-Host "  4) Gemini  (cloud  -- requires GOOGLE_API_KEY env var)"
    Write-Host ""
    $providerChoice = Read-Host "Choice [1-4]"

    $llmProvider = switch ($providerChoice) {
        "1" { "ollama" }
        "2" { "claude" }
        "3" { "openai" }
        "4" { "gemini" }
        default { $null }
    }

    if ($llmProvider) {
        $llmModel = switch ($llmProvider) {
            "ollama" {
                try {
                    $tags   = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 2
                    $models = $tags.models
                    if ($models.Count -gt 0) {
                        Write-Host "Available Ollama models:"
                        for ($i = 0; $i -lt $models.Count; $i++) {
                            Write-Host "  $($i + 1)) $($models[$i].name)"
                        }
                        Write-Host ""
                        $raw = Read-Host "Model [number or name]"
                        $n   = 0
                        if ([int]::TryParse($raw, [ref]$n) -and $n -ge 1 -and $n -le $models.Count) {
                            $models[$n - 1].name
                        } else { $raw }
                    } else {
                        Write-Host "No models found. Pull one first: ollama pull llama3.2"
                        Read-Host "Model name"
                    }
                } catch {
                    Write-Host "Ollama not running. Examples: llama3.2  mistral  qwen3:mcp  phi4"
                    Read-Host "Model name"
                }
            }
            "claude" {
                $m = Read-Host "Claude model [claude-sonnet-4-6]"
                if ($m) { $m } else { "claude-sonnet-4-6" }
            }
            "openai" {
                $m = Read-Host "OpenAI model [gpt-4o]"
                if ($m) { $m } else { "gpt-4o" }
            }
            "gemini" {
                $m = Read-Host "Gemini model [gemini-2.0-flash]"
                if ($m) { $m } else { "gemini-2.0-flash" }
            }
        }

        $configDir = "$env:USERPROFILE\.techbs"
        if (-not (Test-Path $configDir)) { New-Item -ItemType Directory -Path $configDir | Out-Null }
        [ordered]@{ provider = $llmProvider; model = $llmModel } |
            ConvertTo-Json | Set-Content "$configDir\llm_config.json" -Encoding UTF8
        Write-Host "Saved: $llmProvider / $llmModel"

        $pkgMap = @{ claude = "anthropic"; openai = "openai"; gemini = "google-genai" }
        if ($pkgMap.ContainsKey($llmProvider)) {
            Write-Host "Installing $($pkgMap[$llmProvider]) package..."
            & $pip install $pkgMap[$llmProvider] --quiet
        }

        switch ($llmProvider) {
            "ollama" { Write-Host "Make sure Ollama is installed (https://ollama.com) and the model is pulled." }
            "claude" { Write-Host "Set ANTHROPIC_API_KEY in your environment before using --summarize." }
            "openai" { Write-Host "Set OPENAI_API_KEY in your environment before using --summarize." }
            "gemini" { Write-Host "Set GOOGLE_API_KEY in your environment before using --summarize." }
        }
    }
}

Write-Host ""
Write-Host "Installation complete. Run the app with: .\run.ps1" -ForegroundColor Green
Read-Host "Press Enter to exit"
