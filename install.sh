#!/usr/bin/env bash
set -e

# ── TechBS Web Installer (macOS / Linux) ─────────────────────────────────────
# Downloads the latest TechBS release from GitHub, installs to the standard
# user-local location, and registers the `techbs` command in your PATH.
#
# Usage:
#   curl -fsSL https://techbs.ai/install.sh | bash
# ─────────────────────────────────────────────────────────────────────────────

GITHUB_REPO="cloudsec-ninja/techbs"
GITHUB_API="https://api.github.com/repos/$GITHUB_REPO/releases/latest"
INSTALL_DIR="$HOME/.local/share/techbs"
BIN_DIR="$HOME/.local/bin"
BIN_LINK="$BIN_DIR/techbs"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║        TechBS Installer                  ║"
echo "║        Cut through the BS.               ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── Uninstall ─────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--uninstall" ]]; then
    echo "Uninstalling TechBS..."

    if [ -L "$BIN_LINK" ]; then
        rm "$BIN_LINK"
        echo "✓ Removed $BIN_LINK"
    fi

    if [ -d "$INSTALL_DIR" ]; then
        rm -rf "$INSTALL_DIR"
        echo "✓ Removed $INSTALL_DIR"
    fi

    if [ ! -L "$BIN_LINK" ] && [ ! -d "$INSTALL_DIR" ]; then
        echo ""
        echo "TechBS has been uninstalled."
        echo "You may also remove the PATH line added to your shell rc file:"
        echo "  # Added by TechBS installer"
        echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi
    exit 0
fi

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
echo "✓ Python $VERSION"

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
echo "✓ ffmpeg"

# ── Install PortAudio on Linux if needed (required for --mic) ─────────────────
if [[ "$(uname)" == "Linux" ]]; then
    if ! ldconfig -p 2>/dev/null | grep -q libportaudio; then
        echo "Installing libportaudio2 (required for --mic)..."
        sudo apt-get install -y libportaudio2 2>/dev/null || \
            echo "WARNING: Could not install libportaudio2. Run: sudo apt install libportaudio2"
    fi
fi

# ── Handle existing install ───────────────────────────────────────────────────
if [ -d "$INSTALL_DIR" ] && [ "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]; then
    echo ""
    echo "TechBS is already installed at $INSTALL_DIR."
    printf "Reinstall / update? [y/N]: "
    if [ -t 0 ]; then
        read -r CONFIRM
    else
        read -r CONFIRM < /dev/tty || true
    fi
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi
    rm -rf "$INSTALL_DIR"
fi

mkdir -p "$INSTALL_DIR"

# ── Fetch latest release from GitHub ─────────────────────────────────────────
echo ""
echo "Fetching latest release from GitHub..."

if command -v curl &> /dev/null; then
    RELEASE_URL=$(curl -fsSL "$GITHUB_API" | grep '"tarball_url"' | cut -d'"' -f4)
elif command -v wget &> /dev/null; then
    RELEASE_URL=$(wget -qO- "$GITHUB_API" | grep '"tarball_url"' | cut -d'"' -f4)
else
    echo "ERROR: curl or wget is required."
    exit 1
fi

if [ -z "$RELEASE_URL" ]; then
    echo "ERROR: Could not fetch release info from GitHub. Check your internet connection."
    exit 1
fi

# ── Download and extract ──────────────────────────────────────────────────────
echo "Downloading TechBS..."

TMPFILE=$(mktemp /tmp/techbs-XXXXXX.tar.gz)
trap 'rm -f "$TMPFILE"' EXIT

if command -v curl &> /dev/null; then
    curl -fSL --progress-bar "$RELEASE_URL" -o "$TMPFILE"
else
    wget -q --show-progress -O "$TMPFILE" "$RELEASE_URL"
fi

echo "Extracting..."
tar -xzf "$TMPFILE" -C "$INSTALL_DIR" --strip-components=1

# ── Create virtual environment ────────────────────────────────────────────────
echo ""
echo "Creating virtual environment..."
$PYTHON -m venv "$INSTALL_DIR/venv"

# ── Install dependencies ──────────────────────────────────────────────────────
echo "Installing dependencies (this may take a few minutes)..."
source "$INSTALL_DIR/venv/bin/activate"
python -m pip install --upgrade pip --quiet

# Install PyTorch — CUDA build if NVIDIA GPU detected, CPU-only otherwise
if command -v nvidia-smi &> /dev/null; then
    echo "NVIDIA GPU detected — installing CUDA-enabled PyTorch..."
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128 --quiet
else
    echo "No NVIDIA GPU detected — installing CPU-only PyTorch..."
    pip install torch torchvision --quiet
fi

pip install -r "$INSTALL_DIR/requirements.txt" --quiet

# ── Pre-cache Whisper base model ──────────────────────────────────────────────
echo "Downloading Whisper base model..."
python -c "import whisper; whisper.load_model('base'); print('✓ Whisper model cached.')"

deactivate

# ── Register the techbs command ───────────────────────────────────────────────
mkdir -p "$BIN_DIR"
ln -sf "$INSTALL_DIR/techbs.sh" "$BIN_LINK"
chmod +x "$INSTALL_DIR/techbs.sh"

# ── Ensure ~/.local/bin is in PATH ────────────────────────────────────────────
SHELL_NAME=$(basename "$SHELL" 2>/dev/null || echo "bash")
case "$SHELL_NAME" in
    zsh)  RC_FILE="$HOME/.zshrc" ;;
    bash) RC_FILE="$HOME/.bashrc" ;;
    *)    RC_FILE="$HOME/.profile" ;;
esac

PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo "" >> "$RC_FILE"
    echo "# Added by TechBS installer" >> "$RC_FILE"
    echo "$PATH_LINE" >> "$RC_FILE"
    export PATH="$BIN_DIR:$PATH"
    echo "✓ Added ~/.local/bin to PATH in $RC_FILE"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════"
echo "  TechBS installed successfully!"
echo "════════════════════════════════════════════"
echo ""
echo "  Installed to:  $INSTALL_DIR"
echo "  Command:       techbs"
echo ""
echo "  Next steps:"
echo ""
echo "    techbs --model-list           # see available models"
echo "    techbs --model-pull cyberbs   # download a model"
echo "    techbs --file keynote.mp3     # analyze a file"
echo "    techbs --mic                  # analyze live audio"
echo ""
echo "  Restart your terminal (or run: source $RC_FILE) to use the techbs command."
echo ""
