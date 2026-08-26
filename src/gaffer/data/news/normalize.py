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


def club_code_map(teams: pd.DataFrame) -> dict[str, int]:
    """``normalized club string -> team_code``, from names and short names.

    The news sites write "Man City", "Spurs" and "Nott'm Forest" where the
    bootstrap writes its own spellings, and the normalizer collapses most of
    that by itself. A club string nothing answers to resolves to nothing and
    its rows fall through to the all-clubs sweep — never to a guess.
    """
    out: dict[str, int] = {}
    for r in teams.itertuples():
        for key in (normalize_name(r.name),
                    normalize_name(getattr(r, "short_name", ""))):
            if key:
                out.setdefault(key, int(r.code))
    return out


def match_codes(rows: pd.DataFrame, players: pd.DataFrame,
                teams: pd.DataFrame, label: str,
                min_coverage: float = NEWS_MIN_COVERAGE) -> pd.DataFrame:
    """``rows`` (name, club, …) plus a ``code`` column; unmatched rows dropped.

    Two passes over the batch, most conservative first, exactly the shape
    :func:`gaffer.data.odds.ags_frame` uses:

    1. normalized equality against both the web_name and the full name, within
       the club the row names (or across all clubs when the club string does
       not resolve — a source that writes "Wolverhampton" must still find
       Wolves' players);
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
        club = clubs.get(normalize_name(getattr(r, "club", "")))
        candidates = [club] if club is not None else all_teams
        for team_code in candidates:
            code = by_name_team.get((name, int(team_code)))
            if code is not None and code not in claimed:
                codes[i] = code
                claimed.add(code)
                break
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
            club = clubs.get(normalize_name(row.get("club", "")))
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
