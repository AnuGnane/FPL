"""``gaffer mcp`` — this tree, readable by Claude Code over stdio.

Spec §2.10 (specs/2026-09-01-gaffer-v12-program-design.md). Six tools, all
reads, each one the router function that already serves the same payload to the
web UI. No second implementation of anything: a tool that re-derived a number
would drift from the page showing it, and the drift would be invisible from
both sides.

**One correction to the spec.** It says each tool is a thin wrapper over the
existing router function. That is true of five. ``POST /api/whatif`` is
``status_code=202, response_model=JobAccepted``: it queues a job on the web
app's runner and returns an id. A tool returning a job id would be useless, and
polling one from a stdio subprocess would put the runner's lifecycle inside it.
So ``whatif`` wraps :func:`gaffer.web.routers.whatif.solve_whatif`, the
synchronous body the job runs — an import from a protected module, which is not
an edit to it.

**No write tools**, here or in v12 at all — spec §8 names them out of scope. The
tools are also named so that stays checkable: nothing here is a verb that
changes something.

Every tool returns ``{"error": "..."}`` rather than raising. An exception out of
a stdio server is a dead subprocess and a model with no idea why, where the
domain message ("run `gaffer advise` first") is exactly the thing that would
have told it what to do.
"""

from __future__ import annotations

from typing import Any, Callable


def _safe(fn: Callable[[], Any]) -> Any:
    """Run ``fn``; return ``{"error": <message>}`` instead of raising."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 — see the module docstring
        return {"error": str(exc) or exc.__class__.__name__}


def _latest_gw() -> int:
    from gaffer.artifacts import latest_gw
    from gaffer.errors import GafferError

    gw = latest_gw()
    if gw is None:
        raise GafferError("nothing on disk yet — run `gaffer advise` first")
    return int(gw)


def projections(position: str | None = None, team: int | None = None,
                top: int | None = None) -> Any:
    """This week's expected points per player, as the Players page sees them.

    ``position`` is GKP/DEF/MID/FWD; ``team`` is an FPL team *code*; ``top``
    keeps only the first N rows after the endpoint's own sort (highest
    ``ep_next`` first).
    """
    def call():
        from gaffer.web.routers import players as router

        rows = router.players(position=position, team=team)
        # `top` is this tool's own, not the endpoint's: `players()` takes
        # position, team, search and sort and returns every candidate. A model
        # reading seven hundred rows to answer "the best five midfielders" is
        # the cost this server exists to avoid.
        return rows[:top] if top else rows
    return _safe(call)


def explain(code: int) -> Any:
    """Why one player's expected points are what they are — the same breakdown
    the Players page shows when you open a row. ``code`` is the FPL player
    code, which is stable across seasons (``element`` is not)."""
    def call():
        from gaffer.web.routers import players as router

        return router.explain(code)
    return _safe(call)


def whatif(transfers_in: list[int], transfers_out: list[int],
           chip: str = "none") -> Any:
    """Preview a set of transfers against the saved board. Solves nothing on
    the FPL site and starts no job — it re-solves locally and returns the
    baseline, the constrained plan and their difference.

    ``transfers_in`` become ``force_in`` (the solve must include them) and
    ``transfers_out`` become ``ban`` (it may not hold them). ``ban`` is
    stronger than "sell": it also forbids buying the player back, which is the
    closest the constraint vocabulary gets and is stated here rather than
    quietly approximated.
    """
    def call():
        from gaffer.web.routers import whatif as router
        from gaffer.web.schemas import WhatIfRequest

        req = WhatIfRequest(force_in=list(transfers_in),
                            ban=list(transfers_out), chip=chip)
        return router.solve_whatif(req, _latest_gw())
    return _safe(call)


def ledger(gw: int | None = None) -> Any:
    """The banked decision ledger: what was advised, what was done, and how
    each graded week turned out. ``gw`` narrows it to one gameweek."""
    def call():
        from gaffer.web.routers import review as router

        payload = router.review().model_dump()
        if gw is not None:
            payload["gws"] = [row for row in payload["gws"]
                              if int(row.get("gw", -1)) == int(gw)]
        return payload
    return _safe(call)


def freshness() -> Any:
    """How old each of the five standing data sources is — the same line the
    UI draws at the top of every page. Answers on a tree with no data."""
    def call():
        from gaffer.web.routers import meta as router

        return router.freshness().model_dump()
    return _safe(call)


def health() -> Any:
    """Data files, model ages, the launchd log, the season check and the last
    backup. Answers on a tree with no data."""
    def call():
        from gaffer.web.routers import meta as router

        return router.health().model_dump()
    return _safe(call)


TOOLS: dict[str, Callable[..., Any]] = {
    "projections": projections,
    "explain": explain,
    "whatif": whatif,
    "ledger": ledger,
    "freshness": freshness,
    "health": health,
}


def build_server():
    """Register the six tools. Built here rather than at import so a bad
    signature fails in a test rather than in a subprocess with no output.

    ``MCPServer``, not ``FastMCP``: mcp 2.x renamed the class and moved it to
    ``mcp.server.mcpserver``, and importing the old path raises a
    ``ModuleNotFoundError`` that says so. ``add_tool(fn)`` and ``run()`` are
    unchanged in shape, so only this import and this constructor differ from
    the v1 idiom every example on the internet still shows.
    """
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("gaffer")
    for fn in TOOLS.values():
        server.add_tool(fn)
    return server


def run() -> None:
    """Serve over stdio until the client disconnects."""
    build_server().run()
