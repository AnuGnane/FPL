"""The decision loop: grading what I did against what the model said in time.

The journal already draws one line — the model's XI against mine, captain
doubled, no autosubs. This module asks the harder question the whole app
exists for: *which decision* cost me, in points and in title odds, and how
much has that decision type cost me all season.

Four things make it more than a bigger journal:

* **The counterfactual is deadline-guarded.** ``journal.latest_run_per_gw`` is
  imported verbatim (spec D3): among a gameweek's banked runs the newest one
  written *before* the deadline wins, and a gameweek where every run was late
  is graded with a flag rather than passed off as foresight.
* **Every squad is scored with real autosubs.** ``backtest.score_gw`` — the
  replay's scorer, with the vice fallback, the bench-boost arithmetic and the
  hit cost already in it. Imported, never modified; its simplified-autosub
  caveats (``backtest.py:36-38``) are exactly what the reconciliation gate
  below is built to catch.
* **Two currencies.** Points, and the change in P(win the mini-league) from
  v8c's Monte Carlo. A captaincy that cost two points and a place in the race
  is a different decision from one that cost two points and nothing.
* **Grades are banked, never re-derived.** ``ADVICE_HISTORY_KEEP`` is 20 and
  global, so GW1's advice is pruned within weeks (spec D2). The review runs
  once a gameweek's results are final and appends to
  ``reports/decision_ledger.json``; every reader afterwards reads the ledger.

Nothing here writes to ``advise``. The ledger is measurement.
"""

from __future__ import annotations

import pandas as pd

from gaffer.artifacts import load_components  # noqa: F401 — Task 5's import
from gaffer.backtest import score_gw
from gaffer.data import store
from gaffer.data.my_entry import (bank_my_entry, chip_for_gw, gw_history_row,
                                  load_my_gw, load_my_history,
                                  load_my_transfers, my_transfers_for_gw)
from gaffer.journal import _code_of_element, latest_run_per_gw

__all__ = ["ACTUAL_COLS", "CHIP_SCORING", "LANES", "MISS_BAR", "PWIN_LANES",
           "SQUAD_CHIPS", "actuals_for_gw", "code_of_element", "grade_gw",
           "grade_gw_from", "hindsight_gap", "hindsight_xi", "label_for",
           "lane_bench", "lane_captaincy", "lane_chip", "lane_transfers",
           "model_decisions", "my_decisions", "pair_by_position",
           "picks_from_squad", "price_lanes", "price_lanes_for_gw",
           "reviewable_gws", "score_gw", "score_squad", "swap_slots"]

ACTUAL_COLS = ["code", "total_points", "minutes", "position"]
"""Exactly the columns :func:`gaffer.backtest.score_gw` reads, in its order."""

PLAYER_GW = "live/player_gw.parquet"

XI_SIZE = 11
"""Picks at a higher ``position`` than this are the bench, in that order."""


def code_of_element() -> dict[int, int]:
    """``element -> code`` off the live players table.

    A re-export of ``journal._code_of_element`` rather than a copy of it:
    ``journal.py`` is import-only this cycle (spec §5) and its row shape is
    pinned by existing tests, so the sharing goes this way round.
    """
    return _code_of_element()


def actuals_for_gw(gw: int) -> pd.DataFrame:
    """One row per code for ``gw``, shaped for :func:`score_gw`.

    Double gameweeks are aggregated here rather than left to the caller,
    which is the join ``backtest``'s docstring records having learned the
    hard way: ``score_gw`` builds a dict off this frame, so a second row for
    a code silently drops one of his two matches.

    Only the newest season is read. The live frame carries several, and GW2
    of 2022-23 is not GW2 of this one.

    An empty frame with the right columns for every failure — no file, no
    such gameweek, an unreadable parquet. ``run_review`` reads emptiness as
    "not reviewable" and says so.
    """
    empty = pd.DataFrame(columns=ACTUAL_COLS)
    if not store.exists(PLAYER_GW):
        return empty
    try:
        frame = store.load(PLAYER_GW)
    except Exception:  # noqa: BLE001 — an unreadable frame is a missing one
        return empty
    if frame.empty:
        return empty
    if "season_idx" in frame.columns:
        frame = frame[frame["season_idx"] == frame["season_idx"].max()]
    frame = frame[pd.to_numeric(frame["gw"], errors="coerce") == int(gw)]
    if frame.empty:
        return empty
    grouped = frame.groupby("code", as_index=False).agg(
        total_points=("total_points", "sum"), minutes=("minutes", "sum"),
        position=("position", "first"))
    grouped["code"] = grouped["code"].astype("int64")
    grouped["total_points"] = pd.to_numeric(
        grouped["total_points"], errors="coerce").fillna(0).astype("int64")
    grouped["minutes"] = pd.to_numeric(
        grouped["minutes"], errors="coerce").fillna(0).astype("int64")
    grouped["position"] = grouped["position"].astype(str)
    return grouped[ACTUAL_COLS]


