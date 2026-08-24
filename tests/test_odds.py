import json
from pathlib import Path

import httpx
import pytest

import gaffer.data.odds as odds_mod
import gaffer.data.store as store
from gaffer.config import load_config
from gaffer.data.odds import OddsClient, devig, invert_odds

SAMPLE_ODDS = [{
    "home_team": "Arsenal", "away_team": "Manchester City",
    "commence_time": "2026-08-29T14:00:00Z",
    "bookmakers": [{"key": "bk1", "markets": [
        {"key": "h2h", "outcomes": [
            {"name": "Arsenal", "price": 2.4},
            {"name": "Manchester City", "price": 2.9},
            {"name": "Draw", "price": 3.4}]},
        {"key": "totals", "outcomes": [
            {"name": "Over", "point": 2.5, "price": 1.9},
            {"name": "Under", "point": 2.5, "price": 1.9}]}]}]},
]


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_get_epl_odds_requests_expected_url_and_snapshots(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    seen = {}

    def handler(request):
        seen["url"] = str(request.url).split("?")[0]
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=SAMPLE_ODDS)

    client = OddsClient("secret-key", client=_client(handler))
    data = client.get_epl_odds()

    assert seen["url"] == "https://api.the-odds-api.com/v4/sports/soccer_epl/odds"
    assert seen["params"] == {
        "regions": "eu", "markets": "h2h,totals", "apiKey": "secret-key"}
    assert data == SAMPLE_ODDS

    snaps = list((tmp_path / "raw").glob("odds-*.json"))
    assert len(snaps) == 1
    assert json.loads(snaps[0].read_text()) == SAMPLE_ODDS


def test_missing_key_returns_none_without_request(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json=SAMPLE_ODDS)

    for key in ("", None):
        client = OddsClient(key, client=_client(handler))
        assert client.get_epl_odds() is None
    assert calls["n"] == 0
    assert not list(tmp_path.glob("**/odds-*.json"))


def test_retries_after_500_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500)
        return httpx.Response(200, json=SAMPLE_ODDS)

    client = OddsClient("k", client=_client(handler), backoff=0.0)
    assert client.get_epl_odds() == SAMPLE_ODDS
    assert calls["n"] == 2


def test_fails_fast_on_403(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(403)

    client = OddsClient("k", client=_client(handler), backoff=0.0)
    try:
        client.get_epl_odds()
        assert False, "should have raised"
    except httpx.HTTPStatusError:
        pass
    assert calls["n"] == 1


def test_retries_on_429_then_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(429)

    client = OddsClient("k", client=_client(handler), retries=3, backoff=0.0)
    try:
        client.get_epl_odds()
        assert False, "should have raised"
    except httpx.HTTPStatusError:
        pass
    assert calls["n"] == 3


def test_no_sleep_after_final_attempt(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    sleeps = []
    monkeypatch.setattr(odds_mod.time, "sleep", sleeps.append)

    def handler(request):
        return httpx.Response(500)

    client = OddsClient("k", client=_client(handler), retries=3, backoff=0.001)
    try:
        client.get_epl_odds()
        assert False, "should have raised"
    except httpx.HTTPStatusError:
        pass
    assert len(sleeps) == 2


_BASE_CFG = ('[fpl]\nentry_id = 123\nleague_id = 456\n'
             '[data]\ntrain_seasons = ["2022-23"]\ncurrent_season = "2026-27"\n')


def _write(tmp_path: Path, extra: str) -> Path:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(_BASE_CFG + extra)
    return cfg_file


def test_config_odds_section_absent(tmp_path):
    assert load_config(_write(tmp_path, "")).odds_api_key == ""


def test_config_odds_section_empty(tmp_path):
    assert load_config(_write(tmp_path, "[odds]\n")).odds_api_key == ""


def test_config_odds_section_populated(tmp_path):
    cfg = load_config(_write(tmp_path, '[odds]\napi_key = "abc123"\n'))
    assert cfg.odds_api_key == "abc123"


def test_shipped_config_toml_loads():
    assert load_config("config.toml").odds_api_key == ""


def _poisson_probs(mu_h, mu_a, cap=10):
    from math import exp, factorial
    ph = [exp(-mu_h) * mu_h**k / factorial(k) for k in range(cap + 1)]
    pa = [exp(-mu_a) * mu_a**k / factorial(k) for k in range(cap + 1)]
    win = draw = away = over = 0.0
    for h in range(cap + 1):
        for a in range(cap + 1):
            pr = ph[h] * pa[a]
            if h > a: win += pr
            elif h == a: draw += pr
            else: away += pr
            if h + a >= 3: over += pr
    return win, draw, away, over


def test_devig_normalizes_implied_probabilities():
    p = devig([2.0, 4.0, 4.0])
    assert p == pytest.approx([0.5, 0.25, 0.25])
    p = devig([1.8, 3.6, 3.6])
    assert sum(p) == pytest.approx(1.0)


def test_invert_odds_recovers_known_mus():
    ph, pd_, pa, pover = _poisson_probs(1.8, 1.0)
    mu_h, mu_a = invert_odds(ph, pd_, pa, pover)
    assert mu_h == pytest.approx(1.8, abs=0.1)
    assert mu_a == pytest.approx(1.0, abs=0.1)


def test_invert_odds_symmetric_case():
    ph, pd_, pa, pover = _poisson_probs(1.3, 1.3)
    mu_h, mu_a = invert_odds(ph, pd_, pa, pover)
    assert mu_h == pytest.approx(mu_a, abs=0.051)   # grid step tolerance


def test_invert_odds_is_deterministic():
    ph, pd_, pa, pover = _poisson_probs(2.1, 0.7)
    first = invert_odds(ph, pd_, pa, pover)
    second = invert_odds(ph, pd_, pa, pover)
    assert first == second
    assert isinstance(first, tuple) and len(first) == 2
