from __future__ import annotations

from artek_buddy.supervisor.desktop_spec import desktop_create_spec, inspect_is_hardened
from artek_buddy.supervisor.docker_engine import published_port
from artek_buddy.supervisor.logic import (
    _close_app_command,
    action_command,
    input_command,
    observe_command,
    shell_quote,
    x11vnc_command,
)


def _open(path: str) -> str:
    return action_command([{"kind": "open", "path": path}])


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


def test_x11vnc_skips_viewer_lock_keys() -> None:
    cmd = x11vnc_command(5901)
    assert "-skip_lockkeys" in cmd
    assert "-xkb" in cmd


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


def test_clipboard_cyrillic_pastes_utf8_instead_of_us_keys() -> None:
    cmd = input_command("clipboard", {"text": "привет"})
    assert "привет" in cmd
    assert "xclip" in cmd
    assert "ctrl+v" in cmd
    assert "xdotool type" not in cmd


def test_ascii_type_still_uses_keystrokes() -> None:
    cmd = input_command("clipboard", {"text": "hello"})
    assert "xdotool type" in cmd
    assert "xclip" not in cmd


def test_open_https_uses_browser_not_file_manager() -> None:
    for path in (
        "https://example.com/x",
        "HTTPS://example.com/x",
        "www.example.com",
        "WWW.example.com/path",
    ):
        cmd = _open(path)
        assert "artek-browser" in cmd, path
        assert "xdg-open" not in cmd, path
        assert "pcmanfm" not in cmd, path
        assert "thunar" not in cmd, path


def test_launch_files_opens_thunar_home() -> None:
    cmd = action_command([{"kind": "launch", "application": "files"}])
    assert "thunar" in cmd
    assert "/home/artek" in cmd
    assert "pcmanfm" not in cmd


def test_close_files_kills_thunar_and_leftover_pcmanfm() -> None:
    cmd = _close_app_command("files")
    assert "thunar" in cmd
    assert "pcmanfm" in cmd
    assert "pkill -x" in cmd
    assert "pkill -f" not in cmd


def test_open_local_path_still_uses_xdg_open() -> None:
    cmd = _open("/home/artek/inbox")
    assert "xdg-open" in cmd
    assert "artek-browser" not in cmd


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
    assert hc["Tmpfs"]["/tmp"] == "rw,noexec,nosuid,nodev,size=256m,mode=1777"
    assert "noexec" in hc["Tmpfs"]["/tmp"].split(",")
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


class _RecordingEngine:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.files: dict[str, bytes] = {}
        self.exec_code = 0

    def exec(self, container_id: str, command: str) -> tuple[int, str]:
        self.commands.append(command)
        return self.exec_code, "mkdir failed" if self.exec_code else ""

    def put_file(self, container_id: str, path: str, data: bytes) -> None:
        self.files[path] = data


def test_write_container_file_does_not_put_bytes_in_the_shell_command() -> None:
    from artek_buddy.supervisor.docker_engine import write_container_file

    engine = _RecordingEngine()
    payload = b"hello\nARTEK_EOF\nrm -rf /\n"
    code, output = write_container_file(engine, "cid", "/home/artek/note.txt", payload)
    assert code == 0
    assert output == ""
    assert engine.files["/home/artek/note.txt"] == payload
    joined = "\n".join(engine.commands)
    assert "ARTEK_EOF" not in joined
    assert "rm -rf" not in joined
    assert "hello" not in joined
    assert "mkdir -p" in engine.commands[0]
    assert "/home/artek" in engine.commands[0]


def test_supervisor_authorized_wrong_token() -> None:
    from artek_buddy.supervisor.server import supervisor_authorized

    token = "sup_token_aaaaaaaaaaaaaaaa"
    assert supervisor_authorized(f"Bearer {token}", token) is True
    assert supervisor_authorized("Bearer sup_token_bbbbbbbbbbbbbbbb", token) is False
    assert supervisor_authorized("Bearer short", token) is False
    assert supervisor_authorized(f"bearer {token}", token) is False
    assert supervisor_authorized(token, token) is False
    assert supervisor_authorized(f"Bearer {token}", "") is False


