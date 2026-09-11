from __future__ import annotations

from tests.api.helpers import create_bot


def test_unknown_run_queues_bot_ask_follow_up_instead_of_second_run(client, auth_header) -> None:
    store = client.app.state.store
    source = store.get_bot(create_bot(client, auth_header, "Unknown source")["id"])
    target = store.get_bot(create_bot(client, auth_header, "Unknown target")["id"])
    assert source is not None and target is not None
    _, old, _ = store.begin_or_enqueue_turn(source, "source")
    _, answer_run, _ = store.begin_or_enqueue_turn(target, "answer")
    store.create_bot_ask(
        from_bot_id=source.id,
        to_bot_id=target.id,
        question="audit",
        from_run_id=old.id,
    )
    store.bind_pending_ask_run(target.id, answer_run.id)
    store.finish_turn(source, old, "", "unknown", error="ambiguous")
    delivered = store.deliver_bot_ask_follow_up(
        to_run_id=answer_run.id,
        reply_text="reply",
        source=source,
        ready_blocks=[{"kind": "text", "text": "reply"}],
        prompt="followup",
        model_provider="scripted",
        model_id="scripted",
    )
    assert delivered is not None
    ask_row, _message, follow = delivered
    assert ask_row is not None
    assert follow is None
    assert store.get_run(old.id).status == "unknown"
    assert store.active_run_count(source.id) == 1
