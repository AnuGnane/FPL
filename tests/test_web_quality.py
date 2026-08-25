import json

import pytest
from fastapi.testclient import TestClient

from gaffer.web.app import create_app

CATEGORY_TABLE = {cat: {"rmse": 1.0, "mae": 0.5, "n": 100}
                  for cat in ["zeros", "blanks", "tickers", "haulers", "all"]}

PAYLOAD = {
    "current": {
        "run_at": "2026-08-25T00:00:00+00:00", "git_sha": "abc1234",
        "holdout_slots": 10,
        "stratified": {"all": CATEGORY_TABLE, "starters": CATEGORY_TABLE},
        "heads": {"p_play": {"log_loss": 0.2732,
                             "reliability": [{"n": 40, "pred": 0.9,
                                              "obs": 0.88}]}},
        "baselines": {"last5": CATEGORY_TABLE,
                      "season_ppg": CATEGORY_TABLE},
    },
    "benchmark": {
        "run_at": "2026-08-25T01:00:00+00:00", "git_sha": "abc1234",
        "test_season": "2024-25",
        "stratified": {"all": CATEGORY_TABLE},
        "references": {"openfpl": {"haulers": {"rmse": 5.142, "mae": 4.317}},
                       "fplreview": {"haulers": {"rmse": 5.172,
                                                 "mae": 4.381}}},
        "caveat": "yardstick, not a controlled comparison",
    },
    "decomposition": {
        "run_at": "2026-08-25T02:00:00+00:00", "git_sha": "abc1234",
        "season": "2025-26", "start_gw": 5,
        "cells": {"model_h1": {"total": 1800, "per_gw": 52.94, "hits": 4},
                  "model_h3": {"total": 1850, "per_gw": 54.41, "hits": 3},
                  "oracle_h1": {"total": 2600, "per_gw": 76.47, "hits": 0},
                  "oracle_h3": {"total": 2700, "per_gw": 79.41, "hits": 0}},
        "forecast_gap_h3": 850.0, "planning_ceiling": 100.0,
    },
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return TestClient(create_app(), raise_server_exceptions=False)


def test_quality_without_an_artifact_tells_you_to_run_evaluate(client):
    response = client.get("/api/quality")
    assert response.status_code == 422
    assert "gaffer evaluate" in response.json()["detail"]


def test_quality_returns_every_stored_mode(client, tmp_path):
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "evaluation.json").write_text(json.dumps(PAYLOAD))
    body = client.get("/api/quality").json()
    assert body["current"]["holdout_slots"] == 10
    assert body["current"]["stratified"]["all"]["haulers"]["rmse"] == 1.0
    assert body["current"]["heads"]["p_play"]["reliability"][0]["obs"] == 0.88
    assert body["benchmark"]["references"]["openfpl"]["haulers"]["mae"] \
        == 4.317
    assert body["decomposition"]["forecast_gap_h3"] == 850.0


def test_quality_tolerates_a_partial_artifact(client, tmp_path):
    """A benchmark run that has never happened is a null, not a 500."""
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "evaluation.json").write_text(
        json.dumps({"current": PAYLOAD["current"]}))
    body = client.get("/api/quality").json()
    assert body["benchmark"] is None and body["decomposition"] is None
    assert body["current"]["git_sha"] == "abc1234"
