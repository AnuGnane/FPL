"""Leakage-safe feature engineering for the canonical ``player_gw`` table.

Every model trains on these columns, so the one invariant that matters is
that a feature for gameweek *t* is computed only from matches strictly
before *t*. ``shift(1)`` before the rolling window enforces that.
"""

from __future__ import annotations

import pandas as pd

from gaffer.data.managers import spell_keys

ROLL_STATS =["total_points", "minutes", "starts", "goals", "assists", "xg",
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

ROTATION_PRIOR_FEATURES = ["tenure_start_share", "manager_tenure_matches",
                           "xi_churn_r5", "started_last_match"]
"""v8a's F1 candidates: how *this* manager has used this player.

:data:`ROTATION_FEATURES` read the season; these read the spell. A nailed-on
starter under the man who was sacked in October is a different bet in
November, and every feature the model currently has blends the two.
"""

TENURE_SHRINK_K = 5.0
"""Prior weight, in matches, for ``tenure_start_share``.

Read as ":data:`SHRINK_K_MODE`, for a shorter denominator". A new manager's
first month is exactly where the player's own record under him is worthless
and the club's own mean is all there is, so the prior is worth five matches
of it — lower than the mode rate's eight because a spell is short by
construction and a k that dominates the whole tenure measures nothing.
"""

MAX_TENURE_MATCHES = 76.0
"""Matches beyond which "settled XI" stops carrying information.

Two seasons. Same reasoning as :data:`MAX_DAYS_SINCE_START`: past that the
number is a tenure length, not a rotation signal, and the model should read
every long reign the same way.
"""

XI_CHURN_WINDOW = 5
"""Club matches the roulette index averages over."""

CONGESTION_FEATURES = ["days_since_last_match", "days_to_next_match",
                       "matches_last_14d"]
CONGESTION_WINDOW_DAYS = 14
MAX_CONGESTION_GAP = 30
"""Days beyond which a gap either side of a match stops meaning anything.

Same reasoning as :data:`MAX_DAYS_SINCE_START` and the existing ``days_rest``
clip: past a month the gap is an international break, a winter break or an
injury, and the model should read them all the same way.
"""

LEAGUE_CONGESTION_PREFIX = "lg_"
LEAGUE_CONGESTION_FEATURES = [LEAGUE_CONGESTION_PREFIX + c
                              for c in CONGESTION_FEATURES]
"""v8a F2 arm A: the same three numbers, league fixtures only.

v5's gate N1 withdrew :data:`CONGESTION_FEATURES` because the cup archive
began in 2025-26 and the feature was therefore partly a season indicator
(``models/train.py``'s ``MINUTES_FEATURES`` docstring records the numbers).
League kickoffs are 100% populated from 2022-23 onward, so this variant has no
confound to be accused of. It carries its own names rather than replacing the
originals so that both can sit in one frame and the gate can attribute the
difference to one arm at a time.
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


def _xi_churn(spell: pd.Series, kt: pd.Series, code: pd.Series,
              starts: pd.Series) -> pd.Series:
    """Mean starting-XI changes over the last five club matches before this.

    The roulette index. A club match is ``(spell, kickoff)`` rather than a
    gameweek: a double gameweek is two team sheets and a slot key would merge
    them into one impossible XI of twenty-two.

    Strictly past, twice over. A match's value is read *before* its own change
    is folded in, so match ``t`` sees only changes into matches ``t-1`` and
    earlier; and a match whose XI is empty — a future probe row, a club-week
    with no ``starts`` recorded — is scored but never becomes a comparison
    point, so a hole in the data cannot manufacture eleven changes.
    """
    xi: dict[tuple, set] = {}
    for s, when, c, st in zip(spell, kt, code, starts):
        if not s or pd.isna(when):
            continue
        bucket = xi.setdefault((s, when), set())
        if st == 1:
            bucket.add(c)
    churn: dict[tuple, float] = {}
    per_spell: dict[str, list] = {}
    for key in sorted(xi, key=lambda k: (k[0], k[1])):
        per_spell.setdefault(key[0], []).append(key[1])
    for s, whens in per_spell.items():
        recent: list[float] = []
        prev: set | None = None
        for when in whens:
            window = recent[-XI_CHURN_WINDOW:]
            churn[(s, when)] = (sum(window) / len(window) if window
                                else float("nan"))
            now = xi[(s, when)]
            if not now:
                continue
            if prev:
                recent.append(float(len(now - prev)))
            prev = now
    return pd.Series(
        [churn.get((s, when), float("nan")) if s and pd.notna(when)
         else float("nan") for s, when in zip(spell, kt)],
        index=spell.index, dtype="float64")


def add_rotation_priors(df: pd.DataFrame,
                        tenures: pd.DataFrame | None = None) -> pd.DataFrame:
    """v8a F1: rotation signals scoped to the *manager*, not the season.

    ``tenure_start_share``
        the player's share of the club's matches under this manager that he
        started, shrunk toward the club's own mean start share over the same
        matches with a :data:`TENURE_SHRINK_K` prior. NaN before the spell has
        any earlier match at all.
    ``manager_tenure_matches``
        club matches the manager has taken before this one, capped at
        :data:`MAX_TENURE_MATCHES`. Zero on his first.
    ``xi_churn_r5``
        the club's roulette index — see :func:`_xi_churn`.
    ``started_last_match``
        did the player start his own previous match. Read off his own rows
        rather than the club's calendar, because a player with no row for a
        match was not in the squad and "the club's previous match" is only
        ever a proxy for the question the trees want: was he in the XI last
        time out. Its interaction with the churn index is the point — high
        churn *and* started-last-match is elevated rest risk.

    Every window is strictly past, by construction rather than by ``shift``:
    a cumulative sum minus the row's own contribution cannot leak whatever a
    double gameweek does to the sort order. ``tenures`` of ``None`` scopes
    every window to the club's season instead (see
    :func:`gaffer.data.managers.spell_keys`), which is the documented
    degradation and not an error.
    """
    sort_cols = [c for c in ("code", "season_idx", "gw", "kickoff_time")
                 if c in df.columns]
    out = df.sort_values(sort_cols, kind="stable").reset_index(drop=True)
    if not {"code", "team_code", "starts", "season_idx"} <= set(out.columns):
        for col in ROTATION_PRIOR_FEATURES:
            out[col] = float("nan")
        return out

    kt = (pd.to_datetime(out["kickoff_time"], errors="coerce", utc=True)
          if "kickoff_time" in out.columns
          else pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns, UTC]"))
    spell = spell_keys(out["team_code"], kt, out["season_idx"], tenures)
    starts = pd.to_numeric(out["starts"], errors="coerce")
    code = out["code"]

    # The player's own record under the spell, this match excluded.
    seen = starts.notna().astype("float64")
    own_n = seen.groupby([code, spell]).cumsum() - seen
    own_starts = (starts.fillna(0.0).groupby([code, spell]).cumsum()
                  - starts.fillna(0.0))

    # The club's record under the spell, this *match* excluded — accumulated
    # per (spell, kickoff) rather than per row, because a row's own teammates
    # play the same match and a row-wise cumsum would read them.
    match = pd.DataFrame({"spell": spell, "when": kt,
                          "starts": starts.fillna(0.0), "rows": seen})
    agg = (match.groupby(["spell", "when"], as_index=False, dropna=False)
           [["starts", "rows"]].sum().sort_values(["spell", "when"]))
    g = agg.groupby("spell")
    before_starts = g["starts"].cumsum() - agg["starts"]
    before_rows = g["rows"].cumsum() - agg["rows"]
    club_share = before_starts / before_rows.where(before_rows > 0)
    played_before = g.cumcount().astype("float64")
    share_of = dict(zip(zip(agg["spell"], agg["when"]), club_share))
    count_of = dict(zip(zip(agg["spell"], agg["when"]), played_before))
    keys = list(zip(spell, kt))
    prior = pd.Series([share_of.get(k, float("nan")) for k in keys],
                      index=out.index, dtype="float64")
    tenure_matches = pd.Series([count_of.get(k, float("nan")) for k in keys],
                               index=out.index, dtype="float64")

    feats = {
        "tenure_start_share": ((own_starts + TENURE_SHRINK_K * prior)
                               / (own_n + TENURE_SHRINK_K)),
        "manager_tenure_matches": tenure_matches.clip(0.0,
                                                      MAX_TENURE_MATCHES),
        "xi_churn_r5": _xi_churn(spell, kt, code, starts),
        "started_last_match": starts.groupby(code).shift(1),
    }
    for col, values in feats.items():
        out[col] = values.astype("float64")
    return out


def latest_rotation_priors(hist: pd.DataFrame,
                           tenures: pd.DataFrame | None = None,
                           when=None) -> pd.DataFrame:
    """Each player's as-of-today rotation-prior state, indexed by ``code``.

    Built by appending one *probe* row per player to history and running
    :func:`add_rotation_priors` over the lot, rather than by restating the
    arithmetic with the exclusions turned off. The probe is a match that has
    not been played — no ``starts``, a kickoff one day past the end of
    history — so "strictly before the probe" is exactly "all of history",
    which is the as-of-end contract every other ``latest_*`` keeps. Sharing
    the code path is what makes train/serve skew impossible here rather than
    merely unlikely.

    ``_prior_spell`` rides along so the caller can tell whether the state
    belongs to the manager who will pick the future team;
    :func:`build_prediction_frame` blanks what a change of manager invalidates.
    """
    cols = ["code"] + ROTATION_PRIOR_FEATURES + ["_prior_spell"]
    if not {"code", "team_code", "season_idx"} <= set(hist.columns):
        return pd.DataFrame(columns=cols).set_index("code")
    sort_cols = [c for c in ("code", "season_idx", "gw", "kickoff_time")
                 if c in hist.columns]
    h = hist.sort_values(sort_cols, kind="stable").reset_index(drop=True)
    kt = (pd.to_datetime(h["kickoff_time"], errors="coerce", utc=True)
          if "kickoff_time" in h.columns
          else pd.Series(pd.NaT, index=h.index, dtype="datetime64[ns, UTC]"))
    stamp = when if when is not None else (
        kt.max() + pd.Timedelta(days=1) if kt.notna().any() else pd.NaT)
    tail = h.groupby("code", sort=False).tail(1)
    probe = pd.DataFrame({
        "code": tail["code"].to_numpy(),
        "team_code": tail["team_code"].to_numpy(),
        "season_idx": tail["season_idx"].to_numpy(),
        "gw": pd.to_numeric(tail["gw"], errors="coerce").to_numpy(),
        "kickoff_time": stamp,
        "starts": float("nan")})
    both = add_rotation_priors(
        pd.concat([h.assign(_probe=False), probe.assign(_probe=True)],
                  ignore_index=True), tenures)
    out = both[both["_probe"].fillna(False).astype(bool)].copy()
    out["_prior_spell"] = spell_keys(
        out["team_code"],
        pd.Series(stamp, index=out.index),
        out["season_idx"], tenures).to_numpy()
    return out[cols].groupby("code", sort=False).tail(1).set_index("code")


def add_congestion(df: pd.DataFrame,
                   cups: pd.DataFrame | None = None,
                   prefix: str = "") -> pd.DataFrame:
    """Fixture-congestion features: the gaps either side, and the recent load.

    ``days_since_last_match``
        days back to the player's previous match, clipped at
        :data:`MAX_CONGESTION_GAP`. NaN for a first match.
    ``days_to_next_match``
        days forward to his next, same clip. NaN for the last match in the
        frame. Forward-looking and *not* leakage: the fixture calendar is
        published weeks before the deadline, so a Saturday prediction knows
        perfectly well that a Tuesday tie follows. What it must not know is
        the *result*, and no result is read here.
    ``matches_last_14d``
        matches in the :data:`CONGESTION_WINDOW_DAYS` days strictly before
        this one — the player's own league matches, plus his club's cup and
        European ties from :func:`gaffer.data.cups.load_cup_matches`. The
        row's own match is excluded, the same ``shift(1)`` discipline
        everything else in this module keeps.

    ``cups`` of ``None`` means no cup frame is available on this machine, and
    the count falls back to league matches alone. That is a number, not a NaN,
    on purpose: the column has to mean the same thing in training and at serve
    time, and a machine without the ingest must not see a differently-shaped
    feature from one with it.

    ``prefix`` renames all three outputs, which is how v8a's two arms coexist
    in one frame: ``prefix=""`` with a cup frame is arm B, ``prefix="lg_"``
    with ``cups=None`` is arm A, and calling it twice adds six columns rather
    than overwriting three.
    """
    sort_cols = [c for c in ("code", "season_idx", "gw", "kickoff_time")
                 if c in df.columns]
    # Stable, because a double gameweek ties on every sort column and the
    # 14-day scan below reads the rows in the order it is handed them.
    out = df.sort_values(sort_cols, kind="stable").reset_index(drop=True)
    names = [prefix + c for c in CONGESTION_FEATURES]
    if "kickoff_time" not in out.columns:
        for col in names:
            out[col] = float("nan")
        return out
    kt = pd.to_datetime(out["kickoff_time"], errors="coerce", utc=True)
    code = out["code"]
    prev = kt.groupby(code).shift(1)
    nxt = kt.groupby(code).shift(-1)
    out[names[0]] = ((kt - prev).dt.days
                     .clip(0, MAX_CONGESTION_GAP).astype("float64"))
    out[names[1]] = ((nxt - kt).dt.days
                     .clip(0, MAX_CONGESTION_GAP).astype("float64"))
    out[names[2]] = _recent_load(out, kt, cups)
    return out


def _recent_load(df: pd.DataFrame, kt: pd.Series,
                 cups: pd.DataFrame | None) -> pd.Series:
    """Matches in the 14 days strictly before each row's kickoff.

    Counted per player for league matches (a benched squad member did travel,
    which is why appearance is not required) and per *club* for cup ties,
    because the cup files carry no player rows and a club's midweek tie is a
    squad-level event either way.

    Written as an explicit per-row scan over the player's own timestamps
    rather than a rolling window: a double gameweek puts two matches in one
    ``gw`` and a time-based roll over a duplicated key silently double-counts.
    """
    days = pd.Timedelta(days=CONGESTION_WINDOW_DAYS)
    own = pd.Series(0.0, index=df.index, dtype="float64")
    for _, idx in df.groupby(df["code"], sort=False).groups.items():
        stamps = kt.loc[idx].to_numpy()
        for pos, when in zip(idx, stamps):
            if pd.isna(when):
                continue
            earlier = stamps[(stamps < when) & (stamps >= when - days)]
            own.loc[pos] = float(len(earlier))
    if cups is None or cups.empty or "team_code" not in df.columns:
        return own
    by_club: dict[int, list] = {}
    dates = pd.to_datetime(cups["date"], errors="coerce", utc=True)
    for team, when in zip(pd.to_numeric(cups["team_code"], errors="coerce"),
                          dates):
        if pd.notna(team) and pd.notna(when):
            by_club.setdefault(int(team), []).append(when)
    extra = pd.Series(0.0, index=df.index, dtype="float64")
    clubs = pd.to_numeric(df["team_code"], errors="coerce")
    for pos, (club, when) in enumerate(zip(clubs, kt)):
        if pd.isna(club) or pd.isna(when):
            continue
        ties = by_club.get(int(club), ())
        idx = df.index[pos]
        extra.loc[idx] = float(sum(1 for t in ties
                                   if when - days <= t < when))
    return own + extra


def latest_congestion(hist: pd.DataFrame, future: pd.DataFrame,
                      cups: pd.DataFrame | None = None,
                      prefix: str = "") -> pd.DataFrame:
    """Congestion for future rows, built from history plus the calendar.

    Unlike the form vectors, this is *not* a broadcast of one as-of-today
    state: every future fixture has its own date, so every future row has its
    own gaps and its own 14-day load. History and future are therefore
    concatenated and run through :func:`add_congestion` together, which is the
    same trick :func:`add_context` already uses for ``days_rest``.
    """
    hist = hist.copy()
    hist["_future"] = False
    future = future.copy()
    future["_future"] = True
    both = add_congestion(pd.concat([hist, future], ignore_index=True), cups,
                          prefix)
    out = both[both["_future"]].drop(columns=["_future"])
    return out.reset_index(drop=True)


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
                           elo_final: dict | None = None,
                           understat_team: pd.DataFrame | None = None,
                           cups: pd.DataFrame | None = None,
                           tenures: pd.DataFrame | None = None
                           ) -> pd.DataFrame:
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
    # Congestion is per-fixture, not a broadcast: each future row has its own
    # date, so it is rebuilt over history+future rather than tailed. Both v8a
    # arms are rebuilt, so the two candidate column sets are populated
    # identically in training and at serve time whichever the model uses.
    cong = latest_congestion(hist, future, cups)[CONGESTION_FEATURES]
    lg = latest_congestion(hist, future, None,
                           LEAGUE_CONGESTION_PREFIX)[LEAGUE_CONGESTION_FEATURES]
    out = out.drop(columns=CONGESTION_FEATURES + LEAGUE_CONGESTION_FEATURES,
                   errors="ignore")
    out = pd.concat([out, cong.reset_index(drop=True),
                     lg.reset_index(drop=True)], axis=1)
    latest = latest_player_rolling(hist, stats, windows)
    rot = latest_rotation(hist).reindex(out["code"]).reset_index(drop=True)
    # A state carried over from an earlier season is not this season's start
    # share — before a player's first match of the new season it is undefined.
    stale = rot["_rot_season_idx"] != out["season_idx"]
    rot.loc[stale, "season_start_share"] = float("nan")
    # v8a F1. The asset is loaded here rather than passed by every caller:
    # ``advise`` builds this frame and must not have to know about a file it
    # is allowed to be missing. ``None`` is the club-season degradation.
    if tenures is None:
        from gaffer.data.managers import load_manager_tenures
        tenures = load_manager_tenures()
    if "team_code" in out.columns:
        pri = (latest_rotation_priors(hist, tenures)
               .reindex(out["code"]).reset_index(drop=True))
        now_spell = spell_keys(
            out["team_code"],
            out["kickoff_time"] if "kickoff_time" in out.columns
            else pd.Series(pd.NaT, index=out.index),
            out["season_idx"], tenures)
        # A state measured under the outgoing manager is not evidence about
        # the incoming one's team sheet: the share and the roulette index
        # describe a squad nobody has picked yet, and the counter genuinely
        # restarts at zero.
        fresh_boss = pri["_prior_spell"].to_numpy() != now_spell.to_numpy()
        pri.loc[fresh_boss, "tenure_start_share"] = float("nan")
        pri.loc[fresh_boss, "xi_churn_r5"] = float("nan")
        pri.loc[fresh_boss, "manager_tenure_matches"] = 0.0
        pri = pri.drop(columns=["_prior_spell"])
    else:
        # No club on the rows: no spell can be named, and the columns degrade
        # to all-NaN exactly as they do inside the builder itself.
        pri = pd.DataFrame({c: float("nan") for c in ROTATION_PRIOR_FEATURES},
                           index=out.index)
    us = latest_understat_rolling(hist, US_WINDOWS)
    shrunk = latest_shrunken_rates(hist)
    modes = latest_shrunken_modes(hist)
    frame = pd.concat(
        [out.drop(columns=list(latest.columns) + ROTATION_FEATURES
                  + ROTATION_PRIOR_FEATURES
                  + list(us.columns) + SHRUNK_FEATURES
                  + SHRUNK_MODE_FEATURES, errors="ignore"),
         latest.reindex(out["code"]).reset_index(drop=True),
         rot.drop(columns=["_rot_season_idx"]),
         pri,
         us.reindex(out["code"]).reset_index(drop=True),
         shrunk.reindex(out["code"]).reset_index(drop=True),
         modes.reindex(out["code"]).reset_index(drop=True)], axis=1)
    return merge_understat_team(
        frame.drop(columns=TEAM_US_FEATURES, errors="ignore"),
        understat_team,
        latest_understat_team(understat_team)
        if understat_team is not None and not understat_team.empty else None)


def feature_columns(stats: list[str] = ROLL_STATS,
                    windows: list[int] = WINDOWS) -> list[str]:
    """Canonical model input columns for the given stats/windows.

    Everything a caller has to strip off a history frame before re-deriving
    features over it — which is why the Understat, team-Understat and
    shrunken-rate blocks belong here too, not only the rolling means.
    """
    cols = [f"{s}_r{w}" for s in stats for w in windows]
    return (cols + ["team_elo", "opp_elo", "elo_diff", "home", "days_rest",
                    "pen_taker", "setpiece_taker"] + ROTATION_FEATURES
            + ROTATION_PRIOR_FEATURES
            + CONGESTION_FEATURES + LEAGUE_CONGESTION_FEATURES
            + understat_feature_columns() + TEAM_US_FEATURES
            + SHRUNK_FEATURES + SHRUNK_MODE_FEATURES)


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


def merge_understat_team(df: pd.DataFrame, rolled: pd.DataFrame | None,
                         latest: pd.DataFrame | None = None) -> pd.DataFrame:
    """Attach own and opponent team Understat features to player rows.

    Joined on ``(team_code, match date)``, the only key both frames share —
    Understat carries no gameweek number. ``rolled`` of ``None`` (no parquet,
    or the source disabled) still produces every column as all-NaN, which is
    what keeps the model's feature schema stable across that switch.

    ``latest`` (from :func:`latest_understat_team`) fills rows the date join
    could not match — every *future* fixture, which by definition has no
    Understat row. Without it these columns would be populated in training
    and empty at serve time, which is the train/serve skew this codebase
    goes out of its way to avoid.
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
    # Frames off the simple component path carry no ``opp_code``; the own
    # side still joins, and the opponent's columns stay NaN rather than
    # taking the whole merge down with a KeyError.
    has_opp = "opp_code" in out.columns
    if has_opp:
        opp = keyed.rename(columns={"date": "_date", "team_code": "opp_code",
                                    **{c: c.replace("team_", "opp_", 1)
                                       for c in own_cols}})
        out = out.merge(opp, on=["opp_code", "_date"], how="left",
                        validate="many_to_one")
    else:
        for col in own_cols:
            out[col.replace("team_", "opp_", 1)] = float("nan")
    if latest is not None and not latest.empty:
        for col in [f"team_{s}_r{w}" for s in TEAM_US_STATS
                    for w in TEAM_US_WINDOWS]:
            opp_col = col.replace("team_", "opp_", 1)
            out[col] = out[col].fillna(out["team_code"].map(latest[col]))
            if has_opp:
                out[opp_col] = out[opp_col].fillna(
                    out["opp_code"].map(latest[col]))
    return out.drop(columns=["_date"])


