from typer.testing import CliRunner

from gaffer.cli import app

runner = CliRunner()


def test_cli_help_lists_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ["advise", "refresh", "train", "prices", "league", "live",
                "backtest", "evaluate", "build-history", "ui",
                "calibrate-decisions"]:
        assert cmd in result.output


def test_advise_fails_cleanly_without_models(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        '[fpl]\nentry_id = 1\nleague_id = 0\n')
    result = runner.invoke(app, ["advise"])
    assert result.exit_code != 0
    assert "gaffer train" in result.output


def test_every_command_help_renders():
    """Each command's body imports lazily, so --help is the cheapest proof
    that no command is wired to a name that does not exist yet."""
    for cmd in ["advise", "refresh", "train", "prices", "league", "live",
                "backtest", "evaluate", "build-history", "ui",
                "calibrate-decisions"]:
        result = runner.invoke(app, [cmd, "--help"])
        assert result.exit_code == 0, f"{cmd} --help failed: {result.output}"


def test_league_without_league_id_fails_cleanly(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text('[fpl]\nentry_id = 1\nleague_id = 0\n')
    result = runner.invoke(app, ["league"])
    assert result.exit_code != 0
    assert "league_id" in result.output


def test_live_between_gameweeks_says_so_without_a_traceback(tmp_path,
                                                            monkeypatch):
    from gaffer.errors import GafferError

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text('[fpl]\nentry_id = 1\nleague_id = 5\n')

    def _boom(cfg, client):
        raise GafferError("no gameweek in progress — nothing to track")

    monkeypatch.setattr("gaffer.live_gw.run_live", _boom)
    monkeypatch.setattr("gaffer.api.client.FPLClient.__init__",
                        lambda self, *a, **k: None)
    result = runner.invoke(app, ["live"])
    assert result.exit_code == 0
    assert "no gameweek in progress" in result.output
    assert "Traceback" not in result.output


def test_live_without_entry_id_fails_cleanly(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text('[fpl]\nentry_id = 0\nleague_id = 5\n')
    result = runner.invoke(app, ["live"])
    assert result.exit_code != 0
    assert "entry_id" in result.output


def test_league_reports_empty_league(tmp_path, monkeypatch):
    import pandas as pd

    from gaffer.data import league as league_mod

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text('[fpl]\nentry_id = 1\nleague_id = 5\n')
    monkeypatch.setattr(
        league_mod, "fetch_rival_entries",
        lambda *a, **k: pd.DataFrame(columns=league_mod.STANDINGS_COLS))
    monkeypatch.setattr("gaffer.api.client.FPLClient.__init__",
                        lambda self, *a, **k: None)
    result = runner.invoke(app, ["league"])
    assert result.exit_code == 0
    assert "No rivals" in result.output


def test_ui_command_is_registered_and_documents_its_port():
    result = runner.invoke(app, ["ui", "--help"])
    assert result.exit_code == 0
    assert "8927" in result.output
    assert "--port" in result.output


def test_ui_binds_loopback_and_opens_the_browser(monkeypatch):
    calls = {}

    def fake_run(application, host, port, log_level):
        calls["host"] = host
        calls["port"] = port

    monkeypatch.setattr("uvicorn.run", fake_run)
    monkeypatch.setattr("webbrowser.open",
                        lambda url: calls.setdefault("url", url))
    result = runner.invoke(app, ["ui", "--port", "9100"])
    assert result.exit_code == 0
    assert calls["host"] == "127.0.0.1"      # never 0.0.0.0
    assert calls["port"] == 9100
    assert calls["url"] == "http://127.0.0.1:9100"


def test_ui_can_skip_the_browser(monkeypatch):
    opened = []
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: None)
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url))
    result = runner.invoke(app, ["ui", "--no-open-browser"])
    assert result.exit_code == 0
    assert opened == []


