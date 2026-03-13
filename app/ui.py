"""
Rich terminal UI for the TechBS live analyzer — 3-label version.
Labels: signal (green) | neutral (blue) | bs (red)
"""
import json
import datetime
from pathlib import Path
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from skip import SkipController


@dataclass
class ChunkResult:
    index: int
    start: float
    end: float
    transcript: str
    signal_score: float
    neutral_score: float
    bs_score: float
    label: str  # "signal" | "neutral" | "bs"


@dataclass
class UIState:
    filename: str = ""
    model_name: str = ""
    model_description: str = ""
    chunks: list[ChunkResult] = field(default_factory=list)
    current_transcript: str = ""
    status: str = "Initializing..."
    done: bool = False
    skip_hint: str = ""


# ── colour helpers ────────────────────────────────────────────────────────────

LABEL_COLOR = {"signal": "green", "neutral": "blue", "bs": "red"}
LABEL_DISPLAY = {"signal": "LEGIT", "neutral": "NEUTRAL", "bs": "BS"}


def _label_text(label: str) -> Text:
    color = LABEL_COLOR.get(label, "white")
    return Text(f"[{LABEL_DISPLAY.get(label, label.upper())}]", style=f"bold {color}")


def _score_bar(score: float, color: str, width: int = 20) -> Text:
    filled = round(score * width)
    empty = width - filled
    bar = Text()
    bar.append("█" * filled, style=color)
    bar.append("░" * empty, style="dim")
    bar.append(f"  {score * 100:.0f}%", style=f"{color} bold")
    return bar


def _chunk_color(chunk: ChunkResult) -> str:
    return LABEL_COLOR.get(chunk.label, "white")


# ── verdict helpers ───────────────────────────────────────────────────────────

VERDICT_WINDOW = 5


def _rolling_counts(chunks: list[ChunkResult]) -> dict[str, int]:
    window = chunks[-VERDICT_WINDOW:]
    counts = {"signal": 0, "neutral": 0, "bs": 0}
    for c in window:
        counts[c.label] = counts.get(c.label, 0) + 1
    return counts


def _verdict_label(counts: dict[str, int]) -> Text:
    total = sum(counts.values()) or 1
    bs_frac = counts["bs"] / total
    sig_frac = counts["signal"] / total
    if counts["neutral"] / total > 0.6:
        return Text("OFF-TOPIC/SMALL TALK", style="bold blue")
    if bs_frac >= 0.6:
        return Text("TOTAL BS", style="bold red reverse")
    if bs_frac >= 0.4:
        return Text("SMELLS LIKE BS", style="bold red")
    if sig_frac >= 0.6:
        return Text("LEGIT CONTENT", style="bold green")
    return Text("MIXED — SOME GOOD STUFF", style="bold yellow")


# ── panels ────────────────────────────────────────────────────────────────────

def _verdict_panel(state: UIState) -> Panel:
    chunks = state.chunks
    content = Text()

    # Current chunk bars
    content.append("\n  CURRENT CHUNK\n", style="bold white")
    if chunks:
        c = chunks[-1]
        color = LABEL_COLOR.get(c.label, "white")
        content.append(f"  ", style="default")
        content.append(_label_text(c.label))
        content.append(f"  {c.signal_score * 100:.0f}% legit · {c.neutral_score * 100:.0f}% neutral · {c.bs_score * 100:.0f}% bs\n", style=f"dim {color}")
    else:
        content.append("  —\n", style="dim")

    # Rolling verdict
    content.append("\n\n  RECENT VERDICT\n  ", style="bold white")
    if chunks:
        counts = _rolling_counts(chunks)
        window = chunks[-VERDICT_WINDOW:]
        content.append(_verdict_label(counts))
        content.append(
            f"\n  (last {len(window)} chunk{'s' if len(window) != 1 else ''}: "
            f"[green]{counts['signal']} legit[/] · "
            f"[blue]{counts['neutral']} neutral[/] · "
            f"[red]{counts['bs']} bs[/])\n",
        )
    else:
        content.append(Text("Waiting for data...\n", style="dim"))

    # Totals
    if chunks:
        total = len(chunks)
        sig = sum(1 for c in chunks if c.label == "signal")
        neu = sum(1 for c in chunks if c.label == "neutral")
        bs  = sum(1 for c in chunks if c.label == "bs")
        content.append(
            f"\n  ALL CHUNKS ({total}): "
            f"[green]{sig} legit[/] · [blue]{neu} neutral[/] · [red]{bs} bs[/]\n",
        )

    content.append(f"\n  {state.status}\n", style="dim italic")
    if state.skip_hint:
        content.append(f"  {state.skip_hint}\n", style="dim cyan")

    model_tag = f" [dim]· {state.model_name}[/]" if state.model_name else ""
    return Panel(content, title=f"[bold cyan]TechBS Meter[/]{model_tag}", border_style="cyan")


