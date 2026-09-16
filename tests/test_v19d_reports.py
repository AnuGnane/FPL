"""v19d §2.4 — the rendered report is served from ``reports/`` as a static
mount, not an API route, so the v11 route pin does not move."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_the_rendered_report_is_served_from_the_reports_directory(tmp_path,
                                                                 monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "gw4-report.html").write_text("<h1>GW4</h1>")
    from gaffer.web.app import create_app

    client = TestClient(create_app())
    assert client.get("/reports/gw4-report.html").text == "<h1>GW4</h1>"
    # A missing report is a plain 404, not the SPA's index (the exception
    # handler's carve-out), so a stale link says so rather than reloading.
    assert client.get("/reports/gw9-report.html").status_code == 404


def test_a_cold_clone_mounts_no_reports_and_still_serves(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from gaffer.web.app import create_app

    app = create_app()
    assert "/reports" not in {getattr(r, "path", None) for r in app.routes}
    assert TestClient(app).get("/api/meta/freshness").status_code == 200


def test_the_mount_is_not_an_openapi_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    from gaffer.web.app import create_app

    assert not [p for p in create_app().openapi()["paths"] if "reports" in p]
