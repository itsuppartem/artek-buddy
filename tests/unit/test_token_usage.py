from __future__ import annotations

from types import SimpleNamespace

from artek_buddy.runtime.token_usage import TokenUsage, extract_token_usage


def test_extract_token_usage_from_wait_result() -> None:
    result = SimpleNamespace(
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=4,
            cache_read_tokens=2,
            cache_write_tokens=1,
            reasoning_tokens=3,
            total_tokens=20,
        )
    )
    usage = extract_token_usage(result, provider="cursor", model="grok-4.6")
    assert usage == TokenUsage(
        input_tokens=10,
        output_tokens=4,
        cache_read_tokens=2,
        cache_write_tokens=1,
        reasoning_tokens=3,
        total_tokens=20,
        provider="cursor",
        model="grok-4.6",
    )


def test_extract_token_usage_from_camel_dict() -> None:
    usage = extract_token_usage(
        {"inputTokens": 5, "outputTokens": 6, "totalTokens": 11},
        provider="cursor",
        model="x",
    )
    assert usage is not None
    assert usage.input_tokens == 5
    assert usage.output_tokens == 6
    assert usage.total_tokens == 11


def test_extract_token_usage_missing_is_none() -> None:
    assert extract_token_usage(None) is None
    assert extract_token_usage(SimpleNamespace(status="completed")) is None
    assert extract_token_usage({"result": "ok"}) is None
    assert extract_token_usage({"input_tokens": 0, "output_tokens": 0}) is None
