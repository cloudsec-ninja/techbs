"""
Downloads TechBS model files from HuggingFace.
Called by install.sh / install.ps1 during setup, or run directly.

Queries the HuggingFace API to discover all models published under the
TechBS organization, then downloads any missing files.

Usage:
    python model_downloader.py                        # download all models
    python model_downloader.py --model cyberbs        # download one model
    python model_downloader.py --models-dir /path/to/models
"""
import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

HF_ORG  = "techbsai"
HF_API  = "https://huggingface.co/api"
HF_BASE = "https://huggingface.co"

# Files required for inference (weights last — they're the largest)
MODEL_FILES = [
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "buzzwords.json",
    "info.json",
    "model.safetensors",
]


def _progress(label: str):
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


def list_hf_models(org: str = HF_ORG) -> list[str]:
    """Return model repo names published under the given HuggingFace org."""
    url = f"{HF_API}/models?author={org}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return [m["id"].split("/")[-1] for m in data]
    except Exception as exc:
        print(f"ERROR: Could not query HuggingFace API: {exc}", file=sys.stderr)
        raise SystemExit(1)


def download_model(model_name: str, models_root: Path, org: str = HF_ORG) -> None:
    repo_id  = f"{org}/{model_name}"
    dest_dir = models_root / model_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    for filename in MODEL_FILES:
        dest = dest_dir / filename
        if dest.exists():
            print(f"  {filename} — already present, skipping.")
            continue

        url  = f"{HF_BASE}/{repo_id}/resolve/main/{filename}"
        hook = _progress(filename) if filename == "model.safetensors" else None
        print(f"  Downloading {filename}...")
        try:
            urllib.request.urlretrieve(url, dest, reporthook=hook)
            if hook:
                sys.stdout.write("\n")
        except urllib.error.HTTPError as exc:
            if hook:
                sys.stdout.write("\n")
            if dest.exists():
                dest.unlink()
            if exc.code == 404:
                print(f"  {filename} — not found in repo, skipping.")
                continue
            print(f"  ERROR downloading {filename}: {exc}", file=sys.stderr)
            raise SystemExit(1)
        except Exception as exc:
            if hook:
                sys.stdout.write("\n")
            if dest.exists():
                dest.unlink()
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
        actual = sha256_file(weights)
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

    models_root = Path(args.models_dir) if args.models_dir else Path(__file__).parent.parent / "models"

    if args.model:
        models = [args.model]
    else:
        print(f"Querying HuggingFace for models under '{args.org}'...")
        models = list_hf_models(args.org)

    if not models:
        print("No models found.")
        return

    print(f"Found {len(models)} model(s): {', '.join(models)}")
    for model_name in models:
        print(f"\nModel: {model_name}")
        download_model(model_name, models_root, org=args.org)


if __name__ == "__main__":
    main()
