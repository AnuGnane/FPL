"""What I actually did, kept.

Everything gaffer knows about its own manager today is transient.
``fetch_my_team`` pulls my fifteen every Thursday so the MILP has a starting
squad, and the moment the solve finishes there is no record that the fetch
ever happened. That is fine for advising and useless for reviewing: a grade
for GW3 asked in December needs the squad I fielded in September, and the FPL
API will still serve it — right up until it does not, and in any case one
HTTP call per gameweek per page view is not a way to read a season.

So three stores, keyed by season and entry, deliberately different in kind:

``data/raw/league/{season}/{entry}-{gw}.json``
    my picks for one finished gameweek. **The same path, and the same bare
    list, that** :func:`gaffer.data.league.fetch_rival_picks_history` **writes
    for every other entry in my mini-league.** My entry is one of the fifty;
    giving it a private format would mean two readers of one fact. Permanent
    and idempotent: a played gameweek's picks never change again.

``data/raw/league/{season}/{entry}-history.json``
    the entry-history payload: per-gameweek points, rank, bench points,
    transfer cost, and the chips list. Replace-on-write, because it is
    cumulative — a permanent cache would freeze the season at the week it was
    first taken.

``data/raw/league/{season}/{entry}-transfers.json``
    every transfer I have made this season, each stamped with the gameweek it
    was made for. Replace-on-write for the same reason.

A note on the points arithmetic, because the reconciliation gate turns on it:
``current[].points`` is **gross** of the transfer hit and ``total_points`` is
cumulative **net**. Verified on the live API, entry 43863 2026-27: GW1 62,
GW2 101 with a cost of 4, cumulative 159 — and 62 + 101 = 163. So the net
score of a gameweek is ``points - event_transfers_cost``, and
:func:`gw_history_row` hands both numbers to the caller rather than doing the
subtraction here, where a reader could not see it.

Nothing in this module raises. It is called from ``gaffer review``, which is
called from launchd, and :func:`gaffer.snapshot.run_snapshot`'s contract
applies: one printed line whatever happens.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from gaffer.data.league import RAW_LEAGUE

__all__ = ["RAW_LEAGUE", "bank_my_entry", "bank_my_gw", "bank_my_history",
           "bank_my_transfers", "chip_for_gw", "gw_history_row", "load_my_gw",
           "load_my_history", "load_my_transfers", "my_history_path",
           "my_picks_path", "my_transfers_for_gw", "my_transfers_path"]


def my_picks_path(season: str, entry_id: int, gw: int,
                  raw_dir: Path | str | None = None) -> Path:
    """``{raw_dir}/{season}/{entry}-{gw}.json`` — the shared league layout."""
    base = Path(raw_dir) if raw_dir is not None else RAW_LEAGUE
    return base / str(season) / f"{int(entry_id)}-{int(gw)}.json"


def my_history_path(season: str, entry_id: int,
                    raw_dir: Path | str | None = None) -> Path:
    base = Path(raw_dir) if raw_dir is not None else RAW_LEAGUE
    return base / str(season) / f"{int(entry_id)}-history.json"


def my_transfers_path(season: str, entry_id: int,
                      raw_dir: Path | str | None = None) -> Path:
    base = Path(raw_dir) if raw_dir is not None else RAW_LEAGUE
    return base / str(season) / f"{int(entry_id)}-transfers.json"


def _write_atomic(path: Path, payload) -> Path:
    """Write JSON through a sibling temp file and rename.

    ``os.replace`` is atomic within a directory, so a reader sees the whole
    old file or the whole new one — never the half-written middle it would
    throw away as corrupt. The same trade ``artifacts.append_advice_history``
    and ``league_sim.append_sim_history`` make.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(payload))
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def _read_json(path: Path):
    """The parsed file, or ``None`` for absent *and* for corrupt.

    A half-written bank and no bank at all mean the same thing to every
    caller here — "this is not available, do not grade it" — and collapsing
    them is what stops one bad file from crashing a scheduled job.
    """
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def load_my_gw(season: str, entry_id: int, gw: int,
               raw_dir: Path | str | None = None) -> list[dict] | None:
    """My banked picks for ``gw``, or ``None`` if that week was never banked."""
    out = _read_json(my_picks_path(season, entry_id, gw, raw_dir))
    return list(out) if isinstance(out, list) else None


def bank_my_gw(client, entry_id: int, season: str, gw: int,
               raw_dir: Path | str | None = None) -> list[dict] | None:
    """Bank my picks for one gameweek. Idempotent; never raises.

    Returns the picks — banked or already-banked — or ``None`` when the API
    would not answer. A gameweek that is not banked is a gameweek the review
    skips, which is the documented degradation (spec §4, G2): the alternative
    is grading a squad we invented.
    """
    banked = load_my_gw(season, entry_id, gw, raw_dir)
    if banked is not None:
        return banked
    try:
        picks = list(client.get_entry_picks(int(entry_id), int(gw))["picks"])
    except Exception as exc:  # noqa: BLE001 — network / 404 / schema
        print(f"my picks for GW{gw} not banked: {exc}")
        return None
    _write_atomic(my_picks_path(season, entry_id, gw, raw_dir), picks)
    return picks


