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

ROTATION_FEATURES = ["season_start_share", "days_since_last_start",
                     "sub_streak"]
MAX_DAYS_SINCE_START = 60
"""Days beyond which "hasn't started recently" stops carrying information.

Past two months the gap is a summer, an injury or a loan spell, and the
model should read them all the same way rather than splitting on the length
of the layoff.
"""


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


def _rotation_state(df: pd.DataFrame) -> dict[str, pd.Series]:
    """The raw parts of the rotation signals, *inclusive* of each row's
    own match.

    Not features — they read the current row's outcome. They describe the
    state a player is in once a match has been played, which is what both
    callers need: :func:`add_rotation` shifts them off the current row
    to build training features, and :func:`latest_rotation` reads the last
    played match's state to broadcast onto future rows.
    """
    code = df["code"]
    nan = pd.Series(float("nan"), index=df.index, dtype="float64")
    starts = (pd.to_numeric(df["starts"], errors="coerce")
              if "starts" in df.columns else nan)
    mins = (pd.to_numeric(df["minutes"], errors="coerce")
            if "minutes" in df.columns else nan)
    kt = (pd.to_datetime(df["kickoff_time"], errors="coerce", utc=True)
          if "kickoff_time" in df.columns
          else pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]"))

    # Share of this season's matches so far that the player started. Grouping
    # by (code, season_idx) is what keeps August from reading May.
    season_key = [code, df["season_idx"]]
    n = starts.notna().astype(int).groupby(season_key).cumsum()
    total = starts.fillna(0.0).groupby(season_key).cumsum()
    share = (total / n).where(n > 0)

    # Kickoff of the most recent start at or before this row.
    last_start_kt = kt.where(starts == 1).groupby(code).ffill()

    # Appearances since the last start. Blocks open at each start, so the
    # within-block appearance rank is the streak: 1 at the start itself
    # (streak 0), 2 at the next appearance (streak 1). Before a player's
    # first start there is no opening start to discount, hence the +1.
    played = (mins > 0)
    blocks = ((starts == 1) & played).astype(int).groupby(code).cumsum()
    rank = played.astype(int).groupby([code, blocks]).cumsum()
    streak = (rank - 1 + (blocks == 0).astype(int)).astype("float64")
    return {"share": share, "last_start_kt": last_start_kt, "kt": kt,
            "streak": streak.where(played)}


def add_rotation(df: pd.DataFrame) -> pd.DataFrame:
    """Rotation features: how a player's *role* has been trending.

    The rolling means in :func:`add_player_rolling` answer this too slowly.
    ``starts_r5`` blends across the season boundary, so a nailed-on starter
    benched in the opener under a new manager still reads ~0.8 — seasons of
    starts against one benching. These three read the current season and the
    recent past on their own terms:

    ``season_start_share``
        mean ``starts`` over this season's earlier matches only. NaN before
        a player's first match of the season.
    ``days_since_last_start``
        days to the previous match the player started, clipped at
        :data:`MAX_DAYS_SINCE_START`. NaN until a first start.
    ``sub_streak``
        consecutive earlier appearances without a start; 0 when the last
        appearance was a start. Matches the player did not appear in are
        skipped rather than counted — an unused substitute says nothing
        about the manager's preference between playing options.

    Same ``shift(1)`` discipline as everything else: nothing from the row's
    own match reaches its features. Columns whose source is absent come out
    all-NaN, which LightGBM splits on natively.
    """
    sort_cols = [c for c in ("code", "season_idx", "gw", "kickoff_time")
                 if c in df.columns]
    df = df.sort_values(sort_cols).reset_index(drop=True)
    st = _rotation_state(df)
    code = df["code"]
    prior_start_kt = st["last_start_kt"].groupby(code).shift(1)
    feats = {
        "season_start_share": st["share"].groupby(
            [code, df["season_idx"]]).shift(1),
        "days_since_last_start": (st["kt"] - prior_start_kt).dt.days
        .clip(0, MAX_DAYS_SINCE_START).astype("float64"),
        "sub_streak": st["streak"].groupby(code).ffill().groupby(code).shift(1),
    }
    return pd.concat([df, pd.DataFrame(feats, index=df.index)], axis=1)


