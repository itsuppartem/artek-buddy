from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeCapabilities:
    """Capability flags for AgentRuntime implementations, avoiding isinstance checks."""

    streaming: bool = True
    cancellation: bool = True
    subagents: bool = True
    computer: bool = True
    memory: bool = True
    models_catalog: bool = False
