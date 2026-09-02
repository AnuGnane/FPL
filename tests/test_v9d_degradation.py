"""v9d's degradation rails (gate G3).

Every rail here is a state a real machine reaches: a server started with a
worker count, a parquet refreshed under a warm cache, a job cancelled rather
than timed out, a gameweek graded from an artifact written after the whistle.
The pins at the end are the counts that did *not* move — twelve job kinds, and
no config key for ``ABANDON_TIMEOUT_S`` — and the one that moved by exactly
one. (The absolute config-field total used to be asserted here too; v12 W1
moved it to ``tests/test_v12_w1_degradation.py``, where it is the only one in
the suite.)

The most valuable assertion in the file is
``test_the_ui_serves_an_app_instance_and_never_a_worker_count``. Everything
about the job runner's state — the single lane, the in-memory run records, the
SSE line buffers — lives on one process's ``app.state.job_runner``. Nothing in
the tree says so today, and the day someone "optimises" the serve command into
an import string with ``workers=4`` the failure is not a crash: it is a browser
watching a job that a different worker is running, forever.
"""

from __future__ import annotations

import inspect

import pandas as pd
from fastapi.testclient import TestClient

from gaffer.web.app import create_app


# =====================================================================
# Block 1 — §2, the single-process contract
# =====================================================================

def _uvicorn_call() -> str:
    """The text of ``cli.ui``'s ``uvicorn.run(...)`` call.

    Source inspection rather than execution, for the reason plan A6 gives:
    the thing being defended is the *shape of a call*, and actually starting a
    server would be a different test that could pass while the shape was
    wrong. The same idiom guards the protected advice write at
    ``tests/test_v9c_degradation.py:337``.
    """
    import gaffer.cli as cli_mod

    source = inspect.getsource(cli_mod)
    start = source.index("uvicorn.run(")
    return source[start:source.index(")", start) + 1]


def test_the_ui_serves_an_app_instance_and_never_a_worker_count():
    """Spec §2. ``uvicorn`` forks workers only when it is handed an import
    string; handed an app *instance* it cannot, which is the only reason the
    single lane and the SSE buffers on ``app.state.job_runner`` work at all
    today. Both halves are asserted, because either alone can be defeated."""
    call = _uvicorn_call()
    # v12 W1 §2.8 (specs/2026-09-01-gaffer-v12-program-design.md): the literal
    # `create_app()`. §2.8 gave `create_app` a keyword-only `token`, and the
    # LAN branch passes it — so the literal forced `cli.ui` to spell one call
    # as two branches, one per argument list, purely to keep this grep
    # matching. That is a source pin changing shipped code to suit itself.
    # The prefix is what the claim was ever about: an app *instance*, built
    # here, rather than an import string uvicorn could fork workers from. The
    # two asserts below are the substance and neither is weakened.
    assert "create_app(" in call
    assert '"' not in call.split(",")[0], (
        "the first argument became an import string — uvicorn can fork "
        "workers off one of those, and every job-runner invariant assumes "
        "one process")
    assert "workers" not in call


def test_the_contract_is_stated_where_the_server_starts():
    """A rail that only pins the call shape teaches nobody why. The reason
    has to be readable at the call site, or the next person removes the
    constraint correctly and breaks the product."""
    import gaffer.cli as cli_mod

    source = inspect.getsource(cli_mod)
    window = source[source.index("uvicorn.run(") - 900:
                    source.index("uvicorn.run(")]
    assert "single process" in window


def test_the_job_runner_says_it_is_per_process():
    """The other end of the same contract. ``JobRunner`` is where the state
    lives, so it is where a reader looks first."""
    from gaffer.web.jobs import JobRunner

    assert "single process" in (JobRunner.__doc__ or "")


# =====================================================================
# Block 2 — §1, the two switched consumers
# =====================================================================

