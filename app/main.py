#!/usr/bin/env python3
"""
TechBS Analyzer
Usage:
    python main.py --file <audio_file> [--whisper-model base] [--chunk-seconds 15]
    python main.py --url <url> [--whisper-model base] [--chunk-seconds 15]
    python main.py --mic [--whisper-model base] [--chunk-seconds 15]
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

# Ensure imports work when run from any directory
sys.path.insert(0, str(Path(__file__).parent))

from analyzer import TechBSAnalyzer
from version import VERSION
from mic_transcriber import MicTranscriber
from model_updater import ModelUpdater
from rich.console import Console
from rich.table import Table
from rich import box
from skip import SkipController
from model_debugger import ModelDebugger, load_llm_config
from transcriber import AudioTranscriber
from ui import TechBSUI

MODELS_DIR = Path(__file__).parent.parent / "models"


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


def select_model() -> tuple[Path, dict]:
    """Print available models and prompt the user to pick one.
    Returns (model_path, info) where info is the contents of info.json (may be empty).
    """
    console = Console()
    models = discover_models()

    if not models:
        console.print(f"[red]No models found in {MODELS_DIR}[/]")
        sys.exit(1)

    infos = [load_model_info(m) for m in models]

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
        except (ValueError, EOFError):
            pass
        console.print(f"[red]Enter a number between 1 and {len(models)}[/]")


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
            ps_cmd = (
                "Add-Type -AssemblyName presentationCore; "
                "$m = New-Object System.Windows.Media.MediaPlayer; "
                f"$m.Open([Uri]'{safe_path}'); "
                "Start-Sleep -Milliseconds 300; "
                f"$m.Position = [TimeSpan]::FromMilliseconds({seek_ms}); "
                "$m.Play(); "
                "Start-Sleep -Seconds 7200"
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
        "--whisper-model",
        default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size (default: base)",
    )
    parser.add_argument(
        "--chunk-seconds",
        type=int,
        default=15,
        help="Seconds of audio per analysis chunk (default: 15)",
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
        "--update-models",
        action="store_true",
        help="Check for model updates and download if available",
    )
    parser.add_argument(
        "--check-updates",
        action="store_true",
        help="Check for model updates without downloading",
    )
    parser.add_argument(
        "--manifest-url",
        default=None,
        help="Override the manifest URL for --update-models / --check-updates",
    )
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

    if args.update_models or args.check_updates:
        kw = {"manifest_url": args.manifest_url} if args.manifest_url else {}
        ModelUpdater(models_dir=MODELS_DIR, **kw).run(check_only=args.check_updates)
        return

    if not args.mic and not args.file and not args.url:
        parser.error("provide --file <path>, --url <url>, or --mic")

    model_path, model_info = select_model()
    model_description = model_info.get("description", "")
    print(f"Loading model: {model_path.name}...")
    analyzer = TechBSAnalyzer(model_path=str(model_path))
    print(f"  device: {analyzer.device}")
    print(f"Loading Whisper ({args.whisper_model})...")

    # ── Model debugger setup (before analysis so model selection doesn't interrupt results) ──
    debugger = None
    if args.debug_model:
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
    need_transcript = args.transcript or args.debug_model

    # ── microphone mode ───────────────────────────────────────────────────────
    if args.mic:
        mic = MicTranscriber(
            model_size=args.whisper_model,
            chunk_seconds=args.chunk_seconds,
        )
        mic.start()  # begin recording immediately while UI initialises
        ui = TechBSUI(filename="Live Microphone", model_name=model_path.name, model_description=model_description)
        skipper = SkipController()
        skipper.start()
        try:
            transcript_path = ui.run(mic.transcribe_chunks(stop_event=skipper.quit_event), analyzer, skipper, save_transcript=need_transcript)
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
    transcriber = AudioTranscriber(model_size=args.whisper_model)
    ui = TechBSUI(filename=audio_path.name, model_name=model_path.name, model_description=model_description)

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
        transcript_path = ui.run(chunk_gen, analyzer, skipper, save_transcript=need_transcript)
    finally:
        if skipper:
            skipper.stop()
        if player:
            player.stop()
        if tmp_audio_path is not None:
            shutil.rmtree(tmp_audio_path.parent, ignore_errors=True)

    _run_debugger(debugger, transcript_path, keep=args.transcript)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Ensure terminal is restored if Rich's alternate screen didn't exit cleanly
        from rich.console import Console
        Console().print("\n[dim]Interrupted.[/]")
        raise SystemExit(0)