def latest_rotation(hist: pd.DataFrame) -> pd.DataFrame:
    """Each player's as-of-today rotation state, indexed by ``code``.

    The counterpart of :func:`latest_player_rolling` for
    :data:`ROTATION_FEATURES`: the state at the last match played, evaluated
    one row past the end of history. ``days_since_last_start`` is therefore
    measured at that last match rather than at the future kickoff — the same
    choice the form vector makes, and it keeps every future row of a player
    identical, which is the point of the broadcast.

    ``_rot_season_idx`` rides along so the caller can tell whether that state
    belongs to the season being predicted; ``season_start_share`` is
    meaningless across a boundary and must not be carried over one.
    """
    sort_cols = [c for c in ("code", "season_idx", "gw", "kickoff_time")
                 if c in hist.columns]
    h = hist.sort_values(sort_cols)
    st = _rotation_state(h)
    frame = pd.DataFrame({
        "code": h["code"],
        "_rot_season_idx": h["season_idx"],
        "season_start_share": st["share"],
        "days_since_last_start": (st["kt"] - st["last_start_kt"]).dt.days
        .clip(0, MAX_DAYS_SINCE_START).astype("float64"),
        "sub_streak": st["streak"].groupby(h["code"]).ffill(),
    })
    return frame.groupby("code", sort=False).tail(1).set_index("code")


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


