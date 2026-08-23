"""Team Elo ratings derived from historical match results."""

from __future__ import annotations

import pandas as pd

K = 20.0
HOME_ADV = 60.0
INIT = 1500.0


def compute_elo(fixtures: pd.DataFrame) -> pd.DataFrame:
    """Per-team pre-match Elo for every (season_idx, gw, team code).

    Input: rows with season_idx, gw, kickoff_time, home_code, away_code,
    home_goals, away_goals — completed matches only. Returns long frame
    [season_idx, gw, code, elo_pre]; df.attrs['final'] maps code -> latest elo
    (used to rate future fixtures).
    """
    fx = fixtures.sort_values(["season_idx", "kickoff_time"]).copy()
    ratings: dict[int, float] = {}
    rows = []
    for m in fx.itertuples():
        rh = ratings.get(m.home_code, INIT)
        ra = ratings.get(m.away_code, INIT)
        rows.append({"season_idx": m.season_idx, "gw": m.gw,
                     "code": m.home_code, "elo_pre": rh})
        rows.append({"season_idx": m.season_idx, "gw": m.gw,
                     "code": m.away_code, "elo_pre": ra})
        exp_home = 1.0 / (1.0 + 10 ** (-((rh + HOME_ADV) - ra) / 400.0))
        if m.home_goals > m.away_goals:
            score = 1.0
        elif m.home_goals < m.away_goals:
            score = 0.0
        else:
            score = 0.5
        ratings[m.home_code] = rh + K * (score - exp_home)
        ratings[m.away_code] = ra + K * ((1 - score) - (1 - exp_home))
    out = pd.DataFrame(rows).drop_duplicates(
        subset=["season_idx", "gw", "code"], keep="first")
    out.attrs["final"] = ratings
    return out
