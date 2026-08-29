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

These are the *additive* terms, and they sum to ``ep``. ``ep_pen_taker`` is
deliberately not among them: the penalty increment was folded into
``e_goals`` before ``assemble_ep`` ever ran, so it is already inside the Goals
line. Listing it here as a thirteenth row double-counted it, and made a panel
whose whole promise is "these numbers add up to that number" stop adding up
for exactly the players anyone would check. It travels instead as
``ComponentFixture.pen_taker``, an annotation the panel prints *under* Goals.
"""


def _num(value) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(out) else out


def _xmins(p_play, p60) -> float | None:
    """Expected minutes from the two probabilities the minutes model emits.

    ``p_play * (45 + 45 * p60)``: half a match for being on the pitch at all,
    and the second half weighted by the chance he sees the hour out. A nailed-on
    starter comes to 90, a player who never gets on comes to 0.

    ``None`` rather than 0.0 when either probability is missing. The squad
    table's xMin column would otherwise report an un-modelled player as one
    expected to play no minutes, which is a different and much stronger claim.
    """
    if p_play is None or p60 is None:
        return None
    try:
        play, hour = float(p_play), float(p60)
    except (TypeError, ValueError):
        return None
    if math.isnan(play) or math.isnan(hour):
        return None
    return round(play * (45 + 45 * hour), 1)


def _text(value) -> str:
    """A cell as a string, with a missing one reading as empty.

    ``str(value or "")`` is not this: a float NaN is *truthy*, so a player
    whose opponent or club failed to join came out of the panel labelled
    "nan". The row is right to survive the gap — a missing name is not a
    reason to 500 — but it has to survive it as a blank.
    """
    return "" if value is None or pd.isna(value) else str(value)


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
            pen = round(_num(getattr(row, "ep_pen_taker", 0.0)), 2)
            fixtures.append(ComponentFixture(
                gw=int(row.gw), opponent=_text(row.opp_name),
                home=bool(_num(row.was_home)),
                kickoff_time=(None if pd.isna(row.kickoff_time)
                              else str(row.kickoff_time)),
                components=terms,
                pen_taker=(pen if pen != 0.0 else None),
                minutes=MinutesOutput(
                    p_play=round(_num(row.p_play), 3),
                    p60=round(_num(row.p60), 3),
                    # From the raw cells, not the _num'd ones: _num turns a
                    # missing probability into 0.0, and 0.0 is a real answer.
                    xmins=_xmins(getattr(row, "p_play", None),
                                 getattr(row, "p60", None))),
                ep=round(_num(row.ep), 2)))
        head = rows.iloc[0]
        players.append(ComponentPlayer(
            code=int(code), name=str(head["name"]),
            position=str(head["position"]),
            team_name=_text(head["team_name"]),
            ep=round(float(sum(f.ep for f in fixtures)), 2),
            fixtures=fixtures))
    return ComponentsBreakdown(gw=int(gw), players=players)
