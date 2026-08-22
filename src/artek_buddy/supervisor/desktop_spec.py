from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# Pi 5 (typically 8 GiB) may run the host stack plus Team and one Private box.
DESKTOP_UID = 1000
DESKTOP_GID = 1000
DESKTOP_USER = f"{DESKTOP_UID}:{DESKTOP_GID}"
DESKTOP_MEMORY_BYTES = 1536 * 1024 * 1024
DESKTOP_NANO_CPUS = 1_000_000_000
DESKTOP_PIDS_LIMIT = 512
DESKTOP_SHM_SIZE = 256 * 1024 * 1024
DESKTOP_TMPFS_OPTS = "rw,nosuid,nodev,size=256m,mode=1777"
DESKTOP_CAP_DROP = ["ALL"]
DESKTOP_SECURITY_OPT = ["no-new-privileges:true"]


def ensure_desktop_home(
    path: Path, uid: int = DESKTOP_UID, gid: int = DESKTOP_GID
) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for item in [path, *path.rglob("*")]:
        try:
            os.chown(item, uid, gid)
        except OSError:
            continue


def desktop_create_spec(
    *,
    name: str,
    image: str,
    home: str,
    bot_id: str,
    home_key: str,
    network: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "Image": image,
        "Hostname": name,
        "User": DESKTOP_USER,
        "Env": ["DISPLAY=:1", "HOME=/home/artek"],
        "Labels": {
            "artek.managed": "true",
            "artek.bot_id": bot_id,
            "artek.home_key": home_key,
        },
        "ExposedPorts": {"6080/tcp": {}, "6081/tcp": {}},
        "HostConfig": {
            "Binds": [f"{home}:/home/artek"],
            "PortBindings": {
                "6080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "0"}],
                "6081/tcp": [{"HostIp": "127.0.0.1", "HostPort": "0"}],
            },
            "NetworkMode": network,
            "SecurityOpt": list(DESKTOP_SECURITY_OPT),
            "CapDrop": list(DESKTOP_CAP_DROP),
            "Memory": DESKTOP_MEMORY_BYTES,
            "NanoCpus": DESKTOP_NANO_CPUS,
            "PidsLimit": DESKTOP_PIDS_LIMIT,
            "ShmSize": DESKTOP_SHM_SIZE,
            "RestartPolicy": {"Name": "no"},
            "Tmpfs": {"/tmp": DESKTOP_TMPFS_OPTS},
        },
    }


def inspect_is_hardened(inspect: dict[str, Any]) -> bool:
    config = inspect.get("Config") or {}
    user = str(config.get("User") or "")
    if user not in {DESKTOP_USER, str(DESKTOP_UID)}:
        return False
    hc = inspect.get("HostConfig") or {}
    caps = {str(c).upper() for c in (hc.get("CapDrop") or [])}
    if "ALL" not in caps:
        return False
    opts = [str(opt) for opt in (hc.get("SecurityOpt") or [])]
    if not any("no-new-privileges" in opt for opt in opts):
        return False
    try:
        if int(hc.get("Memory") or 0) != DESKTOP_MEMORY_BYTES:
            return False
        if int(hc.get("NanoCpus") or 0) != DESKTOP_NANO_CPUS:
            return False
        if int(hc.get("PidsLimit") or 0) != DESKTOP_PIDS_LIMIT:
            return False
    except (TypeError, ValueError):
        return False
    tmpfs = hc.get("Tmpfs") or {}
    if "/tmp" not in tmpfs:
        return False
    ports = hc.get("PortBindings") or {}
    for key in ("6080/tcp", "6081/tcp"):
        bindings = ports.get(key) or []
        if not bindings or (bindings[0] or {}).get("HostIp") != "127.0.0.1":
            return False
    return not bool(hc.get("Privileged") or hc.get("ReadonlyRootfs"))
