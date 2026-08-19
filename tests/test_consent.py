from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from artek_buddy.consent import (
    CLASS_BROWSE,
    CLASS_OWNER_EXEC,
    CLASS_OWNER_READ,
    CLASS_OWNER_WRITE,
    CLASS_PAGE,
    OWNER_HOME_SCOPE,
    ConsentHub,
    browse_origin,
    owner_command_is_readonly,
    owner_scope,
)
from artek_buddy.runtime.tools import ProductTools


class _Msg:
    def __init__(self, msg_id: str, blocks: list) -> None:
        self.id = msg_id
        self.blocks = blocks

    def model_dump(self, mode: str = "json") -> dict:
        return {"id": self.id, "blocks": self.blocks}


class FakeStore:
    def __init__(self) -> None:
        self.bot = SimpleNamespace(id="bot_1", workspace_id="ws", thread_id="th_1")
        self.grants: list[tuple] = []
        self.requests: dict[str, object] = {}
        self.messages: list[_Msg] = []

    def get_bot(self, bot_id: str):
        return self.bot if bot_id == self.bot.id else None

    def find_consent_grant(self, bot_id, action_class, scope_key, device_id=None):
        for item in self.grants:
            if item[:3] == (bot_id, action_class, scope_key):
                if device_id is None or item[3] is None or item[3] == device_id:
                    return item[4]
        return None

    def save_consent_grant(self, bot_id, action_class, scope_key, device_id=None, workspace_id="ws"):
        grant_id = f"cng_{len(self.grants)}"
        self.grants.append((bot_id, action_class, scope_key, device_id, grant_id))
        return grant_id

    def append_bot_message(self, bot, blocks, run_id=None):
        msg = _Msg(f"msg_{len(self.messages)}", blocks)
        self.messages.append(msg)
        return msg

    def create_consent_request(self, request_id, **kwargs):
        from artek_buddy.consent import ConsentRequest

        self.requests[request_id] = ConsentRequest(
            id=request_id,
            bot_id=kwargs["bot_id"],
            action_class=kwargs["action_class"],
            scope_key=kwargs["scope_key"],
            summary=kwargs["summary"],
            run_id=kwargs.get("run_id"),
            message_id=kwargs.get("message_id"),
        )

    def get_consent_request(self, request_id):
        return self.requests.get(request_id)

    def answer_consent_request(self, request_id, decision, device_id):
        row = self.requests.get(request_id)
        if row is None or getattr(row, "status", "pending") != "pending":
            return None
        row.status = decision
        return row

    def answer_message_ask(self, message_id, answer):
        for msg in self.messages:
            if msg.id != message_id:
                continue
            for block in msg.blocks:
                if isinstance(block, dict) and block.get("kind") == "ask":
                    block["status"] = "answered"
                    block["answer"] = answer
            return msg
        return None

    def mark_run_waiting_input(self, run_id):
        return None

    def mark_run_running(self, run_id):
        return None


class _Runtime:
    def __init__(self, consent=None, home: str | None = None) -> None:
        self.consent = consent
        self.computers = SimpleNamespace(
            open_path=lambda bot, path: {"ok": True, "opened": path},
            act=lambda bot, actions: {"ok": True, "actions": actions},
            observe=lambda bot: {"ok": True, "observe": True},
            launch_app=lambda bot, name, uri=None: {"ok": True, "app": name, "uri": uri},
            status=lambda bot: SimpleNamespace(model_dump=lambda mode="json": {}),
        )
        self.store = SimpleNamespace(get_bot=lambda bid: SimpleNamespace(id=bid, thread_id="th_1"))
        self.events = None
        self.owner_file_reader = None
        self._home = home or tempfile.mkdtemp()

    def resolve_turn_context(self, bound=None):
        return ("bot_1", "run_1", "th_1")

    def resolve_turn_device(self):
        return "dev_1"

    def home_cwd(self, bot_id=None):
        return self._home


