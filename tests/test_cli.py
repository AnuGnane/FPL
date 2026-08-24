from typer.testing import CliRunner

from gaffer.cli import app

runner = CliRunner()


def test_cli_help_lists_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ["advise", "refresh", "train", "prices", "league",
                "backtest", "build-history"]:
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
    for cmd in ["advise", "refresh", "train", "prices", "league",
                "backtest", "build-history"]:
        result = runner.invoke(app, [cmd, "--help"])
        assert result.exit_code == 0, f"{cmd} --help failed: {result.output}"


def test_league_without_league_id_fails_cleanly(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text('[fpl]\nentry_id = 1\nleague_id = 0\n')
    result = runner.invoke(app, ["league"])
    assert result.exit_code != 0
    assert "league_id" in result.output


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
