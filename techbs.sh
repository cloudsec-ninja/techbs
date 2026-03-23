#!/usr/bin/env bash

# Resolve symlinks so SCRIPT_DIR always points to the real install directory
SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
    SOURCE="$(readlink "$SOURCE")"
done
SCRIPT_DIR="$(cd "$(dirname "$SOURCE")" && pwd)"

if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo "ERROR: Virtual environment not found. Run the installer first:"
    echo "  curl -fsSL https://techbs.ai/install.sh | bash"
    exit 1
fi

source "$SCRIPT_DIR/venv/bin/activate"
python "$SCRIPT_DIR/app/main.py" "$@"
