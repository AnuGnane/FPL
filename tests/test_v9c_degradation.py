"""v9c's degradation rails (gate G2).

Every rail here is a state a real machine reaches: a season whose fixture list
was never archived, a corrupt one, an advice file banked before this cycle, a
job that wedged. The pins at the end are the counts that did *not* move — a
cancel is a DELETE on a lane, not a thirteenth job kind, and
``ADVISE_TIMEOUT_S`` is a module constant that finally acquired a reader, not
a new config knob.

The single most valuable assertion in the file is
``test_a_prediction_frames_future_rows_all_have_an_elo``. If a later cycle
"simplifies" ``engineer.as_of_club`` from a per-row coalesce into a
column-presence check, that is what fails — and the failure is worth reading
rather than adjusting, because the bug it catches is a model predicting every
serving row against a null opponent.
"""

from __future__ import annotations

import json
import threading

import pandas as pd
from fastapi.testclient import TestClient

from gaffer.artifacts import SolveState, pool_rows, save_solve_state
from gaffer.features.bps import as_of_club_code
from gaffer.features.engineer import (ROLL_STATS, add_player_rolling,
                                      as_of_club, build_prediction_frame,
                                      feature_columns)
from gaffer.models.components import card_penalty
from gaffer.web.app import create_app
from gaffer.web.jobs import JobRunner


# =====================================================================
# Block 1 — the card term (D1 shipped: the arm passed, so it is live)
# =====================================================================

def _cards(n: int = 6) -> pd.DataFrame:
    return pd.DataFrame({
        "code": [1] * n, "season_idx": [3] * n, "gw": list(range(1, n + 1)),
        "rc": [1.0] + [0.0] * (n - 1), "yc": [0.0] * n,
        "minutes": [90.0] * n,
    })


def test_rc_r38_is_built_and_is_not_all_nan_on_a_frame_with_a_red_card():
    rolled = add_player_rolling(_cards())
    assert "rc_r38" in rolled.columns
    assert rolled["rc_r38"].notna().any()
    assert (rolled["rc_r38"].fillna(0.0) > 0).any()


def test_card_penalty_separates_a_sent_off_row_from_a_clean_one():
    """The D1 finding, as a rail. Before v9c these two returned the same
    number for every player in every gameweek."""
    sent_off = pd.Series({"yc_r38": 0.0, "rc_r38": 0.2})
    clean = pd.Series({"yc_r38": 0.0, "rc_r38": 0.0})
    assert card_penalty(sent_off) < card_penalty(clean)


def test_a_frame_with_no_card_columns_at_all_still_gives_a_finite_penalty():
    """``_rate``'s NaN guard doing its real job again — the one it was written
    for — now that it is no longer covering for a missing column."""
    assert card_penalty(pd.Series({"minutes": 90.0})) == 0.0
    assert card_penalty(pd.Series({"yc_r38": float("nan"),
                                   "rc_r38": float("nan")})) == 0.0


def test_rc_is_in_roll_stats_and_the_arm_that_put_it_there_is_on_the_record():
    """The D1 branch taken, pinned. A later cycle that drops the entry has to
    face the measurement that shipped it rather than a bare list."""
    assert "rc" in ROLL_STATS
    doc = _roll_stats_doc()
    assert "Measured, v9c G1" in doc
    assert "0.005" in doc


def _roll_stats_doc() -> str:
    """``ROLL_STATS``'s docstring, which is a module-level attribute docstring
    and therefore not reachable as ``ROLL_STATS.__doc__`` (it is a list). Read
    from source, which is also what a reader does."""
    import inspect

    import gaffer.features.engineer as eng

    source = inspect.getsource(eng)
    start = source.index("ROLL_STATS = [")
    return source[start:start + 2000]


# =====================================================================
# Block 2 — the as-of club
# =====================================================================

def _fixtures() -> pd.DataFrame:
    return pd.DataFrame({
        "season_idx": [3, 3], "gw": [1, 2],
        "kickoff_time": ["2024-08-17T14:00:00Z", "2024-08-24T14:00:00Z"],
        "home_code": [3, 43], "away_code": [1, 3],
    })


