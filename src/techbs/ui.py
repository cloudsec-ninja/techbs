"""
Rich terminal UI for TechBS: a full-screen live dashboard while analysing, and
a final report printed to the terminal afterwards.

Labels: signal → LEGIT (green) | neutral → NEUTRAL (grey) | bs → BS (red)
"""
import datetime
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional, Sequence

from rich import box
from rich.console import Console, ConsoleOptions, Group, RenderResult
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from .pipeline import ChunkResult
from .labels import field_name
from .verdict import detected_field, format_time, overall_verdict, rolling_verdict, tally, top_moments

if TYPE_CHECKING:
    from .skip import SkipController


@dataclass
class UIState:
    filename: str = ""
    model_name: str = ""
    domain: str = ""
    is_live: bool = False  # True for live mic input, False for file/URL
    chunks: list[ChunkResult] = field(default_factory=list)
    status: str = "Starting..."
    done: bool = False
    key_hint: str = ""
    duration: Optional[float] = None  # total audio length, when known


# ── colours ───────────────────────────────────────────────────────────────────

LABEL_COLOR = {"signal": "green", "neutral": "grey62", "bs": "red"}
LABEL_DISPLAY = {"signal": "LEGIT", "neutral": "NEUTRAL", "bs": "BS"}
TONE_STYLE = {"legit": "bold green", "bs": "bold red", "mixed": "bold yellow", "neutral": "bold grey70"}
TONE_BORDER = {"legit": "green", "bs": "red", "mixed": "yellow", "neutral": "grey50"}
CONFIDENCE_COLOR = {"HIGH": "green", "MEDIUM": "yellow", "LOW": "red"}

TIMELINE_BLOCK = "█"
TIMELINE_EMPTY = "·"


def _label(label: str) -> Text:
    return Text(LABEL_DISPLAY.get(label, label.upper()), style=f"bold {LABEL_COLOR.get(label, 'white')}")


def _bar(fraction: float, color: str, width: int = 12) -> Text:
    filled = max(0, min(width, round(fraction * width)))
    bar = Text("█" * filled, style=color)
    bar.append("░" * (width - filled), style="grey30")
    return bar


def _highlight(text: str, buzzwords: Sequence[str]) -> Text:
    """Transcript text with buzzwords in bold magenta."""
    out = Text(text.replace("\n", " "))
    if buzzwords:
        pattern = re.compile("|".join(re.escape(b) for b in buzzwords), re.IGNORECASE)
        out.highlight_regex(pattern, style="bold magenta")
    return out


def _shares_line(chunks: Sequence[ChunkResult]) -> Text:
    """'12% legit · 30% neutral · 58% BS' by audio time."""
    t = tally(chunks)
    total = t.seconds or 1
    line = Text()
    line.append(f"{t.legit_seconds / total:.0%} legit", style=LABEL_COLOR["signal"])
    line.append(" · ", style="dim")
    line.append(f"{t.neutral_seconds / total:.0%} neutral", style=LABEL_COLOR["neutral"])
    line.append(" · ", style="dim")
    line.append(f"{t.bs_seconds / total:.0%} BS", style=LABEL_COLOR["bs"])
    return line


class Timeline:
    """One coloured block per slice of the talk, sized to the available width.

    With a known duration the full width is the whole talk and unanalysed time
    shows as dots. Without one (live mic) each block is one sample and the
    newest samples stay in view.
    """

    def __init__(self, chunks: Sequence[ChunkResult], duration: Optional[float]):
        self.chunks = chunks
        self.duration = duration

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        width = max(10, options.max_width)
        text = Text(no_wrap=True, overflow="crop")
        if self.duration:
            step = self.duration / width
            i = 0
            for cell in range(width):
                t = (cell + 0.5) * step
                while i < len(self.chunks) and self.chunks[i].end <= t:
                    i += 1
                if i < len(self.chunks) and self.chunks[i].start <= t:
                    text.append(TIMELINE_BLOCK, style=LABEL_COLOR.get(self.chunks[i].label, "white"))
                else:
                    text.append(TIMELINE_EMPTY, style="grey30")
        else:
            for c in self.chunks[-width:]:
                text.append(TIMELINE_BLOCK, style=LABEL_COLOR.get(c.label, "white"))
        yield text


# ── live dashboard ────────────────────────────────────────────────────────────

def _position(state: UIState) -> Text:
    pos = state.chunks[-1].end if state.chunks else 0.0
    if state.is_live:
        return Text.assemble(("● LIVE ", "bold red"), (format_time(pos), "bold"))
    if state.duration:
        return Text.assemble((format_time(min(pos, state.duration)), "bold"),
                             (f" / {format_time(state.duration)}", "dim"))
    return Text(format_time(pos), style="bold")


