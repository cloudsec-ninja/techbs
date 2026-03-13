from pathlib import Path

def get_version() -> str:
    try:
        return (Path(__file__).parent.parent / "VERSION").read_text().strip()
    except FileNotFoundError:
        return "unknown"

VERSION = get_version()
