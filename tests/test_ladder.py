"""v13 §3 — the transfer ladder's arithmetic, on a hand-built saved state."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from gaffer.artifacts import SolveState, pool_rows, save_solve_state

OWNED = [1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 16, 17, 18]


def _pool_frame():
    rows, code = [], 1
    for pos, n in [("GKP", 2), ("DEF", 6), ("MID", 7), ("FWD", 5)]:
        for _ in range(n):
            rows.append({"code": code, "position": pos,
                         "team_code": code % 8, "cost": 50, "sell": 50})
            code += 1
    return pd.DataFrame(rows)


def save_state(opt_extra=None, star=9.0, second=7.0, gws=(1, 2)):
    """Code 20 is worth a free transfer, code 19 is worth a hit (5 EP/GW over
    two weeks against a 4-point hit), nothing else moves."""
    frame = _pool_frame()
    players = pd.DataFrame({"code": frame["code"],
                            "name": [f"P{c}" for c in frame["code"]]})
    ep = {20: star, 19: second}
    ep_by = {(int(c), g): ep.get(int(c), 2.0)
             for c in frame["code"] for g in gws}
    save_solve_state(SolveState(
        gw=gws[0], gws=list(gws), deadline="2026-09-11T17:30:00Z",
        generated_at="2026-09-10T09:00:00Z", mode="weekly", bank=0,
        free_transfers=1, owned_codes=list(OWNED), lam=0.0, league_eo={},
        avail_by_gw={g: [] for g in gws},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.5, "itb_value": 0.05, "hit_cost": 4,
             "horizon": len(gws), **(opt_extra or {})},
        pool=pool_rows(frame, players, OWNED, ep_by, list(gws))))
    return ep_by


@pytest.fixture()
def board(tmp_path, monkeypatch):
    """The saved board, with the serve-time config cache dropped either side.

    ``build_ladder`` now reads the *live* caps through ``serving_config``,
    which is cached for the life of the process: without these the ladder
    would answer with whatever config the last test's directory held."""
    from gaffer.config import serving_config

    monkeypatch.chdir(tmp_path)
    serving_config.cache_clear()
    yield save_state({"max_hits": 2, "max_transfers": 15})
    serving_config.cache_clear()


def _zero_noise(monkeypatch):
    from gaffer import ladder

    monkeypatch.setattr(ladder, "OUTCOME_VAR_PER_EP", 0.0)
    monkeypatch.setattr(ladder, "sigma_table", lambda gw: ({}, "outcome_only"))


def test_with_no_noise_every_probability_is_zero_or_one_and_mean_is_horizon(
        board, monkeypatch):
    from gaffer.ladder import build_ladder

    _zero_noise(monkeypatch)
    out = build_ladder(1, n_draws=25, seed=1)
    distinct = [r for r in out["rungs"] if r["same_as"] is None]
    assert len(distinct) >= 2
    for r in distinct:
        # No clip and no noise: every draw *is* the horizon points, exactly.
        assert r["mean_pts"] == r["horizon_pts"]
        assert r["p10_pts"] == r["mean_pts"] == r["p90_pts"]
        for key in ("p_beats_bank", "p_beats_top"):
            assert r[key] in (None, 0.0, 1.0)
    assert out["sigma_source"] == "outcome_only"


def test_the_mean_tracks_the_horizon_points_under_real_noise(board):
    """F3 — with the clip gone the draws are unbiased, so the Monte Carlo
    mean sits on the deterministic horizon points."""
    from gaffer.ladder import build_ladder

    out = build_ladder(1, n_draws=2000, seed=5)
    distinct = [r for r in out["rungs"] if r["same_as"] is None]
    assert len(distinct) >= 2
    for r in distinct:
        assert abs(r["mean_pts"] - r["horizon_pts"]) < 1.0


def test_the_hit_numbers_split_into_first_week_and_horizon(board):
    """F1 — ``hits``/``cost`` are the first week's, ``horizon_hits``/
    ``horizon_cost`` span the horizon, and ``vs_below`` prints both."""
    from gaffer.ladder import build_ladder

    out = build_ladder(1, n_draws=25, seed=1)
    by = {r["key"]: r for r in out["rungs"]}
    distinct = [r for r in out["rungs"] if r["same_as"] is None]
    prev = None
    for r in distinct:
        assert r["horizon_hits"] >= r["hits"]
        assert r["horizon_hits"] == sum(w["hits"] for w in r["plan_by_gw"])
        assert r["cost"] == r["hits"] * 4
        assert r["horizon_cost"] == r["horizon_hits"] * 4
        if prev is not None:
            below = r["vs_below"]
            assert below["delta_cost"] == \
                (r["horizon_hits"] - prev["horizon_hits"]) * 4
            assert below["delta_cost_now"] == (r["hits"] - prev["hits"]) * 4
        prev = r
    # A collapsed row copies the source's four numbers.
    for key in ("hits2", "hits3"):
        for field in ("hits", "cost", "horizon_hits", "horizon_cost"):
            assert by[key][field] == by["hits1"][field]