class BrowseOriginTest(unittest.TestCase):
    def test_http_and_www(self) -> None:
        self.assertEqual(browse_origin("https://Wikipedia.org/wiki/X"), "https://wikipedia.org")
        self.assertEqual(browse_origin("www.example.com/a"), "https://www.example.com")
        self.assertIsNone(browse_origin("/tmp/notes.txt"))
        self.assertIsNone(browse_origin("notes.txt"))

    def test_owner_scope_is_parent(self) -> None:
        self.assertEqual(owner_scope("/home/me/Projects/readme.md"), "/home/me/Projects")
        self.assertEqual(owner_scope("notes.md"), "notes.md")

    def test_owner_command_readonly_matches_explore_shell(self) -> None:
        explore = (
            'echo "HOME=$HOME"; echo "USER=$USER"; echo "PWD=$(pwd)"; echo "---"; '
            "ls -la ~; echo \"---\"; echo \"OS:\"; uname -a"
        )
        self.assertTrue(owner_command_is_readonly(explore))
        self.assertTrue(owner_command_is_readonly("ls ~/Загрузки"))
        self.assertTrue(owner_command_is_readonly("git status"))
        self.assertTrue(owner_command_is_readonly("timeout 2 ls"))
        self.assertFalse(owner_command_is_readonly("echo hi > notes.txt"))
        self.assertFalse(owner_command_is_readonly("rm -rf ~/tmp"))
        self.assertFalse(owner_command_is_readonly("python -c 'print(1)'"))
        self.assertFalse(owner_command_is_readonly("find ~ -delete"))
        self.assertFalse(owner_command_is_readonly("git commit -am x"))
        self.assertFalse(owner_command_is_readonly("echo $(rm -rf /)"))


class ConsentHubTest(unittest.TestCase):
    def test_scripted_auto_allows(self) -> None:
        hub = ConsentHub(FakeStore(), auto=None, settings=SimpleNamespace(agent_runtime="scripted", consent_auto=""))
        self.assertTrue(
            hub.require(
                bot_id="bot_1",
                action_class=CLASS_BROWSE,
                scope_key="https://example.com",
                summary="Open example.com?",
                run_id="run_1",
                device_id="dev_1",
            )
        )
        self.assertEqual(len(hub.store.messages), 0)

    def test_offer_posts_page_card_without_waiting(self) -> None:
        store = FakeStore()
        hub = ConsentHub(store, auto=None, settings=SimpleNamespace(agent_runtime="scripted", consent_auto=""))
        request_id = hub.offer(
            bot_id="bot_1",
            action_class=CLASS_PAGE,
            scope_key="https://example.com",
            summary="Fill, type, or click on https://example.com in the remote browser?",
            run_id="run_1",
            detail="page_input: https://example.com",
        )
        self.assertIsNotNone(request_id)
        self.assertEqual(len(store.messages), 1)
        block = store.messages[0].blocks[0]
        self.assertEqual(block["kind"], "ask")
        self.assertEqual(block["consent_id"], request_id)
        self.assertEqual(block["status"], "pending")
        self.assertIn("Fill, type, or click", block["text"])
        labels = [item["label"] for item in block["actions"]]
        self.assertEqual(labels, ["Allow once", "Always", "Deny"])
        row = hub.answer(request_id or "", "deny", "dev_1")
        self.assertIsNotNone(row)
        self.assertEqual(block["status"], "answered")
        self.assertEqual(block["answer"], "Deny")

    def test_consent_auto_deny(self) -> None:
        hub = ConsentHub(FakeStore(), auto="deny")
        self.assertFalse(
            hub.require(
                bot_id="bot_1",
                action_class=CLASS_BROWSE,
                scope_key="https://example.com",
                summary="Open?",
                run_id="run_1",
                device_id="dev_1",
            )
        )

    def test_once_asks_again_always_does_not(self) -> None:
        store = FakeStore()
        hub = ConsentHub(store, auto=None, settings=SimpleNamespace(agent_runtime="cursor", consent_auto="ask"))

        def once() -> None:
            time.sleep(0.05)
            self.assertIsNotNone(hub.last_request_id)
            hub.answer(hub.last_request_id or "", "once", "dev_1")

        with patch("artek_buddy.consent.WAIT_SECONDS", 2):
            threading.Thread(target=once, daemon=True).start()
            self.assertTrue(
                hub.require(
                    bot_id="bot_1",
                    action_class=CLASS_BROWSE,
                    scope_key="https://example.com",
                    summary="Open?",
                    run_id="run_1",
                    device_id="dev_1",
                )
            )
        self.assertEqual(len(store.messages), 1)
        self.assertEqual(len(store.grants), 0)

        def always() -> None:
            time.sleep(0.05)
            hub.answer(hub.last_request_id or "", "always", "dev_1")

        with patch("artek_buddy.consent.WAIT_SECONDS", 2):
            threading.Thread(target=always, daemon=True).start()
            self.assertTrue(
                hub.require(
                    bot_id="bot_1",
                    action_class=CLASS_BROWSE,
                    scope_key="https://example.com",
                    summary="Open?",
                    run_id="run_1",
                    device_id="dev_1",
                )
            )
        self.assertEqual(len(store.grants), 1)
        self.assertTrue(
            hub.require(
                bot_id="bot_1",
                action_class=CLASS_BROWSE,
                scope_key="https://example.com",
                summary="Open?",
                run_id="run_1",
                device_id="dev_1",
            )
        )
        self.assertEqual(len(store.messages), 2)

    def test_deny_stops(self) -> None:
        hub = ConsentHub(FakeStore(), settings=SimpleNamespace(agent_runtime="cursor", consent_auto="ask"))

        def deny() -> None:
            time.sleep(0.05)
            hub.answer(hub.last_request_id or "", "deny", "dev_1")

        with patch("artek_buddy.consent.WAIT_SECONDS", 2):
            threading.Thread(target=deny, daemon=True).start()
            self.assertFalse(
                hub.require(
                    bot_id="bot_1",
                    action_class=CLASS_OWNER_WRITE,
                    scope_key=OWNER_HOME_SCOPE,
                    summary="Write file?",
                    run_id="run_1",
                    device_id="dev_1",
                )
            )

    def test_owner_read_never_prompts(self) -> None:
        store = FakeStore()
        hub = ConsentHub(store, settings=SimpleNamespace(agent_runtime="cursor", consent_auto="ask"))
        self.assertTrue(
            hub.require(
                bot_id="bot_1",
                action_class=CLASS_OWNER_READ,
                scope_key="~/Загрузки",
                summary="List ~/Загрузки on your computer?",
                run_id="run_1",
                device_id="dev_1",
            )
        )
        self.assertEqual(len(store.messages), 0)

    def test_write_always_covers_later_writes_on_that_pc(self) -> None:
        store = FakeStore()
        hub = ConsentHub(store, settings=SimpleNamespace(agent_runtime="cursor", consent_auto="ask"))
        store.save_consent_grant("bot_1", CLASS_OWNER_WRITE, OWNER_HOME_SCOPE, "dev_1")
        store.save_consent_grant("bot_1", CLASS_OWNER_EXEC, OWNER_HOME_SCOPE, "dev_1")
        self.assertTrue(
            hub.require(
                bot_id="bot_1",
                action_class=CLASS_OWNER_WRITE,
                scope_key=OWNER_HOME_SCOPE,
                summary="Write ~/other.txt on your computer?",
                run_id="run_1",
                device_id="dev_1",
            )
        )
        self.assertTrue(
            hub.require(
                bot_id="bot_1",
                action_class=CLASS_OWNER_EXEC,
                scope_key=OWNER_HOME_SCOPE,
                summary="Run `touch x` on your computer?",
                run_id="run_1",
                device_id="dev_1",
            )
        )
        self.assertEqual(len(store.messages), 0)


