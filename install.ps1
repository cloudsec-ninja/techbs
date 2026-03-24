#Requires -Version 5.1
<#
.SYNOPSIS
    TechBS web installer for Windows.
.DESCRIPTION
    Downloads the latest TechBS release, extracts it, creates a Python virtual
    environment, and installs all dependencies.
.NOTES
    Usage:  irm https://techbs.ai/install.ps1 | iex

    If execution policy blocks this script, run once from an admin PowerShell:
        Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
#>

$ErrorActionPreference = "Stop"

# Detect uninstall: set $env:TECHBS_UNINSTALL=1 before piping, or pass -Uninstall as arg
$Uninstall = ($args -contains "-Uninstall") -or ($env:TECHBS_UNINSTALL -eq "1")

$GitHubRepo     = "cloudsec-ninja/techbs"
$GitHubApi      = "https://api.github.com/repos/$GitHubRepo/releases/latest"
$DefaultInstall = Join-Path $env:USERPROFILE "techbs"

Write-Host ""
Write-Host "+==========================================+" -ForegroundColor Cyan
Write-Host "|        TechBS Installer                  |" -ForegroundColor Cyan
Write-Host "|        Cut through the BS.               |" -ForegroundColor Cyan
Write-Host "+==========================================+" -ForegroundColor Cyan
Write-Host ""

# -- Uninstall ----------------------------------------------------------------
if ($Uninstall) {
    Write-Host "Uninstalling TechBS..." -ForegroundColor Cyan

    $techbsCmd = Get-Command techbs -ErrorAction SilentlyContinue
    if ($techbsCmd) {
        $cmdPath = $techbsCmd.Source
        Remove-Item $cmdPath -Force -ErrorAction SilentlyContinue
        Write-Host "Removed $cmdPath" -ForegroundColor Green
    }

    if (Test-Path $DefaultInstall) {
        Remove-Item $DefaultInstall -Recurse -Force
        Write-Host "Removed $DefaultInstall" -ForegroundColor Green
    }

    # Remove from user PATH
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -like "*$DefaultInstall*") {
        $newPath = ($userPath -split ";" | Where-Object { $_ -ne $DefaultInstall }) -join ";"
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-Host "Removed from PATH" -ForegroundColor Green
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

# -- Visual C++ Redistributable ------------------------------------------------
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

# -- Microsoft Visual C++ Redistributable (required by PyTorch) ----------------
$vcInstalled = Test-Path "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
if (-not $vcInstalled) {
    $vcInstalled = (Get-ChildItem "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall" -ErrorAction SilentlyContinue |
        Get-ItemProperty | Where-Object { $_.DisplayName -like "*Visual C++*Redistributable*x64*" }) -ne $null
}
if (-not $vcInstalled) {
    Write-Host ""
    Write-Host "WARNING: Microsoft Visual C++ Redistributable (x64) not detected." -ForegroundColor Yellow
    Write-Host "PyTorch requires this to run. Install it from:" -ForegroundColor Yellow
    Write-Host "  https://aka.ms/vs/17/release/vc_redist.x64.exe" -ForegroundColor Cyan
    Write-Host ""
    $vcContinue = Read-Host "Continue anyway? [y/N]"
    if ($vcContinue -notin @("y", "Y")) {
        Write-Host "Install the Visual C++ Redistributable and re-run this installer."
        Read-Host "Press Enter to exit"
        return
    }
}

# -- Choose install directory --------------------------------------------------
Write-Host ""
$InstallDir = Read-Host "Install directory [$DefaultInstall]"
if ([string]::IsNullOrWhiteSpace($InstallDir)) {
    $InstallDir = $DefaultInstall
}

if ((Test-Path $InstallDir) -and (Get-ChildItem $InstallDir -Force | Measure-Object).Count -gt 0) {
    $overwrite = Read-Host "Directory $InstallDir already exists and is not empty. Overwrite? [y/N]"
    if ($overwrite -notin @("y", "Y")) {
        Write-Host "Installation cancelled."
        return
    }
}

New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null

# -- Fetch latest release URL from GitHub --------------------------------------
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

# -- Download and extract ------------------------------------------------------
Write-Host "Downloading TechBS..."

$ZipPath = Join-Path $env:TEMP "techbs-download.zip"
try {
    Invoke-WebRequest -Uri $ReleaseUrl -OutFile $ZipPath -UseBasicParsing
} catch {
    Write-Error "Download failed: $_"
    return
}

Write-Host "Extracting to $InstallDir..."

# Extract to a temp dir first so we can strip the top-level folder
$ExtractTemp = Join-Path $env:TEMP "techbs-extract"
if (Test-Path $ExtractTemp) { Remove-Item $ExtractTemp -Recurse -Force }
Expand-Archive -Path $ZipPath -DestinationPath $ExtractTemp -Force

# Find the inner folder (the archive wraps files in a single top-level dir)
$inner = Get-ChildItem $ExtractTemp -Directory | Select-Object -First 1
if ($inner) {
    Get-ChildItem $inner.FullName -Force | Move-Item -Destination $InstallDir -Force
} else {
    Get-ChildItem $ExtractTemp -Force | Move-Item -Destination $InstallDir -Force
}

Remove-Item $ExtractTemp -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $ZipPath -Force -ErrorAction SilentlyContinue

# -- Virtual environment -------------------------------------------------------
Write-Host ""
Write-Host "Creating virtual environment..."
if (-not (Test-Path "$InstallDir\venv")) {
    & python -m venv "$InstallDir\venv"
}

$pip  = "$InstallDir\venv\Scripts\pip.exe"
$pyEx = "$InstallDir\venv\Scripts\python.exe"

# -- Dependencies --------------------------------------------------------------
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

& $pip install -r "$InstallDir\requirements.txt" --quiet

# -- Whisper base model --------------------------------------------------------
Write-Host "Downloading Whisper base model..."
try {
    & $pyEx -c "import whisper; whisper.load_model('base'); print('Whisper model cached.')"
} catch {
    Write-Host "WARNING: Could not pre-cache Whisper model. It will download on first run." -ForegroundColor Yellow
}

# -- Done ----------------------------------------------------------------------
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  TechBS installed successfully!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Location:  $InstallDir"
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Cyan
Write-Host ""
Write-Host "    1. Pull a model:"
Write-Host "       cd $InstallDir"
Write-Host "       .\techbs.ps1 --model-list          # see available models"
Write-Host "       .\techbs.ps1 --model-pull cyberbs  # download a model"
Write-Host ""
Write-Host "    2. Run TechBS:"
Write-Host "       .\techbs.ps1 --file keynote.mp3"
Write-Host "       .\techbs.ps1 --mic"
Write-Host ""

# PATH hint
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$InstallDir*") {
    Write-Host "  Tip: Add TechBS to your PATH for easy access:" -ForegroundColor Yellow
    Write-Host "    `$env:Path += `";$InstallDir`""
    Write-Host "    [Environment]::SetEnvironmentVariable('Path', `$env:Path + ';$InstallDir', 'User')"
    Write-Host ""
}
