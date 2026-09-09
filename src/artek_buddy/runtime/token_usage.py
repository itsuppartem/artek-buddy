from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    provider: str = ""
    model: str = ""

    def counts_payload(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "total_tokens": self.total_tokens,
        }


def _int_field(obj: Any, *names: str) -> int:
    if obj is None:
        return 0
    if isinstance(obj, dict):
        for name in names:
            raw = obj.get(name)
            if raw is None:
                continue
            try:
                return max(0, int(raw))
            except (TypeError, ValueError):
                continue
        return 0
    for name in names:
        raw = getattr(obj, name, None)
        if raw is None:
            continue
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            continue
    return 0


def _usage_object(obj: Any) -> Any | None:
    if obj is None:
        return None
    if isinstance(obj, TokenUsage):
        return obj
    if isinstance(obj, dict):
        if "usage" in obj:
            return obj.get("usage")
        if any(
            key in obj
            for key in (
                "input_tokens",
                "inputTokens",
                "output_tokens",
                "outputTokens",
                "total_tokens",
                "totalTokens",
            )
        ):
            return obj
        return None
    nested = getattr(obj, "usage", None)
    if nested is not None:
        return nested
    return None


def extract_token_usage(
    *sources: Any,
    provider: str = "",
    model: str = "",
) -> TokenUsage | None:
    """Read TokenUsage from a wait result, run handle, or mapping. None if absent."""
    seen: Any | None = None
    for source in sources:
        seen = _usage_object(source)
        if seen is not None:
            break
    if seen is None:
        return None
    if isinstance(seen, TokenUsage):
        return TokenUsage(
            input_tokens=seen.input_tokens,
            output_tokens=seen.output_tokens,
            cache_read_tokens=seen.cache_read_tokens,
            cache_write_tokens=seen.cache_write_tokens,
            reasoning_tokens=seen.reasoning_tokens,
            total_tokens=seen.total_tokens or _total_from_parts(seen),
            provider=seen.provider or provider,
            model=seen.model or model,
        )
    input_tokens = _int_field(seen, "input_tokens", "inputTokens", "prompt_tokens")
    output_tokens = _int_field(seen, "output_tokens", "outputTokens", "completion_tokens")
    cache_read = _int_field(seen, "cache_read_tokens", "cacheReadTokens", "cache_read")
    cache_write = _int_field(seen, "cache_write_tokens", "cacheWriteTokens", "cache_write")
    reasoning = _int_field(seen, "reasoning_tokens", "reasoningTokens")
    total = _int_field(seen, "total_tokens", "totalTokens")
    if total <= 0:
        total = input_tokens + output_tokens + cache_read + cache_write + reasoning
    if (
        input_tokens == 0
        and output_tokens == 0
        and cache_read == 0
        and cache_write == 0
        and reasoning == 0
        and total == 0
    ):
        return None
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        reasoning_tokens=reasoning,
        total_tokens=total,
        provider=provider,
        model=model,
    )


def _total_from_parts(usage: TokenUsage) -> int:
    return (
        usage.input_tokens
        + usage.output_tokens
        + usage.cache_read_tokens
        + usage.cache_write_tokens
        + usage.reasoning_tokens
    )


SCRIPTED_LEAD_USAGE = TokenUsage(
    input_tokens=12,
    output_tokens=7,
    cache_read_tokens=1,
    cache_write_tokens=0,
    reasoning_tokens=2,
    total_tokens=22,
    provider="scripted",
    model="scripted",
)

SCRIPTED_WORKER_USAGE = TokenUsage(
    input_tokens=3,
    output_tokens=4,
    cache_read_tokens=0,
    cache_write_tokens=0,
    reasoning_tokens=0,
    total_tokens=7,
    provider="scripted",
    model="scripted",
)
