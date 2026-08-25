import math

import numpy as np
import pandas as pd

from gaffer.models.dixon_coles import (GOAL_CAP, RHO_BOUNDS, fixture_outcomes,
                                       scoreline_pmf, tau_correction)


def test_tau_correction_is_one_away_from_the_low_score_corner():
    assert tau_correction(2, 3, 1.4, 1.1, -0.1) == 1.0
    assert tau_correction(0, 2, 1.4, 1.1, -0.1) == 1.0


def test_tau_correction_matches_the_published_four_cases():
    lam, mu, rho = 1.4, 1.1, -0.12
    assert abs(tau_correction(0, 0, lam, mu, rho) - (1 - lam * mu * rho)) < 1e-12
    assert abs(tau_correction(0, 1, lam, mu, rho) - (1 + lam * rho)) < 1e-12
    assert abs(tau_correction(1, 0, lam, mu, rho) - (1 + mu * rho)) < 1e-12
    assert abs(tau_correction(1, 1, lam, mu, rho) - (1 - rho)) < 1e-12


def test_scoreline_pmf_sums_to_one():
    pmf = scoreline_pmf(1.6, 1.1, -0.12)
    assert abs(pmf.sum() - 1.0) < 1e-12
    assert pmf.shape == (GOAL_CAP + 1, GOAL_CAP + 1)


def test_scoreline_pmf_with_zero_rho_is_independent_poisson():
    pmf = scoreline_pmf(1.6, 1.1, 0.0)
    for x in (0, 1, 3):
        for y in (0, 2):
            want = (math.exp(-1.6) * 1.6 ** x / math.factorial(x)
                    * math.exp(-1.1) * 1.1 ** y / math.factorial(y))
            assert abs(pmf[x, y] - want) < 1e-6


def test_scoreline_pmf_negative_rho_lifts_the_nil_nil():
    """The correction exists because low-scoring scorelines are more common
    than independence implies; a negative rho is what buys that."""
    assert scoreline_pmf(1.4, 1.1, -0.12)[0, 0] > scoreline_pmf(1.4, 1.1, 0.0)[0, 0]


def test_scoreline_pmf_is_never_negative():
    for rho in (-0.4, -0.1, 0.0, 0.1, 0.4):
        assert (scoreline_pmf(0.4, 3.5, rho) >= 0.0).all()


def test_fixture_outcomes_clean_sheet_is_the_opponents_zero_column():
    out = fixture_outcomes(1.6, 1.1, -0.12)
    pmf = scoreline_pmf(1.6, 1.1, -0.12)
    assert abs(out["p_cs_home"] - pmf[:, 0].sum()) < 1e-12
    assert abs(out["p_cs_away"] - pmf[0, :].sum()) < 1e-12


def test_fixture_outcomes_expected_goals_conceded_matches_the_mean():
    out = fixture_outcomes(1.6, 1.1, 0.0)
    # With rho = 0 the marginals are Poisson, so E[GC] is the mu — up to the
    # mass truncated past GOAL_CAP, which is worth ~1e-5 of the mean at
    # Premier League scoring rates.
    assert abs(out["e_gc_home"] - 1.1) < 1e-4
    assert abs(out["e_gc_away"] - 1.6) < 1e-4


def test_fixture_outcomes_result_probabilities_sum_to_one():
    out = fixture_outcomes(1.6, 1.1, -0.12)
    total = out["p_home_win"] + out["p_draw"] + out["p_away_win"]
    assert abs(total - 1.0) < 1e-12


def test_fixture_outcomes_reports_the_two_goal_concession_band():
    """The -0.5/goal deduction only starts biting at two conceded, so the
    band is worth carrying out of the one coherent distribution."""
    out = fixture_outcomes(1.6, 1.1, -0.12)
    pmf = scoreline_pmf(1.6, 1.1, -0.12)
    assert abs(out["p_gc2_home"] - pmf[:, 2:].sum()) < 1e-12


