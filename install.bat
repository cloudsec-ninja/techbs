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

REM Check ffmpeg
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo.
    echo WARNING: ffmpeg not found. Whisper requires ffmpeg to decode audio files.
    echo Download from https://ffmpeg.org/download.html and add it to your PATH.
    echo.
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
