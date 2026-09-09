from artek_buddy.runtime.tools.common import _playwright_browser_command


def test_playwright_browser_command_grants_site_chrome_on_current_origin() -> None:
    cmd = _playwright_browser_command(
        [{"kind": "goto", "url": "https://example.com/path"}, {"kind": "click", "selector": "#go"}]
    )
    assert "connect_over_cdp('http://127.0.0.1:9222'" in cmd
    assert "timeout=15000" in cmd
    assert "select_target_page" in cmd
    assert "bring_to_front" in cmd
    assert "grant_permissions" in cmd
    assert "geolocation" in cmd
    assert "notifications" in cmd
    assert "camera" in cmd
    assert "microphone" in cmd
    assert "page.goto" in cmd
    assert "https://example.com/path" in cmd


def test_playwright_browser_command_scroll_and_eval_and_force_click() -> None:
    cmd = _playwright_browser_command(
        [
            {"kind": "scroll", "delta_y": 600},
            {"kind": "scroll", "selector": "#feed", "direction": "down"},
            {"kind": "click", "selector": "button.more", "force": True},
            {"kind": "evaluate", "expression": "window.scrollTo(0, 100)"},
        ]
    )
    assert "mouse.wheel" in cmd
    assert "window.scrollBy" in cmd
    assert "scroll_into_view_if_needed" in cmd
    assert "force=force" in cmd
    assert "page.evaluate" in cmd
    assert "el => el.click()" in cmd


def test_playwright_browser_command_scroll_up_direction() -> None:
    cmd = _playwright_browser_command([{"kind": "scroll", "direction": "up", "clicks": 4}])
    assert "mouse.wheel" in cmd
    assert "-400" in cmd


def test_playwright_browser_command_extract_and_click_all() -> None:
    cmd = _playwright_browser_command(
        [
            {"kind": "click_all", "selector": ".see-more"},
            {"kind": "extract", "selector": "div.post"},
            {"kind": "text"},
            {"kind": "wait", "ms": 500},
            {"kind": "hover", "selector": "#menu"},
        ]
    )
    assert "loc.nth(i).inner_text()" in cmd
    assert "page.inner_text('body')" in cmd
    assert "hover(timeout=10000)" in cmd
    assert "page.wait_for_timeout" in cmd
    assert "step_data" in cmd
    assert "clicked" in cmd


def test_playwright_browser_command_unknown_kind_fails_closed() -> None:
    cmd = _playwright_browser_command([{"kind": "explode"}])
    assert '"ok": false' in cmd
    assert "explode" in cmd
    assert "connect_over_cdp" not in cmd


def test_playwright_browser_command_wrong_case_extract_is_known() -> None:
    cmd = _playwright_browser_command([{"kind": "Extract", "selector": "div.post"}])
    assert "connect_over_cdp" in cmd
    assert "inner_text" in cmd
    assert '"kind": "extract"' in cmd


def test_playwright_browser_command_evaluate_without_expression_fails_closed() -> None:
    cmd = _playwright_browser_command([{"kind": "evaluate", "code": "1+1"}])
    assert '"ok": false' in cmd
    assert "evaluate without expression" in cmd
    assert "code" in cmd
    assert "connect_over_cdp" not in cmd