def _players(**over) -> "pd.DataFrame":
    frame = pd.DataFrame({
        "code": [7, 7],
        "season_idx": [3, 3],
        "gw": [1, 2],
        "kickoff_time": ["2024-08-17T14:00:00Z", "2024-08-24T14:00:00Z"],
        "team_code": [3, 3],
        "club_code": [1, 3],
        "opp_code": [43, 43],
    })
    return frame.assign(**over) if over else frame


def _rolled() -> "pd.DataFrame":
    from gaffer.features.engineer import add_understat_team_rolling

    return add_understat_team_rolling(pd.DataFrame({
        "team_code": [1, 1, 3, 3],
        "date": ["2024-08-10", "2024-08-17", "2024-08-10", "2024-08-17"],
        "us_xga": [0.5, 0.5, 3.0, 3.0],
        "ppda": [8.0, 8.0, 20.0, 20.0],
    }))


def _cups() -> "pd.DataFrame":
    return pd.DataFrame({"team_code": [3],
                         "date": ["2024-08-14T19:45:00Z"]})


def test_a_frame_with_no_club_code_reads_exactly_what_main_read():
    """The degradation direction, both consumers at once. A banked frame
    built before v9c's derivation must produce the pre-v9d answer rather than
    a KeyError or a NaN column."""
    from gaffer.features.engineer import add_congestion, merge_understat_team

    thin = _players().drop(columns=["club_code"])
    assert merge_understat_team(thin, _rolled())["team_us_xga_r5"].iloc[0] == 3.0
    assert add_congestion(thin.head(1), _cups())["matches_last_14d"].iloc[0] == 1.0


def test_an_all_nan_club_code_falls_back_per_row_not_per_frame():
    """``as_of_club`` coalesces row by row. A column-presence check would see
    the column, read NaN for every row and miss the join on all of them —
    which is exactly how ``build_prediction_frame``'s concatenated future rows
    would have been served against a null club."""
    from gaffer.features.engineer import add_congestion, merge_understat_team

    nan_club = _players(club_code=[float("nan"), float("nan")])
    out = merge_understat_team(nan_club, _rolled())
    assert out["team_us_xga_r5"].iloc[0] == 3.0
    assert add_congestion(nan_club.head(1),
                          _cups())["matches_last_14d"].iloc[0] == 1.0


def test_the_understat_merge_leaks_neither_scaffolding_column():
    """``_club`` and ``_date`` both reach ``feature_columns``' strip in
    ``advise.py:548`` as unrecognised names if they survive."""
    from gaffer.features.engineer import merge_understat_team

    out = merge_understat_team(_players(), _rolled())
    assert "_club" not in out.columns and "_date" not in out.columns


def test_the_opponent_side_is_still_keyed_on_opp_code():
    """Untouched by v9d and deliberately: ``opp_code`` is written per row from
    the fixture at ingest and already survives a transfer. Present it and the
    columns populate; drop it and they are all-NaN rather than absent."""
    from gaffer.features.engineer import merge_understat_team

    with_opp = merge_understat_team(_players(opp_code=[1, 1]), _rolled())
    assert with_opp["opp_us_xga_r5"].notna().any()
    without = merge_understat_team(_players().drop(columns=["opp_code"]),
                                   _rolled())
    assert "opp_us_xga_r5" in without.columns
    assert without["opp_us_xga_r5"].isna().all()


def test_congestion_on_a_frame_with_no_team_code_returns_the_league_count():
    """Plan A3's guard. ``as_of_club`` falls back to ``team_code`` and raises
    without it, so the column check above the cup block stays even though the
    line below it no longer reads the column directly."""
    from gaffer.features.engineer import add_congestion

    thin = _players().head(1).drop(columns=["team_code", "club_code"])
    assert add_congestion(thin, _cups())["matches_last_14d"].iloc[0] == 0.0


