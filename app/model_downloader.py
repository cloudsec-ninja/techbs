"""
Downloads TechBS model weights from Azure Blob Storage.
Called by install.sh / install.bat during setup.

Auto-discovers model directories under models/ and downloads any missing
model.safetensors files. Only downloads a model if it exists on storage.

Usage:
    python model_downloader.py \
        --url "https://account.blob.core.windows.net/container?sv=...&sig=..."
"""
import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

# Files required to run inference
MODEL_FILES = [
    "model.safetensors",
]


def _progress(label: str):
    """Return a urlretrieve reporthook that prints a progress line."""
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


def discover_models(models_root: Path) -> list:
    """Return names of all subdirectories present in models_root."""
    if not models_root.is_dir():
        return []
    return sorted(p.name for p in models_root.iterdir() if p.is_dir())


def download_model(model_name: str, base: str, sas: str, models_root: Path) -> None:
    dest_dir = models_root / model_name

    for filename in MODEL_FILES:
        dest = dest_dir / filename
        if dest.exists():
            print(f"  {filename} — already present, skipping.")
            continue

        url = f"{base}/{model_name}/{filename}{sas}"

        print(f"  {filename}")
        try:
            urllib.request.urlretrieve(url, dest, reporthook=_progress(filename))
            sys.stdout.write("\n")
        except urllib.error.HTTPError as exc:
            sys.stdout.write("\n")
            if dest.exists():
                dest.unlink()
            if exc.code == 404:
                print(f"  {model_name}/{filename} — not found on storage, skipping.")
                return
            print(f"  ERROR downloading {filename}: {exc}", file=sys.stderr)
            raise SystemExit(1)
        except Exception as exc:
            sys.stdout.write("\n")
            if dest.exists():
                dest.unlink()
            print(f"  ERROR downloading {filename}: {exc}", file=sys.stderr)
            raise SystemExit(1)

    print(f"  Model '{model_name}' ready.")


def main():
    parser = argparse.ArgumentParser(description="Download TechBS model weights from Azure Blob Storage")
    parser.add_argument("--url",        required=True, help="Full Azure container URL with embedded SAS token")
    parser.add_argument("--models-dir", default=None,  help="Path to models directory (default: ../models relative to this script)")
    args = parser.parse_args()

    models_root = Path(args.models_dir) if args.models_dir else Path(__file__).parent.parent / "models"

    models = discover_models(models_root)
    if not models:
        print("No model directories found — nothing to download.")
        return

    parts = urlsplit(args.url)
    base = urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))
    sas  = ("?" + parts.query) if parts.query else ""

    print(f"Checking {len(models)} model(s): {', '.join(models)}")
    for model_name in models:
        print(f"\nModel: {model_name}")
        download_model(model_name, base, sas, models_root)


if __name__ == "__main__":
    main()
