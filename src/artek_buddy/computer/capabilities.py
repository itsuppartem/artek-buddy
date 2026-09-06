from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ComputerCapabilities:
    """Capability flags for Computer and Supervisor implementations, avoiding isinstance checks."""

    team_desktop: bool = True
    private_desktop: bool = True
    screen_preview: bool = True
    interactive_input: bool = True
    file_transfer: bool = True
    direct_execution: bool = True