def test_the_rotation_probe_still_reads_the_stamped_team_code():
    """A source pin, because the file's own comment forbids the switch (plan
    A4): the probe frame is built *without* a ``club_code`` column, so
    ``as_of_club`` would fall back to exactly this — and a later sweep taking
    the switch "for consistency" would add a column the probe cannot derive.
    """
    import gaffer.features.engineer as eng

    source = inspect.getsource(eng.latest_rotation_priors)
    assert 'out["team_code"]' in source


# =====================================================================
# Block 3 — §3a, the identity memo
# =====================================================================

def _identity_files(tmp_path):
    from gaffer.data import store

    (tmp_path / "data" / "live").mkdir(parents=True)
    store.save(pd.DataFrame({"code": [3], "short_name": ["ARS"],
                             "team_id": [1]}), "live/teams.parquet")
    store.save(pd.DataFrame({"code": [7], "team_code": [3]}),
               "live/players.parquet")
    store.save(pd.DataFrame({"gw": [9], "finished": [False], "home_id": [1],
                             "away_id": [1],
                             "kickoff_time": ["2026-01-01T12:00:00Z"]}),
               "live/fixtures_all.parquet")


def test_a_file_that_vanishes_between_calls_does_not_serve_a_stale_map(
        tmp_path, monkeypatch):
    """``_file_key`` returns ``None``, the read is attempted uncached, and the
    reader's own ``except`` returns the empty map. Nothing here raises, which
    is the module's standing contract and not something a cache may change."""
    from gaffer.web import identity

    monkeypatch.chdir(tmp_path)
    identity.clear_cache()
    _identity_files(tmp_path)
    payload = {"xi": [{"code": 7, "name": "Someone"}]}
    assert identity.with_identity(payload, 9)["xi"][0]["team_code"] == 3
    (tmp_path / "data" / "live" / "players.parquet").unlink()
    assert identity.with_identity(payload, 9)["xi"][0]["team_code"] is None
    identity.clear_cache()


def test_a_same_size_rewrite_with_a_new_mtime_misses(tmp_path, monkeypatch):
    """``mtime_ns`` is in the key precisely because a same-size rewrite is the
    common case for these three files — a refreshed snapshot with one club's
    short name changed is exactly the same number of bytes."""
    from gaffer.data import store
    from gaffer.web import identity

    monkeypatch.chdir(tmp_path)
    identity.clear_cache()
    _identity_files(tmp_path)
    payload = {"xi": [{"code": 7, "name": "Someone"}]}
    assert identity.with_identity(payload, 9)["xi"][0]["team_short"] == "ARS"
    store.save(pd.DataFrame({"code": [3], "short_name": ["ARZ"],
                             "team_id": [1]}), "live/teams.parquet")
    assert identity.with_identity(payload, 9)["xi"][0]["team_short"] == "ARZ"
    identity.clear_cache()


def test_clear_cache_exists_and_empties_the_memo():
    from gaffer.web import identity

    identity._CACHE["live/teams.parquet"] = (("x", 1, 1), ({}, {}))
    identity.clear_cache()
    assert identity._CACHE == {}


# =====================================================================
# Block 4 — §3b/§3c, timeouts and the cancel
# =====================================================================

def test_every_job_kind_has_a_deadline_and_none_of_them_is_zero():
    """A zero would make ``start`` reap the holder unconditionally, turning
    the single lane into last-writer-wins."""
    from gaffer.web.job_kinds import (ABANDON_TIMEOUT_S, JOB_KINDS,
                                      SLOW_ABANDON_KINDS)

    assert set(ABANDON_TIMEOUT_S) | SLOW_ABANDON_KINDS == set(JOB_KINDS)
    # Disjoint as well as complete. A kind in both would read as having a
    # deadline while taking the slow default, so the union above would keep
    # passing while the table said one thing and the lookup did another.
    assert not (set(ABANDON_TIMEOUT_S) & SLOW_ABANDON_KINDS)
    assert all(v > 0 for v in ABANDON_TIMEOUT_S.values())