SHRINK_K = 20.0
"""Prior weight, in nineties, for the empirical-Bayes rates.

``k`` is literally "how many matches of league-average evidence the prior is
worth". Chosen by out-of-sample correlation against held-out goals-per-90 on
the last ten gameweek slots over the grid {2, 5, 10, 20} — see the v4b
spec's Outcome table. Twenty is the grid's heavy-shrinkage end: individual
scoring rates are noisy enough that the position-by-club prior deserves
roughly half a season's benefit of the doubt.
"""

SHRINK_K_GRID = [2.0, 5.0, 10.0, 20.0]
SHRUNK_FEATURES = ["shrunk_goals90", "shrunk_assists90"]

SHRINK_K_MODE = 8.0
"""Prior weight, in *matches*, for the mode rates.

Read the same way :data:`SHRINK_K` is: "how many matches of position-by-club
evidence the prior is worth". Lower than the goals-rate k because the quantity
is far less noisy — whether a man started is observed exactly, where whether
he was going to score is a coin flip on a small number — so his own record
earns its weight back in a handful of matches rather than half a season.
Chosen off :func:`best_mode_shrinkage_k` on the last ten gameweek slots over
the grid {2, 4, 8, 16}, the same offline procedure and the same pinning
convention v4b used for ``SHRINK_K = 20``.
"""

