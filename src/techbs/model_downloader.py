"""
Downloads TechBS model files from HuggingFace.
Called by install.sh / install.ps1 during setup, or run directly.

Queries the HuggingFace API to discover all models published under the
TechBS organization, then downloads any missing files.

Usage:
    python -m techbs.model_downloader                        # download all models
    python -m techbs.model_downloader --model techbs         # download one model
    python -m techbs.model_downloader --models-dir /path/to/models
"""
import argparse
import json
import sys
import urllib.error
from pathlib import Path

from . import hf_repo
from .hf_repo import HF_ORG
from .paths import models_dir


def download_model(model_name: str, models_root: Path, org: str = HF_ORG) -> None:
    repo_id  = f"{org}/{model_name}"
    dest_dir = models_root / model_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    for filename in hf_repo.MODEL_FILES:
        dest = dest_dir / filename
        if dest.exists():
            print(f"  {filename} — already present, skipping.")
            continue

        hook = hf_repo.progress_hook(filename) if filename == "model.safetensors" else None
        print(f"  Downloading {filename}...")
        try:
            hf_repo.download_atomic(hf_repo.file_url(repo_id, filename), dest, reporthook=hook)
            if hook:
                sys.stdout.write("\n")
        except urllib.error.HTTPError as exc:
            if hook:
                sys.stdout.write("\n")
            if exc.code == 404:
                print(f"  {filename} — not found in repo, skipping.")
                continue
            print(f"  ERROR downloading {filename}: {exc}", file=sys.stderr)
            raise SystemExit(1)
        except Exception as exc:
            if hook:
                sys.stdout.write("\n")
            print(f"  ERROR downloading {filename}: {exc}", file=sys.stderr)
            raise SystemExit(1)

    # SHA256 integrity check on weights
    weights   = dest_dir / "model.safetensors"
    info_file = dest_dir / "info.json"
    expected  = None

    if info_file.exists():
        try:
            info     = json.loads(info_file.read_text(encoding="utf-8"))
            expected = info.get("weights_sha256") or info.get("sha256")
        except Exception:
            pass

    if expected and weights.exists():
        actual = hf_repo.sha256_file(weights)
        if actual != expected:
            weights.unlink()
            print(f"  ERROR: SHA256 mismatch for model.safetensors — file deleted.", file=sys.stderr)
            print(f"  Expected: {expected}", file=sys.stderr)
            print(f"  Got:      {actual}", file=sys.stderr)
            raise SystemExit(1)
        print(f"  Integrity verified.")

    print(f"  Model '{model_name}' ready.")


def main():
    parser = argparse.ArgumentParser(description="Download TechBS models from HuggingFace")
    parser.add_argument("--model",      default=None,   help="Model name to download (default: all available)")
    parser.add_argument("--org",        default=HF_ORG, help=f"HuggingFace organization (default: {HF_ORG})")
    parser.add_argument("--models-dir", default=None,   help="Path to models directory")
    args = parser.parse_args()

    models_root = Path(args.models_dir) if args.models_dir else models_dir()

    if args.model:
        models = [args.model]
    else:
        print(f"Querying HuggingFace for models under '{args.org}'...")
        try:
            models = hf_repo.list_org_model_names(args.org)
        except Exception as exc:
            print(f"ERROR: Could not query HuggingFace API: {exc}", file=sys.stderr)
            raise SystemExit(1)

    if not models:
        print("No models found.")
        return

    print(f"Found {len(models)} model(s): {', '.join(models)}")
    for model_name in models:
        print(f"\nModel: {model_name}")
        download_model(model_name, models_root, org=args.org)


if __name__ == "__main__":
    main()
