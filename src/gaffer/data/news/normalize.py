"""Name → code matching and the availability precedence table.

Two jobs, one module, because they are two halves of the same question: which
FPL player is this row about, and what does the row mean once we know.
"""

from __future__ import annotations

import pandas as pd

from gaffer.data.names import normalize_name

NEWS_MIN_COVERAGE = 0.5
"""Share of a source's rows that must resolve to FPL codes.

Straight off :data:`gaffer.data.odds.AGS_MIN_COVERAGE`, for the same reason: a
page that has been rewritten still parses into *something*, and a third of an
injury table is not a picture of the league's injuries. A shape change must not
half-apply, so the batch is discarded whole and counted.
"""


def player_name_index(players: pd.DataFrame) -> tuple[dict, dict]:
    """``(name, team_code) -> code``, and ``team_code -> {code: tokens}``.

    The AGS index (:func:`gaffer.data.odds._ags_name_index`) with the same two
    keys per player — the bootstrap's abbreviated ``name`` and the normalized
    full name — because the news sites print the full name the way the odds
    feed does and the abbreviation the way older fixtures do.
    """
    has_full = ("first_name" in players.columns
                and "second_name" in players.columns)
    by_name_team: dict[tuple[str, int], int] = {}
    by_tokens_team: dict[int, dict[int, tuple[str, ...]]] = {}
    for r in players.itertuples():
        keys = [normalize_name(r.name)]
        if has_full:
            keys.append(normalize_name(f"{r.first_name} {r.second_name}"))
        keys = [k for k in keys if k]
        if not keys:
            continue
        team_code = int(r.team_code)
        for key in keys:
            by_name_team.setdefault((key, team_code), int(r.code))
        by_tokens_team.setdefault(team_code, {})[int(r.code)] = tuple(
            max(keys, key=len).split())
    return by_name_team, by_tokens_team


_CLUB_ALIASES_RAW: dict[str, str] = {
    "nottingham forest": "nott'm forest",
    "manchester united": "man utd",
    "manchester city": "man city",
    "tottenham hotspur": "spurs",
    "tottenham": "spurs",
    "wolverhampton wanderers": "wolves",
    "wolverhampton": "wolves",
    "newcastle united": "newcastle",
    "brighton and hove albion": "brighton",
    "brighton & hove albion": "brighton",
    "west ham united": "west ham",
    "afc bournemouth": "bournemouth",
    "leeds united": "leeds",
    "leicester city": "leicester",
    "sheffield united": "sheff utd",
}
"""Press spellings the normalizer cannot reach -> the bootstrap's own.

``normalize_name`` folds accents and punctuation, not vocabulary: nothing in
it turns "Nottingham Forest" into "Nott'm Forest" or "Spurs" into
"Tottenham Hotspur". An alias is only consulted *after* the built map has been
asked, so a bootstrap that already spells a club out in full keeps winning.
"""

CLUB_ALIASES: dict[str, str] = {
    normalize_name(k): normalize_name(v)
    for k, v in _CLUB_ALIASES_RAW.items()}
"""The same table with both sides run through :func:`normalize_name`.

Written out longhand above and normalized here rather than the other way
round, so the source reads as club names and the lookup keys cannot drift
from whatever the normalizer currently does to an apostrophe.
"""


def club_code_map(teams: pd.DataFrame) -> dict[str, int]:
    """``normalized club string -> team_code``, from names and short names.

    The news sites write "Man City", "Spurs" and "Nott'm Forest" where the
    bootstrap writes its own spellings, and :data:`CLUB_ALIASES` carries the
    ones normalization alone cannot bridge. A club string nothing answers to
    resolves to nothing and its rows fall through to the uniqueness rule —
    never to a guess.
    """
    out: dict[str, int] = {}
    for r in teams.itertuples():
        for key in (normalize_name(r.name),
                    normalize_name(getattr(r, "short_name", ""))):
            if key:
                out.setdefault(key, int(r.code))
    return out


def club_code(clubs: dict[str, int], raw) -> int | None:
    """One club cell -> a team_code, via the map and then the alias table."""
    key = normalize_name(raw or "")
    if not key:
        return None
    if key in clubs:
        return clubs[key]
    alias = CLUB_ALIASES.get(key)
    return clubs.get(alias) if alias else None


