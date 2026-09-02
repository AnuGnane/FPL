"""v12 W2's degradation contract: four ways for each reader to have nothing.

Missing file, malformed file, empty result, partial result — each a named
behaviour and none of them a crash (spec §1). Plus the three claims W2 makes
about the shape of the tree, stated as absence rather than as counts: the
route-pin restructure (v11 §0) put the absolute totals in one file and this is
not that file.
"""

from __future__ import annotations

import dataclasses

import pandas as pd

from gaffer import availability_eval as ae
from gaffer.config import Config


def _events():
    return pd.DataFrame({"gw": [3],
                         "deadline_time": ["2026-09-04T17:30:00Z"]})


# --- missing -------------------------------------------------------------

def test_no_availability_log_at_all_is_a_refusal(monkeypatch):
    monkeypatch.setattr(ae, "load_snapshot_log", lambda: pd.DataFrame())
    monkeypatch.setattr(ae, "news_actuals", lambda: pd.DataFrame())
    monkeypatch.setattr(ae, "load_events", _events)
    monkeypatch.setattr(ae, "load_config",
                        lambda: Config(entry_id=1, league_id=2))
    for payload in (ae.evaluate_flag_latency(), ae.evaluate_presser_grades()):
        assert payload["available"] is False
        assert payload["rows"] == 0
        assert payload["note"]


def test_no_events_snapshot_means_no_deadlines_and_no_report():
    """Without a deadline there is no such thing as a lead time, and the
    report says so rather than measuring from an assumed Friday."""
    log = pd.DataFrame({"season": ["2026-27"], "gw": [3],
                        "snap_date": ["2026-09-01"], "code": [1],
                        "status": ["a"], "llm_verdict": ["ruled_out"],
                        "source": ["premierinjuries"]})
    actuals = pd.DataFrame({"gw": [3], "code": [1], "minutes": [0],
                            "starts": [0]})
    empty = pd.DataFrame(columns=["gw", "deadline_time"])
    assert ae.score_flag_latency(log, actuals, empty,
                                 season="2026-27")["rows"] == 0
    assert ae.score_presser_grades(log, actuals, empty,
                                   season="2026-27")["rows"] == 0


# --- malformed -----------------------------------------------------------

def test_a_log_missing_the_status_column_is_a_refusal():
    log = pd.DataFrame({"season": ["2026-27"], "gw": [3],
                        "snap_date": ["2026-09-01"], "code": [1]})
    out = ae.score_flag_latency(log, pd.DataFrame(), _events(),
                                season="2026-27")
    assert out["available"] is False


def test_every_structural_column_is_guarded_and_none_of_them_raise():
    """The four guards, pinned together. Each reader needs the two keys that
    date a row plus the one column it scores, and ``deadlines`` needs both of
    its own; a frame handed in without one used to reach ``pre_deadline`` and
    raise a KeyError inside a page render rather than degrade.
    """
    full = pd.DataFrame({"season": ["2026-27"], "gw": [3],
                         "snap_date": ["2026-09-01"], "code": [1],
                         "status": ["a"], "llm_verdict": ["ruled_out"],
                         "source": ["premierinjuries"]})
    actuals = pd.DataFrame({"gw": [3], "code": [1], "minutes": [0],
                            "starts": [0]})
    for col in ("gw", "snap_date", "status"):
        out = ae.score_flag_latency(full.drop(columns=[col]), actuals,
                                    _events(), season="2026-27")
        assert out["available"] is False and out["rows"] == 0, col
    for col in ("gw", "snap_date", "llm_verdict"):
        out = ae.score_presser_grades(full.drop(columns=[col]), actuals,
                                      _events(), season="2026-27")
        assert out["available"] is False and out["rows"] == 0, col
    for col in ("gw", "deadline_time"):
        assert ae.deadlines(_events().drop(columns=[col])) == {}
    assert ae.pre_deadline(full.drop(columns=["snap_date"]), {3: None}).empty


