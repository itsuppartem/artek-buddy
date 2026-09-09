from __future__ import annotations

EFFORT_LABELS = {
    "xhigh": "Extra high",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}


def default_model_line(
    model: str,
    effort: str | None,
    fast: bool | None,
    *,
    live: bool = False,
) -> str:
    parts = [f"Using {model}"]
    if effort:
        parts.append(EFFORT_LABELS.get(effort, effort))
    if fast:
        parts.append("Fast")
    text = " · ".join(parts) + "."
    if live:
        text += " This turn keeps going."
    return text


def model_fingerprint(
    default: tuple[str, str] | None,
    effort: str | None,
    fast: bool | None,
) -> str:
    if default is None:
        return ""
    fast_bit = "" if fast is None else str(int(fast))
    return f"{default[0]}:{default[1]}:{effort or ''}:{fast_bit}"
