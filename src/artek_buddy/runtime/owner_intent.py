from __future__ import annotations

STATUS_MARKERS = (
    "e2e-worker-status",
    "e2e-worker-false-idle",
    "what is happening",
    "what's happening",
    "whats happening",
    "what's going on",
    "как там",
    "ты завис",
    "еще делаешь",
    "ещё делаешь",
    "still working?",
    "are you stuck",
)

CORRECTION_MARKERS = (
    "e2e-worker-steer",
    "use path b",
    "use path B",
)


def classify_owner_intent(text: str) -> str:
    hay = " ".join((text or "").lower().split())
    if any(marker.lower() in hay for marker in CORRECTION_MARKERS):
        return "correction"
    if any(marker.lower() in hay for marker in STATUS_MARKERS):
        return "status"
    return "other"