def match_codes(rows: pd.DataFrame, players: pd.DataFrame,
                teams: pd.DataFrame, label: str,
                min_coverage: float = NEWS_MIN_COVERAGE) -> pd.DataFrame:
    """``rows`` (name, club, …) plus a ``code`` column; unmatched rows dropped.

    Two passes over the batch, most conservative first, exactly the shape
    :func:`gaffer.data.odds.ags_frame` uses:

    1. normalized equality against both the web_name and the full name, within
       the club the row names — and, when the club string resolves to nothing
       even through :data:`CLUB_ALIASES`, across all clubs but **only when
       exactly one unclaimed player answers**, the same uniqueness rule the
       sweeps keep;
    2. a token pass — same tokens reordered, or one name a subset of the
       other — taken **only when exactly one unclaimed candidate answers**.

    No edit distance, ever. A wrong player's injury is worse than none: it
    benches a fit starter and, through the pessimism rule in
    :func:`availability_frame`, it can zero a captain.

    A batch whose matched share falls below ``min_coverage`` is discarded
    whole and the shortfall printed. The caller sees an empty frame, which is
    indistinguishable from the source being down — which is the point.
    """
    if rows is None or rows.empty:
        empty = pd.DataFrame(columns=list(getattr(rows, "columns", [])))
        empty["code"] = pd.Series(dtype="int64")
        return empty
    by_name_team, by_tokens_team = player_name_index(players)
    clubs = club_code_map(teams)
    all_teams = sorted(by_tokens_team)

    rows = rows.reset_index(drop=True)
    claimed: set[int] = set()
    codes: list[int | None] = [None] * len(rows)
    pending: list[int] = []

    for i, r in enumerate(rows.itertuples()):
        name = normalize_name(getattr(r, "name", ""))
        if not name:
            continue
        club = club_code(clubs, getattr(r, "club", ""))
        if club is not None:
            code = by_name_team.get((name, int(club)))
            if code is not None and code not in claimed:
                codes[i] = code
                claimed.add(code)
                continue
            pending.append(i)
            continue
        # No club to key on, so the league is the search space and the
        # sweeps' uniqueness rule applies here too: two Danny Wards answer to
        # the same exact name, and taking whichever comes first in team order
        # benches a fit keeper on the other one's hamstring.
        hits = {by_name_team[(name, t)] for t in all_teams
                if (name, t) in by_name_team
                and by_name_team[(name, t)] not in claimed}
        if len(hits) == 1:
            code = hits.pop()
            codes[i] = code
            claimed.add(code)
        else:
            pending.append(i)

    def sweep(rule) -> None:
        """One pass over what is still unmatched, taken only where exactly
        one unclaimed player answers."""
        for i in list(pending):
            if codes[i] is not None:
                continue
            row = rows.iloc[i]
            tokens = tuple(normalize_name(row.get("name", "")).split())
            club = club_code(clubs, row.get("club", ""))
            candidates = [club] if club is not None else all_teams
            hits = [code
                    for team_code in candidates
                    for code, cand in by_tokens_team.get(int(team_code),
                                                         {}).items()
                    if code not in claimed and cand and rule(tokens, cand)]
            if len(hits) == 1:
                codes[i] = hits[0]
                claimed.add(hits[0])

    # The same tokens in another order — "Magalhaes Gabriel" against the
    # bootstrap's "Gabriel Magalhães".
    sweep(lambda a, b: sorted(a) == sorted(b))
    # The two sources disagree about how much of the legal name to print:
    # the press writes "Bruno Fernandes", the bootstrap "Bruno Borges
    # Fernandes". Understat's pass 3, and it does the same work here.
    sweep(lambda a, b: set(a) <= set(b) or set(b) <= set(a))

    out = rows.copy()
    out["code"] = codes
    matched = out[out["code"].notna()].copy()
    share = len(matched) / len(out) if len(out) else 0.0
    if share < float(min_coverage):
        print(f"news: {label} matched {len(matched)}/{len(out)} players "
              f"({share:.0%} < {float(min_coverage):.0%}) — discarding the "
              "batch, official flags only")
        return out.iloc[0:0]
    if len(matched) < len(out):
        print(f"news: {label} matched {len(matched)}/{len(out)} players")
    matched["code"] = matched["code"].astype(int)
    return matched.reset_index(drop=True)


AVAIL_COLS = ["code", "status", "chance_of_playing", "injury_type",
              "expected_return_gw", "p_start_hint", "source", "fetched_at"]

OFFICIAL_AUTHORITATIVE = ("s", "u", "n")
"""Official statuses news may never soften: suspended, unavailable, not in
squad. All three are administrative facts rather than medical opinions — a ban
is a ban whoever predicts the XI (spec §4 rule 1)."""

NEWS_RETURNS_THIS_GW = 50.0
"""``chance_of_playing`` a listed injury implies when its return date lands in
the gameweek being advised. He is expected back *this* week and might make it,
which is a coin flip rather than the zero a later return date earns."""


def gw_for_date(events: pd.DataFrame | None, date) -> int | None:
    """The first gameweek whose deadline falls on or after ``date``.

    ``None`` when there is no calendar, no date, or the date is past the end of
    the season — all three mean "we cannot place this return", and the horizon
    decay then falls back to the pooled curve rather than inventing a gameweek.
    """
    if events is None or date is None or len(events) == 0:
        return None
    deadlines = pd.to_datetime(events["deadline_time"], errors="coerce",
                               utc=True)
    target = pd.Timestamp(date, tz="UTC")
    ok = events.loc[deadlines >= target, "gw"]
    return int(ok.min()) if len(ok) else None


