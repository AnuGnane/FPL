"""Wide bands on the chip valuations: arithmetic, not opinion (spec D5).

Everything asserted here would have to be *broken* to fail — a bench boost
worth forty points, a triple captain worth a negative number, a chip flagged
"play it now" whose own gain is under its own threshold. The community's
base-rate bands (a single-gameweek bench boost is worth roughly 8-12 points,
a double-gameweek one 15-25) are deliberately **not** asserted: they are
printed by ``scripts/chip_baserates.py`` for the outcome record, because our
model is allowed to disagree with a forum and is not allowed to disagree with
addition.

The board is a fixture, so these rails run in milliseconds on any machine and
say the same thing on all of them. The second half checks the *real* served
table when there is one on disk, and skips when there is not.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from gaffer.artifacts import REPORTS, latest_gw
from gaffer.optimize.chip_policy import chip_thresholds_from_asset
from gaffer.optimize.chips import evaluate_chips
from gaffer.optimize.milp import SolveInput

BB_BAND = (0.0, 40.0)
"""Bench boost, expected points. Zero because the chip is never forced to
hurt — the solver may decline to place it — and forty because four bench
players cannot outscore the entire eleven that is already on the pitch."""

TC_BAND = (0.0, 25.0)
"""Triple captain: one extra copy of one player's week. Twenty-five is a
hat-trick with the bonus and the clean sheet, which is the ceiling of a
gameweek nobody plans for."""

WC_BAND = (0.0, 120.0)
"""Wildcard, over the whole horizon. A whole squad rebuilt across six weeks
can be worth a lot; a hundred and twenty is where the number stops being a
squad upgrade and starts being a units bug."""

CFG = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
           itb_value=0.05, hit_cost=4)

OWNED = [1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 16, 17, 18]


def _pool(star: float = 3.0) -> pd.DataFrame:
    rows, code = [], 1
    for position, n in (("GKP", 2), ("DEF", 6), ("MID", 7), ("FWD", 5)):
        for _ in range(n):
            ep = star if code == 20 else 3.0
            rows.append({"code": code, "position": position,
                         "team_code": code % 8, "cost": 50, "sell": 50,
                         "ep": {1: ep, 2: ep}})
            code += 1
    return pd.DataFrame(rows)


def _table(**kw) -> pd.DataFrame:
    state = SolveInput(owned_codes=list(OWNED), bank=0, free_transfers=1,
                       gws=[1, 2])
    return evaluate_chips(_pool(**kw), state,
                          chips_available=["wildcard", "bboost", "3xc"],
                          **CFG)


def _gain(table: pd.DataFrame, chip: str) -> float:
    rows = table[table["chip"] == chip]
    return float(rows["gain"].max())


# --- the fixture board ------------------------------------------------


def test_no_chip_is_ever_valued_negative():
    """A chip you may decline to play is worth zero, never less: a negative
    gain means the no-chip baseline was solved on a different board."""
    assert (_table()["gain"] > -1e-6).all()


def test_the_bench_boost_stays_inside_its_band():
    assert BB_BAND[0] <= _gain(_table(), "bboost") <= BB_BAND[1]


def test_the_triple_captain_stays_inside_its_band():
    assert TC_BAND[0] <= _gain(_table(), "3xc") <= TC_BAND[1]


def test_the_wildcard_stays_inside_its_band():
    assert WC_BAND[0] <= _gain(_table(), "wildcard") <= WC_BAND[1]


def test_the_triple_captain_is_worth_about_the_captains_own_week():
    """The one arithmetic identity in the set: a third copy of the armband is
    a third copy of that player's expected points, not of the squad's."""
    table = _table(star=9.0)
    assert _gain(table, "3xc") == pytest.approx(9.0, abs=1.0)


def test_a_better_bench_is_worth_more_bench_boost():
    """Monotonicity, which a sign error breaks and a band does not."""
    poor = _gain(_table(), "bboost")
    rich = _gain(_table(star=9.0), "bboost")
    assert rich >= poor


def test_per_week_is_gain_over_the_weeks_it_is_credited_with():
    table = _table()
    row = table.iloc[0]
    assert row["per_week"] <= row["gain"] + 1e-9
    assert row["per_week"] > 0 or row["gain"] == pytest.approx(0.0)


# --- the play_now flag ------------------------------------------------


def _play_now(table: pd.DataFrame) -> dict[str, bool]:
    """``run_advise``'s own two lines, mirrored on a fixture table.

    The advice writes, for every row of ``evaluate_chips``' output::

        theta = float(chip_thresholds(str(row["chip"]), int(row["gw"])))
        row["threshold"] = round(theta, 2)
        row["play_now"] = bool(float(row["gain"]) >= theta)

    with ``chip_thresholds`` built by ``chip_thresholds_from_asset``. Repeated
    here rather than imported because ``advise`` builds it inside a several
    hundred line function; the served half of this file checks the real
    table's own flag against its own threshold, so the two cannot drift apart
    unnoticed.

    Answers the best row per chip, which is the row the recommendation is
    about.
    """
    thresholds = chip_thresholds_from_asset(None)
    best: dict[str, bool] = {}
    for row in table.sort_values("gain").to_dict("records"):
        theta = float(thresholds(str(row["chip"]), int(row["gw"])))
        best[str(row["chip"])] = bool(float(row["gain"]) >= theta)
    return best


def test_a_chip_worth_more_than_its_bar_is_flagged_and_one_worth_less_is_not():
    """The flag against a board whose answer is known by arithmetic.

    With the captain on nine expected points the triple captain is worth about
    nine (the identity two tests up) against a four-point bar with no priors
    asset, so it plays; on the flat board it is worth three against the same
    bar, so it waits. A flag that cannot tell those two boards apart is a chip
    recommendation nobody can audit.
    """
    assert _play_now(_table(star=9.0))["3xc"] is True
    assert _play_now(_table())["3xc"] is False


def test_a_chip_worth_nothing_is_never_flagged():
    """theta is never negative, so a zero gain can never clear it."""
    table = _table()
    flags = _play_now(table)
    for chip, flagged in flags.items():
        if _gain(table, chip) == pytest.approx(0.0):
            assert flagged is False


# --- the served table, when there is one ------------------------------


def _served() -> list[dict]:
    gw = latest_gw()
    if gw is None:
        pytest.skip("no advice on disk — the fixture rails still ran")
    path = REPORTS / f"gw{gw}-advice.json"
    if not path.exists():
        pytest.skip(f"no reports/gw{gw}-advice.json on this machine")
    rows = json.loads(path.read_text()).get("chip_table") or []
    if not rows:
        pytest.skip("this week's advice priced no chips")
    return [r for r in rows if isinstance(r, dict)]


def test_the_served_chip_table_is_inside_the_same_bands():
    bands = {"bboost": BB_BAND, "3xc": TC_BAND, "wildcard": WC_BAND}
    for row in _served():
        low, high = bands.get(str(row.get("chip")), (-1e9, 1e9))
        gain = float(row.get("gain", 0.0))
        assert low - 1e-6 <= gain <= high, row


def test_the_served_play_now_flag_agrees_with_its_own_threshold():
    for row in _served():
        if row.get("threshold") is None:
            continue
        assert bool(row.get("play_now")) == (
            float(row["gain"]) >= float(row["threshold"])), row
