"""Candidate 9's reading: would a blended league stance differ from the focus's?

ROADMAP candidate 9 ("A blended league stance (v15 deferred): per-league λ
and cover tables merged by weight. Chasing in one league and defending in
another largely cancel, so it needs a replay to justify before it touches
protected solver code"; holiday F-72). The blend is not built here: this
reads whether the leagues the manager is in would pull the focus league's λ
far enough, and in enough directions, to be worth a replay.

The leagues are the ones the League hub's overview lists, read the same way
(``web/routers/league.py`` ``_league_rows``, repeated here rather than
imported from the router): the entry payload's classic leagues with
``league_type == "x"`` (private), started (a ``rank_count``) and with more
than one entry, each from page 1 of its standings. My total is my row on that
page, or the entry payload's ``summary_overall_points`` when I am not on it.
The stance and its ``lam`` are ``league_mode.compute_strategy``'s with
``history=None``, the overview's documented path (every sigma the fallback),
at the entry's ``current_event`` + 1. The focus league is ``cfg.league_id``.

The merge: each league's λ weighted by its entry count, capped at the focus
league's entry count, so a 400-entry office league cannot outvote the league
the manager chose; ``merged = Σ w·λ / Σ w`` over every league read, the focus
included. A league *disagrees* when its λ and the focus's are of opposite
sign (one chases, the other defends); a neutral league, or a neutral focus,
disagrees with nothing, since a zero λ pulls the blend nowhere by itself.
``disagree_share`` is over the leagues other than the focus.

The pass rule, written here before the script has run on real data: the
blend earns a replay (verdict ``replay``, an arm and the Mac's) iff two or
more leagues disagree in sign with the focus and ``|merged − focus| ≥
MERGE_GAP`` (0.1) on the unrounded floats; otherwise the verdict is ``the
focus league is the blend``. A focus league the overview does not list, or
one whose page will not read, decides nothing: the line says so and the
verdict is ``none``.

Read-only. It fetches with a client whose raw snapshots go to a temporary
directory, so nothing under ``data/`` is written. No ``config.toml``, no entry
id, no leagues or no network prints one ``LEAGUE_BLEND`` line saying so and
exits 0, never a traceback, because the night shift transcribes the line
whatever it says (``tests/test_readings_cold.py``).

    uv run python scripts/league_blend.py
"""

from __future__ import annotations

import json
import math
import tempfile

import httpx
import pandas as pd

from gaffer.config import load_config
from gaffer.data.league import STANDINGS_COLS
from gaffer.errors import GafferError
from gaffer.league_mode import LeagueParams, compute_strategy

MERGE_GAP = 0.1
"""How far the merged λ must move from the focus's to earn a replay."""

MIN_DISAGREE = 2
"""How many leagues must pull against the focus to earn a replay."""

REPLAY = "replay"
FOCUS_IS_BLEND = "the focus league is the blend"

# A drifted payload raises KeyError or TypeError; a bad number ValueError.
_UNREADABLE = (GafferError, httpx.HTTPError, KeyError, TypeError, ValueError)


def _maybe_int(value) -> int | None:
    return None if value is None else int(value)


def _sign(lam: float) -> int:
    return 0 if lam == 0 else (1 if lam > 0 else -1)


def private_leagues(entry: dict) -> list[dict]:
    """The started private classic leagues with a rival in them."""
    out = []
    for league in (entry.get("leagues") or {}).get("classic") or []:
        if league.get("league_type") != "x":
            continue
        entries = _maybe_int(league.get("rank_count"))
        if entries is None or entries <= 1:
            continue
        out.append({"id": int(league["id"]), "name": str(league["name"]),
                    "entries": entries})
    return out


def league_strategy(results: list[dict], *, my_entry: int, my_total: int,
                    gw: int | None, params: LeagueParams) -> tuple[float, str]:
    """``(lam, stance)`` off one standings page, as the overview reads it."""
    mine = next((r for r in results if int(r["entry"]) == my_entry), None)
    total = int(mine["total"]) if mine else my_total
    rivals = [r for r in results if int(r["entry"]) != my_entry]
    if not rivals:
        # The overview frames no stance for such a page either (``would``
        # stays None there), so it is unread here, not a neutral λ.
        raise ValueError("no rival on page 1")
    frame = pd.DataFrame(rivals, columns=STANDINGS_COLS)
    strat = compute_strategy(total, frame, (gw or 0) + 1, history=None,
                             my_entry=my_entry, params=params)
    return float(strat.lam), str(strat.stance)


