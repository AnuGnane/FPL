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

import dataclasses
import importlib.util
import inspect
from pathlib import Path

import httpx
import pandas as pd
import pytest

import gaffer.optimize.milp as milp
from gaffer.config import DEFAULT_LINEUP_PROVIDERS, Config, lineup_providers
from gaffer.data.news.lineups import (LINEUP_COLS, PROVIDERS, Provider,
                                      ROTOWIRE_URL, fetch_lineups)
from gaffer.news_shadow import SHADOW_COLS
from gaffer.optimize.milp import (BENCH_SLOTS, DEFAULT_BENCH_CURVE,
                                  FRAILTY_CLAMP, POPULATION_DNP, SolveInput,
                                  _frailty, solve_plan)
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


def test_the_frailty_is_clamped_at_both_ends_and_is_one_at_the_population():
    lo, hi = FRAILTY_CLAMP
    assert _frailty(POPULATION_DNP) == pytest.approx(1.0)
    assert _frailty(0.0) == lo
    assert _frailty(1.0) == hi
    assert lo == 0.25 and hi == 2.0


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
    argued for survives; only the storage does not."""
    assert len(dataclasses.fields(Config)) == 48
    monkeypatch.chdir(tmp_path)
    assert lineup_providers() == list(DEFAULT_LINEUP_PROVIDERS)


def test_the_route_count_did_not_move(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert len(create_app().openapi()["paths"]) == 44


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


def test_lineup_cols_is_unchanged_from_mains_five():
    """What keeps normalize.availability_frame and every protected
    availability rail out of this cycle's blast radius."""
    assert LINEUP_COLS == ["code", "p_start_hint", "absence_damp", "source",
                           "fetched_at"]


def test_every_provider_can_be_named_by_the_config():
    """A provider nobody can name is a provider nobody can kill."""
    assert set(PROVIDERS) == set(DEFAULT_LINEUP_PROVIDERS)
