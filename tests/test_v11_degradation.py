"""v11's rails: what each of the three views says when it has nothing to say.

Every state below is one a real machine reaches, and — this cycle in
particular — several of them are the state *this* machine is in today. The
ledger holds one row, its four lanes are ungraded, it has no accuracy and no
rank, so §F3's honesty rules fire on the real data on day one rather than in a
corner case somebody has to imagine.

Three null conventions are in play and they are not interchangeable:
``field_eo``'s "never 0.0 for unknown", ``p_play``'s "0.0 reads as
expected-not-to-play", and the graded counter's "never measured is not never
wrong". Each new field this cycle added inherits one of them by name.
"""

from __future__ import annotations

import pathlib
import re

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import (COMPONENT_COLS, SolveState, load_solve_state,
                              save_components, save_solve_state)
from gaffer.data import store
from gaffer.data.field import FIELD_EO_COLS, append_field_eo, field_eo_rows
from gaffer.review import season_summary
from gaffer.web.app import create_app
from gaffer.web.routers import plan as plan_router
from gaffer.web.schemas import Review, ReviewGw

from tests.test_web_league_sim import _artifacts

# --- Block 1: §F1's honesty — the bank, and what breaks it ----------------

POOL = pd.DataFrame({"code": [100, 200], "name": ["In", "Out"],
                     "cost": [80.0, 75.0], "sell": [78.0, 74.0]})


def _week(gw, buys=(), sells=(), hits=0):
    return {"gw": gw, "hits": hits, "expected_pts": 60.0,
            "buys": [dict(b) for b in buys], "sells": [dict(s) for s in sells]}


@pytest.fixture()
def planned(monkeypatch):
    def install(weeks, bank=15):
        monkeypatch.setattr(plan_router, "load_advice", lambda gw: {
            "gw": 5, "deadline": "2026-09-18T17:30:00Z", "chip_table": [],
            "captain": None, "vice": None, "plan_by_gw": weeks})
        state = SolveState(gw=5, gws=[5, 6, 7],
                           deadline="2026-09-18T17:30:00Z",
                           generated_at="2026-09-01T09:00:00+00:00",
                           mode="weekly", bank=bank, free_transfers=1,
                           owned_codes=[200], lam=0.0, league_eo={},
                           avail_by_gw={}, opt={"hit_cost": 4}, pool=POOL)
        monkeypatch.setattr(plan_router, "load_solve_state", lambda gw: state)
    return install


def test_a_fully_priced_plan_reports_a_bank_every_week(planned):
    planned([_week(5, sells=[{"code": 200, "name": "Out"}]),
             _week(6, buys=[{"code": 100, "name": "In"}])])
    assert [w.bank for w in plan_router.plan(5).weeks] == [8.9, 0.9]


def test_one_unpriced_move_blanks_that_week_and_every_later_one(planned):
    """The rail this whole workstream exists for. Skipping the move would
    report a bank wrong by exactly that player's price, confidently, with
    nothing on the page to say so — and there is no later week at which the
    running sum comes right again."""
    planned([_week(5), _week(6, buys=[{"code": 999, "name": "Ghost"}]),
             _week(7)])
    out = plan_router.plan(5)
    assert out.bank == 1.5                     # the week-zero fact survives
    assert [w.bank for w in out.weeks] == [1.5, None, None]


def test_a_solve_state_with_no_usable_bank_is_never_zero(planned):
    """0.0 is "fully invested", which is a real state a manager can be in and
    a different one from "we do not know"."""
    planned([_week(5)], bank=None)
    out = plan_router.plan(5)
    assert out.bank is None
    assert out.weeks[0].bank is None


def test_every_pre_existing_plan_field_is_untouched(planned):
    """The timeline is a shipped view and ``bank`` is the only thing that
    moved on its payload."""
    planned([_week(5, buys=[{"code": 100, "name": "In", "position": "MID",
                             "ep": 6.1}],
                   sells=[{"code": 200, "name": "Out", "position": "FWD",
                           "ep": 2.0}], hits=1)])
    week = plan_router.plan(5).weeks[0]
    assert (week.gw, week.hits, week.hit_cost) == (5, 1, 4)
    assert week.expected_pts == 60.0
    assert week.chip is None
    assert (week.buys[0].price, week.sells[0].price) == (8.0, 7.4)


# --- Block 2: §F2's honesty — the error bar, absent and never zero --------