def reviewable_gws() -> list[int]:
    """Every gameweek whose results are final, ascending.

    Presence in ``player_gw.parquet`` *is* the ``data_checked`` gate:
    ``refresh_live`` drops every gameweek FPL has not marked so, which is the
    same reasoning ``artifacts.ingested_through`` documents. Reviewing a week
    FPL is still adjusting would bank a grade against numbers that then move.
    """
    if not store.exists(PLAYER_GW):
        return []
    try:
        frame = store.load(PLAYER_GW)
    except Exception:  # noqa: BLE001
        return []
    if frame.empty:
        return []
    if "season_idx" in frame.columns:
        frame = frame[frame["season_idx"] == frame["season_idx"].max()]
    gws = pd.to_numeric(frame["gw"], errors="coerce").dropna()
    return sorted({int(g) for g in gws})


def _codes(entries) -> list[int]:
    return [int(e["code"]) for e in (entries or [])
            if isinstance(e, dict) and e.get("code") is not None]


def model_decisions(gw: int) -> dict | None:
    """What the model said before ``gw``'s deadline, or ``None``.

    ``None`` is not an edge case. ``ADVICE_HISTORY_KEEP`` is 20 runs across
    all gameweeks, so by October GW1's advice is gone and its ledger row is
    marked ``no_advice`` with every lane null — null, not zero, because "the
    model had no opinion" and "the model agreed with me" are different facts
    and only one of them is a grade (spec G2).
    """
    payload = latest_run_per_gw().get(int(gw))
    if payload is None:
        return None
    captain = (payload.get("captain") or {}).get("code")
    vice = (payload.get("vice") or {}).get("code")
    chip = next((str(row.get("chip")) for row in payload.get("chip_table") or []
                 if isinstance(row, dict) and row.get("play_now")), None)
    names = {int(p["code"]): str(p.get("name", p["code"]))
             for key in ("xi", "bench", "buys", "sells")
             for p in payload.get(key) or []
             if isinstance(p, dict) and p.get("code") is not None}
    positions = {int(p["code"]): str(p.get("position", ""))
                 for key in ("xi", "bench", "buys", "sells")
                 for p in payload.get(key) or []
                 if isinstance(p, dict) and p.get("code") is not None}
    return {
        "xi": _codes(payload.get("xi")),
        "bench": _codes(payload.get("bench")),
        "captain": None if captain is None else int(captain),
        "vice": None if vice is None else int(vice),
        "buys": _codes(payload.get("buys")),
        "sells": _codes(payload.get("sells")),
        "hits": int(payload.get("hits") or 0),
        "chip": chip,
        "names": names,
        "positions": positions,
        "post_deadline": bool(payload.get("post_deadline")),
    }


def my_decisions(gw: int, *, season: str, entry_id: int,
                 raw_dir=None) -> dict | None:
    """What I actually did in ``gw``, off the bank, or ``None``.

    Off the bank and never off the API: ``run_review`` banks first and grades
    second, so this function is a pure read and a gameweek nobody banked is a
    gameweek nobody grades (spec G2).

    ``xi`` is ``position`` 1-11 in that order and ``bench`` is 12-15 in that
    order, because bench order is one of the four graded lanes and a set
    would throw the lane away. The armband comes from ``is_captain`` rather
    than from the multiplier, which is 3 under a triple captain and 1 under a
    bench boost.
    """
    picks = load_my_gw(season, entry_id, gw, raw_dir)
    if picks is None:
        return None
    history = load_my_history(season, entry_id, raw_dir)
    row = gw_history_row(history, gw) or {}
    code_of = code_of_element()

    ordered, unresolved = [], 0
    for pick in picks:
        try:
            slot = int(pick["position"])
            element = int(pick["element"])
        except (KeyError, TypeError, ValueError):
            unresolved += 1
            continue
        code = code_of.get(element)
        if code is None:
            unresolved += 1
            continue
        ordered.append((slot, int(code), bool(pick.get("is_captain")),
                        bool(pick.get("is_vice_captain"))))
    ordered.sort(key=lambda r: r[0])

    notices = []
    if unresolved:
        notices.append(
            f"{unresolved} pick could not be resolved to a player and was "
            f"dropped from the grade" if unresolved == 1 else
            f"{unresolved} picks could not be resolved to players and were "
            f"dropped from the grade")
    cost = int(row.get("event_transfers_cost", 0) or 0)
    return {
        "xi": [code for slot, code, _, _ in ordered if slot <= XI_SIZE],
        "bench": [code for slot, code, _, _ in ordered if slot > XI_SIZE],
        "captain": next((c for _, c, cap, _ in ordered if cap), None),
        "vice": next((c for _, c, _, vc in ordered if vc), None),
        "chip": chip_for_gw(history, gw),
        "hits": cost // 4,
        "official_gross": (int(row["points"]) if row.get("points") is not None
                           else None),
        "official_cost": cost,
        "points_on_bench": (int(row["points_on_bench"])
                            if row.get("points_on_bench") is not None
                            else None),
        "transfers": my_transfers_for_gw(
            load_my_transfers(season, entry_id, raw_dir), gw),
        "notices": notices,
    }


