"""Persistent user preferences (config.json in paths.config_dir())."""
import json
from pathlib import Path

from .paths import config_file


def load_config(path: Path | None = None) -> dict:
    path = path or config_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_config(updates: dict, path: Path | None = None) -> Path:
    """Merge *updates* into the saved config and write it back."""
    path = path or config_file()
    data = load_config(path)
    data.update(updates)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path
