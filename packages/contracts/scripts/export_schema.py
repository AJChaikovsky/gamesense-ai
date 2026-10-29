"""Export the contracts as one JSON Schema bundle.

Usage: uv run python packages/contracts/scripts/export_schema.py
Then:  npm run gen -w packages/contracts   (generates ts/index.ts)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gamesense_contracts import (
    CONTRACTS_VERSION,
    CaptureStatus,
    CoachingDecision,
    Condition,
    GameState,
    HabitObservation,
    HeartbeatEvent,
    ModelAnalysis,
    Observation,
    StatusEvent,
    TipEvent,
)
from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

MODELS: list[type[BaseModel]] = [
    Observation,
    GameState,
    Condition,
    CoachingDecision,
    HabitObservation,
    ModelAnalysis,
    CaptureStatus,
    HeartbeatEvent,
    TipEvent,
    StatusEvent,
]

OUT = Path(__file__).resolve().parent.parent / "schema" / "contracts.schema.json"


def _strip_titles(node: Any) -> None:
    """Drop per-field titles so TypeScript output uses plain types, not one alias per field."""
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict):
            for prop in props.values():
                _drop_title(prop)
        for value in node.values():
            _strip_titles(value)
    elif isinstance(node, list):
        for value in node:
            _strip_titles(value)


def _drop_title(node: Any) -> None:
    if isinstance(node, dict):
        node.pop("title", None)
        for key in ("anyOf", "oneOf", "allOf"):
            for option in node.get(key, []):
                _drop_title(option)
        if isinstance(node.get("items"), dict):
            _drop_title(node["items"])
        if isinstance(node.get("additionalProperties"), dict):
            _drop_title(node["additionalProperties"])


def build() -> dict[str, Any]:
    _, schema = models_json_schema(
        [(m, "serialization") for m in MODELS], ref_template="#/$defs/{model}"
    )
    defs = schema["$defs"]
    _strip_titles(defs)
    defs["EngineEvent"] = {
        "oneOf": [{"$ref": f"#/$defs/{n}"} for n in ("HeartbeatEvent", "TipEvent", "StatusEvent")],
        "discriminator": {"propertyName": "type"},
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "GameSenseContracts",
        "description": f"GameSense contracts v{CONTRACTS_VERSION}. Generated; do not edit.",
        "type": "object",
        "properties": {name: {"$ref": f"#/$defs/{name}"} for name in sorted(defs)},
        "$defs": defs,
    }


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
