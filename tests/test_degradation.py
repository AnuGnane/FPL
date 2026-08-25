"""Every v4b source has to be optional.

A fresh clone has no football-data CSV, no Understat parquet and no odds
API key, and it must behave exactly as the tool did before this cycle — the
same columns, the same fallbacks, the same numbers. These are the tests that
say so, gathered in one file so the rail is visible as a rail rather than
scattered across six suites.
"""

import numpy as np
import pandas as pd
import pytest

from gaffer.features.engineer import (TEAM_US_FEATURES, add_shrunken_rates,
                                      add_understat_rolling,
                                      merge_understat_team,
                                      understat_feature_columns)


def _plain_history(n_players=6, n_gws=12):
    """History with no Understat columns whatsoever."""
    rows = []
    for gw in range(1, n_gws + 1):
        for i in range(n_players):
            rows.append({
                "code": 100 + i, "season_idx": 0, "gw": gw,
                "position": ["GKP", "DEF", "MID", "FWD"][i % 4],
                "team_code": 1 + i % 2, "opp_code": 2 - i % 2,
                "was_home": i % 2 == 0, "minutes": 90,
                "kickoff_time": f"2024-08-{10 + gw:02d}T14:00:00Z",
                "goals": i % 3 == 0, "assists": 0, "starts": 1,
                "total_points": 2, "bps": 20, "bonus": 0})
    return pd.DataFrame(rows)


def test_understat_rolling_without_data_produces_only_nan_columns():
    out = add_understat_rolling(_plain_history())
    for col in understat_feature_columns():
        assert col in out.columns and out[col].isna().all()


def test_team_understat_without_data_produces_only_nan_columns():
    out = merge_understat_team(_plain_history(), None)
    for col in TEAM_US_FEATURES:
        assert col in out.columns and out[col].isna().all()


def test_shrunken_rates_survive_a_frame_with_no_goals_column():
    out = add_shrunken_rates(_plain_history().drop(columns=["goals"]))
    assert out["shrunk_goals90"].isna().all()
    assert "shrunk_assists90" in out.columns


def test_blend_weight_without_match_odds_is_the_module_constant():
    from gaffer.models.dixon_coles import walk_forward_cs
    from gaffer.models.team import ODDS_BLEND_WEIGHT, fit_blend_weight

    empty = pd.DataFrame(columns=["season_idx", "gw", "home_code",
                                  "away_code", "p_home", "p_draw", "p_away",
                                  "p_over25"])
    tg = pd.DataFrame([{"code": 1, "opp_code": 2, "home": 1.0,
                        "season_idx": 0, "gw": 1, "cs": 1, "gf": 1, "ga": 0,
                        "kickoff_time": "2024-08-11T14:00:00Z"}])
    assert fit_blend_weight(walk_forward_cs(tg, empty)) == ODDS_BLEND_WEIGHT


def test_blend_team_odds_without_an_odds_column_is_the_identity():
    from gaffer.models.team import blend_team_odds

    preds = pd.DataFrame({"code": [1], "season_idx": [0], "gw": [1],
                          "p_cs": [0.25], "e_gc": [1.4]})
    out = blend_team_odds(preds)
    assert out.equals(preds)


@pytest.mark.xfail(reason="AGS layer lands in Tasks 22-23", strict=False)
def test_odds_client_without_a_key_makes_no_request_for_player_props():
    from gaffer.data.odds import OddsClient

    def refuse(request):
        raise AssertionError("no key means no request")

    import httpx

    client = OddsClient("", client=httpx.Client(
        transport=httpx.MockTransport(refuse)))
    assert client.get_player_goalscorer_odds(["abc"]) is None


@pytest.mark.xfail(reason="AGS layer lands in Tasks 22-23", strict=False)
def test_blend_attacking_odds_with_no_odds_is_byte_identical():
    """Gate G3's no-key half: the AGS layer must be provably invisible when
    the market is not there."""
    from gaffer.data.odds import blend_attacking_odds

    comp = pd.DataFrame({"code": [1, 2], "gw": [1, 1], "opp_code": [9, 9],
                         "p_play": [0.9, 0.8], "e_goals": [0.4, 0.1],
                         "e_assists": [0.2, 0.1]})
    for absent in (None, pd.DataFrame()):
        out = blend_attacking_odds(comp, absent, weight=0.5)
        pd.testing.assert_frame_equal(out, comp)


def test_understat_client_with_a_dead_site_returns_empty_frames(tmp_path):
    import httpx

    from gaffer.data.understat import UnderstatClient

    client = UnderstatClient(
        client=httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(500))),
        cache_dir=tmp_path, sleep=0.0, retries=1)
    assert client.league_matches("2024-25").empty
    assert client.team_history("2024-25", 0).empty


def test_dixon_coles_predicts_every_row_of_an_all_promoted_fixture_list():
    """Worst case for the fallback: nobody in the fixture list was fitted."""
    from gaffer.models.dixon_coles import DixonColesModel
    from gaffer.models.team import build_team_gw

    rng = np.random.default_rng(0)
    fx = pd.DataFrame([
        {"season_idx": 0, "gw": 1 + i // 5,
         # The plan's literal f"2024-08-{10 + i:02d}" runs past the end of
         # August at i=22; a real date offset keeps the ordering it wanted.
         "kickoff_time": (pd.Timestamp("2024-08-10T14:00:00Z")
                          + pd.Timedelta(days=i)).isoformat(),
         "home_code": 1 + i % 4, "away_code": 1 + (i + 1) % 4,
         "home_goals": int(rng.poisson(1.4)),
         "away_goals": int(rng.poisson(1.1))}
        for i in range(40)])
    model = DixonColesModel().fit(build_team_gw(fx))
    future = pd.DataFrame([{"code": 900, "opp_code": 901, "home": 1.0,
                            "season_idx": 1, "gw": 1}])
    out = model.predict(future)
    assert out["p_cs"].notna().all() and out["e_gc"].notna().all()
