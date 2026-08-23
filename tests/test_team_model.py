import pandas as pd
import numpy as np
from gaffer.models.team import build_team_gw, add_team_rolling, TeamModel


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
