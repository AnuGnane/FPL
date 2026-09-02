"""v10's degradation rails (gate G4).

Every rail here is a state a real machine reaches: a provider whose host is
down, a second provider that parses into nonsense, an optimizer handed a
p_play column that is all one number, an arm driver whose two arms are the
same arm.

The most valuable assertion in the file is
``test_a_uniform_p_play_builds_character_identically_the_same_problem``.
Everything about §F1 is *relative* — which sub comes on first, how fragile
this XI is against the population, how likely the captain is to leave the
armband unused — and a column with no spread in it answers none of those. Fed
through the arithmetic anyway it would shift the bench block against the XI
block by a constant nobody chose, and the failure would not be a crash: it
would be a squad, every week, slightly wrong for a reason no rail could name.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib.util
import inspect
import json
import textwrap
from pathlib import Path

import httpx
import pandas as pd
import pytest

import gaffer.optimize.milp as milp
from gaffer.config import DEFAULT_LINEUP_PROVIDERS, Config, lineup_providers
from gaffer.data.news.lineups import (LINEUP_COLS, PROVIDERS, Provider,
                                      ROTOWIRE_URL, fetch_lineups)
from gaffer.evaluation import score_news_shadow
from gaffer.news_shadow import SHADOW_COLS
from gaffer.optimize.milp import (BENCH_SLOTS, DEFAULT_BENCH_CURVE,
                                  FRAILTY_CLAMP, KEEPER_DNP, POPULATION_DNP,
                                  SolveInput, _frailty, solve_plan)
from gaffer.web.app import create_app
from gaffer.web.job_kinds import JOB_KINDS


# --- Block 1: §F2a, provider degradation ---------------------------------

def _players() -> pd.DataFrame:
    return pd.DataFrame({
        "code": [100, 101, 102],
        "name": ["Bukayo Saka", "Gabriel Magalhaes", "Declan Rice"],
        "team_code": [3, 3, 3], "starts": [20, 20, 20],
        "status": ["a", "a", "a"], "chance_of_playing": [None, None, None]})


def _teams() -> pd.DataFrame:
    return pd.DataFrame({"code": [3], "name": ["Arsenal"],
                         "short_name": ["ARS"]})


FFS_HTML = ('<h2>Arsenal</h2><ul class="row-1">'
            '<li title="Saka (Bukayo)">'
            '<img src="/photos/players/110x140/100.png"></li>'
            '<li title="Rice (Declan)">'
            '<img src="/photos/players/110x140/102.png"></li></ul>'
            '<strong>Out:</strong><ul class="players">'
            '<li>Gabriel Magalhaes</li></ul>')


def _client(calls: list[str], mapping: dict[str, str]):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        for key, body in mapping.items():
            if key in url:
                return httpx.Response(200, text=body)
        return httpx.Response(200, text="")
    return httpx.Client(transport=httpx.MockTransport(handler))


def _ffs_only(tmp_path, rotowire_body: str | None, **kw) -> pd.DataFrame:
    mapping = {"fantasyfootballscout": FFS_HTML}
    if rotowire_body is not None:
        mapping["rotowire"] = rotowire_body
    return fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                         client=_client([], mapping),
                         providers=["ffs", "rotowire"], absence=False, **kw)


BASELINE = [(100, 1.0), (101, 0.0), (102, 1.0)]


def _pairs(frame: pd.DataFrame):
    return list(zip(frame["code"], frame["p_start_hint"]))


def test_a_provider_whose_fetch_returns_nothing_does_not_stop_the_other(
        tmp_path):
    assert _pairs(_ffs_only(tmp_path, None)) == BASELINE


def test_a_provider_that_parses_zero_rows_does_not_stop_the_other(tmp_path):
    assert _pairs(_ffs_only(tmp_path, "<html><p>no lineups</p></html>")) \
        == BASELINE


def test_a_provider_below_the_coverage_floor_does_not_stop_the_other(
        tmp_path):
    """RotoWire's names are strangers here, so match_codes discards the batch
    whole — which is indistinguishable from the source being down, and is the
    point."""
    rw = ('<div class="lineup__box">'
          '<div class="lineup__mteam is-home">Arsenal</div>'
          '<ul class="lineup__list is-home">'
          + "".join('<li class="lineup__player">'
                    f'<div class="lineup__pos">DC</div>'
                    f'<a title="Nobody Number{i}" href="/x">N</a></li>'
                    for i in range(11))
          + '</ul></div>')
    assert _pairs(_ffs_only(tmp_path, rw, min_coverage=0.9)) == BASELINE


def test_a_provider_that_raises_does_not_stop_the_other(tmp_path,
                                                        monkeypatch, capsys):
    def boom(_markup):
        raise ValueError("parser exploded")

    monkeypatch.setitem(PROVIDERS, "rotowire",
                        Provider("rotowire", ROTOWIRE_URL, boom,
                                 absence_capable=False))
    assert _pairs(_ffs_only(tmp_path, "<div/>")) == BASELINE
    assert "parser exploded" in capsys.readouterr().out


def test_all_providers_down_is_the_flags_only_frame(tmp_path):
    """The end-to-end statement, and the one v5's rail makes for one source:
    an empty LINEUP_COLS frame is what availability_frame reads as "the news
    layer said nothing", which is the official-flags path."""
    out = fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                        client=_client([], {}),
                        providers=["ffs", "rotowire"])
    assert out.empty
    assert list(out.columns) == LINEUP_COLS


