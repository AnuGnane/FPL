"""v18g §2.6 — the six commands nothing named.

`build-history`, `understat`, `league-sim`, `backtest`, `calibrate-decisions`
and `diagnose-zeros` were registered, documented and never invoked by a test:
a renamed option or a body wired to a moved function would have shipped and
been found by the person running it. Two rails each, and neither needs the
thing the command is for. ``--help`` proves the command is registered under
the name the docs use and that its lazily-imported body parses; the stubbed
run proves the option string the user types arrives at the function the body
calls, with the type Typer parsed it into — an int as an int and not "6".

Every body in ``cli.py`` imports inside itself (its module docstring says
why), so the name is looked up on the *source* module at call time. That is
where each stub goes, and it is why nothing here touches the network,
``models/`` or ``reports/``.
"""
from __future__ import annotations

import pandas as pd
import pytest
from typer.testing import CliRunner

from gaffer.cli import app
from gaffer.config import Config
from tests.conftest import patch_view

runner = CliRunner()

COMMANDS = ["build-history", "understat", "league-sim", "backtest",
            "calibrate-decisions", "diagnose-zeros"]

SEASONS = ["2023-24", "2024-25"]


def _cfg() -> Config:
    """The config every stubbed run reads. Two finished seasons because
    ``backtest`` defaults its season to ``train_seasons[-1]``."""
    return Config(entry_id=1, league_id=0, train_seasons=list(SEASONS))


class _Recorder:
    """A stand-in that remembers how it was called and answers ``answer``."""

    def __init__(self, answer=None):
        self.answer = answer
        self.calls: list[tuple[tuple, dict]] = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.answer

    @property
    def call(self) -> tuple[tuple, dict]:
        assert len(self.calls) == 1, f"called {len(self.calls)} times"
        return self.calls[0]


class _NoClient:
    """``FPLClient`` for a command that builds one before the work starts."""

    def get_bootstrap(self):
        return {}


def _ok(result) -> None:
    assert result.exit_code == 0, result.output


# --- registered under the name the docs use ---------------------------


@pytest.mark.parametrize("command", COMMANDS)
def test_the_command_is_registered_and_its_help_names_it(command):
    result = runner.invoke(app, [command, "--help"])
    _ok(result)
    assert command in result.output


# --- the parsed arguments reach the function the body calls -----------


def test_build_history_hands_the_configured_seasons_to_the_builder(monkeypatch):
    build = _Recorder(answer=[1, 2, 3])
    monkeypatch.setattr("gaffer.config.load_config", _cfg)
    monkeypatch.setattr("gaffer.data.history.build_history", build)
    monkeypatch.setattr("gaffer.data.history.build_history_fixtures",
                        _Recorder(answer=[1]))
    monkeypatch.setattr("gaffer.data.history.season_name_codes",
                        _Recorder(answer={}))
    monkeypatch.setattr("gaffer.data.match_odds.build_match_odds",
                        _Recorder(answer=[]))

    _ok(runner.invoke(app, ["build-history"]))
    assert build.call == ((SEASONS,), {})


def test_understat_scrapes_the_training_seasons_and_the_current_one(monkeypatch):
    players = _Recorder(answer=[])
    monkeypatch.setattr("gaffer.config.load_config", _cfg)
    monkeypatch.setattr("gaffer.api.client.FPLClient", _NoClient)
    monkeypatch.setattr("gaffer.data.bootstrap.build_teams",
                        _Recorder(answer=pd.DataFrame(columns=["name", "code"])))
    monkeypatch.setattr("gaffer.data.history.season_name_codes",
                        _Recorder(answer={}))
    monkeypatch.setattr("gaffer.data.understat.history_player_index",
                        _Recorder(answer={}))
    monkeypatch.setattr("gaffer.data.understat.build_understat_player", players)
    monkeypatch.setattr("gaffer.data.understat.build_understat_team",
                        _Recorder(answer=[]))

    _ok(runner.invoke(app, ["understat"]))
    seasons, indexes, _index = players.call[0]
    assert seasons == [*SEASONS, _cfg().current_season]
    assert indexes == {s: i for i, s in enumerate(seasons)}


def test_league_sim_parses_its_seeds_count_and_drift(monkeypatch):
    sim = _Recorder(answer={})
    monkeypatch.setattr("gaffer.config.load_config", _cfg)
    monkeypatch.setattr("gaffer.api.client.FPLClient", _NoClient)
    monkeypatch.setattr("gaffer.league_sim.build_inputs", _Recorder(answer=None))
    monkeypatch.setattr("gaffer.league_sim.multi_seed", sim)
    monkeypatch.setattr("gaffer.league_sim.format_multi_seed",
                        _Recorder(answer="simulated"))

    _ok(runner.invoke(app, ["league-sim", "--seeds", "11,12",
                            "--n", "7", "--drift", "0.25"]))
    kwargs = sim.call[1]
    assert kwargs["seeds"] == [11, 12] and all(type(s) is int for s in kwargs["seeds"])
    assert kwargs["n"] == 7 and type(kwargs["n"]) is int
    assert kwargs["rival_drift"] == 0.25 and type(kwargs["rival_drift"]) is float


def test_backtest_passes_the_season_the_start_and_the_chips_flag(monkeypatch):
    run = _Recorder(answer="graded")
    patch_view(monkeypatch, _cfg)
    monkeypatch.setattr("gaffer.backtest.run_backtest", run)

    _ok(runner.invoke(app, ["backtest", "--season", "2022-23", "--start-gw", "6",
                            "--horizon", "3", "--chips"]))
    args, kwargs = run.call
    assert args == ("2022-23", 6) and type(args[1]) is int
    assert kwargs == {"horizon": 3, "chips": True} and type(kwargs["horizon"]) is int


def test_calibrate_decisions_replays_the_training_seasons_from_the_given_gw(
        monkeypatch):
    calibrate = _Recorder(answer={"transfer_surplus": {"2023-24": [1.0, 2.0]},
                                  "seasons": SEASONS})
    write = _Recorder(answer="src/gaffer/assets/decision_priors.json")
    monkeypatch.setattr("gaffer.config.load_config", _cfg)
    monkeypatch.setattr("gaffer.calibrate_decisions.run_calibration", calibrate)
    monkeypatch.setattr("gaffer.calibrate_decisions.write_priors", write)

    _ok(runner.invoke(app, ["calibrate-decisions", "--start-gw", "8"]))
    args, kwargs = calibrate.call
    assert args == (SEASONS,)
    assert kwargs == {"start_gw": 8} and type(kwargs["start_gw"]) is int
    # The asset is written through the stub, so the shipped file is untouched.
    assert write.call[0][1] == "src/gaffer/assets/decision_priors.json"


def test_diagnose_zeros_passes_the_holdout_slots_as_a_number(monkeypatch):
    diagnose = _Recorder()
    monkeypatch.setattr("gaffer.zeros_diagnostic.run_diagnostic", diagnose)

    _ok(runner.invoke(app, ["diagnose-zeros", "--holdout-slots", "12"]))
    assert diagnose.call == ((12,), {})
    assert type(diagnose.call[0][0]) is int
