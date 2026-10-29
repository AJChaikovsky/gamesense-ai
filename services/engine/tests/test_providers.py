import json
from types import SimpleNamespace
from typing import Any

import pytest
from gamesense.providers import AnalysisRequest, LiveAnalysis, ProviderError
from gamesense.providers.anthropic_provider import AnthropicProvider
from gamesense.providers.google_provider import GoogleProvider
from gamesense.providers.jsonschema import inline_schema
from gamesense.providers.mock import MockProvider

VALID = {
    "activity": "combat",
    "observations": [{"type": "health_low", "value": "15%", "confidence": 0.9, "kind": "observed"}],
    "unknowns": ["enemies behind wall"],
    "tip": {
        "category": "survivability",
        "action": "heal_now",
        "message": "Back off and heal",
        "detail": None,
        "priority": "urgent",
        "confidence": 0.85,
        "expires_in_seconds": 6,
        "valid_while": [{"observation_type": "health_low", "op": "present", "value": None}],
        "evidence": ["health_low"],
    },
}


def _request() -> AnalysisRequest:
    return AnalysisRequest(
        system_prompt="sys", context="ctx", frames_jpeg=[b"\xff\xd8jpeg"], request_id="r1"
    )


def test_inline_schema_has_no_refs() -> None:
    text = json.dumps(inline_schema(LiveAnalysis))
    assert "$ref" not in text and "$defs" not in text
    assert '"additionalProperties": false' in text


class _FakeMessages:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self.response


def _claude_response(text: str, stop: str = "end_turn") -> Any:
    return SimpleNamespace(
        stop_reason=stop,
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(
            input_tokens=1000,
            output_tokens=200,
            cache_read_input_tokens=500,
            cache_creation_input_tokens=0,
        ),
    )


async def test_anthropic_provider_parses_and_costs() -> None:
    messages = _FakeMessages(_claude_response(json.dumps(VALID)))
    provider = AnthropicProvider(client=SimpleNamespace(messages=messages))
    result = await provider.analyze(_request())
    assert result.analysis.tip is not None and result.analysis.tip.priority == "urgent"
    assert result.usage.input_tokens == 1500
    assert result.cost_usd == pytest.approx((1000 * 0.10 + 200 * 0.50 + 500 * 0.1 * 0.10) / 1e6)
    sent = messages.kwargs
    assert sent["model"] == "claude-haiku-5-5"
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert sent["messages"][0]["content"][0]["type"] == "image"
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}


@pytest.mark.parametrize(
    ("text", "stop"), [("not json", "end_turn"), ("{}", "refusal"), ("{}", "max_tokens")]
)
async def test_anthropic_provider_errors(text: str, stop: str) -> None:
    provider = AnthropicProvider(
        client=SimpleNamespace(messages=_FakeMessages(_claude_response(text, stop)))
    )
    with pytest.raises(ProviderError):
        await provider.analyze(_request())


async def test_google_provider_parses() -> None:
    captured: dict[str, Any] = {}

    async def generate_content(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return SimpleNamespace(
            text=json.dumps(VALID),
            usage_metadata=SimpleNamespace(
                prompt_token_count=900, candidates_token_count=150, thoughts_token_count=50
            ),
        )

    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    provider = GoogleProvider(client=client)
    result = await provider.analyze(_request())
    assert result.analysis.activity == "combat"
    assert result.usage.output_tokens == 200
    assert captured["model"] == "gemini-3.1-flash-lite"
    assert captured["config"].response_mime_type == "application/json"


async def test_mock_provider_tips_only_when_busy() -> None:
    mock = MockProvider(latency_s=0)
    quiet = await mock.analyze(_request())
    assert quiet.analysis.tip is None
    busy_req = AnalysisRequest(
        system_prompt="s",
        context="c",
        frames_jpeg=[],
        request_id="r",
        game_id="minecraft",
        hints={"activity": 0.05, "scene_change": 0.1},
    )
    busy = await mock.analyze(busy_req)
    assert busy.analysis.tip is not None and "mock" in (busy.analysis.tip.detail or "")