def blend(rows: list[dict], focus_id: int) -> dict:
    """The ``LEAGUE_BLEND`` payload over the leagues read.

    Each row is ``{id, name, entries, lam, stance}``; the focus must be one
    of them, or nothing is decided."""
    focus = next((r for r in rows if r["id"] == focus_id), None)
    leagues = [{"id": r["id"], "name": r["name"], "entries": r["entries"],
                "lam": round(r["lam"], 4), "stance": r["stance"]}
               for r in rows]
    if focus is None:
        return {"n": len(rows), "focus": focus_id, "leagues": leagues,
                "verdict": "none",
                "reason": f"focus league {focus_id} is not among the "
                          f"private leagues read"}
    cap = focus["entries"]
    weights = [min(r["entries"], cap) for r in rows]
    merged = sum(w * r["lam"] for w, r in zip(weights, rows)) / sum(weights)
    others = [r for r in rows if r["id"] != focus_id]
    disagree = [r["id"] for r in others
                if _sign(r["lam"]) * _sign(focus["lam"]) < 0]
    gap = abs(merged - focus["lam"])
    earns = len(disagree) >= MIN_DISAGREE and gap >= MERGE_GAP
    return {"n": len(rows), "focus": focus_id,
            "focus_lam": round(focus["lam"], 4),
            "merged_lam": round(merged, 4), "gap": round(gap, 4),
            "disagree": disagree,
            "disagree_share": (round(len(disagree) / len(others), 4)
                               if others else None),
            "leagues": leagues,
            "verdict": REPLAY if earns else FOCUS_IS_BLEND,
            "reason": (f"{len(disagree)} league(s) pull against the focus "
                       f"and the blend moves λ by {gap:.3f} "
                       f"(needs ≥ {MIN_DISAGREE} and ≥ {MERGE_GAP})")}


def _empty(reason: str) -> dict:
    return {"n": 0, "verdict": "none", "reason": reason}


def blend_reading(client, cfg) -> dict:
    """Read every private league the overview lists and blend their λ."""
    entry = client.get_entry(cfg.entry_id)
    my_total = int(entry.get("summary_overall_points") or 0)
    gw = _maybe_int(entry.get("current_event"))
    params = LeagueParams.from_config(cfg)
    leagues = private_leagues(entry)
    if not leagues:
        return _empty("no started private league with a rival in it")
    rows, unread = [], []
    for league in leagues:
        try:
            page = client.get_league_standings(league["id"], 1)
            lam, stance = league_strategy(
                page["standings"]["results"], my_entry=cfg.entry_id,
                my_total=my_total, gw=gw, params=params)
        except _UNREADABLE as exc:
            unread.append({"id": league["id"],
                           "reason": f"{type(exc).__name__}: {exc}"[:80]})
            continue
        if not math.isfinite(lam):
            unread.append({"id": league["id"], "reason": "non-finite lam"})
            continue
        rows.append({**league, "lam": lam, "stance": stance})
    out = blend(rows, int(cfg.league_id))
    out["unread"] = unread
    return out


def main() -> int:
    try:
        cfg = load_config()
    except (GafferError, OSError, ValueError, KeyError, TypeError) as exc:
        # A missing file is GafferError; a malformed TOML a ValueError; a
        # missing table KeyError and a mistyped key TypeError (config.py).
        payload = _empty(f"no readable config.toml ({type(exc).__name__})")
    else:
        if not cfg.entry_id or not cfg.league_id:
            payload = _empty("no fpl.entry_id or fpl.league_id configured")
        else:
            from gaffer.api.client import FPLClient

            with tempfile.TemporaryDirectory() as raw:
                client = FPLClient(raw_dir=raw, retries=1, backoff=0)
                try:
                    payload = blend_reading(client, cfg)
                except _UNREADABLE as exc:
                    payload = _empty(f"entry unreadable: "
                                     f"{type(exc).__name__}")
    print(f"LEAGUE_BLEND {json.dumps(payload, sort_keys=True, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
