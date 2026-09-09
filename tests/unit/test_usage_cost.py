from __future__ import annotations

from artek_buddy.usage_cost import estimate_cost_usd_micros, micros_to_usd, rate_card_for


def test_grok_fast_uses_fast_card_not_standard() -> None:
    # 128700 in · 1242 out · 47872 cache-read on grok-4.6 Fast.
    micros = estimate_cost_usd_micros(
        model="grok-4.6",
        input_tokens=128700,
        output_tokens=1242,
        cache_read_tokens=47872,
        fast=True,
    )
    assert micros == 577576
    assert micros_to_usd(micros) == 0.577576
    standard = estimate_cost_usd_micros(
        model="grok-4.6",
        input_tokens=128700,
        output_tokens=1242,
        cache_read_tokens=47872,
        fast=False,
    )
    assert standard == 288788
    assert rate_card_for("grok-4.6", fast=True) != rate_card_for("grok-4.6", fast=False)


def test_unknown_and_scripted_models_omit_a_cost() -> None:
    assert (
        estimate_cost_usd_micros(
            model="scripted",
            input_tokens=12,
            output_tokens=7,
            cache_read_tokens=1,
        )
        is None
    )
    assert (
        estimate_cost_usd_micros(
            model="mystery-model",
            input_tokens=100,
            output_tokens=20,
        )
        is None
    )
    assert micros_to_usd(None) is None


def test_composer_fast_card_is_distinct() -> None:
    micros = estimate_cost_usd_micros(
        model="composer-2.5",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_read_tokens=1_000_000,
        fast=True,
    )
    assert micros == 18_500_000
    standard = estimate_cost_usd_micros(
        model="composer-2.5",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_read_tokens=1_000_000,
        fast=False,
    )
    assert standard == 3_200_000
