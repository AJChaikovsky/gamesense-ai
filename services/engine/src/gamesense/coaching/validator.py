"""Stale-result validator: checks a tip's ``valid_while`` conditions before showing it.

A model answer can arrive seconds after the frames it was based on, and a held
tip can wait much longer, so each tip carries conditions on observations (for
example ``health le 25``) that must still hold at display time. Conditions are
checked against the freshest facts available: exact telemetry first, then the
latest model observations.

An observation nobody can currently see does not drop the tip (we can't prove
it stale), except for ``present``, which needs it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from gamesense_contracts import Condition

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_TRUE = {"true", "yes", "1", "on"}
_FALSE = {"false", "no", "0", "off", "none"}


def _scalar(value: Any) -> bool | float | str | None:
    """Normalise model strings ("18%", "True", "$2,300") and telemetry values alike."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    match = _NUMBER.search(text.replace(",", ""))
    if match and len(match.group()) >= len(text.replace(",", "").strip("$%hp ")):
        return float(match.group())
    return text


def _number(value: Any) -> float | None:
    v = _scalar(value)
    if isinstance(v, float):
        return v
    if isinstance(v, str):
        match = _NUMBER.search(v.replace(",", ""))
        return float(match.group()) if match else None
    return None


def holds(condition: Condition, facts: Mapping[str, Any]) -> bool:
    known = condition.observation_type in facts
    actual = facts.get(condition.observation_type)
    op = condition.op
    if op == "present":
        return known and actual not in (None, False)
    if op == "absent":
        return not known or actual in (None, False)
    if not known:
        return True  # can't verify, so don't call it stale
    if op in ("eq", "ne"):
        same = _scalar(actual) == _scalar(condition.value)
        return same if op == "eq" else not same
    a, b = _number(actual), _number(condition.value)
    if a is None or b is None:
        return True
    return {"lt": a < b, "le": a <= b, "gt": a > b, "ge": a >= b}[op]


def first_failed(conditions: Iterable[Condition], facts: Mapping[str, Any]) -> Condition | None:
    """The first condition that no longer holds, or None when the tip is still valid."""
    return next((c for c in conditions if not holds(c, facts)), None)
