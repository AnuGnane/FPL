"""Turn component predictions into expected points with the live scoring table.

Components are trained once and stay valid across rule changes: the points
value of a goal, a clean sheet or a defensive contribution enters only here,
read from ``bootstrap.scoring_table`` (i.e. the current season's rules).
"""

from __future__ import annotations

import math

import pandas as pd


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

    NaN components (a team missing from the clean-sheet model, say) propagate
    into ``ep`` for that row rather than being imputed here; callers decide
    what a missing component should default to.
    """
    df = components.copy()
    pos = df["position"]

    def s(key: str) -> pd.Series:
        return pos.map(scoring[key]).astype(float)

    df["ep"] = (
        df["p_play"] * s("minutes_0_59")
        + df["p60"] * (s("minutes_60_plus") - s("minutes_0_59"))
        + df["p_play"] * df["e_goals"] * s("goals_scored")
        + df["p_play"] * df["e_assists"] * s("assists")
        + df["p60"] * df["p_cs"] * s("clean_sheets")
        + df["p60"] * df["e_gc"] * s("goals_conceded")
        + df["p_play"] * df["e_saves"] * s("saves")
        + df["p_play"] * df["p_defcon"] * s("defensive_contribution")
        + df["p_play"] * df["e_bonus"]
        + df["p_play"] * df["e_cards"]
    )
    df["p_haul"] = [
        p_haul(_num(pl) * _num(g), _num(pl) * _num(a))
        for pl, g, a in zip(df["p_play"], df["e_goals"], df["e_assists"])
    ]
    return df


def ep_matrix(per_fixture: pd.DataFrame) -> pd.DataFrame:
    """Collapse per-fixture rows to one row per player-gameweek.

    Double gameweeks add their fixtures' expected points; a blank gameweek has
    no fixture rows at all and so is simply absent from the result. ``p_haul``
    takes the best single fixture rather than summing, since it is a
    probability.
    """
    return (per_fixture.groupby(["code", "gw"], as_index=False)
            .agg(ep=("ep", "sum"), p_haul=("p_haul", "max")))
