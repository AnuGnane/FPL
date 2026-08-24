import pandas as pd
from gaffer import backtest as bt
from gaffer.backtest import run_backtest, score_gw
from gaffer.config import Config
from gaffer.optimize.milp import GwPlan, Plan


def _actuals():
    """Legal XI: code 1 GKP, 2-6 DEF, 7-10 MID, 11 FWD; bench 12-15 MID."""
    spec = {1: (10, 90, "GKP"),                      # captain, hauled
            2: (2, 90, "DEF"), 3: (2, 90, "DEF"), 4: (2, 90, "DEF"),
            5: (0, 0, "DEF"),                        # starter, didn't play
            6: (2, 90, "DEF"),
            7: (2, 90, "MID"), 8: (2, 90, "MID"),
            9: (2, 90, "MID"), 10: (2, 90, "MID"),
            11: (2, 90, "FWD"),
            12: (6, 90, "MID"),                      # bench, played -> subs in
            13: (2, 90, "MID"), 14: (2, 90, "MID"), 15: (2, 90, "MID")}
    return pd.DataFrame([{"code": c, "total_points": p, "minutes": m,
                          "position": pos} for c, (p, m, pos) in spec.items()])


def test_score_gw_captain_doubles_and_autosub():
    xi = list(range(1, 12))       # includes code 5 (0 mins)
    bench = [12, 13, 14, 15]
    pts = score_gw(_actuals(), xi=xi, bench=bench, captain=1, vice=2, hits=1)
    # XI without 5: 10(GK) + 4*2(DEF) + 4*2(MID) + 2(FWD) = 28
    # sub 12 in for 5 (formation 1-4-5-1, legal): +6 = 34
    # captain 1 played -> +10 = 44 ; one hit -> -4 => 40
    assert pts == 40


def test_score_gw_vice_takes_over_when_captain_blanks():
    actuals = _actuals()
    actuals.loc[actuals.code == 1, ["total_points", "minutes"]] = [0, 0]
    pts = score_gw(actuals, xi=list(range(1, 12)), bench=[12, 13, 14, 15],
                   captain=1, vice=2, hits=0)
    # GK blanked; no GK on the bench so no legal sub for him. Code 5 still
    # subs out for 12: 0 + 4*2 + 8 + 2 + 6 = 24
    # captain 0 mins -> vice code 2 doubles: +2 => 26
    assert pts == 26


# --- receding-horizon replay --------------------------------------------
#
# The whole pipeline around the MILP is stubbed out (training frame, model
# fit, component prediction, EP assembly) so the loop runs on a synthetic
# three-gameweek season in milliseconds. ``solve_plan`` is the seam under
# test: a spy records the horizon it was handed and returns a Plan whose
# second gameweek plan deliberately differs from the first, so a run that
# executed anything other than ``gw_plans[0]`` would show up in the squad.

POSITIONS = (["GKP"] * 4 + ["DEF"] * 6 + ["MID"] * 6 + ["FWD"] * 4)


def _season_rows(gws, n=20):
    rows = []
    for gw in gws:
        for i in range(n):
            rows.append({
                "season_idx": 0, "gw": gw, "code": 101 + i,
                "element": 1 + i, "name": f"P{i}", "position": POSITIONS[i],
                "team_code": 1 + i % 7, "value": 40 + i,
                "kickoff_time": f"2025-0{1 + gw % 9}-01T12:00:00Z",
                "total_points": 2, "minutes": 90,
            })
    return pd.DataFrame(rows)


