#!/usr/bin/env bash
set -e

# ── Azure model storage ───────────────────────────────────────────────────────
# Replace the value below with your full Azure Blob container URL including
# the embedded SAS token before distributing.
#   e.g. https://mystorageaccount.blob.core.windows.net/cyberbs-models?sv=2022-11-02&ss=b&sp=rl&sig=XXXXX
AZURE_MODEL_URL="https://ddffrrrsseee.blob.core.windows.net/models?sp=r&st=2026-03-14T18:13:10Z&se=2026-04-01T02:28:10Z&spr=https&sv=2024-11-04&sr=c&sig=E0TDvGmNUYCNW9MeW8KgAsI6JMk9BmI66EkisaIQIFQ%3D"
# ─────────────────────────────────────────────────────────────────────────────

echo "=== TechBS Installer ==="

# Check Python 3.10+
PYTHON=$(command -v python3 || command -v python)
if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.10 or higher is required."
    echo "Install from https://www.python.org/downloads/"
    exit 1
fi

MAJOR=$($PYTHON -c "import sys; print(sys.version_info.major)")
MINOR=$($PYTHON -c "import sys; print(sys.version_info.minor)")
VERSION="$MAJOR.$MINOR"
if [ "$MAJOR" -lt 3 ] || { [ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 10 ]; }; then
    echo "ERROR: Python 3.10+ required. Found $VERSION."
    exit 1
fi
echo "Python $VERSION found."

# Check ffmpeg (required by Whisper for audio decoding)
if ! command -v ffmpeg &> /dev/null; then
    echo ""
    echo "ERROR: ffmpeg not found. Whisper requires ffmpeg to decode audio files."
    echo "Install it before running the app:"
    echo "  macOS:   brew install ffmpeg"
    echo "  Ubuntu:  sudo apt install ffmpeg"
    echo ""
    exit 1
fi

# Install PortAudio on Linux if needed (required by sounddevice for --mic)
if [[ "$(uname)" == "Linux" ]]; then
    if ! ldconfig -p 2>/dev/null | grep -q libportaudio; then
        echo "Installing libportaudio2 (required for --mic)..."
        sudo apt-get install -y libportaudio2 2>/dev/null || \
            echo "WARNING: Could not install libportaudio2. Run: sudo apt install libportaudio2"
    fi
fi

# Create virtual environment
echo "Creating virtual environment..."
$PYTHON -m venv venv

# Activate and install dependencies
echo "Installing dependencies (this may take several minutes)..."
source venv/bin/activate
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

# Pre-cache the Whisper base model so first run is instant
echo "Downloading Whisper base model..."
python -c "import whisper; whisper.load_model('base'); print('Whisper model cached.')"

# Download TechBS model weights from Azure
if [ "$AZURE_MODEL_URL" = "REPLACE_WITH_AZURE_URL" ]; then
    echo ""
    echo "WARNING: Azure model URL not configured in installer."
    echo "         Models must be placed in the models/ folder manually."
else
    echo "Downloading TechBS models from Azure..."
    python app/model_downloader.py \
        --url "$AZURE_MODEL_URL" \
        --models-dir models
fi

deactivate

echo ""
echo "Installation complete. Run the app with: ./techbs.sh"
