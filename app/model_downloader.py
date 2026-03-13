"""
Downloads CyberBS model files from Azure Blob Storage.
Called by install.sh / install.bat during setup.

Usage:
    python model_downloader.py --model cyberbs \
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
    "config.json",
    "tokenizer_config.json",
    "tokenizer.json",
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


def download_model(model_name: str, container_url: str, models_root: Path) -> None:
    dest_dir = models_root / model_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Split the container URL into base path and query string (SAS token)
    parts = urlsplit(container_url)
    base = urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))
    sas  = ("?" + parts.query) if parts.query else ""

    print(f"\nDownloading model: {model_name}")

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
                print(f"  {filename} — not found in blob storage, skipping.")
                continue
            print(f"  ERROR downloading {filename}: {exc}", file=sys.stderr)
            raise SystemExit(1)
        except Exception as exc:
            sys.stdout.write("\n")
            if dest.exists():
                dest.unlink()
            print(f"  ERROR downloading {filename}: {exc}", file=sys.stderr)
            raise SystemExit(1)

    print(f"  Model '{model_name}' ready.\n")


def main():
    parser = argparse.ArgumentParser(description="Download CyberBS model from Azure Blob Storage")
    parser.add_argument("--model",      required=True, help="Model folder name (e.g. cyberbs)")
    parser.add_argument("--url",        required=True, help="Full Azure container URL with embedded SAS token")
    parser.add_argument("--models-dir", default=None,  help="Path to models directory (default: ../models relative to this script)")
    args = parser.parse_args()

    models_root = Path(args.models_dir) if args.models_dir else Path(__file__).parent.parent / "models"
    download_model(args.model, args.url, models_root)


if __name__ == "__main__":
    main()