CHIP_SCORING = {"bboost": (2, True), "3xc": (3, False)}
"""``chip -> (captain multiplier, bench boost)`` for the two chips that change
how a *fixed* fifteen scores. Everything else scores the ordinary way."""

SQUAD_CHIPS = ("wildcard", "freehit")
"""Chips that change *which* fifteen you own rather than how it scores. There
is no same-squad counterfactual for one of these, so the chip lane declines to
grade a week either side played one (see :func:`lane_chip`)."""

NO_PLAYER = -1
"""``score_gw`` looks the armband up in a points dict, so an absent captain
has to be a code that cannot match. A squad with no captain flag at all is
rare and must not be a crash."""

MISS_BAR = 6
"""Points a move I skipped must have returned *over its replacement* before
the review calls it a Miss (spec D5). Six is a goal and change: below it the
model was right by less than one bounce of the ball."""

LANES = ("transfers", "captaincy", "bench", "chip")
"""The pre-registered order. Stable, because a season ledger whose columns
move is a ledger nobody can read across weeks (CONVENTIONS.md §2)."""


def score_squad(actuals: pd.DataFrame, *, xi, bench, captain, vice, hits,
                chip=None) -> int:
    """One squad's real points: :func:`score_gw` with the chip decoded.

    Adds no arithmetic. The autosubs, the vice fallback and the four points a
    hit costs are all ``backtest``'s, which is the point — the review grades
    against the same scorer the season replay is measured with, so a lane
    delta and a replay delta are the same kind of number.
    """
    mult, boost = CHIP_SCORING.get(str(chip or ""), (2, False))
    return int(score_gw(
        actuals, list(xi), list(bench),
        NO_PLAYER if captain is None else int(captain),
        NO_PLAYER if vice is None else int(vice),
        int(hits), captain_mult=mult, bench_boost=boost))


def swap_slots(xi, bench, pairs) -> tuple[list[int], list[int]] | None:
    """Replace each ``out`` with its ``in`` *where the out was sitting*.

    Slot-preserving on purpose. A counterfactual that rebuilt the eleven from
    scratch would be answering a selection question inside a transfer lane,
    and the incoming player would quietly inherit the best slot available
    rather than the one his predecessor held.

    ``None`` when an ``out`` is in neither list: that is the model naming a
    player I never owned, and there is no squad to score.
    """
    xi, bench = list(xi), list(bench)
    for out_code, in_code in pairs:
        if out_code in xi:
            xi[xi.index(out_code)] = in_code
        elif out_code in bench:
            bench[bench.index(out_code)] = in_code
        else:
            return None
    return xi, bench


def pair_by_position(outs, ins, positions) -> list[tuple[int, int]] | None:
    """Match sells to buys by position, in the order each was listed.

    FPL's own constraint: a transfer swaps like for like, so a two-move week
    is two independent position-preserving swaps and the pairing is
    determined. ``None`` when the two sides do not have the same positional
    shape — a squad that is 4 defenders after the move and 5 before it is not
    a squad, and grading against one would be grading against a fiction.
    """
    outs, ins = list(outs), list(ins)
    if len(outs) != len(ins):
        return None
    pool: dict[str, list[int]] = {}
    for code in ins:
        pool.setdefault(str(positions.get(int(code), "")), []).append(int(code))
    pairs: list[tuple[int, int]] = []
    for code in outs:
        bucket = pool.get(str(positions.get(int(code), "")))
        if not bucket:
            return None
        pairs.append((int(code), bucket.pop(0)))
    return pairs


def hindsight_gap(best: int, actual: int) -> int:
    """Selection EV left on the table: the best legal eleven, less mine."""
    return int(best) - int(actual)


