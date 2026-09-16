"""What the Health page says about the two halves of the model nobody watched.

v19g §2.1 and §2.2. The EP calibration fits a position only once that position
has ``MIN_ROWS`` sixty-minute appearances, so its fourth key arrived by
accrual part-way through a season and nothing anywhere said so — and nothing
would say it if one dropped back out, because an unfitted position is the
identity and the identity looks exactly like a delta of zero.

The team model's band is the same shape of silence: ``p_cs_model`` and
``e_gc_model`` are unbounded, and a gameweek with no bookmaker odds is priced
on them alone. Neither number changes here. Both readers are read-only over
what is already on disk, and both answer ``None`` rather than raising, because
``/api/health`` is polled by an open tab.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import COMPONENT_COLS, save_components
from gaffer.models.calibrate import CalibrationModel
from gaffer.models.persistence import save_model
from gaffer.web.app import create_app
from gaffer.web.routers.meta import calibration_health, team_model_health

GW = 6


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return TestClient(create_app())


def _calibration(by_pos: dict[str, float]) -> None:
    """Bank a calibration through the same writer training uses.

    Not a hand-rolled joblib: the point of reading it back through
    ``load_model`` is that the route cannot drift from where training writes,
    and a test that pickles its own object would not notice if it did.
    """
    model = CalibrationModel()
    model.by_pos = dict(by_pos)
    save_model(model, "calibration", {"rows": len(by_pos)})


def _components(rows: list[dict]) -> None:
    """A components file with the club-fixture columns filled in.

    ``tests/test_web_advice_movers.py``'s ``_frame`` with the team columns
    added, per the same argument: everything else in ``COMPONENT_COLS`` is
    NaN, so a reader that quietly depends on a column it did not declare
    fails here rather than in a season.
    """
    out = pd.DataFrame(rows)
    for col in COMPONENT_COLS:
        if col not in out.columns:
            out[col] = float("nan")
    save_components(out[COMPONENT_COLS], GW)


def _fixture_row(team: int, opp: int, gw: int, p_cs: float, e_gc: float,
                 weight: float, code: int) -> dict:
    return {"code": code, "name": f"P{code}", "gw": gw, "team_code": team,
            "opp_code": opp, "p_cs_model": p_cs, "e_gc_model": e_gc,
            "odds_weight": weight, "ep": 4.0}


def test_a_fitted_calibration_names_all_four_positions(client):
    _calibration({"GKP": 0.43, "DEF": 1.06, "MID": 1.15, "FWD": 0.99})
    body = client.get("/api/health").json()
    cal = body["calibration"]
    assert cal["fitted_positions"] == ["GKP", "DEF", "MID", "FWD"]
    assert cal["missing"] == []
    assert cal["by_pos"]["GKP"] == pytest.approx(0.43)
    assert cal["min_rows"] == 200
    assert cal["saved_at"] is not None


def test_a_position_that_never_reached_the_floor_is_named_as_missing(client):
    """v19g §2.1: three keys and four groups is the state the page exists to
    report, and it is not the same news as a delta of zero."""
    _calibration({"DEF": 1.06, "MID": 1.15, "FWD": 0.99})
    cal = client.get("/api/health").json()["calibration"]
    assert cal["missing"] == ["GKP"]
    assert cal["fitted_positions"] == ["DEF", "MID", "FWD"]
    assert "GKP" not in cal["by_pos"]


def test_the_positions_are_ordered_by_the_model_not_by_the_dict(client):
    """A row whose columns move between polls is a row nobody can read."""
    _calibration({"FWD": 0.99, "GKP": 0.43, "MID": 1.15, "DEF": 1.06})
    cal = client.get("/api/health").json()["calibration"]
    assert cal["fitted_positions"] == ["GKP", "DEF", "MID", "FWD"]


def test_no_calibration_artifact_is_an_absence_not_a_failure(client):
    body = client.get("/api/health").json()
    assert body["calibration"] is None


def test_an_unreadable_calibration_is_an_absence_too(tmp_path, monkeypatch):
    """The route is polled, so a truncated pickle is a blank line on the tab
    and never a 500 on the page somebody opened to find out what broke."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "calibration.joblib").write_text("not a pickle")
    client = TestClient(create_app())
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["calibration"] is None
    assert calibration_health() is None


