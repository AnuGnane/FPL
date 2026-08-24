import json
from pathlib import Path

import httpx
import pandas as pd
import pytest

import gaffer.data.odds as odds_mod
import gaffer.data.store as store
from gaffer.config import load_config
from gaffer.data.odds import (OddsClient, devig, invert_odds, odds_frame,
                              resolve_team)
from gaffer.errors import GafferError

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


# ---------------------------------------------------------------- odds_frame

_TEAMS = pd.DataFrame([
    {"team_id": 1, "code": 3, "name": "Arsenal", "short_name": "ARS"},
    {"team_id": 2, "code": 43, "name": "Man City", "short_name": "MCI"},
    {"team_id": 3, "code": 14, "name": "Liverpool", "short_name": "LIV"},
])

_EVENTS = pd.DataFrame([
    {"gw": 1, "deadline_time": "2026-08-22T10:00:00Z"},
    {"gw": 2, "deadline_time": "2026-08-29T10:00:00Z"},
    {"gw": 3, "deadline_time": "2026-09-05T10:00:00Z"},
])


def test_resolve_team_aliases_and_identity():
    assert resolve_team("Manchester City") == "Man City"
    assert resolve_team("Tottenham Hotspur") == "Spurs"
    assert resolve_team("Nottingham Forest") == "Nott'm Forest"
    assert resolve_team("Brighton and Hove Albion") == "Brighton"
    assert resolve_team("AFC Bournemouth") == "Bournemouth"
    assert resolve_team("Coventry") == "Coventry City"
    assert resolve_team("Hull") == "Hull City"
    assert resolve_team("Leeds United") == "Leeds"
    # already an FPL name -> identity
    assert resolve_team("Arsenal") == "Arsenal"
    assert resolve_team("Nott'm Forest") == "Nott'm Forest"


def test_resolve_team_unknown_raises_naming_team():
    with pytest.raises(GafferError) as exc:
        resolve_team("Racing Club de Lens")
    assert "Racing Club de Lens" in str(exc.value)


def test_odds_frame_two_rows_per_fixture_favorite_scores_more():
    df = odds_frame(SAMPLE_ODDS, _TEAMS, _EVENTS)
    assert list(df.columns) == ["team_code", "opp_code", "gw",
                                "odds_e_goals_for", "odds_e_goals_against"]
    assert len(df) == 2
    assert set(df["gw"]) == {2}          # 2026-08-29T14:00 -> GW2 window
    home = df[df.team_code == 3].iloc[0]   # Arsenal, the favorite (2.4 v 2.9)
    away = df[df.team_code == 43].iloc[0]
    assert home["odds_e_goals_for"] > home["odds_e_goals_against"]
    assert away["odds_e_goals_for"] == home["odds_e_goals_against"]
    assert away["odds_e_goals_against"] == home["odds_e_goals_for"]
    assert away["odds_e_goals_for"] < away["odds_e_goals_against"]


def test_odds_frame_uses_first_bookmaker_only():
    payload = [dict(SAMPLE_ODDS[0])]
    second = {"key": "bk2", "markets": [
        {"key": "h2h", "outcomes": [
            {"name": "Arsenal", "price": 9.0},
            {"name": "Manchester City", "price": 1.2},
            {"name": "Draw", "price": 6.0}]}]}
    payload[0]["bookmakers"] = SAMPLE_ODDS[0]["bookmakers"] + [second]
    df = odds_frame(payload, _TEAMS, _EVENTS)
    ref = odds_frame(SAMPLE_ODDS, _TEAMS, _EVENTS)
    assert df["odds_e_goals_for"].tolist() == ref["odds_e_goals_for"].tolist()


def test_odds_frame_skips_fixture_outside_all_deadline_windows():
    early = [dict(SAMPLE_ODDS[0], commence_time="2026-08-01T14:00:00Z")]
    assert odds_frame(early, _TEAMS, _EVENTS).empty
    # ...but the columns still exist so a merge on an empty frame works
    assert list(odds_frame(early, _TEAMS, _EVENTS).columns) == [
        "team_code", "opp_code", "gw", "odds_e_goals_for",
        "odds_e_goals_against"]


