from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

CLIENT = Path(__file__).resolve().parents[2] / "client" / "artek_buddy.py"


@pytest.fixture(scope="module")
def client_mod():
    spec = importlib.util.spec_from_file_location("artek_buddy_client", CLIENT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
