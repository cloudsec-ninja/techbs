"""Label schemes for TechBS models (pure Python, no torch).

Legacy domain models (cyberbs, aibs, netbs) output three classes in the order
signal / neutral / bs. The unified model (info.json "scheme":
"techbs-unified-v1") outputs combined labels such as "legit_cyber" or
"bs_networking"; these are summed into the same three quality scores plus a
probability for each field.
"""
UNIFIED_SCHEME = "techbs-unified-v1"
DEFAULT_MODEL = "techbs"

FIELD_NAMES = {"cyber": "Cybersecurity", "ai": "AI / ML", "networking": "Network Engineering"}


def collapse_unified(probs: list[float], labels: list[str]) -> tuple[float, float, float, dict[str, float]]:
    """Sum combined-label probabilities into (signal, neutral, bs, field_scores).

    field_scores are normalised over the on-topic (legit + bs) probability, so
    they say which field the speech is about, whatever its quality.
    """
    signal = neutral = bs = 0.0
    fields: dict[str, float] = {}
    for p, label in zip(probs, labels):
        if label == "neutral":
            neutral += p
            continue
        quality, field = label.split("_", 1)
        if quality == "legit":
            signal += p
        else:
            bs += p
        fields[field] = fields.get(field, 0.0) + p
    on_topic = sum(fields.values())
    field_scores = {f: v / on_topic for f, v in fields.items()} if on_topic else {}
    return signal, neutral, bs, field_scores


def field_name(field: str | None) -> str:
    return FIELD_NAMES.get(field or "", field or "")


def preferred_models(names: list, infos: list[dict]) -> list[int]:
    """Indexes of the models to offer: unified models when any are installed
    (they cover every field), otherwise all of them (legacy domain models)."""
    unified = [i for i, info in enumerate(infos) if info.get("scheme") == UNIFIED_SCHEME]
    return unified or list(range(len(names)))
