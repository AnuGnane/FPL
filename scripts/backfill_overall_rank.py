"""Fill the ledger's null ``overall_rank`` cells from the banked entry history.

GUIDE §12.4's residual ("``overall_rank`` and ``projection_snapshot`` fill
forward only") and the ROADMAP's Data-gated row W4 §5.3 overall-rank change,
which waits on five graded gameweeks carrying both ``my_points`` and
``overall_rank`` and counts GW1 short because its rank was banked null
(holiday F-33). The rank is public and already on disk:
``data/my_entry.bank_my_history`` writes the entry-history payload, each
gameweek's ``overall_rank`` included, to
``data/raw/league/{season}/{entry}-history.json``.

Dry run by default: one ``BACKFILL_RANK gw=… was=null now=…`` line per graded
row of the season in force whose ``overall_rank`` is null (or absent) and
whose gameweek the history carries with a rank. ``--write`` banks exactly
those rows again through ``review.append_ledger``, the ledger's own save path
and its lock, each row as ``review.load_ledger`` read it with that one cell
filled, so points, grades, ``projection_snapshot`` and every row that already
has a rank keep their values. ``append_ledger`` rewrites the whole file as it
always does: it re-sorts by ``(season, gw)`` and writes the current season
onto a legacy row that carries none, the v19h §2.2 migration ``load_ledger``
already reads them under, and no cell's value moves. A second ``--write``
finds nothing to fill.
``projection_snapshot`` is out of scope: it has no public source.

The rows are read once, before the first write, outside the lock that
``append_ledger`` takes per row (and gives up after two seconds, by its own
design); a review banking one of those gameweeks while the script writes
would be overwritten with the row as read. The script is run by hand, once,
away from the Tuesday review, so it reuses the save path rather than reaching
into ``review``'s private lock.

A missing or unreadable history, or one whose ``current`` is not a list of
rows, prints a sentence and exits 0, never a traceback: the night shift
transcribes what it prints.

    uv run python scripts/backfill_overall_rank.py            # dry run
    uv run python scripts/backfill_overall_rank.py --write
"""

from __future__ import annotations

import argparse
from pathlib import Path

from gaffer import review
from gaffer.data.my_entry import gw_history_row, load_my_history, my_history_path


def _rank(history: dict | None, gw: int) -> int | None:
    # ``gw_history_row`` calls ``.get`` on each element of ``current``; a
    # payload of another shape is no rank, not an AttributeError.
    current = (history or {}).get("current")
    if not isinstance(current, list) or not all(isinstance(r, dict)
                                                for r in current):
        return None
    row = gw_history_row(history, gw)
    if row is None or row.get("overall_rank") is None:
        return None
    try:
        return int(row["overall_rank"])
    except (TypeError, ValueError):
        return None


def fills(season: str, entry_id: int,
          raw_dir: Path | str | None = None) -> tuple[list[tuple[dict, int]],
                                                      str | None]:
    """``(row, rank)`` for every graded row whose null rank the history can
    fill, and the reason there are none to look for (``None`` when the
    history was read)."""
    path = my_history_path(season, entry_id, raw_dir)
    history = load_my_history(season, entry_id, raw_dir)
    if history is None:
        return [], (f"no banked entry history at {path} "
                    f"(missing or unreadable); nothing to backfill")
    out = []
    for row in review.load_ledger():
        if row.get("overall_rank") is not None:
            continue
        rank = _rank(history, int(row["gw"]))
        if rank is not None:
            out.append((row, rank))
    return out, None


def backfill(season: str, entry_id: int, *, write: bool = False,
             raw_dir: Path | str | None = None) -> list[str]:
    """The lines to print; with ``write`` the cells are banked as well."""
    found, reason = fills(season, entry_id, raw_dir)
    if reason is not None:
        return [reason]
    lines = []
    for row, rank in found:
        if write:
            review.append_ledger({**row, "overall_rank": rank})
        lines.append(f"BACKFILL_RANK gw={int(row['gw'])} was=null now={rank}")
    if not lines:
        lines.append("no graded row with a null overall_rank that the "
                     "history can fill")
    elif not write:
        lines.append(f"dry run: {len(found)} cell(s) would be filled; "
                     f"--write banks them")
    return lines


def main(argv: list[str] | None = None) -> int:
    """Print the ledger's fillable ``overall_rank`` cells, and bank them with
    ``--write``."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true",
                        help="bank the filled cells (default: dry run)")
    args = parser.parse_args(argv)
    from gaffer.config import config_in_force

    cfg = config_in_force()
    for line in backfill(str(cfg.current_season), int(cfg.entry_id),
                         write=args.write):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
