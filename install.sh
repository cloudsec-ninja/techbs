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

# ── LLM summary preference ────────────────────────────────────────────────────
echo ""
echo "Configure LLM provider for --summarize? (run installer again to change) [y/N]: "
read -r LLM_CHOICE
if [[ "$LLM_CHOICE" =~ ^[Yy]$ ]]; then
    echo ""
    echo "Select LLM provider:"
    echo "  1) Ollama  (local, free — requires Ollama installed separately)"
    echo "  2) Claude  (cloud  — requires ANTHROPIC_API_KEY env var)"
    echo "  3) OpenAI  (cloud  — requires OPENAI_API_KEY env var)"
    echo "  4) Gemini  (cloud  — requires GOOGLE_API_KEY env var)"
    echo ""
    read -r -p "Choice [1-4]: " PROVIDER_CHOICE
    case "$PROVIDER_CHOICE" in
        1) LLM_PROVIDER="ollama" ;;
        2) LLM_PROVIDER="claude" ;;
        3) LLM_PROVIDER="openai" ;;
        4) LLM_PROVIDER="gemini" ;;
        *) LLM_PROVIDER="" ;;
    esac

    if [ -n "$LLM_PROVIDER" ]; then
        echo ""
        # ── Model selection ──
        if [ "$LLM_PROVIDER" = "ollama" ]; then
            OLLAMA_JSON=$(curl -sf --max-time 2 http://localhost:11434/api/tags 2>/dev/null)
            if [ -n "$OLLAMA_JSON" ]; then
                echo "Available Ollama models:"
                echo "$OLLAMA_JSON" | python3 -c "
import json,sys
data=json.load(sys.stdin)
models=data.get('models',[])
for i,m in enumerate(models,1):
    print(f'  {i}) {m[\"name\"]}')
" 2>/dev/null
                echo ""
                read -r -p "Model [number or name]: " RAW
                LLM_MODEL=$(echo "$OLLAMA_JSON" | python3 -c "
import json,sys
data=json.load(sys.stdin)
models=data.get('models',[])
raw='$RAW'.strip()
try:
    n=int(raw)-1
    print(models[n]['name'] if 0<=n<len(models) else raw)
except:
    print(raw)
" 2>/dev/null || echo "$RAW")
            else
                echo "Ollama not detected — enter model name manually."
                echo "Examples: llama3.2  mistral  qwen3:mcp  phi4"
                read -r -p "Model name: " LLM_MODEL
            fi
        elif [ "$LLM_PROVIDER" = "claude" ]; then
            read -r -p "Claude model [claude-sonnet-4-6]: " LLM_MODEL
            LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-6}"
        elif [ "$LLM_PROVIDER" = "openai" ]; then
            read -r -p "OpenAI model [gpt-4o]: " LLM_MODEL
            LLM_MODEL="${LLM_MODEL:-gpt-4o}"
        elif [ "$LLM_PROVIDER" = "gemini" ]; then
            read -r -p "Gemini model [gemini-2.0-flash]: " LLM_MODEL
            LLM_MODEL="${LLM_MODEL:-gemini-2.0-flash}"
        fi

        mkdir -p "$HOME/.techbs"
        printf '{"provider":"%s","model":"%s"}\n' "$LLM_PROVIDER" "$LLM_MODEL" \
            > "$HOME/.techbs/llm_config.json"
        echo "Saved: $LLM_PROVIDER / $LLM_MODEL"

        # Install the provider's Python package into the venv
        case "$LLM_PROVIDER" in
            claude)
                echo "Installing anthropic package..."
                source venv/bin/activate
                pip install anthropic --quiet
                deactivate ;;
            openai)
                echo "Installing openai package..."
                source venv/bin/activate
                pip install openai --quiet
                deactivate ;;
            gemini)
                echo "Installing google-genai package..."
                source venv/bin/activate
                pip install google-genai --quiet
                deactivate ;;
        esac

        case "$LLM_PROVIDER" in
            ollama) echo "Make sure Ollama is installed (https://ollama.com) and the model is pulled." ;;
            claude) echo "Set ANTHROPIC_API_KEY in your environment before using --summarize." ;;
            openai) echo "Set OPENAI_API_KEY in your environment before using --summarize." ;;
            gemini) echo "Set GOOGLE_API_KEY in your environment before using --summarize." ;;
        esac
    fi
fi

echo ""
echo "Installation complete. Run the app with: ./run.sh"
