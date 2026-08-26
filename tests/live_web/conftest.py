from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest

# iPhone 11 Pro logical screen (home-screen app). Playwright's named device
# is 375×635 because it subtracts Safari chrome; the saved app uses 375×812.
IPHONE_11_PRO = {
    "user_agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
        "Mobile/15E148 Safari/604.1"
    ),
    "viewport": {"width": 375, "height": 812},
    "device_scale_factor": 3,
    "is_mobile": True,
    "has_touch": True,
}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    live_on = os.environ.get("ARTEK_LIVE") == "1"
    ui_on = os.environ.get("ARTEK_UI") == "1" or live_on
    skip_ui = pytest.mark.skip(reason="host page suite runs on Actions with ARTEK_UI=1")
    skip_model = pytest.mark.skip(reason="model suite runs on Actions with ARTEK_LIVE=1")
    for item in items:
        model = "model" in item.keywords
        if model and not live_on:
            item.add_marker(skip_model)
        elif (not model) and ("live" in item.keywords) and not ui_on:
            item.add_marker(skip_ui)


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict) -> dict:
    return {**browser_context_args, **IPHONE_11_PRO}


@pytest.fixture(scope="session")
def host_url() -> str:
    return (os.environ.get("ARTEK_HOST_URL") or "http://127.0.0.1:8080").rstrip("/")


@pytest.fixture(autouse=True)
def _unpair_host_page(host_url: str) -> None:
    reset_host_pairing(host_url)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed:
        return
    page = item.funcargs.get("page")
    if page is None:
        return
    try:
        url = page.url
        text = page.locator("body").inner_text(timeout=1_000)[:4000]
    except Exception as err:
        print(f"\npage dump failed: {err}", flush=True)
        return
    print(
        f"\n----- page at failure url={url} -----\n{text}\n----- end page dump -----\n", flush=True
    )


def reset_host_pairing(host_url: str) -> None:
    origin = host_url.rstrip("/")
    try:
        status_req = urllib.request.Request(
            origin + "/local/status",
            method="GET",
            headers={"Origin": origin, "Accept": "application/json"},
        )
        with urllib.request.urlopen(status_req, timeout=5) as resp:
            payload = json.loads(resp.read().decode())
        nonce = str(payload.get("nonce") or "")
        req = urllib.request.Request(
            origin + "/local/unpair",
            data=b"{}",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Origin": origin,
                "X-Artek-Local-Nonce": nonce,
            },
        )
        urllib.request.urlopen(req, timeout=5)
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError):
        return
