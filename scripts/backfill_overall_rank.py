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
has a rank stay as they are. A second ``--write`` finds nothing to fill.
``projection_snapshot`` is out of scope: it has no public source.

``append_ledger`` takes the lock per row and the rows are read just before,
outside it; a review banking the same gameweek in that window would be
overwritten with the row as read. The window is one JSON dump wide and the
script is run by hand, so it reuses the save path rather than reaching into
``review``'s private lock.

A missing or unreadable history prints a sentence and exits 0, never a
traceback: the Mac runs this unattended and transcribes what it prints.

    uv run python scripts/backfill_overall_rank.py            # dry run
    uv run python scripts/backfill_overall_rank.py --write
"""

from __future__ import annotations

import argparse
from pathlib import Path

from gaffer import review
from gaffer.data.my_entry import gw_history_row, load_my_history, my_history_path


def _rank(history: dict | None, gw: int) -> int | None:
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
