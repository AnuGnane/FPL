"""Health names each v20 arm's switch (holiday F-30).

v20 spec §2 v20c "Served numbers move" and §3's gate line: the night shift's
screenshot pairs need the page itself to say which switches were on, or a
pair taken with a switch left over from a replay reads as the arm's effect.
The reader is read-only over the switch constants (four since F-122, five
since F-91) and never raises.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import gaffer.backtest as backtest
from gaffer.models import components, dixon_coles, train
from gaffer.web.app import create_app
from gaffer.web.routers.meta import arm_switches

NAMES = ["models.components.BONUS_SEES_ATTACK",
         "models.dixon_coles.MU_BOUNDS",
         "backtest.REPLAY_TEAM_MODEL",
         "backtest.REPLAY_AVAILABILITY",
         "models.train.PPLAY_TOP_BIN_STEP"]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return TestClient(create_app())


def test_every_switch_reads_off_as_shipped(client):
    arms = client.get("/api/health").json()["arms"]
    assert [a["name"] for a in arms] == NAMES
    assert [(a["on"], a["value"]) for a in arms] == [
        (False, "False"), (False, "None"), (False, "False"), (False, "None"),
        (False, "False")]


def test_each_switch_reads_on_with_its_value_when_patched(monkeypatch):
    monkeypatch.setattr(components, "BONUS_SEES_ATTACK", True)
    monkeypatch.setattr(dixon_coles, "MU_BOUNDS", (0.1, 9.0))
    monkeypatch.setattr(backtest, "REPLAY_TEAM_MODEL", True)
    monkeypatch.setattr(backtest, "REPLAY_AVAILABILITY", "flags")
    monkeypatch.setattr(train, "PPLAY_TOP_BIN_STEP", True)
    rows = {a.name: (a.on, a.value) for a in arm_switches()}
    assert rows == {NAMES[0]: (True, "True"),
                    NAMES[1]: (True, "(0.1, 9.0)"),
                    NAMES[2]: (True, "True"),
                    NAMES[3]: (True, "'flags'"),
                    NAMES[4]: (True, "True")}


def test_one_switch_on_leaves_the_others_off(monkeypatch):
    monkeypatch.setattr(dixon_coles, "MU_BOUNDS", (0.2, 4.5))
    assert [a.on for a in arm_switches()] == [False, True, False, False, False]