def test_odds_frame_unmapped_team_raises_gaffer_error():
    bad = [dict(SAMPLE_ODDS[0], home_team="Racing Club de Lens")]
    with pytest.raises(GafferError) as exc:
        odds_frame(bad, _TEAMS, _EVENTS)
    assert "Racing Club de Lens" in str(exc.value)


def test_odds_frame_without_totals_market_uses_neutral_prior():
    no_totals = [{
        "home_team": "Arsenal", "away_team": "Liverpool",
        "commence_time": "2026-08-29T14:00:00Z",
        "bookmakers": [{"key": "bk1", "markets": [
            {"key": "h2h", "outcomes": [
                {"name": "Arsenal", "price": 2.4},
                {"name": "Liverpool", "price": 2.9},
                {"name": "Draw", "price": 3.4}]}]}]}]
    df = odds_frame(no_totals, _TEAMS, _EVENTS)
    assert len(df) == 2
    assert df["odds_e_goals_for"].notna().all()


def test_odds_frame_matches_h2h_outcomes_by_name_not_position():
    shuffled = [{
        "home_team": "Arsenal", "away_team": "Manchester City",
        "commence_time": "2026-08-29T14:00:00Z",
        "bookmakers": [{"key": "bk1", "markets": [
            {"key": "h2h", "outcomes": [
                {"name": "Draw", "price": 3.4},
                {"name": "Manchester City", "price": 2.9},
                {"name": "Arsenal", "price": 2.4}]},
            {"key": "totals", "outcomes": [
                {"name": "Under", "point": 2.5, "price": 1.9},
                {"name": "Over", "point": 2.5, "price": 1.9}]}]}]}]
    df = odds_frame(shuffled, _TEAMS, _EVENTS)
    ref = odds_frame(SAMPLE_ODDS, _TEAMS, _EVENTS)
    assert df["odds_e_goals_for"].tolist() == ref["odds_e_goals_for"].tolist()


def test_run_advise_fetches_odds_before_building_the_team_future():
    """No cheap end-to-end harness for run_advise (see test_assemble), so pin
    the seam at the source level: odds are fetched first, guarded so a bad
    feed cannot block advice, and merged onto tg_future afterwards."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    fetch = src.index("odds_frame(raw_odds, teams, events)")
    build = src.index("tg_future = build_team_future(")
    merge = src.index("merge_team_odds(tg_future, odds_df)")
    assert fetch < build < merge
    assert "if cfg.odds_api_key:" in src
    assert "except Exception" in src
    # The odds join itself is a left join keyed by fixture, not just by team.
    from gaffer.advise import merge_team_odds
    msrc = inspect.getsource(merge_team_odds)
    assert 'how="left"' in msrc
    assert '["code", "gw", "opp_code"]' in msrc
    assert '["team_code", "gw", "opp_code"]' in msrc
    # The DGW drop_duplicates hack collapsed a team's two fixtures into one;
    # opp_code in the key replaces it.
    assert "drop_duplicates" not in msrc
    assert "drop_duplicates" not in src


def test_run_advise_persists_the_weekly_odds_frame():
    """Snapshotted for a future training backfill: history frames have no
    odds, so the only way to ever train on them is to bank them weekly."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    assert 'store.save(odds_df, f"live/odds/gw{gw}.parquet")' in src


def test_predict_components_blends_odds_before_merging_onto_players():
    """The blend has to land on the team frame while it is still one row per
    team-fixture — after the many-to-one merge onto players it would be
    applied once per player."""
    import inspect

    from gaffer.advise import predict_components

    src = inspect.getsource(predict_components)
    blend = src.index("blend_team_odds(")
    merge = src.index("comp.merge(tp")
    assert blend < merge


