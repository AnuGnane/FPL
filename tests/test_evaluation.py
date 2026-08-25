import numpy as np
import pandas as pd

from gaffer.evaluation import (RETURN_CATEGORIES, categorize,
                               stratified_metrics)


def test_categorize_uses_openfpl_return_buckets():
    points = [0, 1, 2, 3, 4, 5, 12]
    assert list(categorize(points)) == ["zeros", "blanks", "blanks",
                                        "tickers", "tickers", "haulers",
                                        "haulers"]


def test_categorize_counts_a_negative_score_as_a_zero():
    # Own goal plus a red card can push a return below zero; it is still the
    # "nothing came of him" bucket.
    assert list(categorize([-2])) == ["zeros"]


def test_stratified_metrics_reports_every_category_plus_all():
    out = stratified_metrics([0.0, 1.0, 3.0, 6.0], [0, 1, 3, 6])
    assert list(out) == RETURN_CATEGORIES
    for cat in RETURN_CATEGORIES:
        assert out[cat]["rmse"] == 0.0 and out[cat]["mae"] == 0.0
    assert out["all"]["n"] == 4


def test_stratified_metrics_splits_error_by_the_actual_return():
    # Perfect on the zeros, two points out on the single hauler.
    out = stratified_metrics([0.0, 0.0, 3.0], [0, 0, 5])
    assert out["zeros"] == {"rmse": 0.0, "mae": 0.0, "n": 2}
    assert out["haulers"] == {"rmse": 2.0, "mae": 2.0, "n": 1}
    assert out["blanks"]["n"] == 0


def test_stratified_metrics_on_an_empty_category_is_zero_not_nan():
    out = stratified_metrics([0.0], [0])
    assert out["haulers"] == {"rmse": 0.0, "mae": 0.0, "n": 0}
    assert not np.isnan(out["haulers"]["rmse"])


def test_stratified_metrics_accepts_pandas_series():
    pred = pd.Series([2.0, 8.0], index=[7, 9])
    actual = pd.Series([1, 9], index=[3, 4])
    out = stratified_metrics(pred, actual)
    assert out["all"]["n"] == 2
    assert out["blanks"]["mae"] == 1.0


from gaffer.evaluation import head_metrics, log_loss, reliability  # noqa: E402


def test_log_loss_of_a_perfect_confident_prediction_is_about_zero():
    assert log_loss([1.0, 0.0, 1.0], [1, 0, 1]) < 1e-6


def test_log_loss_punishes_a_confident_mistake():
    assert log_loss([0.99], [0]) > log_loss([0.5], [0])


def test_log_loss_of_a_coin_flip_is_ln_two():
    assert abs(log_loss([0.5, 0.5], [1, 0]) - np.log(2)) < 1e-9


def test_log_loss_ignores_rows_with_a_missing_prediction():
    assert abs(log_loss([0.5, float("nan")], [1, 0]) - np.log(2)) < 1e-9


def test_reliability_returns_at_most_ten_bins_with_counts():
    bins = reliability(np.linspace(0.0, 1.0, 200),
                       (np.linspace(0.0, 1.0, 200) > 0.5).astype(int))
    assert 1 <= len(bins) <= 10
    assert sum(b["n"] for b in bins) == 200
    assert set(bins[0]) == {"n", "pred", "obs"}


def test_reliability_of_a_calibrated_head_tracks_the_diagonal():
    rng = np.random.default_rng(4)
    p = rng.random(20000)
    y = (rng.random(20000) < p).astype(int)
    for b in reliability(p, y):
        assert abs(b["pred"] - b["obs"]) < 0.05


def test_reliability_of_an_overconfident_head_sits_below_the_diagonal():
    # Predicts 0.9 everywhere; only half of them happen.
    p = np.full(1000, 0.9)
    y = np.tile([1, 0], 500)
    bins = reliability(p, y)
    assert len(bins) == 1
    assert bins[0]["pred"] > bins[0]["obs"]


def test_reliability_skips_empty_bins():
    bins = reliability([0.05, 0.06], [0, 1])
    assert len(bins) == 1
    assert bins[0]["n"] == 2


