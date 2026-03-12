#!/usr/bin/env bash
set -e

echo "=== CyberBS Installer ==="

# Check Python 3.10+
PYTHON=$(command -v python3 || command -v python)
if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.10 or higher is required."
    echo "Install from https://www.python.org/downloads/"
    exit 1
fi

VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
MAJOR=$($PYTHON -c "import sys; print(sys.version_info.major)")
MINOR=$($PYTHON -c "import sys; print(sys.version_info.minor)")
if [ "$MAJOR" -lt 3 ] || { [ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 10 ]; }; then
    echo "ERROR: Python 3.10+ required. Found $VERSION."
    exit 1
fi
echo "Python $VERSION found."

# Check ffmpeg (required by Whisper for audio decoding)
if ! command -v ffmpeg &> /dev/null; then
    echo ""
    echo "WARNING: ffmpeg not found. Whisper requires ffmpeg to decode audio files."
    echo "Install it before running the app:"
    echo "  macOS:   brew install ffmpeg"
    echo "  Ubuntu:  sudo apt install ffmpeg"
    echo ""
fi

# Create virtual environment
echo "Creating virtual environment..."
$PYTHON -m venv venv

# Activate and install dependencies
echo "Installing dependencies (this may take several minutes)..."
source venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

# Pre-cache the Whisper base model so first run is instant
echo "Downloading Whisper base model..."
python -c "import whisper; whisper.load_model('base'); print('Whisper model cached.')"

deactivate
echo ""
echo "Installation complete. Run the app with: ./run.sh"
