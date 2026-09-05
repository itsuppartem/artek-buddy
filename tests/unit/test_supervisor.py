from __future__ import annotations

from artek_buddy.supervisor.credential_runner import (
    credential_runner_spec,
    resolve_credential_home,
    run_credential_container,
)
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


def test_x11vnc_refreshes_interactive_desktop_without_100ms_delays() -> None:
    for cmd in (x11vnc_command(5900, view_only=True), x11vnc_command(5901)):
        assert "-wait 30" in cmd
        assert "-defer 20" in cmd
        assert "-wait 100" not in cmd
        assert "-defer 100" not in cmd


def test_published_port_reads_host_binding() -> None:
    inspect = {"NetworkSettings": {"Ports": {"6080/tcp": [{"HostPort": "33100"}]}}}
    assert published_port(inspect, "6080") == 33100
    assert published_port({}, "6080") is None


def test_docker_log_demux_bounds_each_stream() -> None:
    from artek_buddy.supervisor.docker_engine import _demux_docker_streams

    def frame(stream: int, body: bytes) -> bytes:
        return bytes([stream, 0, 0, 0]) + len(body).to_bytes(4, "big") + body

    stdout, stderr, truncated = _demux_docker_streams(
        frame(1, b"abcdef") + frame(2, b"uvwxyz"),
        4,
    )
    assert stdout == "abcd"
    assert stderr == "uvwx"
    assert truncated is True


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
    assert "--clearmodifiers" in cmd
    assert "xdotool type" not in cmd


def test_clipboard_ascii_uses_xclip_and_ctrl_v() -> None:
    cmd = input_command("clipboard", {"text": "https://example.com/login"})
    assert "https://example.com/login" in cmd
    assert "xclip -selection clipboard" in cmd
    assert "xclip -selection primary" in cmd
    assert "ctrl+v" in cmd
    assert "--clearmodifiers" in cmd
    assert "xdotool type" not in cmd


def test_clipboard_without_paste_only_sets_selections() -> None:
    cmd = input_command("clipboard", {"text": "token123", "paste": False})
    assert "token123" in cmd
    assert "xclip" in cmd
    assert "ctrl+v" not in cmd


def test_ascii_type_still_uses_keystrokes() -> None:
    cmd = action_command([{"kind": "type", "text": "hello"}])
    assert "xdotool type" in cmd
    assert "--clearmodifiers" in cmd
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
    assert hc["NanoCpus"] == 1_500_000_000
    assert hc["PidsLimit"] == 512
    assert hc["ShmSize"] == 512 * 1024 * 1024
    assert hc["Tmpfs"]["/tmp"] == "rw,noexec,nosuid,nodev,size=256m,mode=1777"
    assert "noexec" in hc["Tmpfs"]["/tmp"].split(",")
    assert hc.get("ReadonlyRootfs") in (None, False)
    assert hc.get("Privileged") in (None, False)
    assert hc["PortBindings"]["6080/tcp"][0]["HostIp"] == "127.0.0.1"
    assert hc["PortBindings"]["6081/tcp"][0]["HostIp"] == "127.0.0.1"
    assert hc["Binds"] == ["/data/homes/team-ws:/home/artek"]
    assert hc["NetworkMode"] == "artek-computers"


def test_credential_runner_mounts_one_home_and_is_disposable() -> None:
    spec = credential_runner_spec(
        name="artek-credential-runner-abc",
        image="ghcr.io/itsuppartem/artek-buddy:0.10.28",
        home="/data/homes/team-ws",
        home_key="team-ws",
        cwd="project",
        command="gh auth status && uv --version",
        network="artek-computers",
        injected_env={"GH_TOKEN": "fixture", "UV_PUBLISH_TOKEN": "fixture-pypi"},
    )
    hc = spec["HostConfig"]
    assert spec["Image"] == "ghcr.io/itsuppartem/artek-buddy:0.10.28"
    assert spec["Entrypoint"] == ["/usr/bin/prlimit"]
    assert spec["Cmd"][0] == "--as=2147483648:2147483648"
    assert spec["Cmd"][-3:] == ["/bin/sh", "-c", "gh auth status && uv --version"]
    assert spec["WorkingDir"] == "/workspace/project"
    assert spec["Env"] == []
    assert spec["Cmd"][4:-3] == [
        "HOME=/workspace",
        "PATH=/usr/local/bin:/usr/bin:/bin",
        "LANG=C.UTF-8",
        "LC_ALL=C.UTF-8",
        "GIT_TERMINAL_PROMPT=0",
        "GH_TOKEN=fixture",
        "UV_PUBLISH_TOKEN=fixture-pypi",
    ]
    assert hc["Binds"] == ["/data/homes/team-ws:/workspace"]
    assert hc["NetworkMode"] == "artek-computers"
    assert hc["CapDrop"] == ["ALL"]
    assert hc["SecurityOpt"] == ["no-new-privileges:true"]
    assert hc["ReadonlyRootfs"] is True
    assert hc["Memory"] == 256 * 1024 * 1024
    assert hc["NanoCpus"] == 500_000_000
    assert hc["PidsLimit"] == 64
    assert hc["Tmpfs"] == {"/tmp": "rw,noexec,nosuid,nodev,size=64m,mode=1777"}
    assert hc["RestartPolicy"] == {"Name": "no"}
    assert hc["LogConfig"] == {
        "Type": "local",
        "Config": {
            "max-size": "128k",
            "max-file": "1",
            "compress": "false",
        },
    }
    assert "PortBindings" not in hc
    assert "credential" not in " ".join(hc["Binds"])