def _news_chance(return_gw, gw: int) -> float | None:
    """The current-gameweek ``chance_of_playing`` a news row implies.

    Keyed off the *return gameweek* rather than the prose, because the prose is
    a headline and the date is a claim: back after this week is a zero, back
    this week is a coin flip, no date at all says nothing about this week and
    leaves the official number exactly where it was.
    """
    if return_gw is None or pd.isna(return_gw):
        return None
    return 0.0 if int(return_gw) > int(gw) else NEWS_RETURNS_THIS_GW


def availability_frame(official: pd.DataFrame,
                       injuries: pd.DataFrame | None,
                       lineups: pd.DataFrame | None,
                       gw: int,
                       events: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per official player code, sharpened by whatever news exists.

    ``official`` is the bootstrap slice ``[code, status, chance_of_playing]``.
    ``injuries`` and ``lineups`` are the fetchers' frames, either of which may
    be ``None`` or empty. The result is the frame
    :func:`gaffer.models.availability.apply_availability` consumes:

    ``code, status, chance_of_playing, injury_type, expected_return_gw,
    p_start_hint, source, fetched_at``

    Precedence, spec §4, in order:

    1. Official ``s``/``u``/``n`` is authoritative — news never lifts a ban,
       and no hint or injury row is attached to one.
    2. For ``i``/``d`` and unflagged players a listed injury supplies
       ``injury_type`` and ``expected_return_gw`` even when the official flag
       has not caught up. That head start is the point of the source. A row
       whose return date lands *before* ``gw`` is stale — the listing outlived
       the injury — and is dropped whole: no type, no date, no chance change.
    3. ``p_start_hint`` comes from line-ups alone and is carried, not folded
       in: it applies to the horizon's first gameweek only, and this frame has
       no gameweek axis, so ``apply_availability`` is what applies it.
    4. Where the sources disagree about *this* gameweek, the most pessimistic
       view wins, and only downward — a news row can lower a chance, never
       raise one.

    With both news frames empty the output is the official frame with five
    empty columns beside it, which is why the all-sources-down path is
    byte-identical to the flags-only one.
    """
    out = (official[["code", "status", "chance_of_playing"]]
           .drop_duplicates(subset=["code"]).reset_index(drop=True))
    for col in ("injury_type", "expected_return_gw", "p_start_hint",
                "source", "fetched_at"):
        out[col] = None
    open_codes = set(out.loc[~out["status"].isin(OFFICIAL_AUTHORITATIVE),
                             "code"])

    if injuries is not None and not injuries.empty:
        inj = injuries[injuries["code"].isin(open_codes)].copy()
        inj = inj.drop_duplicates(subset=["code"])
        if not inj.empty:
            inj["expected_return_gw"] = [
                gw_for_date(events, d) for d in inj["expected_return_date"]]
            # A return date the calendar places *before* the gameweek being
            # advised is a listing nobody took down, not news: he is already
            # back. Dropped whole rather than half-applied — an injury_type
            # off a stale row would still steer the horizon decay, and the
            # 50% "back this week" reading would bench a fit starter.
            inj = inj[~(pd.to_numeric(inj["expected_return_gw"],
                                      errors="coerce") < int(gw))]
        if not inj.empty:
            inj["_chance"] = [_news_chance(g, gw)
                              for g in inj["expected_return_gw"]]
            keyed = inj.set_index("code")
            hit = out["code"].isin(keyed.index)
            for col in ("injury_type", "expected_return_gw", "source",
                        "fetched_at"):
                out.loc[hit, col] = out.loc[hit, "code"].map(keyed[col])
            # Rule 4, one-way. 101.0 stands in for "unflagged", so an
            # unflagged player is lowered by any news claim and a flagged one
            # only by a stricter one.
            cop = pd.to_numeric(out["chance_of_playing"], errors="coerce")
            news = out["code"].map(keyed["_chance"]).astype("float64")
            bites = hit & news.notna() & (news < cop.fillna(101.0))
            out.loc[bites, "chance_of_playing"] = news[bites]
            # An unflagged player the press has out needs a status the
            # multiplier recognises; a player FPL already flagged keeps his.
            unflagged = bites & ~out["status"].isin(["i", "d"])
            out.loc[unflagged, "status"] = "i"

    if lineups is not None and not lineups.empty:
        hints = lineups[lineups["code"].isin(open_codes)].copy()
        hints = hints.drop_duplicates(subset=["code"]).set_index("code")
        if not hints.empty:
            got = out["code"].isin(hints.index)
            out.loc[got, "p_start_hint"] = out.loc[got, "code"].map(
                hints["p_start_hint"])
            no_source = got & out["source"].isna()
            out.loc[no_source, "source"] = "lineups"
            no_stamp = got & out["fetched_at"].isna()
            out.loc[no_stamp, "fetched_at"] = out.loc[no_stamp, "code"].map(
                hints["fetched_at"])

    out["expected_return_gw"] = pd.to_numeric(out["expected_return_gw"],
                                              errors="coerce")
    out["p_start_hint"] = pd.to_numeric(out["p_start_hint"], errors="coerce")
    return out[AVAIL_COLS]
