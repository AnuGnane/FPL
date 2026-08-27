"""The v6 degradation rails.

Three things are pinned here; Task 3 adds the noise rail and Task 14 restates
the lot:

1. No penalty history, or no taker orders, leaves the component frame exactly
   as it was — column for column, not merely in the numbers EP happens to
   read.
2. The penalty term never escapes its clamp, whatever the inputs.
3. The protected source-text orderings in ``run_advise`` and
   ``predict_components`` still hold after everything v6 inserted.

If a later task legitimately changes one of these, that task's gate says so
and the pin here is updated deliberately — never quietly.
"""

from __future__ import annotations

import pandas as pd

from gaffer.set_pieces import (EP_CLAMP, PenPriors, add_pen_ep,
                               attack_multipliers)


def _comp() -> pd.DataFrame:
    return pd.DataFrame([
        {"code": 1, "gw": 5, "position": "MID", "team_code": 3,
         "p_play": 0.95, "p60": 0.9, "e_goals": 0.42, "e_assists": 0.3},
        {"code": 2, "gw": 5, "position": "GKP", "team_code": 8,
         "p_play": 1.0, "p60": 1.0, "e_goals": 0.01, "e_assists": 0.01},
    ])


def _players(order=None) -> pd.DataFrame:
    return pd.DataFrame([
        {"code": 1, "name": "A", "position": "MID", "team_code": 3,
         "penalties_order": order},
        {"code": 2, "name": "B", "position": "GKP", "team_code": 8,
         "penalties_order": None},
    ])


# --- rail 1: no taker data == today's components ---------------------------

def test_no_priors_is_byte_identical_components():
    comp = _comp()
    out = add_pen_ep(comp, _players(order=1), None, {})
    pd.testing.assert_frame_equal(out.drop(columns=["ep_pen_taker"]), comp)
    assert (out["ep_pen_taker"] == 0.0).all()


def test_no_taker_orders_is_byte_identical_components():
    comp = _comp()
    priors = PenPriors(share_hist={1: 0.0}, league_pens_pg=0.13,
                       team_games=760)
    out = add_pen_ep(comp, _players(order=None), priors, {})
    pd.testing.assert_frame_equal(out.drop(columns=["ep_pen_taker"]), comp)
    assert (out["ep_pen_taker"] == 0.0).all()


def test_a_team_model_with_no_attack_strengths_still_prices_the_term():
    """The multiplier degrades to flat, not to zero: a missing Dixon-Coles
    fit is no reason to unlearn who takes the penalties."""
    priors = PenPriors(share_hist={}, league_pens_pg=0.13, team_games=760)
    out = add_pen_ep(_comp(), _players(order=1), priors,
                     attack_multipliers(object()))
    assert out["ep_pen_taker"].iloc[0] > 0.0


# --- rail 2: the clamp holds ------------------------------------------------

def test_the_clamp_holds_against_absurd_inputs():
    priors = PenPriors(share_hist={1: 0.0}, league_pens_pg=99.0,
                       team_games=1)
    out = add_pen_ep(_comp(), _players(order=1), priors, {3: 99.0})
    assert out["ep_pen_taker"].max() <= EP_CLAMP[1]
    assert out["ep_pen_taker"].min() >= EP_CLAMP[0]


# --- rail 3: the protected orderings, restated -----------------------------

def test_run_advise_still_orders_every_protected_seam():
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    league = src.index("fetch_rival_entries(")
    tilt = src.index("tilt_ep(")
    pool = src.index("pool = build_pool(")
    assert league < tilt < pool
    assert src.index("compute_strategy(") < pool
    assert "build_pool(players, pool_ep," in src

    comp = src.index("comp = predict_components(")
    blend = src.index("blend_attacking_odds(")
    assemble = src.index("ep_matrix(apply_calibration(assemble_ep(")
    assert comp < blend < assemble
    assert "except Exception" in src[blend - 600:blend + 600]

    assert 'ep_gw1 = ep_named[ep_named["gw"] == gw]' in src
    assert "pool_ep" not in src[src.index("ep_gw1 ="):]

    assert src.index("avail = news_availability(") < comp
    assert comp < src.index("write_shadow(comp, gw)") < blend
    assert src.index("pens = pen_priors(hist)") < comp


def test_predict_components_still_blends_before_merging_onto_players():
    import inspect

    from gaffer.advise import predict_components

    src = inspect.getsource(predict_components)
    assert src.index("blend_team_odds(") < src.index("comp.merge(tp")
    assert 'tp["p_cs_model"] = tp["p_cs"].values' in src
    assert 'tp["e_gc_model"] = tp["e_gc"].values' in src
    assert "odds_blend_weight()" in src
    for col in ["was_home", "kickoff_time", "pen_taker", "setpiece_taker"]:
        assert f'"{col}"' in src