def label_for(delta_pts, delta_pwin, *, aligned: bool) -> str | None:
    """The pre-registered band for one lane (spec D5).

    ``None`` for an ungraded lane, which is not a band and must never be
    rendered as one. ``aligned`` short-circuits everything: a lane where I
    made the model's own choice is Aligned however the week turned out, and
    calling it a Blunder because the model's own pick blanked would be
    grading the outcome instead of the decision.

    Brilliant needs *both* currencies. A move that gained four points and cost
    title odds is a Good week for the points column and a bad week for the
    thing being played for, so with no Δwin% available the band tops out at
    Good — the honest answer when half the evidence is missing.
    """
    if delta_pts is None:
        return None
    if aligned:
        return "Aligned"
    value = float(delta_pts)
    if value >= 4 and (delta_pwin or 0.0) > 0:
        return "Brilliant"
    if value >= 1:
        return "Good"
    if value <= -4:
        return "Blunder"
    if value <= -1:
        return "Inaccuracy"
    return "Aligned"


def _lane(name: str, cf: dict | None, mine: dict, actuals: pd.DataFrame, *,
          note: str | None, aligned: bool, mine_label: str,
          model_label: str) -> dict:
    """One graded lane. ``cf`` is my squad with exactly one thing changed.

    Both sides are scored with :func:`score_squad`, so the delta is "my
    choice minus the model's, both on what really happened". ``None`` for
    ``cf`` means the lane could not be built and the delta is null with the
    note saying why — spec G2's "null, not zero".
    """
    if cf is None:
        return {"lane": name, "delta_pts": None, "delta_pwin": None,
                "label": None, "aligned": False, "mine": mine_label,
                "model": model_label, "note": note}
    delta = score_squad(actuals, **mine) - score_squad(actuals, **cf)
    return {"lane": name, "delta_pts": int(delta), "delta_pwin": None,
            "label": label_for(delta, None, aligned=aligned),
            "aligned": bool(aligned), "mine": mine_label,
            "model": model_label, "note": note, "cf": cf}


def _name(names: dict, code) -> str:
    if code is None:
        return "none"
    return str((names or {}).get(int(code), code))


def lane_transfers(mine: dict, model: dict, actuals: pd.DataFrame, *,
                   my_transfers: list[dict], positions: dict,
                   code_of: dict | None = None) -> dict:
    """My transfer set against the model's, hits included.

    Two swaps, in order. First my own week is *undone* — each player I
    brought in goes back to the one I sold, in his slot — because the
    counterfactual starts from the fifteen I owned at the deadline and not
    from the one I ended the week with. Then the model's moves are applied to
    that pre-transfer squad.

    The armband follows the squad: if the model's counterfactual sells the
    player I captained, the armband goes to the model's captain when he is in
    the resulting eleven and to my vice otherwise, which is FPL's own
    fallback rather than a rule invented here.
    """
    code_of = code_of or {}
    names, note = model.get("names") or {}, None
    label_mine = ", ".join(_name(names, c) for c in model.get("sells") or []) \
        or "no move"
    undo = []
    for row in my_transfers or []:
        try:
            got = int(code_of.get(int(row["element_in"]), row["element_in"]))
            gone = int(code_of.get(int(row["element_out"]), row["element_out"]))
        except (KeyError, TypeError, ValueError):
            continue
        undo.append((got, gone))
    pre = swap_slots(mine["xi"], mine["bench"], undo)
    label_model = " / ".join(
        f"{_name(names, out)}->{_name(names, got)}"
        for out, got in zip(model.get("sells") or [], model.get("buys") or [])
    ) or "no move"
    mine_label = " / ".join(
        f"{_name(names, out)}->{_name(names, got)}" for got, out in undo
    ) or "no move"
    if pre is None:
        return _lane("transfers", None, mine, actuals,
                     note="a player you transferred in is not in your banked "
                          "squad, so the pre-deadline fifteen could not be "
                          "rebuilt",
                     aligned=False, mine_label=mine_label,
                     model_label=label_model)
    pairs = pair_by_position(model.get("sells") or [],
                             model.get("buys") or [], positions)
    if pairs is None:
        return _lane("transfers", None, mine, actuals,
                     note="the model's moves do not pair up by position, so "
                          "there is no legal counterfactual squad",
                     aligned=False, mine_label=mine_label,
                     model_label=label_model)
    swapped = swap_slots(pre[0], pre[1], pairs)
    if swapped is None:
        return _lane("transfers", None, mine, actuals,
                     note=f"the model sold {label_mine}, who was not in your "
                          f"squad — there is no counterfactual to score",
                     aligned=False, mine_label=mine_label,
                     model_label=label_model)
    xi, bench = swapped
    captain = mine["captain"] if mine["captain"] in xi + bench else None
    if captain is None:
        captain = model.get("captain") if model.get("captain") in xi \
            else mine["vice"]
    cf = {"xi": xi, "bench": bench, "captain": captain,
          "vice": mine["vice"] if mine["vice"] in xi + bench else captain,
          "hits": int(model.get("hits") or 0), "chip": mine["chip"]}
    aligned = (sorted(xi + bench) == sorted(mine["xi"] + mine["bench"])
               and int(model.get("hits") or 0) == int(mine["hits"]))
    return _lane("transfers", cf, mine, actuals, note=None, aligned=aligned,
                 mine_label=mine_label, model_label=label_model)


