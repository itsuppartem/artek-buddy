from __future__ import annotations


import re


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


_BROWSER_APPS = frozenset(
    {
        "chromium",
        "chromium-browser",
        "google-chrome",
        "chrome",
        "browser",
        "web-browser",
        "artek-browser",
    }
)


_FILE_APPS = frozenset(
    {
        "files",
        "file-manager",
        "filemanager",
        "pcmanfm",
        "thunar",
        "nautilus",
    }
)

_TERMINAL_APPS = frozenset(
    {
        "terminal",
        "xterm",
        "x-terminal-emulator",
    }
)

_CAPS_KEYS = frozenset({"Caps_Lock", "CapsLock", "capslock", "caps_lock"})


def _is_browser_app(name: str) -> bool:
    return name.strip().lower() in _BROWSER_APPS


def _is_files_app(name: str) -> bool:
    return name.strip().lower() in _FILE_APPS


def _is_terminal_app(name: str) -> bool:
    return name.strip().lower() in _TERMINAL_APPS


def normalize_keysym(key: str) -> str:
    value = (key or "").strip()
    if value in _CAPS_KEYS or value.lower() == "capslock":
        return "Caps_Lock"
    return value


def _close_app_command(raw_app: str) -> str:
    # Kill by window class + exact comm. `pkill -f` matches supervisor wrappers.
    if _is_browser_app(raw_app):
        return (
            "for cls in chromium Chromium Google-chrome google-chrome Chrome; do "
            "ids=$(xdotool search --onlyvisible --class \"$cls\" 2>/dev/null || true); "
            "for id in $ids; do xdotool windowkill \"$id\" 2>/dev/null || true; done; "
            "done; "
            "for comm in chromium chrome chromium-browser; do "
            "pkill -x \"$comm\" >/dev/null 2>&1 || true; "
            "done"
        )
    if _is_files_app(raw_app):
        raw_app = "pcmanfm"
    safe = re.sub(r"[^A-Za-z0-9._+-]", "", raw_app.strip())
    if not safe:
        return "true"
    quoted = shell_quote(safe)
    return (
        f"ids=$(xdotool search --onlyvisible --class {quoted} 2>/dev/null || true); "
        f"for id in $ids; do xdotool windowkill \"$id\" 2>/dev/null || true; done; "
        f"pkill -x {quoted} >/dev/null 2>&1 || true"
    )


def x11vnc_command(port: int, *, view_only: bool = False) -> str:
    extra = " -viewonly" if view_only else ""
    return (
        f"x11vnc -display :1 -forever -shared{extra} -nopw -listen 127.0.0.1 "
        f"-rfbport {port} -xkb -ncache 0 -noxdamage -noshm -noxinerama "
        f"-threads -wait 100 -defer 100"
    )


def _kill_control_stack() -> str:
    # Kill by comm + /proc cmdline. `pkill -f` matches the supervisor's
    # `bash -lc` wrapper because that wrapper's argv contains the same flags.
    return (
        "for pid in $(pgrep -x x11vnc || true); do "
        "tr '\\0' ' ' < /proc/$pid/cmdline 2>/dev/null | grep -q -- '-rfbport 5901' "
        "&& kill \"$pid\" || true; "
        "done; "
        "for pid in $(pgrep -x websockify || true); do "
        "tr '\\0' ' ' < /proc/$pid/cmdline 2>/dev/null | grep -q -- ':6081' "
        "&& kill \"$pid\" || true; "
        "done; "
        "rm -f /tmp/artek/control-token"
    )


def _control_vnc_up() -> str:
    return (
        "up=0; "
        "for pid in $(pgrep -x x11vnc || true); do "
        "tr '\\0' ' ' < /proc/$pid/cmdline 2>/dev/null | grep -q -- '-rfbport 5901' && up=1; "
        "done; "
        "[ \"$up\" = 1 ]"
    )


def interactive_screen_command(interactive: bool, control_token: str | None = None) -> str:
    token_file = "/tmp/artek/control-token"
    stop_processes = _kill_control_stack()
    if control_token:
        stop = (
            f"[ -f {token_file} ] && [ \"$(cat {token_file})\" != {shell_quote(control_token)} ] "
            f"|| {{ {stop_processes}; }}"
        )
    else:
        stop = stop_processes
    if not interactive:
        return stop
    if not control_token:
        raise ValueError("interactive screen requires a control token")
    quoted = shell_quote(control_token)
    wait_port = (
        "python3 -c 'import socket; socket.create_connection((\"127.0.0.1\",6081),0.2).close()'"
    )
    # Newlines after `&` — `"; ".join` would emit `&;`, which bash rejects.
    return "\n".join(
        [
            (
                f"[ -f {token_file} ] && [ \"$(cat {token_file})\" = {quoted} ] "
                f"&& {{ {_control_vnc_up()}; }} "
                f"&& {wait_port} >/dev/null 2>&1 && exit 0 || true"
            ),
            stop_processes,
            f"mkdir -p /tmp/artek && printf %s {quoted} > {token_file}",
            "export DISPLAY=:1",
            f"setsid nohup {x11vnc_command(5901)} >/tmp/artek/x11vnc-control.log 2>&1 < /dev/null &",
            "setsid nohup websockify --web=/usr/share/novnc 0.0.0.0:6081 127.0.0.1:5901 >/tmp/artek/novnc-control.log 2>&1 < /dev/null &",
            (
                "ready=0\n"
                "for i in $(seq 1 80); do "
                f"{wait_port} >/dev/null 2>&1 && ready=1 && break; "
                "sleep 0.15; done\n"
                "[ \"$ready\" = 1 ] && exit 0\n"
                "exit 1"
            ),
        ]
    )