def test_an_empty_provider_list_fetches_nothing_at_all(tmp_path):
    calls: list[str] = []
    out = fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                        client=_client(calls, {"fantasyfootballscout":
                                               FFS_HTML}),
                        providers=[])
    assert out.empty
    assert calls == []


def test_the_coarse_switch_short_circuits_before_providers_are_read():
    """``[news] lineups = false`` is checked in advise.py before
    fetch_lineups is reached at all, which is the composition plan A6
    promises: the coarse switch wins and the fine one refines it."""
    src = inspect.getsource(__import__("gaffer.advise",
                                       fromlist=["run_advise"]))
    assert "cfg.news_lineups" in src


# --- Block 2: §F1, optimizer degradation ---------------------------------

GWS = [1, 2]
KW = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
          itb_value=0.05, hit_cost=4, bench_curve=list(DEFAULT_BENCH_CURVE))


def _pool() -> pd.DataFrame:
    rows, code = [], 1
    for pos, n in [("GKP", 4), ("DEF", 9), ("MID", 10), ("FWD", 7)]:
        for i in range(n):
            rows.append({"code": code, "position": pos,
                         "team_code": code % 10, "cost": 50, "sell": 50,
                         "ep": {g: 2.0 + i * 0.1 for g in GWS}})
            code += 1
    return pd.DataFrame(rows)


OWNED = [1, 2, 5, 6, 7, 8, 9, 14, 15, 16, 17, 18, 24, 25, 26]


def _state() -> SolveInput:
    return SolveInput(owned_codes=list(OWNED), bank=0, free_transfers=2,
                      gws=list(GWS))


def _capture(monkeypatch, **kw):
    """One solve, returning (call count, LP text)."""
    seen: list[tuple[str, tuple[str, ...]]] = []
    real = milp._solve

    def spy(prob):
        real(prob)
        seen.append((str(prob.objective),
                     tuple(sorted(str(c) for c in prob.constraints.values()))))

    monkeypatch.setattr(milp, "_solve", spy)
    solve_plan(_pool(), _state(), **KW, **kw)
    return len(seen), seen[0]


def test_an_absent_p_play_is_one_solve_and_the_pre_v10_problem(monkeypatch):
    n_none, lp_none = _capture(monkeypatch)
    n_kw, lp_kw = _capture(monkeypatch, p_play=None)
    assert n_none == n_kw == 1
    assert lp_none == lp_kw