def _rows() -> pd.DataFrame:
    return pd.DataFrame({
        "code": [7, 7], "season_idx": [3, 3], "gw": [1, 2],
        "kickoff_time": ["2024-08-17T14:00:00Z", "2024-08-24T14:00:00Z"],
        "team_code": [3, 3], "opp_code": [3, 43], "was_home": [False, True],
    })


def test_a_season_with_no_fixture_rows_falls_back_and_never_nan_scatters():
    """The named G2 clause: a NaN club would scatter every downstream
    ``groupby`` into a silent extra bucket, which is a worse failure than the
    staleness this column exists to fix."""
    club = as_of_club_code(_rows(), _fixtures().iloc[0:0])
    assert club.notna().all()
    assert club.tolist() == [3, 3]


def test_a_corrupt_fixture_list_drops_to_the_fallback_rather_than_mis_keys():
    """``fixture_key``'s duplicate poisoning, inherited. A mis-keyed club is
    worse than a stale one: it is a club the player never played for."""
    dupes = pd.concat([_fixtures(),
                       _fixtures().iloc[[0]].assign(away_code=99)],
                      ignore_index=True)
    assert as_of_club_code(_rows(), dupes).iloc[0] == 3


def test_a_fixture_list_missing_home_code_degrades_instead_of_raising():
    thin = _fixtures().drop(columns=["home_code"])
    assert as_of_club_code(_rows(), thin).tolist() == [3, 3]


def test_a_player_frame_missing_the_join_columns_degrades_too():
    assert as_of_club_code(_rows().drop(columns=["kickoff_time"]),
                           _fixtures()).tolist() == [3, 3]


def test_as_of_club_on_a_frame_with_no_club_code_is_the_stamped_club():
    assert as_of_club(_rows()).tolist() == [3, 3]


def test_a_prediction_frames_future_rows_all_have_an_elo():
    """Plan A6, and the rail worth reading rather than adjusting. History
    carries ``club_code``, future rows cannot; a frame-level presence check
    would read NaN for every serving row and the model would predict against
    a null opponent strength."""
    elo = pd.DataFrame({"season_idx": [3] * 4, "gw": [1, 1, 3, 3],
                        "code": [1, 3, 1, 3],
                        "elo_pre": [1500.0, 1600.0, 1520.0, 1580.0]})
    hist = _rows().assign(club_code=[1, 3], position=["MID", "MID"],
                          minutes=[90.0, 90.0], starts=[1.0, 1.0],
                          total_points=[5.0, 6.0])
    future = pd.DataFrame({
        "code": [7], "season_idx": [3], "gw": [3], "team_code": [3],
        "opp_code": [1], "was_home": [True], "position": ["MID"],
        "kickoff_time": ["2024-08-31T14:00:00Z"]})
    out = build_prediction_frame(hist, future, elo=elo, elo_final=None)
    assert out["team_elo"].notna().all()
    assert out["opp_elo"].notna().all()


def test_club_code_is_not_a_feature_column_so_advise_never_strips_it():
    """Plan A10, pinned without editing a protected file."""
    assert "club_code" not in feature_columns()


# =====================================================================
# Block 3 — the boundary rename, both directions
# =====================================================================

PAST = "2026-08-01T17:30:00Z"
GW = 3

OLD_ADVICE = {
    "gw": GW, "deadline": PAST, "buys": [], "sells": [], "hits": 0,
    "xi": [], "bench": [], "captain": {"code": 100, "name": "Salah"},
    "vice": None,
    "captain_options": [{"code": 100, "name": "Salah", "p_haul": 0.55}],
    "alternatives": [{"code": 11, "name": "Saka", "p_haul": 0.4}],
    "chip_table": [], "wildcard_now": None, "threats": [], "price_alerts": [],
    "expected_pts": 0.0, "plan_by_gw": [], "strategy": {}, "win_probs": [],
    "mode": "weekly",
}