SHRINK_K_MODE_GRID = [2.0, 4.0, 8.0, 16.0]
SHRUNK_MODE_FEATURES = ["shrunk_start_rate", "shrunk_min_per_app"]


def _shrunk_ratio(df: pd.DataFrame, val: pd.Series, den: pd.Series,
                  k: float, as_of_end: bool = False) -> pd.Series:
    """``(sum val + k * prior) / (sum den + k)``, all sums leakage-free.

    The generalisation of :func:`_shrunk_rate` over the *denominator*: v4b's
    rates are per-ninety, but a start rate is per-match and a
    minutes-per-appearance is per-appearance, and all three are the same
    empirical-Bayes estimator with a different unit of exposure.

    The player's own record is ``shift(1)`` then ``cumsum`` within his own
    rows, whose order is chronological inside each code group. The
    position-by-club prior CANNOT be built the same way: the frame is sorted
    by *player*, not by time, so a per-row cumsum over the (position, club)
    group would fold in other players' future matches — and teammates share
    fixtures, so even a time-sorted row cumsum would leak the current match's
    own result through the teammate's row. The prior is therefore accumulated
    at gameweek-slot granularity: per-(position, club, slot) totals, cumsummed
    over slots with the current slot subtracted out, so a row's prior contains
    strictly-earlier gameweeks only.

    ``as_of_end`` drops both exclusions — no ``shift(1)`` on the player's own
    sums, no current-slot subtraction on the prior — so a row's value counts
    its own match too. That is wrong for a *training* row, whose window may
    only see matches strictly before it, and right for the as-of-end-of-
    history broadcast onto a future fixture, where every played match is
    legal evidence.
    """
    code = df["code"]
    val = val.astype("float64").fillna(0.0)
    den = den.astype("float64").fillna(0.0)

    if as_of_end:
        own_val = val.groupby(code).cumsum()
        own_den = den.groupby(code).cumsum()
    else:
        own_val = val.groupby(code).shift(1).fillna(0.0).groupby(code).cumsum()
        own_den = den.groupby(code).shift(1).fillna(0.0).groupby(code).cumsum()

    slots = pd.DataFrame({
        "pos": df["position"].to_numpy(),
        "team": df["team_code"].to_numpy(),
        # gw <= 38, so *100 keeps (season, gw) ordered in one integer key.
        "slot": (pd.to_numeric(df["season_idx"]).astype(int) * 100
                 + pd.to_numeric(df["gw"]).astype(int)).to_numpy(),
        "val": val.to_numpy(), "den": den.to_numpy()})
    agg = (slots.groupby(["pos", "team", "slot"], as_index=False)
           [["val", "den"]].sum().sort_values(["pos", "team", "slot"]))
    g = agg.groupby(["pos", "team"])
    # cumsum minus the current slot's own total == everything strictly before.
    before_val = g["val"].cumsum() - (0.0 if as_of_end else agg["val"])
    before_den = g["den"].cumsum() - (0.0 if as_of_end else agg["den"])
    prior_rate = before_val / before_den.where(before_den > 0.0)
    lookup = dict(zip(zip(agg["pos"], agg["team"], agg["slot"]), prior_rate))
    prior = pd.Series(
        [lookup[key] for key in zip(slots["pos"], slots["team"],
                                    slots["slot"])],
        index=df.index, dtype="float64")
    return (own_val + k * prior) / (own_den + k)


