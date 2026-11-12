"""
TechBS model update checker.

Queries the HuggingFace API to discover available models under the techbsai
organization, then downloads or updates model weights as needed.

Usage:
    python -m techbs.model_updater [--check] [--models-dir PATH]
"""
import json
import sys
import urllib.error
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich import box

from . import hf_repo
from .hf_repo import HF_ORG
from .paths import models_dir

MODELS_DIR = models_dir()


def _parse_version(v: str) -> tuple:
    """Parse a 'major.minor.patch' version string into a comparable tuple."""
    try:
        return tuple(int(x) for x in str(v).split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)


class ModelUpdater:
    def __init__(self, models_dir: Path = MODELS_DIR, manifest_url: str = None, hf_org: str = HF_ORG):
        self.models_dir   = models_dir
        self.hf_org       = hf_org
        self.manifest_url = manifest_url  # kept for backward compat; ignored when None
        self.console      = Console()

    def _fetch_manifest(self) -> dict:
        """Build a manifest by querying the HuggingFace API for all models under the org."""
        try:
            names = hf_repo.list_org_model_names(self.hf_org)
        except urllib.error.URLError as e:
            raise RuntimeError(f"Could not reach HuggingFace API: {e}") from e
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid response from HuggingFace API: {e}") from e

        models = {}
        for name in names:
            repo_id = f"{self.hf_org}/{name}"

            # Fetch info.json for version, sha256, and metadata. Skip models
            # whose info.json couldn't be fetched — without version metadata we
            # can't reliably compare local vs remote versions.
            info = hf_repo.fetch_info_json(repo_id)
            if info is None:
                continue

            models[name] = {
                "display_name": info.get("domain", name),
                "domain":       info.get("domain", ""),
                "description":  info.get("description", ""),
                "version":      info.get("version", "0.0.0"),
                "sha256":       info.get("weights_sha256") or info.get("sha256", ""),
                "size_mb":      info.get("size_mb"),
                "url":          hf_repo.file_url(repo_id, "model.safetensors"),
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
        try:
            hf_repo.download_atomic(url, dest, reporthook=hf_repo.progress_hook("model.safetensors"))
        finally:
            sys.stdout.write("\n")

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

    def _download_supporting_files(self, name: str, model_dir: Path) -> bool:
        """Fetch config, tokenizer, buzzwords and info.json for a model.

        Always overwrites: a new model version can change any of them (e.g. its
        labels), and they must match the weights. Returns False on failure.
        """
        repo_id = f"{self.hf_org}/{name}"
        for filename in hf_repo.MODEL_FILES:
            if filename == "model.safetensors":
                continue  # weights are downloaded separately, with progress
            try:
                hf_repo.download_atomic(hf_repo.file_url(repo_id, filename), model_dir / filename)
            except Exception as e:
                if filename == "buzzwords.json":  # optional
                    continue
                self.console.print(f"  [red]Could not download {filename}: {e}[/]")
                return False
        return True

    def pull_models(self, names: list[str], assume_yes: bool = False) -> bool:
        """Download one or more models by name. Returns True if every model is
        installed and up to date afterwards. assume_yes installs available
        updates without asking (for installers)."""
        try:
            manifest = self._fetch_manifest()
        except RuntimeError as e:
            self.console.print(f"[red]{e}[/]")
            return False

        remote_models = manifest.get("models", {})
        if not remote_models:
            self.console.print("[yellow]No models found in manifest.[/]")
            return False

        ok = True

        for name in names:
            if name not in remote_models:
                self.console.print(f"[red]Model '{name}' not found in manifest.[/]")
                self.console.print(f"[dim]Available: {', '.join(sorted(remote_models))}[/]")
                ok = False
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
                    if not assume_yes:
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
                ok = False
                continue

            self.console.print(f"\n[bold cyan]Pulling {display}[/] ({name})...")
            model_dir.mkdir(parents=True, exist_ok=True)


            # Download model weights
            try:
                self._download_weights(url, weights)
            except Exception as e:
                self.console.print(f"  [red]Download failed: {e}[/]")
                ok = False
                continue

            if sha256:
                actual = hf_repo.sha256_file(weights)
                if actual != sha256:
                    weights.unlink(missing_ok=True)
                    self.console.print(f"  [red]SHA256 mismatch — file deleted.[/]")
                    self.console.print(f"  [dim]Expected: {sha256}[/]")
                    self.console.print(f"  [dim]Got:      {actual}[/]")
                    ok = False
                    continue
                self.console.print(f"  [green]Integrity verified[/]")

            # Supporting files only after the weights are in place, so they always match
            if not self._download_supporting_files(name, model_dir):
                ok = False
                continue

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
        return ok

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
                actual = hf_repo.sha256_file(weights_path)
                if actual != expected_sha256:
                    weights_path.unlink(missing_ok=True)
                    self.console.print(f"  [red]SHA256 mismatch — file deleted. Update aborted.[/]")
                    self.console.print(f"  [dim]Expected: {expected_sha256}[/]")
                    self.console.print(f"  [dim]Got:      {actual}[/]")
                    continue
                self.console.print(f"  [green]✓ Integrity verified[/]")

            # Config, tokenizer and labels can change between versions
            if not self._download_supporting_files(model_name, model_dir):
                continue

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
