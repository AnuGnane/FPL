"""Re-derive BPS and bonus under the 2026/27 rules.

Stored history was scored under the old rules, so the bonus model's target
and its BPS features silently mean two different things either side of the
2026/27 boundary. These are pure functions over a player-match frame — no
I/O, no config reads — so the caller decides which season counts as
"current" and callers in training and serving can share one adjusted
history (no train/serve skew).

The 2026/27 change (premierleague.com/en/news/4679946) has two halves and we
can only reproduce one. Clearances/blocks/interceptions now earn 1 BPS per
*three* actions instead of per two, which the stored ``cbi`` count lets us
correct exactly. The -1 BPS for being tackled was removed, and no public
source carries a times-tackled column — so old-season BPS here slightly
*underestimates* new-rules BPS for players who are dispossessed often. That
is a known, deliberate approximation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FIRST_NEW_RULES_SEASON = "2026-27"
"""The first season scored under the rules this module restates history *to*.

The boundary is a property of the game's rule change, not of what happens to
be newest on disk. Deriving it from ``max(season_idx) + 1`` was only ever
right while no new-rules season had been archived; the day 2026-27 lands in
the history store, that reading would start "correcting" a season that needs
no correction. Season labels sort lexicographically in FPL's ``YYYY-YY`` form,
so ``season >= FIRST_NEW_RULES_SEASON`` is the whole test.
"""


def adjust_bps(df: pd.DataFrame, current_idx: int) -> pd.Series:
    """Per-row BPS restated under the 2026/27 CBI rule.

    ``bps + floor(cbi/3) - floor(cbi/2)`` — a non-positive delta — for rows
    older than ``current_idx``. Rows at or after ``current_idx`` were already
    scored under the new rules and come back untouched. A missing ``cbi``
    (every season before 2025/26) means there is nothing to correct, so the
    delta is zero rather than NaN; a missing ``bps`` stays missing.
    """
    bps = pd.to_numeric(df["bps"], errors="coerce")
    if "cbi" in df.columns:
        cbi = pd.to_numeric(df["cbi"], errors="coerce").fillna(0.0)
    else:
        cbi = pd.Series(0.0, index=df.index, dtype="float64")
    delta = np.floor(cbi / 3.0) - np.floor(cbi / 2.0)
    old = pd.to_numeric(df["season_idx"], errors="coerce") < current_idx
    return bps + delta.where(old, 0.0)


def fixture_pair(df: pd.DataFrame) -> pd.Series:
    """The unordered ``{team_code, opp_code}`` pair as a stable string.

    Both sides of one match have to land in the same bonus ranking, and they
    carry the pair the other way round, so the key sorts the two codes before
    joining them.
    """
    a = pd.to_numeric(df["team_code"], errors="coerce")
    b = pd.to_numeric(df["opp_code"], errors="coerce")
    lo = np.minimum(a, b)
    hi = np.maximum(a, b)
    return (pd.Series(lo, index=df.index).astype("string") + "-"
            + pd.Series(hi, index=df.index).astype("string"))


def fixture_key(df: pd.DataFrame,
                fixtures: pd.DataFrame | None = None) -> pd.Series:
    """Which real match each player-row belongs to, as a group key.

    With a ``fixtures`` frame (``season_idx, gw, kickoff_time, home_code,
    away_code``) the identity comes from the fixture list rather than from the
    player row: a row joins the fixture at its own ``(season_idx, gw,
    kickoff_time)`` whose ``home_code`` *or* ``away_code`` is its ``opp_code``.
    That is unique — a team plays at most once per kickoff — and, crucially,
    ``opp_code`` is fixture-sourced, so it survives a transfer. ``team_code``
    does not: the store carries the player's *current* club, so keying on
    ``{team_code, opp_code}`` scatters everyone who has since moved into
    singleton pseudo-fixtures where the re-derivation hands each of them the
    3 bonus of a one-man ranking. Rows matching no fixture get ``None``.

    A team playing twice at one kickoff is impossible, so a key that two
    different fixtures both claim means the fixture list is corrupt — a
    duplicated ingest, a postponement re-added rather than moved. That key is
    dropped rather than last-wins-overwritten or raised on: the rows fall to
    the unmatched branch and keep their stored bonus, which is the safe
    direction, whereas last-wins keys half a match onto the wrong fixture and
    an exception lets one bad ingest row kill an entire training run.

    Without ``fixtures`` the key falls back to :func:`fixture_pair`, which is
    what synthetic frames (and callers with no fixture list) still use.

    The lookup itself lives in :func:`_fixture_lookup`, extracted in v9c so
    :func:`as_of_club_code` reads the same join — and the same
    corrupt-duplicate poisoning — rather than a second one beside it.
    """
    if fixtures is None:
        return pd.Series(
            list(zip(df["season_idx"], df["gw"],
                     df["kickoff_time"].astype("string"), fixture_pair(df))),
            index=df.index, dtype=object)

    lookup = _fixture_lookup(fixtures)
    rows = zip(pd.to_numeric(df["season_idx"], errors="coerce"),
               pd.to_numeric(df["gw"], errors="coerce"),
               df["kickoff_time"].astype("string"),
               pd.to_numeric(df["opp_code"], errors="coerce"))
    return pd.Series([lookup.get((s, g, k, o)) for s, g, k, o in rows],
                     index=df.index, dtype=object)


def as_of_club_code(df: pd.DataFrame, fixtures: pd.DataFrame) -> pd.Series:
    """The club each row's player actually played for, not the one he is at.

    ``data/live.py`` rebuilds player history every run and stamps today's
    ``team_code`` onto every row of it, so a January transfer rewrites the
    player's August rows under his new club.

    v9c switched **three** consumers onto this column (spec D2): the
    position-by-club prior in ``_shrunk_ratio``, manager-spell scoping in
    ``add_rotation_priors``, and the own side of the Elo merge in
    ``add_context``. Those are the three the finding named.

    **Two more still read the stamped ``team_code``** and are deliberately
    left for v9d rather than swept in here: the own-side Understat team merge
    (``engineer.merge_understat_team``) and the club-congestion lookup
    (``engineer.add_congestion``). Both key on club and both therefore carry
    the same staleness; neither was in the reviewed finding, and switching a
    feature family without measuring it is what this cycle exists to stop
    doing. Saying so here is cheaper than a reader inferring from "three
    builders" that the column is now the only club key in the tree.

    ``opp_code`` survives a transfer because it is written per row from the
    fixture, and that asymmetry is the derivation: match the row to its
    fixture on ``(season_idx, gw, kickoff_time)`` where one side is
    ``opp_code``, and the player's club is the other side. ``was_home``
    cross-checks it; a row that disagrees is describing a different match
    from the fixture it matched, and falls back rather than inventing a club.

    Rows that match no fixture fall back to ``team_code``, and so do whole
    seasons with no archived fixture list (spec §3 puts backfilling those out
    of scope). The fallback is never NaN: a NaN club would scatter every
    downstream ``groupby`` into a silent extra bucket, which is a worse
    failure than the staleness this function exists to fix.
    """
    fallback = pd.to_numeric(df["team_code"], errors="coerce")
    needed = {"season_idx", "gw", "kickoff_time", "opp_code", "team_code"}
    if fixtures is None or fixtures.empty or not needed <= set(df.columns):
        return fallback.fillna(0).astype("int64")
    if not {"season_idx", "gw", "kickoff_time", "home_code",
            "away_code"} <= set(fixtures.columns):
        return fallback.fillna(0).astype("int64")

    lookup = _fixture_lookup(fixtures)
    home_flags = (df["was_home"] if "was_home" in df.columns
                  else pd.Series(None, index=df.index, dtype=object))

    out: list[float] = []
    rows = zip(pd.to_numeric(df["season_idx"], errors="coerce"),
               pd.to_numeric(df["gw"], errors="coerce"),
               df["kickoff_time"].astype("string"),
               pd.to_numeric(df["opp_code"], errors="coerce"),
               home_flags, fallback)
    for s, g, k, opp, was_home, stamped in rows:
        ident = lookup.get((s, g, k, opp))
        if ident is None:
            out.append(stamped)
            continue
        _, _, _, home, away = ident
        # The player's club is the side ``opp_code`` is not. A fixture where
        # both sides read as the opponent is not a fixture we can read.
        if home == opp and away == opp:
            out.append(stamped)
            continue
        club = away if home == opp else home
        derived_home = club == home
        if was_home is not None and not pd.isna(was_home) \
                and bool(was_home) != bool(derived_home):
            out.append(stamped)
            continue
        out.append(club)

    club_series = pd.Series(out, index=df.index, dtype="float64")
    return club_series.where(club_series.notna(),
                             fallback).fillna(0).astype("int64")


def _fixture_lookup(fixtures: pd.DataFrame) -> dict:
    """``{(season_idx, gw, kickoff_time, team_code): ident | None}``.

    Extracted from :func:`fixture_key` in v9c so :func:`as_of_club_code` can
    build on the same join rather than writing a second one that agrees with
    it until the day it does not. The body is unchanged, and that includes the
    clause that matters most: a key claimed by two different fixtures is
    poisoned to ``None`` rather than resolved last-wins, so corrupt data
    becomes an unmatched row instead of a confidently wrong one.
    """
    lookup: dict[tuple, tuple | None] = {}
    for s, g, k, h, a in zip(
            pd.to_numeric(fixtures["season_idx"], errors="coerce"),
            pd.to_numeric(fixtures["gw"], errors="coerce"),
            fixtures["kickoff_time"].astype("string"),
            pd.to_numeric(fixtures["home_code"], errors="coerce"),
            pd.to_numeric(fixtures["away_code"], errors="coerce")):
        ident = (s, g, k, h, a)
        for team in (h, a):
            seen = lookup.get((s, g, k, team), ident)
            lookup[(s, g, k, team)] = ident if seen == ident else None
    return lookup


def award_bonus(values: list[float]) -> list[int]:
    """FPL bonus for one fixture's BPS values, published tie rules included.

    Ranked descending on distinct values:

    * tie for 1st among two -> ``3, 3`` then the next player takes 1 (the 2
      is skipped, because it would have gone to the second of the two);
    * tie for 1st among three or more -> every tied player takes 3 and
      nothing else is awarded;
    * tie for 2nd -> every tied player takes 2 and no 1 is awarded;
    * tie for 3rd -> every tied player takes 1.

    A fixture with no ties awards exactly 6 points; a tied one awards more,
    which is the real game's behaviour, not a bug.
    """
    out = [0] * len(values)
    distinct = sorted(set(values), reverse=True)
    groups = [[i for i, v in enumerate(values) if v == d] for d in distinct]
    if not groups:
        return out
    for i in groups[0]:
        out[i] = 3
    if len(groups[0]) >= 3:
        return out
    if len(groups[0]) == 2:
        if len(groups) > 1:
            for i in groups[1]:
                out[i] = 1
        return out
    if len(groups) > 1:
        for i in groups[1]:
            out[i] = 2
        if len(groups[1]) >= 2:
            return out
        if len(groups) > 2:
            for i in groups[2]:
                out[i] = 1
    return out


def rederive_bonus(df: pd.DataFrame, bps: pd.Series | None = None,
                   fixtures: pd.DataFrame | None = None) -> pd.Series:
    """Bonus points re-awarded per fixture from (adjusted) BPS.

    Fixtures are identified by :func:`fixture_key` — off the real fixture list
    when ``fixtures`` is given, off ``(season_idx, gw, kickoff_time,
    fixture_pair)`` when it is not. ``bps`` defaults to the frame's own column
    so the function is usable on unadjusted history too.

    A row that matches no fixture is passed through with its stored ``bonus``
    rather than re-awarded: an unrecognised row is a data problem, and the one
    thing it must never do is invent bonus out of a ranking of itself.

    Only appearances are ranked. A player on zero minutes carries a zero BPS
    that would otherwise tie with every other absentee and, in a fixture
    where nobody scored, could be handed bonus the real game never awarded.
    """
    values = (pd.to_numeric(df["bps"], errors="coerce") if bps is None
              else pd.to_numeric(bps, errors="coerce"))
    if "minutes" in df.columns:
        minutes = pd.to_numeric(df["minutes"], errors="coerce").fillna(0.0)
    else:
        minutes = pd.Series(1.0, index=df.index, dtype="float64")
    out = pd.Series(0.0, index=df.index, dtype="float64")
    out[values.isna()] = float("nan")

    key = fixture_key(df, fixtures)
    matched = key.notna()
    if not matched.all() and "bonus" in df.columns:
        stored = pd.to_numeric(df["bonus"], errors="coerce")
        out[~matched] = stored[~matched]

    eligible = values.notna() & (minutes > 0) & matched
    if not eligible.any():
        return out
    for _, idx in values[eligible].groupby(key[eligible]).groups.items():
        awards = award_bonus([float(v) for v in values.loc[idx]])
        out.loc[idx] = [float(a) for a in awards]
    return out


def restated_groups(df: pd.DataFrame, key: pd.Series) -> pd.Series:
    """Per row: did the CBI adjustment move any BPS in its fixture?

    The re-derivation is only ever an improvement where it has something to
    correct. Where the adjustment is provably a no-op for a whole fixture —
    every season before 2025/26 carries no ``cbi`` at all — a fresh ranking
    can only differ from the stored bonus because our BPS is an approximation
    (the removed times-tackled penalty we cannot reconstruct, a stored BPS
    that disagrees with the published bonus), and in that argument the stored
    truth wins. Rows in no fixture at all count as unmoved.
    """
    new = pd.to_numeric(df["bps"], errors="coerce").to_numpy(dtype="float64")
    old = pd.to_numeric(df["bps_old"], errors="coerce").to_numpy(dtype="float64")
    changed = pd.Series(~np.isclose(new, old, equal_nan=True), index=df.index)
    if not key.notna().any():
        return pd.Series(False, index=df.index)
    moved = changed.groupby(key).transform("any")
    return moved.reindex(df.index).fillna(False).astype(bool)


def apply_new_bps(df: pd.DataFrame, current_idx: int,
                  fixtures: pd.DataFrame | None = None) -> pd.DataFrame:
    """``bps`` and ``bonus`` restated under the 2026/27 rules.

    The originals are kept as ``bps_old`` / ``bonus_old`` — partly so a
    regression can be diffed against the stored truth, partly because their
    presence marks a frame as restated (see :mod:`gaffer.models.train`).

    Only rows older than ``current_idx`` are restated, and among those only
    the fixtures where the adjustment actually moved a BPS (see
    :func:`restated_groups`). Current-season rows were already scored under
    the new rules, so their stored bonus is the truth: re-ranking them could
    only corrupt it on a data quirk.

    ``fixtures`` is the real fixture list and should be passed wherever one is
    available — see :func:`fixture_key` for why the player row alone cannot
    identify the match it was played in.

    ``total_points`` is deliberately *not* restated. The stored season total
    is the scoring authority: it is what the game actually paid out, what
    every evaluation and backtest scores against, and it is not reconstructable
    anyway (the removed times-tackled BPS penalty has no public column). Only
    the bonus model's target and the BPS features are restated, so on a
    restated row the sum of the scoring components may differ from
    ``total_points`` by the bonus delta. That is intended: the restatement
    exists to make ``bps``/``bonus`` mean one thing across the rule boundary
    for *fitting*, not to rewrite history's scoreline.

    The index is reset because the fixture grouping addresses rows by label:
    a frame concatenated without ``ignore_index`` would have duplicates.
    """
    out = df.reset_index(drop=True).copy()
    out["bps_old"] = out["bps"]
    out["bonus_old"] = out["bonus"]
    out["bps"] = adjust_bps(out, current_idx)
    old = pd.to_numeric(out["season_idx"], errors="coerce") < current_idx
    moved = restated_groups(out, fixture_key(out, fixtures))
    rederived = rederive_bonus(out, out["bps"], fixtures=fixtures)
    out["bonus"] = rederived.where(old & moved, out["bonus"])
    return out