def _stub_advice(**kw):
    from gaffer.advise import Advice

    base = dict(gw=2, deadline="2026-08-22T17:30:00Z", buys=[], sells=[],
                hits=0, xi=[], bench=[],
                captain={"name": "Salah"}, vice={"name": "Bloke"},
                captain_options=[], chip_table=[], wildcard_now=None,
                alternatives=[], threats=[], price_alerts=[],
                expected_pts=61.5)
    return Advice(**{**base, **kw})


def _advise_run(tmp_path, monkeypatch, advice):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        '[fpl]\nentry_id = 1\nleague_id = 0\n')
    monkeypatch.setattr("gaffer.advise.run_advise", lambda cfg: advice)
    monkeypatch.setattr("gaffer.report.render.render_report",
                        lambda a, model_health=None: "reports/gw2.md")
    monkeypatch.setattr("gaffer.tracking.latest_health", lambda: None)
    return runner.invoke(app, ["advise"])


def test_advise_warns_loudly_when_the_model_has_not_seen_last_gameweek(
        tmp_path, monkeypatch):
    """The bug this exists for: FPL had not marked GW1 data_checked, so the
    GW2 advice was built off last season alone and nothing said so."""
    warning = ("model has no data for GW1 — FPL usually finalizes it the "
               "morning after the last match; re-run gaffer advise after that")
    result = _advise_run(tmp_path, monkeypatch,
                         _stub_advice(data_through_gw=None,
                                      data_warning=warning))
    assert result.exit_code == 0
    assert "no data for GW1" in result.output
    assert "WARNING" in result.output


def test_advise_says_nothing_extra_when_the_data_is_current(tmp_path,
                                                            monkeypatch):
    result = _advise_run(tmp_path, monkeypatch,
                         _stub_advice(data_through_gw=1, data_warning=None))
    assert result.exit_code == 0
    assert "WARNING" not in result.output


def test_evaluate_writes_the_artifact_and_prints_the_table(tmp_path,
                                                           monkeypatch):
    import json

    monkeypatch.chdir(tmp_path)
    payload = {"run_at": "now", "git_sha": "abc1234", "holdout_slots": 10,
               "stratified": {"all": {c: {"rmse": 1.0, "mae": 0.5, "n": 3}
                                      for c in ["zeros", "blanks", "tickers",
                                                "haulers", "all"]}},
               "heads": {}, "baselines": {}}
    monkeypatch.setattr("gaffer.evaluation.evaluate_current",
                        lambda *a, **k: payload)
    result = runner.invoke(app, ["evaluate"])
    assert result.exit_code == 0, result.output
    stored = json.loads((tmp_path / "reports" / "evaluation.json").read_text())
    assert stored["current"]["git_sha"] == "abc1234"
    assert "haulers" in result.output


def test_evaluate_rejects_an_unknown_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["evaluate", "--mode", "nonsense"])
    assert result.exit_code != 0
    assert "nonsense" in result.output


def test_build_history_also_builds_the_match_odds_parquet():
    """Closing odds are part of the training corpus now, so the one-shot
    corpus command has to produce them."""
    import inspect

    from gaffer.cli import build_history_cmd

    src = inspect.getsource(build_history_cmd)
    assert "build_match_odds(" in src


def test_cups_ingests_every_training_season_and_the_current_one(monkeypatch):
    """The congestion feature is served as well as trained, so the ingest has
    to cover the season being predicted."""
    import pandas as pd

    from gaffer.config import Config
    from gaffer.data import cups as cups_mod
    from gaffer.data import history as history_mod

    seen = {}

    def fake(seasons, indexes, *a, **k):
        seen["seasons"] = list(seasons)
        return pd.DataFrame({"team_code": [3, 8]})

    monkeypatch.setattr(cups_mod, "download_cup_matches", fake)
    monkeypatch.setattr(history_mod, "season_name_codes", lambda s: {})
    monkeypatch.setattr("gaffer.config.load_config", lambda *a, **k: Config(
        entry_id=1, league_id=2, train_seasons=["2023-24", "2024-25"],
        current_season="2025-26"))

    result = CliRunner().invoke(app, ["cups"])
    assert result.exit_code == 0, result.output
    assert seen["seasons"] == ["2023-24", "2024-25", "2025-26"]
    assert "2 club-match dates" in result.output


