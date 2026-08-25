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


def test_run_at_is_an_iso_utc_stamp():
    assert run_at().endswith("+00:00")


def test_git_sha_is_a_string_even_outside_a_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert isinstance(git_sha(), str)