def _transcript_panel(state: UIState) -> Panel:
    lines = []
    for chunk in state.chunks[-6:]:
        color = _chunk_color(chunk)
        time_str = f"[{chunk.start:.0f}s–{chunk.end:.0f}s]"
        label_str = LABEL_DISPLAY.get(chunk.label, chunk.label.upper())
        snippet = chunk.transcript[:120].replace("\n", " ")
        if len(chunk.transcript) > 120:
            snippet += "..."
        lines.append(f"[dim]{time_str}[/] [{color} bold]{label_str}[/]\n{snippet}\n")

    content = "\n".join(lines) if lines else "[dim]Waiting for transcription...[/]"
    subtitle = f"[dim]{state.model_description}[/]" if state.model_description else None
    return Panel(
        content,
        title=f"[bold cyan]Live Transcript — {state.filename}[/]",
        subtitle=subtitle,
        border_style="cyan",
        padding=(0, 1),
    )


def _history_table(state: UIState) -> Panel:
    table = Table(box=box.SIMPLE, expand=True, show_header=True, header_style="bold cyan")
    table.add_column("#", width=4, style="dim")
    table.add_column("Time", width=12)
    table.add_column("Label", width=10)
    table.add_column("Legit", width=8)
    table.add_column("Neutral", width=8)
    table.add_column("BS", width=8)
    table.add_column("Transcript snippet")

    for chunk in state.chunks[-8:]:
        color = _chunk_color(chunk)
        label_str = LABEL_DISPLAY.get(chunk.label, chunk.label.upper())
        snippet = chunk.transcript[:55].replace("\n", " ")
        if len(chunk.transcript) > 55:
            snippet += "..."
        table.add_row(
            str(chunk.index + 1),
            f"{chunk.start:.0f}s–{chunk.end:.0f}s",
            f"[{color} bold]{label_str}[/]",
            f"[green]{chunk.signal_score * 100:.0f}%[/]",
            f"[blue]{chunk.neutral_score * 100:.0f}%[/]",
            f"[red]{chunk.bs_score * 100:.0f}%[/]",
            snippet,
        )

    return Panel(table, title="[bold cyan]Chunk History[/]", border_style="cyan")


def make_layout(state: UIState) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="top", ratio=3),
        Layout(name="bottom", ratio=2),
    )
    layout["top"].split_row(
        Layout(_verdict_panel(state), name="meter", ratio=1),
        Layout(_transcript_panel(state), name="transcript", ratio=2),
    )
    layout["bottom"].update(_history_table(state))
    return layout


# ── main UI class ─────────────────────────────────────────────────────────────

