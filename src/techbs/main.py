#!/usr/bin/env python3
"""
TechBS Analyzer
Usage:
    techbs --file <audio_file> [--whisper-model NAME] [--chunk-seconds 15]
    techbs --url <url> [--whisper-model NAME] [--chunk-seconds 15]
    techbs --mic [--whisper-model NAME] [--chunk-seconds 15]
"""
import argparse
import itertools
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Iterator

from .analyzer import TechBSAnalyzer
from .config import load_config, save_config
from .labels import DEFAULT_MODEL, preferred_models
from .paths import models_dir
from .pipeline import DEFAULT_CONTEXT_SECONDS, ContextScorer, context_samples
from .whisper_models import (
    CONFIG_KEY as WHISPER_CONFIG_KEY,
    WhisperSelectionError,
    pick_interactively,
    resolve_whisper_model,
)
from .version import VERSION
from .mic_transcriber import MicTranscriber
from .model_updater import ModelUpdater
from rich.console import Console
from rich.table import Table
from rich import box
from .skip import SkipController
from .transcriber import AudioTranscriber

# model_debugger is a dev-only module, not shipped in the distribution package
try:
    from .model_debugger import ModelDebugger, load_llm_config
    _HAS_DEBUGGER = True
except ImportError:
    _HAS_DEBUGGER = False
from .ui import TechBSUI

MODELS_DIR = models_dir()


def discover_models() -> list[Path]:
    """Return model dirs that look like valid HuggingFace checkpoints."""
    if not MODELS_DIR.exists():
        return []
    return sorted(
        p for p in MODELS_DIR.iterdir()
        if p.is_dir() and (p / "config.json").exists()
    )


