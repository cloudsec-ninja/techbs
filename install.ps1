#Requires -Version 5.1
<#
.SYNOPSIS
    TechBS web installer for Windows.
.DESCRIPTION
    Downloads the latest TechBS release, creates a Python virtual environment,
    installs TechBS into it, and registers the `techbs` command.
    Downloaded models are kept across reinstalls.
.NOTES
    Usage:  irm https://techbs.ai/install.ps1 | iex

    Testing an unpublished build:
        $env:TECHBS_SOURCE = "C:\path\to\techbs-v0.90b0.zip"; .\install.ps1

    If execution policy blocks this script, run once:
        Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
#>

$ErrorActionPreference = "Stop"

# Detect uninstall: set $env:TECHBS_UNINSTALL=1 before piping, or pass -Uninstall as arg
$Uninstall = ($args -contains "-Uninstall") -or ($env:TECHBS_UNINSTALL -eq "1")

$GitHubRepo     = "cloudsec-ninja/techbs"
$GitHubApi      = "https://api.github.com/repos/$GitHubRepo/releases/latest"
$DefaultInstall = Join-Path $env:LOCALAPPDATA "techbs"
$LegacyInstall  = Join-Path $env:USERPROFILE "techbs"   # pre-0.91 install location

function Remove-FromUserPath([string]$dir) {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -and ($userPath -split ";") -contains $dir) {
        $newPath = ($userPath -split ";" | Where-Object { $_ -and $_ -ne $dir }) -join ";"
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-Host "Removed $dir from PATH" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "+==========================================+" -ForegroundColor Cyan
Write-Host "|        TechBS Installer                  |" -ForegroundColor Cyan
Write-Host "|        Cut through the BS.               |" -ForegroundColor Cyan
Write-Host "+==========================================+" -ForegroundColor Cyan
Write-Host ""

# -- Uninstall ----------------------------------------------------------------
if ($Uninstall) {
    Write-Host "Uninstalling TechBS..." -ForegroundColor Cyan

    $customHome = [Environment]::GetEnvironmentVariable("TECHBS_HOME", "User")
    $targets = @($DefaultInstall, $LegacyInstall)
    if ($customHome) { $targets += $customHome }

    foreach ($dir in $targets) {
        Remove-FromUserPath (Join-Path $dir "bin")
        Remove-FromUserPath $dir
        if (Test-Path $dir) {
            Remove-Item $dir -Recurse -Force
            Write-Host "Removed $dir" -ForegroundColor Green
        }
    }
    if ($customHome) {
        [Environment]::SetEnvironmentVariable("TECHBS_HOME", $null, "User")
    }

    Write-Host ""
    Write-Host "TechBS has been uninstalled." -ForegroundColor Green
    $env:TECHBS_UNINSTALL = $null
    return
}

# -- Python 3.10+ -------------------------------------------------------------
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python not found. Install Python 3.10+ from https://www.python.org/downloads/"
    return
}

$pyVersion = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$pyParts   = $pyVersion -split '\.'
if ([int]$pyParts[0] -lt 3 -or ([int]$pyParts[0] -eq 3 -and [int]$pyParts[1] -lt 10)) {
    Write-Error "Python 3.10+ required. Found $pyVersion."
    return
}
Write-Host "Python $pyVersion found."

# -- ffmpeg --------------------------------------------------------------------
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host "ERROR: ffmpeg not found. TechBS requires ffmpeg to decode audio." -ForegroundColor Red
    Write-Host "  1. Download: https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    Write-Host "  2. Extract ffmpeg.exe to e.g. C:\ffmpeg\bin\"
    Write-Host "  3. Add that folder to your system PATH"
    Write-Host "  4. Re-run this installer."
    Read-Host "Press Enter to exit"
    return
}
Write-Host "ffmpeg found."

# -- Visual C++ Redistributable (required by PyTorch) --------------------------
$vcDll = Join-Path $env:SystemRoot "System32\vcruntime140.dll"
if (-not (Test-Path $vcDll)) {
    Write-Host ""
    Write-Host "ERROR: Microsoft Visual C++ Redistributable not found." -ForegroundColor Red
    Write-Host "  PyTorch requires vcruntime140.dll to run on Windows."
    Write-Host ""
    Write-Host "  Download and install from:" -ForegroundColor Cyan
    Write-Host "  https://aka.ms/vs/17/release/vc_redist.x64.exe"
    Write-Host ""
    Write-Host "  Install the redistributable, then re-run this installer."
    return
}

# -- Choose install directory --------------------------------------------------
Write-Host ""
$InstallDir = Read-Host "Install directory [$DefaultInstall]"
if ([string]::IsNullOrWhiteSpace($InstallDir)) {
    $InstallDir = $DefaultInstall
}
$InstallDir = [IO.Path]::GetFullPath($InstallDir)

# TechBS looks for models in %LOCALAPPDATA%\techbs unless TECHBS_HOME says otherwise
if ($InstallDir -ne $DefaultInstall) {
    [Environment]::SetEnvironmentVariable("TECHBS_HOME", $InstallDir, "User")
    $env:TECHBS_HOME = $InstallDir
    Write-Host "Set TECHBS_HOME=$InstallDir"
}

# -- Handle existing install (keep downloaded models) --------------------------
if (Test-Path (Join-Path $InstallDir "venv")) {
    $overwrite = Read-Host "TechBS is already installed at $InstallDir. Reinstall / update? (downloaded models are kept) [y/N]"
    if ($overwrite -notin @("y", "Y")) {
        Write-Host "Installation cancelled."
        return
    }
    Get-ChildItem $InstallDir -Force | Where-Object { $_.Name -ne "models" } | Remove-Item -Recurse -Force
}

