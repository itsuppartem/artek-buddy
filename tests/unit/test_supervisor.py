from __future__ import annotations

from artek_buddy.supervisor.desktop_spec import desktop_create_spec, inspect_is_hardened
from artek_buddy.supervisor.docker_engine import published_port
from artek_buddy.supervisor.logic import (
    _close_app_command,
    action_command,
    observe_command,
    shell_quote,
    x11vnc_command,
)


def test_shell_quote_wraps_single_quotes() -> None:
    assert shell_quote("abc") == "'abc'"
    assert "\"'\"'" in shell_quote("it's")


def test_close_browser_does_not_use_pkill_dash_f() -> None:
    cmd = _close_app_command("chromium")
    assert "pkill -x" in cmd
    assert "pkill -f" not in cmd


def test_x11vnc_listens_loopback() -> None:
    cmd = x11vnc_command(5900, view_only=True)
    assert "-listen 127.0.0.1" in cmd
    assert "-viewonly" in cmd


def test_published_port_reads_host_binding() -> None:
    inspect = {"NetworkSettings": {"Ports": {"6080/tcp": [{"HostPort": "33100"}]}}}
    assert published_port(inspect, "6080") == 33100
    assert published_port({}, "6080") is None


def test_observe_command_skips_screenshot_by_default() -> None:
    slim = observe_command()
    assert "import -window root" not in slim
    assert "TITLE" in slim
    shot = observe_command(include_image=True)
    assert "import -window root" in shot


def test_launch_terminal_is_xterm_once() -> None:
    cmd = action_command([{"kind": "launch", "application": "terminal"}])
    assert "xterm" in cmd
    assert cmd.count("xterm") == 1


def test_caps_lock_key_uses_xdotool_caps_lock() -> None:
    cmd = action_command([{"kind": "key", "key": "CapsLock"}])
    assert "Caps_Lock" in cmd


def test_desktop_create_spec_capdrop_all_and_pi5_limits() -> None:
    spec = desktop_create_spec(
        name="artek-bot-team-ws",
        image="artek-buddy-computer:local",
        home="/data/homes/team-ws",
        bot_id="bot-1",
        home_key="team-ws",
        network="artek-computers",
    )
    hc = spec["HostConfig"]
    assert "User" not in spec
    assert hc["CapDrop"] == ["ALL"]
    assert hc["SecurityOpt"] == ["no-new-privileges:true"]
    assert hc["Memory"] == 1536 * 1024 * 1024
    assert hc["NanoCpus"] == 1_000_000_000
    assert hc["PidsLimit"] == 512
    assert hc["ShmSize"] == 256 * 1024 * 1024
    assert hc["Tmpfs"]["/tmp"] == "rw,nosuid,nodev,size=256m,mode=1777"
    assert "noexec" not in hc["Tmpfs"]["/tmp"]
    assert hc.get("ReadonlyRootfs") in (None, False)
    assert hc.get("Privileged") in (None, False)
    assert hc["PortBindings"]["6080/tcp"][0]["HostIp"] == "127.0.0.1"
    assert hc["PortBindings"]["6081/tcp"][0]["HostIp"] == "127.0.0.1"
    assert hc["Binds"] == ["/data/homes/team-ws:/home/artek"]
    assert hc["NetworkMode"] == "artek-computers"


def test_inspect_is_hardened_rejects_unlimited_box() -> None:
    assert inspect_is_hardened({}) is False
    spec = desktop_create_spec(
        name="n",
        image="img",
        home="/h",
        bot_id="b",
        home_key="k",
        network="artek-computers",
    )
    inspect = {"Config": {}, "HostConfig": spec["HostConfig"]}
    assert inspect_is_hardened(inspect) is True
    unlimited = dict(spec["HostConfig"])
    unlimited["CapDrop"] = []
    assert inspect_is_hardened({"Config": {}, "HostConfig": unlimited}) is False