def _shrunk_rate(df: pd.DataFrame, stat: str, k: float,
                 as_of_end: bool = False) -> pd.Series:
    """``(sum stat + k * prior) / (sum nineties + k)``, all sums leakage-free.

    The player's own record is ``shift(1)`` then ``cumsum`` within his own
    rows, whose order is chronological inside each code group. The
    position-by-club prior CANNOT be built the same way: the frame is sorted
    by *player*, not by time, so a per-row cumsum over the (position, club)
    group would fold in other players' future matches — and teammates share
    fixtures, so even a time-sorted row cumsum would leak the current match's
    own result through the teammate's row. The prior is therefore accumulated
    at gameweek-slot granularity: per-(position, club, slot) totals, cumsummed
    over slots with the current slot subtracted out, so a row's prior contains
    strictly-earlier gameweeks only.

    ``as_of_end`` drops both exclusions — no ``shift(1)`` on the player's own
    sums, no current-slot subtraction on the prior — so a row's value counts
    its own match too. That is wrong for a *training* row, whose window may
    only see matches strictly before it, and right for the as-of-end-of-
    history broadcast onto a future fixture, where every played match is
    legal evidence. Only :func:`latest_shrunken_rates` passes it.

    See :func:`_shrunk_ratio` for the mechanics.
    """
    return _shrunk_ratio(
        df,
        pd.to_numeric(df[stat], errors="coerce").fillna(0.0),
        pd.to_numeric(df["minutes"], errors="coerce").fillna(0.0) / 90.0,
        k, as_of_end)


