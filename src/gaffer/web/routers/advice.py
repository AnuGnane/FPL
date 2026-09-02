"""This Week: the saved advice payload and its staleness.

``run_train_and_advise`` lives here and is still the body of the ``advise``
job kind (``job_kinds.JOB_KINDS``). What used to live here as well was a
``POST /rerun`` that queued that same body on the legacy ``JobRegistry``, a
second lane past the single-flight ``JobRunner`` — two callers could start two
full train+advise runs writing to ``reports/`` at once. The route is gone;
``POST /api/jobs/advise`` is the one way in.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pandas as pd
from fastapi import APIRouter

from gaffer.artifacts import (advice_history_files, data_warning,
                              diff_advice, ep_movers, ingested_through,
                              latest_gw, load_advice, load_solve_state,
                              upcoming_gw)
from gaffer.errors import GafferError
from gaffer.web.field_frame import with_field_frame
from gaffer.web.identity import with_identity
from gaffer.web.schemas import AdviceDiff, AdviceLatest, Staleness

if TYPE_CHECKING:  # the runtime import stays lazy inside the function body
    from gaffer.config import Config

router = APIRouter(prefix="/api/advice", tags=["advice"])


def run_train_and_advise(cfg: "Config | None" = None) -> dict:
    """The job body: exactly what the launchd Thursday run does.

    ``cfg`` defaults to ``None`` — that is, to ``load_config()`` — so the
    zero-argument callers (``JOB_KINDS['advise']``, which the runner calls
    with no arguments) are untouched. The keyword exists for the one caller
    that wants the same run under a modified config: ``advise-fast``, which
    hands it ``scenarios_n=0``.
    """
    from gaffer.advise import run_advise
    from gaffer.config import load_config
    from gaffer.models.train import load_training_frame, train_all
    from gaffer.report.render import render_report
    from gaffer.tracking import latest_health

    frame, team_frame, _ = load_training_frame()
    train_all(frame, team_frame, save=True)
    advice = run_advise(cfg if cfg is not None else load_config())
    render_report(advice, model_health=latest_health())
    return {"gw": advice.gw, "expected_pts": advice.expected_pts}


def staleness_for(advice_gw: int, deadline: str,
                  generated_at: str) -> Staleness:
    """Server-side staleness — the client only displays it (spec §4)."""
    current = upcoming_gw()
    stamp = pd.Timestamp(deadline)
    stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None \
        else stamp.tz_convert("UTC")
    passed = stamp < pd.Timestamp.now(tz="UTC")
    behind = current is not None and current > advice_gw
    if behind:
        reason = (f"this advice is for GW{advice_gw}; GW{current} is the next "
                  f"deadline")
    elif passed:
        reason = f"GW{advice_gw}'s deadline has passed"
    else:
        reason = f"current for GW{advice_gw}"
    # Read from the parquet, not from the stored advice payload: an advice
    # file written days ago still gets today's answer about what the model
    # has actually ingested.
    through = ingested_through()
    return Staleness(advice_gw=advice_gw, current_gw=current,
                     generated_at=generated_at, deadline=deadline,
                     deadline_passed=passed, stale=bool(behind or passed),
                     reason=reason, data_through_gw=through,
                     data_warning=data_warning(current, through))


PLAYER_KEYS = ("xi", "bench", "buys", "sells", "captain", "vice")
"""Advice keys holding player dicts the UI renders by position."""


def with_positions(payload: dict, pool: pd.DataFrame) -> dict:
    """Backfill ``position`` on player entries written before it was saved.

    ``advise`` only started emitting positions in v3.1, and a user with last
    week's advice on disk must not have to re-run the whole pipeline to get a
    pitch. The solved pool already knows every candidate's position, so read
    it from there and leave anything already positioned alone.
    """
    pos_of = {int(c): str(p)
              for c, p in zip(pool["code"], pool["position"])}

    def fill(entry: dict) -> dict:
        if entry.get("position"):
            return entry
        return {**entry, "position": pos_of.get(int(entry["code"]), "")}

    out = dict(payload)
    for key in PLAYER_KEYS:
        value = out.get(key)
        if isinstance(value, list):
            out[key] = [fill(e) for e in value if isinstance(e, dict)]
        elif isinstance(value, dict) and "code" in value:
            out[key] = fill(value)
    return out


HAUL_KEYS = ("alternatives", "captain_options")
"""The two payload keys carrying ``assemble.p_haul``.

Both are written by ``advise.py`` as ``.to_dict("records")`` off frames whose
column list lives in ``optimize/differentials.py`` — two protected files, and
the reason this rename happens here (spec D3).

