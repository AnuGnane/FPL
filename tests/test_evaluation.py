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