def add_shrunken_rates(df: pd.DataFrame,
                       k: float = SHRINK_K) -> pd.DataFrame:
    """``shrunk_goals90`` and ``shrunk_assists90``.

    A rolling mean over five matches is a terrible estimate of a rate when
    only three matches exist, and August is full of those. Shrinking toward
    the position-by-club prior gives a sensible number from the first
    gameweek and converges on the player's own record as he plays — the
    standard empirical-Bayes trade, applied to the two rates the attacking
    heads care about most.

    Rows before the prior has any evidence at all come back NaN, which
    LightGBM splits on natively.
    """
    sort_cols = [c for c in ("code", "season_idx", "gw", "kickoff_time")
                 if c in df.columns]
    out = df.sort_values(sort_cols).reset_index(drop=True)
    for stat, col in (("goals", "shrunk_goals90"),
                      ("assists", "shrunk_assists90")):
        if stat in out.columns:
            out[col] = _shrunk_rate(out, stat, k)
        else:
            out[col] = float("nan")
    return out


def add_shrunken_modes(df: pd.DataFrame,
                       k: float = SHRINK_K_MODE) -> pd.DataFrame:
    """``shrunk_start_rate`` and ``shrunk_min_per_app``.

    The two numbers the three-mode model most wants and the rolling means are
    worst at. ``starts_r5`` over three matches of a new signing is a third,
    two thirds or one, and none of those is an estimate of anything;
    shrinking toward the position-by-club prior gives a usable number from
    the first gameweek and converges on his own record as he plays.

    The denominators are what makes them different from
    :func:`add_shrunken_rates`. The start rate is per *match in the squad* —
    every row counts, because being left out is exactly the signal. The
    minutes rate is per *appearance* — a DNP is not a zero-minute cameo, and
    counting it as one reads a rotated-out starter as a 20-minute substitute.

    Rows before the prior has any evidence at all come back NaN, which
    LightGBM splits on natively.
    """
    sort_cols = [c for c in ("code", "season_idx", "gw", "kickoff_time")
                 if c in df.columns]
    out = df.sort_values(sort_cols).reset_index(drop=True)
    for col, val, den in _mode_rate_parts(out):
        out[col] = (_shrunk_ratio(out, val, den, k) if val is not None
                    else float("nan"))
    return out