def load_model_info(model_path: Path) -> dict:
    """Load optional info.json metadata from a model directory."""
    info_file = model_path / "info.json"
    if not info_file.exists():
        return {}
    try:
        return json.loads(info_file.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _offer_model_download(console: Console) -> bool:
    """No model installed: offer to download the default one (interactive only)."""
    if not sys.stdin.isatty():
        return False
    console.print(f"[yellow]No TechBS model is installed yet.[/]")
    try:
        answer = input(f"Download the {DEFAULT_MODEL} model now (about 420 MB)? [Y/n]: ").strip().lower()
    except EOFError:
        return False
    if answer not in ("", "y", "yes"):
        return False
    return ModelUpdater(models_dir=MODELS_DIR).pull_models([DEFAULT_MODEL])


def select_model(name: str | None = None) -> tuple[Path, dict]:
    """Pick the classifier model. Returns (model_path, info.json contents).

    --model NAME picks one directly. Otherwise the unified model is used when
    installed; legacy domain models are only offered when no unified model is.
    """
    console = Console()
    if name:
        path = MODELS_DIR / name
        if not (path / "config.json").exists():
            console.print(f"[red]Model '{name}' is not installed in {MODELS_DIR}.[/] "
                          f"Download it with: techbs --model-pull {name}")
            sys.exit(1)
        return path, load_model_info(path)

    all_models = discover_models()
    if not all_models and _offer_model_download(console):
        all_models = discover_models()
    if not all_models:
        console.print(f"[red]No models installed in {MODELS_DIR}.[/] "
                      f"Download one with: techbs --model-pull {DEFAULT_MODEL}")
        sys.exit(1)

    all_infos = [load_model_info(m) for m in all_models]
    keep = preferred_models(all_models, all_infos)
    models = [all_models[i] for i in keep]
    infos = [all_infos[i] for i in keep]

    if len(models) == 1:
        desc = infos[0].get("description", "")
        console.print(f"[dim]Using model:[/] [bold cyan]{models[0].name}[/]" + (f"  [dim]{desc}[/]" if desc else ""))
        return models[0], infos[0]

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("#", style="bold", width=3)
    table.add_column("Model", style="bold cyan", min_width=16)
    table.add_column("Domain", style="yellow", min_width=14)
    table.add_column("Description", style="dim")

    for i, (m, info) in enumerate(zip(models, infos), 1):
        table.add_row(
            str(i),
            m.name,
            info.get("domain", ""),
            info.get("description", ""),
        )

    console.print()
    console.print("[bold cyan]Available models:[/]")
    console.print(table)

    while True:
        try:
            choice = input(f"Select model [1-{len(models)}]: ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(models):
                return models[idx], infos[idx]
        except ValueError:
            pass
        except EOFError:
            console.print(f"[red]No interactive input available. Use --model to specify a model.[/]")
            sys.exit(1)
        console.print(f"[red]Enter a number between 1 and {len(models)}[/]")


def _gpu_name() -> str | None:
    import torch
    return torch.cuda.get_device_name(0) if torch.cuda.is_available() else None


def choose_whisper_model(cli_value: str | None, reselect: bool) -> str:
    """Pick the Whisper model: --whisper-model > picker (first run / --select-whisper) > saved."""
    config = load_config()
    try:
        return resolve_whisper_model(
            cli_value,
            reselect,
            config,
            pick=lambda: pick_interactively(_gpu_name(), current=config.get(WHISPER_CONFIG_KEY)),
            save=lambda name: save_config({WHISPER_CONFIG_KEY: name}),
        )
    except WhisperSelectionError as exc:
        Console().print(f"[red]{exc}[/]")
        sys.exit(1)


def _detect_platform() -> str:
    """Return 'wsl', 'macos', or 'linux'."""
    if platform.system() == "Darwin":
        return "macos"
    if os.path.exists("/proc/version"):
        with open("/proc/version") as f:
            if "microsoft" in f.read().lower():
                return "wsl"
    return "linux"


def download_url(url: str, console: "Console | None" = None) -> Path:
    """Download audio from a URL (YouTube, podcast, etc.) and return the local file path.

    Uses yt-dlp for YouTube and other supported sites.
    Raises SystemExit on failure after cleaning up temp files.
    """
    if console is None:
        from rich.console import Console
        console = Console()

    # Check for yt-dlp
    if not shutil.which("yt-dlp"):
        console.print("[red]yt-dlp is required for --url support.[/]")
        console.print("[dim]Install it:  pip install yt-dlp[/]")
        sys.exit(1)

    tmp_dir = Path(tempfile.mkdtemp(prefix="techbs_"))
    output_template = str(tmp_dir / "audio.%(ext)s")

    console.print(f"[bold cyan]Downloading audio from URL...[/]")
    result = subprocess.run(
        [
            "yt-dlp",
            "--extract-audio",
            "--audio-format", "wav",
            "--audio-quality", "0",
            "--no-playlist",
            "-o", output_template,
            url,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        console.print(f"[red]yt-dlp failed:[/]\n{result.stderr.strip()}")
        sys.exit(1)

    # Find the downloaded file
    downloaded = list(tmp_dir.glob("audio.*"))
    if not downloaded:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        console.print("[red]Download completed but no audio file was produced.[/]")
        sys.exit(1)

    audio_file = downloaded[0]
    console.print(f"[green]Downloaded:[/] {audio_file.name} ({audio_file.stat().st_size / 1024 / 1024:.1f} MB)")
    return audio_file


class AudioPlayer:
    """Manages an audio subprocess that can be killed and restarted at a new position."""

    def __init__(self, audio_path: Path):
        self.audio_path = audio_path
        self._platform = _detect_platform()
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        # Cache the Windows path once for WSL
        if self._platform == "wsl":
            result = subprocess.run(
                ["wslpath", "-w", str(audio_path.resolve())],
                capture_output=True, text=True,
            )
            if result.returncode != 0 or not result.stdout.strip():
                raise RuntimeError(
                    f"wslpath failed to convert path for Windows playback: {result.stderr.strip() or 'no output'}"
                )
            self._win_path = result.stdout.strip()

    def play(self, seek_seconds: float = 0.0):
        """Start playback from *seek_seconds*. Kills any existing playback first."""
        with self._lock:
            self._kill_proc()
            self._proc = self._spawn(seek_seconds)

    def stop(self):
        with self._lock:
            self._kill_proc()

    def seek(self, seconds: float):
        """Jump playback to *seconds* into the file."""
        self.play(seek_seconds=seconds)

    def _kill_proc(self):
        if self._proc and self._proc.poll() is None:
            self._proc.kill()
            self._proc.wait()
        self._proc = None

    def _spawn(self, seek: float) -> subprocess.Popen:
        p = self._platform
        devnull = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}

        if p == "wsl":
            # PowerShell MediaPlayer with seek via Position property
            seek_ms = int(seek * 1000)
            # Escape single quotes for PowerShell single-quoted strings (' → '')
            safe_path = self._win_path.replace("'", "''")
            # Wait for media to open, then sleep until playback finishes.
            # Uses NaturalDuration instead of a fixed 7200s sleep so the
            # process exits shortly after the audio ends.
            ps_cmd = (
                "Add-Type -AssemblyName presentationCore; "
                "$m = New-Object System.Windows.Media.MediaPlayer; "
                f"$m.Open([Uri]'{safe_path}'); "
                "Start-Sleep -Milliseconds 300; "
                f"$m.Position = [TimeSpan]::FromMilliseconds({seek_ms}); "
                "$m.Play(); "
                "while (-not $m.NaturalDuration.HasTimeSpan) { Start-Sleep -Milliseconds 200 }; "
                "$dur = $m.NaturalDuration.TimeSpan.TotalSeconds - $m.Position.TotalSeconds + 2; "
                "if ($dur -gt 0) { Start-Sleep -Seconds ([math]::Ceiling($dur)) }"
            )
            return subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-Command", ps_cmd], **devnull,
            )
        else:
            # macOS and Linux: ffplay supports -ss for true start-position seeking.
            # afplay has no start-offset option so it cannot be used for skip.
            # macOS: brew install ffmpeg
            cmd = [
                "ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
                str(self.audio_path),
            ]
            if seek > 0:
                cmd.extend(["-ss", str(seek)])
            return subprocess.Popen(cmd, **devnull)


def realtime_sync(
    chunk_gen: Iterator,
    start_time: float,
    skipper: SkipController | None = None,
    player: AudioPlayer | None = None,
    transcriber: AudioTranscriber | None = None,
    chunk_seconds: int = 15,
) -> Iterator:
    """Throttle chunk processing to stay in sync with audio playback.
    If a SkipController is provided, the user can skip the wait between chunks
    and the AudioPlayer will seek to the new position.
    """
    for chunk in chunk_gen:
        if skipper and skipper.quit_requested:
            if player:
                player.stop()
            return
        yield chunk
        _, _, end_sec, _ = chunk
        wait = (start_time + end_sec) - time.monotonic()
        if wait > 0:
            if skipper:
                skipped = skipper.wait_interruptible(wait)
                if skipped and not skipper.quit_requested:
                    skipper.consume_skip()
                    # Jump both audio and transcription to the next chunk
                    if player:
                        player.seek(end_sec)
                    if transcriber:
                        next_chunk_idx = int(end_sec // chunk_seconds)
                        transcriber.skip_to(next_chunk_idx)
                    # Reset the clock so future waits are relative to now
                    start_time = time.monotonic() - end_sec
            else:
                time.sleep(wait)


def _run_debugger(debugger, transcript_path, keep: bool) -> None:
    """Call the LLM model debugger then delete the transcript if the user didn't ask to keep it."""
    if debugger is None or transcript_path is None:
        return
    debugger.run_diagnostics(transcript_path)
    if not keep:
        transcript_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(
        description="TechBS — Real-Time BS Detection for Tech"
    )
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument(
        "--file",
        metavar="AUDIO_FILE",
        help="Path to a local audio file (mp3, wav, m4a, etc.)",
    )
    input_group.add_argument(
        "--url",
        metavar="URL",
        help="URL to a YouTube video, podcast episode, or audio stream",
    )
    input_group.add_argument(
        "--mic",
        action="store_true",
        help="Use live microphone input",
    )
    parser.add_argument(
        "--model",
        metavar="NAME",
        default=None,
        help=f"Classifier model to use (default: {DEFAULT_MODEL}, or ask if several are installed)",
    )
    parser.add_argument(
        "--whisper-model",
        metavar="NAME",
        default=None,
        help="Whisper model for this run only, e.g. small or large-v3-turbo "
             "(default: the model you picked on first run)",
    )
    parser.add_argument(
        "--select-whisper",
        action="store_true",
        help="Choose and save the Whisper transcription model",
    )
    parser.add_argument(
        "--chunk-seconds",
        type=int,
        default=15,
        help="Seconds of audio per analysis chunk (default: 15)",
    )
    parser.add_argument(
        "--context-seconds",
        type=int,
        default=DEFAULT_CONTEXT_SECONDS,
        help="Seconds of speech each sample is judged with, including the samples "
             f"before it (default: {DEFAULT_CONTEXT_SECONDS}; the models are trained on "
             "about a minute of speech). Set to the chunk size to judge samples alone",
    )
    parser.add_argument(
        "--no-play",
        action="store_true",
        help="Disable audio playback for file mode (transcribe only)",
    )
    parser.add_argument(
        "--transcript",
        action="store_true",
        help="Save full transcript and scores to a JSON file after analysis",
    )
    parser.add_argument(
        "--model-list",
        action="store_true",
        help="List all available models and their install status",
    )
    parser.add_argument(
        "--model-pull",
        nargs="+",
        metavar="NAME",
        help="Download one or more models by name (e.g. --model-pull techbs)",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="With --model-pull: install available model updates without asking",
    )
    parser.add_argument(
        "--update-models",
        action="store_true",
        help="Check for model updates and download if available",
    )
    parser.add_argument(
        "--check-updates",
        action="store_true",
        help="Check for model updates without downloading",
    )

    if _HAS_DEBUGGER:
        parser.add_argument(
            "--debug-model",
            action="store_true",
            help="Run LLM-powered model diagnostics: fact-check claims, find misclassifications, suggest training improvements",
        )
        parser.add_argument(
            "--llm-provider",
            default=None,
            choices=["ollama", "claude", "openai", "gemini"],
            help="LLM provider for --debug-model (default: ollama)",
        )
        parser.add_argument(
            "--llm-model",
            default=None,
            help="Model name override for the selected LLM provider",
        )
    args = parser.parse_args()

    print(f"TechBS v{VERSION}")

    if args.model_list:
        ModelUpdater(models_dir=MODELS_DIR).list_models()
        return

    if args.model_pull:
        ok = ModelUpdater(models_dir=MODELS_DIR).pull_models(args.model_pull, assume_yes=args.yes)
        sys.exit(0 if ok else 1)

    if args.update_models or args.check_updates:
        ModelUpdater(models_dir=MODELS_DIR).run(check_only=args.check_updates)
        return

    if args.select_whisper and not (args.mic or args.file or args.url):
        name = choose_whisper_model(None, reselect=True)
        Console().print(f"[green]Saved.[/] TechBS will use Whisper [bold]{name}[/] from now on.")
        return

    if not args.mic and not args.file and not args.url:
        parser.error("provide --file <path>, --url <url>, or --mic")
    if args.mic and args.no_play:
        args.no_play = False  # mic mode has no playback; ignore silently

    model_path, model_info = select_model(args.model)
    model_domain = model_info.get("domain", "")
    whisper_model = choose_whisper_model(args.whisper_model, reselect=args.select_whisper)
    print(f"Loading model: {model_path.name}...")
    analyzer = TechBSAnalyzer(model_path=str(model_path))
    print(f"  device: {analyzer.device}")
    scorer = ContextScorer(analyzer, context_samples(args.context_seconds, args.chunk_seconds))
    print(f"Loading Whisper ({whisper_model})...")

    # ── Model debugger setup (before analysis so model selection doesn't interrupt results) ──
    debugger = None
    if _HAS_DEBUGGER and getattr(args, "debug_model", False):
        # Resolve provider/model: CLI flags > saved config > default (ollama)
        cfg = load_llm_config()
        provider = args.llm_provider or cfg.get("provider", "ollama")
        model    = args.llm_model    or cfg.get("model")

        debugger = ModelDebugger(provider=provider, model=model, domain_info=model_info)

        if provider == "ollama" and not model:
            # No saved model yet — show picker (will save after selection)
            debugger.model = debugger.select_ollama_model()
        else:
            debugger.console.print(
                f"[dim]LLM: {provider} / {debugger.model}"
                + (" (saved preference)" if cfg else "") + "[/]"
            )

    # Transcript must be saved if we need it for the model debugger
    need_transcript = args.transcript or getattr(args, "debug_model", False)

    # ── microphone mode ───────────────────────────────────────────────────────
    if args.mic:
        mic = MicTranscriber(
            model_name=whisper_model,
            chunk_seconds=args.chunk_seconds,
        )
        print(f"  device: {mic.device}")
        mic.start()  # begin recording immediately while UI initialises
        ui = TechBSUI(filename="Live Microphone", model_name=model_path.name, domain=model_domain, is_live=True)
        skipper = SkipController()
        skipper.start()
        try:
            transcript_path = ui.run(mic.transcribe_chunks(stop_event=skipper.quit_event), scorer, skipper, save_transcript=need_transcript)
        finally:
            skipper.stop()
            mic.stop()
        _run_debugger(debugger, transcript_path, keep=args.transcript)
        return

    # ── URL mode: download first ──────────────────────────────────────────────
    tmp_audio_path = None
    if args.url:
        tmp_audio_path = download_url(args.url)
        audio_path = tmp_audio_path
    else:
        audio_path = Path(args.file)
        if not audio_path.exists():
            print(f"Error: audio file not found: {audio_path}", file=sys.stderr)
            sys.exit(1)

    # ── file / URL mode ───────────────────────────────────────────────────────
    transcriber = AudioTranscriber(model_name=whisper_model)
    print(f"  device: {transcriber.device}")
    ui = TechBSUI(filename=audio_path.name, model_name=model_path.name, domain=model_domain,
                  duration=lambda: transcriber.duration)

    skipper = None
    player = None
    if not args.no_play:
        # Pre-transcribe the first chunk so audio playback and analysis start together.
        # Without this, audio starts immediately but the UI shows nothing until
        # Whisper finishes transcribing chunk 0 (typically 2-5 seconds into playback).
        print("Preparing first chunk...")
        chunk_iter = transcriber.transcribe_chunks(str(audio_path), args.chunk_seconds)
        first_chunk = next(chunk_iter, None)

        skipper = SkipController()
        skipper.start()
        player = AudioPlayer(audio_path)
        player.play()
        start_time = time.monotonic()
        seeded = itertools.chain([first_chunk], chunk_iter) if first_chunk else chunk_iter
        chunk_gen = realtime_sync(
            seeded, start_time, skipper, player, transcriber, args.chunk_seconds
        )
    else:
        chunk_gen = transcriber.transcribe_chunks(str(audio_path), args.chunk_seconds)

    try:
        transcript_path = ui.run(chunk_gen, scorer, skipper, save_transcript=need_transcript)
    finally:
        if skipper:
            skipper.stop()
        if player:
            player.stop()
        if tmp_audio_path is not None:
            shutil.rmtree(tmp_audio_path.parent, ignore_errors=True)

    _run_debugger(debugger, transcript_path, keep=args.transcript)


def cli():
    """Console-script entry point (the `techbs` command)."""
    try:
        main()
    except KeyboardInterrupt:
        # Ensure terminal is restored if Rich's alternate screen didn't exit cleanly
        Console().print("\n[dim]Interrupted.[/]")
        raise SystemExit(0)


if __name__ == "__main__":
    cli()