@pytest.fixture()
def players_rows(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    _artifacts(tmp_path)
    pd.DataFrame([{"team_id": 1, "code": 300, "name": "LIV"},
                  {"team_id": 2, "code": 301, "name": "ARS"},
                  {"team_id": 3, "code": 302, "name": "MCI"}]).to_parquet(
        tmp_path / "data/live/teams.parquet", index=False)
    state = load_solve_state(3)
    state.pool = pd.concat([
        state.pool,
        pd.DataFrame([{**state.pool.iloc[0].to_dict(), "code": 101,
                       "name": "Dud", "position": "DEF", "team_code": 301,
                       "cost": 45, "sell": 45, "owned": False,
                       "ep_raw": 3.0}])], ignore_index=True)
    save_solve_state(state)
    client = TestClient(create_app())
    return lambda: client.get("/api/players").json()


def test_no_field_log_leaves_all_three_null_and_none_of_them_zero(
        players_rows):
    rows = players_rows()
    assert rows
    for row in rows:
        assert (row["field_eo"], row["field_se"], row["field_n"]) \
            == (None, None, None)


def test_a_log_carrying_a_player_serves_all_three(players_rows):
    append_field_eo(field_eo_rows({7: {"eo": 62.4, "se": 2.8, "n": 300}},
                                  2, "2026-27", day="2026-08-31"))
    row = next(r for r in players_rows() if r["element"] == 7)
    assert (row["field_eo"], row["field_se"], row["field_n"]) \
        == (62.4, 2.8, 300)


def test_an_older_log_with_no_error_serves_the_eo_and_no_error(players_rows):
    """The case that would tempt a 0.0. ``FIELD_EO_COLS`` is fixed, so a
    scrape that never computed an error writes a NaN rather than dropping the
    column, and a NaN must reach the wire as null."""
    append_field_eo(field_eo_rows(
        {7: {"eo": 62.4, "se": float("nan"), "n": 300}},
        2, "2026-27", day="2026-08-31"))
    row = next(r for r in players_rows() if r["element"] == 7)
    assert row["field_eo"] == 62.4
    assert row["field_se"] is None


def test_the_field_eo_columns_are_the_ones_the_log_carries():
    """``se`` and ``n`` were in ``latest_field_eo``'s return all along; the
    row is what dropped them."""
    assert FIELD_EO_COLS == ["season", "gw", "snap_date", "element", "eo",
                             "se", "n"]


# --- Block 2b: §F2's other absent-not-zero — the minutes pair -------------
#
# ``p_play``'s convention, applied to the probability beside it. A frame
# banked without a minutes model carries a NaN in ``p60`` (``COMPONENT_COLS``
# is fixed, so the column is written and left empty rather than dropped), and
# 0.0 there reads as "he will not see the hour out" — a claim about a player
# the frame never made.


def _component_row(**over) -> dict:
    row = {c: 0.0 for c in COMPONENT_COLS}
    row.update({"code": 100, "element": 100, "name": "Salah",
                "position": "MID", "team_code": 14, "team_name": "Liverpool",
                "gw": 5, "opp_code": 3, "opp_name": "ARS", "was_home": 1.0,
                "kickoff_time": "2026-09-05T14:00:00Z",
                "p_play": 0.96, "p60": 0.9, "ep_minutes": 1.9, "ep": 6.4})
    row.update(over)
    return row


@pytest.fixture()
def components(tmp_path, monkeypatch):
    client = TestClient(create_app())

    def install(rows):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir(exist_ok=True)
        save_components(pd.DataFrame(rows)[COMPONENT_COLS], 5)
        body = client.get("/api/components/5")
        assert body.status_code == 200
        return body.json()["players"][0]["fixtures"]
    return install


def test_a_nan_p60_serves_null_and_never_zero(components):
    """The rail ``p_play`` already had. 0.0 on this field is "expected off
    before the hour", which is a real forecast and not the absence of one."""
    fixture = components([_component_row(p_play=float("nan"),
                                         p60=float("nan"))])[0]
    assert fixture["minutes"]["p60"] is None
    assert fixture["minutes"]["p_play"] is None
    assert fixture["minutes"]["xmins"] is None


def test_a_modelled_p60_is_still_a_number(components):
    """The degradation must not swallow the ordinary case."""
    fixture = components([_component_row()])[0]
    assert fixture["minutes"]["p60"] == 0.9
    assert fixture["minutes"]["p_play"] == 0.96


# --- Block 3: §F3's honesty, on today's actual ledger shape ---------------

TODAY = [{"gw": 1,
          "lanes": [{"lane": name, "delta_pts": None, "delta_pwin": None,
                     "label": None} for name in
                    ("transfers", "captaincy", "bench", "chip")],
          "accuracy": None, "points_on_bench": 2}]
"""``reports/decision_ledger.json``, measured rather than imagined: one row,
four ungraded lanes, no accuracy, two points on the bench."""


def test_todays_ledger_grades_nothing_and_says_so():
    out = season_summary(TODAY)
    for name in ("transfers", "captaincy", "bench", "chip"):
        cell = out["lanes"][name]
        assert (cell["graded"], cell["wins"], cell["losses"]) == (0, 0, 0)
    assert out["accuracy"] == []
    assert out["points_on_bench"] == 2
    assert out["points_on_bench_gws"] == 1


@pytest.mark.parametrize("deltas,expected", [
    ([4.0, -1.0, 0.0, None], (3, 1, 1)),
    ([0.0, 0.0], (2, 0, 0)),
    ([None, None], (0, 0, 0)),
    ([2.0, 3.0], (2, 2, 0)),
])
def test_the_record_never_exceeds_the_graded_count(deltas, expected):
    rows = [{"gw": i + 1,
             "lanes": [{"lane": "transfers", "delta_pts": d,
                        "delta_pwin": 0.0, "label": None}]}
            for i, d in enumerate(deltas)]
    cell = season_summary(rows)["lanes"]["transfers"]
    assert (cell["graded"], cell["wins"], cell["losses"]) == expected
    assert cell["wins"] + cell["losses"] <= cell["graded"]


def test_a_zero_delta_counts_as_graded_and_as_neither():
    """A week I did what the model did. Counting agreement as judgment is how
    a lane that never disagreed comes to look like a lane that was never
    wrong."""
    cell = season_summary([{"gw": 1, "lanes": [
        {"lane": "bench", "delta_pts": 0.0, "delta_pwin": 0.0,
         "label": "Aligned"}]}])["lanes"]["bench"]
    assert cell["graded"] == 1
    assert (cell["wins"], cell["losses"]) == (0, 0)


def test_a_ledger_row_with_no_rank_still_validates():
    """Every row on disk, forever: grades are banked and never re-derived, so
    a gameweek graded before v11 has no rank and will never acquire one."""
    row = ReviewGw(**{"gw": 1, "lanes": [], "points_on_bench": 2})
    assert row.overall_rank is None
    assert Review(gws=[row], summary=None).gws[0].overall_rank is None


def test_the_review_endpoint_still_answers_on_a_clone_with_no_ledger(
        tmp_path, monkeypatch):
    """``GET /api/review``'s never-errors contract is the one thing §F3 could
    most easily have broken."""
    monkeypatch.chdir(tmp_path)
    body = TestClient(create_app()).get("/api/review")
    assert body.status_code == 200
    assert body.json() == {"gws": [], "summary": None}


# --- Block 4: the counts --------------------------------------------------


def test_the_job_kinds_are_still_twelve():
    """Spec §0. The Tuesday review job already exists (job_kinds.py:200) and
    this cycle adds no thirteenth — which would also need a row in
    ABANDON_TIMEOUT_S or SLOW_ABANDON_KINDS, pinned as jointly exhaustive in
    the protected test_v9d_degradation.py."""
    from gaffer.web.job_kinds import JOB_KINDS

    assert len(JOB_KINDS) == 12


def test_the_config_gained_no_field():
    """Spec §0: nothing in a UI cycle is a knob."""
    import dataclasses

    from gaffer.config import Config

    assert len(dataclasses.fields(Config)) == 48


def test_the_route_total_did_not_move_and_this_is_where_it_is_pinned(
        tmp_path, monkeypatch):
    """45 at the branch point (3404fc3) and 45 now: every serve-side change
    this cycle made is an additive field on a model that already existed.

    **This is the only absolute route pin in the suite.** Task 11 replaced the
    four that used to exist — three of them in protected files — with the
    by-name claim each cycle is entitled to make about its own routes. A
    future cycle that adds a route moves this number, here, and nowhere else.

    Pinned as a total *and* by absence: a count alone would let a route be
    added and another removed in one cycle, and this cycle's claim is
    precisely that it added none.
    """
    monkeypatch.chdir(tmp_path)
    paths = set(create_app().openapi()["paths"])
    assert len(paths) == 45
    assert not [p for p in paths
                if p.startswith(("/api/board", "/api/season",
                                 "/api/compare"))]


# --- Block 5: the cold clone, condition by condition ----------------------
#
# Spec §Gates names the four individually and they fail in different places,
# so they are asserted individually rather than through one "empty tree"
# fixture. Each view's *client-side* empty state is tested in its own frontend
# file, because the hub-level cold-clone rail renders only each hub's default
# tab.


@pytest.fixture()
def cold(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return TestClient(create_app())


def test_no_advice_makes_the_plan_a_404_that_names_the_command(cold):
    body = cold.get("/api/plan/5")
    assert body.status_code == 404
    assert "advise" in body.json()["detail"]


def test_no_advice_leaves_the_latest_endpoint_where_it_was(cold):
    assert cold.get("/api/advice/latest").status_code in (404, 422)


def test_no_calibration_report_is_a_200_carrying_the_servers_own_note(cold):
    body = cold.get("/api/model/calibration")
    assert body.status_code == 200
    assert body.json()["available"] is False
    assert body.json()["note"]


# --- Block 6: the restructure held ---------------------------------------


def test_only_one_file_pins_the_absolute_route_count():
    """The residual v10b recorded, closed and then defended. Four files used
    to pin this number; a fifth would have cost the next cycle another
    orchestrator authorization for a route it was entitled to add."""
    hits = [p.name for p in pathlib.Path("tests").glob("test_*.py")
            if re.search(r"len\((?:paths|create_app\(\)\.openapi\(\)"
                         r"\[[\"']paths[\"']\])\)\s*==\s*\d+",
                         p.read_text())]
    assert hits == ["test_v11_degradation.py"]