def _mode_rate_parts(df: pd.DataFrame):
    """``(column, numerator, denominator)`` for each mode rate.

    One place defines what the two rates are made of, so
    :func:`add_shrunken_modes` and :func:`latest_shrunken_modes` cannot drift
    apart — the train/serve skew this module keeps repeating itself about.
    """
    ones = pd.Series(1.0, index=df.index, dtype="float64")
    # The prior keys are part of the requirement, not just the numerators:
    # _shrunk_ratio accumulates position-by-club totals per gameweek slot, so
    # a frame without them yields the all-NaN column the module's convention
    # gives any feature whose source is absent.
    needed = {"starts", "minutes", "position", "team_code", "season_idx", "gw"}
    if needed <= set(df.columns):
        mins = pd.to_numeric(df["minutes"], errors="coerce").fillna(0.0)
        starts = pd.to_numeric(df["starts"], errors="coerce")
        # A missing ``starts`` (a season the feed predates) is inferred from
        # the minutes rather than dropped: 60+ is a start in all but a
        # handful of cases, and a hole here would blank the feature for a
        # whole season.
        starts = starts.fillna((mins >= 60).astype("float64"))
        played = (mins > 0).astype("float64")
        yield "shrunk_start_rate", starts, ones
        yield "shrunk_min_per_app", mins, played
    else:
        yield "shrunk_start_rate", None, None
        yield "shrunk_min_per_app", None, None


