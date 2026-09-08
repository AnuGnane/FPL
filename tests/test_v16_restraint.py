"""v16 §4 — the advice is the chosen rung: the CLI lines. The source-order
pins on ``run_advise`` moved to the round trip in
``tests/test_served_plan.py`` (v17f §1 part 3)."""
from __future__ import annotations

from tests.test_v4c_degradation import _fixture_advice


def _cli(tmp_path, monkeypatch, advice):
    from typer.testing import CliRunner

    import gaffer.advise as advise_mod
    import gaffer.config as config_mod
    import gaffer.report.render as render_mod
    import gaffer.tracking as tracking_mod
    from gaffer.cli import app

    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        '[fpl]\nentry_id = 1\nleague_id = 2\n'
        '[data]\ntrain_seasons = ["2025-26"]\ncurrent_season = "2026-27"\n')
    real_load = config_mod.load_config
    monkeypatch.setattr(config_mod, "load_config",
                        lambda path="config.toml": real_load(cfg_path))
    monkeypatch.setattr(advise_mod, "run_advise", lambda cfg, client=None: advice)
    monkeypatch.setattr(render_mod, "render_report",
                        lambda advice, **kw: "reports/gw7.html")
    monkeypatch.setattr(tracking_mod, "latest_health", lambda: None)
    # v17d §2.9: the CLI chains the brief; stubbed so this rail neither
    # reads the real reports/ nor runs the configured LLM command.
    monkeypatch.setattr("gaffer.brief.run_brief",
                        lambda gw, cfg=None: {"gw": gw, "written": False,
                                              "note": None, "path": None})
    return CliRunner().invoke(app, ["advise"])


def test_the_cli_prints_the_restraint_line_and_the_objective_when_they_differ(
        tmp_path, monkeypatch):
    advice = _fixture_advice()
    # v17b §3.3 (orchestrator ruling): the CLI prints the served line rather
    # than composing it, so the fixture carries what serve_rung now writes;
    # the asserted strings are unchanged.
    advice.restraint = {"chosen": "hits0", "label": "free transfers only", "bar": 0.6,
                        "agrees": False, "note": "x", "hit_cost": 4,
                        "line": ("restraint: free transfers only; the step to 1 hit "
                                 "was refused, 46% — expected points alone"),
                        "steps": [{"below": "bank", "above": "hits0", "share": 0.79,
                                   "taken": True, "reason": "expected points alone",
                                   "reason_kind": "points"},
                                  {"below": "hits0", "above": "hits1", "share": 0.46,
                                   "taken": False, "reason": "expected points alone",
                                   "reason_kind": "points"}]}
    advice.objective = {"buys": [{"name": "Isak"}], "sells": [{"name": "Rice"}],
                        "hits": 1, "expected_pts": 60.0,
                        "line": "the objective wanted: Isak in; Rice out; 1 hit"}
    out = _cli(tmp_path, monkeypatch, advice)
    assert out.exit_code == 0, out.output
    assert ("restraint: free transfers only; the step to 1 hit was refused, "
            "46% — expected points alone\n") in out.output
    assert "the objective wanted: Isak in; Rice out; 1 hit\n" in out.output
    assert out.output.index("restraint:") < out.output.index("Captain:")


def test_the_cli_prints_no_objective_line_when_they_agree(tmp_path, monkeypatch):
    advice = _fixture_advice()
    advice.restraint = {"chosen": "hits1", "label": "1 hit", "bar": 0.6, "agrees": True,
                        "note": None, "hit_cost": 4, "steps": [],
                        "line": "restraint: 1 hit; every step was taken"}
    advice.objective = {"buys": [], "sells": [], "hits": 1, "expected_pts": 60.0}
    out = _cli(tmp_path, monkeypatch, advice)
    assert "restraint: 1 hit; every step was taken\n" in out.output
    assert "the objective wanted" not in out.output


def test_an_advice_without_the_field_prints_nothing_extra(tmp_path, monkeypatch):
    out = _cli(tmp_path, monkeypatch, _fixture_advice())
    assert "restraint:" not in out.output
