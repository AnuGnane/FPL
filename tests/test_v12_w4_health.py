"""The core-insights health line: rows and latest date, or an honest never."""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.data import store
from gaffer.data.core_insights import CI_FIXTURE_COLS, CI_PLAYER_COLS, ci_path
from gaffer.web.app import create_app


@pytest.fixture()
def clone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    return tmp_path


def test_a_cold_clone_says_never_collected_and_renders_no_zeros(clone):
    body = TestClient(create_app()).get("/api/health").json()
    ci = body["core_insights"]
    assert ci["season"] == "2026-27"
    assert ci["collected"] is False
    assert ci["tables"] == []
    assert "gaffer core-insights" in ci["waiting_for"]


def test_a_collected_season_reports_rows_and_the_latest_date(clone):
    store.save(pd.DataFrame([{**{c: 0 for c in CI_PLAYER_COLS},
                              "season": "2026-27", "code": 1, "gw": 2}]),
               ci_path("2026-27", "players"))
    store.save(pd.DataFrame([{**{c: None for c in CI_FIXTURE_COLS},
                              "season": "2026-27", "gw": 6,
                              "kickoff": pd.Timestamp("2026-10-10T14:00Z"),
                              "team_code": 8}]),
               ci_path("2026-27", "fixtures"))
    body = TestClient(create_app()).get("/api/health").json()
    ci = body["core_insights"]
    assert ci["collected"] is True
    assert ci["waiting_for"] is None
    by = {t["table"]: t for t in ci["tables"]}
    assert by["players"]["rows"] == 1
    assert by["fixtures"]["latest"] == "2026-10-10"
    # Elo was never written on this clone, so it reports zero rows and says
    # so rather than being omitted — an absent Elo table is the archive's
    # state for 2026-27 today, and hiding it would hide that.
    assert by["elo"]["rows"] == 0


def test_the_health_line_added_no_route(clone):
    """The block is an additive field on ``Health``, not an endpoint of its
    own. Asserted by absence rather than by a count: the absolute route pin
    lives in one file (tests/test_v11_degradation.py) and duplicating the
    number here would make every future route a two-file edit."""
    paths = create_app().openapi()["paths"]
    assert not [p for p in paths if p.startswith("/api/core-insights")]
    assert "/api/health" in paths
