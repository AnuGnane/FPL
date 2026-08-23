import pandas as pd
from gaffer.optimize.differentials import (captain_table, transfer_alternatives,
                                           threat_board)

EP = pd.DataFrame({
    "code": [1, 2, 3, 4], "name": ["Salah", "Haaland", "Punt", "Gordon"],
    "position": ["MID", "FWD", "MID", "MID"],
    "ep": [8.0, 7.8, 7.6, 5.0], "p_haul": [0.4, 0.45, 0.5, 0.2],
})
EO = {1: 90.0, 2: 80.0, 3: 5.0, 4: 60.0}


def test_captain_table_flags_differential():
    t = captain_table(EP, xi_codes=[1, 2, 3], league_eo=EO, top=3)
    assert t.iloc[0]["code"] == 1                      # highest EP first
    assert t[t.code == 3]["differential"].iloc[0]      # low EO + high ceiling
    assert not t[t.code == 1]["differential"].iloc[0]


def test_transfer_alternatives_within_margin_low_eo():
    alts = transfer_alternatives(EP, buy_code=1, league_eo=EO, margin=0.5)
    assert alts["code"].tolist() == [3]     # within 0.5 EP, EO<20, same position


def test_threat_board_lists_unowned_high_eo():
    t = threat_board(EP, my_codes=[1], league_eo=EO, min_eo=50.0)
    assert t["code"].tolist() == [2, 4]     # sorted by EP desc


def test_transfer_alternatives_unknown_buy_code_is_empty():
    alts = transfer_alternatives(EP, buy_code=999, league_eo=EO)
    assert alts.empty
    assert alts.columns.tolist() == ["code", "name", "ep", "p_haul",
                                     "league_eo"]


def test_no_league_configured_degrades_gracefully():
    t = captain_table(EP, xi_codes=[1, 2, 3], league_eo={}, top=3)
    assert t["code"].tolist() == [1, 2, 3]          # still ranks by EP
    assert (t["league_eo"] == 0.0).all()
    assert threat_board(EP, my_codes=[1], league_eo={}).empty
