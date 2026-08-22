from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    live_on = os.environ.get("ARTEK_LIVE") == "1"
    ui_on = os.environ.get("ARTEK_UI") == "1" or live_on
    skip_ui = pytest.mark.skip(reason="UI suite runs on Actions with ARTEK_UI=1")
    skip_model = pytest.mark.skip(reason="model suite runs on Actions with ARTEK_LIVE=1")
    for item in items:
        model = "model" in item.keywords
        if model and not live_on:
            item.add_marker(skip_model)
        elif (not model) and ("live" in item.keywords) and not ui_on:
            item.add_marker(skip_ui)


@pytest.fixture(scope="session")
def client_url() -> str:
    url = (os.environ.get("ARTEK_CLIENT_URL") or "").rstrip("/") + "/"
    if not url.startswith("http://127.0.0.1"):
        pytest.skip("ARTEK_CLIENT_URL must be loopback")
    return url


@pytest.fixture(scope="session")
def host_url() -> str:
    return (os.environ.get("ARTEK_HOST_URL") or "http://127.0.0.1:8080").rstrip("/")


@pytest.fixture(autouse=True)
def _unpair_between_tests(client_url: str) -> None:
    from tests.live.helpers import reset_pairing

    reset_pairing(client_url)


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
