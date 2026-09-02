"""§4.5: wildcard plus bench boost, as one option.

The empty state is the main case and is tested first, because it is the state
every machine is in: ``data/chip_scenarios.toml`` does not exist, the writer
refuses to create it while every gameweek has ten fixtures, so ``dgw_gws`` is
empty and the table is exactly the table it was.

The most important assertion in the file is the one about *other* callers.
``backtest.py``'s chip executor branches on the chip name and has no arm for a
pair: a pair row reaching ``_pick_chip`` would be selected, recorded as played
and applied to nothing — a phantom chip in a replay. The parameter is opt-in
and this file pins that no caller but ``advise`` opts in.
"""

from __future__ import annotations

import inspect
from dataclasses import replace

import pandas as pd
import pytest

from gaffer.optimize import chips as chips_mod
from gaffer.optimize.chips import (PAIR_CHIP, PAIR_DGW_MIN_PROB,
                                   _weeks_covered, evaluate_chips)
from gaffer.optimize.milp import SolveInput

CFG = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
           itb_value=0.05, hit_cost=4)
GWS = [1, 2, 3]


def _pool() -> pd.DataFrame:
    rows, code = [], 1
    for pos, n in [("GKP", 4), ("DEF", 9), ("MID", 10), ("FWD", 7)]:
        for i in range(n):
            rows.append({"code": code, "position": pos,
                         "team_code": (code % 6) + 1, "cost": 40, "sell": 40,
                         "ep": {g: 1.0 + (code % 7) * 0.3 + g * 0.1
                                for g in GWS}})
            code += 1
    return pd.DataFrame(rows)


def _state() -> SolveInput:
    return SolveInput(owned_codes=list(range(1, 16)), bank=200,
                      free_transfers=1, gws=list(GWS))


def _table(**kw):
    return evaluate_chips(_pool(), _state(),
                          chips_available=["wildcard", "bboost"], **kw, **CFG)


def test_with_no_doubles_the_table_is_the_table_it_was():
    """Today's state on every machine."""
    table = _table()
    assert PAIR_CHIP not in set(table["chip"])
    assert list(table.columns) == ["chip", "gw", "gw2", "gain", "per_week"]


def test_gw2_is_None_on_an_ordinary_row_and_never_nan():
    """pandas turns a column of None-and-int into float64 with NaN, which
    pydantic refuses and json writes as a bare NaN."""
    rows = _table(dgw_gws={3}).to_dict("records")
    singles = [r for r in rows if r["chip"] != PAIR_CHIP]
    assert singles and all(r["gw2"] is None for r in singles)


def test_a_double_in_the_horizon_produces_a_pair_naming_both_weeks():
    rows = [r for r in _table(dgw_gws={3}).to_dict("records")
            if r["chip"] == PAIR_CHIP]
    assert rows
    assert all(r["gw2"] == 3 and r["gw"] < 3 for r in rows)


def test_the_boost_is_never_in_the_wildcards_own_week():
    """One chip per gameweek is the rule of the game."""
    rows = [r for r in _table(dgw_gws={1, 2, 3}).to_dict("records")
            if r["chip"] == PAIR_CHIP]
    assert all(r["gw2"] > r["gw"] for r in rows)


def test_the_pair_is_scored_against_the_same_baseline_as_the_singles():
    """A joint solve minus the no-chip plan, in the same undecayed frame — so
    a pair worth less than its wildcard alone is a readable comparison rather
    than a units bug."""
    table = _table(dgw_gws={3})
    wc = table[(table["chip"] == "wildcard") & (table["gw"] == 1)]
    pair = table[(table["chip"] == PAIR_CHIP) & (table["gw"] == 1)]
    assert not wc.empty and not pair.empty
    # The pair is the same wildcard plus a boost, so it cannot be worth less.
    assert float(pair["gain"].iloc[0]) >= float(wc["gain"].iloc[0]) - 1e-6


def test_a_pair_is_credited_the_wildcards_weeks_not_one():
    assert _weeks_covered(PAIR_CHIP, 1, GWS) == 3
    assert _weeks_covered("bboost", 1, GWS) == 1


