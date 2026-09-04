from __future__ import annotations

import logging
import re
from pathlib import Path, PurePosixPath
from typing import Any

from artek_buddy.bot_credentials import (
    CredentialExecutionResult,
    normalized_credential_env,
)

RUNNER_MEMORY_BYTES = 256 * 1024 * 1024
# Go CLIs reserve a large virtual arena even when RSS is small. Docker gets a
# 256 MiB cgroup request; this hard address-space ceiling is a fail-safe on
# kernels where the daemon cannot enforce that request.
RUNNER_ADDRESS_SPACE_BYTES = 2 * 1024 * 1024 * 1024
RUNNER_NANO_CPUS = 500_000_000
RUNNER_PIDS_LIMIT = 64
RUNNER_TMPFS_OPTS = "rw,noexec,nosuid,nodev,size=64m,mode=1777"
RUNNER_MAX_COMMAND_CHARS = 16_000
RUNNER_MAX_CWD_CHARS = 512
RUNNER_MAX_TIMEOUT_SECONDS = 60.0
RUNNER_MAX_OUTPUT_BYTES = 64 * 1024

_HOME_KEY = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
log = logging.getLogger("artek_buddy.supervisor")


def _pinned_image(image: str) -> str:
    value = (image or "").strip()
    tail = value.rsplit("/", 1)[-1]
    if not value or value.endswith(":latest") or ("@" not in tail and ":" not in tail):
        raise ValueError("credential runner image must use a pinned non-latest tag or digest")
    return value


def _working_dir(cwd: str) -> str:
    value = (cwd or ".").strip() or "."
    path = PurePosixPath(value)
    if (
        len(value) > RUNNER_MAX_CWD_CHARS
        or "\x00" in value
        or path.is_absolute()
        or ".." in path.parts
    ):
        raise ValueError("cwd must stay under this bot home")
    suffix = "" if path.as_posix() == "." else f"/{path.as_posix()}"
    return f"/workspace{suffix}"


def resolve_credential_home(
    data_dir: str | Path,
    home_key: str,
    cwd: str,
) -> tuple[Path, Path]:
    if not _HOME_KEY.fullmatch(home_key or ""):
        raise ValueError("invalid home key")
    _working_dir(cwd)
    root = (Path(data_dir) / "homes").resolve()
    root.mkdir(parents=True, exist_ok=True)
    candidate = root / home_key
    if candidate.is_symlink():
        raise ValueError("credential runner home cannot be a symlink")
    # The key and cwd are validated before these resolved containment checks.
    # codeql[py/path-injection]
    home = candidate.resolve()  # lgtm[py/path-injection]
    if home.parent != root:
        raise ValueError("invalid home key")
    home.mkdir(parents=True, exist_ok=True)
    target = (home / (cwd or ".")).resolve()  # lgtm[py/path-injection]
    if not target.is_relative_to(home) or not target.is_dir():
        raise ValueError("cwd does not exist under this bot home")
    return home, target


def credential_runner_spec(
    *,
    name: str,
    image: str,
    home: str | Path,
    home_key: str,
    cwd: str,
    command: str,
    network: str,
    injected_env: dict[str, str],
) -> dict[str, Any]:
    if not _HOME_KEY.fullmatch(home_key or ""):
        raise ValueError("invalid home key")
    text = (command or "").strip()
    if not text:
        raise ValueError("command is required")
    if len(text) > RUNNER_MAX_COMMAND_CHARS or "\x00" in text:
        raise ValueError("command is too long")
    env = [
        "HOME=/workspace",
        "PATH=/usr/local/bin:/usr/bin:/bin",
        "LANG=C.UTF-8",
        "LC_ALL=C.UTF-8",
        "GIT_TERMINAL_PROMPT=0",
    ]
    for key, value in injected_env.items():
        if normalized_credential_env(key.lower(), key) != key:
            raise ValueError("invalid credential environment name")
        env.append(f"{key}={value}")
    return {
        "name": name,
        "Image": _pinned_image(image),
        "Entrypoint": ["/usr/bin/prlimit"],
        "Cmd": [
            f"--as={RUNNER_ADDRESS_SPACE_BYTES}:{RUNNER_ADDRESS_SPACE_BYTES}",
            "--",
            "/usr/bin/env",
            "-i",
            *env,
            "/bin/sh",
            "-c",
            text,
        ],
        "WorkingDir": _working_dir(cwd),
        "Env": [],
        "Labels": {
            "artek.managed": "true",
            "artek.kind": "credential-runner",
            "artek.home_key": home_key,
        },
        "AttachStdout": True,
        "AttachStderr": True,
        "HostConfig": {
            "Binds": [f"{Path(home)}:/workspace"],
            "NetworkMode": network,
            "SecurityOpt": ["no-new-privileges:true"],
            "CapDrop": ["ALL"],
            "ReadonlyRootfs": True,
            "Memory": RUNNER_MEMORY_BYTES,
            "NanoCpus": RUNNER_NANO_CPUS,
            "PidsLimit": RUNNER_PIDS_LIMIT,
            "RestartPolicy": {"Name": "no"},
            "LogConfig": {
                "Type": "local",
                "Config": {
                    "max-size": "128k",
                    "max-file": "1",
                    "compress": "false",
                },
            },
            "Tmpfs": {"/tmp": RUNNER_TMPFS_OPTS},  # noqa: S108
        },
    }


def _redact(value: str, stored: list[str]) -> str:
    output = value
    for secret in sorted({item for item in stored if item}, key=len, reverse=True):
        output = output.replace(secret, "[redacted]")
    return output


def run_credential_container(
    engine: Any,
    spec: dict[str, Any],
    *,
    timeout_seconds: float,
    redacted_secrets: list[str],
) -> CredentialExecutionResult:
    timeout = max(0.1, min(float(timeout_seconds), RUNNER_MAX_TIMEOUT_SECONDS))
    container_id: str | None = None
    started = False
    timed_out = False
    stdout = ""
    stderr = ""
    truncated = False
    exit_code = 1
    error = ""
    try:
        container_id = engine.create(spec)
        engine.start(container_id)
        started = True
        finished, status = engine.wait(container_id, timeout)
        if not finished:
            timed_out = True
            engine.stop(container_id, timeout=0)
            exit_code = 124
            error = f"credential command timed out after {timeout:g}s"
        else:
            exit_code = int(status or 0)
        stdout, stderr, truncated = engine.logs(
            container_id,
            RUNNER_MAX_OUTPUT_BYTES,
        )
    except Exception:
        error = "credential runner unavailable"
        exit_code = 127 if not started else 1
    finally:
        if container_id:
            removed = False
            for attempt in range(3):
                try:
                    engine.remove(container_id)
                    removed = True
                    break
                except Exception:
                    log.warning(
                        "credential runner removal failed attempt=%s",
                        attempt + 1,
                    )
                    continue
            if not removed:
                error = "credential runner cleanup failed"
                exit_code = 1
    return CredentialExecutionResult(
        ok=exit_code == 0 and not timed_out and not error,
        exit_code=exit_code,
        stdout=_redact(stdout, redacted_secrets),
        stderr=_redact(stderr, redacted_secrets),
        timed_out=timed_out,
        truncated=truncated,
        error=_redact(error, redacted_secrets),
    )