def latest_understat_rolling(hist: pd.DataFrame,
                             windows: list[int] = US_WINDOWS) -> pd.DataFrame:
    """Each player's as-of-today Understat per-90 vector, indexed by ``code``.

    The counterpart of :func:`latest_player_rolling`: an unshifted roll
    ending at the last played match is the same window a next-fixture row's
    ``shift(1)``-then-roll would produce, without needing a placeholder row.
    """
    sort_cols = [c for c in ("code", "season_idx", "gw", "kickoff_time")
                 if c in hist.columns]
    h = hist.sort_values(sort_cols)
    for col in US_STATS + ["us_minutes"]:
        if col not in h.columns:
            h = h.assign(**{col: float("nan")})
    codes = h["code"]
    mins = pd.to_numeric(h["us_minutes"], errors="coerce")
    denom = {}
    for w in windows:
        rolled = (mins.groupby(codes).rolling(w, min_periods=1).sum()
                  .reset_index(level=0, drop=True))
        denom[w] = rolled.where(rolled > 0.0)
    feats: dict[str, pd.Series] = {}
    for stat in US_STATS:
        s = pd.to_numeric(h[stat], errors="coerce")
        for w in windows:
            num = (s.groupby(codes).rolling(w, min_periods=1).sum()
                   .reset_index(level=0, drop=True))
            feats[f"{US_FEATURE_NAMES[stat]}_r{w}"] = num / denom[w] * 90.0
    frame = pd.DataFrame(feats, index=h.index)
    frame.insert(0, "code", codes)
    return frame.groupby("code", sort=False).tail(1).set_index("code")


def latest_shrunken_rates(hist: pd.DataFrame,
                          k: float = SHRINK_K) -> pd.DataFrame:
    """Each player's as-of-today shrunken rates, indexed by ``code``.

    The value a hypothetical next fixture would carry, which means it
    *includes the last played match* — the same contract
    :func:`latest_player_rolling`, :func:`latest_understat_rolling` and
    :func:`latest_understat_team` all keep. The stored training column
    cannot supply it: ``add_shrunken_rates`` excludes each row's own match by
    construction, so tailing it would serve a vector one match stale, with a
    final-matchday hat-trick reaching the model a week late. The rates are
    therefore recomputed here with the exclusions off.
    """
    sort_cols = [c for c in ("code", "season_idx", "gw", "kickoff_time")
                 if c in hist.columns]
    h = hist.sort_values(sort_cols).reset_index(drop=True)
    out = pd.DataFrame({"code": h["code"]})
    for stat, col in (("goals", "shrunk_goals90"),
                      ("assists", "shrunk_assists90")):
        out[col] = (_shrunk_rate(h, stat, k, as_of_end=True)
                    if stat in h.columns else float("nan"))
    return out.groupby("code", sort=False).tail(1).set_index("code")


def latest_shrunken_modes(hist: pd.DataFrame,
                          k: float = SHRINK_K_MODE) -> pd.DataFrame:
    """Each player's as-of-today mode rates, indexed by ``code``.

    The same as-of-end contract :func:`latest_shrunken_rates` keeps and for
    the same reason: the stored training column excludes each row's own match
    by construction, so tailing it would serve a vector one match stale — a
    debut start reaching the model a week late.
    """
    sort_cols = [c for c in ("code", "season_idx", "gw", "kickoff_time")
                 if c in hist.columns]
    h = hist.sort_values(sort_cols).reset_index(drop=True)
    out = pd.DataFrame({"code": h["code"]})
    for col, val, den in _mode_rate_parts(h):
        out[col] = (_shrunk_ratio(h, val, den, k, as_of_end=True)
                    if val is not None else float("nan"))
    return out.groupby("code", sort=False).tail(1).set_index("code")


