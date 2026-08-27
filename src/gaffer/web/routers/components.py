"""GET /api/components/{gw} — the saved EP decomposition (spec §4).

``run_advise`` has written ``reports/components_gw{N}.parquet`` since v3; this
serves it. No model is loaded and nothing is recomputed, which is what makes
it cheap enough for a row to expand on click.

The terms are the ones ``ep_breakdown`` produced, in the order a human reads
them (what he gets for turning up, then what he might do, then what might be
done to him), with zeroes dropped: a panel whose job is showing what moved
should not print nine zeroes to get to the one number that did.
"""

from __future__ import annotations

import math

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from gaffer.artifacts import load_components
from gaffer.errors import GafferError
from gaffer.web.schemas import (Component, ComponentFixture, ComponentPlayer,
                                ComponentsBreakdown, MinutesOutput)

router = APIRouter(prefix="/api", tags=["components"])

TERMS: list[tuple[str, str]] = [
    ("ep_minutes", "Minutes"),
    ("ep_goals", "Goals"),
    ("ep_pen_taker", "Penalty duty"),
    ("ep_assists", "Assists"),
    ("ep_cs", "Clean sheet"),
    ("ep_gc", "Goals conceded"),
    ("ep_saves", "Saves"),
    ("ep_defcon", "Defensive contribution"),
    ("ep_bonus", "Bonus"),
    ("ep_pensave", "Penalty saves"),
    ("ep_cards", "Cards"),
    ("cal_delta", "Calibration"),
]
"""Component column -> the label the panel prints.

``ep_pen_taker`` sits directly under Goals because it *is* part of the goals
term — it was folded into ``e_goals`` before ``assemble_ep`` ever ran — and
showing it anywhere else would imply it is a separate line of the scoring
table, which it is not.
"""


def _num(value) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(out) else out


@router.get("/components/{gw}", response_model=ComponentsBreakdown)
def components(gw: int,
               codes: str | None = Query(
                   None, description="Comma-separated player codes; all "
                                     "players when omitted.")
               ) -> ComponentsBreakdown:
    try:
        frame = load_components(gw)
    except GafferError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if codes:
        wanted = {int(c) for c in codes.split(",") if c.strip().isdigit()}
        frame = frame[frame["code"].astype(int).isin(wanted)]

    players: list[ComponentPlayer] = []
    for code, rows in frame.groupby("code", sort=True):
        # mergesort because it is stable: a double gameweek's two fixtures
        # can share a kickoff time in a fixture file, and the order they were
        # written in is the order the opponents should read in.
        rows = rows.sort_values("kickoff_time", na_position="last",
                                kind="mergesort")
        fixtures = []
        for row in rows.itertuples():
            terms = [Component(label=label, points=round(_num(
                getattr(row, col, 0.0)), 2))
                for col, label in TERMS
                if round(_num(getattr(row, col, 0.0)), 2) != 0.0]
            fixtures.append(ComponentFixture(
                gw=int(row.gw), opponent=str(row.opp_name or ""),
                home=bool(_num(row.was_home)),
                kickoff_time=(None if pd.isna(row.kickoff_time)
                              else str(row.kickoff_time)),
                components=terms,
                minutes=MinutesOutput(p_play=round(_num(row.p_play), 3),
                                      p60=round(_num(row.p60), 3)),
                ep=round(_num(row.ep), 2)))
        head = rows.iloc[0]
        players.append(ComponentPlayer(
            code=int(code), name=str(head["name"]),
            position=str(head["position"]),
            team_name=str(head["team_name"] or ""),
            ep=round(float(sum(f.ep for f in fixtures)), 2),
            fixtures=fixtures))
    return ComponentsBreakdown(gw=int(gw), players=players)
