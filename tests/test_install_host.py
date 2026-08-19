from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "infra" / "install-host.sh"


class InstallHostTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="artek-install-"))
        shutil.copy(ROOT / ".env.example", self.tmp / ".env.example")
        shutil.copy(ROOT / "docker-compose.release.yml", self.tmp / "docker-compose.release.yml")
        env = os.environ.copy()
        env.update(
            {
                "ARTEK_HOME": str(self.tmp),
                "ARTEK_VERSION": "0.10.22",
                "ARTEK_INSTALL_SKIP_STACK": "1",
            }
        )
        self.env = env

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self) -> subprocess.CompletedProcess[str]:
        script = self.tmp / "install-host.sh"
        shutil.copy(SCRIPT, script)
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return subprocess.run(
            ["sh", str(SCRIPT)],
            cwd=str(self.tmp),
            env=self.env,
            text=True,
            capture_output=True,
        )

    def test_first_run_writes_tokens_and_stops_for_key(self) -> None:
        result = self._run()
        self.assertEqual(result.returncode, 2, result.stderr)
        text = (self.tmp / ".env").read_text(encoding="utf-8")
        self.assertNotIn("AGENT_HTTP_TOKEN=\n", text)
        self.assertNotIn("MEMORY_DB_PASSWORD=\n", text)
        self.assertIn("CURSOR_API_KEY=crsr_your_key_here", text)
        self.assertIn("ARTEK_VERSION=0.10.22", text)

    def test_existing_env_is_left_alone(self) -> None:
        (self.tmp / ".env").write_text(
            "AGENT_HTTP_TOKEN=keep-me\nMEMORY_DB_PASSWORD=also\nCURSOR_API_KEY=crsr_real\n",
            encoding="utf-8",
        )
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        text = (self.tmp / ".env").read_text(encoding="utf-8")
        self.assertIn("AGENT_HTTP_TOKEN=keep-me", text)
        self.assertIn("CURSOR_API_KEY=crsr_real", text)


if __name__ == "__main__":
    unittest.main()
