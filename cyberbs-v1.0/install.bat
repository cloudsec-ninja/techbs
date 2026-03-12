@echo off
echo === CyberBS Installer ===

REM Check Python
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found.
    echo Install Python 3.10+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Check version
python -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)" 2>nul
if errorlevel 1 (
    echo ERROR: Python 3.10 or higher is required.
    pause
    exit /b 1
)

REM Check ffmpeg — hard requirement, Whisper cannot decode audio without it
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: ffmpeg is not installed or not in your PATH.
    echo CyberBS cannot decode audio files without ffmpeg.
    echo.
    echo  1. Download ffmpeg for Windows:
    echo     https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
    echo  2. Extract and copy ffmpeg.exe to a folder, e.g. C:\ffmpeg\bin\
    echo  3. Add that folder to your system PATH:
    echo     Settings - System - Advanced system settings - Environment Variables
    echo     Edit "Path" under System variables, add C:\ffmpeg\bin
    echo  4. Re-run this installer.
    echo.
    pause
    exit /b 1
)

echo Creating virtual environment...
python -m venv venv

echo Installing dependencies (this may take several minutes)...
call venv\Scripts\activate.bat
pip install --upgrade pip --quiet

REM Install PyTorch with CUDA if an NVIDIA GPU is present, otherwise CPU-only
nvidia-smi >nul 2>&1
if not errorlevel 1 (
    echo NVIDIA GPU detected -- installing CUDA-enabled PyTorch...
    pip install torch torchvision torchaudio --index-url pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu126 --quiet
) else (
    echo No NVIDIA GPU detected -- installing CPU-only PyTorch...
    pip install torch torchvision torchaudio --quiet
)

REM Install remaining dependencies (torch already satisfied above)
pip install -r requirements.txt --quiet

echo Downloading Whisper base model...
python -c "import whisper; whisper.load_model('base'); print('Whisper model cached.')"

call deactivate
echo.
echo Installation complete. Run the app with: run.bat
pause