def test_the_cancel_and_the_timeout_say_different_true_things():
    """One helper, two callers, and until v9d one sentence — which meant a
    button the user had just pressed reported "timed out after 0s"."""
    import threading
    import time

    from gaffer.web.job_kinds import ABANDON_TIMEOUT_S
    from gaffer.web.jobs import JobRunner

    release = threading.Event()
    runner = JobRunner({"snapshot": lambda: release.wait(5.0),
                        "evaluate": lambda: None})
    cancelled = runner.start("snapshot")
    error = runner.abandon_current().error
    assert "cancelled" in error and "timed out" not in error
    assert "abandoned as a daemon, its thread still running" in error

    ABANDON_TIMEOUT_S["snapshot"], keep = 0.05, ABANDON_TIMEOUT_S["snapshot"]
    try:
        timed = runner.start("snapshot")
        time.sleep(0.1)
        runner.start("evaluate")
        reaped = runner.get(timed).error
    finally:
        ABANDON_TIMEOUT_S["snapshot"] = keep
        release.set()
    assert "timed out after 0s" in reaped
    assert "abandoned as a daemon, its thread still running" in reaped
    assert runner.get(cancelled) is not None


def test_a_kind_with_no_override_is_reaped_on_the_old_constant():
    """A ``KeyError`` here would 500 every POST /api/jobs/{kind} while a job
    was running."""
    import threading
    import time

    from gaffer.web import jobs as jobs_module
    from gaffer.web.jobs import JobRunner

    release = threading.Event()
    keep = jobs_module.ADVISE_TIMEOUT_S
    jobs_module.ADVISE_TIMEOUT_S = 0.05
    try:
        runner = JobRunner({"unlisted": lambda: release.wait(5.0),
                            "evaluate": lambda: None})
        first = runner.start("unlisted")
        time.sleep(0.1)
        assert runner.start("evaluate")
        assert "timed out" in runner.get(first).error
    finally:
        jobs_module.ADVISE_TIMEOUT_S = keep
        release.set()


# =====================================================================
# Block 5 — §4, calibration's honesty
# =====================================================================

def test_a_calibration_key_does_not_break_the_quality_page(tmp_path,
                                                           monkeypatch):
    """Pydantic ignores extra keys — asserted, because it is the one way the
    new key could break a shipped page."""
    from gaffer.evaluation import save_evaluation

    monkeypatch.chdir(tmp_path)
    save_evaluation("calibration", {"gameweeks": [], "cumulative": {}})
    client = TestClient(create_app())
    assert client.get("/api/quality").status_code == 200


def test_the_calibration_route_is_a_200_with_the_sentence_when_empty(
        tmp_path, monkeypatch):
    """200, not /api/quality's 422: this card renders beside populated ones,
    where a 422 is indistinguishable from a broken endpoint."""
    monkeypatch.chdir(tmp_path)
    body = TestClient(create_app()).get("/api/model/calibration").json()
    assert body["available"] is False
    assert "gaffer evaluate --calibration" in body["note"]


def test_an_insufficient_head_serialises_with_a_null_brier(tmp_path,
                                                           monkeypatch):
    """``None`` is JSON's null and survives the round trip; NaN is not JSON at
    all and ``save_evaluation`` refuses it."""
    from gaffer.evaluation import MIN_CALIBRATION_SAMPLES, calibration_head

    monkeypatch.chdir(tmp_path)
    head = calibration_head([0.5] * (MIN_CALIBRATION_SAMPLES - 1),
                            [1.0] * (MIN_CALIBRATION_SAMPLES - 1))
    assert head["brier"] is None and head["reliability"] == []
    import json

    assert json.dumps(head, allow_nan=False)