def _header_panel(state: UIState) -> Panel:
    title = Table.grid(expand=True)
    title.add_column()
    title.add_column(justify="right")
    name = Text.assemble(("TechBS", "bold cyan"), (f" · {state.model_name}" if state.model_name else "", "cyan"),
                         (f" · {state.filename}", "default"))
    field, share = detected_field(state.chunks)
    if field:
        name.append_text(Text.assemble(("  field: ", "dim"), (field_name(field), "bold"), (f" {share:.0%}", "dim")))
    title.add_row(name, _position(state))

    stats = Text(no_wrap=True, overflow="ellipsis")
    if state.chunks:
        last = state.chunks[-1]
        top = max(last.signal_score, last.neutral_score, last.bs_score)
        stats.append("NOW ", style="dim")
        stats.append_text(_label(last.label))
        stats.append(f" {top:.0%}", style=LABEL_COLOR.get(last.label, "white"))
        name, tone = rolling_verdict(state.chunks)
        stats.append("    LAST 5 ", style="dim")
        stats.append(name, style=TONE_STYLE[tone])
        stats.append("    SO FAR ", style="dim")
        stats.append_text(_shares_line(state.chunks))
    else:
        stats.append("Waiting for the first sample...", style="dim")

    return Panel(Group(title, stats, Timeline(state.chunks, state.duration)),
                 border_style="cyan", padding=(0, 1))


def _current_panel(state: UIState) -> Panel:
    if not state.chunks:
        return Panel(Text("The first sample will appear here.", style="dim"),
                     title="Current sample", border_style="grey50", padding=(1, 2))
    c = state.chunks[-1]
    color = LABEL_COLOR.get(c.label, "white")

    bars = Text(no_wrap=True, overflow="crop")
    for i, (key, score) in enumerate((("signal", c.signal_score), ("neutral", c.neutral_score), ("bs", c.bs_score))):
        if i:
            bars.append("   ")
        bars.append(f"{LABEL_DISPLAY[key].title() if key != 'bs' else 'BS'} ", style="dim")
        bars.append_text(_bar(score, LABEL_COLOR[key], width=10))
        bars.append(f" {score:4.0%}", style=LABEL_COLOR[key])

    parts = [bars]
    if c.buzzwords:
        parts.append(Text.assemble(("buzzwords: ", "dim"), (", ".join(c.buzzwords), "bold magenta")))
    parts.append(Text())
    parts.append(_highlight(c.transcript, c.buzzwords) if c.transcript.strip()
                 else Text("(no speech in this sample)", style="dim italic"))

    title = Text.assemble((f"{format_time(c.start)}–{format_time(c.end)}", "bold"), "  ", _label(c.label),
                          ("  ·  ", "dim"), (f"{c.confidence.lower()} confidence", CONFIDENCE_COLOR.get(c.confidence, "white")))
    return Panel(Group(*parts), title=title, title_align="left", border_style=color, padding=(0, 2))


def _earlier_panel(state: UIState) -> Panel:
    table = Table.grid(padding=(0, 2), expand=True)
    table.add_column(style="dim", no_wrap=True)
    table.add_column(no_wrap=True, width=7)
    table.add_column(no_wrap=True, overflow="ellipsis", ratio=1)
    for c in reversed(state.chunks[-41:-1]):  # newest first; the panel crops what doesn't fit
        snippet = c.transcript.replace("\n", " ").strip() or "(no speech)"
        table.add_row(format_time(c.start), _label(c.label), _highlight(snippet, c.buzzwords))
    body = table if state.chunks[:-1] else Text("Earlier samples will be listed here.", style="dim")
    return Panel(body, title="Earlier", title_align="left", border_style="grey50", padding=(0, 1))


def _footer(state: UIState) -> Table:
    grid = Table.grid(expand=True)
    grid.add_column()
    grid.add_column(justify="right")
    status = Text(state.status, style="dim")
    left = status if state.done else Table.grid()
    if not state.done:
        left.add_row(Spinner("dots", style="cyan"), Text(" "), status)
    grid.add_row(left, Text(state.key_hint, style="dim cyan"))
    return grid


def build_layout() -> Layout:
    """Construct the screen skeleton once. Regions are filled by refresh_panels()."""
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=5),
        Layout(name="current", ratio=3, minimum_size=5),
        Layout(name="earlier", ratio=2, minimum_size=3),
        Layout(name="footer", size=1),
    )
    return layout


