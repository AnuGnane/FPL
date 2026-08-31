"""v8g's degraded states, pinned (spec G2).

Every card this cycle adds is a claim about the model's own uncertainty, which
makes a *wrong* card worse than no card: a band of width zero on a player
nobody has modelled, or a calibration curve drawn from an empty artifact, says
the tool is certain about something it has never measured. So the whole rail
set is about absence — absent artifact, absent minutes model, absent ledger,
absent σ asset — and about the one thing that must not change at all, which is
the number of job kinds.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import gaffer.optimize.scenarios as sc
from gaffer.artifacts import SolveState, save_components, save_solve_state
from gaffer.web.app import create_app

GW = 5

COMPONENTS = pd.DataFrame([
    {"code": 11, "element": 11, "name": "Saka", "position": "MID",
     "team_code": 3, "team_name": "Arsenal", "gw": GW, "opp_code": 4,
     "opp_name": "City", "was_home": 1.0, "kickoff_time": None,
     "p_play": 0.95, "p60": 0.9, "ep": 5.0}])

PLAYERS = pd.DataFrame({
    "code": [11], "element": [11], "name": ["Saka"], "position": ["MID"],
    "team_id": [1], "team_code": [3], "now_cost": [100], "status": ["a"],
    "news": [""], "chance_of_playing": [None], "selected_by_percent": [40.0],
    "form": [5.0], "points_per_game": [5.0], "ep_next": [5.0],
    "price_change_percent": [0.0], "price_change_calibrating": [False],
    "penalties_order": [1.0], "direct_freekicks_order": [None],
    "corners_and_indirect_freekicks_order": [None]})

TEAMS = pd.DataFrame({"code": [3, 4], "id": [1, 2],
                      "name": ["Arsenal", "City"],
                      "short_name": ["ARS", "MCI"]})

POOL = pd.DataFrame([
    {"code": 11, "name": "Saka", "position": "MID", "team_code": 3,
     "cost": 100, "sell": 100, "owned": True, "gw": GW, "ep_raw": 5.0}])


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    TEAMS.to_parquet(tmp_path / "data/live/teams.parquet", index=False)
    save_components(COMPONENTS, GW)
    save_solve_state(SolveState(
        gw=GW, gws=[GW], deadline="2026-09-01T11:00:00Z",
        generated_at="2026-08-31T09:00:00Z", mode="weekly", bank=0,
        free_transfers=1, owned_codes=[11], lam=0.0, league_eo={},
        avail_by_gw={GW: []},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.0, "horizon": 1, "hit_cost": 4,
             "max_transfers": 2, "bank_weight": 0.0},
        pool=POOL))
    return tmp_path, TestClient(create_app())


# --- rail 1: no evaluation artifact, no calibration cards --------------

def test_no_evaluation_is_a_422_with_a_sentence_not_a_page_of_zeros(app):
    """The Quality tab's existing contract, re-pinned because v8g adds cards
    to that tab and a new card must not invent its own empty state."""
    _, client = app
    response = client.get("/api/quality")
    assert response.status_code == 422
    assert "gaffer evaluate" in response.json()["detail"]


def test_an_evaluation_with_no_p_start_head_serves_the_others(app):
    """v8a's head is optional: an artifact written before it existed must
    still render its three older curves."""
    tmp_path, client = app
    (tmp_path / "reports/evaluation.json").write_text(json.dumps({
        "current": {"run_at": "x", "git_sha": "y", "holdout_slots": 10,
                    "stratified": {"all": {}}, "baselines": {"last5": {}},
                    "heads": {"p_play": {"log_loss": 0.4,
                                         "reliability": []}}}}))
    heads = client.get("/api/quality").json()["current"]["heads"]
    assert set(heads) == {"p_play"}


# --- rail 2: no components, no bands ----------------------------------

def test_no_components_file_means_no_bands_and_an_unchanged_headline(app):
    tmp_path, client = app
    (tmp_path / f"reports/components_gw{GW}.parquet").unlink()
    rows = client.get("/api/players").json()
    assert rows[0]["ep_next"] == pytest.approx(5.0)
    assert rows[0]["ep_lo"] is None and rows[0]["ep_hi"] is None
    assert rows[0]["p_haul"] is None and rows[0]["p_blank"] is None


def test_no_minutes_model_means_no_bands_on_the_breakdown(app):
    tmp_path, client = app
    save_components(COMPONENTS.drop(columns=["p_play", "p60"]), GW)
    player = client.get(f"/api/components/{GW}").json()["players"][0]
    assert player["ep"] == pytest.approx(5.0)
    for field in ("ep_lo", "ep_hi", "p_haul", "p_blank", "sigma"):
        assert player[field] is None, field


def test_a_band_is_never_a_zero_width_stand_in(app):
    """The rail behind A3, stated as the thing it forbids: an un-modelled
    player must not come back looking like the most certain one on the page."""
    tmp_path, client = app
    save_components(COMPONENTS.drop(columns=["p_play", "p60"]), GW)
    player = client.get(f"/api/components/{GW}").json()["players"][0]
    assert player["ep_lo"] != player["ep_hi"] or player["ep_lo"] is None


# --- rail 3: no ledger, the "too early" branch ------------------------

def test_an_empty_ledger_is_the_too_early_branch(app):
    _, client = app
    body = client.get("/api/confidence").json()
    assert body["captain"]["tier"] == "early"
    assert body["captain"]["graded"] == 0
    assert "%" not in body["captain"]["text"]


def test_a_corrupt_ledger_is_the_too_early_branch(app):
    tmp_path, client = app
    (tmp_path / "reports/decision_ledger.json").write_text("{half-written")
    assert client.get("/api/confidence").json()["captain"]["tier"] == "early"


def test_three_graded_gameweeks_still_decline_to_grade(app):
    """MIN_GRADED is a bar, not a suggestion."""
    from gaffer.confidence import MIN_GRADED

    tmp_path, client = app
    (tmp_path / "reports/decision_ledger.json").write_text(json.dumps({
        "gws": [{"gw": g, "lanes": [{"lane": "captaincy", "delta_pts": -2,
                                     "aligned": False}]}
                for g in range(1, MIN_GRADED)]}))
    assert client.get("/api/confidence").json()["captain"]["tier"] == "early"


# --- rail 4: no σ asset, the pre-v6 heuristic exactly -----------------

def test_no_noise_asset_bands_on_the_pre_v6_heuristic_exactly(monkeypatch):
    """v6's rail, copied forward to the new consumer. The band module is the
    second reader of that asset, and a clone without the file has to produce
    the same scale here as the sweep does there."""
    import gaffer.uncertainty as unc

    monkeypatch.setattr(unc, "scenario_noise", lambda: None)
    ep, xmins = 4.0, 20.0
    band = unc.band_for(ep, xmins)
    want = ep * (sc.NOISE_FLOOR_XMINS - xmins) / sc.NOISE_DENOM
    assert band.sigma == pytest.approx(round(want, 3))
    # And the centre is the EP itself: the heuristic scale is multiplicative
    # and vanishes with the EP, so ``noise_ep`` does not recentre it.
    assert band.ep_lo + band.ep_hi == pytest.approx(2 * ep, abs=0.01)


def test_an_unreadable_noise_asset_bands_on_the_heuristic(monkeypatch):
    def boom():
        raise OSError("disk")

    import gaffer.uncertainty as unc

    monkeypatch.setattr(sc, "CALIBRATED_NOISE_DEFAULT", True)
    monkeypatch.setattr(sc, "load_scenario_noise", boom)
    sc.scenario_noise.cache_clear()
    try:
        assert unc.shipped_table() is None
        assert unc.band_for(4.0, 20.0) is not None
    finally:
        sc.scenario_noise.cache_clear()


def test_the_band_module_reads_the_asset_through_one_seam():
    """If a second loader ever appears here, the rail above stops pinning
    anything: it monkeypatches exactly one name."""
    import inspect

    import gaffer.uncertainty as unc

    src = inspect.getsource(unc)
    assert "load_scenario_noise" not in src
    assert src.count("def shipped_table") == 1


# --- rail 5: no scored week, no misses card ---------------------------

def test_no_results_frame_is_an_absent_misses_card(app):
    _, client = app
    body = client.get("/api/misses").json()
    assert body == {"gw": None, "rows": []}


def test_results_for_an_unforecast_week_are_an_absent_card(app):
    tmp_path, client = app
    pd.DataFrame([{"code": 11, "gw": 99, "total_points": 8,
                   "minutes": 90}]).to_parquet(
        tmp_path / "data/live/player_gw.parquet", index=False)
    assert client.get("/api/misses").json()["gw"] is None


# --- rail 6: no sensitivity report, no noise line ---------------------

def test_no_sensitivity_report_carries_no_decision_sigma(app):
    _, client = app
    body = client.get("/api/sensitivity").json()
    assert body["available"] is False
    assert body["decision_sigma"] is None


# --- rail 7: v8g adds no job kinds ------------------------------------

def test_v8g_adds_no_job_kinds():
    """The pin five other degradation suites already assert, asserted a sixth
    time from this cycle's own file so a v8g task that reaches for a job kind
    fails in its own suite rather than in somebody else's."""
    from gaffer.web.job_kinds import JOB_KINDS

    assert len(JOB_KINDS) == 10