def test_a_components_file_written_after_the_whistle_is_not_graded(
        tmp_path, monkeypatch):
    """The file's second-most valuable assertion. Without the guard the report
    is a plausible-looking grade of hindsight: ``save_components`` writes
    ``gw{N}`` whatever today's date is, so re-running advise on a finished
    gameweek replaces an as-of prediction with one that has seen the result.
    """
    import os

    from gaffer.artifacts import components_path, save_components
    from gaffer.data import store
    from gaffer.evaluation import evaluate_calibration

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    n = 40
    save_components(pd.DataFrame({
        "code": list(range(n)), "gw": [1] * n, "team_code": [1] * n,
        "opp_code": [2] * n,
        "p_play": [0.8] * n, "p60": [0.6] * n, "p_cs": [0.3] * n,
        "e_goals": [0.4] * n, "e_assists": [0.2] * n}), 1)
    store.save(pd.DataFrame({
        "season": ["2025-26"] * n, "gw": [1] * n, "code": list(range(n)),
        "team_code": [1] * n, "opp_code": [2] * n, "minutes": [90] * n,
        "goals": [0] * n, "assists": [0] * n, "cs": [1] * n,
        "gc": [0] * n}), "live/player_gw.parquet")
    store.save(pd.DataFrame({"gw": [1], "finished": [True], "home_id": [1],
                             "away_id": [2],
                             "kickoff_time": ["2025-08-16T14:00:00Z"]}),
               "live/fixtures_all.parquet")
    late = pd.Timestamp("2025-08-20T00:00:00Z").timestamp()
    os.utime(components_path(1), (late, late))

    out = evaluate_calibration(season="2025-26")
    assert out["gameweeks"] == []
    assert {"gw": 1,
            "reason": "artifact written after the gameweek's first kickoff"
            } in out["excluded"]


# =====================================================================
# Block 6 — the counts
# =====================================================================

def test_the_job_kinds_are_still_twelve():
    """Spec §0: no new job kinds. The calibration report is a CLI mode and a
    GET, not a thirteenth thing to run — and it could not be a job anyway,
    because JOB_KINDS maps a kind to a zero-argument callable and there is no
    way to pass it a flag."""
    from gaffer.web.job_kinds import JOB_KINDS

    assert len(JOB_KINDS) == 12


def test_the_config_gained_no_field():
    """Spec §0: no new config keys. ABANDON_TIMEOUT_S is an engineering
    deadline on a local single-lane runner, not something a user tunes.

    v12 W1 §2.6/§2.8 (specs/2026-09-01-gaffer-v12-program-design.md): this
    asserted an absolute count of 48, in one of seven protected files that
    did — the same shape v10b hit with routes and v11 retired. It becomes the
    claim this cycle is entitled to make about its own constant, and the total
    lives in ``tests/test_v12_w1_degradation.py`` alone.
    """
    import dataclasses

    from gaffer.config import Config

    names = {f.name for f in dataclasses.fields(Config)}
    # `advise_timeout` / `abandon` rather than a bare "timeout": the tree
    # already has `news_llm_timeout_s`, which is an HTTP deadline on one news
    # source (v8a) and not this claim's subject. Naming the two constants
    # keeps the exception visible instead of quietly widening the pattern.
    assert not [n for n in names
                if "advise_timeout" in n or "abandon" in n]


def test_this_cycle_added_exactly_the_calibration_get(tmp_path, monkeypatch):
    """43 at the branch point (2802165), 44 after v9d, and the one was the
    calibration GET.

    This file no longer pins the absolute total. It pinned 43, then 44, then 45
    under v10b's orchestrator authorization — a toll every route addition
    charged to three protected files at once — and v11 moved that single
    absolute pin to ``tests/test_v11_degradation.py``. What survives here is
    the claim v9d is entitled to make about its own cycle, by name, which is
    what the assertion below has always been."""
    monkeypatch.chdir(tmp_path)
    paths = set(create_app().openapi()["paths"])
    assert {p for p in paths if p.startswith("/api/model")} == {
        "/api/model/calibration"}
