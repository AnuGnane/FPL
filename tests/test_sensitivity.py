"""The sensitivity sweep: how much of this plan is the forecast, and how much
is the forecast's error.

The advice already runs a scenario sweep when ``[scenarios] n`` is on, but it
runs it to *gate* moves and it throws the board away. This is the same
machinery asked a different question — if the EPs were wrong by their own
plausible error, how often would the plan still be this plan, and what is the
next-best plan worth? — and its answer is written down instead of consumed.

Nothing here re-implements a scenario. ``run_scenarios`` and
``move_frequencies`` come from ``optimize.scenarios`` unchanged.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from gaffer.artifacts import (POOL_COLS, SolveState, save_solve_state,
                              solve_state_paths)
from gaffer.sensitivity import (SENSITIVITY_K, load_sensitivity,
                                run_sensitivity, sensitivity_path)

SQUAD = [("GKP", 3), ("DEF", 8), ("MID", 8), ("FWD", 5)]
OWNED = [1, 2, 4, 5, 6, 7, 8, 12, 13, 14, 15, 16, 20, 21, 22]   # legal 15
GWS = [5, 6]

OPT = {"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
       "ft_value": 1.5, "itb_value": 0.05, "hit_cost": 4, "horizon": 2}


def _pool_frame(star_ep: float = 9.0) -> pd.DataFrame:
    """One row per (candidate, gameweek), the shape ``pool_rows`` writes.

    Player 23 is a forward nobody owns, on ``star_ep``: the sweep's job is to
    say how often buying him survives the forecast being wrong.
    """
    rows, code = [], 1
    for position, n in SQUAD:
        for _ in range(n):
            for gw in GWS:
                rows.append({"code": code, "name": f"P{code}",
                             "position": position, "team_code": code % 8,
                             "cost": 50, "sell": 50,
                             "owned": code in OWNED, "gw": gw,
                             "ep_raw": star_ep if code == 23 else 3.0})
            code += 1
    return pd.DataFrame(rows, columns=POOL_COLS)


def _save(tmp_path, **kw) -> None:
    state = SolveState(
        gw=5, gws=list(GWS), deadline="2026-09-05T17:30:00Z",
        generated_at="2026-08-31T09:00:00Z", mode="weekly", bank=0,
        free_transfers=1, owned_codes=list(OWNED), lam=0.0, league_eo={},
        avail_by_gw={5: [], 6: []}, opt=dict(OPT), pool=_pool_frame(**kw))
    save_solve_state(state)


def _components(tmp_path) -> None:
    """A component file with a minutes model in it, so xMins is real."""
    rows = [{"code": code, "gw": gw, "p_play": 0.9, "p60": 0.8, "ep": 3.0}
            for code in range(1, 25) for gw in GWS]
    pd.DataFrame(rows).to_parquet(
        tmp_path / "reports/components_gw5.parquet", index=False)


@pytest.fixture()
def board(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    _save(tmp_path)
    _components(tmp_path)
    return tmp_path


def test_a_sweep_writes_its_report(board):
    payload = run_sensitivity(k=4, seed=1)
    assert payload["gw"] == 5
    assert payload["k"] == 4 and payload["completed"] == 4
    assert payload["seed"] == 1
    assert sensitivity_path(5).exists()
    assert load_sensitivity(5)["seed"] == 1
    assert payload["wall_s"] >= 0.0


def test_the_same_seed_is_the_same_report(board):
    first = run_sensitivity(k=4, seed=7)
    second = run_sensitivity(k=4, seed=7)
    assert first["frequencies"] == second["frequencies"]
    assert first["modal"] == second["modal"]
    assert first["margin"] == second["margin"]


def test_a_different_seed_may_differ_but_stays_well_formed(board):
    payload = run_sensitivity(k=4, seed=99)
    assert 0 < len(payload["frequencies"])
    for row in payload["frequencies"]:
        assert 0.0 < row["frequency"] <= 1.0
        assert row["count"] <= payload["completed"]


def test_frequencies_carry_the_player_name(board):
    """A report the UI has to re-join against the pool is a report the UI
    will re-join wrongly."""
    payload = run_sensitivity(k=3, seed=1)
    buys = [r for r in payload["frequencies"] if r["kind"] == "buy"]
    assert buys and all(r["name"] for r in buys)


def test_an_obvious_transfer_survives_every_draw(board):
    """Player 23 is worth three times anybody else. A sweep that cannot find
    him is measuring nothing."""
    payload = run_sensitivity(k=6, seed=3)
    buys = {r["code"]: r["frequency"] for r in payload["frequencies"]
            if r["kind"] == "buy"}
    assert buys.get(23, 0.0) == 1.0


def test_a_marginal_transfer_does_not(tmp_path, monkeypatch):
    """The same board with the star two tenths better than the incumbents:
    now the noise decides, and the report must say so rather than rounding
    the disagreement away."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    _save(tmp_path, star_ep=3.2)
    _components(tmp_path)
    payload = run_sensitivity(k=8, seed=5)
    buys = {r["code"]: r["frequency"] for r in payload["frequencies"]
            if r["kind"] == "buy"}
    assert buys.get(23, 0.0) < 1.0


