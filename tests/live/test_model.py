from __future__ import annotations

import subprocess
import time

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import ensure_bot, pair_fresh, send_message, unique_bot

pytestmark = [pytest.mark.live, pytest.mark.model, pytest.mark.timeout(400)]


def _ensure_paired(page: Page, client_url: str, host_url: str) -> str:
    pair_fresh(page, client_url, host_url)
    name = unique_bot("Grok")
    ensure_bot(page, name)
    return name


def _chromium_running() -> bool:
    try:
        raw = subprocess.check_output(
            ["docker", "ps", "--format", "{{.Names}}"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return False
    names = [line.strip() for line in raw.splitlines() if line.startswith("artek-bot-")]
    for name in names:
        try:
            out = subprocess.check_output(
                [
                    "docker",
                    "exec",
                    name,
                    "bash",
                    "-lc",
                    "pgrep -x chromium >/dev/null && echo yes || echo no",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            continue
        if "yes" in out:
            return True
    return False


def test_real_model_replies(page: Page, client_url: str, host_url: str) -> None:
    name = _ensure_paired(page, client_url, host_url)
    send_message(page, "Reply with the single word pong and nothing else.", name)
    expect(page.locator("[data-testid=thread-message][data-role=bot]").last).to_be_visible(
        timeout=180_000
    )
    expect(page.get_by_test_id("typing-indicator")).to_have_count(0, timeout=180_000)


def test_browse_allow_starts_chromium(page: Page, client_url: str, host_url: str) -> None:
    name = _ensure_paired(page, client_url, host_url)
    send_message(
        page, "Open https://example.com on the remote desktop. Do not skip the Allow card.", name
    )
    card = page.get_by_test_id("consent-card")
    try:
        card.wait_for(timeout=180_000)
    except Exception:
        pytest.skip("model did not request browse consent")
    page.get_by_test_id("ask-option").filter(has_text="Allow once").click()
    deadline = time.time() + 90
    while time.time() < deadline:
        if _chromium_running():
            return
        time.sleep(2)
    raise AssertionError("chromium did not start after Allow")


def test_browse_deny_leaves_chromium_down(page: Page, client_url: str, host_url: str) -> None:
    name = _ensure_paired(page, client_url, host_url)
    before = _chromium_running()
    send_message(
        page, "Open https://example.org on the remote desktop. Wait for the Allow card.", name
    )
    card = page.get_by_test_id("consent-card")
    try:
        card.wait_for(timeout=180_000)
    except Exception:
        pytest.skip("model did not request browse consent")
    page.get_by_test_id("ask-option").filter(has_text="Deny").click()
    time.sleep(5)
    assert _chromium_running() == before


def test_real_worker_id_survives_status_ping(page: Page, client_url: str, host_url: str) -> None:
    name = _ensure_paired(page, client_url, host_url)
    send_message(
        page,
        "Spawn one background worker to wait two minutes with a remote command loop. "
        "Finish your own turn after spawn. Do not wait yourself.",
        name,
    )
    snapshot = None
    deadline = time.time() + 120
    while time.time() < deadline:
        snapshot = page.evaluate(
            """async (botName) => {
                const listed = await fetch('/v1/bots').then((r) => r.json());
                const bot = (listed.bots || []).find((item) => item.name === botName);
                if (!bot) return null;
                return fetch('/v1/threads/' + bot.id).then((r) => r.json());
            }""",
            name,
        )
        workers = [
            item
            for item in (snapshot or {}).get("subagents") or []
            if item.get("status") in {"queued", "running"}
        ]
        if workers:
            worker_id = workers[0]["id"]
            send_message(page, "what is happening", name)
            later = None
            status_deadline = time.time() + 180
            while time.time() < status_deadline:
                later = page.evaluate(
                    """async (botName) => {
                        const listed = await fetch('/v1/bots').then((r) => r.json());
                        const bot = (listed.bots || []).find((item) => item.name === botName);
                        if (!bot) return null;
                        return fetch('/v1/threads/' + bot.id).then((r) => r.json());
                    }""",
                    name,
                )
                run = (later or {}).get("run") or {}
                if run.get("status") in {"completed", "failed", "cancelled"}:
                    break
                time.sleep(1)
            still = [
                item for item in (later or {}).get("subagents") or [] if item.get("id") == worker_id
            ]
            assert still, later
            assert still[0]["id"] == worker_id
            assert still[0]["status"] in {"queued", "running"}
            return
        time.sleep(2)
    pytest.skip("model did not spawn a background worker")