def _current_height(state: UIState, console: Console) -> int:
    """Rows the current-sample panel needs: borders, bars, buzzwords, gap, text."""
    if not state.chunks:
        return 5
    c = state.chunks[-1]
    text_width = max(20, console.width - 6)  # borders + padding
    text_lines = len(_highlight(c.transcript or " ", c.buzzwords).wrap(console, text_width))
    return 2 + 1 + (1 if c.buzzwords else 0) + 1 + max(1, text_lines)


def refresh_panels(layout: Layout, state: UIState, console: Optional[Console] = None) -> None:
    """Fill the regions from state. With a console, the current-sample panel is
    sized to its text and the "Earlier" list gets the rest of the screen."""
    if console is not None:
        cap = max(6, console.height - 5 - 1 - 5)  # leave room for header, footer, a few earlier rows
        layout["current"].size = min(_current_height(state, console), cap)
    layout["header"].update(_header_panel(state))
    layout["current"].update(_current_panel(state))
    layout["earlier"].update(_earlier_panel(state))
    layout["footer"].update(_footer(state))


# ── final report ──────────────────────────────────────────────────────────────

def render_report(state: UIState) -> Group:
    """The end-of-run report, as a renderable (printed once, not live)."""
    chunks = state.chunks
    field, field_share = detected_field(chunks)
    verdict = overall_verdict(chunks, field_name(field) if field else state.domain)
    t = verdict.tally
    total = t.seconds or 1
    parts: list = []

    meta = Text.assemble(("File  ", "dim"), (state.filename, "bold"),
                         ("    Length  ", "dim"), (format_time(chunks[-1].end), "bold"),
                         ("    Samples  ", "dim"), (str(len(chunks)), "bold"))
    if state.model_name:
        meta.append_text(Text.assemble(("    Model  ", "dim"), (state.model_name, "bold")))
    if field:
        meta.append_text(Text.assemble(("    Field  ", "dim"), (field_name(field), "bold"), (f" ({field_share:.0%})", "dim")))
    parts += [meta, Text()]

    banner = Text.assemble((verdict.headline, TONE_STYLE[verdict.tone]), ("\n", ""), (verdict.detail, "default"))
    parts.append(Panel(banner, border_style=TONE_BORDER[verdict.tone], padding=(0, 2), expand=False))

    basis = Text("Verdict basis: ", style="dim")
    basis.append(f"{t.coverage:.0%} on-topic", style="bold")
    if t.content_weight:
        basis.append(", and of that ", style="dim")
        basis.append(f"{t.legit_share:.0%} legit", style=LABEL_COLOR["signal"])
        basis.append(" / ", style="dim")
        basis.append(f"{t.bs_share:.0%} BS", style=LABEL_COLOR["bs"])
    basis.append("  (uncertain samples count less)", style="dim")
    parts += [basis, Text()]

    breakdown = Table.grid(padding=(0, 2))
    breakdown.add_column(width=8)
    breakdown.add_column()
    breakdown.add_column(justify="right")
    breakdown.add_column(justify="right", style="dim")
    for key, secs in (("signal", t.legit_seconds), ("neutral", t.neutral_seconds), ("bs", t.bs_seconds)):
        breakdown.add_row(_label(key), _bar(secs / total, LABEL_COLOR[key], width=30),
                          Text(f"{secs / total:.0%}", style=LABEL_COLOR[key]), format_time(secs))
    parts += [breakdown, Text(), Timeline(chunks, chunks[-1].end), Text()]

    for label, heading in (("bs", "Most BS moments"), ("signal", "Most technical moments")):
        moments = top_moments(chunks, label)
        if not moments:
            continue
        parts.append(Text(heading, style=f"bold {LABEL_COLOR[label]}"))
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="dim", no_wrap=True)
        grid.add_column(ratio=1)
        for c in moments:
            quote = c.transcript.replace("\n", " ").strip()
            if len(quote) > 160:
                quote = quote[:157].rsplit(" ", 1)[0] + "…"
            grid.add_row(format_time(c.start), _highlight(f"“{quote}”", c.buzzwords))
        parts += [grid, Text()]

    conf = Counter(c.confidence for c in chunks)
    conf_line = Text.assemble(("Model confidence  ", "dim"),
                              (f"{conf['HIGH']} high", CONFIDENCE_COLOR["HIGH"]), (" · ", "dim"),
                              (f"{conf['MEDIUM']} medium", CONFIDENCE_COLOR["MEDIUM"]), (" · ", "dim"),
                              (f"{conf['LOW']} low", CONFIDENCE_COLOR["LOW"]))
    parts.append(conf_line)
    uncertain = [format_time(c.start) for c in chunks if c.confidence == "LOW"]
    if uncertain:
        shown = ", ".join(uncertain[:8]) + (f" +{len(uncertain) - 8} more" if len(uncertain) > 8 else "")
        parts.append(Text(f"Worth checking (model unsure): {shown}", style="dim"))

    all_bw = [bw.lower() for c in chunks for bw in c.buzzwords]
    if all_bw:
        top = ", ".join(f"{w} ({n})" for w, n in Counter(all_bw).most_common(10))
        parts += [Text(), Text.assemble(("Buzzwords  ", "bold magenta"), (top, "magenta"))]

    return Group(*parts)


