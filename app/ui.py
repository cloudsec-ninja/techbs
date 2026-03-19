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
    confidence: str = "HIGH"  # "HIGH" | "MEDIUM" | "LOW"
    confidence_margin: float = 1.0
    buzzwords: list[str] = field(default_factory=list)


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


CONFIDENCE_COLOR = {"HIGH": "green", "MEDIUM": "yellow", "LOW": "red"}


def _confidence_tag(confidence: str) -> str:
    color = CONFIDENCE_COLOR.get(confidence, "white")
    return f"[{color}]{confidence}[/{color}]"


def _chunk_color(chunk: ChunkResult) -> str:
    return LABEL_COLOR.get(chunk.label, "white")


def _buzzword_snippet(transcript: str, buzzwords: list[str], max_len: int = 120) -> Text:
    """Build a Rich Text snippet with buzzwords highlighted in magenta bold."""
    snippet_str = transcript[:max_len].replace("\n", " ")
    if len(transcript) > max_len:
        snippet_str += "..."
    if not buzzwords:
        return Text(snippet_str)

    import re
    # Build a single pattern matching any buzzword (case-insensitive)
    escaped = [re.escape(bw) for bw in buzzwords]
    pattern = re.compile("(" + "|".join(escaped) + ")", re.IGNORECASE)

    result = Text()
    last = 0
    for m in pattern.finditer(snippet_str):
        if m.start() > last:
            result.append(snippet_str[last:m.start()])
        result.append(m.group(), style="bold magenta")
        last = m.end()
    if last < len(snippet_str):
        result.append(snippet_str[last:])
    return result


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
        conf_color = CONFIDENCE_COLOR.get(c.confidence, "white")
        content.append(f"  ", style="default")
        content.append(_label_text(c.label))
        content.append(f"  {c.signal_score * 100:.0f}% legit · {c.neutral_score * 100:.0f}% neutral · {c.bs_score * 100:.0f}% bs", style=f"dim {color}")
        content.append(f"  conf: ", style="dim")
        content.append(c.confidence, style=f"bold {conf_color}")
        content.append("\n")
        if c.buzzwords:
            content.append(f"  buzzwords: ", style="dim")
            content.append(", ".join(c.buzzwords), style="bold magenta")
            content.append("\n")
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
    content = Text()
    if not state.chunks:
        content.append("Waiting for transcription...", style="dim")
    else:
        for chunk in state.chunks[-6:]:
            color = _chunk_color(chunk)
            conf_color = CONFIDENCE_COLOR.get(chunk.confidence, "white")
            time_str = f"[{chunk.start:.0f}s\u2013{chunk.end:.0f}s]"
            label_str = LABEL_DISPLAY.get(chunk.label, chunk.label.upper())
            content.append(time_str, style="dim")
            content.append(f" {label_str}", style=f"bold {color}")
            content.append(f" {chunk.confidence}", style=f"{conf_color}")
            content.append("\n")
            content.append_text(_buzzword_snippet(chunk.transcript, chunk.buzzwords))
            content.append("\n\n")
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
    table.add_column("Conf", width=8)
    table.add_column("Legit", width=8)
    table.add_column("Neutral", width=8)
    table.add_column("BS", width=8)
    table.add_column("Buzzwords", width=20)
    table.add_column("Transcript snippet")

    for chunk in state.chunks[-8:]:
        color = _chunk_color(chunk)
        conf_color = CONFIDENCE_COLOR.get(chunk.confidence, "white")
        label_str = LABEL_DISPLAY.get(chunk.label, chunk.label.upper())
        snippet = chunk.transcript[:45].replace("\n", " ")
        if len(chunk.transcript) > 45:
            snippet += "..."
        bw_str = ", ".join(chunk.buzzwords[:3])
        if len(chunk.buzzwords) > 3:
            bw_str += f" +{len(chunk.buzzwords) - 3}"
        table.add_row(
            str(chunk.index + 1),
            f"{chunk.start:.0f}s\u2013{chunk.end:.0f}s",
            f"[{color} bold]{label_str}[/]",
            f"[{conf_color}]{chunk.confidence}[/{conf_color}]",
            f"[green]{chunk.signal_score * 100:.0f}%[/]",
            f"[blue]{chunk.neutral_score * 100:.0f}%[/]",
            f"[red]{chunk.bs_score * 100:.0f}%[/]",
            f"[magenta]{bw_str}[/]" if bw_str else "[dim]—[/]",
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
                        confidence=result["confidence"],
                        confidence_margin=result["confidence_margin"],
                        buzzwords=result["buzzwords"],
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
        # Ignore neutral (off-topic) chunks when judging quality
        content_chunks = total - len(by_label["neutral"])
        neutral_pct = len(by_label["neutral"]) / total if total else 0
        if content_chunks == 0 or neutral_pct >= 0.90:
            return "OFF-TOPIC — No domain content detected", "bold blue"

        sig_of_content = len(by_label["signal"]) / content_chunks
        bs_of_content  = len(by_label["bs"])      / content_chunks

        # Judge based on the ratio of legit-to-BS among actual content chunks.
        # High neutral % doesn't get a free pass — if what little content exists is BS, say so.
        if sig_of_content >= 0.75:
            return "HIGHLY TECHNICAL — Excellent technical depth throughout", "bold green"
        if bs_of_content >= 0.75:
            return "TOTAL BS — Marketing, hype, self promotion, and very little substance", "bold red reverse"
        if sig_of_content > 0.6:
            return "SOLID CONTENT — Good technical material with some filler", "bold green"
        if bs_of_content > 0.6:
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
            f"  [green]Legit   {sig_pct*100:5.0f}%[/]  (avg score {avg_sig*100:.0f}%)\n"
            f"  [blue]Neutral {neu_pct*100:5.0f}%[/]  (off-topic / small talk)\n"
            f"  [red]BS      {bs_pct*100:5.0f}%[/]  (avg score {avg_bs*100:.0f}%)\n"
        )

        # Model confidence breakdown
        high   = sum(1 for c in chunks if c.confidence == "HIGH")
        medium = sum(1 for c in chunks if c.confidence == "MEDIUM")
        low    = sum(1 for c in chunks if c.confidence == "LOW")
        self.console.print(
            f"  Model confidence:  "
            f"[green]{high} HIGH[/] · [yellow]{medium} MEDIUM[/] · [red]{low} LOW[/]"
        )
        if low > 0:
            self.console.print(f"  [dim]({low} chunk{'s' if low != 1 else ''} where the model was uncertain — review these for accuracy)[/]")

        # Buzzword summary
        all_bw = [bw for c in chunks for bw in c.buzzwords]
        if all_bw:
            from collections import Counter
            bw_counts = Counter(bw.lower() for bw in all_bw).most_common(10)
            bw_display = ", ".join(f"{w} ({n})" for w, n in bw_counts)
            self.console.print(f"\n  [bold magenta]Buzzwords detected:[/] {len(all_bw)} total across {sum(1 for c in chunks if c.buzzwords)} chunks")
            self.console.print(f"  [magenta]{bw_display}[/]")

        self.console.print()

        if self._save_transcript:
            self._transcript_path = self._save_analysis(chunks, rating_text)
            self.console.print(f"[dim]Transcript saved → {self._transcript_path}[/]\n")

    def _save_analysis(self, chunks: list, rating: str) -> Path:
        """Save full transcript and scores to a JSON file for later LLM analysis."""
        stem = Path(self.state.filename).stem
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = Path(f"{stem}_{ts}_techbs.json")

        total = len(chunks)
        if total == 0:
            out_path.write_text(json.dumps({"file": self.state.filename, "error": "no chunks analyzed"}, indent=2))
            return out_path

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
                    "index":            c.index,
                    "start":            round(c.start, 1),
                    "end":              round(c.end, 1),
                    "label":            c.label,
                    "confidence":       c.confidence,
                    "confidence_margin": c.confidence_margin,
                    "legit_score":      round(c.signal_score,  3),
                    "neutral_score":    round(c.neutral_score, 3),
                    "bs_score":         round(c.bs_score,      3),
                    "buzzwords":        c.buzzwords,
                    "transcript":       c.transcript,
                }
                for c in chunks
            ],
        }

        out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return out_path
