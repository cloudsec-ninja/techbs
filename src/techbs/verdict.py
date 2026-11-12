"""Verdict logic: turns scored samples into an overall judgement.

A verdict has two parts:
  1. Coverage — how much of the audio is on-topic (legit + BS) vs. neutral.
  2. Quality  — of the on-topic part, how much is legit vs. BS.

Each sample counts with a weight based on how sure the classifier was, so a
LOW-confidence guess can't tip the verdict on its own. The same rules drive
the live "last 5" verdict and the final report.
"""
from dataclasses import dataclass
from typing import Optional, Sequence

from .pipeline import ChunkResult

CONFIDENCE_WEIGHT = {"HIGH": 1.0, "MEDIUM": 0.7, "LOW": 0.3}

# Below this share of on-topic audio, the talk is called off-topic outright
OFF_TOPIC_COVERAGE = 0.10
# Below this share, the verdict leads with "mostly off-topic"
LOW_COVERAGE = 0.40
# Minimum on-topic samples before making a quality call
MIN_CONTENT_SAMPLES = 4
MIN_CONTENT_SAMPLES_LIVE = 2

# Quality tiers (share of weighted on-topic content)
HIGHLY_TECHNICAL = 0.75
SOLID = 0.60


@dataclass(frozen=True)
class Tally:
    """Weighted and plain counts over a set of samples."""
    samples: int
    content_samples: int          # samples labelled legit or BS (unweighted)
    legit_weight: float
    neutral_weight: float
    bs_weight: float
    seconds: float                # total audio covered
    legit_seconds: float
    neutral_seconds: float
    bs_seconds: float

    @property
    def total_weight(self) -> float:
        return self.legit_weight + self.neutral_weight + self.bs_weight

    @property
    def content_weight(self) -> float:
        return self.legit_weight + self.bs_weight

    @property
    def coverage(self) -> float:
        """Weighted share of samples that are on-topic (0–1)."""
        return self.content_weight / self.total_weight if self.total_weight else 0.0

    @property
    def legit_share(self) -> float:
        """Weighted legit share of the on-topic part (0–1)."""
        return self.legit_weight / self.content_weight if self.content_weight else 0.0

    @property
    def bs_share(self) -> float:
        return self.bs_weight / self.content_weight if self.content_weight else 0.0


def tally(chunks: Sequence[ChunkResult]) -> Tally:
    weights = {"signal": 0.0, "neutral": 0.0, "bs": 0.0}
    seconds = {"signal": 0.0, "neutral": 0.0, "bs": 0.0}
    content = 0
    for c in chunks:
        w = CONFIDENCE_WEIGHT.get(c.confidence, 1.0)
        weights[c.label] = weights.get(c.label, 0.0) + w
        seconds[c.label] = seconds.get(c.label, 0.0) + max(0.0, c.end - c.start)
        if c.label in ("signal", "bs"):
            content += 1
    return Tally(
        samples=len(chunks),
        content_samples=content,
        legit_weight=weights["signal"],
        neutral_weight=weights["neutral"],
        bs_weight=weights["bs"],
        seconds=sum(seconds.values()),
        legit_seconds=seconds["signal"],
        neutral_seconds=seconds["neutral"],
        bs_seconds=seconds["bs"],
    )


# tone: "legit" | "mixed" | "bs" | "neutral" — the UI maps tones to colours
@dataclass(frozen=True)
class Quality:
    name: str          # short tier name shown live and in the report
    phrase: str        # used after "the on-topic parts are ..."
    description: str   # one-line explanation for the report
    tone: str


def quality_tier(t: Tally) -> Quality:
    if t.legit_share >= HIGHLY_TECHNICAL:
        return Quality("HIGHLY TECHNICAL", "highly technical",
                       "Excellent technical depth throughout", "legit")
    if t.bs_share >= HIGHLY_TECHNICAL:
        return Quality("TOTAL BS", "almost all BS",
                       "Marketing, hype, self promotion, and very little substance", "bs")
    if t.legit_share > SOLID:
        return Quality("SOLID CONTENT", "mostly solid",
                       "Good technical material with some filler", "legit")
    if t.bs_share > SOLID:
        return Quality("MOSTLY BS", "mostly BS",
                       "Heavy on buzzwords, light on technical depth", "bs")
    return Quality("MIXED", "a mix of real content and fluff",
                   "Some useful technical content buried in fluff", "mixed")


@dataclass(frozen=True)
class Verdict:
    headline: str
    detail: str
    tone: str
    tally: Tally

    def __str__(self) -> str:
        return f"{self.headline} — {self.detail}"


def overall_verdict(chunks: Sequence[ChunkResult], domain: str = "") -> Verdict:
    """The final-report verdict for a whole talk."""
    t = tally(chunks)
    topic = f"{domain} content" if domain else "domain content"

    if t.samples == 0:
        return Verdict("NO DATA", "Nothing was analyzed", "neutral", t)
    if t.coverage < OFF_TOPIC_COVERAGE:
        return Verdict("OFF-TOPIC", f"Little to no {topic} detected", "neutral", t)
    if t.content_samples < MIN_CONTENT_SAMPLES:
        return Verdict("NOT ENOUGH TO JUDGE",
                       f"Only {t.content_samples} on-topic sample"
                       f"{'s' if t.content_samples != 1 else ''}, too few for a verdict",
                       "neutral", t)

    q = quality_tier(t)
    if t.coverage < LOW_COVERAGE:
        return Verdict("MOSTLY OFF-TOPIC", f"and the on-topic parts are {q.phrase}", q.tone, t)
    return Verdict(q.name, q.description, q.tone, t)


def rolling_verdict(chunks: Sequence[ChunkResult], window: int = 5) -> tuple[str, str]:
    """Short live verdict over the last *window* samples: (name, tone)."""
    recent = list(chunks[-window:])
    if not recent:
        return "WAITING", "neutral"
    t = tally(recent)
    if t.coverage < LOW_COVERAGE:
        return "OFF-TOPIC", "neutral"
    if t.content_samples < MIN_CONTENT_SAMPLES_LIVE:
        return "TOO EARLY", "neutral"
    q = quality_tier(t)
    return q.name, q.tone


def top_moments(chunks: Sequence[ChunkResult], label: str, n: int = 3) -> list[ChunkResult]:
    """The *n* most confident samples with *label*, in time order."""
    score = {"bs": lambda c: c.bs_score, "signal": lambda c: c.signal_score}[label]
    picked = sorted(
        (c for c in chunks if c.label == label and c.confidence != "LOW" and c.transcript.strip()),
        key=score,
        reverse=True,
    )[:n]
    return sorted(picked, key=lambda c: c.start)


def detected_field(chunks: Sequence[ChunkResult]) -> tuple[Optional[str], float]:
    """The field a talk is mostly about: (field, share of on-topic evidence).

    Only on-topic samples (legit or BS) count, each by its on-topic probability
    and confidence weight. Returns (None, 0.0) for legacy models or an
    off-topic talk.
    """
    totals: dict[str, float] = {}
    for c in chunks:
        if c.label not in ("signal", "bs") or not c.field_scores:
            continue
        w = CONFIDENCE_WEIGHT.get(c.confidence, 1.0) * (c.signal_score + c.bs_score)
        for f, v in c.field_scores.items():
            totals[f] = totals.get(f, 0.0) + w * v
    total = sum(totals.values())
    if not total:
        return None, 0.0
    best = max(totals, key=totals.get)
    return best, totals[best] / total


def format_time(seconds: float) -> str:
    """mm:ss, or h:mm:ss for an hour or more."""
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"