class TechBSUI:
    def __init__(self, filename: str, model_name: str = "", model_description: str = ""):
        self.state = UIState(filename=filename, model_name=model_name, model_description=model_description)
        self.console = Console()

    def run(self, chunk_iterator, analyzer, skipper: "SkipController | None" = None, save_transcript: bool = False) -> Optional[Path]:
        is_live = self.state.filename == "Live Microphone"
        if skipper:
            self.state.skip_hint = "[Q] Quit" if is_live else "[S/Space] Skip chunk  [Q] Quit"

        self._save_transcript = save_transcript
        self._transcript_path: Optional[Path] = None

        with Live(make_layout(self.state), console=self.console, refresh_per_second=4, screen=False) as live:
            self.state.status = "Listening on microphone..." if is_live else "Analyzing..."
            live.update(make_layout(self.state))

            try:
                for idx, start, end, text in chunk_iterator:
                    if skipper and skipper.quit_requested:
                        self.state.status = "Stopped by user."
                        live.update(make_layout(self.state))
                        break

                    self.state.status = f"Transcribing... ({start:.0f}s–{end:.0f}s)" if is_live else f"Analyzing chunk {idx + 1} ({start:.0f}s–{end:.0f}s)..."
                    live.update(make_layout(self.state))

                    if text:
                        result = analyzer.score(text)
                        chunk = ChunkResult(
                            index=idx,
                            start=start,
                            end=end,
                            transcript=text,
                            signal_score=result["signal_score"],
                            neutral_score=result["neutral_score"],
                            bs_score=result["bs_score"],
                            label=result["label"],
                        )
                        self.state.chunks.append(chunk)
                        label_str = LABEL_DISPLAY.get(result["label"], result["label"].upper())
                        self.state.status = f"Chunk {idx + 1}: {label_str}"
                        live.update(make_layout(self.state))

                self.state.status = "Analysis complete."
                self.state.done = True
                live.update(make_layout(self.state))

            except KeyboardInterrupt:
                self.state.status = "Interrupted."
                live.update(make_layout(self.state))
                # Live context manager exits cleanly — terminal is restored before we return

        self._print_summary()
        return self._transcript_path

    def _overall_rating(self, by_label: dict, total: int) -> tuple[str, str]:
        """Return (rating_text, rich_style) based on label distribution."""
        sig_pct  = len(by_label["signal"])  / total
        bs_pct   = len(by_label["bs"])      / total
        neu_pct  = len(by_label["neutral"]) / total

        # Ignore neutral (off-topic) chunks when judging quality
        content_chunks = total - len(by_label["neutral"])
        if content_chunks == 0:
            return "NO TECHNICAL CONTENT", "bold blue"

        sig_of_content = len(by_label["signal"]) / content_chunks
        bs_of_content  = len(by_label["bs"])      / content_chunks

        if neu_pct > 0.7:
            return "OFF-TOPIC — Mostly greetings and small talk, nothing technical", "bold blue"
        if sig_of_content >= 0.75:
            return "HIGHLY TECHNICAL — Excellent technical depth throughout", "bold green"
        if sig_of_content >= 0.5:
            return "SOLID CONTENT — Good technical material with some filler", "bold green"
        if bs_of_content >= 0.75:
            return "TOTAL BS — Marketing and hype, self promotion, very little substance", "bold red reverse"
        if bs_of_content >= 0.5:
            return "MOSTLY BS — Heavy on buzzwords, light on technical depth", "bold red"
        return "MIXED — Some useful technical content buried in fluff", "bold yellow"

    def _print_summary(self):
        if not self.state.chunks:
            self.console.print("[yellow]No chunks analyzed.[/]")
            return

        chunks = self.state.chunks
        total = len(chunks)
        by_label: dict[str, list] = {"signal": [], "neutral": [], "bs": []}
        for c in chunks:
            by_label[c.label].append(c)

        sig_pct = len(by_label["signal"]) / total
        bs_pct  = len(by_label["bs"])     / total
        neu_pct = len(by_label["neutral"])/ total
        avg_sig = sum(c.signal_score for c in chunks) / total
        avg_bs  = sum(c.bs_score     for c in chunks) / total

        rating_text, rating_style = self._overall_rating(by_label, total)

        model_tag = f" [dim]· {self.state.model_name}[/]" if self.state.model_name else ""
        self.console.rule(f"[bold cyan]TechBS Final Report[/]{model_tag}")
        self.console.print(f"\n[bold]File:[/] {self.state.filename}")
        self.console.print(f"[bold]Duration:[/] {chunks[-1].end:.0f}s  ·  [bold]Chunks analyzed:[/] {total}\n")

        # Overall verdict
        self.console.print(f"  OVERALL VERDICT", style="bold white")
        self.console.print(f"  {rating_text}\n", style=rating_style)

        # Score breakdown
        self.console.print(
            f"  [green]Legit   {sig_pct*100:5.0f}%[/]  (avg confidence {avg_sig*100:.0f}%)\n"
            f"  [blue]Neutral {neu_pct*100:5.0f}%[/]  (off-topic / small talk)\n"
            f"  [red]BS      {bs_pct*100:5.0f}%[/]  (avg confidence {avg_bs*100:.0f}%)\n"
        )

        if self._save_transcript:
            self._transcript_path = self._save_analysis(chunks, rating_text)
            self.console.print(f"[dim]Transcript saved → {self._transcript_path}[/]\n")

    def _save_analysis(self, chunks: list, rating: str) -> Path:
        """Save full transcript and scores to a JSON file for later LLM analysis."""
        stem = Path(self.state.filename).stem
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = Path(f"{stem}_{ts}_techbs.json")

        total = len(chunks)
        by_label: dict[str, list] = {"signal": [], "neutral": [], "bs": []}
        for c in chunks:
            by_label[c.label].append(c)

        data = {
            "file": self.state.filename,
            "analyzed_at": datetime.datetime.now().isoformat(),
            "overall_verdict": rating,
            "summary": {
                "total_chunks": total,
                "duration_seconds": chunks[-1].end,
                "legit_count":   len(by_label["signal"]),
                "neutral_count": len(by_label["neutral"]),
                "bs_count":      len(by_label["bs"]),
                "legit_pct":   round(len(by_label["signal"])  / total * 100, 1),
                "neutral_pct": round(len(by_label["neutral"]) / total * 100, 1),
                "bs_pct":      round(len(by_label["bs"])      / total * 100, 1),
                "avg_legit_confidence": round(sum(c.signal_score for c in chunks) / total, 3),
                "avg_bs_confidence":    round(sum(c.bs_score     for c in chunks) / total, 3),
            },
            "chunks": [
                {
                    "index":         c.index,
                    "start":         round(c.start, 1),
                    "end":           round(c.end, 1),
                    "label":         c.label,
                    "legit_score":   round(c.signal_score,  3),
                    "neutral_score": round(c.neutral_score, 3),
                    "bs_score":      round(c.bs_score,      3),
                    "transcript":    c.transcript,
                }
                for c in chunks
            ],
        }

        out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return out_path
