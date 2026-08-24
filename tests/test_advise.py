import pandas as pd
from gaffer.advise import (Advice, chips_available_for, future_fixture_frame,
                           transfer_tag)


def test_future_fixture_frame_one_row_per_player_fixture():
    fixtures = pd.DataFrame([
        {"gw": 2, "home_id": 1, "away_id": 2, "kickoff_time": "2026-08-28T19:00:00Z"},
        {"gw": 3, "home_id": 2, "away_id": 1, "kickoff_time": "2026-09-04T19:00:00Z"},
    ])
    players = pd.DataFrame([
        {"code": 10, "element": 5, "name": "A", "position": "MID",
         "team_id": 1, "team_code": 100},
        {"code": 11, "element": 6, "name": "B", "position": "DEF",
         "team_id": 2, "team_code": 200},
    ])
    teams = pd.DataFrame([{"team_id": 1, "code": 100}, {"team_id": 2, "code": 200}])
    ff = future_fixture_frame(fixtures, players, teams, gws=[2, 3],
                              season_idx=4)
    assert len(ff) == 4                       # 2 players x 2 fixtures
    row = ff[(ff.code == 10) & (ff.gw == 2)].iloc[0]
    assert row["was_home"] == True and row["opp_code"] == 200
    row3 = ff[(ff.code == 10) & (ff.gw == 3)].iloc[0]
    assert row3["was_home"] == False


def test_chips_available_for_splits_the_season_in_halves():
    used = {3: "wildcard", 8: "3xc", 25: "bboost"}
    # First half: the two chips already played in GW3/GW8 are gone, the rest
    # remain — a second-half chip does not consume a first-half one.
    assert chips_available_for(used, 10) == ["freehit", "bboost"]
    # Boundary: GW19 is still the first half, GW20 is the second.
    assert chips_available_for(used, 19) == ["freehit", "bboost"]
    # Second half: the first-half chips are back, only GW25's bboost is spent.
    assert chips_available_for(used, 20) == ["wildcard", "freehit", "3xc"]


def _bare_advice(**kw):
    """Minimal Advice with every positional field filled — the two league
    fields must be optional, so a caller that knows nothing about the league
    can still build one."""
    base = dict(
        gw=3, deadline="2026-09-04T17:30:00Z", buys=[], sells=[], hits=0,
        xi=[], bench=[], captain={}, vice={}, captain_options=[],
        chip_table=[], wildcard_now=None, alternatives=[], threats=[],
        price_alerts=[], expected_pts=0.0)
    return Advice(**{**base, **kw})


def test_advice_carries_strategy_and_win_probs_with_safe_defaults():
    a = _bare_advice()
    assert a.strategy is None
    assert a.win_probs == []
    # Default list is per-instance, not shared class state.
    a.win_probs.append({"name": "x"})
    assert _bare_advice().win_probs == []


def test_transfer_tag_splits_differentials_from_cover():
    # No strategy (no league, or the league fetch failed): no tags at all,
    # including for players nobody in the league owns.
    assert transfer_tag(None, False) == ""
    assert transfer_tag(2.0, False) == ""
    # With a strategy: EO is a percent, the thresholds are fractions.
    assert transfer_tag(None, True) == "attack"      # unowned -> 0% -> attack
    assert transfer_tag(0.0, True) == "attack"
    assert transfer_tag(29.9, True) == "attack"
    assert transfer_tag(30.0, True) == ""            # boundary: no longer a diff
    assert transfer_tag(69.9, True) == ""
    assert transfer_tag(70.0, True) == "cover"       # boundary: cover starts here
    assert transfer_tag(140.0, True) == "cover"      # captaincy pushes EO > 100