def _write_advice(root, advice):
    (root / "reports").mkdir(exist_ok=True)
    path = root / "reports" / f"gw{GW}-advice.json"
    path.write_text(json.dumps(advice))
    pool = pool_rows(
        pd.DataFrame([{"code": 100, "position": "MID", "team_code": 300,
                       "cost": 130, "sell": 128}]),
        pd.DataFrame([{"code": 100, "name": "Salah"}]),
        owned_codes=[100], ep_by={(100, GW): 6.4}, gws=[GW])
    save_solve_state(SolveState(
        gw=GW, gws=[GW], deadline=PAST,
        generated_at="2026-09-10T09:00:00Z", mode="weekly", bank=12,
        free_transfers=2, owned_codes=[100], lam=0.25, league_eo={},
        avail_by_gw={GW: []},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.5, "itb_value": 0.05, "hit_cost": 4, "horizon": 1},
        pool=pool))
    events = pd.DataFrame([{"gw": GW, "deadline_time": PAST,
                            "is_current": False, "is_next": True,
                            "finished": False, "data_checked": False}])
    (root / "data" / "live").mkdir(parents=True, exist_ok=True)
    events.to_parquet(root / "data" / "live" / "events.parquet", index=False)
    return path


def test_an_advice_file_banked_before_this_cycle_serves_renamed(
        tmp_path, monkeypatch):
    """And the file on disk is byte-identical afterwards: ``digest.py`` reads
    it and the since-last-run diff compares against it."""
    monkeypatch.chdir(tmp_path)
    path = _write_advice(tmp_path, OLD_ADVICE)
    before = path.read_bytes()
    assert b"p_attacking_haul" not in before

    body = TestClient(create_app()).get("/api/advice/latest").json()["advice"]
    assert body["alternatives"][0]["p_attacking_haul"] == 0.4
    assert "p_haul" not in body["alternatives"][0]
    assert body["captain_options"][0]["p_attacking_haul"] == 0.55
    assert "p_haul" not in body["captain_options"][0]
    assert path.read_bytes() == before