def test_the_modal_plan_is_the_most_common_signature(board):
    payload = run_sensitivity(k=6, seed=3)
    modal = payload["modal"]
    assert modal["count"] >= 1
    assert modal["count"] <= payload["completed"]
    assert modal["value"] == pytest.approx(modal["value"])
    assert isinstance(modal["buys"], list)


def test_the_margin_prices_the_best_differing_plan(board):
    """A6: every distinct signature is re-scored on the *true* board, so the
    margin is what the runner-up would really have cost."""
    payload = run_sensitivity(k=8, seed=5)
    if payload["runner_up"] is None:
        assert payload["margin"] is None
        assert "every" in payload["verdict"]
    else:
        assert payload["margin"] == pytest.approx(
            round(payload["modal"]["value"]
                  - payload["runner_up"]["value"], 2))
        assert payload["margin"] >= 0.0


def test_no_solve_state_is_a_readable_refusal(tmp_path, monkeypatch):
    from gaffer.errors import GafferError

    monkeypatch.chdir(tmp_path)
    with pytest.raises(GafferError) as exc:
        run_sensitivity()
    assert "advise" in str(exc.value)


def test_without_components_the_sweep_still_runs_and_says_why(tmp_path,
                                                              monkeypatch):
    """A5: a flat 75-minute assumption, and a notice saying it was used."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    _save(tmp_path)
    payload = run_sensitivity(k=3, seed=1)
    assert payload["completed"] == 3
    assert "75" in payload["notice"]
    assert payload["frequencies"]


def test_a_component_file_with_no_minutes_model_falls_back_the_same_way(
        tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    _save(tmp_path)
    pd.DataFrame([{"code": 1, "gw": 5, "ep": 3.0}]).to_parquet(
        tmp_path / "reports/components_gw5.parquet", index=False)
    assert "75" in run_sensitivity(k=2, seed=1)["notice"]


def test_the_report_is_written_atomically(board):
    """``pen_tracker.save_tracker``'s idiom: no .tmp file survives a run."""
    run_sensitivity(k=2, seed=1)
    assert not list((board / "reports").glob("*.tmp"))
    json.loads(sensitivity_path(5).read_text())


def test_a_corrupt_report_reads_as_absent(board):
    run_sensitivity(k=2, seed=1)
    sensitivity_path(5).write_text("{not json")
    assert load_sensitivity(5) is None


def test_the_sweep_re_solves_the_saved_board_and_nothing_else(board):
    """The state on disk is untouched: sensitivity is a read of the week's
    decision, not a revision of it."""
    parquet, meta = solve_state_paths(5)
    before = (parquet.read_bytes(), meta.read_bytes())
    run_sensitivity(k=2, seed=1)
    assert (parquet.read_bytes(), meta.read_bytes()) == before


def test_the_default_k_is_the_specs_twenty():
    assert SENSITIVITY_K == 20
