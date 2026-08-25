import pandas as pd

from gaffer.optimize.milp import GwPlan, Plan
from gaffer.optimize.policy import (NEAR_MISS_BAND, Decision, Thresholds,
                                    decide)


def _freq(rows) -> pd.DataFrame:
    """Rows as (kind, code, gw, label, frequency); count is derived."""
    return pd.DataFrame(
        [{"kind": k, "code": c, "gw": g, "label": lab,
          "count": int(round(f * 100)), "frequency": f}
         for k, c, g, lab, f in rows],
        columns=["kind", "code", "gw", "label", "count", "frequency"])


def _raw(buys=(), sells=(), captain=9, hits=0, gw=5) -> Plan:
    gp = GwPlan(gw=gw, squad=[], xi=[], xi_rows=[], bench=[], captain=captain,
                vice=0, buys=list(buys), sells=list(sells), hits=hits,
                expected_pts=0.0)
    return Plan(objective=0.0, gw_plans=[gp])


TH = Thresholds(transfer=0.60, irreversible=0.75)


def test_thresholds_carry_the_spec_defaults():
    assert Thresholds().transfer == 0.60
    assert Thresholds().irreversible == 0.75


def test_a_transfer_above_sixty_percent_is_recommended():
    freq = _freq([("buy", 1, 5, "buy", 0.80), ("sell", 2, 5, "sell", 0.75),
                  ("captain", 9, 5, "captain", 1.0)])
    d = decide(freq, _raw(buys=[1], sells=[2]), TH)
    assert d.buys == [1] and d.sells == [2]
    assert d.hold is False


def test_a_transfer_exactly_at_the_bar_is_recommended():
    """>= 60%, not > 60%: the bar is a bar, not a strict inequality."""
    freq = _freq([("buy", 1, 5, "buy", 0.60), ("sell", 2, 5, "sell", 0.60),
                  ("captain", 9, 5, "captain", 1.0)])
    assert decide(freq, _raw(buys=[1], sells=[2]), TH).buys == [1]


def test_a_transfer_below_the_bar_is_held():
    freq = _freq([("buy", 1, 5, "buy", 0.55), ("sell", 2, 5, "sell", 0.55),
                  ("captain", 9, 5, "captain", 1.0)])
    d = decide(freq, _raw(buys=[1], sells=[2]), TH)
    assert d.buys == [] and d.sells == [] and d.hold is True


def test_a_held_decision_lists_its_near_misses_with_frequencies():
    freq = _freq([("buy", 1, 5, "buy", 0.55), ("sell", 2, 5, "sell", 0.50),
                  ("buy", 7, 5, "buy", 0.05),
                  ("captain", 9, 5, "captain", 1.0)])
    d = decide(freq, _raw(buys=[1], sells=[2]), TH)
    labels = {(m["kind"], m["code"]): m["frequency"] for m in d.near_misses}
    assert labels[("buy", 1)] == 0.55
    # 5% is not a near miss, it is a non-starter.
    assert ("buy", 7) not in labels


def test_the_near_miss_band_is_the_documented_width():
    assert NEAR_MISS_BAND == 0.20


def test_a_hit_needs_the_irreversible_bar():
    below = _freq([("hit", 0, 5, "hit", 0.70),
                   ("buy", 1, 5, "buy", 0.90), ("sell", 2, 5, "sell", 0.90),
                   ("captain", 9, 5, "captain", 1.0)])
    assert decide(below, _raw(buys=[1], sells=[2], hits=1), TH).hit is False

    above = _freq([("hit", 0, 5, "hit", 0.80),
                   ("buy", 1, 5, "buy", 0.90), ("sell", 2, 5, "sell", 0.90),
                   ("captain", 9, 5, "captain", 1.0)])
    assert decide(above, _raw(buys=[1], sells=[2], hits=1), TH).hit is True


