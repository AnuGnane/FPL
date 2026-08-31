"""``ep_movers`` on ``/api/advice/diff``: additive, and honestly absent.

The endpoint's existing contract is that it is never an error, so the new
fields have to survive every path the old ones already survive — including the
one where ``available`` is false. That case is the interesting one: a first
run of the week is exactly when a retrain happened, so the movers can be
non-empty while there is no plan diff at all (plan A10).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import (COMPONENT_COLS, append_advice_history,
                              save_components)
from gaffer.web.app import create_app

GW = 5


def _frame(eps: dict[int, float]) -> pd.DataFrame:
    out = pd.DataFrame([{"code": code, "name": f"P{code}", "gw": GW,
                         "ep": ep} for code, ep in eps.items()])
    for col in COMPONENT_COLS:
        if col not in out.columns:
            out[col] = float("nan")
    return out[COMPONENT_COLS]


ADVICE = {"gw": GW, "buys": [], "sells": [], "expected_pts": 60.0,
          "captain": {"code": 11, "name": "P11"}}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    (tmp_path / f"reports/gw{GW}-advice.json").write_text(json.dumps(ADVICE))
    return TestClient(create_app())


def test_no_predecessor_is_a_null_count_not_a_zero(client):
    """The first run after this cycle merges says nothing rather than
    claiming a quiet retrain."""
    save_components(_frame({11: 5.0}), GW)
    body = client.get(f"/api/advice/diff?gw={GW}").json()
    assert body["ep_movers"] == []
    assert body["ep_movers_count"] is None


def test_a_second_run_reports_what_moved(client):
    save_components(_frame({11: 5.0, 22: 7.0}), GW)
    save_components(_frame({11: 6.4, 22: 7.1}), GW)
    body = client.get(f"/api/advice/diff?gw={GW}").json()
    assert body["ep_movers_count"] == 1
    assert body["ep_movers"][0]["name"] == "P11"
    assert body["ep_movers"][0]["delta"] == pytest.approx(1.4)


def test_a_retrain_that_moved_nobody_is_a_count_of_zero(client):
    save_components(_frame({11: 5.0}), GW)
    save_components(_frame({11: 5.0}), GW)
    body = client.get(f"/api/advice/diff?gw={GW}").json()
    assert body["ep_movers"] == [] and body["ep_movers_count"] == 0


def test_the_movers_ride_a_first_run_of_the_week(client):
    """A10: ``available`` is false and there is still something true to
    say."""
    save_components(_frame({11: 5.0}), GW)
    save_components(_frame({11: 6.4}), GW)
    body = client.get(f"/api/advice/diff?gw={GW}").json()
    assert body["available"] is False
    assert body["ep_movers_count"] == 1


def test_the_movers_ride_a_full_diff_too(client):
    save_components(_frame({11: 5.0}), GW)
    save_components(_frame({11: 6.4}), GW)
    # Explicit stamps, ``test_web_advice``'s idiom: the history file is named
    # to the second, so two banked runs inside one second are one file and
    # there would be nothing to diff.
    append_advice_history(ADVICE, GW, now=datetime(2026, 8, 31, 9, 0,
                                                   tzinfo=timezone.utc))
    append_advice_history({**ADVICE, "expected_pts": 62.0}, GW,
                          now=datetime(2026, 8, 31, 17, 0,
                                       tzinfo=timezone.utc))
    body = client.get(f"/api/advice/diff?gw={GW}").json()
    assert body["available"] is True and body["changed"] is True
    assert body["ep_movers_count"] == 1


def test_no_advice_at_all_is_still_not_an_error(client, tmp_path):
    (tmp_path / f"reports/gw{GW}-advice.json").unlink()
    body = client.get("/api/advice/diff").json()
    assert body["available"] is False and body["ep_movers"] == []


def test_a_corrupt_predecessor_is_a_null_count_not_a_500(client, tmp_path):
    from gaffer.artifacts import prev_components_path

    save_components(_frame({11: 5.0}), GW)
    save_components(_frame({11: 6.4}), GW)
    prev_components_path(GW).write_text("garbage")
    body = client.get(f"/api/advice/diff?gw={GW}").json()
    assert body["ep_movers_count"] is None