New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null

# -- Migrate models from the pre-0.91 install location -------------------------
$legacyModels = Join-Path $LegacyInstall "models"
$newModels    = Join-Path $InstallDir "models"
if (($LegacyInstall -ne $InstallDir) -and (Test-Path $legacyModels) -and -not (Test-Path $newModels)) {
    Write-Host "Moving models from previous install ($legacyModels)..."
    Move-Item $legacyModels $newModels
    Remove-FromUserPath $LegacyInstall
    Write-Host "  The old folder $LegacyInstall is no longer used and can be deleted." -ForegroundColor Yellow
}

# -- Download the release (or use TECHBS_SOURCE) -------------------------------
$ZipPath     = Join-Path $env:TEMP "techbs-download.zip"
$ExtractTemp = Join-Path $env:TEMP "techbs-extract"

if ($env:TECHBS_SOURCE) {
    Write-Host ""
    Write-Host "Using local source: $env:TECHBS_SOURCE"
    Copy-Item $env:TECHBS_SOURCE $ZipPath -Force
} else {
    Write-Host ""
    Write-Host "Fetching latest release from GitHub..."
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $Release    = Invoke-RestMethod -Uri $GitHubApi -Headers @{ "User-Agent" = "TechBS-Installer" }
        $ReleaseUrl = ($Release.assets | Where-Object { $_.name -like "*.zip" } | Select-Object -First 1).browser_download_url
        if (-not $ReleaseUrl) {
            # Fallback to source zipball if no .zip asset uploaded
            $ReleaseUrl = $Release.zipball_url
        }
    } catch {
        Write-Error "Could not fetch release info from GitHub: $_"
        return
    }

    if (-not $ReleaseUrl) {
        Write-Error "Could not determine download URL from GitHub. Check your internet connection."
        return
    }

    Write-Host "Downloading TechBS..."
    try {
        Invoke-WebRequest -Uri $ReleaseUrl -OutFile $ZipPath -UseBasicParsing
    } catch {
        Write-Error "Download failed: $_"
        return
    }
}

if (Test-Path $ExtractTemp) { Remove-Item $ExtractTemp -Recurse -Force }
Expand-Archive -Path $ZipPath -DestinationPath $ExtractTemp -Force

# The archive wraps files in a single top-level dir
$inner  = Get-ChildItem $ExtractTemp -Directory | Select-Object -First 1
$SrcDir = if ($inner -and (Test-Path (Join-Path $inner.FullName "pyproject.toml"))) { $inner.FullName } else { $ExtractTemp }

# -- Virtual environment -------------------------------------------------------
Write-Host ""
Write-Host "Creating virtual environment..."
& python -m venv "$InstallDir\venv"
$pyEx = "$InstallDir\venv\Scripts\python.exe"

# -- Install TechBS and dependencies -------------------------------------------
Write-Host "Installing TechBS (this may take several minutes)..."
& $pyEx -m pip install --upgrade pip --quiet

# PyTorch first: CUDA build if NVIDIA GPU present, otherwise CPU-only
$nvSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if (-not $nvSmi -and (Test-Path "C:\Windows\System32\nvidia-smi.exe")) {
    $nvSmi = "C:\Windows\System32\nvidia-smi.exe"
}
if ($nvSmi) {
    Write-Host "NVIDIA GPU detected -- installing CUDA-enabled PyTorch..."
    & $pyEx -m pip install torch --index-url https://download.pytorch.org/whl/cu128 --quiet
} else {
    Write-Host "No NVIDIA GPU detected -- installing CPU-only PyTorch..."
    & $pyEx -m pip install torch --quiet
}

& $pyEx -m pip install "$SrcDir" --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Error "pip install failed."
    return
}

Remove-Item $ExtractTemp -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $ZipPath -Force -ErrorAction SilentlyContinue

# -- Download the TechBS model -------------------------------------------------
Write-Host ""
Write-Host "Downloading the TechBS model (about 420 MB)..."
& "$InstallDir\venv\Scripts\techbs.exe" --model-pull techbs --yes
if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNING: Could not download the model. TechBS will offer to download it on first run," -ForegroundColor Yellow
    Write-Host "         or run: techbs --model-pull techbs" -ForegroundColor Yellow
}

# -- Register the techbs command -----------------------------------------------
# A small shim in bin\ keeps the venv's python.exe etc. off the PATH.
$BinDir = Join-Path $InstallDir "bin"
New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
Set-Content -Path (Join-Path $BinDir "techbs.cmd") -Encoding ASCII -Value "@`"%~dp0..\venv\Scripts\techbs.exe`" %*"

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not $userPath -or -not (($userPath -split ";") -contains $BinDir)) {
    $newPath = if ($userPath) { "$userPath;$BinDir" } else { $BinDir }
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Host "Added $BinDir to your PATH"
}
$env:Path = "$env:Path;$BinDir"

# -- Done ----------------------------------------------------------------------
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  TechBS installed successfully!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Location:  $InstallDir"
Write-Host "  Command:   techbs"
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Cyan
Write-Host ""
Write-Host "    techbs --file keynote.mp3     # analyze a file"
Write-Host "    techbs --mic                  # analyze live audio"
Write-Host ""
Write-Host "  On first run TechBS asks which Whisper transcription model to use."
Write-Host "  Open a new terminal to use the techbs command." -ForegroundColor Yellow
Write-Host ""