def load_my_history(season: str, entry_id: int,
                    raw_dir: Path | str | None = None) -> dict | None:
    out = _read_json(my_history_path(season, entry_id, raw_dir))
    return out if isinstance(out, dict) else None


def bank_my_history(client, entry_id: int, season: str,
                    raw_dir: Path | str | None = None) -> dict | None:
    """Refresh the banked entry history. Replace-on-write; never raises.

    A failed fetch leaves the previous bank exactly where it was rather than
    truncating it: last week's history is a strictly better answer than no
    history, and every reader here is asking about weeks that have already
    finished.
    """
    try:
        payload = client.get_entry_history(int(entry_id))
    except Exception as exc:  # noqa: BLE001 — network / 404 / schema
        print(f"my entry history not banked: {exc}")
        return None
    _write_atomic(my_history_path(season, entry_id, raw_dir), payload)
    return payload


def load_my_transfers(season: str, entry_id: int,
                      raw_dir: Path | str | None = None) -> list[dict] | None:
    out = _read_json(my_transfers_path(season, entry_id, raw_dir))
    return list(out) if isinstance(out, list) else None


def bank_my_transfers(client, entry_id: int, season: str,
                      raw_dir: Path | str | None = None
                      ) -> list[dict] | None:
    """Refresh the banked transfer list. Replace-on-write; never raises."""
    try:
        payload = list(client.get_entry_transfers(int(entry_id)))
    except Exception as exc:  # noqa: BLE001 — network / 404 / schema
        print(f"my transfers not banked: {exc}")
        return None
    _write_atomic(my_transfers_path(season, entry_id, raw_dir), payload)
    return payload


def gw_history_row(history: dict | None, gw: int) -> dict | None:
    """One gameweek's row out of ``current``, or ``None``.

    The row carries ``points`` (gross) *and* ``event_transfers_cost``
    separately; the subtraction is the reconciliation's, not this function's,
    so a reader of the ledger can see which number came from where.
    """
    for row in ((history or {}).get("current") or []):
        try:
            if int(row.get("event")) == int(gw):
                return dict(row)
        except (TypeError, ValueError):
            continue
    return None


def chip_for_gw(history: dict | None, gw: int) -> str | None:
    """The chip I played in ``gw``, or ``None``.

    Read off the history's ``chips`` list rather than the picks payload's
    ``active_chip``: the history is banked once and answers for every week of
    the season at once, including weeks whose picks endpoint has stopped
    answering.
    """
    for chip in ((history or {}).get("chips") or []):
        try:
            if int(chip.get("event")) == int(gw):
                return str(chip.get("name") or "") or None
        except (TypeError, ValueError):
            continue
    return None


def my_transfers_for_gw(transfers: list[dict] | None,
                        gw: int) -> list[dict]:
    """The transfers I made *for* ``gw``, in the order the API listed them.

    Takes the banked list rather than a client, unlike the sketch in spec §1:
    ``run_review`` banks the whole season's transfers once and then grades
    several gameweeks off it, and a function that could also take a client
    would be a second fetch path for one fact.
    """
    out = []
    for row in (transfers or []):
        try:
            if int(row.get("event")) == int(gw):
                out.append(dict(row))
        except (TypeError, ValueError):
            continue
    return out


def bank_my_entry(client, entry_id: int, season: str, gw: int,
                  raw_dir: Path | str | None = None) -> dict:
    """Bank all three stores and return one gameweek's view of them.

    ``hits`` is the *count* of hits, not their cost: ``score_gw`` takes a
    count and multiplies by four itself, and handing it a cost would charge
    the user sixteen points for a single hit.

    Every field degrades independently. A dead API on a Tuesday morning gives
    back a dict of nothings and a printed line, and ``run_review`` skips that
    gameweek while still grading the ones already banked.
    """
    picks = bank_my_gw(client, entry_id, season, gw, raw_dir)
    history = (bank_my_history(client, entry_id, season, raw_dir)
               or load_my_history(season, entry_id, raw_dir))
    transfers = (bank_my_transfers(client, entry_id, season, raw_dir)
                 or load_my_transfers(season, entry_id, raw_dir))
    row = gw_history_row(history, gw)
    cost = int((row or {}).get("event_transfers_cost", 0) or 0)
    return {"picks": picks, "history": history, "history_row": row,
            "chip": chip_for_gw(history, gw), "hits": cost // 4,
            "transfers": my_transfers_for_gw(transfers, gw)}