def test_a_week_with_no_bench_boost_available_produces_no_pair():
    table = evaluate_chips(_pool(), _state(),
                           avail_by_gw={1: ["wildcard"], 2: [], 3: []},
                           dgw_gws={3}, **CFG)
    assert PAIR_CHIP not in set(table["chip"])


# --- the loop's cap (T8-T11 review, Minor 6) ------------------------------

LONG_GWS = list(range(1, 9))


def _long_pool() -> pd.DataFrame:
    rows, code = [], 1
    for pos, n in [("GKP", 4), ("DEF", 9), ("MID", 10), ("FWD", 7)]:
        for i in range(n):
            rows.append({"code": code, "position": pos,
                         "team_code": (code % 6) + 1, "cost": 40, "sell": 40,
                         "ep": {g: 1.0 + (code % 7) * 0.3 + g * 0.1
                                for g in LONG_GWS}})
            code += 1
    return pd.DataFrame(rows)


def test_the_pair_loop_is_capped_and_takes_the_closest_doubles_first():
    """Every pair is a full-horizon MILP. A horizon whose every week is a
    believed double is quadratic in the horizon, and an advise run is not the
    place to discover that."""
    from gaffer.optimize.chips import PAIR_EVAL_MAX

    assert PAIR_EVAL_MAX == 6
    state = SolveInput(owned_codes=list(range(1, 16)), bank=200,
                       free_transfers=1, gws=list(LONG_GWS))
    table = evaluate_chips(_long_pool(), state,
                           chips_available=["wildcard", "bboost"],
                           dgw_gws=set(LONG_GWS), **CFG)
    pairs = table[table["chip"] == PAIR_CHIP]
    assert len(pairs) == PAIR_EVAL_MAX
    # Closest first: every kept pair puts the boost in the week straight after
    # the rebuild. There are seven such pairs here and room for six, so the
    # tie breaks on the earlier wildcard week.
    assert {(int(r.gw), int(r.gw2)) for r in pairs.itertuples()} == \
        {(g, g + 1) for g in LONG_GWS[:PAIR_EVAL_MAX]}


# --- the pair's bar (T8-T11 review, Important 2) --------------------------

def _priors_covering_everything() -> dict:
    """A sample in every week of both chip windows, for both halves of the
    pair, so no lookup has an excuse to fall through to flat."""
    return {"chip_surplus": {
        "wildcard": {str(gw): [3.0, 5.0, 9.0] for gw in range(1, 39)},
        "bboost": {str(gw): [1.0, 2.0, 4.0] for gw in range(1, 39)}}}


def test_the_pairs_flat_bar_is_the_sum_of_the_two_chips_it_spends():
    """The pair fell through ``chip == "wildcard"`` to the 4.0 one-week bar —
    *below* the lone wildcard's 8.0 — while its gain is at least the
    wildcard's by construction, because a wildcard-and-no-boost squad is one
    of the things the pair's own solve may choose. So the pair read "play
    now" everywhere the wildcard did, and on a whole band of boards where it
    did not."""
    from gaffer.optimize.chip_policy import flat_thresholds

    flat = flat_thresholds()
    assert flat(PAIR_CHIP, 7) == flat("wildcard", 7) + flat("bboost", 7)
    assert flat(PAIR_CHIP, 7) > flat("wildcard", 7)


def test_the_pairs_theta_bar_is_the_sum_of_the_two_thetas():
    from gaffer.optimize.chip_policy import (chip_thresholds_from_asset,
                                             threshold_with_source)

    lookup = chip_thresholds_from_asset(_priors_covering_everything())
    for gw in (1, 12, 19, 20, 33, 38):
        pair, _ = threshold_with_source(lookup, PAIR_CHIP, gw)
        wc, _ = threshold_with_source(lookup, "wildcard", gw)
        bb, _ = threshold_with_source(lookup, "bboost", gw)
        assert pair == pytest.approx(wc + bb)


