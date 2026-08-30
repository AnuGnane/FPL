"""The G1 driver's arithmetic and its hygiene.

The run itself is hours long and the orchestrator's job (CONVENTIONS.md §7).
What is testable here is the arm table, the verdict rule and the promise the
driver makes to the rest of the repo: it must not leave ``MINUTES_FEATURES``
mutated behind it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path("scripts/v8a_arms.py")


def _driver():
    """Import the script without running its ``main``."""
    spec = importlib.util.spec_from_file_location("v8a_arms", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_candidate_is_an_arm_of_its_own():
    """G1 ablates each F1 feature individually and each F2 variant as a
    block. Bundling two F1 features into one arm would make a withdrawal
    impossible to target."""
    from gaffer.features.engineer import (LEAGUE_CONGESTION_FEATURES,
                                          ROTATION_PRIOR_FEATURES,
                                          CONGESTION_FEATURES)

    arms = _driver().ARMS
    assert arms["baseline"] == []
    for col in ROTATION_PRIOR_FEATURES:
        assert arms[f"f1_{col}"] == [col]
    assert arms["f2_league"] == LEAGUE_CONGESTION_FEATURES
    assert arms["f2_cups"] == CONGESTION_FEATURES


def test_the_arm_feature_list_is_the_baseline_plus_the_arm():
    from gaffer.models.train import MINUTES_FEATURES

    mod = _driver()
    cols = mod.arm_features("f2_league")
    assert cols[:len(MINUTES_FEATURES)] == list(MINUTES_FEATURES)
    assert cols[len(MINUTES_FEATURES):] == mod.ARMS["f2_league"]


def test_the_driver_does_not_leave_minutes_features_mutated():
    import gaffer.models.train as tr

    before = list(tr.MINUTES_FEATURES)
    mod = _driver()
    mod.arm_features("f1_xi_churn_r5")
    assert list(tr.MINUTES_FEATURES) == before


@pytest.mark.parametrize(
    "zeros,haulers,all_,expect",
    [(1.060, 5.140, 1.980, "keep"),        # clearly better zeros, no cost
     (1.066, 5.140, 1.980, "withdraw"),    # under the 0.005 bar
     (1.050, 5.150, 1.980, "withdraw"),    # haulers regressed too far
     (1.050, 5.140, 1.992, "withdraw")])   # all-RMSE regressed too far
def test_the_verdict_rule_is_the_pre_registered_one(zeros, haulers, all_,
                                                    expect):
    mod = _driver()
    base = {"zeros": 1.070, "haulers": 5.145, "all": 1.986}
    arm = {"zeros": zeros, "haulers": haulers, "all": all_}
    assert mod.verdict(base, arm)["decision"] == expect


def test_a_tie_withdraws():
    """v5 discipline: an arm that measured level did not earn its column."""
    mod = _driver()
    base = {"zeros": 1.070, "haulers": 5.145, "all": 1.986}
    assert mod.verdict(base, dict(base))["decision"] == "withdraw"
