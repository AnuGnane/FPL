"""``/api/drafts`` — CRUD, and the comparison job.

The comparison is the point: three named constraint sets re-solved against
today's board, side by side, with the unconstrained optimum as the reference
row so "worse than what?" has an answer on the page.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gaffer.web.app import create_app
from tests.test_sensitivity import OWNED, _components, _save

BODY = {"name": "Salah route",
        "constraints": {"lock": [], "ban": [], "force_in": [], "max_hits": 0,
                        "chip": "none", "horizon": 2}}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text('[fpl]\nentry_id = 1\n'
                                          'league_id = 5\n')
    (tmp_path / "reports").mkdir()
    _save(tmp_path)
    _components(tmp_path)
    return TestClient(create_app())


def _run(client, names):
    """Submit a comparison and drain the legacy job registry, as the what-if
    lab's tests do."""
    accepted = client.post("/api/drafts/compare", json={"names": names})
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["job_id"]
    for _ in range(200):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            return job
    raise AssertionError("comparison never finished")


def test_no_drafts_is_an_empty_list(client):
    assert client.get("/api/drafts").json() == {"drafts": []}


def test_saving_a_draft_returns_the_list(client):
    body = client.post("/api/drafts", json=BODY).json()
    assert [d["name"] for d in body["drafts"]] == ["Salah route"]
    assert body["drafts"][0]["constraints"]["horizon"] == 2


def test_a_duplicate_name_is_a_structured_422(client):
    client.post("/api/drafts", json=BODY)
    response = client.post("/api/drafts", json=BODY)
    assert response.status_code == 422
    assert response.json()["detail"]["constraint"] == "draft_name"


def test_a_draft_naming_an_unknown_player_is_refused_at_write_time(client):
    """The same validation the what-if lab runs, run early: a draft that can
    never be solved is not worth saving."""
    response = client.post("/api/drafts", json={
        "name": "nonsense",
        "constraints": {**BODY["constraints"], "lock": [9999]}})
    assert response.status_code == 422
    assert response.json()["detail"]["constraint"] == "unknown_player"


def test_deleting_a_draft(client):
    client.post("/api/drafts", json=BODY)
    assert client.delete("/api/drafts/Salah route").json() == {"drafts": []}
    assert client.delete("/api/drafts/Salah route").status_code == 404


def test_a_comparison_has_the_optimum_as_its_reference_row(client):
    client.post("/api/drafts", json=BODY)
    job = _run(client, ["Salah route"])
    assert job["status"] == "done", job["error"]
    rows = job["result"]["rows"]
    assert rows[0]["name"] == "the optimum"
    assert rows[0]["is_reference"] is True
    assert rows[0]["delta_xpts"] == 0.0
    assert rows[1]["name"] == "Salah route"
    assert rows[1]["solved_at"].startswith("20")


def test_a_constrained_draft_never_beats_the_optimum(client):
    """It is the same board with strictly fewer legal squads on it."""
    client.post("/api/drafts", json={
        "name": "no star", "constraints": {**BODY["constraints"],
                                           "ban": [23]}})
    job = _run(client, ["no star"])
    row = job["result"]["rows"][1]
    assert row["delta_xpts"] <= 0.0
    assert row["horizon_pts"] < job["result"]["rows"][0]["horizon_pts"]


def test_each_row_carries_the_weeks_moves(client):
    client.post("/api/drafts", json=BODY)
    row = _run(client, ["Salah route"])["result"]["rows"][1]
    assert set(row) >= {"buys", "sells", "captain", "hits", "chip",
                        "expected_pts", "horizon_pts"}
    assert all("name" in p for p in row["buys"])


def test_an_infeasible_draft_is_a_row_with_a_reason_not_a_failed_job(client):
    """Locking fifteen players and forcing in a sixteenth cannot be solved;
    the other drafts in the comparison must still be shown."""
    client.post("/api/drafts", json={
        "name": "impossible",
        "constraints": {**BODY["constraints"], "lock": list(OWNED),
                        "force_in": [23], "max_hits": 0}})
    client.post("/api/drafts", json=BODY)
    job = _run(client, ["impossible", "Salah route"])
    assert job["status"] == "done", job["error"]
    rows = {r["name"]: r for r in job["result"]["rows"]}
    assert rows["impossible"]["error"]
    assert rows["impossible"]["horizon_pts"] is None
    assert rows["Salah route"]["horizon_pts"] is not None


def test_an_unknown_draft_name_is_a_422(client):
    assert client.post("/api/drafts/compare",
                       json={"names": ["ghost"]}).status_code == 422


def test_too_many_drafts_in_one_comparison_is_a_422(client):
    """A8: six solves plus the reference is the timeout budget."""
    for i in range(7):
        client.post("/api/drafts", json={**BODY, "name": f"d{i}"})
    response = client.post("/api/drafts/compare",
                           json={"names": [f"d{i}" for i in range(7)]})
    assert response.status_code == 422
    assert response.json()["detail"]["constraint"] == "too_many_drafts"


def test_no_solve_state_is_a_readable_422(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text('[fpl]\nentry_id = 1\n'
                                          'league_id = 5\n')
    (tmp_path / "reports").mkdir()
    client = TestClient(create_app())
    response = client.post("/api/drafts/compare", json={"names": []})
    assert response.status_code == 422
    assert "advise" in str(response.json()["detail"])