def lane_captaincy(mine: dict, model: dict, actuals: pd.DataFrame) -> dict:
    """My armband against the model's, on my own eleven.

    Only comparable when the model's captain is in my eleven. You cannot
    captain a player you did not field, so a model captain I never owned is
    not a decision I declined to take — it is a decision that was never
    available, and grading it would charge me for a squad I could not have
    had. (That cost belongs to the transfers lane, where it already is.)
    """
    names = model.get("names") or {}
    mine_label, model_label = (_name(names, mine["captain"]),
                               _name(names, model.get("captain")))
    if model.get("captain") is None or int(model["captain"]) not in mine["xi"]:
        return _lane("captaincy", None, mine, actuals,
                     note="the model's captain was not in your eleven",
                     aligned=False, mine_label=mine_label,
                     model_label=model_label)
    vice = model.get("vice")
    cf = {**mine, "captain": int(model["captain"]),
          "vice": int(vice) if vice in mine["xi"] else mine["vice"]}
    aligned = mine["captain"] == int(model["captain"])
    return _lane("captaincy", cf, mine, actuals, note=None, aligned=aligned,
                 mine_label=mine_label, model_label=model_label)


def lane_bench(mine: dict, model: dict, actuals: pd.DataFrame) -> dict:
    """My bench order against the model's, on my own fifteen.

    The model benched its own players, so its ordering is applied as a
    *ranking* over mine: my bench players it named, in its order, then the
    rest in mine. A week where nobody blanked scores zero on both sides —
    which is a real grade and not a missing one, because the ordering was
    tested by the week and cost nothing.
    """
    ranked = [c for c in (model.get("bench") or []) if c in mine["bench"]]
    order = ranked + [c for c in mine["bench"] if c not in ranked]
    names = model.get("names") or {}
    cf = {**mine, "bench": order}
    return _lane("bench", cf, mine, actuals, note=None,
                 aligned=order == list(mine["bench"]),
                 mine_label=", ".join(_name(names, c) for c in mine["bench"]),
                 model_label=", ".join(_name(names, c) for c in order))


def lane_chip(mine: dict, model: dict, actuals: pd.DataFrame) -> dict:
    """My chip decision against the model's ``play_now``.

    Bench boost and triple captain change how a fixed fifteen scores, so both
    sides are the same squad under two rulebooks and the delta is exact. A
    wildcard or a free hit changes *which* fifteen you own; there is no
    same-squad comparison, and inventing the squad a wildcard would have
    bought is a whole solve with a different budget — out of scope this cycle
    (spec §6) and null here rather than guessed.
    """
    mine_chip, model_chip = mine["chip"], model.get("chip")
    labels = (str(mine_chip or "none"), str(model_chip or "none"))
    if str(mine_chip or "") in SQUAD_CHIPS or str(model_chip or "") \
            in SQUAD_CHIPS:
        return _lane("chip", None, mine, actuals,
                     note="a wildcard or free hit changes the squad, not the "
                          "way it scores — there is no same-squad "
                          "counterfactual",
                     aligned=False, mine_label=labels[0],
                     model_label=labels[1])
    cf = {**mine, "chip": model_chip}
    return _lane("chip", cf, mine, actuals, note=None,
                 aligned=str(mine_chip or "") == str(model_chip or ""),
                 mine_label=labels[0], model_label=labels[1])


def _misses(mine: dict, model: dict, actuals: pd.DataFrame) -> list[dict]:
    """Moves the model flagged, I did not make, and that hauled anyway.

    Not a fifth lane: the transfers lane already prices the whole set against
    the whole set, and this is the human-readable line item inside it — "you
    were told about Guehi and he returned nine over the man you kept". Paired
    by position against the model's own sell, so the number is a *difference*
    and not a scoreline; an unpaired buy is skipped rather than compared
    against nothing.
    """
    owned = set(mine["xi"]) | set(mine["bench"])
    pairs = pair_by_position(model.get("sells") or [],
                             model.get("buys") or [],
                             model.get("positions") or {}) or []
    points = dict(zip(actuals["code"], actuals["total_points"]))
    names = model.get("names") or {}
    out = []
    for sold, bought in pairs:
        if bought in owned or sold not in owned:
            continue
        gain = int(points.get(bought, 0) or 0) - int(points.get(sold, 0) or 0)
        if gain >= MISS_BAR:
            out.append({"code": int(bought), "name": _name(names, bought),
                        "over": _name(names, sold), "gain": int(gain)})
    return out


