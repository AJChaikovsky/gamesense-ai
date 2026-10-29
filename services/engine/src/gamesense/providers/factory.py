from __future__ import annotations

from .base import VisionModelProvider


def create_provider(name: str, model: str) -> VisionModelProvider:
    if name == "mock":
        from .mock import MockProvider

        return MockProvider(model)
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(model)
    if name == "google":
        from .google_provider import GoogleProvider

        return GoogleProvider(model)
    if name == "openai":
        from .openai_provider import openai_provider

        return openai_provider(model)
    if name == "muse":
        from .openai_provider import muse_provider

        return muse_provider(model)
    raise ValueError(f"unknown provider {name!r}")