def test_unparseable_gameweeks_and_dates_are_dropped_not_defaulted():
    log = pd.DataFrame({
        "season": ["2026-27"] * 2, "gw": ["three", 3],
        "snap_date": ["not-a-date", "2026-09-01"], "code": [1, 1],
        "status": ["a", "a"]})
    kept = ae.pre_deadline(log, ae.deadlines(_events()))
    assert len(kept) == 1


def test_a_deadline_that_will_not_parse_takes_its_gameweek_with_it():
    events = pd.DataFrame({"gw": [3], "deadline_time": ["never"]})
    assert ae.deadlines(events) == {}


# --- empty ---------------------------------------------------------------

def test_a_log_with_verdicts_but_no_results_waits():
    log = pd.DataFrame({"season": ["2026-27"], "gw": [3],
                        "snap_date": ["2026-09-01"], "code": [1],
                        "status": ["d"], "llm_verdict": ["assess"],
                        "source": ["premierinjuries"]})
    out = ae.score_presser_grades(log, pd.DataFrame(columns=["gw", "code",
                                                             "minutes"]),
                                  _events(), season="2026-27")
    assert out["available"] is False
    assert out["verdicts_banked"] == 1


def test_a_shut_gate_serves_no_tables_at_all():
    """The gate decides whether the report is computed, not how it is
    labelled. Under it there is nothing for a caller that forgets to read
    ``available`` to draw — only the two numbers saying how far off it is."""
    dates = ["2026-09-01", "2026-09-02"]
    log = pd.DataFrame([{"season": "2026-27", "gw": 3, "snap_date": d,
                         "code": 1, "status": "a" if i == 0 else "i"}
                        for i, d in enumerate(dates)])
    actuals = pd.DataFrame({"gw": [3], "code": [1], "minutes": [0],
                            "starts": [0]})
    out = ae.score_flag_latency(log, actuals, _events(), season="2026-27")
    assert out["available"] is False
    assert out["rows"] == 0
    assert out["histogram"] == []
    assert out["late_flags"] == []
    assert out["changes"] == []
    assert out["snap_dates"] == 2
    assert out["min_snap_dates"] == ae.MIN_SNAP_DATES


def test_a_season_with_no_rows_scores_nothing_rather_than_everything():
    """The season guard has no fallback: "whatever is newest" is the failure
    it exists to prevent (field.py:233-234's rule, applied here)."""
    log = pd.DataFrame({"season": ["2025-26"], "gw": [3],
                        "snap_date": ["2026-09-01"], "code": [1],
                        "status": ["a"], "llm_verdict": ["assess"],
                        "source": ["premierinjuries"]})
    actuals = pd.DataFrame({"gw": [3], "code": [1], "minutes": [0],
                            "starts": [0]})
    assert ae.score_flag_latency(log, actuals, _events(),
                                 season="2026-27")["rows"] == 0
    assert ae.score_presser_grades(log, actuals, _events(),
                                   season="2026-27")["rows"] == 0


# --- partial -------------------------------------------------------------

def test_a_player_with_no_result_row_is_skipped_and_the_rest_score():
    dates = [f"2026-08-{d:02d}" for d in range(18, 32)] + ["2026-09-01"]
    rows = []
    for code in (1, 2):
        for i, day in enumerate(dates):
            rows.append({"season": "2026-27", "gw": 3, "snap_date": day,
                         "code": code, "status": "a" if i == 0 else "i",
                         "chance_of_playing": None, "llm_verdict": None,
                         "source": None})
    actuals = pd.DataFrame({"gw": [3], "code": [1], "minutes": [0],
                            "starts": [0]})
    out = ae.score_flag_latency(pd.DataFrame(rows), actuals, _events(),
                                season="2026-27")
    assert out["rows"] == 1
    assert [c["code"] for c in out["changes"]] == [1]


