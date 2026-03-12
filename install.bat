@echo off
echo === CyberBS Installer ===

REM Check Python
where python >nul 2>&1
if errorlevel 1 (`
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

REM Check ffmpeg
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo ffmpeg not found. Attempting to install...
    where winget >nul 2>&1
    if not errorlevel 1 (
        winget install --id Gyan.FFmpeg -e --silent
        goto ffmpeg_done
    )
    where choco >nul 2>&1
    if not errorlevel 1 (
        choco install ffmpeg -y
        goto ffmpeg_done
    )
    echo ERROR: Could not install ffmpeg automatically.
    echo Install manually from https://ffmpeg.org/download.html and add it to your PATH.
    pause
    exit /b 1
    :ffmpeg_done
    echo ffmpeg installed.
) else (
    echo ffmpeg found.
)

echo Creating virtual environment...
python -m venv venv

echo Installing dependencies (this may take several minutes)...
call venv\Scripts\activate.bat
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

echo Downloading Whisper base model...
python -c "import whisper; whisper.load_model('base'); print('Whisper model cached.')"

call deactivate
echo.
echo Installation complete. Run the app with: run.bat
pause
