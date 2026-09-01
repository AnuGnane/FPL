"""The calibration report grades what the solver actually multiplied by.

``reports/components_gw{N}.parquet`` is written on the weekly run, *before*
the gameweek is played, and carries the probability heads the optimizer used.
This report reads them back and scores them against the week that happened.
Nothing refits — a walk-forward refit would grade a different model from the
one that served, and ``evaluate_current`` already exists for that protocol.

The value of the thing is in its refusals, which is why most of this file is
about them: the omitted head that is never banked, the gameweek whose artifact
post-dates its own first kickoff, the head with too few rows to say anything.
Take those away and what is left is a plausible-looking grade of hindsight.
"""

from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import pytest

from gaffer.artifacts import components_path, save_components
from gaffer.data import store
from gaffer.evaluation import (FIXTURE_KEYS, MIN_CALIBRATION_SAMPLES,
                               _club_clean_sheets, _key, brier,
                               calibration_head, evaluate_calibration,
                               format_report, load_evaluation,
                               save_evaluation)
from gaffer.models.assemble import p_haul

KICKOFF = "2025-08-16T14:00:00Z"
LATER = "2025-08-23T14:00:00Z"


# --- 1-2: the primitives --------------------------------------------

def test_brier_is_a_mean_squared_error_and_never_raises():
    assert brier([1.0, 0.0], [1.0, 0.0]) == 0.0
    assert brier([0.5, 0.5], [1.0, 0.0]) == 0.25
    assert np.isnan(brier([], []))


def test_a_head_above_the_threshold_reports_a_curve():
    n = 40
    head = calibration_head([0.5] * n, [1.0] * 20 + [0.0] * 20)
    assert head["status"] == "scored"
    assert head["n"] == n
    assert head["brier"] == 0.25
    assert head["log_loss"] is not None
    assert head["reliability"]


def test_a_head_below_the_threshold_refuses_in_the_same_shape():
    """Same keys either way, so nothing downstream branches on absence."""
    n = MIN_CALIBRATION_SAMPLES - 1
    head = calibration_head([0.5] * n, [1.0] * n)
    assert head["status"] == "insufficient"
    assert head["n"] == n
    assert head["brier"] is None and head["log_loss"] is None
    assert head["reliability"] == []


# --- fixtures -------------------------------------------------------

def _components(gw: int, n: int = 40) -> pd.DataFrame:
    """A banked components frame: two clubs, ``n`` players, four heads."""
    return pd.DataFrame({
        "code": list(range(n)),
        "gw": [gw] * n,
        "kickoff_time": [KICKOFF] * n,
        "team_code": [1 if i % 2 else 3 for i in range(n)],
        "opp_code": [3 if i % 2 else 1 for i in range(n)],
        "p_play": [0.8] * n,
        "p60": [0.6] * n,
        "p_cs": [0.3] * n,
        "e_goals": [0.4] * n,
        "e_assists": [0.2] * n,
    })


def _truth(gw: int, n: int = 40) -> pd.DataFrame:
    return pd.DataFrame({
        "season": ["2025-26"] * n,
        "gw": [gw] * n,
        "kickoff_time": [KICKOFF] * n,
        "code": list(range(n)),
        "team_code": [1 if i % 2 else 3 for i in range(n)],
        "opp_code": [3 if i % 2 else 1 for i in range(n)],
        "minutes": [90 if i % 3 else 0 for i in range(n)],
        "starts": [1 if i % 3 else 0 for i in range(n)],
        "goals": [1 if i % 5 == 0 else 0 for i in range(n)],
        "assists": [1 if i % 5 == 0 else 0 for i in range(n)],
        # Club 1 (odd rows) kept a clean sheet; club 3 conceded one. ``cs`` is
        # the per-player award, ``gc`` the club's result seen from the pitch.
        "cs": [1 if i % 2 else 0 for i in range(n)],
        "gc": [0 if i % 2 else 1 for i in range(n)],
    })