def test_run_advise_tilts_ep_before_building_the_candidate_pool():
    """Source-level seam (no cheap end-to-end harness for run_advise): the
    league fetch has to happen before the pool is built, because the tilt
    shapes *which* players become candidates, not just which get picked."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    league = src.index("fetch_rival_entries(")
    tilt = src.index("tilt_ep(")
    pool = src.index("pool = build_pool(")
    assert league < tilt < pool
    assert "compute_strategy(" in src
    assert src.index("compute_strategy(") < pool
    # Any league failure degrades to no strategy; the solve is then identical
    # to v1 because tilt_ep(..., 0.0) is an exact passthrough.
    assert "except Exception" in src
    assert 'summary_overall_points' in src
    # The pool eats the tilted values; nothing else does.
    assert "build_pool(players, pool_ep," in src


def test_run_advise_reports_raw_ep_not_the_tilted_values():
    """Every table in the report shows real expected points. The tilt exists
    to steer the optimizer, and would be a lie on a printed xPts column."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    assert "ep_named = ep.merge(" in src          # built from the raw frame
    assert "ep_gw1 = ep_named[ep_named[\"gw\"] == gw]" in src
    assert "pool_ep" not in src[src.index("ep_gw1 ="):]
    # _named renders from ep_by, the untilted dict.
    assert "_named(first.xi, name_of, ep_by, gw)" in src


# --- GW1 initial squad ------------------------------------------------------


def test_advice_defaults_to_weekly_mode_and_accepts_initial_squad():
    """``mode`` is appended last and defaulted, so every existing positional
    construction and every advice JSON written before it still loads."""
    assert _bare_advice().mode == "weekly"
    assert _bare_advice(mode="initial_squad").mode == "initial_squad"


def test_initial_squad_state_is_an_empty_squad_on_the_full_budget():
    from gaffer.advise import initial_squad_state

    state, picks = initial_squad_state([1, 2, 3])
    assert state.owned_codes == []
    assert state.bank == 1000                  # 100.0m, in 0.1m units
    assert state.free_transfers == 15          # building 15 costs no hits
    assert state.gws == [1, 2, 3]
    # build_pool only reads code/sell; an empty frame with those columns keeps
    # the "owned" set empty and every sell price at now_cost.
    assert list(picks.columns) == ["code", "sell"]
    assert picks.empty


def test_initial_squad_solve_buys_fifteen_and_takes_no_hits():
    """With nothing owned the first gw plan's buys *are* the squad, its sells
    are empty, and 15 free transfers make the hit count zero."""
    from gaffer.advise import initial_squad_state
    from gaffer.optimize.milp import solve_plan

    rows, code = [], 1
    for pos, n in [("GKP", 2), ("DEF", 6), ("MID", 7), ("FWD", 5)]:
        for _ in range(n):
            rows.append({"code": code, "position": pos, "team_code": code % 8,
                         "cost": 50, "sell": 50, "ep": {1: 2.0}})
            code += 1
    pool = pd.DataFrame(rows)

    state, _ = initial_squad_state([1])
    first = solve_plan(pool, state, decay=0.85, bench_weight=0.1,
                       vice_weight=0.1, ft_value=1.5, itb_value=0.05,
                       hit_cost=4).gw_plans[0]
    assert sorted(first.buys) == sorted(first.squad)
    assert len(first.buys) == 15
    assert first.sells == []
    assert first.hits == 0


def test_run_advise_falls_back_to_initial_squad_advice_at_gw1():
    """Source-level seam (no cheap end-to-end harness for run_advise): the
    GW1 GafferError out of fetch_my_team must become initial-squad advice
    rather than propagating to the CLI as a clean exit."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    fetch = src.index("fetch_my_team(")
    caught = src.index("except GafferError", fetch)
    assert caught - fetch < 200                # the try wraps *that* call
    assert "my = None" in src[caught:caught + 200]
    assert "initial_squad_state(gws)" in src
    assert '"initial_squad"' in src
    # Everything downstream that reads the squad has to be guarded.
    for ref in ["my.picks", "my.bank", "my.free_transfers", "my.chips_by_gw"]:
        i = src.index(ref)
        before = src[max(0, i - 400):i]
        assert "my is None" in before or "my is not None" in before, ref


def test_run_advise_only_tags_buys_when_league_ownership_is_known():
    """At GW1 no rival picks are public, so the EO map is empty. An empty map
    means "unknown", and must not tag every opening pick as a differential."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    assert "strat is not None and bool(league_eo)" in src