def test_a_payload_with_no_alternatives_key_at_all_is_a_200(
        tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cold = {k: v for k, v in OLD_ADVICE.items()
            if k not in ("alternatives", "captain_options")}
    _write_advice(tmp_path, cold)
    response = TestClient(create_app()).get("/api/advice/latest")
    assert response.status_code == 200


def test_the_band_quantity_keeps_its_name_on_both_typed_payloads():
    """The other direction. Renaming both would leave the page exactly as
    ambiguous as it was, in a new vocabulary."""
    from gaffer.web.schemas import ComponentPlayer, PlayerRow

    for model in (PlayerRow, ComponentPlayer):
        assert "p_haul" in model.model_fields
        assert "p_attacking_haul" not in model.model_fields


# =====================================================================
# Block 4 — the freed lane
# =====================================================================

def test_a_wedged_job_past_the_timeout_frees_the_lane_on_the_next_start(
        monkeypatch):
    from gaffer.web import jobs as jobs_module

    release = threading.Event()
    monkeypatch.setattr(jobs_module, "ADVISE_TIMEOUT_S", 0.05)
    runner = JobRunner({"advise": lambda: release.wait(5.0),
                        "evaluate": lambda: None})
    first = runner.start("advise")
    import time
    time.sleep(0.1)
    assert runner.start("evaluate")
    wedged = runner.get(first)
    assert wedged.status == "failed"
    assert "timed out" in wedged.error and "abandoned" in wedged.error
    release.set()


def test_delete_current_is_404_when_idle_and_frees_the_lane_when_busy(
        tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    release = threading.Event()
    app = create_app()
    app.state.job_runner = JobRunner({"advise": lambda: release.wait(5.0),
                                      "evaluate": lambda: None})
    client = TestClient(app)

    assert client.delete("/api/jobs/current").status_code == 404
    client.post("/api/jobs/advise")
    assert client.post("/api/jobs/evaluate").status_code == 409
    assert client.delete("/api/jobs/current").status_code == 200
    assert client.post("/api/jobs/evaluate").status_code == 202
    release.set()


def test_a_normal_run_still_reaches_done_with_no_error():
    """The rail against a reaper that reaps the living."""
    import time

    runner = JobRunner({"advise": lambda: {"gw": 5}})
    job_id = runner.start("advise")
    deadline = time.time() + 5.0
    while time.time() < deadline and runner.get(job_id).status == "running":
        time.sleep(0.01)
    run = runner.get(job_id)
    assert run.status == "done" and run.error is None
    assert runner.current() is None


# =====================================================================
# Block 5 — pins for what did not move (plan A13)
# =====================================================================

def test_the_job_kinds_are_still_twelve():
    """Spec §2: no new job kinds. A cancel is a DELETE on a lane, not a
    thirteenth thing to run."""
    from gaffer.web.job_kinds import JOB_KINDS

    assert len(JOB_KINDS) == 12


def test_the_config_gained_no_field():
    """Spec §2: no new config keys. ``ADVISE_TIMEOUT_S`` is a module constant
    that finally acquired a reader, not a knob."""
    import dataclasses

    from gaffer.config import Config

    assert len(dataclasses.fields(Config)) == 48


def test_the_jobs_routes_are_the_four_plus_the_new_delete(tmp_path,
                                                          monkeypatch):
    """The DELETE shares a path with the GET, so the OpenAPI path set does
    not move — which is why no pre-existing route pin needed updating this
    cycle (plan A13). Pinned here so the *methods* are named somewhere."""
    monkeypatch.chdir(tmp_path)
    schema = create_app().openapi()["paths"]
    assert set(schema["/api/jobs/current"]) == {"get", "delete"}


# =====================================================================
# Review I1 — the advice artifact is written atomically
# =====================================================================

def test_the_advice_artifact_is_written_through_a_temp_and_os_replace():
    """Review I1, source-pinned because ``tests/test_advise.py`` is protected
    and ``run_advise`` is not callable without the whole pipeline behind it.

    Three docstrings — ``JobRunner._abandon_current``, ``abandon_current`` and
    ``cancel_current`` — now rest on "every job kind writes its artifacts
    idempotently", which is the argument that makes abandoning a wedged job
    safe. A plain ``write_text`` does not clear that bar: it is idempotent
    across whole runs but *interruptible* within one, and the abandoned thread
    that keeps running is precisely the caller that can be halfway through it
    while its replacement reads the file. The house idiom (``digest.py``) is a
    pid-suffixed temp plus ``os.replace``.
    """
    import inspect

    import gaffer.advise as advise_mod
    import gaffer.io as io_mod

    source = inspect.getsource(advise_mod)
    start = source.index('f"gw{gw}-advice.json"')
    window = source[start - 600:start + 600]
    # v12 W1 §2.11 (specs/2026-09-01-gaffer-v12-program-design.md). The idiom
    # moved into gaffer.io, so the grep follows it. `atomic_write` in the
    # window is a *stronger* assertion than `os.replace` was: a comment
    # mentioning os.replace would have satisfied the old one, and a comment
    # cannot satisfy this one, because the name has to be called.
    assert "atomic_write(" in window
    # And the non-atomic form is gone, not merely joined.
    assert 'f"gw{gw}-advice.json").write_text' not in source
    # The guarantee itself, checked where it now lives.
    helper = inspect.getsource(io_mod)
    assert "os.replace" in helper and "os.getpid()" in helper


def test_the_helper_this_borrowed_from_still_uses_the_same_idiom():
    """If ``gaffer.io`` ever stops being the reference, the comment in
    ``advise.py`` pointing at it becomes a lie. Cheap to notice here.

    v12 W1 §2.11: this used to name ``digest.py``, which was the house
    reference until twenty copies of its four lines were replaced by one
    helper. ``digest.py`` is now a caller like every other.
    """
    import inspect

    import gaffer.digest as digest_mod
    import gaffer.io as io_mod

    assert "os.replace" in inspect.getsource(io_mod)
    assert "os.getpid()" in inspect.getsource(io_mod)
    assert "atomic_write(" in inspect.getsource(digest_mod)
