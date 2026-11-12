"""Shared HuggingFace model-repo helpers.

Both the installer-time downloader (model_downloader.py) and the runtime
updater (model_updater.py) pull TechBS models from the same HuggingFace org.
This module holds everything they have in common — the repo constants, the
file manifest, the progress hook, hashing, and the low-level HTTP helpers — so
the two can't drift apart.
"""
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

HF_ORG  = "techbsai"
HF_API  = "https://huggingface.co/api"
HF_BASE = "https://huggingface.co"

# Files that make up a model, weights last (they're the largest).
MODEL_FILES = [
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "buzzwords.json",
    "info.json",
    "model.safetensors",
]


def progress_hook(label: str):
    """Return a urlretrieve reporthook that draws a one-line progress bar."""
    def hook(count, block_size, total_size):
        if total_size <= 0:
            mb = count * block_size / 1_048_576
            sys.stdout.write(f"\r  {label}  {mb:.1f} MB")
        else:
            pct = min(100, int(count * block_size * 100 / total_size))
            mb_done = count * block_size / 1_048_576
            mb_total = total_size / 1_048_576
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            sys.stdout.write(f"\r  {label}  [{bar}] {pct:3d}%  {mb_done:.0f}/{mb_total:.0f} MB")
        sys.stdout.flush()
    return hook


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def file_url(repo_id: str, filename: str) -> str:
    """Resolve URL for a single file in a HuggingFace repo's main branch."""
    return f"{HF_BASE}/{repo_id}/resolve/main/{filename}"


def list_org_model_names(org: str = HF_ORG, timeout: int = 15) -> list[str]:
    """Return the repo names (without the org prefix) published under *org*.

    Raises urllib.error.URLError on network failure.
    """
    url = f"{HF_API}/models?author={org}"
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return [m["id"].split("/")[-1] for m in data if m.get("id")]


def fetch_info_json(repo_id: str, timeout: int = 10) -> dict | None:
    """Fetch and parse info.json from a repo, or None if it can't be retrieved."""
    try:
        with urllib.request.urlopen(file_url(repo_id, "info.json"), timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def download_atomic(url: str, dest: Path, reporthook=None) -> None:
    """Download *url* to a temp file, then atomically replace *dest*.

    Cleans up the temp file and re-raises on failure so a partial download
    never masquerades as a complete one.
    """
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        urllib.request.urlretrieve(url, tmp, reporthook=reporthook)
        tmp.replace(dest)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise
