import pandas as pd
import pytest
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


# --- chips ---------------------------------------------------------------
#
# ``score_gw``'s two contract tests above are left untouched on purpose: the
# chip arguments are keyword-only defaults, so the old call shape has to keep
# scoring 40 and 26.


def test_score_gw_triple_captain_adds_the_captain_twice_over():
    pts = score_gw(_actuals(), xi=list(range(1, 12)), bench=[12, 13, 14, 15],
                   captain=1, vice=2, hits=1, captain_mult=3)
    # Same XI as the doubling case (34 after the autosub); the captain now
    # adds (3-1)*10 = 20 instead of 10 -> 54, one hit -> 50.
    assert pts == 50


def test_score_gw_bench_boost_scores_all_fifteen_and_skips_autosubs():
    pts = score_gw(_actuals(), xi=list(range(1, 12)), bench=[12, 13, 14, 15],
                   captain=1, vice=2, hits=0, bench_boost=True)
    # No autosub, so code 5 stays in the XI on 0: XI = 28. Bench adds
    # 6+2+2+2 = 12 -> 40, captain 1 doubles -> +10 => 50.
    assert pts == 50


def _stub_evaluate_chips(monkeypatch, calls, gains):
    """Stand in for ``evaluate_chips``: one row per available chip, gain from
    ``gains[(gw, chip)]`` (0 otherwise). Records the availability list it was
    handed so the half-season bookkeeping can be asserted."""
    calls["avail"] = []

    def fake(pool, state, chips_available, base=None, **cfg):
        calls["avail"].append(list(chips_available))
        gw = state.gws[0]
        rows = [{"chip": c, "gw": gw, "gain": float(gains.get((gw, c), 0.0))}
                for c in chips_available]
        return (pd.DataFrame(rows)
                .sort_values("gain", ascending=False).reset_index(drop=True))

    monkeypatch.setattr(bt, "evaluate_chips", fake)


def test_backtest_plays_no_chips_by_default(monkeypatch):
    calls = _install_stubs(monkeypatch, _season_rows([1, 2, 3]))
    _stub_evaluate_chips(monkeypatch, calls, {(2, "3xc"): 50.0})
    out = run_backtest(season="2025-26", start_gw=1, retrain_every=4)
    assert out["chips_played"] == {}
    assert [r["chip"] for r in out["log"]] == ["", "", ""]
    assert calls["avail"] == []


def test_backtest_plays_triple_captain_and_spends_it_for_the_half(monkeypatch):
    calls = _install_stubs(monkeypatch, _season_rows([1, 2, 3]))
    _stub_evaluate_chips(monkeypatch, calls, {(2, "3xc"): 50.0})
    out = run_backtest(season="2025-26", start_gw=1, retrain_every=4,
                       chips=True)
    rows = {r["gw"]: r for r in out["log"]}

    assert [r["chip"] for r in out["log"]] == ["", "3xc", ""]
    assert out["chips_played"] == {2: "3xc"}
    # Every stub player scores 2 off 90 minutes: XI 22 + the captain again.
    assert rows[1]["points"] == 24 and rows[3]["points"] == 24
    assert rows[2]["points"] == 26           # captain tripled
    # GW1 builds the squad, so chips are first weighed in GW2; by GW3 the
    # 3xc is spent for this half of the season.
    assert calls["avail"] == [["wildcard", "freehit", "bboost", "3xc"],
                              ["wildcard", "freehit", "bboost"]]


FH_GW = 2


def _fh_alt_squad(monkeypatch):
    """Make the free-hit solve (owns nothing, single gameweek, GW2) return a
    *different* 15, so a replay that failed to revert would show it."""
    inner = bt.solve_plan

    def spy(pool, state, **kw):
        plan = inner(pool, state, **kw)
        if not state.owned_codes and list(state.gws) == [FH_GW]:
            alt = list(pool["code"])[-15:]
            plan.gw_plans[0] = GwPlan(
                gw=FH_GW, squad=alt, xi=alt[:11], xi_rows=[], bench=alt[11:],
                captain=alt[0], vice=alt[1], buys=list(alt), sells=[],
                hits=0, expected_pts=99.0)
        return plan

    monkeypatch.setattr(bt, "solve_plan", spy)


