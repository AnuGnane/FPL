"""Turn component predictions into expected points with the live scoring table.

Components are trained once and stay valid across rule changes: the points
value of a goal, a clean sheet or a defensive contribution enters only here,
read from ``bootstrap.scoring_table`` (i.e. the current season's rules).
"""

from __future__ import annotations

import math

import pandas as pd


PEN_FACED_RATE = 0.06
"""Penalties faced per gameweek by a starting keeper — a league-average prior,
not modelled per team or per keeper."""

PEN_SAVE_RATE = 0.30
"""Share of faced penalties a keeper saves — a league-average prior, not
modelled per keeper."""


def _num(value) -> float:
    """``value`` as a float, with NaN/None/unparseable mapped to 0.0.

    ``value or 0.0`` will not do: NaN is truthy, so it survives the
    short-circuit and poisons the total.
    """
    if value is None:
        return 0.0
    try:
        out = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(out) else out


def p_haul(e_goals: float, e_assists: float) -> float:
    """P(2+ attacking returns) under Poisson(e_goals + e_assists)."""
    lam = max(0.0, _num(e_goals) + _num(e_assists))
    return 1.0 - math.exp(-lam) * (1.0 + lam)


def assemble_ep(components: pd.DataFrame,
                scoring: dict[str, dict[str, float]]) -> pd.DataFrame:
    """One row per player-fixture with all component predictions -> ``ep``.

    Attacking/saves/defcon/bonus/cards components are per-appearance rates, so
    they scale by ``p_play``; clean sheets and goals conceded only score for a
    player who reaches 60 minutes, so they scale by ``p60``. Appearance points
    are ``p_play`` for turning out at all plus the extra step at 60 minutes.

    Keepers additionally earn a penalty-save term from the league-average
    priors :data:`PEN_FACED_RATE` and :data:`PEN_SAVE_RATE`; the points value
    still comes from the table. Rules an older table predates
    (``penalties_saved``, ``bonus``) or a restated one deliberately omits
    (``defensive_contribution``, which 2024-25 did not award) fall back to a
    no-op.

    NaN components (a team missing from the clean-sheet model, say) propagate
    into ``ep`` for that row rather than being imputed here; callers decide
    what a missing component should default to.
    """
    df = components.copy()
    pos = df["position"]

    def s(key: str) -> pd.Series:
        return pos.map(scoring[key]).astype(float)

    def s_opt(key: str, default: float) -> pd.Series:
        """``s`` for a rule an older scoring table may not carry at all."""
        table = scoring.get(key) or {}
        return pos.map(lambda p: float(table.get(p, default))).astype(float)

    df["ep"] = (
        df["p_play"] * s("minutes_0_59")
        + df["p60"] * (s("minutes_60_plus") - s("minutes_0_59"))
        + df["p_play"] * df["e_goals"] * s("goals_scored")
        + df["p_play"] * df["e_assists"] * s("assists")
        + df["p60"] * df["p_cs"] * s("clean_sheets")
        + df["p60"] * df["e_gc"] * s("goals_conceded")
        + df["p_play"] * df["e_saves"] * s("saves")
        + df["p_play"] * df["p_defcon"]
        * s_opt("defensive_contribution", 0.0)
        + df["p_play"] * df["e_bonus"] * s_opt("bonus", 1.0)
        + df["p_play"] * df["e_cards"]
        + df["p_play"] * (pos == "GKP").astype(float)
        * PEN_FACED_RATE * PEN_SAVE_RATE * s_opt("penalties_saved", 0.0)
    )
    df["p_haul"] = [
        p_haul(_num(pl) * _num(g), _num(pl) * _num(a))
        for pl, g, a in zip(df["p_play"], df["e_goals"], df["e_assists"])
    ]
    return df


def apply_calibration(assembled: pd.DataFrame, cal) -> pd.DataFrame:
    """Calibrate per-fixture ``ep``, before :func:`ep_matrix` collapses rows.

    Sitting here rather than after ``ep_matrix`` means each fixture of a
    double gameweek gets its own correction and only then sums — a DGW player
    is expected to start twice, so he earns the starter correction twice,
    which collapsing first would hide. ``cal`` of ``None`` (an old model
    directory with no calibration artifact) is the identity.
    """
    if cal is None:
        return assembled
    return cal.apply(assembled)


def ep_matrix(per_fixture: pd.DataFrame) -> pd.DataFrame:
    """Collapse per-fixture rows to one row per player-gameweek.

    Double gameweeks add their fixtures' expected points; a blank gameweek has
    no fixture rows at all and so is simply absent from the result. ``p_haul``
    takes the best single fixture rather than summing, since it is a
    probability.
    """
    return (per_fixture.groupby(["code", "gw"], as_index=False)
            .agg(ep=("ep", "sum"), p_haul=("p_haul", "max")))


BREAKDOWN_COLS = ["ep_minutes", "ep_goals", "ep_assists", "ep_cs", "ep_gc",
                  "ep_saves", "ep_defcon", "ep_bonus", "ep_cards",
                  "ep_pensave"]


def ep_breakdown(assembled: pd.DataFrame,
                 scoring: dict[str, dict[str, float]]) -> pd.DataFrame:
    """Split each row's ``ep`` into the additive terms that produced it.

    Deliberately a second spelling of :func:`assemble_ep`'s expression rather
    than a refactor of it: the aggregate is on the hot path of every solve and
    every backtest week, and a per-term frame there would cost memory for a
    number only the explainability page reads. The two are pinned together by
    a test that re-adds the terms.
    """
    df = assembled.copy()
    pos = df["position"]

    def s(key: str) -> pd.Series:
        return pos.map(scoring[key]).astype(float)

    def s_opt(key: str, default: float) -> pd.Series:
        table = scoring.get(key) or {}
        return pos.map(lambda p: float(table.get(p, default))).astype(float)

    df["ep_minutes"] = (df["p_play"] * s("minutes_0_59")
                        + df["p60"] * (s("minutes_60_plus")
                                       - s("minutes_0_59")))
    df["ep_goals"] = df["p_play"] * df["e_goals"] * s("goals_scored")
    df["ep_assists"] = df["p_play"] * df["e_assists"] * s("assists")
    df["ep_cs"] = df["p60"] * df["p_cs"] * s("clean_sheets")
    df["ep_gc"] = df["p60"] * df["e_gc"] * s("goals_conceded")
    df["ep_saves"] = df["p_play"] * df["e_saves"] * s("saves")
    df["ep_defcon"] = (df["p_play"] * df["p_defcon"]
                       * s_opt("defensive_contribution", 0.0))
    df["ep_bonus"] = df["p_play"] * df["e_bonus"] * s_opt("bonus", 1.0)
    df["ep_cards"] = df["p_play"] * df["e_cards"]
    df["ep_pensave"] = (df["p_play"] * (pos == "GKP").astype(float)
                        * PEN_FACED_RATE * PEN_SAVE_RATE
                        * s_opt("penalties_saved", 0.0))
    return df
