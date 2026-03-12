#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo "ERROR: Virtual environment not found. Run install.sh first."
    exit 1
fi

source "$SCRIPT_DIR/venv/bin/activate"
python "$SCRIPT_DIR/app/main.py" "$@"