def add_setpiece(df: pd.DataFrame) -> pd.DataFrame:
    """``pen_taker`` and ``setpiece_taker`` from the bootstrap order columns.

    The orders only exist on live snapshots, so every historical row carries
    NaN and LightGBM simply ignores the column until live snapshots
    accumulate. An earlier version back-filled ``pen_taker`` on history from
    ``pens_missed`` — a player who missed a penalty demonstrably takes them.
    It measured out as noise: over the real 113k-row history it produced
    1770 non-null values whose ``nunique()`` was 1, a constant-where-present
    column that could only add split noise to the attacking model. Absence
    of evidence stays NaN rather than being manufactured into a feature.

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

    df["pen_taker"] = _order_score(src("penalties_order"))
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


def latest_player_rolling(hist: pd.DataFrame, stats: list[str] = ROLL_STATS,
                          windows: list[int] = WINDOWS) -> pd.DataFrame:
    """Each player's as-of-today form vector, indexed by ``code``.

    The values a next-fixture row would see: window ``w`` is the mean of the
    player's last ``w`` played matches. That is ``shift(1)``-then-roll
    evaluated one row past the end of history, computed here as an unshifted
    roll ending at the last played match — the same window, without needing a
    placeholder row. Players absent from ``hist`` are simply absent here.
    """
    sort_cols = [c for c in ("code", "season_idx", "gw", "kickoff_time")
                 if c in hist.columns]
    h = hist.sort_values(sort_cols)
    codes = h["code"]
    absent = pd.Series(float("nan"), index=h.index, dtype="float64")
    feats: dict[str, pd.Series] = {}
    for stat in stats:
        s = h[stat] if stat in h.columns else absent
        for w in windows:
            feats[f"{stat}_r{w}"] = (
                s.groupby(codes).rolling(w, min_periods=1).mean()
                .reset_index(level=0, drop=True))
    frame = pd.DataFrame(feats, index=h.index)
    frame.insert(0, "code", codes)
    return frame.groupby("code", sort=False).tail(1).set_index("code")


def build_prediction_frame(hist: pd.DataFrame, future: pd.DataFrame,
                           stats: list[str] = ROLL_STATS,
                           windows: list[int] = WINDOWS,
                           elo: pd.DataFrame | None = None,
                           elo_final: dict | None = None) -> pd.DataFrame:
    """Feature rows for upcoming fixtures, built purely from history.

    ``future``: one row per player per upcoming fixture (code, season_idx,
    gw, opp_code, was_home, team_code, position, kickoff_time).

    A prediction made today for GW+3 knows exactly what a prediction for GW+1
    knows — the matches already played — so every future row of a player
    carries the *same* form vector, :func:`latest_player_rolling`. Appending
    the future rows to history and rolling over the lot instead made the
    window slide over the appended NaNs: a GW+2 row's ``_r1`` window held only
    GW+1's NaN and came out NaN, which LightGBM read as a low-minutes player
    and which collapsed ``p_play`` further out the horizon. Only fixture
    context — opponent, home, Elo, rest days, set-piece order — varies per
    future row. A player with no history keeps NaN features.

    Training features are unaffected: :func:`add_player_rolling` still builds
    them over history alone, where every row is a played match.
    """
    future = future.copy()
    future["_future"] = True
    hist = hist.copy()
    hist["_future"] = False
    combined = pd.concat([hist, future], ignore_index=True)
    combined = add_setpiece(combined)
    combined = add_context(combined, elo, elo_final)
    out = combined[combined["_future"]].drop(columns=["_future"])
    out = out.reset_index(drop=True)
    latest = latest_player_rolling(hist, stats, windows)
    rot = latest_rotation(hist).reindex(out["code"]).reset_index(drop=True)
    # A state carried over from an earlier season is not this season's start
    # share — before a player's first match of the new season it is undefined.
    stale = rot["_rot_season_idx"] != out["season_idx"]
    rot.loc[stale, "season_start_share"] = float("nan")
    return pd.concat(
        [out.drop(columns=list(latest.columns) + ROTATION_FEATURES,
                  errors="ignore"),
         latest.reindex(out["code"]).reset_index(drop=True),
         rot.drop(columns=["_rot_season_idx"])], axis=1)


def feature_columns(stats: list[str] = ROLL_STATS,
                    windows: list[int] = WINDOWS) -> list[str]:
    """Canonical model input columns for the given stats/windows."""
    cols = [f"{s}_r{w}" for s in stats for w in windows]
    return cols + ["team_elo", "opp_elo", "elo_diff", "home", "days_rest",
                   "pen_taker", "setpiece_taker"] + ROTATION_FEATURES


US_STATS = ["us_shots", "us_key_passes", "us_npxg", "us_xgchain",
            "us_xgbuildup"]
US_FEATURE_NAMES = {"us_shots": "us_shots90", "us_key_passes": "us_kp90",
                    "us_npxg": "us_npxg90", "us_xgchain": "us_xgchain90",
                    "us_xgbuildup": "us_xgbuildup90"}
US_WINDOWS = [3, 5, 10, 38]

TEAM_US_STATS = ["us_xga", "ppda"]
TEAM_US_WINDOWS = [5, 38]
TEAM_US_FEATURES = [f"{side}_{stat}_r{w}"
                    for side in ("team", "opp")
                    for stat in TEAM_US_STATS
                    for w in TEAM_US_WINDOWS]
"""Own and opponent defensive shape. The opponent's is the attacking signal:
a forward's chances come from how leaky and how passive the defence in front
of him is, which ``opp_us_xga`` and ``opp_ppda`` measure directly and Elo
only summarizes."""


def understat_feature_columns(windows: list[int] = US_WINDOWS) -> list[str]:
    """Every player-level Understat feature name, in a stable order."""
    return [f"{name}_r{w}" for name in US_FEATURE_NAMES.values()
            for w in windows]


def add_understat_rolling(df: pd.DataFrame,
                          windows: list[int] = US_WINDOWS) -> pd.DataFrame:
    """Rolling per-90 Understat rates from past matches only.

    Per-90 rather than per-match: a substitute's four shots in 20 minutes and
    a starter's four in 90 are different players, and a per-match mean calls
    them the same. The rate is ``sum(stat) / sum(minutes) * 90`` over the
    window, both sums taken from the ``shift(1)``-ed series — the identical
    leakage discipline :func:`add_player_rolling` uses, for the identical
    reason.

    A window with no minutes at all yields NaN rather than an infinity;
    LightGBM splits on missing natively and an ``inf`` would propagate into
    a crash. Frames with no Understat columns at all (no parquet on disk, or
    the source disabled) come back with every feature present and empty, so
    the model's feature schema never depends on whether the scrape ran.
    """
    sort_cols = ["code", "season_idx", "gw"]
    if "kickoff_time" in df.columns:
        sort_cols.append("kickoff_time")
    df = df.sort_values(sort_cols).reset_index(drop=True)
    missing = [c for c in US_STATS + ["us_minutes"] if c not in df.columns]
    if missing:
        df = df.assign(**{c: float("nan") for c in missing})
    code = df["code"]
    mins = pd.to_numeric(df["us_minutes"], errors="coerce")
    shifted_mins = mins.groupby(code).shift(1)
    denom = {}
    for w in windows:
        rolled = (shifted_mins.groupby(code).rolling(w, min_periods=1).sum()
                  .reset_index(level=0, drop=True))
        denom[w] = rolled.where(rolled > 0.0)
    feats: dict[str, pd.Series] = {}
    for stat in US_STATS:
        shifted = (pd.to_numeric(df[stat], errors="coerce")
                   .groupby(code).shift(1))
        for w in windows:
            num = (shifted.groupby(code).rolling(w, min_periods=1).sum()
                   .reset_index(level=0, drop=True))
            feats[f"{US_FEATURE_NAMES[stat]}_r{w}"] = num / denom[w] * 90.0
    return pd.concat([df, pd.DataFrame(feats, index=df.index)], axis=1)


def add_understat_team_rolling(
        ut: pd.DataFrame,
        windows: list[int] = TEAM_US_WINDOWS) -> pd.DataFrame:
    """Rolling team xGA and PPDA from a team's past matches only.

    Input is the Understat team parquet: one row per team per match, keyed by
    ``(team_code, date)``. Output adds ``team_<stat>_r<w>`` columns; the
    opponent's copies are attached by :func:`merge_understat_team`, which is
    where the same numbers get read from the other side of the fixture.
    """
    ut = ut.sort_values(["team_code", "date"]).reset_index(drop=True)
    code = ut["team_code"]
    feats: dict[str, pd.Series] = {}
    for stat in TEAM_US_STATS:
        shifted = (pd.to_numeric(ut[stat], errors="coerce")
                   .groupby(code).shift(1))
        for w in windows:
            feats[f"team_{stat}_r{w}"] = (
                shifted.groupby(code).rolling(w, min_periods=1).mean()
                .reset_index(level=0, drop=True))
    return pd.concat([ut, pd.DataFrame(feats, index=ut.index)], axis=1)


def merge_understat_team(df: pd.DataFrame,
                         rolled: pd.DataFrame | None) -> pd.DataFrame:
    """Attach own and opponent team Understat features to player rows.

    Joined on ``(team_code, match date)``, the only key both frames share —
    Understat carries no gameweek number. ``rolled`` of ``None`` (no parquet,
    or the source disabled) still produces every column as all-NaN, which is
    what keeps the model's feature schema stable across that switch.
    """
    out = df.copy()
    own_cols = [f"team_{s}_r{w}" for s in TEAM_US_STATS
                for w in TEAM_US_WINDOWS]
    if rolled is None or rolled.empty:
        for col in TEAM_US_FEATURES:
            out[col] = float("nan")
        return out
    out["_date"] = pd.to_datetime(out["kickoff_time"], errors="coerce",
                                  utc=True).dt.tz_convert(
                                      "Europe/London").dt.date
    keyed = rolled[["team_code", "date"] + own_cols].copy()
    # Both sides have to be plain ``date`` objects: the player frame's key is
    # derived from a timestamp and the parquet's may come back as a string,
    # and a string-vs-date merge matches nothing while looking fine.
    keyed["date"] = pd.to_datetime(keyed["date"], errors="coerce").dt.date
    keyed = keyed.drop_duplicates(subset=["team_code", "date"])
    own = keyed.rename(columns={"date": "_date"})
    out = out.merge(own, on=["team_code", "_date"], how="left",
                    validate="many_to_one")
    opp = keyed.rename(columns={"date": "_date", "team_code": "opp_code",
                                **{c: c.replace("team_", "opp_", 1)
                                   for c in own_cols}})
    out = out.merge(opp, on=["opp_code", "_date"], how="left",
                    validate="many_to_one")
    return out.drop(columns=["_date"])