def test_fixture_outcomes_stronger_side_has_the_better_clean_sheet():
    strong = fixture_outcomes(2.2, 0.6, -0.12)
    weak = fixture_outcomes(0.6, 2.2, -0.12)
    assert strong["p_cs_home"] > weak["p_cs_home"]


from gaffer.models.dixon_coles import DEFAULT_XI, DixonColesModel
from gaffer.models.team import build_team_gw


def _synthetic_fixtures(attack, defence, gamma=0.28, repeats=8, seed=7,
                        season_idx=0, start_day=0):
    """Double round-robins sampled from known Dixon-Coles parameters."""
    rng = np.random.default_rng(seed)
    n = len(attack)
    rows, day = [], start_day
    for _ in range(repeats):
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                lam = math.exp(attack[i] + defence[j] + gamma)
                mu = math.exp(attack[j] + defence[i])
                rows.append({
                    "season_idx": season_idx, "gw": 1 + day // 20,
                    "kickoff_time": (pd.Timestamp("2020-01-01", tz="UTC")
                                     + pd.Timedelta(days=day)).isoformat(),
                    "home_code": i, "away_code": j,
                    "home_goals": int(rng.poisson(lam)),
                    "away_goals": int(rng.poisson(mu))})
                day += 1
    return pd.DataFrame(rows)


_TRUE_ATTACK = np.linspace(0.5, -0.5, 12) - np.linspace(0.5, -0.5, 12).mean()
_TRUE_DEFENCE = np.linspace(-0.4, 0.4, 12)


def _fitted(xi=0.0):
    fx = _synthetic_fixtures(_TRUE_ATTACK, _TRUE_DEFENCE)
    return DixonColesModel(xi=xi).fit(build_team_gw(fx)), fx


def test_matches_from_team_gw_rebuilds_one_row_per_match():
    fx = _synthetic_fixtures(_TRUE_ATTACK, _TRUE_DEFENCE, repeats=1)
    tg = build_team_gw(fx)
    matches = DixonColesModel.matches_from_team_gw(tg)
    assert len(matches) == len(fx)
    assert set(matches.columns) >= {"season_idx", "gw", "kickoff_time",
                                    "home_code", "away_code", "home_goals",
                                    "away_goals"}
    assert matches["home_goals"].sum() == fx["home_goals"].sum()


def test_fit_recovers_the_attack_parameters():
    model, _ = _fitted()
    fitted = np.array([model.attack_[c] for c in range(12)])
    assert np.abs(fitted - _TRUE_ATTACK).max() < 0.25
    assert np.corrcoef(fitted, _TRUE_ATTACK)[0, 1] > 0.9


def test_fit_recovers_the_defence_parameters_up_to_the_shared_level():
    """Only differences are identified: the attack constraint fixes the
    overall scale, and a constant added to every defence is absorbed by the
    attacks."""
    model, _ = _fitted()
    fitted = np.array([model.defence_[c] for c in range(12)])
    centred = fitted - fitted.mean()
    assert np.abs(centred - (_TRUE_DEFENCE - _TRUE_DEFENCE.mean())).max() < 0.25


def test_fit_recovers_the_home_advantage():
    model, _ = _fitted()
    assert abs(model.gamma_ - 0.28) < 0.1


def test_fit_holds_mean_log_attack_at_zero():
    """Identifiability: without it every attack could rise by a constant and
    every defence fall by the same one with no change in likelihood."""
    model, _ = _fitted()
    assert abs(float(np.mean(list(model.attack_.values())))) < 1e-9


def test_fit_keeps_rho_inside_its_bracket():
    model, _ = _fitted()
    assert RHO_BOUNDS[0] <= model.rho_ <= RHO_BOUNDS[1]


