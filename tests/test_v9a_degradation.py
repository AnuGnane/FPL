"""v9a degradation rails (gate G2).

The pitch is decoration over a page that already worked, so every rail here
asks the same question of a different missing thing: does This Week still
render? The answer has to be the same every time — a plain shirt, a chip that
says "Blank", a printed line on the server — and never a 500, never a
traceback, and never a broken image.

The two pins at the end are not degradations. The job-kind count and the
config-field count did **not** move this cycle (spec §2: no new job kinds, no
new config keys), and asserting the unchanged numbers from this cycle's own
file is what makes the next cycle's accidental addition fail in its own suite
rather than in six older ones.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.data import store
from gaffer.web.app import create_app
from gaffer.web.routers import assets

GW = 5

PLAYERS = pd.DataFrame({
    "code": [11, 22], "name": ["Saka", "Haaland"],
    "position": ["MID", "FWD"], "team_id": [1, 13], "team_code": [3, 43],
    "now_cost": [101, 150], "selected_by_percent": [40.0, 60.0],
})
TEAMS = pd.DataFrame({"team_id": [1, 13, 14], "code": [3, 43, 1],
                      "name": ["Arsenal", "Man City", "Man Utd"],
                      "short_name": ["ARS", "MCI", "MUN"]})
FIXTURES = pd.DataFrame({
    "gw": [GW], "home_id": [1], "away_id": [14],
    "kickoff_time": ["2026-09-12T14:00:00Z"],
    "home_goals": [None], "away_goals": [None], "finished": [False]})

# ``staleness_for`` reads the event table on every request to /api/advice, so
# the route needs one on disk before it can answer at all — the same two-row
# table the rest of the advice suite writes.
EVENTS = pd.DataFrame([
    {"gw": GW, "deadline_time": "2026-09-11T17:30:00Z", "is_current": False,
     "is_next": True, "finished": False, "data_checked": False},
    {"gw": GW + 1, "deadline_time": "2099-09-18T17:30:00Z",
     "is_current": False, "is_next": False, "finished": False,
     "data_checked": False}])

ADVICE = {
    "gw": GW, "hits": 0, "expected_pts": 54.3,
    "xi": [{"code": 11, "name": "Saka", "position": "MID", "ep": 5.1}],
    "bench": [{"code": 22, "name": "Haaland", "position": "FWD", "ep": 6.2}],
    "buys": [], "sells": [],
    "captain": {"code": 11, "name": "Saka", "position": "MID", "ep": 5.1},
    "vice": {"code": 22, "name": "Haaland", "position": "FWD", "ep": 6.2},
    "chip_table": [], "strategy": None,
}

PRE_EXISTING = ("code", "name", "position", "ep")
"""What an advice player entry carried before this cycle. The enrichment is
additive, and this tuple is how the byte-identity rail says so."""


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    from gaffer.artifacts import SolveState, save_solve_state

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    (tmp_path / "data" / "live").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    TEAMS.to_parquet(tmp_path / "data/live/teams.parquet", index=False)
    FIXTURES.to_parquet(tmp_path / "data/live/fixtures_all.parquet",
                        index=False)
    EVENTS.to_parquet(tmp_path / "data/live/events.parquet", index=False)
    (tmp_path / "reports" / f"gw{GW}-advice.json").write_text(
        json.dumps(ADVICE))
    save_solve_state(SolveState(
        gw=GW, gws=[GW], deadline="2026-09-11T17:30:00Z",
        generated_at="2026-09-10T20:00:00+00:00", mode="weekly", bank=0.5,
        free_transfers=1, owned_codes=[11, 22], lam=0.0, league_eo={},
        cover={}, avail_by_gw={}, opt={},
        pool=pd.DataFrame({"code": [11, 22], "position": ["MID", "FWD"]})))
    monkeypatch.setattr(assets, "_fetch", lambda url: b"fake-image-bytes")
    return tmp_path, TestClient(create_app())


# --- rail 1: a dead upstream --------------------------------------

def test_a_dead_cdn_serves_the_bundled_fallback_with_a_short_max_age(
        wired, monkeypatch):
    """G2, first clause. The pitch renders identically with zero network."""
    _tmp, client = wired
    monkeypatch.setattr(assets, "_fetch", lambda url: (_ for _ in ()).throw(
        RuntimeError("network is unreachable")))
    response = client.get("/api/assets/shirt/3")
    assert response.status_code == 200
    assert b"<svg" in response.content
    assert "max-age=60" in response.headers["cache-control"]


def test_a_dead_cdn_writes_nothing_at_all(wired, monkeypatch):
    tmp_path, client = wired
    monkeypatch.setattr(assets, "_fetch", lambda url: (_ for _ in ()).throw(
        RuntimeError("network is unreachable")))
    client.get("/api/assets/shirt/3")
    client.get("/api/assets/photo/11")
    cache = tmp_path / "data/live/assets"
    assert not cache.exists() or list(cache.iterdir()) == []


def test_a_cache_hit_never_refetches(wired, monkeypatch):
    _tmp, client = wired
    client.get("/api/assets/shirt/3")
    monkeypatch.setattr(assets, "_fetch", lambda url: (_ for _ in ()).throw(
        AssertionError("a cache hit refetched")))
    assert client.get("/api/assets/shirt/3").status_code == 200


# --- rail 2: the allowlist and the path ---------------------------

@pytest.mark.parametrize("path", [
    "/api/assets/shirt/../../etc/passwd",
    "/api/assets/shirt/..%2F..%2Fetc%2Fpasswd",
    # Two dots rather than three: httpx normalises the path *before* it is
    # sent, and a third pair would climb above /api entirely — testing the
    # client's normaliser rather than this router's refusal.
    "/api/assets/photo/../../secret",
    "/api/assets/photo/..%2F..%2F..%2Fsecret",
    "/api/assets/shirt/3.webp",
])
def test_path_traversal_is_refused_before_any_handler_runs(wired, path):
    tmp_path, client = wired
    assert client.get(path).status_code in (404, 422)
    assert not (tmp_path / "data/live/assets").exists()


def test_a_code_outside_the_bootstrap_is_refused_without_a_fetch(wired,
                                                                 monkeypatch):
    """Not an open proxy (spec §2)."""
    _tmp, client = wired
    monkeypatch.setattr(assets, "_fetch", lambda url: (_ for _ in ()).throw(
        AssertionError("fetched for a code the bootstrap does not know")))
    assert client.get("/api/assets/shirt/999").status_code == 404
    assert client.get("/api/assets/photo/999999").status_code == 404


# --- rail 3: a corrupt or absent fixture list ---------------------

def test_a_corrupt_fixture_file_nulls_every_next_fixture(wired):
    tmp_path, client = wired
    (tmp_path / "data/live/fixtures_all.parquet").write_bytes(b"not parquet")
    advice = client.get("/api/advice/latest").json()["advice"]
    assert advice["xi"][0]["next_fixture"] is None
    assert advice["bench"][0]["next_fixture"] is None


def test_an_absent_fixture_file_nulls_every_next_fixture(wired):
    tmp_path, client = wired
    (tmp_path / "data/live/fixtures_all.parquet").unlink()
    advice = client.get("/api/advice/latest").json()["advice"]
    assert advice["xi"][0]["next_fixture"] is None


def test_the_squad_payloads_pre_existing_fields_survive_a_broken_fixture_file(
        wired):
    """G2's byte-identity clause: everything that was there is still there,
    with the same values, and only the three new keys are added."""
    tmp_path, client = wired
    (tmp_path / "data/live/fixtures_all.parquet").unlink()
    advice = client.get("/api/advice/latest").json()["advice"]
    for key in ("xi", "bench"):
        for served, original in zip(advice[key], ADVICE[key]):
            assert all(served[f] == original[f] for f in PRE_EXISTING)
            assert set(served) - set(original) == {"team_short", "team_code",
                                                   "next_fixture"}


def test_a_blank_gameweek_is_a_null_fixture_not_a_zero(wired):
    """D2: the chip says "blank" honestly."""
    _tmp, client = wired
    advice = client.get("/api/advice/latest").json()["advice"]
    # Man City have no GW5 fixture in the banked list.
    assert advice["bench"][0]["team_short"] == "MCI"
    assert advice["bench"][0]["next_fixture"] is None


# --- rail 4: a bootstrap without team identity --------------------

def test_a_players_snapshot_without_team_code_is_nulls_not_a_raise(wired):
    tmp_path, client = wired
    PLAYERS.drop(columns=["team_code"]).to_parquet(
        tmp_path / "data/live/players.parquet", index=False)
    advice = client.get("/api/advice/latest").json()["advice"]
    assert advice["xi"][0]["team_code"] is None
    assert advice["xi"][0]["team_short"] is None


def test_an_absent_teams_snapshot_is_nulls_not_a_raise(wired):
    tmp_path, client = wired
    (tmp_path / "data/live/teams.parquet").unlink()
    advice = client.get("/api/advice/latest").json()["advice"]
    assert advice["xi"][0]["team_short"] is None


def test_a_clone_with_no_snapshots_at_all_still_serves_the_advice(wired):
    """The coldest case: the artifact is on disk and nothing else is."""
    tmp_path, client = wired
    for name in ("players", "teams", "fixtures_all"):
        (tmp_path / f"data/live/{name}.parquet").unlink()
    body = client.get("/api/advice/latest").json()
    assert body["advice"]["xi"][0]["name"] == "Saka"
    assert body["advice"]["xi"][0]["team_short"] is None


# --- rail 5: an unrateable fixture --------------------------------

def test_a_fixture_the_ticker_cannot_rate_keeps_the_chip_and_loses_the_tint(
        wired, monkeypatch):
    from gaffer.web.routers import meta

    _tmp, client = wired
    monkeypatch.setattr(meta, "ticker", lambda weeks=8: (_ for _ in ()).throw(
        RuntimeError("no odds, no elo")))
    fixture = client.get("/api/advice/latest").json()[
        "advice"]["xi"][0]["next_fixture"]
    assert fixture["opponent_short"] == "MUN"
    assert fixture["difficulty"] is None


# --- rail 6: the artifact is never rewritten ----------------------

def test_serving_the_pitch_never_touches_the_advice_artifact(wired):
    """A2. The enrichment is a decoration on the way out; the file the next
    ``advise`` run diffs against must be byte-identical."""
    tmp_path, client = wired
    path = tmp_path / "reports" / f"gw{GW}-advice.json"
    before = path.read_bytes()
    client.get("/api/advice/latest")
    client.get("/api/advice/latest")
    assert path.read_bytes() == before


# --- pins: nothing moved this cycle -------------------------------

def test_the_job_kinds_are_still_twelve(wired):
    """Spec §2: no new job kinds. The pitch is a read, not a run."""
    from gaffer.web.job_kinds import JOB_KINDS

    assert len(JOB_KINDS) == 12


def test_the_config_still_has_no_assets_section(wired):
    """A7: the CDN bases are module constants, deliberately, because a config
    key would have broken a count pin inside a protected rail file."""
    from gaffer.config import Config

    assert not any(f.startswith("assets") for f in Config.__dataclass_fields__)


def test_the_asset_router_is_the_only_new_route_prefix(wired):
    # The schema rather than ``app.routes``: this FastAPI keeps an included
    # router as one opaque wrapper object in ``routes``, so the flat list of
    # paths only exists in the generated OpenAPI document.
    _tmp, client = wired
    paths = set(client.app.openapi()["paths"])
    new = {p for p in paths if p.startswith("/api/assets")}
    assert new == {"/api/assets/shirt/{team_code}",
                   "/api/assets/photo/{player_code}"}