def test_head_metrics_packs_log_loss_and_the_curve_together():
    out = head_metrics([0.5, 0.5], [1, 0])
    assert round(out["log_loss"], 4) == round(float(np.log(2)), 4)
    assert isinstance(out["reliability"], list)


def test_stratified_metrics_drops_a_non_finite_pair():
    """One NaN ep must not poison a whole category's RMSE and MAE — the
    artifact is JSON, and a NaN in it is neither valid nor renderable."""
    out = stratified_metrics([1.0, float("nan"), 3.0], [0, 0, 0])
    assert out["zeros"]["n"] == 2
    assert out["zeros"]["mae"] == 2.0
    assert out["all"]["n"] == 2


def test_stratified_metrics_drops_a_non_finite_actual():
    out = stratified_metrics([1.0, 2.0], [0, float("nan")])
    assert out["zeros"]["n"] == 1
    assert out["all"]["n"] == 1


def test_stratified_metrics_of_only_non_finite_rows_is_zeros_not_nan():
    out = stratified_metrics([float("nan")], [float("nan")])
    assert out["all"] == {"rmse": 0.0, "mae": 0.0, "n": 0}


def test_head_metrics_reports_a_missing_log_loss_as_none_not_nan():
    """``None`` is JSON's null; ``NaN`` is not JSON at all, and the artifact
    it lands in is served straight to the web layer."""
    out = head_metrics([], [])
    assert out["log_loss"] is None


import json  # noqa: E402

import pytest  # noqa: E402

from gaffer.errors import GafferError  # noqa: E402
from gaffer.evaluation import (EVALUATION_PATH, git_sha,  # noqa: E402
                               load_evaluation, run_at, save_evaluation)