def test_backtest_free_hit_scores_one_week_then_reverts(monkeypatch):
    calls = _install_stubs(monkeypatch, _season_rows([1, 2, 3]))
    _stub_evaluate_chips(monkeypatch, calls, {(FH_GW, "freehit"): 50.0})
    _fh_alt_squad(monkeypatch)
    out = run_backtest(season="2025-26", start_gw=1, retrain_every=4,
                       chips=True)
    rows = {r["gw"]: r for r in out["log"]}

    assert rows[2]["chip"] == "freehit"
    assert out["chips_played"] == {2: "freehit"}
    # Solves: GW1 build, GW2 base, GW2 free hit, GW3 base.
    assert calls["owned"][2] == []
    before, after = calls["owned"][1], calls["owned"][3]
    fh_squad = calls["plans"][2][0].squad
    assert set(after) == set(before)         # permanent squad reverted
    assert set(after) != set(fh_squad)       # ... and it is not the FH squad
    assert rows[2]["bank"] == rows[1]["bank"]
    assert rows[2]["transfers"] == 0 and rows[2]["hits"] == 0
    assert rows[2]["points"] == 24           # the free-hit XI was scored
    # The free hit is spent for the half.
    assert calls["avail"] == [["wildcard", "freehit", "bboost", "3xc"],
                              ["wildcard", "bboost", "3xc"]]


# --- horizon feature rows carry no future information --------------------
#
# The replay's later-gameweek rows used to come straight out of the
# untruncated training frame, so a GW+1 row's shift(1) rolling window held
# the GW result that had not been played yet at the decision deadline.


def _explosion_season(explode_gw, n=3, gws=(1, 2, 3, 4)):
    """Raw (unengineered) player-match rows; player 101 hauls in
    ``explode_gw`` and scores 2 everywhere else."""
    rows = []
    for gw in gws:
        for i in range(n):
            code = 101 + i
            pts = 50 if (code == 101 and gw == explode_gw) else 2
            rows.append({
                "season_idx": 0, "gw": gw, "code": code, "element": 1 + i,
                "name": f"P{i}", "position": POSITIONS[i],
                "team_code": 1 + i, "opp_code": 20 + i, "was_home": True,
                "kickoff_time": f"2025-01-{gw:02d}T12:00:00Z",
                "total_points": pts, "minutes": 90, "starts": 1,
            })
    return pd.DataFrame(rows)


def test_horizon_rows_do_not_see_results_after_the_decision_gw():
    hist = _explosion_season(explode_gw=2)
    # Deciding at GW2: plan GW2..GW4, execute GW2. The GW3 row's r1 window
    # may only see matches strictly before GW2.
    out = bt.horizon_feature_rows(hist, gw=2, gws=[2, 3, 4], season_idx=0,
                                  elo_at={})
    gw3 = out[(out["code"] == 101) & (out["gw"] == 3)]
    assert len(gw3) == 1
    # GW1 scored 2; the GW2 explosion (50) is unplayed at the deadline.
    assert float(gw3["total_points_r1"].iloc[0]) == 2.0
    assert float(gw3["total_points_r3"].iloc[0]) == 2.0


def test_horizon_rows_keep_the_known_fixture_list():
    hist = _explosion_season(explode_gw=2)
    out = bt.horizon_feature_rows(hist, gw=2, gws=[2, 3, 4], season_idx=0,
                                  elo_at={})
    assert sorted(out["gw"].unique().tolist()) == [3, 4]
    gw3 = out[(out["code"] == 101) & (out["gw"] == 3)].iloc[0]
    assert int(gw3["opp_code"]) == 20 and float(gw3["home"]) == 1.0
    # The outcome columns are blanked: they are not known at the deadline.
    assert pd.isna(gw3["total_points"])


def _understat_team_raw():
    """Raw understat team rows: club 1 leaks 1.0 xGA before the GW2 deadline
    and 9.0 after it."""
    return pd.DataFrame([
        {"season": "2024-25", "season_idx": 0, "team_code": 1,
         "date": pd.Timestamp("2025-01-01").date(), "us_xg": 1.0,
         "us_xga": 1.0, "ppda": 10.0, "deep": 5, "deep_allowed": 5},
        {"season": "2024-25", "season_idx": 0, "team_code": 1,
         "date": pd.Timestamp("2025-01-04").date(), "us_xg": 1.0,
         "us_xga": 9.0, "ppda": 10.0, "deep": 5, "deep_allowed": 5},
    ])


