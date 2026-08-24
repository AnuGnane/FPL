"""Leakage-safe feature engineering for the canonical ``player_gw`` table.

Every model trains on these columns, so the one invariant that matters is
that a feature for gameweek *t* is computed only from matches strictly
before *t*. ``shift(1)`` before the rolling window enforces that.
"""

from __future__ import annotations

import pandas as pd

ROLL_STATS = ["total_points", "minutes", "starts", "goals", "assists", "xg",
              "xa", "xgi", "xgc", "cs", "gc", "saves", "bonus", "bps",
              "defcon", "tackles", "cbi", "recoveries", "yc"]
WINDOWS = [1, 3, 5, 10, 38]


def add_player_rolling(df: pd.DataFrame, stats: list[str] = ROLL_STATS,
                       windows: list[int] = WINDOWS) -> pd.DataFrame:
    """Rolling means of past matches only. Rows must be one per player-match.

    ``shift(1)`` guarantees the current row never leaks into its own
    features. NaNs inside a window (missing stat / future rows) are skipped
    by ``mean()``.
    """
    # kickoff_time breaks the tie between a double gameweek's two fixtures,
    # which otherwise share (code, season_idx, gw) and order arbitrarily.
    sort_cols = ["code", "season_idx", "gw"]
    if "kickoff_time" in df.columns:
        sort_cols.append("kickoff_time")
    df = df.sort_values(sort_cols).reset_index(drop=True)
    missing = [s for s in stats if s not in df.columns]
    if missing:
        df = df.assign(**{s: float("nan") for s in missing})
    g = df.groupby("code", sort=False)
    # built as one block: ~100 individual inserts fragments the frame
    feats: dict[str, pd.Series] = {}
    for stat in stats:
        shifted = g[stat].shift(1)
        for w in windows:
            feats[f"{stat}_r{w}"] = (
                shifted.groupby(df["code"]).rolling(w, min_periods=1).mean()
                .reset_index(level=0, drop=True))
    return pd.concat([df, pd.DataFrame(feats, index=df.index)], axis=1)


def _order_score(order: pd.Series) -> pd.Series:
    """FPL set-piece queue position -> [0, 1]. First choice is worth the
    whole feature, second choice half, anyone further down nothing. An
    absent order stays NaN: LightGBM splits on missing natively, and
    "not listed" is genuinely different from "listed fifth"."""
    v = pd.to_numeric(order, errors="coerce")
    out = pd.Series(float("nan"), index=v.index, dtype="float64")
    out[v == 1] = 1.0
    out[v == 2] = 0.5
    out[v >= 3] = 0.0
    return out


def add_setpiece(df: pd.DataFrame, miss_window: int = 38) -> pd.DataFrame:
    """``pen_taker`` and ``setpiece_taker`` from the bootstrap order columns.

    The orders only exist on live snapshots; every historical row carries
    NaN for them. For penalties there is one usable back-fill: a player who
    missed a penalty demonstrably takes them, so from the match *after* the
    miss (same shift(1)-before-rolling discipline as
    :func:`add_player_rolling`) the trailing ``miss_window`` matches set
    ``pen_taker`` to 1.0. Absence of a miss proves nothing, so it stays NaN
    rather than 0.0. Set pieces have no equivalent proxy.

    Columns whose source is absent are simply skipped (all-NaN output).
    """
    sort_cols = [c for c in ("code", "season_idx", "gw", "kickoff_time")
                 if c in df.columns]
    if "code" in df.columns:
        df = df.sort_values(sort_cols).reset_index(drop=True)
    else:
        df = df.copy()
    absent = pd.Series(float("nan"), index=df.index, dtype="float64")

    def src(name: str) -> pd.Series:
        if name not in df.columns:
            return absent
        return pd.to_numeric(df[name], errors="coerce")

    pen_order = src("penalties_order")
    pen_taker = _order_score(pen_order)
    if "pens_missed" in df.columns and "code" in df.columns:
        missed = pd.to_numeric(df["pens_missed"], errors="coerce")
        shifted = missed.groupby(df["code"]).shift(1)
        rolled = (shifted.groupby(df["code"])
                  .rolling(miss_window, min_periods=1).sum()
                  .reset_index(level=0, drop=True))
        proxy = pd.Series(float("nan"), index=df.index, dtype="float64")
        proxy[rolled > 0] = 1.0
        # Live order wins where present; the proxy fills history rows only.
        pen_taker = pen_taker.where(pen_order.notna(), proxy)
    df["pen_taker"] = pen_taker
    best = pd.DataFrame({"direct": src("direct_freekicks_order"),
                         "corners": src("corners_and_indirect_freekicks_order")}
                        ).min(axis=1)  # NaN-safe: NaN only if both are absent
    df["setpiece_taker"] = _order_score(best)
    return df


def add_context(df: pd.DataFrame, elo: pd.DataFrame | None,
                elo_final: dict | None) -> pd.DataFrame:
    """Team/opponent Elo (own team via ``team_code``, opponent via
    ``opp_code``) and rest days. Future rows fall back to the latest Elo
    (``elo_final``). Columns whose source is absent are simply skipped.
    """
    if elo is not None and "team_code" in df.columns:
        team_elo = elo.rename(columns={"code": "team_code",
                                       "elo_pre": "team_elo"})
        df = df.merge(team_elo, on=["season_idx", "gw", "team_code"], how="left")
        opp_elo = elo.rename(columns={"code": "opp_code", "elo_pre": "opp_elo"})
        df = df.merge(opp_elo, on=["season_idx", "gw", "opp_code"], how="left")
        if elo_final:
            df["team_elo"] = df["team_elo"].fillna(df["team_code"].map(elo_final))
            df["opp_elo"] = df["opp_elo"].fillna(df["opp_code"].map(elo_final))
        df["elo_diff"] = df["team_elo"] - df["opp_elo"]
    if "was_home" in df.columns:
        df["home"] = df["was_home"].astype("float")
    if "kickoff_time" in df.columns:
        kt = pd.to_datetime(df["kickoff_time"], errors="coerce", utc=True)
        df["days_rest"] = (kt - kt.groupby(df["code"]).shift(1)).dt.days.clip(0, 30)
    return df


def build_prediction_frame(hist: pd.DataFrame, future: pd.DataFrame,
                           stats: list[str] = ROLL_STATS,
                           windows: list[int] = WINDOWS,
                           elo: pd.DataFrame | None = None,
                           elo_final: dict | None = None) -> pd.DataFrame:
    """Feature rows for upcoming fixtures, built purely from history.

    ``future``: one row per player per upcoming fixture (code, season_idx,
    gw, opp_code, was_home, team_code, position, kickoff_time). It is
    appended to history with NaN stats, features are computed over the
    combined frame, and only the future rows are returned — so a GW+2 row's
    window skips the NaNs of the GW+1 row ahead of it.
    """
    future = future.copy()
    future["_future"] = True
    hist = hist.copy()
    hist["_future"] = False
    combined = pd.concat([hist, future], ignore_index=True)
    combined = add_player_rolling(combined, stats, windows)
    combined = add_setpiece(combined)
    combined = add_context(combined, elo, elo_final)
    out = combined[combined["_future"]].drop(columns=["_future"])
    return out.reset_index(drop=True)


def feature_columns(stats: list[str] = ROLL_STATS,
                    windows: list[int] = WINDOWS) -> list[str]:
    """Canonical model input columns for the given stats/windows."""
    cols = [f"{s}_r{w}" for s in stats for w in windows]
    return cols + ["team_elo", "opp_elo", "elo_diff", "home", "days_rest",
                   "pen_taker", "setpiece_taker"]
