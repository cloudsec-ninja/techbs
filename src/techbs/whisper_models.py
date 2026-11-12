"""Choosing the Whisper transcription model.

The user picks a model once (interactive picker on first run); the choice is
saved to config.json. --whisper-model overrides it for a single run and
--select-whisper shows the picker again.

This module avoids importing faster-whisper or torch so it stays cheap to
import and easy to test.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

CONFIG_KEY = "whisper_model"

# Every name faster-whisper 1.2 accepts (faster_whisper.available_models()).
KNOWN_MODELS = (
    "tiny.en", "tiny", "base.en", "base", "small.en", "small",
    "medium.en", "medium", "large-v1", "large-v2", "large-v3", "large",
    "distil-large-v2", "distil-medium.en", "distil-small.en",
    "distil-large-v3", "distil-large-v3.5", "large-v3-turbo", "turbo",
)


@dataclass(frozen=True)
class WhisperChoice:
    name: str
    download: str
    speed: str
    accuracy: str
    note: str


# Models shown in the picker. Any KNOWN_MODELS name can still be typed in.
CATALOG = (
    WhisperChoice("tiny",            "75 MB",  "fastest",          "rough",     "Runs anywhere; expect transcription errors"),
    WhisperChoice("base",            "145 MB", "very fast",        "fair",      "Fine on CPU; TechBS's previous default"),
    WhisperChoice("small",           "485 MB", "fast",             "good",      "Best balance on CPU"),
    WhisperChoice("medium",          "1.5 GB", "slow on CPU",      "very good", "GPU recommended"),
    WhisperChoice("large-v3-turbo",  "1.6 GB", "fast on GPU",      "excellent", "Best balance on GPU"),
    WhisperChoice("distil-large-v3", "1.5 GB", "fast on GPU",      "excellent", "English only"),
    WhisperChoice("large-v3",        "3.1 GB", "slowest",          "best",      "GPU strongly recommended"),
)


class WhisperSelectionError(Exception):
    """Raised when no model can be chosen (bad name, or no interactive input)."""


def is_valid_model(name: str) -> bool:
    """A known model name, a HuggingFace repo id (org/name), or a local model folder."""
    return name in KNOWN_MODELS or "/" in name or Path(name).is_dir()


def resolve_whisper_model(
    cli_value: str | None,
    reselect: bool,
    config: dict,
    pick: Callable[[], str],
    save: Callable[[str], None],
) -> str:
    """Decide which Whisper model to use for this run.

    Order: --whisper-model (this run only) > --select-whisper / no saved choice
    (show the picker and save the answer) > saved choice.
    """
    if cli_value:
        if not is_valid_model(cli_value):
            raise WhisperSelectionError(
                f"Unknown Whisper model '{cli_value}'. Choose one of: {', '.join(KNOWN_MODELS)}"
            )
        return cli_value

    saved = config.get(CONFIG_KEY)
    if reselect or not saved:
        name = pick()
        save(name)
        return name
    return saved


def parse_pick(answer: str) -> str | None:
    """Turn picker input (a number from the list, or a model name) into a model name."""
    answer = answer.strip()
    if answer.isdigit():
        idx = int(answer) - 1
        return CATALOG[idx].name if 0 <= idx < len(CATALOG) else None
    return answer if answer and is_valid_model(answer) else None


def pick_interactively(gpu_name: str | None, current: str | None = None) -> str:
    """Show the model table and ask the user to choose. Returns the model name."""
    from rich import box
    from rich.console import Console
    from rich.table import Table

    console = Console()
    console.print()
    console.print("[bold cyan]Choose a Whisper transcription model[/]")
    if gpu_name:
        console.print(f"[dim]GPU detected: {gpu_name}. Larger models will run well.[/]")
    else:
        console.print("[dim]No NVIDIA GPU detected, so transcription runs on CPU. "
                      "tiny, base or small are the practical choices.[/]")
    if current:
        console.print(f"[dim]Current choice: {current}[/]")

    table = Table(box=box.SIMPLE, padding=(0, 1))
    table.add_column("#", style="bold", width=3)
    table.add_column("Model", style="bold cyan")
    table.add_column("Download", justify="right")
    table.add_column("Speed")
    table.add_column("Accuracy")
    table.add_column("Notes", style="dim")
    for i, m in enumerate(CATALOG, 1):
        table.add_row(str(i), m.name, m.download, m.speed, m.accuracy, m.note)
    console.print(table)
    console.print("[dim]The model downloads once on first use. You can also type any "
                  "faster-whisper model name (e.g. small.en).[/]")

    while True:
        try:
            answer = input(f"Select model [1-{len(CATALOG)}] or name: ")
        except EOFError:
            raise WhisperSelectionError(
                "No interactive input available. Pass --whisper-model <name> "
                "(e.g. --whisper-model small)."
            ) from None
        name = parse_pick(answer)
        if name:
            return name
        console.print(f"[red]Enter a number between 1 and {len(CATALOG)}, or a model name.[/]")
