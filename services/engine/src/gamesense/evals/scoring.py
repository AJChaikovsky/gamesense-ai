"""Per-case scorers. Each is cheap and deterministic; usefulness comes from a judge."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..providers import LiveAnalysis
from .dataset import CaseLabels

# The live loop drops tips below this confidence, so the eval does too.
SHOW_THRESHOLD = 0.55

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> frozenset[str]:
    return frozenset(_TOKEN.findall(text.lower()))


def tip_shown(analysis: LiveAnalysis | None, threshold: float = SHOW_THRESHOLD) -> bool:
    return bool(analysis and analysis.tip and analysis.tip.confidence >= threshold)


def observation_matches(label: str, predicted_type: str) -> bool:
    """A label matches when any alternative's words all appear in the predicted type.

    So "health_low" matches "low_health" and "player_health_low", but not "health_full".
    """
    have = _tokens(predicted_type)
    for alt in label.split("|"):
        want = _tokens(alt)
        if want and want <= have:
            return True
    return False


def perception_recall(labels: CaseLabels, analysis: LiveAnalysis | None) -> float | None:
    """Fraction of labeled observations the model noticed (None if nothing was labeled)."""
    if not labels.observations:
        return None
    if analysis is None:
        return 0.0
    predicted = [o.type for o in analysis.observations]
    hits = sum(any(observation_matches(lbl, p) for p in predicted) for lbl in labels.observations)
    return hits / len(labels.observations)


def tip_similarity(tip: str, examples: list[str]) -> float:
    """Best word-overlap (Jaccard) between a tip and a list of example tips."""
    words = _tokens(tip)
    best = 0.0
    for example in examples:
        other = _tokens(example)
        if words and other:
            best = max(best, len(words & other) / len(words | other))
    return best


@dataclass(frozen=True, slots=True)
class Verdict:
    """A usefulness judgment: 1 (harmful or wrong) to 5 (exactly what a coach would say)."""

    usefulness: int
    grounded: bool | None
    reason: str
    cost_usd: float = 0.0
