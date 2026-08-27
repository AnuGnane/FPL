"""The v6 penalty-taker term (spec §1).

Pure arithmetic over three inputs — the bootstrap taker order, the player's
trailing share of his club's penalties, and the club's attack strength — with
a hard clamp round the outside because no backtest can validate it.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.set_pieces import (ATTACK_MULT_CLAMP, EP_CLAMP, GOAL_POINTS,
                               LEAGUE_PENS_PG_FALLBACK, PEN_CONVERSION,
                               PEN_XG, PenPriors, add_pen_ep,
                               attack_multipliers, pen_estimate, pen_notices,
                               pen_priors, pen_table, set_piece_ep, share_now)


def _players(order_1=1, order_2=2) -> pd.DataFrame:
    return pd.DataFrame([
        {"code": 1, "name": "First Choice", "position": "MID",
         "team_code": 3, "penalties_order": order_1},
        {"code": 2, "name": "Backup", "position": "FWD",
         "team_code": 3, "penalties_order": order_2},
        {"code": 3, "name": "Nobody", "position": "DEF",
         "team_code": 8, "penalties_order": None},
    ])


def _comp() -> pd.DataFrame:
    return pd.DataFrame([
        {"code": 1, "gw": 5, "position": "MID", "team_code": 3,
         "p_play": 1.0, "e_goals": 0.5},
        {"code": 2, "gw": 5, "position": "FWD", "team_code": 3,
         "p_play": 0.8, "e_goals": 0.3},
        {"code": 3, "gw": 5, "position": "DEF", "team_code": 8,
         "p_play": 1.0, "e_goals": 0.1},
    ])


def _priors(**shares) -> PenPriors:
    return PenPriors(share_hist={int(k): float(v) for k, v in shares.items()},
                     league_pens_pg=0.13, team_games=760)


# --- share_now --------------------------------------------------------------

def test_share_now_reads_the_bootstrap_queue_position():
    """Order 1 takes them all; order 2 is a hedge against rotation and
    absence, not a claim that he takes 15% of them; below that, nothing."""
    out = share_now(pd.Series([1, 2, 3, None, 0]))
    assert out.tolist() == [1.0, 0.15, 0.0, 0.0, 0.0]


# --- the historical share ---------------------------------------------------

def test_pen_estimate_reads_the_gap_between_fpl_xg_and_understat_npxg():
    """FPL's expected_goals includes penalties; Understat's npxG excludes
    them. The gap is a penalty, priced at PEN_XG."""
    frame = pd.DataFrame({"xg": [1.0, 0.4, 0.2],
                          "us_npxg": [0.21, 0.4, 0.5]})
    out = pen_estimate(frame)
    assert out.iloc[0] == pytest.approx(0.79 / PEN_XG)
    assert out.iloc[1] == 0.0
    # A negative gap is two xG models disagreeing, not a negative penalty.
    assert out.iloc[2] == 0.0


def test_pen_estimate_is_none_without_both_columns():
    assert pen_estimate(pd.DataFrame({"xg": [1.0]})) is None
    assert pen_estimate(pd.DataFrame({"us_npxg": [1.0]})) is None


def _hist() -> pd.DataFrame:
    """Two clubs, three seasons. Player 1 took every one of club 3's
    penalties; player 2 took none; club 8 had one, from player 3."""
    rows = []
    for season in (0, 1, 2):
        for gw in range(1, 11):
            rows += [
                {"season_idx": season, "gw": gw, "code": 1, "team_code": 3,
                 "opp_code": 8, "xg": 0.5 + (PEN_XG if gw == 1 else 0.0),
                 "us_npxg": 0.5},
                {"season_idx": season, "gw": gw, "code": 2, "team_code": 3,
                 "opp_code": 8, "xg": 0.3, "us_npxg": 0.3},
                {"season_idx": season, "gw": gw, "code": 3, "team_code": 8,
                 "opp_code": 3, "xg": 0.2 + (PEN_XG if gw == 2 else 0.0),
                 "us_npxg": 0.2},
            ]
    return pd.DataFrame(rows)


def test_pen_priors_gives_the_sole_taker_the_whole_share():
    priors = pen_priors(_hist())
    assert priors is not None
    assert priors.share_hist[1] == pytest.approx(1.0)
    assert priors.share_hist.get(2, 0.0) == pytest.approx(0.0)
    assert priors.share_hist[3] == pytest.approx(1.0)


def test_pen_priors_falls_back_when_the_league_rate_is_implausible():
    """Three penalties per team-game is a broken estimator, not a wild
    season. The rate is bounded, and the shares are still usable."""
    hist = _hist()
    hist["xg"] = hist["xg"] + 3.0 * PEN_XG
    priors = pen_priors(hist)
    assert priors.league_pens_pg == LEAGUE_PENS_PG_FALLBACK


def test_pen_priors_returns_none_without_the_xg_columns():
    """The rail spec §1 names: no Understat frame -> share_hist = 0 for
    everybody, expressed as no priors at all."""
    hist = _hist().drop(columns=["us_npxg"])
    assert pen_priors(hist) is None
    assert pen_priors(pd.DataFrame()) is None
    assert pen_priors(None) is None


# --- attack multipliers -----------------------------------------------------

class _DC:
    def __init__(self, attack):
        self.attack_ = attack


def test_attack_multipliers_are_a_ratio_to_the_league_mean():
    mult = attack_multipliers(_DC({3: 0.2, 8: 0.0, 14: -0.2}))
    assert mult[3] > 1.0 > mult[14]
    assert mult[8] == pytest.approx(1.0, abs=0.02)


def test_attack_multipliers_are_clamped_both_ways():
    mult = attack_multipliers(_DC({3: 5.0, 8: -5.0}))
    assert mult[3] == ATTACK_MULT_CLAMP[1]
    assert mult[8] == ATTACK_MULT_CLAMP[0]


def test_a_team_model_without_attack_strengths_is_a_flat_multiplier():
    assert attack_multipliers(object()) == {}
    assert attack_multipliers(None) == {}


# --- the term itself --------------------------------------------------------

def test_the_term_prices_the_increment_over_history_not_the_penalty():
    """A first-choice taker whose history already says he takes them all is
    worth nothing extra — that is the whole double-count argument."""
    term = set_piece_ep(_comp(), _players(), _priors(**{"1": 1.0}), {})
    assert term.iloc[0] == pytest.approx(0.0)


def test_a_brand_new_taker_is_where_the_term_is_biggest():
    """Zero history, order 1: the model is blind exactly here."""
    term = set_piece_ep(_comp(), _players(), _priors(), {})
    expected = 1.0 * 0.13 * 1.0 * PEN_CONVERSION * GOAL_POINTS["MID"] * 1.0
    assert term.iloc[0] == pytest.approx(expected)


def test_a_demoted_taker_gets_a_negative_term():
    """History says he took them; the bootstrap says he no longer does."""
    players = _players(order_1=None)
    term = set_piece_ep(_comp(), players, _priors(**{"1": 1.0}), {})
    assert term.iloc[0] < 0.0


def test_the_term_scales_with_p_play_and_the_attack_multiplier():
    term = set_piece_ep(_comp(), _players(), _priors(), {3: 1.5})
    expected = (0.15 * 0.13 * 1.5 * PEN_CONVERSION
                * GOAL_POINTS["FWD"] * 0.8)
    assert term.iloc[1] == pytest.approx(expected)


def test_the_term_is_clamped_both_ways():
    """No backtest can validate this term, so the clamp is the safety."""
    priors = PenPriors(share_hist={}, league_pens_pg=0.35, team_games=760)
    comp = _comp()
    comp.loc[0, "position"] = "GKP"          # 10 points a goal
    term = set_piece_ep(comp, _players(), priors, {3: ATTACK_MULT_CLAMP[1]})
    assert term.iloc[0] == EP_CLAMP[1]
    demoted = set_piece_ep(comp, _players(order_1=None),
                           PenPriors(share_hist={1: 1.0},
                                     league_pens_pg=0.35, team_games=760),
                           {3: ATTACK_MULT_CLAMP[1]})
    assert demoted.iloc[0] == EP_CLAMP[0]


def test_players_with_no_order_at_all_get_exactly_zero():
    term = set_piece_ep(_comp(), _players(), _priors(), {})
    assert term.iloc[2] == 0.0


# --- folding into the components frame --------------------------------------

def test_add_pen_ep_moves_e_goals_by_exactly_the_clamped_points():
    """assemble_ep prices goals as p_play * e_goals * goal_points, so the
    goals increment has to be the clamped EP divided back through both."""
    out = add_pen_ep(_comp(), _players(), _priors(), {})
    row = out.iloc[0]
    delta_goals = row["e_goals"] - _comp().iloc[0]["e_goals"]
    assert (delta_goals * GOAL_POINTS["MID"] * row["p_play"]
            == pytest.approx(row["ep_pen_taker"]))


def test_no_priors_leaves_the_frame_untouched_column_for_column():
    """The rail: no penalty history -> the components are what they were."""
    comp = _comp()
    out = add_pen_ep(comp, _players(), None, {})
    assert (out["ep_pen_taker"] == 0.0).all()
    pd.testing.assert_frame_equal(out.drop(columns=["ep_pen_taker"]), comp)


def test_all_none_taker_orders_leave_the_frame_untouched_column_for_column():
    """The other half of the same rail: the bootstrap stopped publishing
    orders, or every value is null."""
    comp = _comp()
    players = _players(order_1=None, order_2=None)
    out = add_pen_ep(comp, players, _priors(), {})
    assert (out["ep_pen_taker"] == 0.0).all()
    pd.testing.assert_frame_equal(out.drop(columns=["ep_pen_taker"]), comp)


def test_a_players_frame_without_the_order_column_is_the_same_rail():
    comp = _comp()
    players = _players().drop(columns=["penalties_order"])
    out = add_pen_ep(comp, players, _priors(), {})
    pd.testing.assert_frame_equal(out.drop(columns=["ep_pen_taker"]), comp)


# --- the audit log (gate P1) ------------------------------------------------

def test_pen_notices_name_every_term_worth_reading():
    notices = pen_notices(_comp(), _players(), _priors(), {})
    assert any("First Choice" in line for line in notices)
    assert all("Nobody" not in line for line in notices)
    joined = "\n".join(notices)
    assert "share now" in joined and "history" in joined


def test_pen_notices_are_silent_when_nothing_moved():
    assert pen_notices(_comp(), _players(), None, {}) == []


def test_the_goal_points_table_matches_the_shipped_scoring_table():
    """GOAL_POINTS is a module constant so predict_components does not have
    to thread the scoring table down. It has to agree with the real one."""
    from gaffer.assets import load_bootstrap_sample
    from gaffer.data.bootstrap import scoring_table

    real = scoring_table(load_bootstrap_sample())["goals_scored"]
    assert {k: float(v) for k, v in real.items()} == GOAL_POINTS