def test_a_chip_needs_the_irreversible_bar():
    below = _freq([("chip", 0, 5, "bboost", 0.70),
                   ("captain", 9, 5, "captain", 1.0)])
    assert decide(below, _raw(), TH).chip is None

    above = _freq([("chip", 0, 5, "bboost", 0.90),
                   ("captain", 9, 5, "captain", 1.0)])
    d = decide(above, _raw(), TH)
    assert d.chip == "bboost" and d.chip_gw == 5


def test_the_wildcard_is_irreversible_like_every_other_chip():
    freq = _freq([("chip", 0, 5, "wildcard", 0.70),
                  ("captain", 9, 5, "captain", 1.0)])
    assert decide(freq, _raw(), TH).chip is None


def test_the_captain_is_the_plurality_winner_even_below_every_bar():
    """There is no 'hold' for the armband: someone wears it."""
    freq = _freq([("captain", 9, 5, "captain", 0.40),
                  ("captain", 4, 5, "captain", 0.35),
                  ("captain", 7, 5, "captain", 0.25)])
    d = decide(freq, _raw(captain=4), TH)
    assert d.captain == 9
    assert d.captain_frequency == 0.40


def test_a_captain_tie_breaks_towards_the_raw_optimum():
    """A coin flip that always lands the same way is better than one that
    lands differently every time the solver is re-run."""
    freq = _freq([("captain", 9, 5, "captain", 0.50),
                  ("captain", 4, 5, "captain", 0.50)])
    assert decide(freq, _raw(captain=4), TH).captain == 4


def test_with_no_captain_rows_the_raw_optimums_captain_survives():
    """Degradation: an empty sweep must not produce a captainless advice."""
    d = decide(_freq([]), _raw(captain=6), TH)
    assert d.captain == 6 and d.hold is True


def test_raw_optimum_agrees_when_the_gated_moves_match_it():
    freq = _freq([("buy", 1, 5, "buy", 0.90), ("sell", 2, 5, "sell", 0.90),
                  ("captain", 9, 5, "captain", 1.0)])
    assert decide(freq, _raw(buys=[1], sells=[2]), TH).raw_optimum_agrees


def test_raw_optimum_disagrees_when_it_wanted_a_different_player():
    freq = _freq([("buy", 1, 5, "buy", 0.90), ("sell", 2, 5, "sell", 0.90),
                  ("captain", 9, 5, "captain", 1.0)])
    assert not decide(freq, _raw(buys=[7], sells=[2]), TH).raw_optimum_agrees


def test_raw_optimum_disagrees_when_the_gate_held_it_back():
    freq = _freq([("buy", 1, 5, "buy", 0.30), ("sell", 2, 5, "sell", 0.30),
                  ("captain", 9, 5, "captain", 1.0)])
    assert not decide(freq, _raw(buys=[1], sells=[2]), TH).raw_optimum_agrees


def test_a_buy_without_a_passing_sell_still_records_the_buy():
    """decide() reports what cleared the bar; making it *legal* is
    coherent_plan's job, and conflating the two would hide the gap."""
    freq = _freq([("buy", 1, 5, "buy", 0.90), ("sell", 2, 5, "sell", 0.30),
                  ("captain", 9, 5, "captain", 1.0)])
    d = decide(freq, _raw(buys=[1], sells=[2]), TH)
    assert d.buys == [1] and d.sells == []


def test_decide_returns_the_frequency_table_it_was_given():
    """The report prints it next to the recommendation, so the decision
    carries its own evidence."""
    freq = _freq([("captain", 9, 5, "captain", 1.0)])
    d = decide(freq, _raw(), TH)
    assert isinstance(d, Decision)
    assert list(d.frequencies["kind"]) == ["captain"]


def test_buys_and_sells_come_back_in_descending_frequency():
    freq = _freq([("buy", 1, 5, "buy", 0.70), ("buy", 3, 5, "buy", 0.95),
                  ("captain", 9, 5, "captain", 1.0)])
    assert decide(freq, _raw(buys=[1, 3]), TH).buys == [3, 1]