def _install_stubs(monkeypatch, season_rows):
    """Replace everything except the loop itself, and record what the MILP
    and the pool builder were asked to plan over."""
    calls = {"solve_gws": [], "pool_gws": [], "predict_gws": [], "plans": [],
             "owned": []}

    def fake_load_training_frame(*a, **k):
        return season_rows, pd.DataFrame(), None

    def fake_predict(models, rows):
        calls["predict_gws"].append(sorted(set(int(g) for g in rows["gw"])))
        return rows

    real_build_pool = bt.build_pool

    def spy_build_pool(players, ep_by, picks, gws, *a, **k):
        calls["pool_gws"].append(list(gws))
        return real_build_pool(players, ep_by, picks, gws, *a, **k)

    def spy_solve_plan(pool, state, **kw):
        calls["solve_gws"].append(list(state.gws))
        calls["owned"].append(list(state.owned_codes))
        codes = list(pool["code"])
        owned = list(state.owned_codes)
        plans = []
        for i, gw in enumerate(state.gws):
            # gw_plans[1:] pick a *different* 15 on purpose.
            squad = codes[:15] if i == 0 else codes[-15:]
            plans.append(GwPlan(
                gw=gw, squad=squad, xi=squad[:11],
                xi_rows=[], bench=squad[11:],
                captain=squad[0], vice=squad[1],
                buys=[c for c in squad if c not in owned],
                sells=[c for c in owned if c not in squad],
                hits=0, expected_pts=float(len(squad))))
        calls["plans"].append(plans)
        return Plan(objective=1.0, gw_plans=plans)

    monkeypatch.setattr(bt, "load_config", lambda *a, **k: Config(
        entry_id=1, league_id=1, train_seasons=["2025-26"]))
    monkeypatch.setattr(bt, "load_bootstrap_sample", lambda *a, **k: {})
    monkeypatch.setattr(bt, "scoring_table", lambda *a, **k: {})
    monkeypatch.setattr(bt, "load_training_frame", fake_load_training_frame)
    monkeypatch.setattr(bt, "train_all", lambda *a, **k: {})
    monkeypatch.setattr(bt, "predict_components_simple", fake_predict)
    monkeypatch.setattr(bt, "assemble_ep", lambda comp, scoring: comp)
    monkeypatch.setattr(bt, "apply_calibration", lambda df, cal: df)
    monkeypatch.setattr(bt, "ep_matrix",
                        lambda df: df[["code", "gw"]].assign(ep=1.0))
    monkeypatch.setattr(bt, "build_pool", spy_build_pool)
    monkeypatch.setattr(bt, "solve_plan", spy_solve_plan)
    monkeypatch.setattr(bt.store, "save", lambda *a, **k: None)
    return calls


def test_backtest_horizon_plans_ahead_but_executes_only_the_first_gw(
        monkeypatch):
    calls = _install_stubs(monkeypatch, _season_rows([1, 2, 3]))
    run_backtest(season="2025-26", start_gw=1, retrain_every=4, horizon=3)

    # Planned over three weeks each time; the pool and the EP predictions
    # cover the same horizon so future-gameweek EP reaches the objective.
    assert calls["solve_gws"] == [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
    assert calls["pool_gws"] == calls["solve_gws"]
    assert calls["predict_gws"] == [[1, 2, 3], [2, 3], [3]]


def test_backtest_executes_gw_plans_zero_not_later_plans(monkeypatch):
    rows = _season_rows([1, 2, 3])
    calls = _install_stubs(monkeypatch, rows)
    run_backtest(season="2025-26", start_gw=1, retrain_every=4, horizon=3)

    # Week 2 starts from the squad of week 1's *first* plan, not from the
    # deliberately-different gw_plans[1] that was also returned.
    for week in range(2):
        executed = calls["plans"][week][0].squad
        ignored = calls["plans"][week][1].squad
        assert set(executed) != set(ignored)
        assert set(calls["owned"][week + 1]) == set(executed)


def test_backtest_horizon_is_capped_at_the_last_gameweek(monkeypatch):
    calls = _install_stubs(monkeypatch, _season_rows([37, 38]))
    run_backtest(season="2025-26", start_gw=37, retrain_every=4, horizon=4)
    assert calls["solve_gws"] == [[37, 38], [38]]


def test_backtest_horizon_one_keeps_the_single_gw_call_shape(monkeypatch):
    calls = _install_stubs(monkeypatch, _season_rows([1, 2, 3]))
    out = run_backtest(season="2025-26", start_gw=1, retrain_every=4)
    assert calls["solve_gws"] == [[1], [2], [3]]
    assert calls["pool_gws"] == [[1], [2], [3]]
    assert len(out["log"]) == 3