def test_supervisor_client_500_hides_engine_text() -> None:
    import inspect

    from artek_buddy.supervisor import server as supervisor_server
    from artek_buddy.supervisor.server import SUPERVISOR_ERROR

    leak = "Cannot connect to the Docker daemon at unix:///var/run/docker.sock"
    source = inspect.getsource(supervisor_server.Handler.do_POST)
    assert "str(err)" not in source
    assert "SUPERVISOR_ERROR" in source
    assert SUPERVISOR_ERROR == "supervisor error"
    assert leak not in SUPERVISOR_ERROR
    assert "unix://" not in SUPERVISOR_ERROR


def test_write_container_file_stores_nul_and_non_utf8_bytes() -> None:
    from artek_buddy.supervisor.docker_engine import write_container_file

    engine = _RecordingEngine()
    payload = b"\x00\xffARTEK_EOF"
    code, _ = write_container_file(engine, "cid", "/home/artek/bin.dat", payload)
    assert code == 0
    assert engine.files["/home/artek/bin.dat"] == payload
    assert payload not in "\n".join(engine.commands).encode("utf-8")


def test_write_container_file_skips_put_when_mkdir_fails() -> None:
    from artek_buddy.supervisor.docker_engine import write_container_file

    engine = _RecordingEngine()
    engine.exec_code = 1
    code, output = write_container_file(engine, "cid", "/home/artek/x.txt", b"secret")
    assert code == 1
    assert output == "mkdir failed"
    assert engine.files == {}


def test_tar_one_file_roundtrips_binary_payload() -> None:
    import io
    import tarfile

    from artek_buddy.supervisor.docker_engine import tar_one_file

    payload = b"\x00ARTEK_EOF\xff"
    archive = tar_one_file("note.bin", payload)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r") as tar:
        member = tar.getmembers()[0]
        assert member.name == "note.bin"
        extracted = tar.extractfile(member)
        assert extracted is not None
        assert extracted.read() == payload


def test_supervisor_write_source_has_no_heredoc_delimiter() -> None:
    import inspect

    from artek_buddy.supervisor import server as supervisor_server

    source = inspect.getsource(supervisor_server)
    assert "ARTEK_EOF" not in source
    assert "<<" not in source


def test_bridge_icc_off_reads_network_options() -> None:
    from artek_buddy.supervisor.docker_engine import bridge_icc_off, network_has_containers

    assert bridge_icc_off({"Options": {"com.docker.network.bridge.enable_icc": "false"}})
    assert not bridge_icc_off({"Options": {"com.docker.network.bridge.enable_icc": "true"}})
    assert not bridge_icc_off({"Options": {}})
    assert not bridge_icc_off({})
    assert network_has_containers({"Containers": {"abc": {"Name": "box"}}})
    assert not network_has_containers({"Containers": {}})
    assert not network_has_containers({})


class _ScriptedDocker:
    def __init__(self, replies: list[tuple[int, object]]) -> None:
        from artek_buddy.supervisor.docker_engine import DockerEngine

        self.engine = DockerEngine("/dev/null")
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []

        def request(method: str, path: str, body: object = None, timeout: float = 60):
            self.calls.append((method, path))
            return self.replies.pop(0)

        self.engine.request = request  # type: ignore[method-assign]


def test_ensure_network_keeps_icc_off() -> None:
    scripted = _ScriptedDocker(
        [(200, {"Options": {"com.docker.network.bridge.enable_icc": "false"}})]
    )
    assert scripted.engine.ensure_network() == "artek-computers"
    assert scripted.calls == [("GET", "/networks/artek-computers")]


def test_ensure_network_recreates_unused_permissive_network() -> None:
    scripted = _ScriptedDocker(
        [
            (
                200,
                {
                    "Options": {"com.docker.network.bridge.enable_icc": "true"},
                    "Containers": {},
                },
            ),
            (204, {}),
            (201, {"Id": "net-new"}),
        ]
    )
    assert scripted.engine.ensure_network() == "artek-computers"
    assert scripted.calls[1][0] == "DELETE"
    assert scripted.calls[2][0] == "POST"


def test_ensure_network_refuses_permissive_network_in_use() -> None:
    import pytest

    scripted = _ScriptedDocker(
        [
            (
                200,
                {
                    "Options": {"com.docker.network.bridge.enable_icc": "true"},
                    "Containers": {"cid": {"Name": "artek-bot-1"}},
                },
            )
        ]
    )
    with pytest.raises(RuntimeError, match="still has containers"):
        scripted.engine.ensure_network()
    assert all(method != "DELETE" for method, _ in scripted.calls)
