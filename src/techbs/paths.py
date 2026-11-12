"""Where TechBS keeps its data (downloaded models).

Resolution order for the data home:
  1. $TECHBS_HOME, if set
  2. A source checkout's repo root, if it has a models/ folder (dev mode)
  3. The per-user data folder for the platform:
       Linux/macOS: $XDG_DATA_HOME/techbs  (default ~/.local/share/techbs)
       Windows:     %LOCALAPPDATA%\\techbs

Models live in <data home>/models. Keeping them outside the install means a
reinstall or upgrade never deletes downloaded weights.
"""
import os
import sys
from pathlib import Path

APP_NAME = "techbs"


def _source_checkout_root() -> Path | None:
    """Repo root when running from a source checkout with a models/ folder."""
    root = Path(__file__).resolve().parents[2]
    if (root / "pyproject.toml").is_file() and (root / "models").is_dir():
        return root
    return None


def _platform_data_home() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_NAME
    # Linux and macOS share the XDG layout (matches install.sh)
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME


def data_home() -> Path:
    env = os.environ.get("TECHBS_HOME")
    if env:
        return Path(env).expanduser()
    return _source_checkout_root() or _platform_data_home()


def models_dir() -> Path:
    return data_home() / "models"


def config_dir() -> Path:
    """User preferences. Unlike data_home(), a source checkout does not change
    this, so dev and installed copies share the same settings."""
    env = os.environ.get("TECHBS_HOME")
    if env:
        return Path(env).expanduser()
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_NAME


def config_file() -> Path:
    return config_dir() / "config.json"
