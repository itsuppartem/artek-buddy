from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from artek_buddy.contracts import (
    CreateRoutineInput,
    PROCEDURES_BY_NAME,
    Routine,
    TestRunResult,
)
from artek_buddy.worker import wake_routine


class RoutineContractTest(unittest.TestCase):
    def test_routines_procedures_implemented(self) -> None:
        for name in (
            "routines.list",
            "routines.create",
            "routines.update",
            "routines.remove",
            "routines.test_run",
        ):
            self.assertTrue(PROCEDURES_BY_NAME[name].implemented, name)
        self.assertEqual(PROCEDURES_BY_NAME["routines.list"].path, "/v1/routines")
        self.assertEqual(PROCEDURES_BY_NAME["routines.test_run"].method, "POST")
        self.assertEqual(PROCEDURES_BY_NAME["routines.remove"].output_model, "OkResponse")

    def test_create_and_list_shapes(self) -> None:
        body = CreateRoutineInput.model_validate(
            {
                "bot_id": "bot_1",
                "name": "Morning",
                "prompt": "Check status",
                "cron": "0 9 * * *",
            }
        )
        self.assertFalse(body.active)
        self.assertEqual(body.timezone, "UTC")
        routine = Routine.model_validate(
            {
                "id": "rtn_1",
                "bot_id": "bot_1",
                "name": "Morning",
                "prompt": "Check status",
                "cron": "0 9 * * *",
                "timezone": "UTC",
                "active": True,
                "notify": True,
                "last_run_at": None,
                "next_run_at": "2026-08-18T09:00:00Z",
                "created_at": "2026-08-17T00:00:00Z",
            }
        )
        self.assertEqual(routine.next_run_at, "2026-08-18T09:00:00Z")
        result = TestRunResult.model_validate(
            {"routine_id": "rtn_1", "task_id": "tsk_1", "run_id": "run_1", "seq": 3}
        )
        self.assertEqual(result.seq, 3)


class WorkerWakeTest(unittest.TestCase):
    def test_wake_posts_threads_send(self) -> None:
        seen: dict[str, object] = {}

        class FakeHost(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args) -> None:
                return

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                seen["path"] = self.path
                seen["auth"] = self.headers.get("Authorization")
                seen["body"] = json.loads(self.rfile.read(length).decode()) if length else {}
                data = b'{"task_id":"tsk_1","run_id":"run_1","seq":1}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        host = ThreadingHTTPServer(("127.0.0.1", 0), FakeHost)
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        try:
            status = wake_routine(
                f"http://127.0.0.1:{host.server_address[1]}",
                "host-token",
                "bot_1",
                "routine prompt",
            )
        finally:
            host.shutdown()
            host.server_close()
        self.assertEqual(status, 200)
        self.assertEqual(seen["path"], "/v1/threads/bot_1/messages")
        self.assertEqual(seen["auth"], "Bearer host-token")
        self.assertEqual(seen["body"], {"text": "routine prompt", "trigger": "routine"})

    def test_wake_maps_http_error(self) -> None:
        class BusyHost(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args) -> None:
                return

            def do_POST(self) -> None:
                self.send_response(409)
                self.send_header("Content-Length", "0")
                self.end_headers()

        host = ThreadingHTTPServer(("127.0.0.1", 0), BusyHost)
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        try:
            status = wake_routine(
                f"http://127.0.0.1:{host.server_address[1]}",
                "host-token",
                "bot_1",
                "later",
            )
        finally:
            host.shutdown()
            host.server_close()
        self.assertEqual(status, 409)


if __name__ == "__main__":
    unittest.main()