def test_the_pairs_source_names_both_bars():
    """A reader who sees one number has to be able to see where it came from,
    and the pair's number is two numbers added."""
    from gaffer.optimize.chip_policy import (chip_thresholds_from_asset,
                                             threshold_with_source)

    lookup = chip_thresholds_from_asset(_priors_covering_everything())
    _, source = threshold_with_source(lookup, PAIR_CHIP, 7)
    assert source.startswith("theta")
    assert "wildcard" in source and "bboost" in source


def test_the_pair_cannot_play_now_where_the_lone_wildcard_waits():
    """The bug, stated as the behaviour it produced."""
    from gaffer.optimize.chip_policy import (chip_thresholds_from_asset,
                                             flat_thresholds,
                                             threshold_with_source)

    for lookup in (flat_thresholds(),
                   chip_thresholds_from_asset(_priors_covering_everything())):
        wc = threshold_with_source(lookup, "wildcard", 7)[0]
        bb = threshold_with_source(lookup, "bboost", 7)[0]
        pair = threshold_with_source(lookup, PAIR_CHIP, 7)[0]
        for gain in (wc - 0.01, wc, wc + bb - 0.01, wc + bb):
            assert not ((gain >= pair) and not (gain >= wc)), \
                "a pair played on a board where the wildcard alone waits"
        assert (wc + bb - 0.01) < pair <= (wc + bb)


def test_no_caller_but_advise_asks_for_pairs():
    """The rail this file exists for. backtest's chip executor has no branch
    for a pair name, so a pair row reaching _pick_chip would be recorded as
    played and applied to nothing."""
    from gaffer import backtest
    from gaffer.web.routers import meta

    for source in (inspect.getsource(backtest),
                   inspect.getsource(meta.chips_plan)):
        assert "dgw_gws" not in source


def test_the_scenario_file_reaches_the_pair_arm_as_gameweeks(tmp_path):
    """The behavioural sibling to the source rail below (T8-T11 final review,
    Important 2). Every link ``advise`` wires between the file on disk and the
    pair row, driven for real: the loader, the probability bar, and
    ``evaluate_chips``' ``dgw_gws``.

    A spelling check cannot see a *shape* mismatch between two links — the
    §4.6 wiring bug this review found was exactly that, a frame handed to a
    function that answers ``{}`` for it — so the chain is exercised rather
    than read. TOML keys are strings; ``dgw_gws`` is a set of ints; a pair
    row's ``gw2`` is one of them.
    """
    from gaffer.optimize.chip_policy import load_chip_scenarios

    path = tmp_path / "chip_scenarios.toml"
    path.write_text("[dgw]\n3 = 0.9\n2 = 0.3\n")
    probs = load_chip_scenarios(path)
    dgw_gws = {int(g) for g, p in probs.items() if p >= PAIR_DGW_MIN_PROB}
    assert dgw_gws == {3}, "the rumoured double is under the bar"

    rows = [r for r in _table(dgw_gws=dgw_gws).to_dict("records")
            if r["chip"] == PAIR_CHIP]
    assert rows and all(r["gw2"] == 3 for r in rows)


def test_advise_derives_the_doubles_from_the_probabilities_it_already_read():
    """**Kept** as a rail on the call shape (T8-T11 final review, Important 2)
    beside the behavioural chain above. ``run_advise`` has no cheap end-to-end
    harness, and the claim here is not about the arithmetic — the test above
    covers that — but about *where* the derivation happens: one read of the
    scenario asset per run, feeding both the surplus mixture and the pair arm,
    so the two cannot be told different things about the same week."""
    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    assert "dgw_probs = load_chip_scenarios()" in src
    assert src.count("load_chip_scenarios()") == 1
    assert "dgw_gws={int(g) for g, p" in src
    assert "PAIR_DGW_MIN_PROB" in src


def test_the_probability_bar_excludes_a_rumoured_double():
    assert PAIR_DGW_MIN_PROB == 0.5
    probs = {3: 0.3}
    assert {g for g, p in probs.items() if p >= PAIR_DGW_MIN_PROB} == set()
