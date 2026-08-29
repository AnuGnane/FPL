"""A fresh clone with no artifacts at all: nothing may 500 (spec §9).

The per-router suites each write the artifacts their own endpoint reads. This
one deliberately writes nothing, which is the state a user is in the first time
they open the UI.
"""

import pytest
from fastapi.testclient import TestClient

from gaffer.data import store
from gaffer.web.app import create_app

V7_ENDPOINTS = [
    "/api/plan/5",
    "/api/fixtures/matrix",
    "/api/fixtures/matrix?from=5&n=6",
    "/api/journal",
    "/api/jobs/current",
    "/api/jobs/does-not-exist",
    "/api/jobs/does-not-exist/stream",
]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.mark.parametrize("path", V7_ENDPOINTS)
def test_no_endpoint_500s_on_a_cold_clone(client, path):
    assert client.get(path).status_code < 500, path


# The hubs also read endpoints older than this cycle. A clone has no
# config.toml either (it is gitignored — it carries an API key), and Smoke 3
# found the Live and League hubs 500ing on exactly that.
HUB_ENDPOINTS_WITHOUT_A_CONFIG = [
    "/api/live",
    "/api/league/race",
    "/api/league/rivals",
]


@pytest.mark.parametrize("path", HUB_ENDPOINTS_WITHOUT_A_CONFIG)
def test_a_missing_config_is_a_message_not_a_500(client, path):
    resp = client.get(path)
    assert resp.status_code == 422, path
    assert "config.toml" in resp.json()["detail"]


def test_the_matrix_and_the_journal_are_200_empty_not_errors(client):
    assert client.get("/api/fixtures/matrix").status_code == 200
    assert client.get("/api/journal").status_code == 200
    assert client.get("/api/journal").json()["rows"] == []


def test_the_plan_is_a_404_naming_the_command_that_fixes_it(client):
    resp = client.get("/api/plan/5")
    assert resp.status_code == 404
    assert "gaffer advise" in resp.json()["detail"]


def test_current_is_204_with_no_job_ever_started(client):
    assert client.get("/api/jobs/current").status_code == 204


def test_starting_an_unknown_kind_is_a_404_listing_the_real_ones(client):
    resp = client.post("/api/jobs/rm-rf")
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    for kind in ("advise", "evaluate", "refresh-data", "news-shadow"):
        assert kind in detail