@pytest.mark.parametrize("value", [0.0, 0.4, 1.0])
def test_a_uniform_p_play_builds_character_identically_the_same_problem(
        monkeypatch, value):
    base_n, base_lp = _capture(monkeypatch)
    pool = _pool()
    uniform = {int(c): {g: value for g in GWS} for c in pool["code"]}
    n, lp = _capture(monkeypatch, p_play=uniform)
    assert base_n == n == 1
    assert lp == base_lp


def test_incomplete_coverage_fails_closed(monkeypatch):
    """Half a pool with probabilities and half silently nailed-on is the one
    direction that actively misleads."""
    base_n, base_lp = _capture(monkeypatch)
    pool = _pool()
    partial = {int(c): {g: 0.5 + (int(c) % 4) * 0.1 for g in GWS}
               for c in pool["code"][:15]}
    n, lp = _capture(monkeypatch, p_play=partial)
    assert base_n == n == 1
    assert lp == base_lp


def _lookup_reason(capsys, p_play) -> list[str]:
    """The lines ``_p_play_lookup`` printed for this input."""
    capsys.readouterr()
    milp._p_play_lookup(_pool(), _state(), p_play)
    return [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]


def test_a_supplied_p_play_that_is_rejected_says_why_exactly_once(capsys):
    """Failing closed is right and failing closed *silently* is not: the
    caller believes it wired the feature, the solve is the pre-v10 solve, and
    nothing in the advice says so. One line, and the reason in it."""
    pool = _pool()
    codes = [int(c) for c in pool["code"]]
    varied = {c: {g: 0.5 + (c % 5) * 0.1 for g in GWS} for c in codes}

    half = {c: v for c, v in list(varied.items())[:15]}
    lines = _lookup_reason(capsys, half)
    assert len(lines) == 1
    assert "p_play" in lines[0] and "coverage" in lines[0]
    # The count, so a caller can tell one missing player from twenty.
    assert str((len(codes) - 15) * len(GWS)) in lines[0]

    nans = dict(varied)
    nans[codes[0]] = {g: float("nan") for g in GWS}
    lines = _lookup_reason(capsys, nans)
    assert len(lines) == 1 and str(len(GWS)) in lines[0]

    flat = {c: {g: 0.7 for g in GWS} for c in codes}
    lines = _lookup_reason(capsys, flat)
    assert len(lines) == 1 and "spread" in lines[0]


def test_an_accepted_or_absent_p_play_says_nothing(capsys):
    codes = [int(c) for c in _pool()["code"]]
    assert _lookup_reason(capsys, None) == []
    assert _lookup_reason(capsys, {}) == []
    assert _lookup_reason(
        capsys, {c: {g: 0.5 + (c % 5) * 0.1 for g in GWS}
                 for c in codes}) == []


def test_a_p_play_constant_within_every_gameweek_is_not_a_spread(capsys):
    """0.9 in GW1 and 0.4 in GW2 for everybody is two constants, not
    information: inside any one week every player is identical, so nothing
    §F1 asks — which sub comes on first, how this XI compares to the
    population — has an answer. A pooled min/max would have called it spread
    and re-priced the bench off a fixture-difficulty artefact."""
    codes = [int(c) for c in _pool()["code"]]
    by_gw = {c: {GWS[0]: 0.9, GWS[1]: 0.4} for c in codes}
    lines = _lookup_reason(capsys, by_gw)
    assert milp._p_play_lookup(_pool(), _state(), by_gw) is None
    assert len(lines) == 1 and "spread" in lines[0]


def test_the_frailty_is_clamped_at_both_ends_and_is_one_at_the_population():
    lo, hi = FRAILTY_CLAMP
    assert _frailty(POPULATION_DNP) == pytest.approx(1.0)
    assert _frailty(0.0) == lo
    assert _frailty(1.0) == hi
    assert lo == 0.25 and hi == 2.0