def test_a_missing_config_scores_the_empty_season_rather_than_raising(
        monkeypatch):
    def boom():
        raise RuntimeError("no config.toml on this machine")

    monkeypatch.setattr(ae, "load_config", boom)
    monkeypatch.setattr(ae, "load_snapshot_log", lambda: pd.DataFrame())
    monkeypatch.setattr(ae, "news_actuals", lambda: pd.DataFrame())
    monkeypatch.setattr(ae, "load_events", _events)
    assert ae.evaluate_flag_latency()["available"] is False


# --- the shape claims ----------------------------------------------------

def test_w2_adds_no_config_field():
    """Both W2 keys are module-level readers (config.py:221's precedent):
    another field moves a count four protected degradation files pin, and W1
    §2.6 has already spent that once on ``top_n``.

    ``top_n`` is asserted *present* on purpose. It is W1's field, it is
    splatted out of the same ``[optimizer]`` section W2's flag hides in, and
    the pop list is one careless line away from swallowing it."""
    names = {f.name for f in dataclasses.fields(Config)}
    assert "price_timing" not in names
    assert "xg_per_shot" not in names
    assert "top_n" in names


def test_w2_adds_no_job_kind():
    """JOB_KINDS maps a kind to a zero-argument callable, so a report that is
    a CLI flag cannot be a job (evaluation.py:562-566's story)."""
    from gaffer.web.job_kinds import JOB_KINDS

    assert not [k for k in JOB_KINDS
                if "latency" in k or "presser" in k or "trend" in k]


def test_w2_adds_no_route(monkeypatch, tmp_path):
    # ``monkeypatch.chdir`` rather than a bare ``os.chdir``: the app is built
    # on a tree with no config.toml, which is the point, but a working
    # directory this test never gives back is inherited by every test that
    # runs after it — fifteen of them, measured, all of them about files.
    # This is what test_v11_degradation.py already does.
    monkeypatch.chdir(tmp_path)
    from gaffer.web.app import create_app

    paths = set(create_app().openapi()["paths"])
    assert "/api/quality" in paths
    assert not [p for p in paths
                if "latency" in p or "presser" in p or "trend" in p]


# v12 W3 (orchestrator ruling 2026-09-02): the W2 rail audits W2's range, not
# "since main"
W1_MERGE = "ef8c5f3"
W2_TIP = "754e1d1"


def test_the_only_protected_file_w2_touched_is_milp():
    """The audit, as a test rather than as a step somebody remembers.

    Spec §3.4 authorizes one term in optimize/milp.py and nothing else in W2
    touches a protected path.

    The range is W2's own — ``ef8c5f3..754e1d1``, W1's merge to the last
    commit of W2 — and not ``merge-base(HEAD, main)..HEAD``. The claim is
    about what W2 did; scoped to "everything since main" the rail would fail
    on the first authorized protected commit of every later workstream, which
    is a rail reporting somebody else's diff under W2's name. If either commit
    is unreachable — a shallow clone, an export — the audit is skipped rather
    than answered from a range that does not exist.
    """
    import subprocess

    for sha in (W1_MERGE, W2_TIP):
        if subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"],
                          capture_output=True, check=False).returncode:
            import pytest as _pytest
            _pytest.skip(f"{sha} unreachable — W2's range is not in this tree")
    changed = subprocess.run(
        ["git", "diff", "--name-only", W1_MERGE, W2_TIP], capture_output=True,
        text=True, check=False).stdout.split()
    protected = [
        p for p in changed
        if p in {"src/gaffer/advise.py", "src/gaffer/set_pieces.py",
                 "src/gaffer/web/jobs.py",
                 "src/gaffer/web/routers/whatif.py",
                 "tests/test_advise.py", "tests/test_odds.py",
                 "tests/test_web_jobs.py", "scripts/s2_replay.py"}
        or p.startswith("src/gaffer/optimize/")
        or (p.startswith("tests/test_") and p.endswith("_degradation.py")
            and p != "tests/test_v12_w2_degradation.py")]
    assert protected == ["src/gaffer/optimize/milp.py"]