def test_the_rungs_come_in_ladder_order_and_coincident_ones_say_so(board):
    from gaffer.ladder import build_ladder

    out = build_ladder(1, n_draws=25, seed=1)
    keys = [r["key"] for r in out["rungs"]]
    assert keys[:5] == ["bank", "hits0", "hits1", "hits2", "hits3"]
    by = {r["key"]: r for r in out["rungs"]}
    assert by["bank"]["transfers"] == 0 and by["bank"]["p_beats_bank"] is None
    assert [b["code"] for b in by["hits0"]["plan_by_gw"][0]["buys"]] == [20]
    assert sorted(b["code"] for b in by["hits1"]["plan_by_gw"][0]["buys"]) \
        == [19, 20]
    assert by["hits1"]["hits"] == 1 and by["hits1"]["cost"] == 4
    # Nothing is worth a second hit, so the two upper rungs collapse onto
    # hits1 and carry no numbers of their own.
    assert by["hits2"]["same_as"] == "hits1"
    assert by["hits3"]["same_as"] == "hits1"
    assert by["hits3"]["mean_pts"] is None and by["hits3"]["plan_by_gw"] == []
    assert "open" not in keys


def test_p_best_sums_to_one_over_the_distinct_rungs(board):
    from gaffer.ladder import build_ladder

    out = build_ladder(1, n_draws=40, seed=3)
    distinct = [r for r in out["rungs"] if r["same_as"] is None]
    assert sum(r["p_best"] for r in distinct) == pytest.approx(1.0, abs=1e-6)
    for r in distinct:
        for key in ("p_beats_bank", "p_beats_top", "p_best"):
            assert r[key] is None or 0.0 <= r[key] <= 1.0


def test_the_cap_rung_and_the_recommended_rung(board, monkeypatch):
    """cap_rung follows the saved caps; recommended matches the served
    advice's first-week buys, sells and captain when an advice is on disk."""
    import json
    from pathlib import Path

    from gaffer.ladder import build_ladder

    out = build_ladder(1, n_draws=10, seed=1)
    assert out["cap"] == {"max_hits": 2, "max_transfers": None}
    assert out["cap_rung_requested"] == "hits2"
    assert out["cap_rung"] == "hits1"     # hits2 collapses onto it (F4)
    assert out["cap_note"] is None
    assert out["recommended"] is None          # no gw1-advice.json yet
    assert out["recommended_note"] == "no served advice for GW1"

    hits1 = next(r for r in out["rungs"] if r["key"] == "hits1")
    first = hits1["plan_by_gw"][0]
    Path("reports").mkdir(exist_ok=True)
    Path("reports/gw1-advice.json").write_text(json.dumps({
        "buys": [{"code": 999}], "sells": [], "captain": {"code": 999}}))
    gated = build_ladder(1, n_draws=10, seed=1)
    assert gated["recommended"] is None
    assert gated["recommended_note"] == \
        "the served advice was sweep-gated to a plan no rung solves for"

    Path("reports/gw1-advice.json").write_text(json.dumps({
        "buys": [{"code": b["code"]} for b in first["buys"]],
        "sells": [{"code": s["code"]} for s in first["sells"]],
        "captain": {"code": first["captain"]["code"]}}))
    matched = build_ladder(1, n_draws=10, seed=1)
    assert matched["recommended"] == "hits1"
    assert matched["recommended_note"] is None


def test_a_cap_on_a_collapsed_rung_resolves_to_the_row_with_the_numbers(
        tmp_path, monkeypatch):
    """F4 — a cap of three hits names a row the solver would not fill."""
    from gaffer.ladder import build_ladder

    from gaffer import config

    monkeypatch.chdir(tmp_path)
    save_state({"max_hits": 3, "max_transfers": 15})
    monkeypatch.setattr(config, "serving_config",
                        lambda: SimpleNamespace(max_hits=3, max_transfers=15))
    out = build_ladder(1, n_draws=10, seed=1)
    assert out["cap_rung_requested"] == "hits3"
    assert out["cap_rung"] == "hits1"
    by = {r["key"]: r for r in out["rungs"]}
    assert by[out["cap_rung"]]["mean_pts"] is not None