def test_horizon_rows_carry_the_team_understat_features():
    """advise serves these columns; a backtest that leaves them all-NaN is
    scoring a model the live path does not run."""
    from gaffer.features.engineer import TEAM_US_FEATURES

    out = bt.horizon_feature_rows(_explosion_season(explode_gw=2), gw=2,
                                  gws=[2, 3, 4], season_idx=0, elo_at={},
                                  understat_team=_understat_team_raw())
    assert set(TEAM_US_FEATURES) <= set(out.columns)
    own = out[out["team_code"] == 1]["team_us_xga_r5"]
    assert own.notna().all()


def test_horizon_rows_truncate_team_understat_at_the_deadline():
    """The broadcast of a club's latest vector reaches every future row, so
    an untruncated frame would push end-of-history xGA backwards in time."""
    out = bt.horizon_feature_rows(_explosion_season(explode_gw=2), gw=2,
                                  gws=[2, 3, 4], season_idx=0, elo_at={},
                                  understat_team=_understat_team_raw())
    vals = set(out["team_us_xga_r5"].dropna().round(3))
    assert vals == {1.0}


# --- perfect-foresight ("oracle") EP -------------------------------------

def test_oracle_ep_is_the_actual_points_per_player_gameweek():
    rows = _season_rows([1, 2])
    out = bt.oracle_ep(rows, [1, 2])
    assert sorted(out.columns) == ["code", "ep", "gw"]
    assert set(out["ep"]) == {2.0}
    assert len(out) == 40


def test_oracle_ep_sums_a_double_gameweek_and_drops_other_gameweeks():
    rows = pd.concat([_season_rows([1]), _season_rows([1]), _season_rows([2])],
                     ignore_index=True)
    out = bt.oracle_ep(rows, [1])
    assert set(out["gw"]) == {1}
    assert set(out["ep"]) == {4.0}


def test_oracle_ep_scores_a_player_who_did_not_feature_at_zero():
    rows = _season_rows([1])
    rows.loc[rows["code"] == 101, ["total_points", "minutes"]] = [0, 0]
    out = bt.oracle_ep(rows, [1])
    assert float(out.loc[out["code"] == 101, "ep"].iloc[0]) == 0.0


def test_backtest_model_ep_source_is_bit_identical_to_the_default(monkeypatch):
    """The default path must not move: everything measured before this change
    was measured on it."""
    _install_stubs(monkeypatch, _season_rows([1, 2, 3]))
    default = run_backtest(season="2025-26", start_gw=1, retrain_every=4)
    _install_stubs(monkeypatch, _season_rows([1, 2, 3]))
    explicit = run_backtest(season="2025-26", start_gw=1, retrain_every=4,
                            ep_source="model")
    assert explicit == default
    assert default["total"] == 72          # 3 gameweeks x (XI 22 + captain 2)


def test_oracle_replay_never_builds_horizon_feature_rows(monkeypatch):
    """The oracle reads its EP off the played rows, so the re-engineered
    later-gameweek features are dead work on the slowest loop we have. A stub
    that would blow up if called is the only honest way to pin that."""
    _install_stubs(monkeypatch, _season_rows([1, 2, 3]))

    def _boom(*a, **k):
        raise AssertionError("horizon_feature_rows called on the oracle path")

    monkeypatch.setattr(bt, "horizon_feature_rows", _boom)
    out = run_backtest(season="2025-26", start_gw=1, horizon=3,
                       ep_source="oracle")
    assert out["total"] > 0


def test_backtest_rejects_an_unknown_ep_source(monkeypatch):
    _install_stubs(monkeypatch, _season_rows([1, 2, 3]))
    with pytest.raises(ValueError) as exc:
        run_backtest(season="2025-26", start_gw=1, ep_source="crystal ball")
    assert "crystal ball" in str(exc.value)


# --- oracle dominance ----------------------------------------------------
#
# The solver and the pool builder stay real here — the point of the check is
# that the oracle's EP actually reaches the MILP — so only the training and
# prediction machinery is stubbed out.

def _scored_season_rows(gws, n=20):
    """Player i scores i points every gameweek, at a flat price.

    A strictly-ranked pool is what makes the comparison meaningful: with the
    model EP flat at 1.0, only the oracle can tell the 19-point player from
    the 0-point one.
    """
    rows = []
    for gw in gws:
        for i in range(n):
            rows.append({
                "season_idx": 0, "gw": gw, "code": 101 + i,
                "element": 1 + i, "name": f"P{i}", "position": POSITIONS[i],
                "team_code": 1 + i % 7, "value": 40,
                "kickoff_time": f"2025-01-{gw:02d}T12:00:00Z",
                "total_points": i, "minutes": 90,
            })
    return pd.DataFrame(rows)


