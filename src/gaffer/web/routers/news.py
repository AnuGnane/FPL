"""GET /api/news/{gw} — what the news layer moved (spec §5).

Three artifacts, joined on the player code:

* ``data/live/news_shadow.parquet`` — both sides of every prediction, banked
  by ``news_shadow.write_shadow`` on every advise run. The newest ``run_at``
  per code wins: the log is appended, not overwritten, and Friday's reading is
  the one that shipped.
* ``reports/availability_gw{N}.parquet`` — the frame that run predicted on,
  which is the only record of *why* the layer moved him.
* ``data/live/players.parquet`` — names, clubs and the official flag.

Nothing here is an error. A missing shadow log, a missing snapshot and a
gameweek nobody has advised on all produce an empty panel, because "the news
moved nobody this week" and "we have not looked" render the same way and
neither is worth a red box on This Week.
"""

from __future__ import annotations

import math

import pandas as pd
from fastapi import APIRouter

from gaffer.artifacts import load_availability
from gaffer.data import store
from gaffer.news_shadow import SHADOW_PATH, load_shadow
from gaffer.web.schemas import NewsPanelData, NewsRow

router = APIRouter(prefix="/api", tags=["news"])

MOVED_EPSILON = 1e-9
"""Below this the two sides are the same number, not a disagreement."""

HINT_XI = 0.75
HINT_OUT = 0.25
"""Cuts turning ``p_start_hint`` back into the listing it came from.

The fetcher writes 1.0 for a named starter, 0.0 for a named absence and
something in between for a doubt; these are generous either side so a source
that hedges at 0.9 still reads as "in the XI".
"""


def _opt(value):
    """A pandas cell as a plain Python value, or ``None``."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _hint_name(value) -> str | None:
    hint = _opt(value)
    if hint is None:
        return None
    hint = float(hint)
    if hint >= HINT_XI:
        return "xi"
    return "out" if hint <= HINT_OUT else "doubt"


def _snapshot(rel: str) -> pd.DataFrame:
    if not store.exists(rel):
        return pd.DataFrame()
    try:
        return store.load(rel)
    except Exception as exc:  # noqa: BLE001 — a panel is not worth a 500
        print(f"news panel: {rel} unreadable ({exc})")
        return pd.DataFrame()


@router.get("/news/{gw}", response_model=NewsPanelData)
def news(gw: int) -> NewsPanelData:
    empty = NewsPanelData(gw=int(gw), moved=0, rows=[])
    if not store.exists(SHADOW_PATH):
        return empty
    shadow = load_shadow()
    if shadow is None or shadow.empty or "gw" not in shadow.columns:
        return empty
    rows = shadow[pd.to_numeric(shadow["gw"], errors="coerce") == int(gw)]
    if rows.empty:
        return empty
    # One reading per player: the newest run of this gameweek.
    rows = (rows.sort_values("run_at").groupby("code", as_index=False).last())
    moved = (rows["p_play_news"].astype(float)
             - rows["p_play_flags"].astype(float)).abs() > MOVED_EPSILON
    rows = rows[moved]
    if rows.empty:
        return empty

    players = _snapshot("live/players.parquet")
    teams = _snapshot("live/teams.parquet")
    name_of, team_of, status_of, chance_of, note_of = {}, {}, {}, {}, {}
    if not players.empty:
        team_name = (dict(zip(teams["code"], teams["name"]))
                     if not teams.empty else {})
        for row in players.itertuples():
            code = int(row.code)
            name_of[code] = str(row.name)
            team_of[code] = str(team_name.get(int(row.team_code), ""))
            status_of[code] = _opt(getattr(row, "status", None))
            chance_of[code] = _opt(getattr(row, "chance_of_playing", None))
            note_of[code] = _opt(getattr(row, "news", None))

    avail = load_availability(int(gw))
    evidence: dict[int, dict] = {}
    if avail is not None and not avail.empty:
        for row in avail.itertuples():
            evidence[int(row.code)] = {
                "injury_type": _opt(getattr(row, "injury_type", None)),
                "expected_return_gw": _opt(
                    getattr(row, "expected_return_gw", None)),
                "p_start_hint": _opt(getattr(row, "p_start_hint", None)),
                "source": _opt(getattr(row, "source", None)),
                "fetched_at": _opt(getattr(row, "fetched_at", None)),
            }

    out: list[NewsRow] = []
    for row in rows.itertuples():
        code = int(row.code)
        ev = evidence.get(code, {})
        note = note_of.get(code)
        out.append(NewsRow(
            code=code,
            name=name_of.get(code, str(code)),
            team_name=team_of.get(code, ""),
            p_play_news=round(float(row.p_play_news), 3),
            p_play_flags=round(float(row.p_play_flags), 3),
            e_min_news=round(float(row.e_min_news), 1),
            e_min_flags=round(float(row.e_min_flags), 1),
            status=(None if status_of.get(code) is None
                    else str(status_of[code])),
            chance_of_playing=(None if chance_of.get(code) is None
                               else float(chance_of[code])),
            official_note=(None if not note else str(note)),
            injury_type=(None if ev.get("injury_type") is None
                         else str(ev["injury_type"])),
            expected_return_gw=(None if ev.get("expected_return_gw") is None
                                else int(float(ev["expected_return_gw"]))),
            p_start_hint=(None if ev.get("p_start_hint") is None
                          else float(ev["p_start_hint"])),
            lineup_hint=_hint_name(ev.get("p_start_hint")),
            source=(None if ev.get("source") is None else str(ev["source"])),
            fetched_at=(None if ev.get("fetched_at") is None
                        else str(ev["fetched_at"]))))
    # Biggest disagreement first: the panel is read top-down and stopped at
    # the first name the manager recognises.
    out.sort(key=lambda r: abs(r.p_play_news - r.p_play_flags), reverse=True)
    return NewsPanelData(gw=int(gw), moved=len(out), rows=out)