def _coef(objective: str, var: str) -> float:
    """The coefficient on one variable in a pulp objective's printed form."""
    for term in objective.replace(" - ", " + -").split(" + "):
        head, _, name = term.partition("*")
        if name.strip() == var:
            return float(head)
    raise AssertionError(f"{var} is not in the objective")


def test_a_population_typical_keeper_reproduces_the_curve_exactly():
    """The reserve keeper's weight is ``bench_curve[0] * gk_f``, and ``gk_f``
    is the XI keeper's frailty. A keeper at the *keepers'* measured rate is by
    definition population-typical, so his cover must be priced at exactly the
    calibrated first weight — the same statement ``POPULATION_DNP`` makes for
    the outfield slots, over the divisor that belongs to keepers.

    Divided by the outfield rate instead, the same typical keeper priced his
    cover at 0.79 of the curve: a fifth off, every week, in one direction.
    """
    pool = _pool()
    keepers = [int(c) for c, p in zip(pool["code"], pool["position"])
               if p == "GKP"]
    pp = {int(c): {g: 0.5 + (int(c) % 5) * 0.1 for g in GWS}
          for c in pool["code"]}
    for k in keepers:
        pp[k] = {g: 1.0 - KEEPER_DNP for g in GWS}

    seen: list[str] = []
    real = milp._solve

    def spy(prob):
        real(prob)
        seen.append(str(prob.objective))

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(milp, "_solve", spy)
        plan = solve_plan(_pool(), _state(), **KW, p_play=pp)
    assert len(seen) == 2                      # informative: two passes ran
    bench_gk = next(c for c in plan.gw_plans[0].squad
                    if c in keepers and c not in plan.gw_plans[0].xi)
    var = f"sq_{bench_gk}_1"
    assert _coef(seen[1], var) == pytest.approx(_coef(seen[0], var))


def test_the_two_dnp_rates_are_separate_constants():
    assert _frailty(KEEPER_DNP, KEEPER_DNP) == pytest.approx(1.0)
    assert _frailty(POPULATION_DNP) == pytest.approx(1.0)
    # Not the same number, and not accidentally the same number: the gap is
    # what the fix is about.
    assert KEEPER_DNP != POPULATION_DNP
    # What the old single divisor did to a typical keeper: 21% low.
    assert KEEPER_DNP / POPULATION_DNP == pytest.approx(0.79, abs=0.01)


def test_population_dnp_is_a_measured_number_and_not_a_placeholder():
    """A constant nobody measured is the one way §F1 could ship looking
    finished and be arithmetically arbitrary, and there is nothing in a
    solve's output that would say so."""
    assert isinstance(POPULATION_DNP, float)
    assert 0.0 < POPULATION_DNP < 0.5
    src = inspect.getsource(milp)
    assert "<measured by" not in src
    assert "<gk_dnp>" not in src and "<lo>-<hi>" not in src
    assert "scripts/v10_dnp.py" in src


# --- Block 3: the arm lever ----------------------------------------------

