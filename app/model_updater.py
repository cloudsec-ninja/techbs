"""
TechBS model update checker.

Queries the HuggingFace API to discover available models under the techbsai
organization, then downloads or updates model weights as needed.

Usage:
    python model_updater.py [--check] [--models-dir PATH]
"""
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich import box

MODELS_DIR = Path(__file__).parent.parent / "models"

HF_ORG  = "techbsai"
HF_API  = "https://huggingface.co/api"
HF_BASE = "https://huggingface.co"

# Files to download when pulling a model
MODEL_FILES = [
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "buzzwords.json",
    "info.json",
    "model.safetensors",
]


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
    def __init__(self, models_dir: Path = MODELS_DIR, manifest_url: str = None, hf_org: str = HF_ORG):
        self.models_dir   = models_dir
        self.hf_org       = hf_org
        self.manifest_url = manifest_url  # kept for backward compat; ignored when None
        self.console      = Console()

    def _fetch_manifest(self) -> dict:
        """Build a manifest by querying the HuggingFace API for all models under the org."""
        api_url = f"{HF_API}/models?author={self.hf_org}"
        try:
            with urllib.request.urlopen(api_url, timeout=15) as resp:
                hf_models = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise RuntimeError(f"Could not reach HuggingFace API: {e}") from e
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid response from HuggingFace API: {e}") from e

        models = {}
        for hf_model in hf_models:
            repo_id = hf_model.get("id", "")
            if not repo_id:
                continue
            name = repo_id.split("/")[-1]

            # Fetch info.json from the repo for version, sha256, and metadata
            info = {}
            info_fetched = False
            try:
                info_url = f"{HF_BASE}/{repo_id}/resolve/main/info.json"
                with urllib.request.urlopen(info_url, timeout=10) as r:
                    info = json.loads(r.read().decode("utf-8"))
                    info_fetched = True
            except Exception:
                pass

            # Skip models whose info.json couldn't be fetched — without version
            # metadata we can't reliably compare local vs remote versions.
            if not info_fetched:
                continue

            models[name] = {
                "display_name": info.get("domain", name),
                "domain":       info.get("domain", ""),
                "description":  info.get("description", ""),
                "version":      info.get("version", "0.0.0"),
                "sha256":       info.get("weights_sha256") or info.get("sha256", ""),
                "size_mb":      info.get("size_mb"),
                "url":          f"{HF_BASE}/{repo_id}/resolve/main/model.safetensors",
            }

        return {"models": models}

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

    def list_models(self) -> None:
        """Show all available models from the manifest, with local install status."""
        self.console.print("[bold cyan]Available TechBS models[/]\n")

        try:
            manifest = self._fetch_manifest()
        except RuntimeError as e:
            self.console.print(f"[red]{e}[/]")
            return

        remote_models = manifest.get("models", {})
        if not remote_models:
            self.console.print("[yellow]No models found in manifest.[/]")
            return

        local_dirs = (
            {p.name: p for p in self.models_dir.iterdir() if p.is_dir()}
            if self.models_dir.exists()
            else {}
        )

        table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
        table.add_column("Name", style="bold cyan", min_width=14)
        table.add_column("Domain", min_width=16)
        table.add_column("Version", width=10)
        table.add_column("Size", width=10)
        table.add_column("Status", width=14)

        for model_name, info in sorted(remote_models.items()):
            domain  = info.get("domain", info.get("display_name", ""))
            version = info.get("version", "?")
            size_mb = info.get("size_mb")
            size    = f"~{size_mb} MB" if size_mb else "?"

            model_dir = local_dirs.get(model_name, self.models_dir / model_name)
            weights   = model_dir / "model.safetensors"

            if weights.exists():
                local_info = self._local_info(model_dir)
                local_ver  = local_info.get("version", "?")
                if _parse_version(version) > _parse_version(local_ver):
                    status = "[green]update available[/]"
                else:
                    status = "[green]installed[/]"
            else:
                status = "[dim]not installed[/]"

            table.add_row(model_name, domain, version, size, status)

        self.console.print(table)
        self.console.print("[dim]Pull a model:  techbs --model-pull <name>[/]")

    def pull_models(self, names: list[str]) -> None:
        """Download one or more models by name from the manifest."""
        try:
            manifest = self._fetch_manifest()
        except RuntimeError as e:
            self.console.print(f"[red]{e}[/]")
            return

        remote_models = manifest.get("models", {})
        if not remote_models:
            self.console.print("[yellow]No models found in manifest.[/]")
            return

        for name in names:
            if name not in remote_models:
                self.console.print(f"[red]Model '{name}' not found in manifest.[/]")
                self.console.print(f"[dim]Available: {', '.join(sorted(remote_models))}[/]")
                continue

            info        = remote_models[name]
            model_dir   = self.models_dir / name
            weights     = model_dir / "model.safetensors"
            url         = info.get("url", "")
            sha256      = info.get("sha256", "")
            version     = info.get("version", "")
            display     = info.get("display_name", name)

            if weights.exists():
                self.console.print(f"[bold cyan]{display}[/] ({name}) is already installed.")
                local_info = self._local_info(model_dir)
                local_ver  = local_info.get("version", "?")
                if _parse_version(version) > _parse_version(local_ver):
                    self.console.print(f"  [green]Update available: v{local_ver} → v{version}[/]")
                    try:
                        confirm = input("  Download update? [y/N]: ").strip().lower()
                    except EOFError:
                        continue
                    if confirm != "y":
                        continue
                else:
                    self.console.print(f"  [dim]Up to date (v{local_ver})[/]")
                    continue

            if not url:
                self.console.print(f"  [red]No download URL in manifest for {name}[/]")
                continue

            self.console.print(f"\n[bold cyan]Pulling {display}[/] ({name})...")
            model_dir.mkdir(parents=True, exist_ok=True)

            # Download all supporting files from HuggingFace
            repo_id = f"{self.hf_org}/{name}"
            for filename in MODEL_FILES:
                if filename == "model.safetensors":
                    continue  # weights downloaded separately below with progress
                dest = model_dir / filename
                # Re-download if missing or suspiciously small (likely a partial download)
                if dest.exists() and dest.stat().st_size > 0:
                    continue
                file_url = f"{HF_BASE}/{repo_id}/resolve/main/{filename}"
                self.console.print(f"  [dim]{filename}[/]")
                try:
                    tmp = dest.with_suffix(dest.suffix + ".tmp")
                    urllib.request.urlretrieve(file_url, tmp)
                    tmp.replace(dest)
                except Exception as e:
                    if tmp.exists():
                        tmp.unlink()
                    self.console.print(f"  [yellow]Warning: could not download {filename}: {e}[/]")

            # Download model weights
            try:
                self._download_weights(url, weights)
            except Exception as e:
                self.console.print(f"  [red]Download failed: {e}[/]")
                continue

            if sha256:
                actual = _sha256(weights)
                if actual != sha256:
                    weights.unlink(missing_ok=True)
                    self.console.print(f"  [red]SHA256 mismatch — file deleted.[/]")
                    self.console.print(f"  [dim]Expected: {sha256}[/]")
                    self.console.print(f"  [dim]Got:      {actual}[/]")
                    continue
                self.console.print(f"  [green]Integrity verified[/]")

            # Write/update info.json
            local_info = self._local_info(model_dir)
            local_info["version"] = version
            if sha256:
                local_info["sha256"] = sha256
            for field in ("display_name", "domain", "description", "size_mb"):
                if field in info:
                    local_info[field] = info[field]
            (model_dir / "info.json").write_text(
                json.dumps(local_info, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            self.console.print(f"  [green]Model '{name}' ready (v{version})[/]")

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
    parser.add_argument("--check",      action="store_true", help="Check for updates without downloading")
    parser.add_argument("--models-dir", default=None,        help="Path to models directory")
    args = parser.parse_args()

    updater = ModelUpdater(
        models_dir=Path(args.models_dir) if args.models_dir else MODELS_DIR,
    )
    updater.run(check_only=args.check)


if __name__ == "__main__":
    main()