def _two_era_fixtures(seed=5):
    """A team that was poor for six round-robins and good for six."""
    n, rows, day = 6, [], 0
    rng = np.random.default_rng(seed)
    for boost in (-0.6, 0.8):
        for _ in range(6):
            for i in range(n):
                for j in range(n):
                    if i == j:
                        continue
                    a = [0.0] * n
                    a[0] = boost
                    lam = math.exp(a[i] + 0.25)
                    mu = math.exp(a[j])
                    rows.append({
                        "season_idx": 0, "gw": 1 + day // 20,
                        "kickoff_time": (pd.Timestamp("2020-01-01", tz="UTC")
                                         + pd.Timedelta(days=day)).isoformat(),
                        "home_code": i, "away_code": j,
                        "home_goals": int(rng.poisson(lam)),
                        "away_goals": int(rng.poisson(mu))})
                    day += 1
    return pd.DataFrame(rows)


def test_decay_pulls_the_fit_toward_recent_form():
    """The reason the decay exists: a team that improved halfway through has
    to read as good now, not as the average of its two selves."""
    tg = build_team_gw(_two_era_fixtures())
    flat = DixonColesModel(xi=0.0).fit(tg).attack_[0]
    decayed = DixonColesModel(xi=0.02).fit(tg).attack_[0]
    assert decayed > flat + 0.2


def test_default_xi_is_the_pinned_constant():
    assert DixonColesModel().xi == DEFAULT_XI


def test_fit_stores_a_promoted_team_fallback_from_the_bottom_three():
    """A newly-promoted club has no Premier League history at all; the
    bottom three of the latest season are the closest thing to a prior."""
    model, _ = _fitted()
    bottom = model.bottom_codes_
    assert len(bottom) == 3
    assert abs(model.fallback_attack_
               - float(np.mean([model.attack_[c] for c in bottom]))) < 1e-12
    assert abs(model.fallback_defence_
               - float(np.mean([model.defence_[c] for c in bottom]))) < 1e-12


def test_the_bottom_three_are_the_weakest_teams_in_the_latest_season():
    model, _ = _fitted()
    # Attack was built descending, so the weakest codes are the last three.
    assert set(model.bottom_codes_) <= {9, 10, 11}


def test_fit_on_a_single_round_robin_still_converges():
    fx = _synthetic_fixtures(_TRUE_ATTACK, _TRUE_DEFENCE, repeats=1)
    model = DixonColesModel().fit(build_team_gw(fx))
    assert len(model.attack_) == 12
    assert np.isfinite(model.gamma_)


def _future_rows(codes=(0, 1), opp=(1, 0), home=(1.0, 0.0)):
    return pd.DataFrame([
        {"code": c, "opp_code": o, "home": h, "season_idx": 1, "gw": 5,
         "kickoff_time": "2021-01-01T15:00:00Z"}
        for c, o, h in zip(codes, opp, home)])


def test_predict_returns_the_team_model_contract_columns():
    """Parity with TeamModel is the whole reason the swap is one line."""
    from gaffer.models.team import TeamModel

    model, _ = _fitted()
    out = model.predict(_future_rows())
    assert list(out.columns) == ["code", "season_idx", "gw", "p_cs", "e_gc"]
    assert len(out) == 2

    gbm = TeamModel(feature_cols=["home"])
    tg = build_team_gw(_synthetic_fixtures(_TRUE_ATTACK, _TRUE_DEFENCE,
                                           repeats=1))
    gbm.fit(tg)
    assert list(gbm.predict(tg.head(2)).columns) == list(out.columns)


def test_predict_is_row_for_row_with_its_input():
    """Every caller stitches component outputs positionally, so a dropped or
    reordered row silently misattributes a clean sheet."""
    model, _ = _fitted()
    rows = _future_rows(codes=(3, 7, 3), opp=(7, 3, 7),
                        home=(1.0, 0.0, 0.0))
    out = model.predict(rows)
    assert list(out["code"]) == [3, 7, 3]


def test_predict_probabilities_are_in_range():
    model, _ = _fitted()
    out = model.predict(_future_rows(codes=tuple(range(12)),
                                     opp=tuple(reversed(range(12))),
                                     home=tuple([1.0] * 12)))
    assert (out["p_cs"] >= 0.0).all() and (out["p_cs"] <= 1.0).all()
    assert (out["e_gc"] >= 0.0).all()


