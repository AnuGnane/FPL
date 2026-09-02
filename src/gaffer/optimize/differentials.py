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

# v12 W1 §2.2 (specs/2026-09-01-gaffer-v12-program-design.md). Three
# thresholds on effective ownership, in one place and in one unit. They were
# in two places and two units: advise.py carried DIFFERENTIAL_EO = 0.3 and
# TEMPLATE_EO = 0.7 as fractions, this module carried DIFFERENTIAL_EO = 30.0
# and ALTERNATIVE_EO = 20.0 as percentages, and the two DIFFERENTIAL_EOs were
# the same threshold on the same quantity — which is a coincidence waiting to
# stop being one.
#
# Fractions, because that is the unit a probability-shaped quantity should be
# in and because a reader who sees 0.30 cannot mistake it for a count. The two
# comparisons in this module read `league_eo`, which is a *percentage* on the
# frame, so they multiply at the point of comparison rather than dividing the
# column: `league_eo` is returned to callers and rescaling it would change a
# served number.
DIFFERENTIAL_EO = 0.30
"""Rival EO below which a captain pick is a genuine rank differential."""

ALTERNATIVE_EO = 0.20
"""Rival EO below which a same-position swap counts as 'being brave'."""

TEMPLATE_EO = 0.70
"""At or above it, buying a player is covering one the league already owns.

Moved here from ``advise.py`` rather than found here: this module is the
canonical home for EO thresholds and was missing the third.
"""

_ALT_COLS = ["code", "name", "ep", "p_haul", "league_eo"]


def _with_eo(ep: pd.DataFrame, league_eo: dict[int, float]) -> pd.DataFrame:
    df = ep.copy()
    df["league_eo"] = df["code"].map(league_eo).fillna(0.0)
    return df


def captain_table(ep: pd.DataFrame, xi_codes: list[int],
                  league_eo: dict[int, float], top: int = 5,
                  haul: dict[int, float] | None = None) -> pd.DataFrame:
    """Top captain candidates from the recommended XI with EV, ceiling and
    rival ownership.

    ``differential`` = rival EO under :data:`DIFFERENTIAL_EO` *and* an
    above-median ceiling among the shortlisted candidates. Both halves matter:
    a low-owned player with no ceiling is not a differential, it is just a bad
    captain.

    **The ceiling (v12 W3 §4.6,
    specs/2026-09-01-gaffer-v12-program-design.md).** ``haul`` is
    ``{code: P(total points >= 10)}`` from ``uncertainty.bands_by_player_gw``
    — the gameweek's whole point distribution, EP summed across a double
    gameweek's fixtures with the sweep's own sigma. Given one, the table
    carries it as ``p_haul_total`` and drops ``p_haul``.

    Dropping it is the point rather than a tidy-up. ``ep_matrix`` collapses a
    double gameweek with ``p_haul=("p_haul", "max")`` — *"takes the best single
    fixture rather than summing, since it is a probability"* — so on the exact
    week a captain matters most, the ceiling column was the better of two
    fixtures printed under the header ``P(2+ returns)``: a ranking number
    wearing a probability's label, and the number a doubled-up captain is
    chosen *for* was the one it could not show.

    Without a ``haul`` — or with one that covers none of the shortlist — the
    frame is exactly today's, ``p_haul`` and all, and a line says so. That is
    the rail: a component frame with no minutes model produces no bands, and a
    captain table is not worth failing over a ceiling.
    """
    df = _with_eo(ep[ep["code"].isin(xi_codes)], league_eo)
    df = df.nlargest(top, "ep").reset_index(drop=True)
    ceiling_col = "p_haul"
    if haul:
        mapped = df["code"].map(lambda c: haul.get(int(c)))
        if mapped.notna().any():
            # v12 W3 T8-T11 review, Important 1: held as an object column so a
            # missing band stays ``None``. A partially-covered map makes pandas
            # infer float64, whose blank is NaN — and NaN is a float, so the
            # report's ``is not none`` guard passes it through to ``nan%`` and
            # ``advise``'s ``json.dumps`` writes the bare token ``NaN``, which
            # no strict JSON reader accepts. Same idiom, and the same reason,
            # as ``evaluate_chips``' ``gw2``.
            df["p_haul_total"] = mapped.astype("object").where(mapped.notna(),
                                                               None)
            df = df.drop(columns=["p_haul"])
            ceiling_col = "p_haul_total"
        else:
            print("captain_table: no shortlisted captain carries a points "
                  "band, so the ceiling stays P(2+ attacking returns)")
    ceiling = pd.to_numeric(df[ceiling_col], errors="coerce")
    # league_eo is a percentage on this frame (captaincy can push it past 100);
    # the constant is a fraction. Convert here rather than rescaling the
    # column, which is returned to the caller.
    df["differential"] = ((df["league_eo"] < DIFFERENTIAL_EO * 100)
                          & (ceiling >= ceiling.median()))
    return df[["code", "name", "position", "ep", ceiling_col, "league_eo",
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
              # fraction constant, percent column — see captain_table.
              & (df["league_eo"] < ALTERNATIVE_EO * 100)]
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
