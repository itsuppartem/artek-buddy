from __future__ import annotations

import tomllib
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_ruff_selects_bugbear_and_security() -> None:
    select = PYPROJECT["tool"]["ruff"]["lint"]["select"]
    assert "B" in select
    assert "S" in select


def test_pytest_errors_product_deprecation_without_a_global_ignore() -> None:
    filters = PYPROJECT["tool"]["pytest"]["ini_options"]["filterwarnings"]
    assert "ignore::DeprecationWarning" not in filters
    assert "error::DeprecationWarning:artek_buddy" in filters
    assert "error::DeprecationWarning:proxy" in filters


def test_host_deprecation_warning_is_error() -> None:
    with pytest.raises(DeprecationWarning, match="probe-host-deprecation"):
        warnings.warn_explicit(
            "probe-host-deprecation",
            DeprecationWarning,
            filename=str(ROOT / "src" / "artek_buddy" / "__init__.py"),
            lineno=1,
            module="artek_buddy",
        )


def test_client_deprecation_warning_is_error() -> None:
    with pytest.raises(DeprecationWarning, match="probe-client-deprecation"):
        warnings.warn_explicit(
            "probe-client-deprecation",
            DeprecationWarning,
            filename=str(ROOT / "client" / "proxy.py"),
            lineno=1,
            module="proxy",
        )
