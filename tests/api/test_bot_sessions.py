from __future__ import annotations

from tests.api.helpers import create_bot


def _agent_id(row: dict) -> str:
    value = row.get("cursor_agent_id") or row.get("cursorAgentId")
    assert value
    return str(value)


def test_two_inbox_bots_keep_separate_sessions(client, auth_header) -> None:
    runtime = client.app.state.runtime
    host_default = runtime.default_agent_id
    first = create_bot(client, auth_header, "SessWork")
    second = create_bot(client, auth_header, "SessJobs")
    first_id = _agent_id(first)
    second_id = _agent_id(second)
    assert first_id != second_id
    assert first_id != host_default
    assert second_id != host_default
    assert runtime.default_agent_id == host_default
    assert runtime._bot_by_agent[first_id] == first["id"]
    assert runtime._bot_by_agent[second_id] == second["id"]
