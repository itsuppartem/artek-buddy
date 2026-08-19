from __future__ import annotations

import unittest

from artek_buddy.contracts import (
    BOT_COLORS,
    Bot,
    PROCEDURES,
    PROCEDURES_BY_NAME,
    ProductEventType,
    RunRequest,
    RunStatus,
    ThreadSendInput,
    ThreadSendResult,
)


class ContractsTest(unittest.TestCase):
    def test_bot_colors_are_artek_palette(self) -> None:
        self.assertEqual(
            list(BOT_COLORS),
            ["#C45C26", "#1B6B63", "#D4A017", "#3D5A80", "#8F3D55", "#4F7C4A", "#B85C38"],
        )
        retired = {
            "#3EC5A8",
            "#F5A03C",
            "#6A6BF5",
            "#9B5CF6",
            "#3B82F6",
            "#F2622A",
            "#D9508A",
        }
        self.assertFalse(retired & set(BOT_COLORS))

    def test_run_status_product_values(self) -> None:
        values = {item.value for item in RunStatus}
        self.assertEqual(
            values,
            {
                "queued",
                "leased",
                "running",
                "waiting_input",
                "waiting_takeover",
                "completed",
                "failed",
                "cancelled",
            },
        )
        self.assertNotIn("finished", values)

    def test_no_host_run_finished_alias(self) -> None:
        import artek_buddy.contracts as contracts
        import artek_buddy.contracts.domain as domain

        self.assertFalse(hasattr(contracts, "LIVE_RUN_STATUS_FINISHED"))
        self.assertFalse(hasattr(contracts, "HostRunResponse"))
        self.assertFalse(hasattr(domain, "LIVE_RUN_STATUS_FINISHED"))
        self.assertFalse(hasattr(domain, "HostRunResponse"))

    def test_bot_roundtrip(self) -> None:
        raw = {
            "id": "bot_1",
            "workspace_id": "ws_1",
            "name": "Chief",
            "title": "",
            "description": "",
            "instructions": "",
            "color": "#C45C26",
            "notify_on_finish": True,
            "pinned": False,
            "archived_at": None,
            "unread": False,
            "parent_bot_id": None,
            "thread_id": "th_1",
            "preview": "",
            "status": "idle",
            "computer_mode": "team",
            "updated_at": "2026-08-17T00:00:00Z",
            "created_at": "2026-08-17T00:00:00Z",
        }
        bot = Bot.model_validate(raw)
        again = Bot.model_validate(bot.model_dump())
        self.assertEqual(again.id, "bot_1")
        self.assertEqual(again.name, "Chief")
        self.assertEqual(again.computer_mode, "team")
        self.assertIsNone(again.cursor_agent_id)

    def test_product_event_types(self) -> None:
        values = {item.value for item in ProductEventType}
        self.assertIn("thread.message.created", values)
        self.assertIn("thread.replay.gap", values)
        self.assertIn("thread.subagent", values)
        self.assertIn("bot.spawned", values)
        self.assertIn("run.completed", values)
        self.assertIn("computer.status", values)
        self.assertIn("computer.takeover.granted", values)
        self.assertIn("computer.takeover.released", values)
        self.assertIn("computer.takeover.requested", values)

    def test_stage2_procedures_implemented(self) -> None:
        for name in (
            "me",
            "deployment.get",
            "deployment.update",
            "bots.list",
            "bots.list_archived",
            "bots.get",
            "bots.create",
            "bots.duplicate",
            "bots.update",
            "bots.set_computer",
            "bots.archive",
            "bots.restore",
            "bots.remove",
            "threads.get",
            "threads.messages",
            "threads.send",
            "threads.stop",
            "threads.follow_up",
            "threads.mark_read",
            "threads.mark_unread",
            "messages.list",
            "runs.create",
            "threads.subscribe",
            "devices.pairing",
            "devices.create",
            "devices.list",
            "devices.revoke",
            "routines.list",
            "routines.create",
            "routines.update",
            "routines.remove",
            "routines.test_run",
            "memory.list",
            "memory.create",
            "memory.update",
            "memory.remove",
            "memory.export_markdown",
            "computer.status",
            "computer.boot",
            "computer.stop",
            "computer.restart",
            "computer.reset",
            "computer.takeover",
            "computer.release",
            "computer.input",
            "computer.files",
            "computer.read_file",
            "computer.download_file",
            "computer.screen_url",
            "computer.heartbeat",
            "subagents.list",
            "subagents.stop",
            "subagents.restart",
            "subagents.steer",
            "consents.answer",
            "consents.get",
            "consents.file",
            "consents.result",
            "artifacts.list",
            "artifacts.download",
            "threads.attachments",
        ):
            self.assertTrue(PROCEDURES_BY_NAME[name].implemented, name)

        send = PROCEDURES_BY_NAME["threads.send"]
        self.assertEqual(send.method, "POST")
        self.assertEqual(send.path, "/v1/threads/{bot_id}/messages")
        self.assertEqual(send.output_model, "ThreadSendResult")

        runs = [item for item in PROCEDURES if item.path == "/v1/runs"]
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].output_model, "Run")

        self.assertTrue(PROCEDURES_BY_NAME["threads.subscribe"].implemented)
        sub = PROCEDURES_BY_NAME["threads.subscribe"]
        self.assertEqual(sub.method, "GET")
        self.assertEqual(sub.path, "/v1/threads/{bot_id}/events")

    def test_sandbox_kinds_are_local(self) -> None:
        from artek_buddy.contracts import SandboxKind

        values = {item.value for item in SandboxKind}
        self.assertEqual(values, {"docker", "desktop", "fake"})

    def test_send_and_run_request_shapes(self) -> None:
        send = ThreadSendInput.model_validate({"text": "hello", "reply_to_id": "msg_1"})
        self.assertEqual(send.text, "hello")
        self.assertEqual(send.reply_to_id, "msg_1")
        run = RunRequest.model_validate({"text": "hello", "bot_id": "bot_1"})
        self.assertEqual(run.bot_id, "bot_1")
        result = ThreadSendResult.model_validate(
            {"task_id": "tsk_1", "run_id": "run_1", "seq": 0}
        )
        self.assertEqual(result.seq, 0)
        self.assertIsNone(result.message)
        self.assertFalse(result.queued)


if __name__ == "__main__":
    unittest.main()
