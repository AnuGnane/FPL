"""Holiday F-164: ``gaffer.models.modes`` pinned on its own.

v18d §2 cut the mode vocabulary out of ``models.minutes`` into a leaf module
that the minutes model and the DNP calibrator both import; until now it was
reached only through those callers, so a change to the label rule surfaced
as a drift in a fitted model rather than as a named failure.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from gaffer.models.modes import DNP, MODE_COLS, START, SUB, mode_labels


def test_the_mode_columns_run_dnp_sub_start_in_label_order():
    assert MODE_COLS == ["p_dnp", "p_sub", "p_start"]
    assert (DNP, SUB, START) == (0, 1, 2)


def test_a_zero_minute_row_is_dnp_whatever_its_starts_flag():
    df = pd.DataFrame({"minutes": [0, 0], "starts": [0, 1]})
    assert mode_labels(df).tolist() == [DNP, DNP]


def test_minutes_with_no_start_is_a_sub():
    df = pd.DataFrame({"minutes": [12, 75], "starts": [0, 0]})
    assert mode_labels(df).tolist() == [SUB, SUB]


def test_a_start_and_a_double_gameweeks_two_starts_are_both_starts():
    # v18d: the column is a count, so an aggregated double gameweek carries 2.
    df = pd.DataFrame({"minutes": [30, 180], "starts": [1, 2]})
    assert mode_labels(df).tolist() == [START, START]


def test_a_missing_starts_column_falls_back_to_sixty_minutes():
    df = pd.DataFrame({"minutes": [0, 59, 60, 90]})
    assert mode_labels(df).tolist() == [DNP, SUB, START, START]


def test_a_nan_starts_falls_back_to_sixty_minutes_on_that_row_alone():
    df = pd.DataFrame({"minutes": [45, 70, 70],
                       "starts": [np.nan, np.nan, 0]})
    assert mode_labels(df).tolist() == [SUB, START, SUB]


def test_the_labels_keep_the_frames_index_as_integers():
    df = pd.DataFrame({"minutes": [90, 0]}, index=[7, 3])
    out = mode_labels(df)
    assert out.index.tolist() == [7, 3]
    assert out.dtype == "int64"