def test_a_transfer_cap_with_no_rung_of_its_own_gets_a_note(tmp_path,
                                                            monkeypatch):
    """F7 — no rung models ``max_transfers`` in 1..14."""
    from gaffer.ladder import build_ladder

    from gaffer import config

    monkeypatch.chdir(tmp_path)
    save_state({"max_hits": 2, "max_transfers": 2})
    monkeypatch.setattr(config, "serving_config",
                        lambda: SimpleNamespace(max_hits=2, max_transfers=2))
    out = build_ladder(1, n_draws=10, seed=1)
    assert out["cap_note"] == ("a transfer cap of 2 has no rung of its own; "
                               "the highlight follows the hit cap")


def test_a_bank_cap_and_an_uncapped_state_pick_their_rungs(tmp_path,
                                                            monkeypatch):
    from gaffer.ladder import build_ladder

    from gaffer import config

    monkeypatch.chdir(tmp_path)
    save_state({"max_hits": 15, "max_transfers": 0})
    monkeypatch.setattr(config, "serving_config",
                        lambda: SimpleNamespace(max_hits=15, max_transfers=0))
    assert build_ladder(1, n_draws=10, seed=1)["cap_rung"] == "bank"
    save_state({})
    monkeypatch.setattr(config, "serving_config",
                        lambda: SimpleNamespace(max_hits=15, max_transfers=15))
    out = build_ladder(1, n_draws=10, seed=1)
    assert out["cap"] == {"max_hits": None, "max_transfers": None}
    assert [r["key"] for r in out["rungs"]][-1] == "hits3"
    assert out["cap_rung_requested"] == "hits3"     # the top row on offer
    assert out["cap_rung"] == "hits1"               # which collapses onto this


def test_no_saved_state_is_a_gaffer_error(tmp_path, monkeypatch):
    from gaffer.errors import GafferError
    from gaffer.ladder import build_ladder

    monkeypatch.chdir(tmp_path)
    with pytest.raises(GafferError, match="gaffer advise"):
        build_ladder()


def test_a_full_band_table_is_sigma_source_bands(board, monkeypatch):
    """F8 — every needed cell had a band σ, so nothing fell back."""
    from gaffer import ladder

    full = {(c, g): 2.0 for c in range(1, 21) for g in (1, 2)}
    monkeypatch.setattr(ladder, "sigma_table", lambda gw: (full, "bands"))
    out = ladder.build_ladder(1, n_draws=20, seed=1)
    assert out["sigma_source"] == "bands" and out["sigma_fallbacks"] == 0

    monkeypatch.setattr(ladder, "sigma_table", lambda gw: ({(1, 1): 2.0},
                                                           "bands"))
    partial = ladder.build_ladder(1, n_draws=20, seed=1)
    assert partial["sigma_source"] == "bands+outcome"
    assert partial["sigma_fallbacks"] > 0


def test_a_nan_sigma_banks_nulls_rather_than_raising(board, monkeypatch):
    """F5 — a non-finite number anywhere used to abort ``save_ladder``."""
    from gaffer import ladder

    nan = {(c, g): float("nan") for c in range(1, 21) for g in (1, 2)}
    monkeypatch.setattr(ladder, "sigma_table", lambda gw: (nan, "bands"))
    out = ladder.build_ladder(1, n_draws=20, seed=1)
    reloaded = ladder.load_ladder(1)
    assert reloaded is not None and reloaded == out
    distinct = [r for r in reloaded["rungs"] if r["same_as"] is None]
    assert distinct and all(r["mean_pts"] is None for r in distinct)
    assert all(r["horizon_pts"] is not None for r in distinct)


def test_a_rung_that_will_not_solve_is_dropped_with_a_note(board, monkeypatch):
    """F9 — one bad solve costs its row, not the ladder."""
    from gaffer import ladder

    real, seen = ladder.solve_plan, []

    def flaky(pool, solve_state, **kw):
        seen.append(solve_state)
        if len(seen) == 3:                      # the hits1 spec
            raise RuntimeError("no feasible plan")
        return real(pool, solve_state, **kw)

    monkeypatch.setattr(ladder, "solve_plan", flaky)
    out = ladder.build_ladder(1, n_draws=10, seed=1)
    keys = [r["key"] for r in out["rungs"]]
    assert "hits1" not in keys and "bank" in keys and "hits0" in keys
    assert any("hits1" in note for note in out["notes"])