def hindsight_xi(squad15, actuals: pd.DataFrame):
    """The best legal eleven and armband out of a fifteen, by actual points.

    Exhaustive: fifteen choose eleven is 1365 combinations and the formation
    check is a Counter, so the honest answer is cheaper than any clever one.
    Bench-boost and hit arithmetic are deliberately excluded — this measures
    *selection*, and folding a chip into it would price two decisions as one.

    Returns ``(xi, captain, points)``; ``([], None, 0)`` for a squad too small
    to field a legal eleven, which is what a partially-resolved bank looks
    like.
    """
    from itertools import combinations

    from gaffer.backtest import _formation_legal

    codes = [int(c) for c in squad15]
    points = dict(zip(actuals["code"], actuals["total_points"]))
    pos = dict(zip(actuals["code"], actuals["position"]))
    best: tuple[list[int], int | None, int] = ([], None, 0)
    for combo in combinations(codes, 11):
        if not _formation_legal([str(pos.get(c, "MID")) for c in combo]):
            continue
        armband = max(combo, key=lambda c: int(points.get(c, 0) or 0))
        total = sum(int(points.get(c, 0) or 0) for c in combo) \
            + int(points.get(armband, 0) or 0)
        if total > best[2]:
            best = (list(combo), int(armband), int(total))
    return best


def grade_gw_from(gw: int, mine: dict, model: dict | None,
                  actuals: pd.DataFrame, pwin: dict | None = None,
                  pwin_meta: dict | None = None) -> dict:
    """One ledger row from decisions already read. Pure; no I/O, no network.

    Split out from :func:`grade_gw` so the taxonomy can be tested against
    hand-scored squads rather than against a filesystem, and so the Δwin%
    pricing in Task 5 has exactly one place to attach.

    ``model is None`` — the advice for this gameweek has been pruned (spec
    D2) — gives a ``no_advice`` row: every lane null, no accuracy, and the
    reconciliation and hindsight still computed, because those do not need
    the model at all and are the half of the row that stays true forever.
    """
    my_points = score_squad(actuals, **{k: mine[k] for k in
                                        ("xi", "bench", "captain", "vice",
                                         "hits", "chip")})
    my_squad = {k: mine[k] for k in ("xi", "bench", "captain", "vice", "hits",
                                     "chip")}
    notices = list(mine.get("notices") or [])

    gross, cost = mine.get("official_gross"), int(mine.get("official_cost", 0))
    if gross is None:
        official, reconciled = None, None
        notices.append("no official score for this gameweek — the entry "
                       "history was not banked, so nothing reconciled")
    else:
        official = int(gross) - cost
        reconciled = official == my_points

    bench_points = sum(
        int(p) for c, p in zip(actuals["code"], actuals["total_points"])
        if int(c) in set(mine["bench"]))
    best_xi, best_captain, best_points = hindsight_xi(
        list(mine["xi"]) + list(mine["bench"]), actuals)

    row = {
        "gw": int(gw),
        "no_advice": model is None,
        "post_deadline": bool((model or {}).get("post_deadline")),
        "my_points": int(my_points),
        "official_points": official,
        "official_gross": None if gross is None else int(gross),
        "hits": int(mine["hits"]),
        "reconciled": reconciled,
        "chip": mine["chip"],
        "model_chip": (model or {}).get("chip"),
        "points_on_bench": mine.get("points_on_bench"),
        "our_bench_points": int(bench_points),
        "hindsight": {"points": int(best_points), "xi": best_xi,
                      "captain": best_captain,
                      "gap": hindsight_gap(best_points, my_points)},
        "misses": [],
        "notices": notices,
    }
    row.update(pwin_meta or {})

    if model is None:
        row["lanes"] = [{"lane": name, "delta_pts": None, "delta_pwin": None,
                         "label": None, "aligned": False, "mine": None,
                         "model": None,
                         "note": "no banked advice survives for this "
                                 "gameweek"} for name in LANES]
        row["model_points"] = None
        row["accuracy"] = None
        return row

    positions = model.get("positions") or {}
    lanes = [
        lane_transfers(my_squad, model, actuals,
                       my_transfers=mine.get("transfers") or [],
                       positions=positions,
                       code_of=mine.get("code_of") or {}),
        lane_captaincy(my_squad, model, actuals),
        lane_bench(my_squad, model, actuals),
        lane_chip(my_squad, model, actuals),
    ]

    # The composite: my squad with every *comparable* lane taken from the
    # model at once. Applied in the registered order because the lanes
    # compose — a transfer can move the player the armband is on — and an
    # incomparable lane leaves its part of the squad at mine rather than
    # dropping out of the denominator, so accuracy always compares two whole
    # squads.
    composite = dict(my_squad)
    for lane in lanes:
        cf = lane.get("cf")
        if cf is None:
            continue
        if lane["lane"] == "transfers":
            composite = {**composite, "xi": cf["xi"], "bench": cf["bench"],
                         "captain": cf["captain"], "vice": cf["vice"],
                         "hits": cf["hits"]}
        elif lane["lane"] == "captaincy" and cf["captain"] in composite["xi"]:
            composite = {**composite, "captain": cf["captain"],
                         "vice": cf["vice"]}
        elif lane["lane"] == "bench":
            ranked = [c for c in (model.get("bench") or [])
                      if c in composite["bench"]]
            composite = {**composite, "bench": ranked + [
                c for c in composite["bench"] if c not in ranked]}
        elif lane["lane"] == "chip":
            composite = {**composite, "chip": cf["chip"]}
    model_points = score_squad(actuals, **composite)

    pwin = pwin or {}
    for lane in lanes:
        if lane["lane"] in PWIN_LANES:
            lane["delta_pwin"] = pwin.get(lane["lane"])
        else:
            lane["delta_pwin"] = 0.0
            lane["note"] = lane["note"] or (
                "title odds price the starting eleven and the armband; a "
                "bench order and a chip do not move them")
        lane["label"] = label_for(lane["delta_pts"], lane["delta_pwin"],
                                  aligned=lane["aligned"])
    row["lanes"] = [{k: v for k, v in lane.items() if k != "cf"}
                    for lane in lanes]
    row["model_points"] = int(model_points)
    # Floored at 1 so a gameweek where the model's own squad scored nothing
    # cannot divide by zero, and capped at 100 so beating the model reads as
    # a perfect week — the surplus is the Brilliant lane's story, not the
    # dial's (spec D5).
    row["accuracy"] = int(min(100, round(100 * my_points
                                         / max(model_points, 1))))
    row["misses"] = _misses(my_squad, model, actuals)
    return row


