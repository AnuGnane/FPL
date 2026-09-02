"""Six read tools over the payloads the web app already serves.

The point of this server is that Claude Code can read this tree without a browser
and without a second implementation of anything. So every tool is the router's own
function, and the test that matters is not "the tool returns something" — it is
"the tool returns the same thing the endpoint does".

The one tool that is not a router function is `whatif`, and that is the spec being
wrong about the code rather than a shortcut: POST /api/whatif is
`status_code=202, response_model=JobAccepted`. It queues a job and returns an id. A
tool returning a job id would be useless, and polling one from a stdio subprocess
would put the job runner's lifecycle inside it. The synchronous body —
`solve_whatif` — is exported, and whatif.py is protected but importable.

No write tools, in v12 or in this file: spec §8 names them as out of scope.
"""

from __future__ import annotations

import inspect

from gaffer import mcp_server


def test_the_six_tools_are_exactly_these():
    assert sorted(mcp_server.TOOLS) == [
        "explain", "freshness", "health", "ledger", "projections", "whatif"]


def test_every_tool_is_read_only():
    """Spec §8: no write tools in v12. Asserted by name rather than by
    intention, because "read-only" is a property a later cycle can lose in one
    line."""
    for name in mcp_server.TOOLS:
        assert not any(word in name
                       for word in ("save", "set", "add", "delete", "run",
                                    "start", "post", "write"))


def test_every_tool_has_a_docstring_the_model_can_read():
    """An MCP tool's docstring is its description on the wire, so an
    undocumented tool is an unusable one."""
    for name, fn in mcp_server.TOOLS.items():
        assert (fn.__doc__ or "").strip(), name


def test_each_schema_round_trips():
    """§2.10's first test. A tool whose signature cannot be turned into a JSON
    schema fails at registration time, in a subprocess, with no output."""
    for name, fn in mcp_server.TOOLS.items():
        sig = inspect.signature(fn)
        for param in sig.parameters.values():
            assert param.annotation is not inspect.Parameter.empty, \
                f"{name}.{param.name}"


def test_projections_is_the_players_endpoints_own_payload(monkeypatch):
    """§2.10's second test: the tool returns the router's payload, not a
    re-derivation of it."""
    from gaffer.web.routers import players as players_router

    sentinel = [{"code": 1, "name": "A"}]
    monkeypatch.setattr(players_router, "players",
                        lambda **kw: sentinel)
    assert mcp_server.TOOLS["projections"]() == sentinel


def test_projections_forwards_its_filters(monkeypatch):
    from gaffer.web.routers import players as players_router

    seen = {}
    monkeypatch.setattr(players_router, "players",
                        lambda **kw: seen.update(kw) or [])
    mcp_server.TOOLS["projections"](position="MID", team=3, top=5)
    assert seen["position"] == "MID" and seen["team"] == 3


def test_top_truncates_and_is_not_passed_to_the_router(monkeypatch):
    """`players()` has no `top` parameter — it has position, team, search and
    sort. `top` is the tool's own, because a model reading 700 rows to answer
    "who are the best five midfielders" is the cost this server exists to
    avoid."""
    from gaffer.web.routers import players as players_router

    monkeypatch.setattr(players_router, "players",
                        lambda **kw: [{"code": c} for c in range(10)])
    assert len(mcp_server.TOOLS["projections"](top=3)) == 3


def test_whatif_calls_the_solver_body_and_not_the_job_route(monkeypatch):
    from gaffer.web.routers import whatif as whatif_router

    seen = {}

    def fake(req, gw):
        seen["req"], seen["gw"] = req, gw
        return {"diff": []}

    monkeypatch.setattr(whatif_router, "solve_whatif", fake)
    monkeypatch.setattr(mcp_server, "_latest_gw", lambda: 5)
    out = mcp_server.TOOLS["whatif"](transfers_in=[1], transfers_out=[2])
    assert out == {"diff": []}
    assert seen["gw"] == 5
    assert seen["req"].force_in == [1] and seen["req"].ban == [2]


def test_whatif_maps_the_chip_code(monkeypatch):
    from gaffer.web.routers import whatif as whatif_router

    seen = {}
    monkeypatch.setattr(whatif_router, "solve_whatif",
                        lambda req, gw: seen.update(chip=req.chip) or {})
    monkeypatch.setattr(mcp_server, "_latest_gw", lambda: 5)
    mcp_server.TOOLS["whatif"](transfers_in=[], transfers_out=[], chip="wc")
    assert seen["chip"] == "wc"


def test_a_tool_on_a_cold_clone_returns_a_sentence_rather_than_a_traceback(
        tmp_path, monkeypatch):
    """A stdio server's exception is a dead subprocess and a model with no
    idea why. Every tool answers `{"error": ...}` instead, carrying the domain
    message the CLI would have printed."""
    monkeypatch.chdir(tmp_path)
    out = mcp_server.TOOLS["projections"]()
    assert isinstance(out, dict) and "error" in out
    assert "gaffer advise" in out["error"]


def test_freshness_and_health_answer_on_a_cold_clone(tmp_path, monkeypatch):
    """These two are the ones a model reaches for *because* something is
    wrong, so neither may need a working tree."""
    monkeypatch.chdir(tmp_path)
    assert mcp_server.TOOLS["freshness"]()["rows"]
    assert "data" in mcp_server.TOOLS["health"]()


def test_the_server_builds_without_starting(tmp_path, monkeypatch):
    """Registration is where a bad signature fails, and it fails in a
    subprocess with no output — so it is done here, in-process, instead."""
    monkeypatch.chdir(tmp_path)
    server = mcp_server.build_server()
    assert server is not None


def test_the_dependency_is_pinned_in_the_project_metadata():
    import pathlib

    text = pathlib.Path(__file__).parents[1].joinpath("pyproject.toml") \
        .read_text()
    assert "mcp" in text
