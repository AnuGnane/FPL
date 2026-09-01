"""Gate G1's driver: the arm table, the lever guards, and the verdict rule.

The run itself is two benchmark fits and is the orchestrator's job
(CONVENTIONS.md §7). Nothing here fits a model. What is testable is the part
that decides — and, above all, the part that refuses to decide: v9c's rebound
lever was *bound* rather than read and v8a's ``f2_league``/``f2_cups`` pair
were two lists with identical values on the window, and both printed a clean,
believable, meaningless negative. :func:`check_lever` exists so that a third
one raises instead (plan A12).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

SCRIPT = Path("scripts/v10_shrunk_arm.py")


def _driver():
    """Import the script without running its ``main``."""
    spec = importlib.util.spec_from_file_location("v10_shrunk_arm", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _frame(**cols) -> pd.DataFrame:
    return pd.DataFrame(cols)


def test_the_control_arm_is_the_shipped_list_exactly():
    """A control that is not today's model is not a control."""
    from gaffer.models import train as tr

    mod = _driver()
    assert mod.ARMS["baseline"] == []
    assert mod.arm_features("baseline") == list(tr.MINUTES_FEATURES)


def test_the_arm_is_the_shrunken_modes_as_one_block():
    """One claim measured two ways goes in as one arm (plan A13): a
    withdrawal here withdraws the claim, not a column."""
    from gaffer.features.engineer import SHRUNK_MODE_FEATURES

    mod = _driver()
    assert mod.ARMS["shrunk_modes"] == list(SHRUNK_MODE_FEATURES)
    assert set(mod.ARMS) == {"baseline", "shrunk_modes"}


def test_arm_features_never_mutates_the_shipped_constant():
    """The driver swaps a module global for the length of a fit. A driver
    that leaves it swapped poisons every later import in the process."""
    from gaffer.models import train as tr

    mod = _driver()
    before = list(tr.MINUTES_FEATURES)
    first = mod.arm_features("baseline")
    second = mod.arm_features("shrunk_modes")
    assert list(tr.MINUTES_FEATURES) == before
    assert first is not tr.MINUTES_FEATURES
    assert second is not tr.MINUTES_FEATURES
    first.append("scribble")
    assert list(tr.MINUTES_FEATURES) == before


def test_check_lever_raises_when_the_arm_is_the_control():
    """v9c's failure mode: an intervention that is not an intervention."""
    mod = _driver()
    mod.ARMS["shrunk_modes"] = []
    df = _frame(shrunk_start_rate=[0.1, 0.9], shrunk_min_per_app=[10.0, 80.0])
    with pytest.raises(SystemExit, match="lever is disconnected"):
        mod.check_lever(df)


def test_check_lever_raises_on_a_missing_column():
    mod = _driver()
    df = _frame(shrunk_start_rate=[0.1, 0.9])
    with pytest.raises(SystemExit, match="not on the training frame"):
        mod.check_lever(df)


def test_check_lever_raises_on_an_all_null_column():
    mod = _driver()
    df = _frame(shrunk_start_rate=[0.1, 0.9],
                shrunk_min_per_app=[None, None])
    with pytest.raises(SystemExit, match="entirely null"):
        mod.check_lever(df)


def test_check_lever_raises_on_a_constant_column():
    """LightGBM never splits on a constant, so the arm is the control by
    another name — v8a's f2_league/f2_cups tie, generalised."""
    mod = _driver()
    df = _frame(shrunk_start_rate=[0.1, 0.9],
                shrunk_min_per_app=[42.0, 42.0])
    with pytest.raises(SystemExit, match="constant on this window"):
        mod.check_lever(df)


def test_check_lever_passes_on_two_varying_columns(capsys):
    mod = _driver()
    df = _frame(shrunk_start_rate=[0.1, 0.9, 0.5],
                shrunk_min_per_app=[10.0, 80.0, 45.0])
    mod.check_lever(df)
    assert "V10_ARM_LEVER ok" in capsys.readouterr().out


def test_the_verdict_needs_both_halves():
    """Spec §F3a's bar is a conjunction, and the second half is what stops
    the first from being gamed by calling everyone a starter."""
    mod = _driver()
    base = {"p_start_ll_starters": 0.200, "zeros": 1.066}

    keep = mod.verdict(base, {"p_start_ll_starters": 0.196, "zeros": 1.066})
    assert keep["decision"] == "keep"
    assert keep["logloss_relative_gain"] == pytest.approx(0.02)

    costly = mod.verdict(base, {"p_start_ll_starters": 0.196,
                                "zeros": 1.086})
    assert costly["decision"] == "withdraw"
    assert costly["zeros_cost"] == pytest.approx(0.02)

    small = mod.verdict(base, {"p_start_ll_starters": 0.199, "zeros": 1.000})
    assert small["decision"] == "withdraw"


def test_the_gain_is_read_as_a_relative_improvement():
    """1% of a loss, not 0.01 of one: an absolute reading on a slice whose
    log-loss sits around 0.2 would be a 5% bar wearing a 1% label."""
    mod = _driver()
    base = {"p_start_ll_starters": 0.200, "zeros": 1.0}
    assert mod.verdict(base, {"p_start_ll_starters": 0.198,
                              "zeros": 1.0})["decision"] == "keep"
    assert mod.verdict(base, {"p_start_ll_starters": 0.1990,
                              "zeros": 1.0})["decision"] == "withdraw"


def test_a_zero_control_loss_does_not_divide_by_zero():
    mod = _driver()
    v = mod.verdict({"p_start_ll_starters": 0.0, "zeros": 1.0},
                    {"p_start_ll_starters": 0.0, "zeros": 1.0})
    assert v["logloss_relative_gain"] == 0.0
    assert v["decision"] == "withdraw"


def test_the_guard_tolerance_is_v8as():
    """Reused unchanged so the two cycles' withdrawals are comparable."""
    mod = _driver()
    assert mod.GUARD_TOLERANCE == 0.005
    assert mod.LOGLOSS_MIN_RELATIVE_GAIN == 0.01