def test_the_band_counts_club_fixtures_not_player_rows(client):
    """Three clubs, one fixture each, three players apiece — and the one with
    no market odds is counted once, not three times (v19g §2.2).

    Deliberately not a two-club frame with one of each: there the fixtures
    priced on the market and the fixtures priced without it are the same
    count, so a reader that inverted the test would pass. Three fixtures with
    one zero is the smallest frame the two answers disagree on.
    """
    rows = []
    for i in range(3):
        rows.append(_fixture_row(11, 6, GW, 0.44, 0.95, 0.8, code=100 + i))
        rows.append(_fixture_row(6, 11, GW, 0.20, 2.10, 0.8, code=200 + i))
        rows.append(_fixture_row(40, 88, GW, 0.31, 1.40, 0.0, code=300 + i))
    _components(rows)
    body = client.get("/api/health").json()
    team = body["team_model"]
    assert team["gw"] == GW
    assert team["fixtures"] == 3
    assert team["zero_odds_fixtures"] == 1
    assert team["min_e_gc_model"] == pytest.approx(0.95)
    assert team["max_p_cs_model"] == pytest.approx(0.44)


def test_a_double_gameweek_is_two_fixtures_not_one(client):
    """The reduction keys on the opponent as well as the week: a club with
    two fixtures in one gameweek is the week this reading matters most, and
    keying on ``(team_code, gw)`` alone would hide one of them."""
    _components([
        _fixture_row(11, 6, GW, 0.44, 0.95, 0.8, code=100),
        _fixture_row(11, 40, GW, 0.30, 1.40, 0.0, code=101),
    ])
    team = client.get("/api/health").json()["team_model"]
    assert team["fixtures"] == 2 and team["zero_odds_fixtures"] == 1


def test_a_missing_odds_weight_counts_as_no_market(client):
    """A NaN weight is a fixture priced on the model alone, which is the same
    news as a zero and is reported as such."""
    _components([
        _fixture_row(11, 6, GW, 0.44, 0.95, float("nan"), code=100),
        _fixture_row(6, 11, GW, 0.20, 2.10, 0.8, code=200),
        _fixture_row(40, 88, GW, 0.31, 1.40, 0.8, code=300),
    ])
    team = client.get("/api/health").json()["team_model"]
    assert team["fixtures"] == 3 and team["zero_odds_fixtures"] == 1


def test_no_components_file_is_an_absence(client):
    assert client.get("/api/health").json()["team_model"] is None
    assert team_model_health() is None


def test_a_components_file_without_the_model_columns_says_nothing(
        tmp_path, monkeypatch):
    """A file banked before the team model's columns existed is not a band of
    zeros; it is a file with nothing to say."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    pd.DataFrame([{"code": 100, "name": "P100", "gw": GW, "ep": 4.0}]) \
        .to_parquet(tmp_path / f"reports/components_gw{GW}.parquet",
                    index=False)
    client = TestClient(create_app())
    assert client.get("/api/health").json()["team_model"] is None


def test_health_never_500s_on_a_corrupt_components_file(tmp_path,
                                                        monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    (tmp_path / f"reports/components_gw{GW}.parquet").write_text("garbage")
    client = TestClient(create_app())
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["team_model"] is None


def test_the_calibration_stamp_comes_from_the_models_own_sidecar(client,
                                                                 tmp_path):
    """``saved_at`` is the sidecar's, the same field the Models table above
    reads, so the two lines cannot date the same artifact differently."""
    _calibration({"GKP": 0.4, "DEF": 1.0, "MID": 1.1, "FWD": 0.9})
    sidecar = json.loads(
        (tmp_path / "models" / "calibration.meta.json").read_text())
    assert client.get("/api/health").json()["calibration"]["saved_at"] \
        == sidecar["saved_at"]
