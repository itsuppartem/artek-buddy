"""List prices for known host models, snapshotted when a usage row is written.

Unknown models omit a cost instead of inventing one. History does not drift
when the card is edited later.
"""

from __future__ import annotations

from dataclasses import dataclass

MICRODOLLARS_PER_DOLLAR = 1_000_000
TOKENS_PER_MILLION = 1_000_000


@dataclass(frozen=True)
class TokenRateCard:
    input_per_million: float
    cache_read_per_million: float
    output_per_million: float
    cache_write_per_million: float | None = None


_GROK_STANDARD = TokenRateCard(2.0, 0.50, 6.0)
_GROK_FAST = TokenRateCard(4.0, 1.0, 12.0)
_COMPOSER_STANDARD = TokenRateCard(0.5, 0.2, 2.5)
_COMPOSER_FAST = TokenRateCard(3.0, 0.5, 15.0)

_GROK_IDS = frozenset({"grok-4.6", "grok-4.5"})
_COMPOSER_IDS = frozenset({"composer-2.5", "composer-2", "composer"})


def normalize_model_id(model: str) -> str:
    return (model or "").strip().lower().replace("_", "-")


def rate_card_for(model: str, *, fast: bool) -> TokenRateCard | None:
    key = normalize_model_id(model)
    if key in _GROK_IDS:
        return _GROK_FAST if fast else _GROK_STANDARD
    if key in _COMPOSER_IDS:
        return _COMPOSER_FAST if fast else _COMPOSER_STANDARD
    return None


def estimate_cost_usd_micros(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    fast: bool = True,
) -> int | None:
    card = rate_card_for(model, fast=fast)
    if card is None:
        return None
    write_rate = (
        card.cache_write_per_million
        if card.cache_write_per_million is not None
        else card.input_per_million
    )
    usd = (
        input_tokens * card.input_per_million
        + cache_read_tokens * card.cache_read_per_million
        + cache_write_tokens * write_rate
        + output_tokens * card.output_per_million
    ) / TOKENS_PER_MILLION
    return int(round(usd * MICRODOLLARS_PER_DOLLAR))


def micros_to_usd(micros: int | None) -> float | None:
    if micros is None:
        return None
    return round(int(micros) / MICRODOLLARS_PER_DOLLAR, 6)