def test_v8g_added_no_config_key():
    """Spec D5: no config. A key added here would be a switch nobody finds
    and a degraded state nobody tests.

    The plan's rail screened for the substrings ``band``/``uncertainty``/
    ``confidence``; ``z_deadband`` is a v7 key that has carried the first of
    those since long before this cycle, so the screen is narrowed to whole
    names and then backed by a count pin — which catches a v8g key whatever it
    is called, not only one that happens to be named after the feature.
    """
    import dataclasses

    from gaffer.config import Config

    names = {f.name for f in dataclasses.fields(Config)}
    assert not [n for n in names
                if ("band" in n and n != "z_deadband")
                or "uncertainty" in n or "confidence" in n]
    # 47 keys as of v8f. v8g adds none, so any change to this number is a
    # config key this cycle had no business adding.
    assert len(names) == 47


# --- rail 8: protected ordering, forward -----------------------------

def test_the_availability_pass_still_ends_with_the_override(app):
    """v8e's ordering pin, carried forward: v8g touches none of that path and
    the rail says so out loud rather than by omission."""
    import inspect

    from gaffer.models import availability

    src = inspect.getsource(availability.apply_availability)
    assert "_override_first_gw(out)" in src


def test_the_band_module_never_writes(app):
    """Serve-time only. A module that banked anything would be a train/serve
    seam nobody asked for."""
    import inspect

    import gaffer.uncertainty as unc

    src = inspect.getsource(unc)
    for forbidden in ("to_parquet", "write_text", "save_", "open("):
        assert forbidden not in src, forbidden
