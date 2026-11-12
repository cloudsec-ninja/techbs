"""
TechBS model wrapper — 3-label classifier:
  0 = Signal  : real technical content with depth
  1 = Neutral : off-topic (greetings, logistics, small talk)
  2 = BS      : domain-related but fluffy (marketing, hype, no depth)
"""
import json
import re
from pathlib import Path

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

from .device import classifier_device
from .labels import collapse_unified

MAX_TOKENS = 512

LABELS = {0: "signal", 1: "neutral", 2: "bs"}

# Confidence tiers based on margin between top-2 class probabilities
CONFIDENCE_HIGH   = "HIGH"    # margin > 0.5 — model is very sure
CONFIDENCE_MEDIUM = "MEDIUM"  # margin 0.2–0.5 — leaning one way
CONFIDENCE_LOW    = "LOW"     # margin < 0.2 — model is guessing


def _confidence_level(margin: float) -> str:
    if margin > 0.5:
        return CONFIDENCE_HIGH
    if margin >= 0.2:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def load_buzzwords(model_path: str) -> list[re.Pattern]:
    """Load buzzwords.json from the model directory, return compiled regex patterns."""
    bw_file = Path(model_path) / "buzzwords.json"
    if not bw_file.exists():
        return []
    try:
        data = json.loads(bw_file.read_text())
        phrases = data.get("phrases", [])
        return [re.compile(r"\b" + re.escape(p.lower()) + r"\b") for p in phrases]
    except (json.JSONDecodeError, OSError):
        return []


def find_buzzwords(text: str, patterns: list[re.Pattern]) -> list[str]:
    """Return list of buzzword matches found in text (deduplicated, original case)."""
    lower = text.lower()
    found = []
    for pat in patterns:
        match = pat.search(lower)
        if match:
            # Extract the original-case version from the text
            found.append(text[match.start():match.end()])
    return found


class TechBSAnalyzer:
    def __init__(self, model_path: str):
        self.device = classifier_device()
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_path)
        self.model.to(self.device)
        self.model.eval()
        self.buzzword_patterns = load_buzzwords(model_path)
        try:
            info = json.loads((Path(model_path) / "info.json").read_text())
        except (OSError, json.JSONDecodeError):
            info = {}
        # Unified models list their combined labels; legacy models have none
        self.label_names: list[str] | None = info.get("labels")

    def score(self, text: str, context: str | None = None) -> dict:
        """Return per-class probabilities, predicted label, confidence, and buzzwords.

        context: text to classify instead of *text* (e.g. the last minute of
        speech, which matches the length the models were trained on).
        Buzzwords are always found in *text* alone so they aren't double-counted.
        """
        if not text.strip():
            return {
                "signal_score": 0.0,
                "neutral_score": 1.0,
                "bs_score": 0.0,
                "label": "neutral",
                "confidence": CONFIDENCE_HIGH,
                "confidence_margin": 1.0,
                "buzzwords": [],
                "field": None,
                "field_scores": {},
                "text": text,
            }

        inputs = self.tokenizer(
            context if context and context.strip() else text,
            return_tensors="pt",
            truncation=True,
            max_length=MAX_TOKENS,
            padding=True,
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        with torch.no_grad():
            logits = self.model(**inputs).logits
            probs = torch.softmax(logits, dim=-1)[0]

        values = probs.tolist()
        if self.label_names:
            signal_prob, neutral_prob, bs_prob, field_scores = collapse_unified(values, self.label_names)
        else:
            signal_prob, neutral_prob, bs_prob = values[:3]
            field_scores = {}
        quality = [signal_prob, neutral_prob, bs_prob]
        label = LABELS[quality.index(max(quality))]
        field = max(field_scores, key=field_scores.get) if field_scores else None

        sorted_probs = sorted([signal_prob, neutral_prob, bs_prob], reverse=True)
        margin = sorted_probs[0] - sorted_probs[1]

        buzzwords = find_buzzwords(text, self.buzzword_patterns)

        return {
            "signal_score": signal_prob,
            "neutral_score": neutral_prob,
            "bs_score": bs_prob,
            "label": label,
            "confidence": _confidence_level(margin),
            "confidence_margin": round(margin, 3),
            "buzzwords": buzzwords,
            "field": field,
            "field_scores": field_scores,
            "text": text,
        }