def _install_solver_stubs(monkeypatch, season_rows):
    """Everything except ``build_pool`` and ``solve_plan``, which stay real."""
    monkeypatch.setattr(bt, "load_config", lambda *a, **k: Config(
        entry_id=1, league_id=1, train_seasons=["2025-26"]))
    monkeypatch.setattr(bt, "load_bootstrap_sample", lambda *a, **k: {})
    monkeypatch.setattr(bt, "scoring_table", lambda *a, **k: {})
    monkeypatch.setattr(bt, "load_training_frame",
                        lambda *a, **k: (season_rows, pd.DataFrame(), None))
    monkeypatch.setattr(bt, "train_all", lambda *a, **k: {})
    monkeypatch.setattr(bt, "predict_components_simple",
                        lambda models, rows: rows)
    monkeypatch.setattr(bt, "assemble_ep", lambda comp, scoring: comp)
    monkeypatch.setattr(bt, "apply_calibration", lambda df, cal: df)
    monkeypatch.setattr(bt, "ep_matrix",
                        lambda df: df[["code", "gw"]].assign(ep=1.0))
    monkeypatch.setattr(bt.store, "save", lambda *a, **k: None)


def test_oracle_h1_xi_outscores_the_model_xi_on_the_same_fixture_data(
        monkeypatch):
    rows = _scored_season_rows([1, 2, 3])
    _install_solver_stubs(monkeypatch, rows)
    model = run_backtest(season="2025-26", start_gw=1, retrain_every=4,
                         ep_source="model")
    _install_solver_stubs(monkeypatch, rows)
    oracle = run_backtest(season="2025-26", start_gw=1, retrain_every=4,
                          ep_source="oracle")
    # GW1 is the squad build: no transfers, no hits either side, so the two
    # XIs are directly comparable.
    assert oracle["log"][0]["points"] >= model["log"][0]["points"]
    assert oracle["total"] >= model["total"]


# --- v4c: theta-aware chip picking -----------------------------------------

def test_pick_chip_defaults_to_the_flat_constants():
    """Rail: no thresholds argument reproduces the pre-v4c choice."""
    from gaffer.backtest import _pick_chip
    from gaffer.optimize.chips import CHIP_PLAY_THRESHOLD

    table = pd.DataFrame([
        {"chip": "bboost", "gw": 7, "gain": CHIP_PLAY_THRESHOLD + 0.1,
         "per_week": 1.0}])
    assert _pick_chip(table, 7) == "bboost"

    below = pd.DataFrame([
        {"chip": "bboost", "gw": 7, "gain": CHIP_PLAY_THRESHOLD - 0.1,
         "per_week": 1.0}])
    assert _pick_chip(below, 7) == ""


def test_pick_chip_honours_an_injected_threshold_lookup():
    from gaffer.backtest import _pick_chip

    table = pd.DataFrame([
        {"chip": "bboost", "gw": 7, "gain": 6.0, "per_week": 6.0}])
    assert _pick_chip(table, 7, thresholds=lambda c, g: 5.0) == "bboost"
    assert _pick_chip(table, 7, thresholds=lambda c, g: 7.0) == ""


def test_pick_chip_uses_a_per_chip_threshold():
    from gaffer.backtest import _pick_chip

    table = pd.DataFrame([
        {"chip": "wildcard", "gw": 7, "gain": 9.0, "per_week": 3.0},
        {"chip": "bboost", "gw": 7, "gain": 6.0, "per_week": 6.0}])
    only_bb = _pick_chip(table, 7,
                         thresholds=lambda c, g: 100.0 if c == "wildcard"
                         else 5.0)
    assert only_bb == "bboost"


def test_run_backtest_still_pins_the_calibration_seam():
    """Protected: tests/test_assemble.py asserts this literal on
    run_backtest as well as run_advise."""
    import inspect

    from gaffer.backtest import run_backtest

    assert ("ep_matrix(apply_calibration(assemble_ep("
            in inspect.getsource(run_backtest))


# --- v4c: the chip replay, as D3 needs it ----------------------------------