PWIN_LANES = ("transfers", "captaincy")
"""The lanes a win probability can see.

``league_sim.effective_picks`` normalises any squad to its eleven starters and
one armband — the bench scores nothing and a chip's multipliers are stripped,
because a bench-boost week read as a *rate* would hand that manager four extra
players for the whole rest of the season. So a bench reordering and a chip
decision are invisible to the engine by construction, and simulating them
would spend two Monte Carlo runs to rediscover a zero. They carry ``0.0`` and
a note instead, which is the true answer plus the reason.
"""

PWIN_DP = 1
"""Decimal places on a Δ in percentage points. At ``n = 2000`` the counting
granularity is 0.05pp, so one decimal place is already finer than the
instrument; the row carries ``pwin_granularity_pp`` so nobody has to guess."""


def picks_from_squad(squad: dict, element_of: dict[int, int]) -> list[dict]:
    """A counterfactual squad as the pick dicts ``effective_picks`` reads.

    ``position`` is the load-bearing field: 1-11 for the eleven, 12-15 for the
    bench, in order. Without it ``effective_picks`` falls through to its
    stored-multiplier branch and the counterfactual would score its own bench
    — see ``league_sim.py:251-291``. A code with no element this season is
    dropped rather than given an invented id, which would price a different
    player's squad.
    """
    out, started, benched = [], 0, XI_SIZE
    ordered = ([(code, True) for code in squad["xi"]]
               + [(code, False) for code in squad["bench"]])
    for code, starts in ordered:
        element = element_of.get(int(code))
        if element is None:
            continue
        # The bench numbers from 12 whatever the eleven's length: a squad
        # short of eleven resolved players is still a squad whose bench must
        # read as a bench to ``effective_picks``, which splits on ``position``
        # <= XI_SIZE and would otherwise start it.
        if starts and started < XI_SIZE:
            started += 1
            slot = started
        else:
            benched += 1
            slot = benched
        out.append({"element": int(element), "position": slot,
                    "multiplier": (0 if slot > XI_SIZE
                                   else 2 if code == squad.get("captain")
                                   else 1),
                    "is_captain": code == squad.get("captain"),
                    "is_vice_captain": code == squad.get("vice")})
    return out


