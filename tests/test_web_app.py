import pytest
from fastapi.testclient import TestClient

from gaffer.web.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return TestClient(create_app())


def test_ping_is_alive(client):
    resp = client.get("/api/ping")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "app": "gaffer"}


def test_unknown_api_path_is_a_json_404_not_the_spa(client):
    resp = client.get("/api/nope")
    assert resp.status_code == 404
    assert resp.json()["detail"]


def test_domain_errors_map_to_422_with_the_message(client):
    from gaffer.errors import GafferError

    app = client.app

    @app.get("/api/_boom")
    def _boom():
        raise GafferError("run `gaffer advise` first")

    resp = TestClient(app).get("/api/_boom")
    assert resp.status_code == 422
    assert resp.json() == {"detail": "run `gaffer advise` first"}


def test_spa_fallback_serves_index_html_for_client_routes(tmp_path,
                                                          monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>gaffer</title>")
    monkeypatch.setattr("gaffer.web.app.static_dir", lambda: static)
    client = TestClient(create_app())
    resp = client.get("/whatif")
    assert resp.status_code == 200
    assert "gaffer" in resp.text


def test_missing_build_says_how_to_build_it(tmp_path, monkeypatch):
    monkeypatch.setattr("gaffer.web.app.static_dir", lambda: tmp_path / "nope")
    client = TestClient(create_app())
    resp = client.get("/")
    assert resp.status_code == 503
    assert "npm run build" in resp.json()["detail"]