def test_the_default_seed_is_the_offset_arithmetic(board, monkeypatch):
    from gaffer import config, ladder

    monkeypatch.setattr(config, "serving_config",
                        lambda: SimpleNamespace(scenarios_seed=7))
    out = ladder.build_ladder(1, n_draws=5)
    assert out["seed"] == 7 + ladder.SEED_OFFSET + 1


def test_the_collapse_scans_every_distinct_rung_not_just_the_last():
    """F6 — a rung that repeats an *earlier* distinct rung says so."""
    from gaffer.ladder import collapse

    def plan(buys, sells, captain):
        first = SimpleNamespace(buys=buys, sells=sells, captain=captain)
        return SimpleNamespace(gw_plans=[first])

    a, b = plan([], [], 1), plan([2], [3], 1)
    solved = [("bank", a), ("hits0", b), ("hits1", a)]
    distinct, same_as = collapse(solved)
    assert [k for k, _ in distinct] == ["bank", "hits0"]
    assert same_as == {"hits1": "bank"}


def test_two_rungs_share_the_draw_for_a_player_they_both_field(board):
    """End to end: one ``draw_points`` output, and the shared player's
    contribution to each rung's score is the same vector."""
    from gaffer.ladder import build_ladder, draw_points, score_plan

    out = build_ladder(1, n_draws=20, seed=1)
    by = {r["key"]: r for r in out["rungs"]}
    left, right = by["hits0"], by["hits1"]

    def weeks(row):
        return [SimpleNamespace(gw=w["gw"],
                                xi=[p["code"] for p in w["xi"]],
                                captain=w["captain"]["code"],
                                hits=w["hits"]) for w in row["plan_by_gw"]]

    def drop(plans, code, gw):
        return [SimpleNamespace(gw=w.gw, hits=w.hits, captain=w.captain,
                                xi=[c for c in w.xi
                                    if not (c == code and w.gw == gw)])
                for w in plans]

    lp, rp = weeks(left), weeks(right)
    ep_by, keys = {}, set()
    for row in (left, right):
        for week in row["plan_by_gw"]:
            for ref in week["xi"] + [week["captain"]]:
                ep_by[(ref["code"], week["gw"])] = ref["ep"]
                keys.add((ref["code"], week["gw"]))
    draws = draw_points(keys, ep_by, {}, np.random.default_rng(99), 20)

    gw = lp[0].gw
    shared = sorted(set(lp[0].xi) & set(rp[0].xi)
                    - {lp[0].captain, rp[0].captain})
    assert shared, "the two rungs should field players in common"
    code = shared[0]
    kw = dict(draws=draws, hit_cost=4, n_draws=20)
    left_delta = score_plan(lp, **kw) - score_plan(drop(lp, code, gw), **kw)
    right_delta = score_plan(rp, **kw) - score_plan(drop(rp, code, gw), **kw)
    shared_draw = draws[(code, gw)]
    assert left_delta == pytest.approx(shared_draw, abs=1e-9)
    assert right_delta == pytest.approx(left_delta, abs=1e-9)


def test_the_seed_reproduces_the_payload(board):
    from gaffer.ladder import build_ladder

    a = build_ladder(1, n_draws=30, seed=11)
    b = build_ladder(1, n_draws=30, seed=11)
    for payload in (a, b):
        payload.pop("generated_at"), payload.pop("wall_s")
    assert a == b


def test_the_payload_is_banked_and_reloads(board):
    from gaffer.ladder import build_ladder, ladder_path, load_ladder

    out = build_ladder(1, n_draws=10, seed=1)
    assert ladder_path(1).exists()
    assert load_ladder(1)["rungs"][0]["key"] == out["rungs"][0]["key"]
    assert load_ladder(7) is None


def test_score_plan_uses_one_shared_draw_per_player_week():
    from gaffer.ladder import score_plan

    draws = {(1, 1): np.array([3.0, 5.0]), (2, 1): np.array([1.0, 2.0])}
    plan = SimpleNamespace(gw=1, xi=[1, 2], captain=1, hits=1)
    a = score_plan([plan], draws, hit_cost=4, n_draws=2)
    b = score_plan([plan], draws, hit_cost=4, n_draws=2)
    # XI 4/7, captain again 3/5, minus one hit: 3 and 8, identically twice.
    assert a.tolist() == [3.0, 8.0] and b.tolist() == a.tolist()


def test_p_best_splits_ties():
    from gaffer.ladder import p_best

    shares = p_best({"a": np.array([1.0, 2.0]), "b": np.array([1.0, 1.0])})
    assert shares == {"a": 0.75, "b": 0.25}