v12 W3 §4.6: on a banded run ``captain_options`` carries ``p_haul_total``,
``uncertainty.Band.p_haul``, which needs no rename because it was never the
attacking one. The key stays in the tuple for two live reasons: a banked
payload written before v12 still has the old column, and the degraded arm of
``captain_table`` (no bands for the gameweek) still emits ``p_haul`` today —
renaming it on the way out is exactly what this function is for.
"""


def with_attacking_haul(payload: dict) -> dict:
    """Rename the *attacking* ``p_haul`` to ``p_attacking_haul`` on the way out.

    Two different quantities are called ``p_haul`` in this codebase.
    ``models.assemble.p_haul`` is P(2+ attacking returns) under a Poisson on
    expected goals plus assists, and it is what the alternatives and captain
    tables carry. ``uncertainty.Band.p_haul`` is P(total points >= 10) in the
    tail of a normal on the whole forecast, and it is what ``/api/players``
    and ``/api/components`` carry. They are not the same number, they are not
    on the same scale, and until v9c they were served under one name on one
    page.

    Renaming the internal column would mean diffs inside ``advise.py`` and
    ``optimize/**``, which are protected — not worth an authorization for a
    label. So the split is resolved here, at the boundary, and this is the
    single site at which it happens. The artifact on disk is untouched:
    ``digest.py`` reads it, the since-last-run diff compares against it, and
    every advice file already banked stays readable.

    Additive and defensive, like its two siblings: a payload with no
    alternatives, a row with no ``p_haul``, a key that is not a list — each
    comes back as it arrived.
    """
    def renamed(row: dict) -> dict:
        # Rebuilt in place rather than popped-and-appended, so the field keeps
        # its column position for anything reading the payload in order.
        return {("p_attacking_haul" if k == "p_haul" else k): v
                for k, v in row.items()}

    out = dict(payload)
    for key in HAUL_KEYS:
        value = out.get(key)
        if not isinstance(value, list):
            continue
        out[key] = [renamed(e) if isinstance(e, dict) and "p_haul" in e else e
                    for e in value]
    return out


@router.get("/latest", response_model=AdviceLatest)
def latest() -> AdviceLatest:
    gw = latest_gw()
    if gw is None:
        raise GafferError("no advice on disk yet — run `gaffer advise` first")
    state = load_solve_state(gw)
    # Four serve-time decorations, composed. ``with_positions`` backfills a
    # field ``advise`` did not always write; ``with_identity`` adds three it
    # still does not, because it cannot — ``advise.py`` is protected, so the
    # pitch's team identity and fixture chip are resolved here from files the
    # backend already banks (plan A2). ``with_attacking_haul`` is v9c's D3:
    # two different quantities were served as ``p_haul`` on one page, and the
    # attacking one is renamed here because renaming the column would mean
    # editing the protected pipeline for a label. ``with_field_frame`` is
    # v10b §F1a: the captain's standing against the top 10k, with its standard
    # error, which is a number ``/api/players`` computes for every player and
    # serves for none. It runs **outermost** because it reads the captain after
    # ``with_positions`` has filled him in, and because the sentence names the
    # club ``with_identity`` has just resolved. All four are additive, all four
    # leave every pre-existing field alone, and all four are no-ops on a clone
    # with no snapshots rather than an error.
    payload = with_field_frame(
        with_attacking_haul(
            with_identity(with_positions(load_advice(gw), state.pool), gw)),
        gw)
    return AdviceLatest(
        gw=gw, mode=state.mode, deadline=state.deadline, advice=payload,
        staleness=staleness_for(gw, state.deadline, state.generated_at))


@router.get("/diff", response_model=AdviceDiff)
def diff(gw: int | None = None) -> AdviceDiff:
    """The "since last run" strip: this run against the one before it.

    Same gameweek only. Re-running on Friday after the press conferences is
    the case this exists for, and comparing Friday's GW5 plan with last week's
    GW4 plan would answer a question nobody asked.

    Never an error. A first run of the week, a wiped ``reports/`` directory
    and a history file that will not parse all land in the same place: the
    strip is not shown, and the rest of This Week renders exactly as it did.

    The EP movers are computed before every one of those exits, because they
    are not about the plan at all — they are about the *model*, and a first
    run of the week is exactly when a retrain happened (plan A10).
    """
    target = gw if gw is not None else latest_gw()
    if target is None:
        return AdviceDiff(gw=0, available=False)
    movers = ep_movers(int(target))
    extra = {"ep_movers": movers or [],
             "ep_movers_count": None if movers is None else len(movers)}
    files = advice_history_files(int(target))
    if len(files) < 2:
        return AdviceDiff(gw=int(target), available=False, **extra)
    previous_path, current_path = files[-2], files[-1]
    try:
        previous = json.loads(previous_path.read_text())
        current = json.loads(current_path.read_text())
    except (OSError, ValueError) as exc:
        # OSError as well as ValueError: the file was listed a moment ago, so
        # a rerun rotating history underneath the read, or a permission the
        # server lost, is exactly as much of a "no diff to show" as malformed
        # JSON is — and the strip promises never to be an error.
        print(f"advice history unreadable, no diff shown: {exc}")
        return AdviceDiff(gw=int(target), available=False, **extra)
    out = diff_advice(previous, current)
    return AdviceDiff(
        gw=int(target), available=True,
        previous_at=previous_path.stem.partition("-")[2],
        current_at=current_path.stem.partition("-")[2], **out, **extra)