def latest_understat_team(rolled: pd.DataFrame,
                          windows: list[int] = TEAM_US_WINDOWS
                          ) -> pd.DataFrame:
    """Each club's as-of-today team-level Understat vector, by team code.

    The Elo pattern: a future fixture has no row of its own, so it inherits
    the club's latest state. That state *includes the last played match* —
    the same convention :func:`latest_understat_rolling` follows for players,
    and the reason both recompute an unshifted roll rather than tailing the
    ``shift(1)``-ed training frame.

    The distinction is the whole train/serve contract. A training row at slot
    ``t`` may only see matches strictly before ``t``, which is what the
    shifted roll in :func:`add_understat_team_rolling` enforces. A future
    fixture is not at any played slot: everything already played is legal
    evidence, so tailing the shifted frame would hand the model a vector one
    match stale — populated differently in training and at serve time, which
    is exactly the skew the broadcast exists to prevent.
    """
    own_cols = [f"team_{s}_r{w}" for s in TEAM_US_STATS for w in windows]
    frame = rolled.sort_values(["team_code", "date"])
    codes = frame["team_code"]
    feats: dict[str, pd.Series] = {}
    for stat in TEAM_US_STATS:
        vals = pd.to_numeric(frame[stat], errors="coerce")
        for w in windows:
            feats[f"team_{stat}_r{w}"] = (
                vals.groupby(codes).rolling(w, min_periods=1).mean()
                .reset_index(level=0, drop=True))
    out = pd.DataFrame(feats, index=frame.index)[own_cols]
    out.insert(0, "team_code", codes)
    return out.groupby("team_code", sort=False).tail(1).set_index("team_code")



def best_shrinkage_k(df: pd.DataFrame, k_grid: list[float] = SHRINK_K_GRID,
                     holdout_slots: int = 10) -> float:
    """The ``k`` whose shrunken goals rate best predicts held-out goals.

    Scored by correlation against the *actual* goals-per-90 on the last
    ``holdout_slots`` gameweek slots, with the rates themselves built from
    earlier rows only — so this is a genuine out-of-sample choice and not a
    fit of the fit. A frame too short to hold anything out returns
    :data:`SHRINK_K` rather than pretending to have measured something.
    """
    slots = (df[["season_idx", "gw"]].drop_duplicates()
             .sort_values(["season_idx", "gw"]))
    if len(slots) <= holdout_slots:
        return SHRINK_K
    bs, bg = slots.iloc[-holdout_slots][["season_idx", "gw"]]
    best_k, best_score = SHRINK_K, -2.0
    for k in k_grid:
        rated = add_shrunken_rates(df, k=k)
        hold = rated[(rated["season_idx"] > bs)
                     | ((rated["season_idx"] == bs) & (rated["gw"] >= bg))]
        hold = hold[pd.to_numeric(hold["minutes"], errors="coerce") > 0]
        actual = (pd.to_numeric(hold["goals"], errors="coerce")
                  / (pd.to_numeric(hold["minutes"], errors="coerce") / 90.0))
        pair = pd.DataFrame({"pred": hold["shrunk_goals90"],
                             "actual": actual}).dropna()
        if len(pair) < 2 or pair["pred"].nunique() < 2:
            continue
        score = float(pair["pred"].corr(pair["actual"]))
        if score > best_score:
            best_score, best_k = score, float(k)
    return best_k


def best_mode_shrinkage_k(df: pd.DataFrame,
                          k_grid: list[float] = SHRINK_K_MODE_GRID,
                          holdout_slots: int = 10) -> float:
    """The ``k`` whose shrunken start rate best predicts held-out starts.

    The mode-rate twin of :func:`best_shrinkage_k`, scored by correlation
    against the *actual* start indicator on the last ``holdout_slots``
    gameweek slots, with the rates built from earlier rows only. Offline: its
    answer is pinned as :data:`SHRINK_K_MODE` rather than refitted per run, so
    a training run is deterministic and a change of k is a reviewable diff.
    """
    slots = (df[["season_idx", "gw"]].drop_duplicates()
             .sort_values(["season_idx", "gw"]))
    if len(slots) <= holdout_slots:
        return SHRINK_K_MODE
    bs, bg = slots.iloc[-holdout_slots][["season_idx", "gw"]]
    best_k, best_score = SHRINK_K_MODE, -2.0
    for k in k_grid:
        rated = add_shrunken_modes(df, k=k)
        hold = rated[(rated["season_idx"] > bs)
                     | ((rated["season_idx"] == bs) & (rated["gw"] >= bg))]
        actual = pd.to_numeric(hold.get("starts"), errors="coerce")
        pair = pd.DataFrame({"pred": hold["shrunk_start_rate"],
                             "actual": actual}).dropna()
        if len(pair) < 2 or pair["pred"].nunique() < 2:
            continue
        score = float(pair["pred"].corr(pair["actual"]))
        if score > best_score:
            best_score, best_k = score, float(k)
    return best_k