def test_predict_gives_the_stronger_team_the_better_clean_sheet():
    model, _ = _fitted()
    out = model.predict(_future_rows(codes=(0, 11), opp=(11, 0),
                                     home=(1.0, 0.0)))
    assert out.loc[0, "p_cs"] > out.loc[1, "p_cs"]
    assert out.loc[1, "e_gc"] > out.loc[0, "e_gc"]


def test_predict_home_advantage_helps_the_same_pairing():
    model, _ = _fitted()
    at_home = model.predict(_future_rows(codes=(4,), opp=(5,), home=(1.0,)))
    away = model.predict(_future_rows(codes=(4,), opp=(5,), home=(0.0,)))
    assert at_home.loc[0, "e_gc"] < away.loc[0, "e_gc"]


def test_predict_uses_the_promoted_fallback_for_an_unseen_club():
    """A promoted club appears in the fixture list with no history at all;
    predicting NaN for it would knock out every player in its squad."""
    model, _ = _fitted()
    out = model.predict(_future_rows(codes=(999,), opp=(0,), home=(1.0,)))
    assert out["p_cs"].notna().all()
    assert 0.0 < float(out.loc[0, "p_cs"]) < 1.0


def test_predict_treats_two_unseen_clubs_as_equals():
    model, _ = _fitted()
    out = model.predict(_future_rows(codes=(999, 998), opp=(998, 999),
                                     home=(1.0, 0.0)))
    # Same parameters both sides: only the home advantage separates them.
    assert out.loc[0, "p_cs"] > out.loc[1, "p_cs"]


def test_predict_handles_a_double_gameweek_row_pair():
    """The team-future frame is already one row per fixture, so a DGW needs
    nothing special — but it must not be collapsed."""
    model, _ = _fitted()
    rows = _future_rows(codes=(2, 2), opp=(6, 8), home=(1.0, 0.0))
    out = model.predict(rows)
    assert len(out) == 2
    assert out["p_cs"].nunique() == 2


def test_predict_without_a_home_column_treats_every_row_as_neutral():
    """Frames from the simple component path carry no ``home``; a KeyError
    there would take the whole backtest down."""
    model, _ = _fitted()
    rows = _future_rows().drop(columns=["home"])
    out = model.predict(rows)
    assert out["p_cs"].notna().all()


from gaffer.models.dixon_coles import walk_forward_cs
from gaffer.models.team import fit_blend_weight


def test_fit_blend_weight_recovers_a_pure_odds_mixture():
    """If the odds column is the truth and the model column is noise, the
    fit has to land on w = 1."""
    rng = np.random.default_rng(0)
    p = rng.uniform(0.05, 0.95, 4000)
    cs = (rng.random(4000) < p).astype(float)
    frame = pd.DataFrame({"p_cs_odds": p, "p_cs_model": rng.random(4000),
                          "cs": cs})
    assert fit_blend_weight(frame) >= 0.95


def test_fit_blend_weight_recovers_a_pure_model_mixture():
    rng = np.random.default_rng(1)
    p = rng.uniform(0.05, 0.95, 4000)
    cs = (rng.random(4000) < p).astype(float)
    frame = pd.DataFrame({"p_cs_odds": rng.random(4000), "p_cs_model": p,
                          "cs": cs})
    assert fit_blend_weight(frame) <= 0.05


def test_fit_blend_weight_lands_between_two_noisy_signals():
    """Both sides carry the signal plus independent noise, so neither alone
    is optimal and the fit has to compromise."""
    rng = np.random.default_rng(2)
    truth = rng.uniform(0.1, 0.9, 8000)
    cs = (rng.random(8000) < truth).astype(float)
    jitter = lambda: np.clip(truth + rng.normal(0, 0.12, 8000), 0.01, 0.99)
    frame = pd.DataFrame({"p_cs_odds": jitter(), "p_cs_model": jitter(),
                          "cs": cs})
    w = fit_blend_weight(frame)
    assert 0.2 < w < 0.8


