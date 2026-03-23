#!/usr/bin/env bash
set -e

# ── TechBS Web Installer (macOS / Linux) ─────────────────────────────────────
# Downloads the latest TechBS release from GitHub, extracts it, creates a
# virtual environment, and installs all Python dependencies.
#
# Usage:
#   curl -fsSL https://techbs.ai/install.sh | bash
# ─────────────────────────────────────────────────────────────────────────────

GITHUB_REPO="cloudsec-ninja/techbs"
GITHUB_API="https://api.github.com/repos/$GITHUB_REPO/releases/latest"
DEFAULT_INSTALL_DIR="$HOME/techbs"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║        TechBS Installer                  ║"
echo "║        Cut through the BS.               ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── Check Python 3.10+ ───────────────────────────────────────────────────────
PYTHON=$(command -v python3 || command -v python || true)
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

# ── Check ffmpeg ─────────────────────────────────────────────────────────────
if ! command -v ffmpeg &> /dev/null; then
    echo ""
    echo "ERROR: ffmpeg not found. TechBS requires ffmpeg to decode audio."
    echo "Install it before running the installer:"
    echo "  macOS:   brew install ffmpeg"
    echo "  Ubuntu:  sudo apt install ffmpeg"
    echo ""
    exit 1
fi
echo "ffmpeg found."

# ── Install PortAudio on Linux if needed ─────────────────────────────────────
if [[ "$(uname)" == "Linux" ]]; then
    if ! ldconfig -p 2>/dev/null | grep -q libportaudio; then
        echo "Installing libportaudio2 (required for --mic)..."
        sudo apt-get install -y libportaudio2 2>/dev/null || \
            echo "WARNING: Could not install libportaudio2. Run: sudo apt install libportaudio2"
    fi
fi

# ── Choose install directory ─────────────────────────────────────────────────
echo ""
echo "Where would you like to install TechBS?"
printf "Install directory [%s]: " "$DEFAULT_INSTALL_DIR"

# When piped from curl, stdin is the script itself — reattach the terminal
if [ -t 0 ]; then
    read -r INSTALL_DIR
else
    read -r INSTALL_DIR < /dev/tty || true
fi

INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"

# Expand ~ if the user typed it
INSTALL_DIR="${INSTALL_DIR/#\~/$HOME}"

if [ -d "$INSTALL_DIR" ] && [ "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]; then
    echo ""
    printf "Directory %s already exists and is not empty. Overwrite? [y/N]: " "$INSTALL_DIR"
    if [ -t 0 ]; then
        read -r OVERWRITE
    else
        read -r OVERWRITE < /dev/tty || true
    fi
    if [[ ! "$OVERWRITE" =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi
fi

mkdir -p "$INSTALL_DIR"

# ── Fetch latest release URL from GitHub ─────────────────────────────────────
echo ""
echo "Fetching latest release from GitHub..."

if command -v curl &> /dev/null; then
    RELEASE_URL=$(curl -fsSL "$GITHUB_API" | grep '"tarball_url"' | cut -d'"' -f4)
elif command -v wget &> /dev/null; then
    RELEASE_URL=$(wget -qO- "$GITHUB_API" | grep '"tarball_url"' | cut -d'"' -f4)
else
    echo "ERROR: curl or wget is required to download TechBS."
    exit 1
fi

if [ -z "$RELEASE_URL" ]; then
    echo "ERROR: Could not fetch release info from GitHub. Check your internet connection."
    exit 1
fi

# ── Download and extract ─────────────────────────────────────────────────────
echo "Downloading TechBS..."

TMPFILE=$(mktemp /tmp/techbs-XXXXXX.tar.gz)
trap 'rm -f "$TMPFILE"' EXIT

if command -v curl &> /dev/null; then
    curl -fSL --progress-bar "$RELEASE_URL" -o "$TMPFILE"
else
    wget -q --show-progress -O "$TMPFILE" "$RELEASE_URL"
fi

echo "Extracting to $INSTALL_DIR..."
tar -xzf "$TMPFILE" -C "$INSTALL_DIR" --strip-components=1

# ── Create virtual environment ───────────────────────────────────────────────
echo ""
echo "Creating virtual environment..."
$PYTHON -m venv "$INSTALL_DIR/venv"

# ── Install dependencies ─────────────────────────────────────────────────────
echo "Installing dependencies (this may take several minutes)..."
source "$INSTALL_DIR/venv/bin/activate"
python -m pip install --upgrade pip --quiet
pip install -r "$INSTALL_DIR/requirements.txt" --quiet

# ── Pre-cache Whisper base model ─────────────────────────────────────────────
echo "Downloading Whisper base model..."
python -c "import whisper; whisper.load_model('base'); print('Whisper model cached.')"

deactivate

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════"
echo "  TechBS installed successfully!"
echo "════════════════════════════════════════════"
echo ""
echo "  Location:  $INSTALL_DIR"
echo ""
echo "  Next steps:"
echo ""
echo "    1. Pull a model:"
echo "       cd $INSTALL_DIR"
echo "       ./techbs.sh --model-list          # see available models"
echo "       ./techbs.sh --model-pull cyberbs3  # download a model"
echo ""
echo "    2. Run TechBS:"
echo "       ./techbs.sh --file keynote.mp3"
echo "       ./techbs.sh --mic"
echo ""

# Add to PATH hint
SHELL_NAME=$(basename "$SHELL" 2>/dev/null || echo "bash")
case "$SHELL_NAME" in
    zsh)  RC_FILE="$HOME/.zshrc" ;;
    bash) RC_FILE="$HOME/.bashrc" ;;
    *)    RC_FILE="$HOME/.profile" ;;
esac

if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    echo "  Tip: Add TechBS to your PATH for easy access:"
    echo "    echo 'export PATH=\"$INSTALL_DIR:\$PATH\"' >> $RC_FILE"
    echo ""
fi
