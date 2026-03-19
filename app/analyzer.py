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
        if torch.cuda.is_available():
            self.device = torch.device("cuda")
        elif torch.backends.mps.is_available():
            self.device = torch.device("mps")
        else:
            self.device = torch.device("cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_path)
        self.model.to(self.device)
        self.model.eval()
        self.buzzword_patterns = load_buzzwords(model_path)

    def score(self, text: str) -> dict:
        """Return per-class probabilities, predicted label, confidence, and buzzwords."""
        if not text.strip():
            return {
                "signal_score": 0.0,
                "neutral_score": 1.0,
                "bs_score": 0.0,
                "label": "neutral",
                "confidence": CONFIDENCE_HIGH,
                "confidence_margin": 1.0,
                "buzzwords": [],
                "text": text,
            }

        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=MAX_TOKENS,
            padding=True,
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        with torch.no_grad():
            logits = self.model(**inputs).logits
            probs = torch.softmax(logits, dim=-1)[0]

        signal_prob = probs[0].item()
        neutral_prob = probs[1].item()
        bs_prob = probs[2].item()
        label = LABELS[int(probs.argmax().item())]

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
            "text": text,
        }