def _fixtures(gws: list[int], kickoff: str = KICKOFF) -> pd.DataFrame:
    return pd.DataFrame({"gw": gws, "finished": [True] * len(gws),
                         "home_id": [1] * len(gws), "away_id": [2] * len(gws),
                         "kickoff_time": [kickoff] * len(gws)})


def _before_kickoff(gw: int, kickoff: str = KICKOFF) -> None:
    """Backdate the artifact so the post-hoc guard lets it through."""
    when = pd.Timestamp(kickoff).timestamp() - 86400
    os.utime(components_path(gw), (when, when))


@pytest.fixture()
def banked(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    save_components(_components(1), 1)
    _before_kickoff(1)
    store.save(_truth(1), "live/player_gw.parquet")
    store.save(_fixtures([1]), "live/fixtures_all.parquet")
    return tmp_path


# --- 3-6: what a graded gameweek says -------------------------------

def test_a_banked_gameweek_is_graded(banked):
    out = evaluate_calibration(season="2025-26")
    assert [row["gw"] for row in out["gameweeks"]] == [1]
    row = out["gameweeks"][0]
    # p_play's outcome is minutes > 0: 26 of 40 rows played.
    played = int((_truth(1)["minutes"] > 0).sum())
    assert row["heads"]["p_play"]["brier"] == round(
        float(((0.8 - (_truth(1)["minutes"] > 0).astype(float)) ** 2).mean()), 4)
    assert row["heads"]["p60"]["n"] == 40
    assert played == 26
    assert out["cumulative"]["p_play"]["brier"] == row["heads"]["p_play"]["brier"]


def test_p_haul_is_recomputed_from_the_banked_components(banked):
    """Reproduced through the same function assemble_ep called at solve time,
    not approximated from a column that does not exist."""
    out = evaluate_calibration(season="2025-26")
    expected = p_haul(0.4, 0.2)
    truth = (_truth(1)["goals"] + _truth(1)["assists"]) >= 2
    head = out["gameweeks"][0]["heads"]["p_haul"]
    assert head["brier"] == round(
        float(((expected - truth.astype(float)) ** 2).mean()), 4)


def test_p_cs_is_graded_per_club_fixture_and_only_cumulatively(banked):
    """A clean sheet is one event and eleven player rows — and about twenty
    events a gameweek, which is under the sample floor by arithmetic rather
    than by luck. A per-gameweek column of it could only ever read "not
    enough data", so it is not offered at that grain; the rows pool into the
    cumulative row instead, and the payload says so where the card can print
    it.
    """
    out = evaluate_calibration(season="2025-26")
    assert "p_cs" not in out["gameweeks"][0]["heads"]
    assert "p_cs" in out["cumulative"]
    assert out["cumulative"]["p_cs"]["n"] == 2   # two clubs, not forty players
    assert "cumulative row" in out["per_gw_omitted"]["p_cs"]


def _clubs(n: int = 30) -> tuple[pd.DataFrame, pd.DataFrame]:
    """``n`` club-fixtures, half of them clean sheets, three players each.

    Every club's first row is a player who did not get on the pitch, so his
    ``cs`` is 0 whatever the club did. ``p_cs`` is a perfect predictor of the
    club's actual result — 1.0 where the club kept one, 0.0 where it did not —
    so a correct scorer reports a Brier of exactly zero and any scorer that
    reads the outcome off one player's row does not.
    """
    comp, truth = [], []
    for i in range(n):
        kept = i % 2 == 0
        team, opp = i + 1, 100 + i
        for j, minutes in enumerate((0, 90, 90)):
            code = i * 10 + j
            comp.append({"code": code, "gw": 1, "team_code": team,
                         "kickoff_time": KICKOFF,
                         "opp_code": opp, "p_play": 0.8, "p60": 0.6,
                         "p_cs": 1.0 if kept else 0.0,
                         "e_goals": 0.4, "e_assists": 0.2})
            truth.append({"season": "2025-26", "gw": 1, "code": code,
                          "kickoff_time": KICKOFF,
                          "team_code": team, "opp_code": opp,
                          "minutes": minutes, "starts": int(minutes > 0),
                          "goals": 0, "assists": 0,
                          # The FPL award: 60+ minutes and none conceded.
                          "cs": int(kept and minutes >= 60),
                          "gc": 0 if kept else 2})
    return pd.DataFrame(comp), pd.DataFrame(truth)


@pytest.mark.parametrize("reverse", [False, True])
def test_p_cs_reads_the_clubs_result_not_one_players_row(banked, reverse):
    """FPL's per-player ``clean_sheets`` is an award, not a team result.

    It is 0 for everyone under 60 minutes even when the club conceded nothing,
    so taking one arbitrary row's value makes row order the answer — which is
    why this runs the identical data twice, once reversed. The club's result
    is goals conceded among its 60-minute rows, which is ``models.team``'s
    ``ga == 0`` seen from the pitch.
    """
    comp, truth = _clubs()
    if reverse:
        comp = comp.iloc[::-1].reset_index(drop=True)
        truth = truth.iloc[::-1].reset_index(drop=True)
    save_components(comp, 1)
    _before_kickoff(1)
    store.save(truth, "live/player_gw.parquet")

    head = evaluate_calibration(season="2025-26")["cumulative"]["p_cs"]
    assert head["n"] == 30            # one row per club-fixture
    assert head["brier"] == 0.0       # p_cs was right about every one of them


def _dgw(n: int = 40) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One club, ``n`` players, two legs each — and nothing crosses on a leg.

    Every player plays 45 minutes in each leg and scores once in each leg. No
    single fixture is a 60-minute appearance and no single fixture is a haul;
    the gameweek totals (90 minutes, two returns) are both.
    """
    codes = list(range(n))
    comp = pd.DataFrame({
        "code": codes * 2, "gw": [1] * (2 * n), "team_code": [1] * (2 * n),
        "opp_code": [2] * n + [4] * n,
        "kickoff_time": [KICKOFF] * n + [LATER] * n,
        "p_play": [0.8] * (2 * n), "p60": [0.6] * (2 * n),
        "p_cs": [0.3] * (2 * n),
        "e_goals": [0.4] * (2 * n), "e_assists": [0.2] * (2 * n)})
    truth = pd.DataFrame({
        "season": ["2025-26"] * (2 * n), "gw": [1] * (2 * n),
        "code": codes * 2, "team_code": [1] * (2 * n),
        "opp_code": [2] * n + [4] * n,
        "kickoff_time": [KICKOFF] * n + [LATER] * n,
        "minutes": [45] * (2 * n), "starts": [1] * (2 * n),
        "goals": [1] * (2 * n), "assists": [0] * (2 * n),
        "cs": [0] * (2 * n), "gc": [1] * (2 * n)})
    return comp, truth


def test_a_double_gameweek_is_graded_per_fixture_not_per_gameweek(banked):
    """Predictions are per-fixture; the truth has to be read the same way.

    Aggregating the week and merging on ``code`` alone grades each of the two
    prediction rows against the pair's totals — so a player who never reached
    60 minutes in either leg scores ``p60`` against an observed 1.0, and one
    who returned once in each leg scores ``p_haul`` against an event that
    happened in no fixture at all. Both heads then look badly under-confident
    for a reason entirely the scorer's.
    """
    comp, truth = _dgw()
    save_components(comp, 1)
    _before_kickoff(1)
    store.save(truth, "live/player_gw.parquet")

    out = evaluate_calibration(season="2025-26")
    heads = out["gameweeks"][0]["heads"]
    assert heads["p60"]["n"] == 80          # one row per player-fixture
    # 45 minutes in each leg is not a 60-minute appearance in either.
    assert heads["p60"]["brier"] == round((0.6 - 0.0) ** 2, 4)
    # One return per leg is not a haul in either leg.
    assert heads["p_haul"]["brier"] == round(p_haul(0.4, 0.2) ** 2, 4)


def _same_opponent_twice(n: int = 40) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One club meeting one opponent **twice** in a gameweek, two kickoffs.

    A rearranged league fixture landing beside the scheduled one is the
    ordinary way a double gameweek comes about, and it is the case
    ``(code, opp_code)`` cannot key: every player has two rows carrying the
    same player code and the same opponent code.

    The two legs are made to disagree about everything a collapse would have
    to average away — the club keeps a clean sheet in the first and concedes
    twice in the second, and ``p_cs`` is banked as a perfect predictor of each
    (1.0, then 0.0). Every player plays the full ninety in both.
    """
    codes = list(range(n))
    both = 2 * n
    comp = pd.DataFrame({
        "code": codes * 2, "gw": [1] * both, "team_code": [1] * both,
        "opp_code": [2] * both,
        "kickoff_time": [KICKOFF] * n + [LATER] * n,
        "p_play": [0.8] * both, "p60": [0.6] * both,
        "p_cs": [1.0] * n + [0.0] * n,
        "e_goals": [0.4] * both, "e_assists": [0.2] * both})
    truth = pd.DataFrame({
        "season": ["2025-26"] * both, "gw": [1] * both,
        "code": codes * 2, "team_code": [1] * both,
        "opp_code": [2] * both,
        "kickoff_time": [KICKOFF] * n + [LATER] * n,
        "minutes": [90] * both, "starts": [1] * both,
        "goals": [0] * both, "assists": [0] * both,
        "cs": [1] * n + [0] * n, "gc": [0] * n + [2] * n})
    return comp, truth


def test_the_same_opponent_twice_in_one_gameweek_stays_two_fixtures(banked):
    """``(code, opp_code)`` is not a key, and a repeated opponent proves it.

    Without the kickoff in the join the inner merge is multiplicative: each
    prediction row matches *both* of that player's outcome rows, ``n`` doubles
    to four times the players, and every forecast is graded once against a
    match it was not a forecast of. The clean-sheet head fails a second way in
    the same step — ``_club_clean_sheets`` groups the two legs into one
    club-fixture whose conceded is the worse of the two, so one event is
    reported where two were played and the club that kept a clean sheet is
    recorded as having conceded.

    With the kickoff, both stay two.
    """
    comp, truth = _same_opponent_twice()
    save_components(comp, 1)
    _before_kickoff(1)
    store.save(truth, "live/player_gw.parquet")

    out = evaluate_calibration(season="2025-26")
    row = out["gameweeks"][0]
    assert row["n"] == 80                       # 40 players x 2 legs, not 160
    assert row["heads"]["p60"]["n"] == 80
    cs = out["cumulative"]["p_cs"]
    assert cs["n"] == 2                         # two club-fixtures, not one
    # Two events is under the sample floor, as every real week's p_cs is; the
    # count is the thing being pinned here. What was *in* those two events is
    # pinned directly below, where the floor cannot hide it.
    assert cs["status"] == "insufficient"
    by_club = _club_clean_sheets(
        _key(comp).merge(_key(truth), on=list(FIXTURE_KEYS), how="inner",
                         suffixes=("", "_truth")))
    assert len(by_club) == 2
    # One leg kept, one conceded, and p_cs was banked right about each of
    # them separately. A collapse would report a single row whose conceded is
    # the worse of the two and whose p_cs is the better.
    assert sorted(by_club["clean_sheet"]) == [0.0, 1.0]
    assert sorted(by_club["p_cs"]) == [0.0, 1.0]


def test_duplicate_player_fixture_rows_exclude_the_gameweek(banked):
    """A non-unique key on either side is checked before the merge, not after.

    An inner join on a duplicated key multiplies silently, and the product is
    indistinguishable from a genuinely larger week once it exists — so the
    uniqueness is asserted per side while the sides are still separable. The
    week is excluded with its reason rather than raising: every other
    gameweek in the pass still grades.
    """
    comp, truth = _same_opponent_twice()
    # The same fixture banked twice — same player, same opponent, same instant.
    comp = pd.concat([comp, comp.iloc[[0]]], ignore_index=True)
    save_components(comp, 1)
    _before_kickoff(1)
    store.save(truth, "live/player_gw.parquet")

    out = evaluate_calibration(season="2025-26")
    assert out["gameweeks"] == []
    reasons = [row["reason"] for row in out["excluded"] if row["gw"] == 1]
    assert reasons and "duplicate rows per player-fixture" in reasons[0]
    assert "components" in reasons[0]


def test_an_unparseable_kickoff_drops_its_row_rather_than_crossing_it(banked):
    """``NaT`` does not drop itself out of a merge — pandas matches null keys.

    Which is the guarded-parse lesson read the harder way: ``errors="coerce"``
    makes the *parse* safe and leaves the arithmetic downstream unguarded. A
    handful of unparseable kickoffs on each side would inner-join into exactly
    the cartesian the kickoff was added to prevent, so :func:`_key` drops them
    and the week is graded on the rows that have a real instant.
    """
    comp, truth = _same_opponent_twice()
    comp.loc[[0, 1], "kickoff_time"] = "not a timestamp"
    truth.loc[[0, 1], "kickoff_time"] = "not a timestamp"
    save_components(comp, 1)
    _before_kickoff(1)
    store.save(truth, "live/player_gw.parquet")

    out = evaluate_calibration(season="2025-26")
    # 78, not 80 and emphatically not 82: the two unparseable rows are gone
    # from each side rather than matched against each other.
    assert out["gameweeks"][0]["n"] == 78


def test_components_with_no_club_exclude_the_gameweek(banked):
    """``team_code`` is asked of the components, not of the joined frame.

    The merge keeps the left name and suffixes the collision as ``_truth``, so
    a components file with no ``team_code`` leaves ``joined["team_code"]``
    holding the *truth* side's stamped club. p_cs is a banked club-level
    prediction; grading it against clubs the prediction never named is a
    number with nothing behind it, so the week is excluded and says so.
    """
    comp, truth = _same_opponent_twice()
    comp = comp.drop(columns=["team_code"])
    save_components(comp, 1)
    _before_kickoff(1)
    store.save(truth, "live/player_gw.parquet")

    out = evaluate_calibration(season="2025-26")
    assert out["gameweeks"] == []
    assert [row["reason"] for row in out["excluded"] if row["gw"] == 1] == [
        "components carry no club"]


def test_a_short_appearance_still_counts_towards_the_clubs_goals_conceded(
        banked):
    """The 60-minute rule gates whether a club-fixture is real, not its value.

    FPL counts ``gc`` only while a player is on the pitch, so every row is a
    lower bound on the club's total and none can exceed it: widening the
    maximum to every row can only move it towards the truth. Here the only
    60-minute row is a substitute who came on after both goals — the case the
    old 60-minutes-only maximum got wrong, awarding the club a clean sheet it
    did not keep — while the starter who was withdrawn at 45 saw them both.
    """
    rows_comp, rows_truth = [], []
    for i in range(2):
        for j, (minutes, gc) in enumerate(((45, 2), (60, 0), (90, 2))):
            code = i * 10 + j
            rows_comp.append({"code": code, "gw": 1, "team_code": i + 1,
                              "opp_code": 90 + i, "kickoff_time": KICKOFF,
                              "p_play": 0.8, "p60": 0.6, "p_cs": 0.0,
                              "e_goals": 0.4, "e_assists": 0.2})
            rows_truth.append({"season": "2025-26", "gw": 1, "code": code,
                               "team_code": i + 1, "opp_code": 90 + i,
                               "kickoff_time": KICKOFF, "minutes": minutes,
                               "starts": int(minutes > 0), "goals": 0,
                               "assists": 0, "cs": int(minutes >= 60),
                               "gc": gc})
    save_components(pd.DataFrame(rows_comp), 1)
    _before_kickoff(1)
    store.save(pd.DataFrame(rows_truth), "live/player_gw.parquet")

    by_club = _club_clean_sheets(
        _key(pd.DataFrame(rows_comp)).merge(
            _key(pd.DataFrame(rows_truth)), on=list(FIXTURE_KEYS),
            how="inner", suffixes=("", "_truth")))
    assert len(by_club) == 2
    assert list(by_club["conceded"]) == [2.0, 2.0]
    assert list(by_club["clean_sheet"]) == [0.0, 0.0]


def test_p_haul_refuses_rows_whose_inputs_are_missing(banked):
    """``assemble.p_haul`` maps a missing input to ``lam = 0`` and returns 0.0.

    That is right at solve time — a player with no attacking estimate is worth
    nothing to the optimizer — and wrong here, where it turns an artifact with
    a missing column into a head that is confidently certain nothing will
    happen and then graded against weeks where it did. A prediction that was
    never made is not a prediction of zero.
    """
    n = 80
    comp = _components(1, n)
    comp.loc[comp.index >= 40, "e_goals"] = float("nan")
    save_components(comp, 1)
    _before_kickoff(1)
    truth = _truth(1, n)
    # The rows with no inputs are exactly the ones that hauled, so grading
    # them as zeros is not a small error.
    truth.loc[truth.index >= 40, ["goals", "assists"]] = 2
    store.save(truth, "live/player_gw.parquet")

    head = evaluate_calibration(season="2025-26")["gameweeks"][0]["heads"]
    assert head["p_haul"]["n"] == 40           # the rows that had inputs
    assert head["p_play"]["n"] == 80           # and no other head loses rows
    graded = ((truth["goals"] + truth["assists"]) >= 2).iloc[:40]
    assert head["p_haul"]["brier"] == round(
        float(((p_haul(0.4, 0.2) - graded.astype(float)) ** 2).mean()), 4)


def test_p_start_is_omitted_with_its_reason(banked):
    """The trichotomy is never banked (plan A11). Asserted on the string so a
    cycle that starts banking it has to delete the entry rather than leave a
    stale explanation behind."""
    out = evaluate_calibration(season="2025-26")
    assert out["omitted"]["p_start"] == "not banked"
    assert "p_start" not in out["cumulative"]


# --- 7-9: the refusals ----------------------------------------------

def test_a_gameweek_written_after_the_whistle_is_excluded(banked):
    """Plan A12, the one real hazard. Re-running advise on a finished
    gameweek silently replaces an as-of prediction with a hindsight one."""
    save_components(_components(2), 2)
    truth = pd.concat([_truth(1), _truth(2)], ignore_index=True)
    store.save(truth, "live/player_gw.parquet")
    store.save(pd.concat([_fixtures([1]), _fixtures([2], LATER)],
                         ignore_index=True), "live/fixtures_all.parquet")
    late = pd.Timestamp(LATER).timestamp() + 86400
    os.utime(components_path(2), (late, late))

    out = evaluate_calibration(season="2025-26")
    assert {"gw": 2,
            "reason": "artifact written after the gameweek's first kickoff"
            } in out["excluded"]
    assert [row["gw"] for row in out["gameweeks"]] == [1]
    assert out["cumulative"]["p_play"]["n"] == 40   # GW1's rows only


def test_a_rerun_between_the_first_and_last_kickoff_is_excluded(banked):
    """The boundary is the gameweek's *first* kickoff, not its last.

    A gameweek is played over three days. An advise run on Sunday morning —
    ordinary behaviour, nothing exotic — has Saturday's results in the store
    and rewrites ``components_gw{N}.parquet`` for the whole week, including
    the players who already played. Guarding on the last kickoff lets that
    file through: every stamp between the two whistles passes. Only the first
    kickoff is the moment after which any part of the file could be hindsight.
    """
    store.save(pd.DataFrame({
        "gw": [1, 1], "finished": [True, True], "home_id": [1, 3],
        "away_id": [2, 4], "kickoff_time": [KICKOFF, LATER]}),
        "live/fixtures_all.parquet")
    between = pd.Timestamp(LATER).timestamp() - 3600
    os.utime(components_path(1), (between, between))

    out = evaluate_calibration(season="2025-26")
    assert out["gameweeks"] == []
    assert out["excluded"] == [
        {"gw": 1,
         "reason": "artifact written after the gameweek's first kickoff"}]


def test_a_gameweek_with_no_kickoff_information_is_also_excluded(banked):
    """The guard fails closed: unknown is an exclusion, not a pass."""
    store.save(_fixtures([9]), "live/fixtures_all.parquet")
    out = evaluate_calibration(season="2025-26")
    assert {"gw": 1, "reason": "kickoff unknown"} in out["excluded"]
    assert out["gameweeks"] == []


def test_an_artifact_that_joins_no_truth_rows_is_excluded_not_missing(banked):
    """"Missing" means one thing: nobody banked a file for that gameweek.

    A file that exists and joins nothing is a different fact with a different
    fix — codes that do not match the graded week, not an advise run that
    never happened — and folding it into the same list makes the report say
    "run advise" about a file advise already wrote.
    """
    comp = _components(1)
    comp["code"] = comp["code"] + 10_000
    save_components(comp, 1)
    _before_kickoff(1)

    out = evaluate_calibration(season="2025-26")
    assert out["missing"] == []
    assert out["excluded"] == [
        {"gw": 1, "reason": "banked components joined no graded rows"}]


def test_a_gameweek_with_no_banked_components_is_listed_as_missing(banked):
    store.save(pd.concat([_truth(1), _truth(2)], ignore_index=True),
               "live/player_gw.parquet")
    store.save(pd.concat([_fixtures([1]), _fixtures([2], LATER)],
                         ignore_index=True), "live/fixtures_all.parquet")
    out = evaluate_calibration(season="2025-26")
    assert out["missing"] == [2]
    assert [row["gw"] for row in out["gameweeks"]] == [1]


# --- 10-12: the shape it always has ---------------------------------

def test_an_empty_season_is_a_well_formed_payload(tmp_path, monkeypatch):
    """August. Never an exception."""
    monkeypatch.chdir(tmp_path)
    out = evaluate_calibration(season="2025-26")
    assert out["gameweeks"] == []
    assert all(head["status"] == "insufficient"
               for head in out["cumulative"].values())
    assert "gaffer evaluate --calibration" in out["note"]


def test_the_payload_survives_allow_nan_false(banked):
    """``save_evaluation`` refuses NaN, so a head that computed one would take
    the whole artifact down at write time rather than at read."""
    out = evaluate_calibration(season="2025-26")
    assert json.loads(json.dumps(out, allow_nan=False))["gameweeks"]


def test_saving_calibration_leaves_the_other_keys_alone(banked):
    """The merge-under-key contract, asserted here because this is the first
    new key since v5."""
    save_evaluation("current", {"run_at": "x"})
    save_evaluation("calibration", evaluate_calibration(season="2025-26"))
    stored = load_evaluation()
    assert stored["current"] == {"run_at": "x"}
    assert stored["calibration"]["gameweeks"]


def test_the_terminal_report_prints_the_refusals(banked):
    """A run that graded nothing must say so on the terminal, or an empty
    table reads as a clean one."""
    text = format_report("calibration", evaluate_calibration(season="2025-26"))
    assert "p_start" in text and "not banked" in text
    assert "GW1" in text
