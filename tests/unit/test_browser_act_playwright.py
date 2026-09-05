from artek_buddy.runtime.tools.common import _playwright_browser_command


def test_playwright_browser_command_grants_site_chrome_on_current_origin() -> None:
    cmd = _playwright_browser_command(
        [{"kind": "goto", "url": "https://example.com/path"}, {"kind": "click", "selector": "#go"}]
    )
    assert "connect_over_cdp('http://127.0.0.1:9222')" in cmd
    assert "grant_permissions" in cmd
    assert "geolocation" in cmd
    assert "notifications" in cmd
    assert "camera" in cmd
    assert "microphone" in cmd
    assert "page.goto" in cmd
    assert "https://example.com/path" in cmd
