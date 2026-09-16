"""v19's rails: the model's free half (v19g §2.1, §2.2).

Two things the model cycle's candidates said were true and nothing asserted.
C13 closed by accrual — ``models/calibration.joblib`` carries all four
``by_pos`` keys since the 200-row floor was met — but a season that starts
thin would drop the goalkeepers out again silently, so the contract is pinned
on a synthetic fit and ``missing`` is checked to name the position that fell
below the floor. C12 is live: a club-fixture with no market odds is served
on the bare team model, and on the working tree's newest components file
that model puts two clubs at a 0.94 clean-sheet chance and 0.06 goals
conceded. The band below is the spec's pre-registered claim for a v20 clip,
so the market-backed rows are held to it now (a market-priced value outside
it is a bug today) and every served row is a strict ``xfail`` until the clip
lands: the day the band holds on every row, this file says so by failing,
and the mark comes off in that cycle's own commit.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd
import pytest

from gaffer import artifacts
from gaffer.models.calibrate import MIN_ROWS, POSITION_GROUPS, CalibrationModel

# v19g §2.2: the served band a v20 clip is measured against. Not widened to
# pass; see the module docstring for what is held to it today.
P_CS_BAND = (0.02, 0.85)
E_GC_BAND = (0.15, 4.0)

_COMPONENTS_RE = re.compile(r"components_gw(\d+)\.parquet$")


def _fit(rows_per_position: dict[str, int]) -> CalibrationModel:
    rng = np.random.default_rng(0)
    pos = np.concatenate([[p] * n for p, n in rows_per_position.items()])
    ep = pd.Series(rng.uniform(1, 6, len(pos)))
    actual = ep + pd.Series(rng.normal(1.0, 0.5, len(pos)))
    return CalibrationModel().fit(ep, actual, pd.Series(pos))


def test_a_calibration_fit_at_the_floor_carries_all_four_positions():
    fitted = _fit({p: 250 for p in POSITION_GROUPS})
    assert sorted(fitted.by_pos) == sorted(POSITION_GROUPS)


def test_a_position_under_the_floor_is_the_one_missing_names():
    thin = {p: 250 for p in POSITION_GROUPS} | {"GKP": MIN_ROWS - 50}
    fitted = _fit(thin)
    missing = [p for p in POSITION_GROUPS if p not in fitted.by_pos]
    assert missing == ["GKP"]


def _newest_club_fixtures() -> pd.DataFrame:
    newest = None
    for path in artifacts.REPORTS.glob("components_gw*.parquet"):
        m = _COMPONENTS_RE.search(path.name)
        if m and (newest is None or int(m.group(1)) > newest[0]):
            newest = (int(m.group(1)), path)
    if newest is None:
        pytest.skip("no reports/components_gw*.parquet on this machine")
    frame = pd.read_parquet(newest[1])
    for col in ("team_code", "gw", "p_cs", "e_gc", "odds_weight"):
        if col not in frame:
            pytest.skip(f"{newest[1].name} has no {col} column")
    return frame.drop_duplicates(["team_code", "gw"])


def _inside(frame: pd.DataFrame) -> bool:
    return bool(frame["p_cs"].between(*P_CS_BAND).all()
                and frame["e_gc"].between(*E_GC_BAND).all())


def test_a_market_backed_club_fixture_is_served_inside_the_band():
    priced = _newest_club_fixtures().query("odds_weight > 0")
    if priced.empty:
        pytest.skip("no market-backed club-fixture in the newest file")
    assert _inside(priced), (
        priced.loc[~priced["p_cs"].between(*P_CS_BAND)
                   | ~priced["e_gc"].between(*E_GC_BAND),
                   ["team_name", "gw", "p_cs", "e_gc", "odds_weight"]]
        .to_string())


@pytest.mark.xfail(
    strict=True,
    reason="v19g §2.2: the bare team model breaches the band on the zero-odds "
           "week; the v20 clip is measured against this and removes the mark")
def test_every_served_club_fixture_is_inside_the_band():
    assert _inside(_newest_club_fixtures())