_DGW_ODDS = [
    dict(SAMPLE_ODDS[0]),
    {"home_team": "Liverpool", "away_team": "Arsenal",
     "commence_time": "2026-08-31T19:00:00Z",
     "bookmakers": [{"key": "bk1", "markets": [
         {"key": "h2h", "outcomes": [
             {"name": "Liverpool", "price": 2.0},
             {"name": "Arsenal", "price": 3.6},
             {"name": "Draw", "price": 3.5}]},
         {"key": "totals", "outcomes": [
             {"name": "Over", "point": 2.5, "price": 1.7},
             {"name": "Under", "point": 2.5, "price": 2.1}]}]}]},
]


def test_odds_frame_carries_opp_code_for_both_rows():
    df = odds_frame(SAMPLE_ODDS, _TEAMS, _EVENTS).set_index("team_code")
    assert df.loc[3, "opp_code"] == 43        # Arsenal's opponent, Man City
    assert df.loc[43, "opp_code"] == 3


def test_odds_frame_double_gameweek_merges_onto_team_future_without_fanout():
    """A DGW gives one team two rows in the same gameweek; only ``opp_code``
    tells them apart, so it has to be part of the merge key."""
    from gaffer.advise import build_team_future, merge_team_odds

    odds = odds_frame(_DGW_ODDS, _TEAMS, _EVENTS)
    assert len(odds[odds["team_code"] == 3]) == 2      # Arsenal twice in GW2

    tg = pd.DataFrame([
        {"season_idx": 1, "gw": 1, "kickoff_time": "2026-08-23T14:00:00Z",
         "code": c, "opp_code": o, "home": h, "gf": 1, "ga": 1, "cs": 0}
        for c, o, h in ((3, 14, 1.0), (14, 3, 0.0), (43, 3, 1.0), (3, 43, 0.0))
    ])
    future = pd.DataFrame([
        {"team_code": 3, "opp_code": 43, "was_home": True, "gw": 2,
         "season_idx": 1, "kickoff_time": "2026-08-29T14:00:00Z"},
        {"team_code": 3, "opp_code": 14, "was_home": False, "gw": 2,
         "season_idx": 1, "kickoff_time": "2026-08-31T19:00:00Z"},
    ])
    elo_final = {3: 1600.0, 43: 1580.0, 14: 1590.0}
    tg_future = build_team_future(tg, future, gws=[2], season_idx=1,
                                  elo_final=elo_final)
    assert len(tg_future) == 2
    assert "opp_code" in tg_future.columns

    merged = merge_team_odds(tg_future, odds)
    assert len(merged) == 2                            # no fan-out
    assert "team_code" not in merged.columns
    by_opp = merged.set_index("opp_code")
    exp = odds[odds["team_code"] == 3].set_index("opp_code")
    for opp in (43, 14):
        assert by_opp.loc[opp, "odds_e_goals_for"] == pytest.approx(
            exp.loc[opp, "odds_e_goals_for"])
        assert by_opp.loc[opp, "odds_e_goals_against"] == pytest.approx(
            exp.loc[opp, "odds_e_goals_against"])
    # ...and the two fixtures really do carry different odds, so a merge that
    # collapsed them would be caught above rather than passing by accident.
    assert (by_opp.loc[43, "odds_e_goals_against"]
            != by_opp.loc[14, "odds_e_goals_against"])


def test_merge_team_odds_leaves_uncovered_fixtures_as_nan():
    from gaffer.advise import merge_team_odds

    tg_future = pd.DataFrame([
        {"code": 3, "opp_code": 43, "gw": 2, "season_idx": 1},
        {"code": 14, "opp_code": 99, "gw": 2, "season_idx": 1},
    ])
    merged = merge_team_odds(tg_future, odds_frame(SAMPLE_ODDS, _TEAMS, _EVENTS))
    assert len(merged) == 2
    assert merged.set_index("code").loc[3, "odds_e_goals_for"] > 0
    assert pd.isna(merged.set_index("code").loc[14, "odds_e_goals_for"])
