"""``gaffer prices``: the stdout contract, and the bank bolted beside it.

D1c pins the printed output, so the interesting assertions are all about what
must *not* change — and about the ordering that guarantees it. The banking
runs after the alerts are printed, so a broken bank is a line of apology under
a complete alert list rather than a missing alert list.
"""

from __future__ import annotations

import pandas as pd
import pytest
from typer.testing import CliRunner

from gaffer.cli import app

RUNNER = CliRunner()

BOOTSTRAP = {"elements": [], "teams": [], "events": []}

PLAYERS = pd.DataFrame({
    "code": [11, 22],
    "name": ["Saka", "Rice"],
    "position": ["MID", "MID"],
    "now_cost": [101, 65],
    "selected_by_percent": [40.0, 12.0],
    "price_change_percent": [98.5, 3.0],
    "price_change_calibrating": [False, False],
})


@pytest.fixture()
def wired(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("gaffer.api.client.FPLClient.get_bootstrap",
                        lambda self: BOOTSTRAP)
    monkeypatch.setattr("gaffer.data.bootstrap.build_players",
                        lambda raw: PLAYERS)
    return tmp_path


def test_the_printed_contract_is_unchanged(wired):
    result = RUNNER.invoke(app, ["prices"])
    assert result.exit_code == 0
    assert "Saka: rise (98.5%)" in result.stdout
    assert "Rice" not in result.stdout          # below the 90 threshold


def test_the_run_banks_every_player_not_only_the_alert(wired):
    from gaffer.price_log import load_price_log

    assert RUNNER.invoke(app, ["prices"]).exit_code == 0
    log = load_price_log()
    assert sorted(log["code"]) == [11, 22]
    assert "Banked 2 price readings" in RUNNER.invoke(app,
                                                     ["prices"]).stdout


def test_a_second_run_the_same_day_does_not_duplicate(wired):
    from gaffer.price_log import load_price_log

    RUNNER.invoke(app, ["prices"])
    RUNNER.invoke(app, ["prices"])
    assert len(load_price_log()) == 2


def test_a_failing_bank_still_prints_the_alerts(wired, monkeypatch):
    """A2's ordering, asserted: the user's answer comes first."""
    monkeypatch.setattr("gaffer.price_log.append_prices",
                        lambda rows: (_ for _ in ()).throw(
                            OSError("read-only file system")))
    result = RUNNER.invoke(app, ["prices"])
    assert result.exit_code == 0
    assert "Saka: rise (98.5%)" in result.stdout
    assert "price log not written" in result.stdout


def test_a_dead_api_is_still_not_a_traceback(wired, monkeypatch):
    def boom(self):
        raise RuntimeError("connection refused")

    monkeypatch.setattr("gaffer.api.client.FPLClient.get_bootstrap", boom)
    result = RUNNER.invoke(app, ["prices"])
    assert result.exit_code == 0
    assert "price check failed" in result.stdout
