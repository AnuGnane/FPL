"""GET/POST/DELETE ``/api/watchlist`` — the players the manager is watching.

``routers/overrides.py``'s shape, minus everything that made that endpoint
validate hard: there are no numbers here for a model to obey, so there is
nothing to clip, nothing to warn about and nothing to compare against what the
pipeline thought. What survives is the structure — reads never fail, writes
fail in the what-if lab's ``{constraint, error, players}`` shape so the client
can render the reason beside the field that caused it.

The store itself is :mod:`gaffer.watchlist`; nothing here does arithmetic.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from gaffer.artifacts import load_snapshot
from gaffer.errors import GafferError
from gaffer.watchlist import load_watchlist, unwatch, watch
from gaffer.web.schemas import WatchlistPanel, WatchRequest, WatchRow

router = APIRouter(prefix="/api", tags=["watchlist"])


def _fail(constraint: str, error: str, players: list[int]) -> HTTPException:
    """The what-if lab's structured 422, reused so the UI has one shape."""
    return HTTPException(status_code=422,
                         detail={"constraint": constraint, "error": error,
                                 "players": players})


def names() -> dict[int, str]:
    """``{code: name}`` from the bootstrap snapshot, or ``{}``.

    Exported rather than private: the movers endpoint and the digest both need
    exactly this map off exactly this file, and three copies of a four-line
    read is how three different failure modes get invented.
    """
    try:
        players = load_snapshot("live/players.parquet")
        return {int(r.code): str(r.name) for r in players.itertuples()}
    except Exception as exc:  # noqa: BLE001 — a read is never worth a 500
        print(f"watchlist panel: player snapshot unreadable ({exc})")
        return {}


def _panel() -> WatchlistPanel:
    resolved = names()
    return WatchlistPanel(rows=[
        WatchRow(code=code, name=resolved.get(code, str(code)),
                 note=str(row.get("note") or ""),
                 set_at=str(row.get("set_at") or ""))
        for code, row in sorted(load_watchlist().items())])


@router.get("/watchlist", response_model=WatchlistPanel)
def watchlist() -> WatchlistPanel:
    return _panel()


@router.post("/watchlist", response_model=WatchlistPanel)
def star(req: WatchRequest) -> WatchlistPanel:
    known = names()
    if not known:
        raise _fail("no_player_list",
                    "no player snapshot on disk — run `gaffer advise` before "
                    "starring anyone", [int(req.code)])
    if int(req.code) not in known:
        raise _fail("unknown_player",
                    f"player {req.code} is not in the current player list",
                    [int(req.code)])
    try:
        watch(int(req.code), note=req.note, known_codes=list(known))
    except GafferError as exc:
        raise _fail("watch_value", str(exc), [int(req.code)]) from exc
    return _panel()


@router.delete("/watchlist/{code}", response_model=WatchlistPanel)
def unstar(code: int) -> WatchlistPanel:
    if not unwatch(int(code)):
        raise HTTPException(status_code=404,
                            detail=f"player {code} is not starred")
    return _panel()