# ── main UI class ─────────────────────────────────────────────────────────────

class TechBSUI:
    def __init__(self, filename: str, model_name: str = "", domain: str = "",
                 is_live: bool = False, duration: Optional[Callable[[], Optional[float]]] = None):
        """duration: optional callable returning the total audio length once known."""
        self.state = UIState(filename=filename, model_name=model_name, domain=domain, is_live=is_live)
        self._duration = duration
        self.console = Console()

    def _sync_duration(self):
        if self._duration and self.state.duration is None:
            self.state.duration = self._duration()

    def run(self, chunk_iterator, scorer: Callable[[int, float, float, str], ChunkResult],
            skipper: "SkipController | None" = None, save_transcript: bool = False) -> Optional[Path]:
        """scorer turns (idx, start, end, text) into a ChunkResult, e.g. a pipeline.ContextScorer."""
        state = self.state
        if skipper:
            state.key_hint = "[Q] quit" if state.is_live else "[S/Space] skip  [Q] quit"
        waiting = "Listening..." if state.is_live else "Transcribing..."

        self._save_transcript = save_transcript
        self._transcript_path: Optional[Path] = None

        layout = build_layout()
        state.status = waiting
        refresh_panels(layout, state, self.console)

        with Live(layout, console=self.console, refresh_per_second=8, screen=True) as live:
            try:
                for idx, start, end, text in chunk_iterator:
                    if skipper and skipper.quit_requested:
                        break
                    self._sync_duration()
                    state.status = f"Scoring {format_time(start)}–{format_time(end)}..."
                    refresh_panels(layout, state, self.console)
                    live.refresh()

                    state.chunks.append(scorer(idx, start, end, text))
                    state.status = waiting
                    refresh_panels(layout, state, self.console)
                    live.refresh()
            except KeyboardInterrupt:
                pass  # Live exits cleanly and restores the terminal; the report still prints
            state.done = True

        self._print_summary()
        return self._transcript_path

    def _print_summary(self):
        if not self.state.chunks:
            self.console.print("[yellow]No samples analyzed.[/]")
            return
        model_tag = f" · {self.state.model_name}" if self.state.model_name else ""
        self.console.print()
        self.console.rule(f"[bold cyan]TechBS Report{model_tag}[/]")
        self.console.print()
        self.console.print(render_report(self.state))
        self.console.print()

        if self._save_transcript:
            self._transcript_path = self._save_analysis(self.state.chunks)
            self.console.print(f"[dim]Transcript saved → {self._transcript_path}[/]\n")

    def _save_analysis(self, chunks: list) -> Path:
        """Save full transcript and scores to a JSON file for later LLM analysis."""
        stem = Path(self.state.filename).stem
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = Path(f"{stem}_{ts}_techbs.json")

        total = len(chunks)
        if total == 0:
            out_path.write_text(json.dumps({"file": self.state.filename, "error": "no chunks analyzed"}, indent=2))
            return out_path

        field, field_share = detected_field(chunks)
        verdict = overall_verdict(chunks, field_name(field) if field else self.state.domain)
        t = verdict.tally
        counts = Counter(c.label for c in chunks)

        data = {
            "file": self.state.filename,
            "analyzed_at": datetime.datetime.now().isoformat(),
            "overall_verdict": str(verdict),
            "verdict": {
                "headline": verdict.headline,
                "detail": verdict.detail,
                "on_topic_share": round(t.coverage, 3),
                "legit_share_of_on_topic": round(t.legit_share, 3),
                "bs_share_of_on_topic": round(t.bs_share, 3),
                "on_topic_samples": t.content_samples,
                "weighting": "confidence (HIGH 1.0, MEDIUM 0.7, LOW 0.3)",
                "field": field,
                "field_share": round(field_share, 3),
            },
            "summary": {
                "total_chunks": total,
                "duration_seconds": chunks[-1].end,
                "legit_count":   counts["signal"],
                "neutral_count": counts["neutral"],
                "bs_count":      counts["bs"],
                "legit_pct":   round(counts["signal"]  / total * 100, 1),
                "neutral_pct": round(counts["neutral"] / total * 100, 1),
                "bs_pct":      round(counts["bs"]      / total * 100, 1),
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
                    "field":            c.field,
                    "transcript":       c.transcript,
                }
                for c in chunks
            ],
        }

        out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return out_path
