from artek_buddy.model_switch import default_model_line, model_fingerprint


def test_default_model_line_names_effort_and_fast() -> None:
    assert default_model_line("scripted", "low", True) == "Using scripted · Low · Fast."
    assert default_model_line("scripted", "xhigh", False) == "Using scripted · Extra high."
    assert (
        default_model_line("scripted", "low", True, live=True)
        == "Using scripted · Low · Fast. This turn keeps going."
    )


def test_model_fingerprint_changes_when_effort_changes() -> None:
    first = model_fingerprint(("cursor", "scripted"), "xhigh", True)
    second = model_fingerprint(("cursor", "scripted"), "low", True)
    assert first != second
    assert first.startswith("cursor:scripted:")
