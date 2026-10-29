"""Turn a Pydantic model into a self-contained JSON Schema for structured outputs."""

from __future__ import annotations

import copy
from typing import Any

from pydantic import BaseModel


def inline_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Resolve every ``$ref`` and drop titles, so any provider accepts the schema."""
    schema = model.model_json_schema()
    defs: dict[str, Any] = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str):
                target = copy.deepcopy(defs[ref.rsplit("/", 1)[-1]])
                extra = {k: v for k, v in node.items() if k != "$ref"}
                return resolve({**target, **extra})
            return {k: resolve(v) for k, v in node.items() if k != "title"}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    result: dict[str, Any] = resolve(schema)
    return result
