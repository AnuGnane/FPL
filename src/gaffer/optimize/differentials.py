"""Differential awareness: captaincy, brave alternatives, rival threats.

This module *annotates*, it never decides. The optimizer's plan is unchanged by
anything here -- these tables sit next to it and say "and here is what your
mini-league is doing about it", which is the difference between a points-maximal
plan and a rank-maximal one.

``league_eo`` comes from :func:`gaffer.data.league.effective_ownership` over the
user's actual rivals, so it is a *rival* ownership percentage, not global FPL
ownership. Captaincy makes it a multiplier-weighted number: it can exceed 100
when most rivals captain the same player, so never treat it as a 0-100 scale.

An empty ``league_eo`` (no league configured) degrades quietly: every player
gets 0.0 EO, so the captain table still ranks on EP alone, nothing is a threat,
and every alternative clears the low-ownership bar.
"""

from __future__ import annotations

import pandas as pd

DIFFERENTIAL_EO = 30.0
"""Rival EO below which a captain pick is a genuine rank differential."""

ALTERNATIVE_EO = 20.0
"""Rival EO below which a same-position swap counts as 'being brave'."""

_ALT_COLS = ["code", "name", "ep", "p_haul", "league_eo"]


def _with_eo(ep: pd.DataFrame, league_eo: dict[int, float]) -> pd.DataFrame:
    df = ep.copy()
    df["league_eo"] = df["code"].map(league_eo).fillna(0.0)
    return df


def captain_table(ep: pd.DataFrame, xi_codes: list[int],
                  league_eo: dict[int, float], top: int = 5) -> pd.DataFrame:
    """Top captain candidates from the recommended XI with EV, ceiling and
    rival ownership.

    ``differential`` = rival EO under :data:`DIFFERENTIAL_EO` *and* an
    above-median ceiling among the shortlisted candidates. Both halves matter:
    a low-owned player with no ceiling is not a differential, it is just a bad
    captain.
    """
    df = _with_eo(ep[ep["code"].isin(xi_codes)], league_eo)
    df = df.nlargest(top, "ep").reset_index(drop=True)
    median_haul = df["p_haul"].median()
    df["differential"] = ((df["league_eo"] < DIFFERENTIAL_EO)
                          & (df["p_haul"] >= median_haul))
    return df[["code", "name", "position", "ep", "p_haul", "league_eo",
               "differential"]]


def transfer_alternatives(ep: pd.DataFrame, buy_code: int,
                          league_eo: dict[int, float],
                          margin: float = 0.5) -> pd.DataFrame:
    """Same-position players within ``margin`` EP of the recommended buy but
    with rival EO under :data:`ALTERNATIVE_EO` -- the 'if you want to be brave'
    list. Costed in EP, so the price of bravery is explicit.

    An unknown ``buy_code`` (player filtered out of the pool between solve and
    report) yields an empty frame rather than raising.
    """
    df = _with_eo(ep, league_eo)
    match = df[df["code"] == buy_code]
    if match.empty:
        return pd.DataFrame(columns=_ALT_COLS)
    rec = match.iloc[0]
    alts = df[(df["position"] == rec["position"]) & (df["code"] != buy_code)
              & (df["ep"] >= rec["ep"] - margin)
              & (df["league_eo"] < ALTERNATIVE_EO)]
    return alts.sort_values("ep", ascending=False)[
        _ALT_COLS].reset_index(drop=True)


def threat_board(ep: pd.DataFrame, my_codes: list[int],
                 league_eo: dict[int, float],
                 min_eo: float = 50.0) -> pd.DataFrame:
    """High-EO rival players you don't own, by EP -- your exposure if they haul.

    This is the downside mirror of the captain table: not points you can gain,
    but rank you can lose by standing still.
    """
    df = _with_eo(ep, league_eo)
    threats = df[(~df["code"].isin(my_codes)) & (df["league_eo"] >= min_eo)]
    return threats.sort_values("ep", ascending=False)[
        ["code", "name", "position", "ep", "league_eo"]].reset_index(drop=True)
