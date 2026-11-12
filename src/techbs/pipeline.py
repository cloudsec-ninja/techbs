"""Analysis pipeline — turns transcribed audio chunks into scored results.

This layer is deliberately UI-free: it depends only on the analyzer's score()
contract, so it can be driven headless and unit-tested without Rich or torch.
"""
import math
from collections import deque
from dataclasses import dataclass, field as dc_field
from typing import Callable, Iterable, Iterator, Optional

# The models are trained mostly on ~150-word passages (about a minute of
# speech). Scoring a 15 s sample on its own (~40 words) skews results toward
# "neutral", so each sample is classified together with the speech before it.
DEFAULT_CONTEXT_SECONDS = 60


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
    buzzwords: list[str] = dc_field(default_factory=list)
    field: Optional[str] = None  # detected field (unified models only), e.g. "cyber"
    field_scores: dict[str, float] = dc_field(default_factory=dict)


def score_chunk(analyzer, idx: int, start: float, end: float, text: str,
                context: Optional[str] = None) -> ChunkResult:
    """Score a single transcribed chunk into a ChunkResult.

    context: optional longer text to classify in place of *text*.
    """
    result = analyzer.score(text, context=context) if context is not None else analyzer.score(text)
    return ChunkResult(
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
        field=result.get("field"),
        field_scores=result.get("field_scores") or {},
    )


def context_samples(context_seconds: float, chunk_seconds: float) -> int:
    """How many samples (including the current one) make up the context window."""
    if context_seconds <= chunk_seconds or chunk_seconds <= 0:
        return 1
    return math.ceil(context_seconds / chunk_seconds)


class ContextScorer:
    """Scores each sample using the text of the last *window* samples.

    The window resets when samples are not consecutive (e.g. after a skip), so
    context never spans a gap in the audio. A sample with no speech is scored
    on its own (neutral) rather than inheriting the previous context.
    """

    def __init__(self, analyzer, window: int = 1):
        self.analyzer = analyzer
        self.window = max(1, window)
        self._texts: deque[str] = deque(maxlen=self.window)
        self._last_idx: Optional[int] = None

    def __call__(self, idx: int, start: float, end: float, text: str) -> ChunkResult:
        if self._last_idx is not None and idx != self._last_idx + 1:
            self._texts.clear()
        self._last_idx = idx
        self._texts.append(text)

        if self.window == 1 or not text.strip():
            return score_chunk(self.analyzer, idx, start, end, text)
        context = " ".join(t.strip() for t in self._texts if t.strip())
        return score_chunk(self.analyzer, idx, start, end, text, context=context)


def analyze_stream(
    chunk_iterator: Iterable[tuple[int, float, float, str]],
    analyzer,
    should_stop: Optional[Callable[[], bool]] = None,
    context_window: int = 1,
) -> Iterator[ChunkResult]:
    """Score each transcribed chunk in order, yielding ChunkResults.

    should_stop: optional predicate checked before each chunk; return True to
    halt the stream early (e.g. the user pressed Q).
    context_window: number of samples (including the current one) to classify together.
    """
    scorer = ContextScorer(analyzer, context_window)
    for idx, start, end, text in chunk_iterator:
        if should_stop and should_stop():
            return
        yield scorer(idx, start, end, text)
