"""
CyberBS model wrapper — 3-label classifier:
  0 = Signal  : real technical cybersecurity content
  1 = Neutral : not about cybersecurity (greetings, logistics, small talk)
  2 = BS      : cybersecurity-related but fluffy (marketing, hype, no depth)
"""
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

MAX_TOKENS = 512

LABELS = {0: "signal", 1: "neutral", 2: "bs"}


class CyberBSAnalyzer:
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

    def score(self, text: str) -> dict:
        """Return per-class probabilities and predicted label for a text chunk."""
        if not text.strip():
            return {
                "signal_score": 0.0,
                "neutral_score": 1.0,
                "bs_score": 0.0,
                "label": "neutral",
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

        return {
            "signal_score": signal_prob,
            "neutral_score": neutral_prob,
            "bs_score": bs_prob,
            "label": label,
            "text": text,
        }
