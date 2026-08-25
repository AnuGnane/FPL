import json
from pathlib import Path

import httpx
import pandas as pd
import pytest

import gaffer.data.odds as odds_mod
import gaffer.data.store as store
from gaffer.config import load_config
from gaffer.data.odds import (ODDS_FRAME_COLS, OddsClient, devig, invert_odds,
                              odds_frame, resolve_team)
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


def test_merge_team_odds_refuses_a_double_listed_fixture():
    """A fixture listed twice by the feed would fan the team-future row out
    into two, and every player at that club would then be scored twice.
    The merge is declared many-to-one so it raises instead."""
    import pandas as pd
    import pytest
    from pandas.errors import MergeError

    from gaffer.advise import merge_team_odds

    tg_future = pd.DataFrame([
        {"code": 3, "gw": 2, "opp_code": 43, "season_idx": 1},
    ])
    one = {"team_code": 3, "gw": 2, "opp_code": 43, "odds_goals_against": 1.2}
    clean = merge_team_odds(tg_future, pd.DataFrame([one]))
    assert len(clean) == 1 and clean["odds_goals_against"].iloc[0] == 1.2

    with pytest.raises(MergeError):
        merge_team_odds(tg_future, pd.DataFrame([one, dict(one)]))


def test_run_advise_degrades_when_the_odds_frame_will_not_merge():
    """Odds are a best-effort extra everywhere else; a malformed feed must
    not take the week's advice down with it."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    merge = src.index("merge_team_odds(tg_future, odds_df)")
    tail = src[merge:merge + 400]
    assert "except Exception" in tail
    assert "odds unusable" in tail


def test_poisson_win_prob_is_a_probability_that_tracks_the_supremacy():
    from gaffer.data.odds import poisson_win_prob

    even = poisson_win_prob(1.4, 1.4)
    assert 0.3 < even < 0.45                  # draws take the rest
    assert poisson_win_prob(2.5, 0.7) > even
    assert poisson_win_prob(0.7, 2.5) < even
    assert 0.0 <= poisson_win_prob(0.0, 3.0) <= 1.0


# --- Shin devigging --------------------------------------------------------

def test_shin_devig_outputs_sum_to_one():
    from gaffer.data.odds import shin_devig

    for prices in ([1.30, 3.50], [2.4, 3.4, 2.9], [1.2, 7.0, 15.0]):
        assert abs(sum(shin_devig(prices)) - 1.0) < 1e-12


def test_shin_devig_preserves_the_order_of_the_prices():
    from gaffer.data.odds import shin_devig

    out = shin_devig([1.2, 7.0, 15.0])
    assert out[0] > out[1] > out[2]


def test_shin_devig_shrinks_the_longshot_more_than_proportional_devig():
    """The whole point of the change: the pad on a longshot is bigger than
    the pad on a favourite, so removing it proportionally leaves the
    favourite under-priced."""
    from gaffer.data.odds import devig, shin_devig

    prices = [1.30, 3.50]
    shin, prop = shin_devig(prices), devig(prices)
    assert shin[0] > prop[0]        # favourite gains
    assert shin[1] < prop[1]        # longshot shrinks


def test_shin_devig_pins_a_hand_checked_two_way_market():
    from gaffer.data.odds import shin_devig

    out = shin_devig([1.30, 3.50])
    assert round(out[0], 4) == 0.7418
    assert round(out[1], 4) == 0.2582


def test_shin_devig_on_equal_prices_is_uniform():
    from gaffer.data.odds import shin_devig

    assert shin_devig([2.0, 2.0]) == [0.5, 0.5]
    for p in shin_devig([3.0, 3.0, 3.0]):
        assert abs(p - 1 / 3) < 1e-12


def test_shin_devig_on_a_vig_free_book_is_the_implied_probabilities():
    """Booksum <= 1 has no pad to remove; inventing one would push
    probabilities the wrong way."""
    from gaffer.data.odds import shin_devig

    out = shin_devig([2.0, 4.0, 4.0])
    assert abs(out[0] - 0.5) < 1e-12


def test_shin_devig_does_not_diverge_on_an_extreme_favourite():
    from gaffer.data.odds import shin_devig

    out = shin_devig([1.01, 40.0])
    assert abs(sum(out) - 1.0) < 1e-12
    assert 0.0 < out[1] < 0.05


def test_shin_devig_on_a_single_outcome_returns_one():
    from gaffer.data.odds import shin_devig

    assert shin_devig([1.5]) == [1.0]


def test_odds_frame_devigs_the_match_triple_with_shin():
    """The 1X2 triple is where favourite-longshot bias bites; the totals
    pair keeps proportional devig on purpose."""
    import inspect

    from gaffer.data.odds import _p_over25, odds_frame

    src = inspect.getsource(odds_frame)
    assert "shin_devig(triple)" in src
    # "= devig(triple)", not "devig(triple)": the latter is a substring of
    # "shin_devig(triple)" and would never be absent.
    assert "= devig(triple)" not in src
    assert "devig(" in inspect.getsource(_p_over25)


def test_odds_frame_favourite_gets_the_shin_boost():
    """Same fixture, hand-computed: the home mu recovered from Shin-devigged
    probabilities is at least as big as the proportional one."""
    from gaffer.data.odds import devig, invert_odds, shin_devig

    triple = [2.4, 3.4, 2.9]
    ph_s, pd_s, pa_s = shin_devig(triple)
    ph_p, pd_p, pa_p = devig(triple)
    assert ph_s > ph_p
    mu_shin = invert_odds(ph_s, pd_s, pa_s, 0.5)
    mu_prop = invert_odds(ph_p, pd_p, pa_p, 0.5)
    assert mu_shin[0] >= mu_prop[0]


def test_predict_components_still_blends_before_merging_onto_players():
    """Re-pin after the weight argument landed: the protected ordering is
    what the fitted weight must not disturb."""
    import inspect

    from gaffer.advise import predict_components

    src = inspect.getsource(predict_components)
    assert src.index("blend_team_odds(") < src.index("comp.merge(tp")
    assert "odds_blend_weight()" in src


# --- anytime goalscorer props ---------------------------------------------

from gaffer.data.odds import (AGS_EG_CAP, AGS_MARKET, ags_frame,
                              next_gw_event_ids, normalize_ags)

_AGS_EVENT = {
    "id": "evt1", "home_team": "Arsenal", "away_team": "Manchester City",
    "commence_time": "2026-08-29T14:00:00Z",
    "bookmakers": [{"key": "bk1", "markets": [
        {"key": "player_goal_scorer_anytime", "outcomes": [
            {"name": "Bukayo Saka", "price": 3.0},
            {"name": "Kai Havertz", "price": 3.5},
            {"name": "Erling Haaland", "price": 1.8}]}]}]}


def test_get_player_goalscorer_odds_without_a_key_makes_no_request():
    def refuse(request):
        raise AssertionError("no key means no request")

    assert OddsClient("", client=_client(refuse)).get_player_goalscorer_odds(
        ["evt1"]) is None


def test_get_player_goalscorer_odds_requests_the_event_endpoint(tmp_path,
                                                                monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    seen = {}

    def handler(request):
        seen["url"] = str(request.url).split("?")[0]
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=_AGS_EVENT)

    out = OddsClient("k", client=_client(handler)).get_player_goalscorer_odds(
        ["evt1"])
    assert seen["url"] == (
        "https://api.the-odds-api.com/v4/sports/soccer_epl/events/evt1/odds")
    assert seen["params"]["markets"] == AGS_MARKET
    assert out == [_AGS_EVENT]


def test_get_player_goalscorer_odds_returns_none_on_an_exhausted_quota(
        tmp_path, monkeypatch):
    """401/402/429 on the free tier is the normal end of the month, not an
    error worth failing the weekly run over."""
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    client = OddsClient("k", client=_client(
        lambda r: httpx.Response(402)), retries=1)
    assert client.get_player_goalscorer_odds(["evt1"]) is None


def test_next_gw_event_ids_picks_only_the_coming_gameweek():
    """The 29 Aug kickoff sits inside GW2's deadline window in ``_EVENTS``;
    asking for any other gameweek must spend no requests."""
    assert next_gw_event_ids([_AGS_EVENT], _EVENTS, gw=2) == ["evt1"]
    assert next_gw_event_ids([_AGS_EVENT], _EVENTS, gw=1) == []
    assert next_gw_event_ids([], _EVENTS, gw=2) == []


def test_normalize_ags_scales_lambdas_to_the_match_odds_mu():
    """One-sided prices carry an overround that no devig can strip, so the
    market-consistent fix is to make the team's implied goals match the
    number the two-sided match odds already gave us."""
    lam = normalize_ags({"Bukayo Saka": 3.0, "Kai Havertz": 3.5}, mu=1.6)
    assert abs(sum(lam.values()) - 1.6) < 1e-12
    # Ordering survives the scaling: the shorter price stays the bigger lambda.
    assert lam["Bukayo Saka"] > lam["Kai Havertz"]


def test_normalize_ags_on_an_empty_book_is_empty():
    assert normalize_ags({}, mu=1.6) == {}


def test_normalize_ags_with_a_zero_mu_is_all_zero():
    lam = normalize_ags({"A": 3.0}, mu=0.0)
    assert lam == {"A": 0.0}


def test_ags_frame_maps_names_and_teams_onto_codes():
    players = pd.DataFrame([
        {"code": 11, "name": "Bukayo Saka", "team_code": 3},
        {"code": 12, "name": "Kai Havertz", "team_code": 3},
        {"code": 13, "name": "Erling Haaland", "team_code": 43}])
    odds_df = odds_frame(SAMPLE_ODDS, _TEAMS, _EVENTS)
    out = ags_frame([_AGS_EVENT], players, _TEAMS, _EVENTS, odds_df)
    assert set(out.columns) == {"code", "gw", "team_code", "opp_code",
                                "lambda_ags"}
    assert set(out["code"]) == {11, 12, 13}
    # Arsenal's two priced players carry Arsenal's devigged mu between them.
    arsenal = out[out["team_code"] == 3]
    mu = float(odds_df[(odds_df["team_code"] == 3)]["odds_e_goals_for"].iloc[0])
    assert abs(arsenal["lambda_ags"].sum() - mu) < 1e-9


def test_ags_frame_drops_players_the_bootstrap_does_not_carry():
    players = pd.DataFrame([{"code": 11, "name": "Bukayo Saka",
                             "team_code": 3}])
    out = ags_frame([_AGS_EVENT], players, _TEAMS,
                    _EVENTS, odds_frame(SAMPLE_ODDS, _TEAMS, _EVENTS))
    assert set(out["code"]) == {11}


def test_ags_frame_without_match_odds_for_the_fixture_is_empty():
    """No devigged mu means no normalization target, and an un-normalized
    one-sided price is an overround, not a probability."""
    players = pd.DataFrame([{"code": 11, "name": "Bukayo Saka",
                             "team_code": 3}])
    out = ags_frame([_AGS_EVENT], players, _TEAMS, _EVENTS,
                    pd.DataFrame(columns=ODDS_FRAME_COLS))
    assert out.empty


def test_ags_frame_on_none_is_empty():
    players = pd.DataFrame([{"code": 11, "name": "Bukayo Saka",
                             "team_code": 3}])
    assert ags_frame(None, players, _TEAMS, _EVENTS,
                     odds_frame(SAMPLE_ODDS, _TEAMS, _EVENTS)).empty


def test_ags_cap_is_a_sane_per_appearance_ceiling():
    assert AGS_EG_CAP == 2.0


from gaffer.data.odds import AGS_BLEND_WEIGHT_DEFAULT, blend_attacking_odds


def _comp() -> pd.DataFrame:
    return pd.DataFrame({
        "code": [11, 12], "gw": [1, 1], "opp_code": [43, 43],
        "p_play": [0.9, 0.5], "e_goals": [0.20, 0.10],
        "e_assists": [0.15, 0.05]})


def _ags() -> pd.DataFrame:
    return pd.DataFrame({"code": [11], "gw": [1], "team_code": [3],
                         "opp_code": [43], "lambda_ags": [0.45]})


def test_blend_attacking_odds_mixes_the_two_expectations():
    out = blend_attacking_odds(_comp(), _ags(), weight=0.5)
    # e_goals_odds = lambda / p_play = 0.45 / 0.9 = 0.5
    assert abs(out.loc[0, "e_goals_odds"] - 0.5) < 1e-12
    assert abs(out.loc[0, "e_goals"] - (0.5 * 0.5 + 0.5 * 0.20)) < 1e-12


def test_blend_attacking_odds_leaves_unpriced_players_alone():
    out = blend_attacking_odds(_comp(), _ags(), weight=0.5)
    assert out.loc[1, "e_goals"] == 0.10
    assert pd.isna(out.loc[1, "e_goals_odds"])


def test_blend_attacking_odds_caps_the_per_appearance_rate():
    """A fringe player with a long price and a tiny p_play would otherwise
    imply an absurd per-appearance rate."""
    comp = _comp()
    comp.loc[0, "p_play"] = 0.05
    out = blend_attacking_odds(comp, _ags(), weight=1.0)
    assert out.loc[0, "e_goals"] == AGS_EG_CAP


def test_blend_attacking_odds_ignores_a_zero_p_play():
    comp = _comp()
    comp.loc[0, "p_play"] = 0.0
    out = blend_attacking_odds(comp, _ags(), weight=1.0)
    assert out.loc[0, "e_goals"] == 0.20


def test_blend_attacking_odds_does_not_add_or_reorder_rows():
    """Components are stitched positionally everywhere downstream."""
    out = blend_attacking_odds(_comp(), _ags(), weight=0.5)
    assert list(out["code"]) == [11, 12]
    assert len(out) == 2


def test_blend_attacking_odds_leaves_assists_untouched():
    """The free tier drops assist props, so there is nothing to blend there
    and pretending otherwise would double-count the goals signal."""
    out = blend_attacking_odds(_comp(), _ags(), weight=1.0)
    assert list(out["e_assists"]) == [0.15, 0.05]


def test_default_ags_weight_is_a_half():
    """No historical AGS record exists to fit on — a known limitation, an
    even split until a season of snapshots accumulates."""
    assert AGS_BLEND_WEIGHT_DEFAULT == 0.5


def test_run_advise_blends_player_props_before_assembling_ep():
    """Source-level seam (no cheap end-to-end harness for run_advise): the
    AGS blend has to land on the component frame before assemble_ep reads
    it, and the protected calibration literal must survive intact."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    comp = src.index("comp = predict_components(")
    blend = src.index("blend_attacking_odds(")
    assemble = src.index("ep_matrix(apply_calibration(assemble_ep(")
    assert comp < blend < assemble
    assert "cfg.player_props" in src
    assert "except Exception" in src[blend - 600:blend + 600]


def test_run_advise_still_orders_the_league_tilt_seam():
    """The other two protected orderings must not have moved."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    assert (src.index("fetch_rival_entries(") < src.index("tilt_ep(")
            < src.index("pool = build_pool("))
    assert "build_pool(players, pool_ep," in src
