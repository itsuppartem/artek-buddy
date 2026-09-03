"""Fail backend when a security-critical file drops below its coverage floor."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    floors = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["artek"][
        "coverage_floors"
    ]
    failed = 0
    for path, floor in floors.items():
        print(f"coverage floor {path} >= {floor}%")
        ran = subprocess.run(
            [
                sys.executable,
                "-m",
                "coverage",
                "report",
                f"--include={path}",
                f"--fail-under={str(floor)}",
            ],
            cwd=ROOT,
        )
        failed |= ran.returncode
    return failed


if __name__ == "__main__":
    raise SystemExit(main())
