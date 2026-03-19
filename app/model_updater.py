"""
TechBS model update checker.

Fetches a remote manifest and downloads newer model weights when available.
After migrating to HuggingFace, point TECHBS_MANIFEST_URL at the manifest
file in your HF repo — the url fields become HF direct-download links:
  https://huggingface.co/<org>/<repo>/resolve/main/model.safetensors

Manifest format (host this JSON at a stable URL):
{
  "models": {
    "cyberbs": {
      "version": "1.1.0",
      "sha256": "abc123...",
      "url": "https://direct-download-url/model.safetensors"
    }
  }
}

Usage:
    python model_updater.py [--check] [--manifest-url URL] [--models-dir PATH]
"""
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich import box

MODELS_DIR = Path(__file__).parent.parent / "models"

# Override via TECHBS_MANIFEST_URL environment variable
MANIFEST_URL = os.environ.get(
    "TECHBS_MANIFEST_URL",
    "REPLACE_WITH_MANIFEST_URL",
)


def _parse_version(v: str) -> tuple:
    """Parse a 'major.minor.patch' version string into a comparable tuple."""
    try:
        return tuple(int(x) for x in str(v).split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


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


class ModelUpdater:
    def __init__(self, manifest_url: str = MANIFEST_URL, models_dir: Path = MODELS_DIR):
        self.manifest_url = manifest_url
        self.models_dir = models_dir
        self.console = Console()

    def _fetch_manifest(self) -> dict:
        if self.manifest_url.startswith("REPLACE_"):
            raise RuntimeError(
                "No manifest URL configured.\n"
                "Set the TECHBS_MANIFEST_URL environment variable or pass --manifest-url."
            )
        try:
            with urllib.request.urlopen(self.manifest_url, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise RuntimeError(f"Could not fetch manifest: {e}") from e
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Manifest is not valid JSON: {e}") from e

    def _local_info(self, model_dir: Path) -> dict:
        info_file = model_dir / "info.json"
        if not info_file.exists():
            return {}
        try:
            return json.loads(info_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _download_weights(self, url: str, dest: Path) -> None:
        """Download to a .tmp file then atomically replace dest on success."""
        tmp = dest.with_suffix(".tmp")
        try:
            urllib.request.urlretrieve(url, tmp, reporthook=_progress("model.safetensors"))
            sys.stdout.write("\n")
            tmp.replace(dest)
        except Exception:
            sys.stdout.write("\n")
            if tmp.exists():
                tmp.unlink()
            raise

    def run(self, check_only: bool = False) -> None:
        self.console.print("[bold cyan]Checking for model updates...[/]")

        try:
            manifest = self._fetch_manifest()
        except RuntimeError as e:
            self.console.print(f"[red]{e}[/]")
            return

        remote_models = manifest.get("models", {})
        if not remote_models:
            self.console.print("[yellow]Manifest contains no models.[/]")
            return

        local_dirs = (
            {p.name: p for p in self.models_dir.iterdir() if p.is_dir() and (p / "config.json").exists()}
            if self.models_dir.exists()
            else {}
        )

        table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
        table.add_column("Model",  style="bold cyan", min_width=16)
        table.add_column("Local",  width=10)
        table.add_column("Remote", width=10)
        table.add_column("Status", width=18)

        updates_available = []
        for model_name, remote_info in sorted(remote_models.items()):
            remote_ver = remote_info.get("version", "?")
            model_dir  = local_dirs.get(model_name, self.models_dir / model_name)
            local_info = self._local_info(model_dir)
            local_ver  = local_info.get("version", "none")
            weights    = model_dir / "model.safetensors"

            if not weights.exists():
                status = "[yellow]not installed[/]"
            elif _parse_version(remote_ver) > _parse_version(local_ver):
                status = "[green]update available[/]"
                updates_available.append((model_name, remote_info, model_dir))
            else:
                status = "[dim]up to date[/]"

            table.add_row(model_name, local_ver, remote_ver, status)

        self.console.print(table)

        if check_only or not updates_available:
            if not updates_available:
                self.console.print("[dim]All models are up to date.[/]")
            return

        self.console.print(f"\n[bold]{len(updates_available)} update(s) available.[/]")
        try:
            confirm = input("Download updates now? [y/N]: ").strip().lower()
        except EOFError:
            return
        if confirm != "y":
            return

        for model_name, remote_info, model_dir in updates_available:
            self.console.print(f"\n[bold cyan]Updating {model_name}...[/]")
            model_dir.mkdir(parents=True, exist_ok=True)
            weights_path = model_dir / "model.safetensors"

            url             = remote_info.get("url", "")
            expected_sha256 = remote_info.get("sha256", "")
            remote_ver      = remote_info.get("version", "")

            if not url:
                self.console.print(f"  [red]No download URL in manifest for {model_name}[/]")
                continue

            try:
                self._download_weights(url, weights_path)
            except Exception as e:
                self.console.print(f"  [red]Download failed: {e}[/]")
                continue

            if expected_sha256:
                actual = _sha256(weights_path)
                if actual != expected_sha256:
                    weights_path.unlink(missing_ok=True)
                    self.console.print(f"  [red]SHA256 mismatch — file deleted. Update aborted.[/]")
                    self.console.print(f"  [dim]Expected: {expected_sha256}[/]")
                    self.console.print(f"  [dim]Got:      {actual}[/]")
                    continue
                self.console.print(f"  [green]✓ Integrity verified[/]")

            # Update info.json with new version + hash
            local_info = self._local_info(model_dir)
            local_info["version"] = remote_ver
            if expected_sha256:
                local_info["sha256"] = expected_sha256
            (model_dir / "info.json").write_text(
                json.dumps(local_info, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            self.console.print(f"  [green]✓ {model_name} updated to v{remote_ver}[/]")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Check for and apply TechBS model updates")
    parser.add_argument("--manifest-url", default=None, help="Override manifest URL")
    parser.add_argument("--check",        action="store_true", help="Check for updates without downloading")
    parser.add_argument("--models-dir",   default=None, help="Path to models directory")
    args = parser.parse_args()

    updater = ModelUpdater(
        manifest_url=args.manifest_url or MANIFEST_URL,
        models_dir=Path(args.models_dir) if args.models_dir else MODELS_DIR,
    )
    updater.run(check_only=args.check)


if __name__ == "__main__":
    main()