def test_vs_below_is_set_arithmetic_on_the_first_week():
    from gaffer.ladder import vs_below

    meta = {19: {"name": "P19", "position": "FWD"},
            20: {"name": "P20", "position": "FWD"},
            16: {"name": "P16", "position": "FWD"},
            17: {"name": "P17", "position": "FWD"}}
    ep_by = {(19, 1): 7.0, (20, 1): 9.0, (16, 1): 2.0, (17, 1): 2.0}
    below = SimpleNamespace(gw=1, buys=[20], sells=[16], hits=0)
    rung = SimpleNamespace(gw=1, buys=[19, 20], sells=[16, 17], hits=1)
    out = vs_below(below, rung, prev_mean=100.0, mean=103.5, hit_cost=4,
                   meta=meta, ep_by=ep_by, below_horizon_hits=0,
                   horizon_hits=3)
    assert [p["code"] for p in out["extra_buys"]] == [19]
    assert [p["code"] for p in out["extra_sells"]] == [17]
    assert out["dropped_buys"] == [] and out["dropped_sells"] == []
    assert out["delta_mean_pts"] == 3.5
    # The horizon difference is what the extra appetite really costs; the
    # first week's is `delta_cost_now`.
    assert out["delta_cost"] == 12 and out["delta_cost_now"] == 4


# --- The final-review pass: live caps, a dropped cap rung, a dropped bank ---


def _cfg(max_hits=2, max_transfers=15):
    return SimpleNamespace(max_hits=max_hits, max_transfers=max_transfers,
                           scenarios_seed=0)


def test_the_cap_comes_from_the_live_config_not_the_saved_state(board,
                                                                monkeypatch):
    """A cap changed through Settings moves the highlight now, not at the
    next `gaffer advise`: the state was solved under `max_hits=2`, the live
    config says one, and the payload says one."""
    from gaffer import config, ladder

    monkeypatch.setattr(config, "serving_config", lambda: _cfg(max_hits=1))
    out = ladder.build_ladder(1, n_draws=10, seed=1)
    assert out["cap"] == {"max_hits": 1, "max_transfers": None}
    assert out["cap_source"] == "config"
    assert out["cap_rung_requested"] == "hits1"


def test_an_unreadable_config_falls_back_to_the_states_caps(board,
                                                            monkeypatch):
    from gaffer import config, ladder

    def boom():
        raise RuntimeError("no config here")

    monkeypatch.setattr(config, "serving_config", boom)
    out = ladder.build_ladder(1, n_draws=10, seed=1)
    assert out["cap"] == {"max_hits": 2, "max_transfers": None}
    assert out["cap_source"] == "state"


def test_a_cap_naming_a_dropped_rung_falls_back_to_the_one_below(board,
                                                                  monkeypatch):
    """The `hits2` solve fails, so the cap of two names a key no row has;
    the highlight drops to the highest rung at or below it that is there."""
    from gaffer import config, ladder

    monkeypatch.setattr(config, "serving_config", lambda: _cfg(max_hits=2))
    real = ladder.solve_plan

    def flaky(pool, solve_state, **kw):
        if getattr(solve_state, "max_hits", None) == 2:
            raise RuntimeError("no feasible plan")
        return real(pool, solve_state, **kw)

    monkeypatch.setattr(ladder, "solve_plan", flaky)
    out = ladder.build_ladder(1, n_draws=10, seed=1)
    assert "hits2" not in [r["key"] for r in out["rungs"]]
    assert out["cap_rung_requested"] == "hits2"
    assert out["cap_rung"] == "hits1"


def test_a_dropped_bank_rung_blanks_p_beats_bank_instead_of_crashing(
        board, monkeypatch):
    from gaffer import config, ladder

    monkeypatch.setattr(config, "serving_config", lambda: _cfg())
    real = ladder.solve_plan

    def flaky(pool, solve_state, **kw):
        if getattr(solve_state, "max_transfers", None) == 0:
            raise RuntimeError("no feasible plan")
        return real(pool, solve_state, **kw)

    monkeypatch.setattr(ladder, "solve_plan", flaky)
    out = ladder.build_ladder(1, n_draws=10, seed=1)
    assert "bank" not in [r["key"] for r in out["rungs"]]
    assert all(r["p_beats_bank"] is None for r in out["rungs"])
    assert any("bank" in note for note in out["notes"])


def test_the_cap_note_reads_its_sentinel_from_the_config(board):
    from gaffer.config import NO_CAP
    from gaffer.ladder import _cap_note

    assert _cap_note(NO_CAP) is None
    assert _cap_note(NO_CAP - 1) is not None