def _arm_driver():
    """Imported, never shelled out — tests/test_v8a_degradation.py:140 pins
    that no test in this repo runs the real CLI."""
    path = Path("scripts/v10_shrunk_arm.py")
    spec = importlib.util.spec_from_file_location("v10_shrunk_arm", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_arm_lever_guard_refuses_every_way_of_being_disconnected():
    good = pd.DataFrame({"shrunk_start_rate": [0.1, 0.9],
                         "shrunk_min_per_app": [10.0, 80.0]})
    _arm_driver().check_lever(good)          # the control case: no raise

    mod = _arm_driver()
    mod.ARMS["shrunk_modes"] = []
    with pytest.raises(SystemExit):
        mod.check_lever(good)

    for frame in (pd.DataFrame({"shrunk_start_rate": [0.1, 0.9]}),
                  pd.DataFrame({"shrunk_start_rate": [0.1, 0.9],
                                "shrunk_min_per_app": [None, None]}),
                  pd.DataFrame({"shrunk_start_rate": [0.1, 0.9],
                                "shrunk_min_per_app": [42.0, 42.0]})):
        with pytest.raises(SystemExit):
            _arm_driver().check_lever(frame)


def test_the_minutes_features_docstring_records_the_g1_measurement():
    """The measurement must be recorded before the cycle can ship, and this
    is the rail that enforces it."""
    from gaffer.models import train as tr

    src = inspect.getsource(tr)
    block = src.split("MINUTES_FEATURES = ")[1].split('"""')[1]
    assert "v10 gate G1" in block
    assert "_pending G1_" not in block
    # A verdict, not just a number: v8a's block established the shape.
    assert "Kept:" in block or "Withdrawn:" in block


# --- Block 4: the pins ---------------------------------------------------

def test_the_job_count_did_not_move():
    """v10 adds no job: nothing here is a background task."""
    assert len(JOB_KINDS) == 12


def test_the_config_dataclass_did_not_grow(tmp_path, monkeypatch):
    """Plan A6 argued for a 49th field and the tree refused it:
    tests/test_v9c_degradation.py and tests/test_v9d_degradation.py both pin
    48 and both are protected this cycle. The per-provider switch is
    ``config.lineup_providers()`` instead — a module-level reader of the same
    ``[news] lineup_providers`` key, read at serve time the way
    ``serving_config()`` is read and for the same reason. Every behaviour A6
    argued for survives; only the storage does not.

    v12 W1 §2.6/§2.8 (specs/2026-09-01-gaffer-v12-program-design.md): **that
    refusal's cause has been retired.** The absolute count this test used to
    assert is gone from all seven protected files and lives in
    ``tests/test_v12_w1_degradation.py`` alone, so a cycle that wants A6's
    49th field now moves one number in one unprotected place. The design
    question A6 lost on a technicality is open again, and losing it a second
    time would have to be on the merits.

    What v10 is entitled to claim is below, unchanged: the switch is a reader,
    and the field it would have been is absent.
    """
    assert not any(f.name == "news_lineup_providers"
                   for f in dataclasses.fields(Config))
    monkeypatch.chdir(tmp_path)
    assert lineup_providers() == list(DEFAULT_LINEUP_PROVIDERS)


def test_the_route_count_did_not_move(tmp_path, monkeypatch):
    """The name is v10's claim and it stands: v10 added no route.

    The absolute total used to be asserted here, and is now pinned in
    ``tests/test_v11_degradation.py`` and nowhere else — v11's restructure,
    made in a cycle that added no route, so every assertion kept its verdict
    across the diff.

    "The routes that cycle added" is the empty set for v10, so there is no
    existence assert to write and an existence assert over nothing would
    assert nothing. The claim that survives is the one v10 actually made: the
    minutes work — the provider seam, ``p_play``, the two-pass solve — reached
    the app through no HTTP surface at all."""
    monkeypatch.chdir(tmp_path)
    paths = set(create_app().openapi()["paths"])
    assert not [p for p in paths
                if p.startswith(("/api/lineups", "/api/minutes",
                                 "/api/providers"))]


def test_the_bench_curve_was_rescaled_and_not_resized():
    """§F1a modulates the three weights; a fourth would be a different
    claim, and BENCH_SLOTS and the curve must not drift apart."""
    assert len(DEFAULT_BENCH_CURVE) == 3 == BENCH_SLOTS


def test_shadow_cols_is_the_exact_nine():
    """Pinned as a list rather than a length: a length pin would not catch a
    rename, and every reader of this parquet expects run_at last."""
    assert SHADOW_COLS == ["season", "gw", "code", "p_play_news",
                           "p_play_flags", "e_min_news", "e_min_flags",
                           "p_play_presser", "run_at"]


def test_a_mixed_vintage_shadow_parquet_still_serialises(tmp_path,
                                                         monkeypatch):
    """The state every real machine reaches the week v10 lands: a parquet
    whose old rows were back-filled with NaN when ``p_play_presser`` was added
    and whose new rows carry a verdict.

    Scored naively, the third side's Brier is NaN over the whole log, and
    ``save_evaluation`` serialises with ``allow_nan=False`` — so the failure is
    not a wrong number in the N2 readout, it is no readout at all, and the
    pending verdict is what it takes down with it.
    """
    monkeypatch.chdir(tmp_path)
    shadow = pd.DataFrame({
        "season": ["2025-26"] * 4, "gw": [4, 4, 5, 5], "code": [1, 2, 1, 2],
        "p_play_news": [0.9, 0.5, 0.9, 0.5],
        "p_play_flags": [0.8, 0.4, 0.8, 0.4],
        "e_min_news": [80.0, 40.0, 80.0, 40.0],
        "e_min_flags": [70.0, 30.0, 70.0, 30.0],
        # GW4 predates the column; GW5 is the first week the classifier ran.
        "p_play_presser": [float("nan"), float("nan"), 0.72, 0.25],
        "run_at": ["t"] * 4})
    actuals = pd.DataFrame({"gw": [4, 4, 5, 5], "code": [1, 2, 1, 2],
                            "minutes": [90.0, 0.0, 90.0, 0.0]})
    payload = score_news_shadow(shadow, actuals)
    text = json.dumps(payload, allow_nan=False)     # the actual failure mode
    assert "NaN" not in text
    assert payload["overall"]["rows"] == 4
    assert payload["overall"]["rows_presser"] == 2
    gw4 = next(r for r in payload["by_gw"] if r["gw"] == 4)
    assert "brier_presser" not in gw4 and "rows_presser" not in gw4
    gw5 = next(r for r in payload["by_gw"] if r["gw"] == 5)
    assert gw5["rows_presser"] == 2 and gw5["rows"] == 2


def _advise_src() -> str:
    return inspect.getsource(__import__("gaffer.advise",
                                        fromlist=["run_advise"]).run_advise)


def _raw_solve_branches() -> tuple[ast.Call, ast.Call]:
    """The two ``solve_plan`` calls of the raw-optimum ``if``, as AST nodes:
    ``(sweep_runs, sweep_does_not_run)``."""
    tree = ast.parse(textwrap.dedent(_advise_src()))
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        calls = [c for branch in (node.body, node.orelse)
                 for stmt in branch for c in ast.walk(stmt)
                 if isinstance(c, ast.Call)
                 and getattr(c.func, "id", None) == "solve_plan"]
        if len(calls) == 2 and node.orelse:
            return calls[0], calls[1]
    raise AssertionError("the raw optimum is no longer a two-branch if")


def test_the_p_play_seam_follows_the_sweep_and_not_the_solve():
    """The T10-A rewiring, as a rail — and the hole the first cut left.

    ``decide()`` compares the raw optimum against the sweep's plurality, and
    the sweep does not *solve* under ``p_play``. Weighting the raw solve
    *while the sweep runs* would make that comparison a comparison of two
    different objectives — reported to the user as ``raw_optimum_agrees=False``,
    for a reason that is not instability.

    But when the sweep does not run there is no such comparison, and the raw
    solve *is* the advice: fast advice (``scenarios_n = 0``) and the
    initial-squad weeks silently lost the whole of §F1 to a guard that was
    protecting a gate they never reach.

    **v12 W3 §4.4 (specs/2026-09-01-gaffer-v12-program-design.md) narrowed
    this.** The rail used to assert that the string ``p_play`` did not appear
    near the sweep call at all, which was a proxy for the claim above and not
    the claim itself. §4.4 hands the sweep ``p_play`` for a Bernoulli
    availability draw — an outcome per scenario, not a coefficient — so the
    proxy now forbids the feature. What survives is T10-A's actual claim: the
    sweep's *solve bundle* is still ``solve_kw``, so no scenario is solved
    under §F1's frailty weights and the raw optimum remains the unweighted one.
    The consequence §4.4 accepts, recorded rather than papered over: the sweep
    now models availability risk the raw solve does not, so
    ``raw_optimum_agrees`` reads ``False`` more often — and unlike the
    objective mismatch this rail was written about, that disagreement is
    information.
    """
    src = _advise_src()
    assert "solve_kw = dict(opt_kw, ft_lambda=ft_lambda)" in src
    # The sweep's own bundle is still untouched: it never had p_play.
    assert "scenario_kw" not in src
    sweep = src[src.index("run_scenarios("):src.index("run_scenarios(") + 400]
    # The solve bundle the sweep passes through is still the unweighted one.
    assert "**solve_kw" in sweep
    # p_play reaches the sweep as a draw and only behind its own switch.
    assert "draw_availability=cfg.draw_availability" in sweep
    assert "p_play=(p_play_by_code if cfg.draw_availability" in sweep

    gated, ungated = _raw_solve_branches()
    assert not [k for k in gated.keywords if k.arg == "p_play"]
    assert [k.value.id for k in ungated.keywords if k.arg == "p_play"] == [
        "p_play_by_code"]


def test_the_coherent_plan_carries_the_weights_when_the_sweep_ran():
    """The other consumer, and the only one inside the gated branch."""
    src = _advise_src()
    coherent = src.index("coherent_plan(pool, state, decision")
    assert "p_play=p_play_by_code" in src[coherent:coherent + 200]
    # Two consumers now, and both are plans that are actually recommended:
    # the coherent plan, and the raw solve of the modes that have no sweep.
    assert src.count("p_play=p_play_by_code") == 2


def test_the_sweep_condition_is_asked_once_and_named():
    """Fast advice and the initial squad are the *same* condition as the
    scenario block's, and a copy of it that drifts is how the raw solve ends
    up weighted in a mode whose gate is live."""
    src = _advise_src()
    assert src.count("if cfg.scenarios_n > 0 and state.owned_codes:") == 1
    assert src.index("if cfg.scenarios_n > 0 and state.owned_codes:") < \
        src.index("plan = solve_plan(pool, state, **solve_kw)")
    assert "if sweep_runs:" in src


def test_a_bench_boost_week_is_lp_identical_with_and_without_p_play():
    """§F1a deliberately leaves the boosted branch alone: under a bench boost
    every bench player scores in full, so ``bw = 1.0`` and the slot weights do
    not apply. An informative p_play must not move that week's objective."""
    pool, gws = _pool(), list(GWS)
    informative = {int(c): {g: 0.5 + (int(c) % 5) * 0.1 for g in gws}
                   for c in pool["code"]}

    def capture(**kw):
        seen = []
        real = milp._solve

        def spy(prob):
            real(prob)
            seen.append(str(prob.objective))

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(milp, "_solve", spy)
            state = SolveInput(owned_codes=list(OWNED), bank=0,
                               free_transfers=2, gws=gws, bench_boost_gw=gws[0])
            solve_plan(pool, state, **KW, **kw)
        return seen

    base = capture()
    weighted = capture(p_play=informative)
    assert len(base) == 1 and len(weighted) == 2
    # The boosted week's terms are the same terms; only the unboosted second
    # week may be re-priced by the frailty.
    assert _boost_week_terms(base[0]) == _boost_week_terms(weighted[0])


def _boost_week_terms(objective: str) -> set[str]:
    """The objective's terms naming a boosted-week variable (``_1`` suffix)."""
    return {t for t in objective.replace("- ", "+ -").split(" + ")
            if t.rstrip().endswith("_1")}


def test_lineup_cols_is_unchanged_from_mains_five():
    """What keeps normalize.availability_frame and every protected
    availability rail out of this cycle's blast radius."""
    assert LINEUP_COLS == ["code", "p_start_hint", "absence_damp", "source",
                           "fetched_at"]


def test_every_provider_can_be_named_by_the_config():
    """A provider nobody can name is a provider nobody can kill."""
    assert set(PROVIDERS) == set(DEFAULT_LINEUP_PROVIDERS)