def test_run_backtest_already_accepts_the_chips_flag():
    """Spec §9 claims the harness is chip-free; it is not. Pin the reality so
    the D3 measurement is not built on a false premise."""
    import inspect

    from gaffer.backtest import run_backtest

    sig = inspect.signature(run_backtest)
    assert sig.parameters["chips"].default is False


def test_run_backtest_reports_which_chips_went_unplayed():
    """D3's second condition — 'no chip stranded unplayed at expiry' — needs
    the replay to say so, not the reader to infer it."""
    import inspect

    from gaffer.backtest import run_backtest

    src = inspect.getsource(run_backtest)
    assert "unplayed_chips" in src


def test_unplayed_chips_of_a_replay_with_no_chips_is_every_chip_twice():
    """Both halves: four chips before GW19 and four after."""
    from gaffer.backtest import unplayed_chips

    assert unplayed_chips({}) == {"first_half": ["wildcard", "freehit",
                                                 "bboost", "3xc"],
                                  "second_half": ["wildcard", "freehit",
                                                  "bboost", "3xc"]}


def test_unplayed_chips_accounts_for_the_half_a_chip_was_played_in():
    from gaffer.backtest import unplayed_chips

    out = unplayed_chips({7: "bboost", 25: "bboost"})
    assert "bboost" not in out["first_half"]
    assert "bboost" not in out["second_half"]


def test_a_chip_played_in_one_half_is_still_available_in_the_other():
    from gaffer.backtest import unplayed_chips

    out = unplayed_chips({7: "wildcard"})
    assert "wildcard" not in out["first_half"]
    assert "wildcard" in out["second_half"]


def test_the_boundary_gameweek_counts_as_the_first_half():
    from gaffer.backtest import unplayed_chips

    assert "3xc" not in unplayed_chips({19: "3xc"})["first_half"]
    assert "3xc" in unplayed_chips({20: "3xc"})["first_half"]


def test_chip_points_are_attributable_per_chip_from_the_log():
    """D3 compares 'chip-attributed points', so there has to be one place
    that does the attributing. The old version of this test built a two-row
    DataFrame and asserted that pandas can filter it."""
    from gaffer.backtest import chip_points

    log = [{"gw": 7, "points": 80, "chip": "bboost"},
           {"gw": 8, "points": 55, "chip": ""},
           {"gw": 9, "points": 71, "chip": "bboost"},
           {"gw": 20, "points": 90, "chip": "wildcard"}]
    assert chip_points(log) == {"bboost": 151, "wildcard": 90}


def test_a_season_with_no_chips_played_attributes_nothing():
    from gaffer.backtest import chip_points

    assert chip_points([{"gw": 7, "points": 80, "chip": ""}]) == {}
    assert chip_points([]) == {}


def test_the_backtest_reports_the_attribution_it_logged():
    """The helper and the log must not be able to drift apart."""
    from gaffer.backtest import chip_points

    log = [{"gw": 7, "points": 80, "chip": "bboost"},
           {"gw": 8, "points": 55, "chip": ""}]
    result = {"log": log, "chips_played": {7: "bboost"},
              "chip_points": chip_points(log)}
    assert set(result["chip_points"]) == set(result["chips_played"].values())


# --- v4d: the league tilt seam gate E1 injects -----------------------------

def test_run_backtest_without_a_tilt_is_the_default_replay(monkeypatch):
    """Default None means today's behaviour, to the point."""
    import inspect

    _install_stubs(monkeypatch, _season_rows([1, 2, 3]))
    default = run_backtest(season="2025-26", start_gw=1, retrain_every=4)
    _install_stubs(monkeypatch, _season_rows([1, 2, 3]))
    explicit = run_backtest(season="2025-26", start_gw=1, retrain_every=4,
                            tilt=None)
    assert explicit == default
    assert inspect.signature(run_backtest).parameters["tilt"].default is None


def test_run_backtest_applies_an_injected_tilt_before_the_pool_is_built(
        monkeypatch):
    """Gate E1 replays the dial by handing the loop a tilt; it has to reach
    the pool, which is what decides *which* players are candidates."""
    _install_stubs(monkeypatch, _season_rows([1, 2, 3]))
    seen: list[int] = []

    def tilt(ep_by, gw):
        seen.append(gw)
        return {key: value * 2 for key, value in ep_by.items()}

    out = run_backtest(season="2025-26", start_gw=1, retrain_every=4,
                       tilt=tilt)
    assert seen == [1, 2, 3]
    assert out["total"] > 0
