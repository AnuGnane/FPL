import numpy as np
import pandas as pd

from gaffer.models.attacking import AttackingModel
from gaffer.models.minutes import ENSEMBLE_KW, LGB_KW, ThreeModeModel


def _frame(n_codes=40, n_gws=25, seed=5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for code in range(n_codes):
        for gw in range(1, n_gws + 1):
            minutes = 90 if code < 20 else int(rng.choice([0, 0, 20, 90]))
            rows.append({
                "code": code, "season_idx": 0, "gw": gw, "minutes": minutes,
                "starts": int(minutes >= 60), "position": "MID",
                "goals": int(rng.random() < 0.15),
                "assists": int(rng.random() < 0.12),
                "minutes_r5": float(minutes), "starts_r5": float(minutes >= 60),
                "home": 1.0, "xg_r5": rng.random(), "xa_r5": rng.random()})
    return pd.DataFrame(rows)


_MIN_COLS = ["minutes_r5", "starts_r5", "home"]
_ATK_COLS = ["xg_r5", "xa_r5", "minutes_r5"]


def test_no_seed_is_the_shipped_random_state():
    model = ThreeModeModel(_MIN_COLS)
    assert model.lgb_kw == LGB_KW
    assert model.lgb_kw["random_state"] == 7


def test_a_seed_moves_the_random_state_and_turns_on_bagging():
    """A seed on its own is inert: LGB_KW samples neither rows nor columns, so
    two random_states fit the identical model. ENSEMBLE_KW is what makes the
    seed bite, and it is the only other thing a seed changes."""
    model = ThreeModeModel(_MIN_COLS, seed=17)
    assert model.lgb_kw["random_state"] == 17
    assert {k: model.lgb_kw[k] for k in ENSEMBLE_KW} == ENSEMBLE_KW
    rest = {k: v for k, v in model.lgb_kw.items()
            if k != "random_state" and k not in ENSEMBLE_KW}
    assert rest == {k: v for k, v in LGB_KW.items() if k != "random_state"}


def test_a_seedless_head_carries_no_ensemble_knobs_at_all():
    model = ThreeModeModel(_MIN_COLS)
    assert not set(ENSEMBLE_KW) & set(model.lgb_kw)


def test_no_seed_predicts_exactly_what_the_shipped_model_predicts():
    df = _frame()
    a = ThreeModeModel(_MIN_COLS).fit(df).predict_modes(df)
    b = ThreeModeModel(_MIN_COLS, seed=None).fit(df).predict_modes(df)
    pd.testing.assert_frame_equal(a, b)


def test_two_seeds_disagree_at_least_somewhere():
    df = _frame()
    a = ThreeModeModel(_MIN_COLS, seed=7).fit(df).predict_modes(df)
    b = ThreeModeModel(_MIN_COLS, seed=47).fit(df).predict_modes(df)
    assert not np.allclose(a["p_dnp"].to_numpy(), b["p_dnp"].to_numpy())


def test_the_attacking_head_takes_the_same_seam():
    df = _frame()
    plain = AttackingModel(_ATK_COLS).fit(df).predict(df)
    same = AttackingModel(_ATK_COLS, seed=None).fit(df).predict(df)
    pd.testing.assert_frame_equal(plain, same)
    other = AttackingModel(_ATK_COLS, seed=47).fit(df).predict(df)
    assert not np.allclose(plain["e_goals"].to_numpy(),
                           other["e_goals"].to_numpy())


from gaffer.calibrate_noise import (EP_EDGES, MIN_CELL_OBS, XMINS_EDGES,
                                    fit_estimation_sigmas)
from gaffer.optimize.scenarios import sigma_for


def _rows(n_per_cell=120, sigma=0.4) -> pd.DataFrame:
    """Two populated cells: low EP / low xmins, and high EP / nailed."""
    rows = []
    # ep 7.0 lands in EP bin 4 (edges [0,2,3,4,6]); 5.0 would land in bin 3.
    for ep, xmins, s in ((1.0, 10.0, sigma), (7.0, 85.0, sigma * 3)):
        for _ in range(n_per_cell):
            rows.append({"ep": ep, "xmins": xmins, "sigma_est": s})
    return pd.DataFrame(rows)


def test_a_cell_takes_the_mean_ensemble_spread_not_its_spread():
    out = fit_estimation_sigmas(_rows())
    assert out["sigma"]["0_0"] == 0.4
    assert out["sigma"]["4_3"] == 1.2000


def test_the_payload_carries_the_edges_and_the_v6_cell_threshold():
    out = fit_estimation_sigmas(_rows())
    assert out["ep_edges"] == EP_EDGES
    assert out["xmins_edges"] == XMINS_EDGES
    assert out["min_cell_obs"] == MIN_CELL_OBS


def test_a_thin_cell_is_left_out_so_serving_pools_it_up():
    out = fit_estimation_sigmas(_rows(n_per_cell=MIN_CELL_OBS - 1))
    assert out["sigma"] == {}
    assert out["obs"]["0_0"] == MIN_CELL_OBS - 1
    assert out["ep_marginal"]["0"] == 0.4


def test_a_cell_whose_ensemble_agrees_exactly_is_dropped_not_floored():
    """write_noise refuses a non-positive sigma and inventing one would be a
    lie about a cell where the five refits genuinely agree."""
    rows = _rows()
    rows.loc[rows["ep"] == 1.0, "sigma_est"] = 0.0
    out = fit_estimation_sigmas(rows)
    assert "0_0" not in out["sigma"]
    assert "0" not in out["ep_marginal"]
    # The cell and its EP marginal are both zero, and both are dropped.
    assert out["dropped_zero_cells"] == 2


def test_the_global_is_the_pooled_mean_spread():
    out = fit_estimation_sigmas(_rows())
    assert out["global"] == 0.8


def test_the_table_is_readable_by_the_untouched_serving_lookup():
    """Zero new serving code: sigma_for has to read this exactly as it reads
    the v6 residual table."""
    out = fit_estimation_sigmas(_rows())
    assert sigma_for(out, 1.0, 10.0) == 0.4
    assert sigma_for(out, 7.0, 85.0) == 1.2
    # EP bin 2 x xMins bin 1 is unpopulated and bin 2 has no marginal either,
    # so the lookup falls all the way through to the global.
    assert sigma_for(out, 3.5, 45.0) == out["global"]


def test_rows_with_no_xmins_are_dropped_rather_than_binned_at_zero():
    rows = _rows()
    rows.loc[rows.index[:10], "xmins"] = np.nan
    out = fit_estimation_sigmas(rows)
    assert out["rows"] == len(rows) - 10