def test_load_evaluation_without_the_artifact_says_how_to_make_one(
        tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(GafferError) as exc:
        load_evaluation()
    assert "gaffer evaluate" in str(exc.value)


def test_save_evaluation_writes_under_its_mode_key(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = save_evaluation("current", {"run_at": "now", "holdout_slots": 10})
    assert path == EVALUATION_PATH
    assert json.loads(path.read_text())["current"]["holdout_slots"] == 10


def test_save_evaluation_does_not_clobber_the_other_mode(tmp_path,
                                                         monkeypatch):
    """A benchmark run takes an hour; losing last night's current-mode
    numbers to it would make the artifact useless as a regression baseline."""
    monkeypatch.chdir(tmp_path)
    save_evaluation("current", {"holdout_slots": 10})
    save_evaluation("benchmark", {"test_season": "2024-25"})
    save_evaluation("decomposition", {"season": "2025-26"})
    stored = load_evaluation()
    assert stored["current"]["holdout_slots"] == 10
    assert stored["benchmark"]["test_season"] == "2024-25"
    assert stored["decomposition"]["season"] == "2025-26"


def test_save_evaluation_replaces_its_own_key(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    save_evaluation("current", {"holdout_slots": 10})
    save_evaluation("current", {"holdout_slots": 5})
    assert load_evaluation()["current"] == {"holdout_slots": 5}


def test_save_evaluation_refuses_to_write_a_nan(tmp_path, monkeypatch):
    """A NaN written here is invalid JSON that only fails on read, three
    weeks later, as a 500 from /api/quality. Fail at write time instead."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        save_evaluation("current", {"mae": float("nan")})


def test_load_evaluation_on_a_corrupt_artifact_is_a_domain_error(
        tmp_path, monkeypatch):
    """A half-written or truncated artifact is a routine operational state —
    a run killed mid-write, a partial copy — not an unhandled crash that the
    web layer turns into a 500."""
    monkeypatch.chdir(tmp_path)
    save_evaluation("current", {"holdout_slots": 10})
    EVALUATION_PATH.write_text('{"current": {"holdout')
    with pytest.raises(GafferError) as exc:
        load_evaluation()
    assert "corrupt" in str(exc.value)


def test_save_evaluation_leaves_no_temp_file_behind(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = save_evaluation("current", {"holdout_slots": 10})
    assert [p.name for p in path.parent.iterdir()] == [path.name]


def test_save_evaluation_keeps_the_old_artifact_when_the_write_fails(
        tmp_path, monkeypatch):
    """The replace is the last step, so a rejected payload cannot leave the
    artifact truncated — last night's numbers are still on disk."""
    monkeypatch.chdir(tmp_path)
    save_evaluation("current", {"holdout_slots": 10})
    with pytest.raises(ValueError):
        save_evaluation("benchmark", {"mae": float("nan")})
    assert load_evaluation()["current"]["holdout_slots"] == 10
    assert [p.name for p in EVALUATION_PATH.parent.iterdir()] == [
        EVALUATION_PATH.name]


def test_run_at_is_an_iso_utc_stamp():
    assert run_at().endswith("+00:00")


def test_git_sha_is_a_string_even_outside_a_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert isinstance(git_sha(), str)


from gaffer.evaluation import (baseline_metrics, before_mask,  # noqa: E402
                               holdout_boundary)


def _slot_frame(slots):
    """One row per (season_idx, gw) slot, plus a baseline column."""
    return pd.DataFrame([{"season_idx": s, "gw": g, "code": 1, "ep": 1.0,
                          "total_points_r5": 2.0}
                         for s, g in slots])


def test_holdout_boundary_is_the_tenth_slot_from_the_end():
    frame = _slot_frame([(0, g) for g in range(1, 26)])
    assert holdout_boundary(frame, holdout_slots=10) == (0, 16)


def test_holdout_boundary_crosses_the_season_line():
    frame = _slot_frame([(0, g) for g in range(1, 20)]
                        + [(1, g) for g in range(1, 6)])
    assert holdout_boundary(frame, holdout_slots=10) == (0, 15)


def test_holdout_boundary_refuses_a_frame_with_no_room_for_a_holdout():
    frame = _slot_frame([(0, g) for g in range(1, 6)])
    with pytest.raises(GafferError) as exc:
        holdout_boundary(frame, holdout_slots=10)
    assert "slots" in str(exc.value)


def test_before_mask_keeps_only_strictly_earlier_slots():
    frame = _slot_frame([(0, 14), (0, 15), (0, 16), (1, 1)])
    mask = before_mask(frame, 0, 16)
    assert list(mask) == [True, True, False, False]


def test_baseline_metrics_scores_a_rolling_column_on_the_same_yardstick():
    hold = pd.DataFrame({"code": [1, 2], "gw": [10, 10],
                         "total_points_r5": [2.0, 6.0]})
    truth = pd.DataFrame({"code": [1, 2], "gw": [10, 10],
                          "total_points": [2, 5], "minutes": [90, 90]})
    out = baseline_metrics(hold, "total_points_r5", truth)
    assert out["blanks"] == {"rmse": 0.0, "mae": 0.0, "n": 1}
    assert out["haulers"] == {"rmse": 1.0, "mae": 1.0, "n": 1}


def test_baseline_metrics_collapses_a_double_gameweek_to_one_row():
    """``ep_matrix`` sums a DGW's fixtures, so the truth frame has one row
    per player-gameweek; a per-fixture baseline would otherwise be scored
    twice and go unpenalised for it."""
    hold = pd.DataFrame({"code": [1, 1], "gw": [10, 10],
                         "total_points_r5": [3.0, 3.0]})
    truth = pd.DataFrame({"code": [1], "gw": [10], "total_points": [3],
                          "minutes": [180]})
    out = baseline_metrics(hold, "total_points_r5", truth)
    assert out["all"]["n"] == 1


from gaffer.evaluation import (BENCHMARK_CAVEAT,  # noqa: E402
                               BENCHMARK_TEST_IDX, BENCHMARK_TRAIN_MAX_IDX,
                               REFERENCES, benchmark_split)
from gaffer.features.engineer import add_player_rolling  # noqa: E402


def test_reference_constants_match_the_published_openfpl_table():
    """arXiv:2508.09992, Table 3. Pinned so a typo cannot silently make the
    model look better than the paper it is being compared to."""
    assert REFERENCES["openfpl"] == {
        "zeros": {"rmse": 0.818, "mae": 0.427},
        "blanks": {"rmse": 1.291, "mae": 0.749},
        "tickers": {"rmse": 1.517, "mae": 1.127},
        "haulers": {"rmse": 5.142, "mae": 4.317},
    }
    assert REFERENCES["fplreview"] == {
        "zeros": {"rmse": 0.689, "mae": 0.237},
        "blanks": {"rmse": 1.189, "mae": 0.597},
        "tickers": {"rmse": 1.594, "mae": 1.227},
        "haulers": {"rmse": 5.172, "mae": 4.381},
    }


def test_the_caveat_names_the_training_asymmetry():
    assert "four seasons" in BENCHMARK_CAVEAT
    assert "yardstick" in BENCHMARK_CAVEAT


def test_benchmark_split_trains_on_the_first_two_seasons_only():
    frame = pd.DataFrame({"season_idx": [0, 1, 2, 3], "gw": [1, 1, 1, 1]})
    train, test = benchmark_split(frame)
    assert int(train["season_idx"].max()) <= BENCHMARK_TRAIN_MAX_IDX
    assert set(test["season_idx"]) == {BENCHMARK_TEST_IDX}


def test_benchmark_test_rows_never_reach_the_training_set():
    frame = pd.DataFrame({"season_idx": [0, 1, 2, 3], "gw": [1, 1, 1, 1],
                          "marker": ["a", "b", "leak", "d"]})
    train, _ = benchmark_split(frame)
    assert "leak" not in set(train["marker"])


def test_benchmark_features_for_a_gameweek_use_only_strictly_prior_rows():
    """The walk-forward is not a re-engineering loop: the stored rolling
    columns already shift one match back, so GW g's features cannot contain
    GW g. Pin that, because the whole benchmark rests on it."""
    rows = []
    for gw in range(1, 6):
        rows.append({"code": 1, "season_idx": 2, "gw": gw,
                     "kickoff_time": f"2024-09-{gw:02d}T14:00:00Z",
                     "total_points": 50 if gw == 3 else 2, "minutes": 90})
    frame = add_player_rolling(pd.DataFrame(rows))
    _, test = benchmark_split(frame)
    at_gw3 = test[test["gw"] == 3].iloc[0]
    at_gw4 = test[test["gw"] == 4].iloc[0]
    assert float(at_gw3["total_points_r1"]) == 2.0     # the haul is invisible
    assert float(at_gw4["total_points_r1"]) == 50.0    # ... until next week


from gaffer.evaluation import format_report  # noqa: E402


def _current_payload():
    table = {c: {"rmse": 1.0, "mae": 0.5, "n": 10} for c in RETURN_CATEGORIES}
    return {"run_at": "2026-08-25T00:00:00+00:00", "git_sha": "abc1234",
            "holdout_slots": 10,
            "stratified": {"all": table, "starters": table},
            "heads": {"p_play": {"log_loss": 0.2771,
                                 "reliability": [{"n": 5, "pred": 0.5,
                                                  "obs": 0.4}]}},
            "baselines": {"last5": table, "last38_ppg": table}}


def test_format_report_prints_every_category_and_the_baselines():
    text = format_report("current", _current_payload())
    for cat in RETURN_CATEGORIES:
        assert cat in text
    assert "baseline last5" in text
    assert "abc1234" in text
    assert "0.2771" in text


def test_format_report_prints_the_reference_columns_and_the_caveat():
    table = {c: {"rmse": 1.0, "mae": 0.5, "n": 10} for c in RETURN_CATEGORIES}
    text = format_report("benchmark", {
        "run_at": "x", "git_sha": "y", "test_season": "2024-25",
        "stratified": {"all": table}, "references": REFERENCES,
        "caveat": BENCHMARK_CAVEAT})
    assert "openfpl" in text and "fplreview" in text
    assert "5.142" in text
    assert "yardstick" in text


def test_format_report_names_the_two_derived_decomposition_numbers():
    text = format_report("decomposition", {
        "run_at": "x", "git_sha": "y", "season": "2025-26", "start_gw": 5,
        "cells": {"model_h1": {"total": 1800, "per_gw": 52.9, "hits": 4},
                  "model_h3": {"total": 1850, "per_gw": 54.4, "hits": 3},
                  "oracle_h1": {"total": 2600, "per_gw": 76.5, "hits": 2},
                  "oracle_h3": {"total": 2700, "per_gw": 79.4, "hits": 1}},
        "forecast_gap_h3": 850.0, "planning_ceiling": 100.0})
    assert "forecast_gap_h3" in text and "850" in text
    assert "planning_ceiling" in text and "100" in text
    assert "oracle_h3" in text


# --- the benchmark's scoring vintage -------------------------------------
#
# The bundled scoring table is the *current* season's. Pricing 2024-25 with
# it hands every defender free defensive-contribution points that season
# never awarded, which is a systematic upward bias against the truth the
# benchmark is scored on.

import inspect  # noqa: E402

from gaffer.evaluation import (benchmark_scoring, evaluate_benchmark,  # noqa: E402
                               evaluate_current)


def test_benchmark_scoring_drops_the_defensive_contribution_rule():
    scoring = {"goals_scored": {"MID": 5}, "defensive_contribution": {"DEF": 2}}
    assert "defensive_contribution" not in benchmark_scoring(scoring)


def test_benchmark_scoring_keeps_every_other_rule_and_copies():
    scoring = {"goals_scored": {"MID": 5}, "defensive_contribution": {"DEF": 2}}
    out = benchmark_scoring(scoring)
    assert out["goals_scored"] == {"MID": 5}
    assert "defensive_contribution" in scoring       # input untouched
    assert benchmark_scoring(out) == out             # already-absent is fine


def test_only_the_benchmark_path_restates_the_scoring_table():
    assert "benchmark_scoring(" in inspect.getsource(evaluate_benchmark)
    assert "benchmark_scoring(" not in inspect.getsource(evaluate_current)


# --- the decomposition 2x2 -----------------------------------------------

from gaffer.evaluation import run_decomposition  # noqa: E402


def _fake_backtest(totals):
    """Stand in for ``run_backtest``, keyed by (ep_source, horizon)."""
    seen = []

    def fake(season="2025-26", start_gw=5, retrain_every=4, horizon=1,
             chips=False, ep_source="model"):
        seen.append((ep_source, horizon))
        total = totals[(ep_source, horizon)]
        return {"season": season, "from_gw": start_gw, "total": total,
                "per_gw": round(total / 34, 2),
                "log": [{"gw": g, "hits": 1 if g == 6 else 0}
                        for g in range(5, 39)],
                "chips_played": {}}

    return fake, seen


def test_run_decomposition_runs_the_full_two_by_two(monkeypatch):
    fake, seen = _fake_backtest({("model", 1): 1800, ("model", 3): 1850,
                                 ("oracle", 1): 2600, ("oracle", 3): 2700})
    monkeypatch.setattr("gaffer.backtest.run_backtest", fake)
    out = run_decomposition(season="2025-26", start_gw=5)
    assert sorted(seen) == [("model", 1), ("model", 3),
                            ("oracle", 1), ("oracle", 3)]
    assert sorted(out["cells"]) == ["model_h1", "model_h3",
                                    "oracle_h1", "oracle_h3"]
    assert out["cells"]["oracle_h3"] == {"total": 2700, "per_gw": 79.41,
                                         "hits": 1}


def test_run_decomposition_names_the_two_derived_numbers(monkeypatch):
    fake, _ = _fake_backtest({("model", 1): 1800, ("model", 3): 1850,
                              ("oracle", 1): 2600, ("oracle", 3): 2700})
    monkeypatch.setattr("gaffer.backtest.run_backtest", fake)
    out = run_decomposition(season="2025-26", start_gw=5)
    # What better forecasting can win, at the horizon we actually plan on.
    assert out["forecast_gap_h3"] == 850.0
    # The most multi-week planning can ever be worth, forecasting perfect.
    assert out["planning_ceiling"] == 100.0
    assert out["season"] == "2025-26" and out["start_gw"] == 5
    assert out["git_sha"] and out["run_at"]