def price_lanes(cfg, inputs, mine: dict, counterfactuals: dict,
                element_of: dict[int, int], *, simulate=None
                ) -> tuple[dict[str, float], str | None]:
    """``{lane: Δ win% in percentage points}`` for the priceable lanes.

    One baseline run with my real squad, then one run per counterfactual with
    my ``Entry.picks`` swapped and *everything else identical* — same seed,
    same ``n``, same drift. That pairing is the whole method: two Monte Carlo
    runs differing in their seed differ by the seed, and the difference of
    seeds is not the difference of decisions (CONVENTIONS.md §1).

    The sign matches ``delta_pts``: mine minus the model's, so a negative
    number is a decision that cost me ground.

    Never raises. Every failure comes back as ``({}, notice)`` and the row is
    graded in points alone (spec F2).
    """
    import dataclasses

    from gaffer.league_sim import SIM_SEED, simulate_league

    simulate = simulate or simulate_league
    wanted = {lane: cf for lane, cf in counterfactuals.items()
              if lane in PWIN_LANES and cf is not None}
    if not wanted:
        return {}, None
    if not any(entry.is_me for entry in inputs.entries):
        return {}, ("your entry is not in the simulated league, so no "
                    "decision could be priced in title odds")
    kwargs = {"n": int(getattr(cfg, "sim_n", 2000)), "seed": SIM_SEED,
              "rival_drift": float(getattr(cfg, "rival_drift", 0.5))}

    def _with(picks):
        return dataclasses.replace(
            inputs, entries=[dataclasses.replace(e, picks=picks) if e.is_me
                             else e for e in inputs.entries])

    try:
        base = simulate(_with(picks_from_squad(mine, element_of)), **kwargs)
        out = {}
        for lane, cf in wanted.items():
            run = simulate(_with(picks_from_squad(cf, element_of)), **kwargs)
            out[lane] = round((base.p_win - run.p_win) * 100.0, PWIN_DP)
        return out, None
    except Exception as exc:  # noqa: BLE001 — the second currency is optional
        return {}, f"title odds not priced: {exc}"


def price_lanes_for_gw(cfg, client, gw: int, mine: dict,
                       counterfactuals: dict, element_of: dict[int, int]
                       ) -> tuple[dict[str, float], str | None]:
    """:func:`price_lanes` with the gameweek's inputs rebuilt first.

    ``build_inputs(cfg, client, gw=N)`` reads ``components_gw{N}.parquet`` and
    takes every entry's squad from the gameweek before, so this prices GW N's
    decision under the expectations that stood at GW N's own deadline.

    A gameweek whose component parquet has been deleted — and **GW1, which
    never had one**, because the first solve of a season is GW2's — comes back
    absent with a notice. Spec D4 requires exactly that rather than a silent
    zero.
    """
    try:
        from gaffer.league_sim import build_inputs

        inputs = build_inputs(cfg, client, gw=int(gw))
    except Exception as exc:  # noqa: BLE001 — no parquet, no league, no net
        return {}, (f"title odds not priced for GW{int(gw)}: {exc}")
    return price_lanes(cfg, inputs, mine, counterfactuals, element_of)


def grade_gw(gw: int, *, cfg, client=None) -> dict | None:
    """One gameweek's full grade, read off disk and priced. ``None`` when my
    picks for that week were never banked.

    The order matters: everything that can be answered without a network is
    answered first, so an FPL outage costs the Δwin% column and nothing else.
    """
    from gaffer.league_sim import SIM_SEED

    season = str(getattr(cfg, "current_season", "") or "")
    entry_id = int(getattr(cfg, "entry_id", 0) or 0)
    mine = my_decisions(gw, season=season, entry_id=entry_id)
    if mine is None:
        return None
    frame = actuals_for_gw(gw)
    model = model_decisions(gw)
    mine = {**mine, "code_of": {e: c for e, c in code_of_element().items()}}

    n = int(getattr(cfg, "sim_n", 2000) or 2000)
    meta = {"pwin_n": n, "pwin_seed": SIM_SEED,
            "pwin_granularity_pp": round(100.0 / max(n, 1), 3)}
    if model is None or client is None:
        row = grade_gw_from(gw, mine, model, frame, pwin_meta=meta)
        if model is not None:
            row["notices"] = list(row["notices"]) + [
                "no FPL client available, so nothing was priced in title "
                "odds"]
        return row

    my_squad = {k: mine[k] for k in ("xi", "bench", "captain", "vice", "hits",
                                     "chip")}
    counterfactuals = {lane: _cf_squad(lane, my_squad, model)
                       for lane in PWIN_LANES}
    element_of = {c: e for e, c in code_of_element().items()}
    priced, notice = price_lanes_for_gw(cfg, client, gw, my_squad,
                                        counterfactuals, element_of)
    row = grade_gw_from(gw, mine, model, frame, pwin=priced, pwin_meta=meta)
    if notice:
        row["notices"] = list(row["notices"]) + [notice]
    return row


def _cf_squad(lane: str, mine: dict, model: dict) -> dict | None:
    """Rebuild one lane's counterfactual squad for the pricing pass.

    The lane builders drop their ``cf`` before the row is banked — the ledger
    holds grades, not squads — so the two priceable lanes are rebuilt here
    from the same two functions rather than from a second implementation.
    """
    import pandas as pd

    blank = pd.DataFrame(columns=ACTUAL_COLS)
    if lane == "transfers":
        built = lane_transfers(mine, model, blank, my_transfers=[],
                               positions=model.get("positions") or {})
    else:
        built = lane_captaincy(mine, model, blank)
    return built.get("cf")
