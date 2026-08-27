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
                      "last38_ppg": CATEGORY_TABLE},
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


NEWS_SHADOW = {
    "run_at": "2026-09-12T00:00:00+00:00", "git_sha": "abc1234",
    "rows": 1400,
    "overall": {"brier_news": 0.0910, "brier_flags": 0.1020,
                "mae_news": 12.4, "mae_flags": 14.1, "rows": 1400},
    "by_gw": [
        {"gw": 3, "brier_news": 0.0950, "brier_flags": 0.1100,
         "mae_news": 12.9, "mae_flags": 14.8, "rows": 700,
         "cum_brier_news": 0.0950, "cum_brier_flags": 0.1100,
         "cum_mae_news": 12.9, "cum_mae_flags": 14.8},
        {"gw": 4, "brier_news": 0.0870, "brier_flags": 0.0940,
         "mae_news": 11.9, "mae_flags": 13.4, "rows": 700,
         "cum_brier_news": 0.0910, "cum_brier_flags": 0.1020,
         "cum_mae_news": 12.4, "cum_mae_flags": 14.1},
    ],
}


def test_quality_serves_the_news_shadow_scoreboard(client, tmp_path):
    (tmp_path / "reports").mkdir(exist_ok=True)
    (tmp_path / "reports" / "evaluation.json").write_text(
        json.dumps({**PAYLOAD, "news_shadow": NEWS_SHADOW}))
    body = client.get("/api/quality").json()
    assert body["news_shadow"]["rows"] == 1400
    assert body["news_shadow"]["overall"]["brier_news"] == 0.0910
    assert body["news_shadow"]["by_gw"][1]["gw"] == 4
    assert body["news_shadow"]["by_gw"][1]["cum_mae_news"] == 12.4


def test_quality_without_a_news_shadow_run_is_a_null(client, tmp_path):
    (tmp_path / "reports").mkdir(exist_ok=True)
    (tmp_path / "reports" / "evaluation.json").write_text(json.dumps(PAYLOAD))
    assert client.get("/api/quality").json()["news_shadow"] is None


def test_a_news_shadow_with_nothing_scored_yet_still_serves(client, tmp_path):
    """Before the first gameweek completes the scorer writes rows: 0 and two
    empty containers. The page renders nothing from it, but the endpoint must
    not 500 on it."""
    (tmp_path / "reports").mkdir(exist_ok=True)
    (tmp_path / "reports" / "evaluation.json").write_text(json.dumps(
        {**PAYLOAD, "news_shadow": {"run_at": "x", "git_sha": "y",
                                    "rows": 0, "overall": {}, "by_gw": []}}))
    assert client.get("/api/quality").json()["news_shadow"]["rows"] == 0
