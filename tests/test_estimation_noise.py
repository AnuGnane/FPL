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
