from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(ROOT / "infra"))

from perf_budget import (  # type: ignore[import-not-found]
    build_report,
    collect_hardware_spec,
    redact_text,
    run_benchmark,
)


def test_collect_hardware_spec() -> None:
    hw = collect_hardware_spec()
    assert hw.system
    assert hw.machine
    assert hw.cpu_count >= 1
    assert hw.total_memory_mb >= 0.0


def test_perf_budget_report_schema_and_keys() -> None:
    report = build_report(mock_mode=True)
    assert report.timestamp
    assert report.git_commit
    assert report.version
    assert report.hardware.cpu_count >= 1

    metric_names = {m.name for m in report.metrics}
    expected_metrics = {
        "deb_install_or_ready",
        "cold_window_first_paint",
        "pairing_session_resume",
        "open_large_thread",
        "first_scripted_sse_event",
        "replay_n_events",
    }
    assert expected_metrics.issubset(metric_names), (
        f"Missing metrics: {expected_metrics - metric_names}"
    )

    assert len(report.memory) >= 1
    assert report.memory[0].process_name
    assert report.memory[0].idle_rss_mb >= 0.0
    assert report.memory[0].peak_rss_mb >= 0.0

    assert "# Artek Buddy Performance Budget Report" in report.summary_markdown


def test_perf_budget_calibration_moves_metric() -> None:
    baseline = build_report(calibration_sleep_s=0.0)
    calibrated = build_report(calibration_sleep_s=0.05)

    base_metric = next(m for m in baseline.metrics if m.name == "deb_install_or_ready")
    calib_metric = next(m for m in calibrated.metrics if m.name == "deb_install_or_ready")

    # 0.05s sleep should increase duration by at least 35ms
    assert calib_metric.duration_ms >= base_metric.duration_ms + 35.0


def test_perf_budget_secret_redaction() -> None:
    sensitive = (
        "Report with Bearer my_secret_token_123456 and "
        "postgresql://artek:supersecret@127.0.0.1:5432/db and code ABCD-EFGH"
    )
    sanitized = redact_text(sensitive)
    assert "my_secret_token_123456" not in sanitized
    assert "supersecret" not in sanitized
    assert "ABCD-EFGH" not in sanitized
    assert "[redacted]" in sanitized


def test_perf_budget_file_outputs(tmp_path: Path) -> None:
    json_path = tmp_path / "report.json"
    md_path = tmp_path / "report.md"

    report = run_benchmark(output_json=json_path, output_md=md_path)
    assert json_path.is_file()
    assert md_path.is_file()

    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["version"] == report.version
    assert len(loaded["metrics"]) == len(report.metrics)

    md_content = md_path.read_text(encoding="utf-8")
    assert "# Artek Buddy Performance Budget Report" in md_content
