import numpy as np
import pandas as pd
import pytest

from gaffer.models.team import (ODDS_BLEND_WEIGHT, TEAM_FEATURES, TeamModel,
                                add_team_rolling, blend_team_odds,
                                build_team_gw)


def test_build_team_gw_two_rows_per_fixture():
    fixtures = pd.DataFrame([
        {"season_idx": 0, "gw": 1, "kickoff_time": "2022-08-06T14:00:00Z",
         "home_code": 1, "away_code": 2, "home_goals": 2, "away_goals": 0},
    ])
    tg = build_team_gw(fixtures)
    assert len(tg) == 2
    home = tg[tg.code == 1].iloc[0]
    away = tg[tg.code == 2].iloc[0]
    assert home["gf"] == 2 and home["ga"] == 0 and home["cs"] == 1
    assert away["gf"] == 0 and away["ga"] == 2 and away["cs"] == 0
    assert home["home"] == 1.0 and away["home"] == 0.0


def test_team_model_strong_team_higher_cs_prob():
    rng = np.random.default_rng(1)
    rows = []
    for gw in range(1, 60):
        strong_cs = int(rng.random() < 0.6)
        weak_cs = int(rng.random() < 0.1)
        rows.append({"code": 1, "season_idx": 0, "gw": gw, "home": 1.0,
                     "cs": strong_cs, "ga": 0 if strong_cs else 1,
                     "gf": 2, "elo_diff": 200.0})
        rows.append({"code": 2, "season_idx": 0, "gw": gw, "home": 0.0,
                     "cs": weak_cs, "ga": 0 if weak_cs else 2,
                     "gf": 0, "elo_diff": -200.0})
    df = pd.DataFrame(rows)
    m = TeamModel(feature_cols=["elo_diff", "home"])
    m.fit(df[df.gw <= 45])
    pred = m.predict(df[df.gw > 45])
    assert pred[pred.code == 1]["p_cs"].mean() > pred[pred.code == 2]["p_cs"].mean()
    assert pred[pred.code == 2]["e_gc"].mean() > pred[pred.code == 1]["e_gc"].mean()


def test_add_team_rolling_is_leakage_safe():
    """A row's rolling feature must use only strictly-earlier matches."""
    tg = pd.DataFrame([
        {"code": 1, "season_idx": 0, "gw": 1, "gf": 1, "ga": 0, "cs": 1},
        {"code": 1, "season_idx": 0, "gw": 2, "gf": 1, "ga": 3, "cs": 0},
        {"code": 1, "season_idx": 0, "gw": 3, "gf": 1, "ga": 0, "cs": 1},
    ])
    out = add_team_rolling(tg).set_index("gw")
    assert pd.isna(out.loc[1, "team_ga_r5"])
    assert out.loc[2, "team_ga_r5"] == 0.0
    assert out.loc[3, "team_ga_r5"] == 1.5


def _odds_training_frame(with_odds_values: bool) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    rows = []
    for gw in range(1, 60):
        strong_cs = int(rng.random() < 0.6)
        weak_cs = int(rng.random() < 0.1)
        rows.append({"code": 1, "season_idx": 0, "gw": gw, "home": 1.0,
                     "cs": strong_cs, "ga": 0 if strong_cs else 1,
                     "gf": 2, "elo_diff": 200.0,
                     "team_gf_r5": 2.0, "team_ga_r5": 0.5,
                     "team_cs_r10": 0.6, "team_gf_r38": 2.0,
                     "team_ga_r38": 0.5})
        rows.append({"code": 2, "season_idx": 0, "gw": gw, "home": 0.0,
                     "cs": weak_cs, "ga": 0 if weak_cs else 2,
                     "gf": 0, "elo_diff": -200.0,
                     "team_gf_r5": 0.5, "team_ga_r5": 2.0,
                     "team_cs_r10": 0.1, "team_gf_r38": 0.5,
                     "team_ga_r38": 2.0})
    df = pd.DataFrame(rows)
    if with_odds_values:
        df["odds_e_goals_for"] = np.where(df["code"] == 1, 2.0, 0.7)
        df["odds_e_goals_against"] = np.where(df["code"] == 1, 0.6, 2.1)
    else:
        df["odds_e_goals_for"] = np.nan
        df["odds_e_goals_against"] = np.nan
    return df