def test_fit_blend_weight_prefers_the_smaller_w_when_the_curve_is_flat():
    """Two signals of identical quality leave the loss curve flat, so no w
    beats the argmin by more than noise. The 1-SE rule then has to take the
    *smallest* w in that band rather than the noise-won extreme: the raw
    argmin on this draw is 0.41, but every w down to ~0.29 is within one
    standard error of it."""
    rng = np.random.default_rng(1)
    n = 2000
    truth = rng.uniform(0.1, 0.9, n)
    cs = (rng.random(n) < truth).astype(float)
    jitter = lambda: np.clip(truth + rng.normal(0, 0.10, n), 0.01, 0.99)
    frame = pd.DataFrame({"p_cs_odds": jitter(), "p_cs_model": jitter(),
                          "cs": cs})
    assert fit_blend_weight(frame) <= 0.30


def test_fit_blend_weight_is_quantized_to_two_decimals():
    rng = np.random.default_rng(3)
    frame = pd.DataFrame({"p_cs_odds": rng.random(500),
                          "p_cs_model": rng.random(500),
                          "cs": rng.integers(0, 2, 500).astype(float)})
    w = fit_blend_weight(frame)
    assert w == round(w, 2)
    assert 0.0 <= w <= 1.0


def test_fit_blend_weight_on_an_empty_frame_returns_the_constant():
    from gaffer.models.team import ODDS_BLEND_WEIGHT

    empty = pd.DataFrame(columns=["p_cs_odds", "p_cs_model", "cs"])
    assert fit_blend_weight(empty) == ODDS_BLEND_WEIGHT


def test_fit_blend_weight_ignores_rows_missing_either_side():
    frame = pd.DataFrame({"p_cs_odds": [0.9, float("nan"), 0.8],
                          "p_cs_model": [0.9, 0.5, float("nan")],
                          "cs": [1.0, 0.0, 1.0]})
    assert fit_blend_weight(frame) == round(fit_blend_weight(frame.head(1)), 2)


def _odds_for(fx: pd.DataFrame) -> pd.DataFrame:
    """Closing-odds rows for every fixture, priced off the true scoreline."""
    rows = []
    for m in fx.itertuples():
        total = m.home_goals + m.away_goals
        rows.append({"season_idx": m.season_idx, "gw": m.gw,
                     "kickoff_time": m.kickoff_time,
                     "home_code": m.home_code, "away_code": m.away_code,
                     "p_home": 0.45, "p_draw": 0.27, "p_away": 0.28,
                     "p_over25": 0.6 if total >= 3 else 0.4})
    return pd.DataFrame(rows)


def test_walk_forward_cs_predicts_each_half_from_earlier_data_only():
    fx = pd.concat([
        _synthetic_fixtures(_TRUE_ATTACK, _TRUE_DEFENCE, repeats=3,
                            season_idx=0, seed=4),
        _synthetic_fixtures(_TRUE_ATTACK, _TRUE_DEFENCE, repeats=3,
                            season_idx=1, seed=5, start_day=800),
    ], ignore_index=True)
    tg = build_team_gw(fx)
    out = walk_forward_cs(tg, _odds_for(fx), xi=DEFAULT_XI)
    assert set(out.columns) == {"season_idx", "gw", "code", "opp_code",
                                "p_cs_odds", "p_cs_model", "cs"}
    # The first half has nothing before it and is not scored.
    assert out["season_idx"].min() >= 0
    assert len(out) > 0
    assert out["p_cs_model"].between(0.0, 1.0).all()
    assert out["p_cs_odds"].between(0.0, 1.0).all()
    assert set(out["cs"].unique()) <= {0.0, 1.0}


def test_walk_forward_cs_without_odds_returns_an_empty_frame():
    """No football-data file means no fittable weight — and the caller has to
    fall back to the constant rather than fit on nothing."""
    fx = _synthetic_fixtures(_TRUE_ATTACK, _TRUE_DEFENCE, repeats=2)
    out = walk_forward_cs(build_team_gw(fx),
                          pd.DataFrame(columns=["season_idx", "gw",
                                                "home_code", "away_code",
                                                "p_home", "p_draw", "p_away",
                                                "p_over25"]),
                          xi=DEFAULT_XI)
    assert out.empty