def test_cups_is_a_command():
    result = CliRunner().invoke(app, ["--help"])
    assert "cups" in result.output


def test_understat_is_a_command():
    from typer.testing import CliRunner

    from gaffer.cli import app

    result = CliRunner().invoke(app, ["--help"])
    assert "understat" in result.output


def test_understat_name_table_includes_the_current_seasons_clubs():
    """Built from train_seasons alone, the table has no entry for a club
    promoted this season, so every one of its understat rows drops."""
    import inspect

    from gaffer.cli import understat

    src = inspect.getsource(understat)
    assert "build_teams(" in src


def test_calibrate_decisions_writes_the_shipped_asset():
    """The asset lives in the package, not in data/ — it is curated knowledge
    that has to survive a wiped data directory and reach a fresh clone."""
    import inspect

    from gaffer.cli import calibrate_decisions

    src = inspect.getsource(calibrate_decisions)
    assert "run_calibration(" in src
    assert "write_priors(" in src
    assert "src/gaffer/assets/decision_priors.json" in src


def test_advise_prints_the_captain_note_and_the_demoted_pick(tmp_path,
                                                             monkeypatch):
    """When the dial moves the armband both picks are shown, mirroring the
    v4c raw-optimum treatment."""
    import gaffer.advise as advise_mod
    import gaffer.config as config_mod
    import gaffer.report.render as render_mod
    import gaffer.tracking as tracking_mod
    from tests.test_v4c_degradation import _fixture_advice

    advice = _fixture_advice()
    advice.captain_note = "differential vs Ten Hag Hive's last armband"
    advice.demoted_captain = {"code": 9, "name": "Mohamed Salah", "ep": 8.8}

    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text('[fpl]\nentry_id = 1\nleague_id = 2\n')
    real_load = config_mod.load_config
    monkeypatch.setattr(config_mod, "load_config",
                        lambda path="config.toml": real_load(cfg_path))
    monkeypatch.setattr(advise_mod, "run_advise",
                        lambda cfg, client=None: advice)
    monkeypatch.setattr(render_mod, "render_report",
                        lambda advice, **kw: "reports/gw7.html")
    monkeypatch.setattr(tracking_mod, "latest_health", lambda: None)

    out = runner.invoke(app, ["advise"]).output
    assert ("Captain: Erling Haaland (differential vs Ten Hag Hive's "
            "last armband)") in out
    assert "Raw-EP captain: Mohamed Salah (8.8 xPts)" in out


def test_calibrate_injuries_is_registered_and_needs_a_club_table(tmp_path):
    """The command must exist and must refuse to scrape without a club list —
    a stale twenty-club table is how you calibrate on the Championship."""
    from typer.testing import CliRunner

    from gaffer.cli import app

    result = CliRunner().invoke(app, ["calibrate-injuries", "--clubs",
                                      str(tmp_path / "missing.json")])
    assert result.exit_code == 1
    assert "club table" in result.stdout


def test_evaluate_accepts_the_news_shadow_flag(monkeypatch, tmp_path):
    """Gate N2's readout has to be reachable without a model on disk."""
    from typer.testing import CliRunner

    from gaffer import evaluation
    from gaffer.cli import app

    monkeypatch.setattr(evaluation, "evaluate_news_shadow",
                        lambda: {"run_at": "x", "git_sha": "y", "rows": 0,
                                 "overall": {}, "by_gw": []})
    monkeypatch.setattr(evaluation, "save_evaluation",
                        lambda key, payload: tmp_path / "evaluation.json")
    result = CliRunner().invoke(app, ["evaluate", "--news-shadow"])
    assert result.exit_code == 0
    assert "nothing to score yet" in result.stdout


def test_calibrate_noise_is_registered():
    from typer.testing import CliRunner

    from gaffer.cli import app

    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "calibrate-noise" in result.output