def observe_command(*, include_image: bool = False) -> str:
    parts = [
        "export DISPLAY=:1",
        "echo GEOM $(xdpyinfo | awk '/dimensions/{print $2}' | tr 'x' ' ')",
        "echo CURSOR $(xdotool getmouselocation --shell 2>/dev/null | tr '\\n' ' ')",
        "echo WINDOW $(xdotool getactivewindow 2>/dev/null || true)",
        "echo TITLE $(xdotool getactivewindow getwindowname 2>/dev/null || true)",
    ]
    if include_image:
        parts.append("import -window root /tmp/artek/observe.png && echo PNG /tmp/artek/observe.png")
    return "; ".join(parts)


def action_command(actions: list[dict]) -> str:
    parts = ["export DISPLAY=:1"]
    for item in actions[:24]:
        kind = str(item.get("kind") or "")
        if kind in {"click", "move", "down", "up"}:
            x = int(item.get("x") or 0)
            y = int(item.get("y") or 0)
            button = int(item.get("button") or 1)
            if kind == "move":
                parts.append(f"xdotool mousemove {x} {y}")
            elif kind == "down":
                parts.append(f"xdotool mousemove {x} {y} mousedown {button}")
            elif kind == "up":
                parts.append(f"xdotool mouseup {button}")
            else:
                parts.append(f"xdotool mousemove {x} {y} click {button}")
                if item.get("double"):
                    parts.append(f"xdotool click {button}")
        elif kind == "type":
            text = str(item.get("text") or "")
            parts.append(f"xdotool type --delay 12 -- {shell_quote(text)}")
        elif kind == "key":
            key = normalize_keysym(str(item.get("key") or item.get("text") or ""))
            if key:
                parts.append(f"xdotool key {shell_quote(key)}")
        elif kind == "scroll":
            clicks = int(item.get("clicks") or 3)
            button = 4 if str(item.get("direction") or "up") == "up" else 5
            parts.append(f"xdotool click --repeat {max(1, clicks)} {button}")
        elif kind == "wait":
            ms = int(item.get("ms") or 350)
            parts.append(f"sleep {max(0, ms) / 1000:.3f}")
        elif kind == "open":
            path = str(item.get("path") or item.get("url") or "").strip()
            if path:
                if re.match(r"^(https?://|www\.|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(/.*)?$)", path):
                    target = path if path.startswith(("http://", "https://")) else f"https://{path}"
                    parts.append(f"nohup artek-browser {shell_quote(target)} >/tmp/artek/open.log 2>&1 &")
                else:
                    parts.append(f"nohup xdg-open {shell_quote(path)} >/tmp/artek/open.log 2>&1 &")
        elif kind == "launch":
            raw_app = str(item.get("name") or item.get("application") or "artek-browser").strip()
            if _is_browser_app(raw_app):
                app = "artek-browser"
            elif _is_files_app(raw_app):
                app = "pcmanfm"
            elif _is_terminal_app(raw_app):
                app = "xterm"
            else:
                app = raw_app
            uri = str(item.get("uri") or item.get("url") or "").strip()
            if uri:
                parts.append(f"nohup {shell_quote(app)} {shell_quote(uri)} >/tmp/artek/launch.log 2>&1 &")
            else:
                parts.append(f"nohup {shell_quote(app)} >/tmp/artek/launch.log 2>&1 &")
        elif kind == "close":
            raw_app = str(item.get("name") or item.get("application") or "chromium").strip()
            parts.append(_close_app_command(raw_app))
    return "; ".join(parts)


def input_command(kind: str, payload: dict) -> str:
    if kind == "key":
        key = payload.get("key") or payload.get("text")
        return action_command([{"kind": "key", "key": key}])
    if kind == "clipboard":
        return action_command([{"kind": "type", "text": payload.get("text")}])
    return action_command(
        [
            {
                "kind": str(payload.get("type") or "click"),
                "x": payload.get("x"),
                "y": payload.get("y"),
                "button": payload.get("button") or 1,
            }
        ]
    )