def test_credential_runner_rejects_latest_and_escaping_cwd() -> None:
    import pytest

    base = {
        "name": "artek-credential-runner-abc",
        "home": "/data/homes/bot_a",
        "home_key": "bot_a",
        "command": "true",
        "network": "artek-computers",
        "injected_env": {},
    }
    with pytest.raises(ValueError, match="pinned"):
        credential_runner_spec(image="artek-buddy:latest", cwd=".", **base)
    with pytest.raises(ValueError, match="cwd"):
        credential_runner_spec(image="artek-buddy:0.10.28", cwd="../other", **base)


def test_credential_runner_creates_only_selected_unbooted_home(tmp_path) -> None:
    home, target = resolve_credential_home(tmp_path / "data", "bot_a", ".")
    assert home == (tmp_path / "data" / "homes" / "bot_a").resolve()
    assert target == home
    assert home.is_dir()
    assert list((tmp_path / "data" / "homes").iterdir()) == [home]


def test_credential_runner_rejects_symlink_home_alias(tmp_path) -> None:
    import pytest

    homes = tmp_path / "data" / "homes"
    other = homes / "bot-b"
    other.mkdir(parents=True)
    (homes / "bot-a").symlink_to(other, target_is_directory=True)
    with pytest.raises(ValueError, match="home"):
        resolve_credential_home(tmp_path / "data", "bot-a", ".")


class _CredentialRunnerEngine:
    def __init__(self, *, finished: bool = True) -> None:
        self.finished = finished
        self.calls: list[str] = []

    def create(self, _spec):
        self.calls.append("create")
        return "runner-id"

    def start(self, _container_id):
        self.calls.append("start")

    def wait(self, _container_id, _timeout):
        self.calls.append("wait")
        return self.finished, 7 if self.finished else None

    def stop(self, _container_id, timeout=0):
        self.calls.append(f"stop:{timeout}")

    def logs(self, _container_id, _max_bytes):
        self.calls.append("logs")
        return "token-value\n", "err token-value\n", False

    def remove(self, _container_id):
        self.calls.append("remove")


def test_credential_runner_redacts_and_always_removes_container() -> None:
    engine = _CredentialRunnerEngine()
    result = run_credential_container(
        engine,
        {"name": "runner"},
        timeout_seconds=5,
        redacted_secrets=["token-value"],
    )
    assert result.ok is False
    assert result.exit_code == 7
    assert result.stdout == "[redacted]\n"
    assert result.stderr == "err [redacted]\n"
    assert engine.calls == ["create", "start", "wait", "logs", "remove"]


def test_credential_runner_timeout_kills_container_before_logs_and_remove() -> None:
    engine = _CredentialRunnerEngine(finished=False)
    result = run_credential_container(
        engine,
        {"name": "runner"},
        timeout_seconds=0.1,
        redacted_secrets=["token-value"],
    )
    assert result.ok is False
    assert result.exit_code == 124
    assert result.timed_out is True
    assert engine.calls == ["create", "start", "wait", "stop:0", "logs", "remove"]


def test_supervisor_credential_endpoint_uses_distinct_token_and_creates_home(
    tmp_path,
    monkeypatch,
) -> None:
    import json
    import threading
    import urllib.error
    import urllib.request
    from types import SimpleNamespace

    import pytest

    from artek_buddy.supervisor import server as supervisor_server

    engine = _CredentialRunnerEngine()
    engine.spec = None
    engine.ensure_network = lambda _name: "artek-computers"
    real_create = engine.create

    def record_create(spec):
        engine.spec = spec
        return real_create(spec)

    engine.create = record_create
    state = SimpleNamespace(
        engine=engine,
        token="supervisor-token",
        credential_executor_token="executor-token",
        credential_runner_image="artek-buddy:0.10.28",
        data_dir=tmp_path / "data",
    )
    monkeypatch.setattr(supervisor_server, "STATE", state)
    server = supervisor_server.serve("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/credential-executions"
    body = json.dumps(
        {
            "bot_id": "bot_" + ("a" * 16),
            "home_key": "bot-home",
            "command": "printf '%s' \"$GH_TOKEN\"",
            "cwd": ".",
            "timeout_seconds": 2,
            "injected_env": {"GH_TOKEN": "token-value"},
        }
    ).encode()
    try:
        for token in ("host-token", "supervisor-token"):
            request = urllib.request.Request(
                url,
                data=body,
                headers={"Authorization": f"Bearer {token}"},
                method="POST",
            )
            with pytest.raises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request, timeout=2)
            assert caught.value.code == 401
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Authorization": "Bearer executor-token"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            result = json.loads(response.read())
        assert result["stdout"] == "[redacted]\n"
        assert result["stderr"] == "err [redacted]\n"
        assert (tmp_path / "data" / "homes" / "bot-home").is_dir()
        assert engine.spec["HostConfig"]["Binds"] == [
            f"{tmp_path / 'data' / 'homes' / 'bot-home'}:/workspace"
        ]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


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
    old_cpu_limit = dict(spec["HostConfig"])
    old_cpu_limit["NanoCpus"] = 1_000_000_000
    assert inspect_is_hardened({"Config": {}, "HostConfig": old_cpu_limit}) is False
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