class ProductToolsConsentTest(unittest.TestCase):
    def test_no_hub_allows(self) -> None:
        tools = ProductTools(_Runtime(consent=None))
        self.assertTrue(tools.execute("open_path", {"path": "https://example.com"})["ok"])
        self.assertTrue(tools.execute("computer_observe", {})["ok"])

    def test_url_denied(self) -> None:
        tools = ProductTools(_Runtime(consent=ConsentHub(FakeStore(), auto="deny")))
        out = tools.execute("open_path", {"path": "https://example.com"})
        self.assertFalse(out["ok"])
        self.assertTrue(out.get("denied"))

    def test_local_path_skips_browse(self) -> None:
        tools = ProductTools(_Runtime(consent=ConsentHub(FakeStore(), auto="deny")))
        self.assertTrue(tools.execute("open_path", {"path": "/workspace/notes.md"})["ok"])

    def test_click_denied(self) -> None:
        tools = ProductTools(_Runtime(consent=ConsentHub(FakeStore(), auto="deny")))
        out = tools.execute("computer_act", {"actions": [{"kind": "click", "x": 1, "y": 2}]})
        self.assertFalse(out["ok"])

    def test_form_type_denied(self) -> None:
        tools = ProductTools(_Runtime(consent=ConsentHub(FakeStore(), auto="deny")))
        out = tools.execute("computer_act", {"actions": [{"kind": "type", "text": "hello"}]})
        self.assertFalse(out["ok"])
        self.assertTrue(out.get("denied"))

    def test_browser_act_fill_denied(self) -> None:
        tools = ProductTools(_Runtime(consent=ConsentHub(FakeStore(), auto="deny")))
        out = tools.execute(
            "browser_act",
            {
                "origin": "https://example.com",
                "actions": [{"kind": "fill", "selector": "#email", "text": "a@b.c"}],
            },
        )
        self.assertFalse(out["ok"])
        self.assertTrue(out.get("denied"))

    def test_browser_act_goto_denied_as_browse(self) -> None:
        tools = ProductTools(_Runtime(consent=ConsentHub(FakeStore(), auto="deny")))
        out = tools.execute(
            "browser_act",
            {"actions": [{"kind": "goto", "url": "https://example.com/form"}]},
        )
        self.assertFalse(out["ok"])
        self.assertTrue(out.get("denied"))

    def test_observe_skips_page_consent(self) -> None:
        tools = ProductTools(_Runtime(consent=ConsentHub(FakeStore(), auto="deny")))
        self.assertTrue(tools.execute("computer_observe", {})["ok"])

    def test_scripted_open_path_still_works(self) -> None:
        hub = ConsentHub(FakeStore(), settings=SimpleNamespace(agent_runtime="scripted", consent_auto=""))
        tools = ProductTools(_Runtime(consent=hub))
        self.assertTrue(tools.execute("open_path", {"path": "https://youtube.com"})["ok"])

    def test_read_owner_file_with_reader(self) -> None:
        runtime = _Runtime(consent=ConsentHub(FakeStore(), auto="deny"))
        runtime.owner_file_reader = lambda path: ("notes.txt", b"hello")
        tools = ProductTools(runtime)
        out = tools.execute("read_owner_file", {"path": "/home/me/notes.txt"})
        self.assertTrue(out["ok"])
        self.assertEqual(Path(out["path"]).read_bytes(), b"hello")

    def test_tool_injects_mid_turn_owner_message(self) -> None:
        runtime = _Runtime(consent=ConsentHub(FakeStore(), auto="deny"))
        inbox = [
            {
                "text": "не спрашивай разрешение на команды для чтения на хосте",
                "message_id": "msg_2",
                "reply_to_id": None,
            }
        ]

        def drain(bot_id: str) -> list[dict[str, str | None]]:
            self.assertEqual(bot_id, "bot_1")
            out = list(inbox)
            inbox.clear()
            return out

        runtime.store = SimpleNamespace(get_bot=lambda bid: SimpleNamespace(id=bid, thread_id="th_1"), drain_inbox=drain)
        runtime.owner_dir_lister = lambda path: [{"name": "a.txt", "kind": "file", "size": 3}]
        tools = ProductTools(runtime)
        listed = tools.execute("list_owner_dir", {"path": "~"})
        self.assertTrue(listed["ok"])
        self.assertEqual(listed["owner_follow_up"], ["не спрашивай разрешение на команды для чтения на хосте"])
        self.assertIn("Apply it now", listed["owner_instruction"])
        self.assertEqual(inbox, [])

    def test_list_owner_dir_skips_consent(self) -> None:
        runtime = _Runtime(consent=ConsentHub(FakeStore(), auto="deny"))
        runtime.owner_dir_lister = lambda path: [{"name": "a.txt", "kind": "file", "size": 3}]
        tools = ProductTools(runtime)
        listed = tools.execute("list_owner_dir", {"path": "~/Загрузки"})
        self.assertTrue(listed["ok"])
        self.assertEqual(listed["entries"][0]["name"], "a.txt")

    def test_write_and_exec_with_hooks(self) -> None:
        runtime = _Runtime(consent=ConsentHub(FakeStore(), auto="allow"))
        runtime.owner_file_writer = lambda path, text: {"ok": True, "path": path, "bytes": len(text)}
        runtime.owner_dir_lister = lambda path: [{"name": "a.txt", "kind": "file", "size": 3}]
        runtime.owner_command_runner = lambda command, cwd: {
            "ok": True,
            "stdout": "hi\n",
            "stderr": "",
            "exit_code": 0,
        }
        tools = ProductTools(runtime)
        written = tools.execute("write_owner_file", {"path": "~/notes.txt", "content": "x"})
        self.assertTrue(written["ok"])
        listed = tools.execute("list_owner_dir", {"path": "~"})
        self.assertTrue(listed["ok"])
        self.assertEqual(listed["entries"][0]["name"], "a.txt")
        ran = tools.execute("run_owner_command", {"command": "echo hi", "cwd": "~"})
        self.assertTrue(ran["ok"])
        self.assertEqual(ran["stdout"], "hi\n")

    def test_readonly_exec_skips_consent(self) -> None:
        runtime = _Runtime(consent=ConsentHub(FakeStore(), auto="deny"))
        runtime.owner_command_runner = lambda command, cwd: {
            "ok": True,
            "stdout": "Linux\n",
            "stderr": "",
            "exit_code": 0,
        }
        tools = ProductTools(runtime)
        out = tools.execute("run_owner_command", {"command": "uname"})
        self.assertTrue(out["ok"])
        self.assertEqual(out["stdout"], "Linux\n")

    def test_exec_denied(self) -> None:
        tools = ProductTools(_Runtime(consent=ConsentHub(FakeStore(), auto="deny")))
        out = tools.execute("run_owner_command", {"command": "rm -rf ~/tmp"})
        self.assertFalse(out["ok"])
        self.assertTrue(out.get("denied"))


if __name__ == "__main__":
    unittest.main()
