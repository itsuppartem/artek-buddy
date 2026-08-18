from __future__ import annotations

from dataclasses import dataclass

from artek_buddy.contracts.domain import ComputerStatus


@dataclass
class ComputerRecord:
    id: str
    workspace_id: str
    scope: str
    scope_key: str
    home_key: str
    home_revision: str | None
    kind: str
    provider_ref: str | None
    state: str
    control_holder: str
    control_lease_id: str | None
    control_lease_expires_at: str | None
    control_bot_id: str | None
    execution_run_id: str | None
    execution_bot_id: str | None
    execution_lease_expires_at: str | None
    sleep_at: str | None
    updated_at: str

    def status_for(self, bot_id: str, mode: str, busy_bot_name: str | None = None) -> ComputerStatus:
        holder = self.control_holder
        if holder == "user" and not self.control_lease_id:
            holder = "none"
        return ComputerStatus(
            bot_id=bot_id,
            mode="dedicated" if mode == "dedicated" else "team",
            kind=self.kind if self.kind in {"docker", "desktop", "fake"} else "docker",
            state=self.state if self.state in {"stopped", "booting", "running", "suspended", "error"} else "stopped",
            control_holder=holder if holder in {"bot", "user", "none"} else "none",
            screen_available=self.state in {"running", "booting"},
            home_revision=self.home_revision,
            busy_bot_name=busy_bot_name,
        )
