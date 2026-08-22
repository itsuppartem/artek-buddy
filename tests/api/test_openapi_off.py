from __future__ import annotations


def test_docs_redoc_and_openapi_json_are_404(client) -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404