def test_team_model_fits_with_all_nan_odds_columns():
    df = _odds_training_frame(with_odds_values=False)
    m = TeamModel().fit(df[df.gw <= 45])
    assert "odds_e_goals_for" in m.cols_
    pred = m.predict(df[df.gw > 45])
    assert len(pred) == len(df[df.gw > 45])
    assert pred["p_cs"].between(0, 1).all()
    assert pred["e_gc"].notna().all()


def test_team_model_fits_with_populated_odds_columns():
    df = _odds_training_frame(with_odds_values=True)
    m = TeamModel().fit(df[df.gw <= 45])
    pred = m.predict(df[df.gw > 45])
    assert pred[pred.code == 1]["p_cs"].mean() > pred[pred.code == 2]["p_cs"].mean()
    assert pred[pred.code == 2]["e_gc"].mean() > pred[pred.code == 1]["e_gc"].mean()


def test_team_model_tolerates_missing_odds_columns_entirely():
    """Training frames built before odds existed must still fit and predict."""
    df = _odds_training_frame(with_odds_values=False).drop(
        columns=["odds_e_goals_for", "odds_e_goals_against"])
    m = TeamModel().fit(df[df.gw <= 45])
    assert "odds_e_goals_for" in m.cols_          # guard supplied it as NaN
    pred = m.predict(df[df.gw > 45])
    assert pred["e_gc"].notna().all()
    assert "odds_e_goals_for" not in df.columns   # caller's frame untouched


def test_team_features_includes_odds_columns():
    assert TEAM_FEATURES[-2:] == ["odds_e_goals_for", "odds_e_goals_against"]


# ------------------------------------------------------------ blend_team_odds

def _team_preds() -> pd.DataFrame:
    """Two team-fixture predictions: one covered by the odds feed, one not."""
    return pd.DataFrame([
        {"code": 1, "season_idx": 4, "gw": 2, "p_cs": 0.3, "e_gc": 1.5,
         "odds_e_goals_against": 1.0},
        {"code": 2, "season_idx": 4, "gw": 2, "p_cs": 0.44, "e_gc": 1.2,
         "odds_e_goals_against": np.nan},
    ])


def test_blend_team_odds_matches_hand_computed_blend():
    out = blend_team_odds(_team_preds())
    row = out[out["code"] == 1].iloc[0]
    w = ODDS_BLEND_WEIGHT
    assert row["p_cs"] == pytest.approx(w * np.exp(-1.0) + (1 - w) * 0.3)
    assert row["p_cs"] == pytest.approx(0.3475156)
    assert row["e_gc"] == pytest.approx(w * 1.0 + (1 - w) * 1.5)
    assert row["e_gc"] == pytest.approx(1.15)


def test_blend_team_odds_leaves_rows_without_odds_untouched():
    out = blend_team_odds(_team_preds())
    row = out[out["code"] == 2].iloc[0]
    assert row["p_cs"] == pytest.approx(0.44)
    assert row["e_gc"] == pytest.approx(1.2)


def test_blend_team_odds_does_not_mutate_the_caller_frame():
    preds = _team_preds()
    blend_team_odds(preds)
    assert preds.loc[0, "p_cs"] == pytest.approx(0.3)
    assert preds.loc[0, "e_gc"] == pytest.approx(1.5)


def test_blend_team_odds_without_the_odds_column_returns_frame_unchanged():
    preds = _team_preds().drop(columns=["odds_e_goals_against"])
    out = blend_team_odds(preds)
    pd.testing.assert_frame_equal(out, preds)
