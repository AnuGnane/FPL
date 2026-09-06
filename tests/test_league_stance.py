"""v15 §3.2 — the manual stance override, at full tilt."""

from pathlib import Path

import pytest

from gaffer.league_mode import (STANCES, LeagueParams, Strategy,
                                apply_stance)


def _computed() -> Strategy:
    return Strategy(lam=0.31, gap=12, weeks_left=30, stance="chase",
                    rival_name="Ten Hag Hive", z=1.1, sigma_m=14.0,
                    cover_weights={7: 0.6})


def test_the_four_stances_are_named():
    assert STANCES == ("auto", "chase", "defend", "neutral")


def test_auto_returns_the_computed_strategy_untouched():
    s = apply_stance(_computed(), "auto", LeagueParams(lambda_cap=0.5))
    assert (s.lam, s.stance, s.source) == (0.31, "chase", "auto")


def test_chase_pins_lambda_to_plus_cap():
    s = apply_stance(_computed(), "chase", LeagueParams(lambda_cap=0.5))
    assert (s.lam, s.stance, s.source) == (0.5, "chase", "manual")


def test_defend_pins_lambda_to_minus_cap():
    s = apply_stance(_computed(), "defend", LeagueParams(lambda_cap=0.5))
    assert (s.lam, s.stance, s.source) == (-0.5, "defend", "manual")


def test_neutral_is_exactly_zero():
    s = apply_stance(_computed(), "neutral", LeagueParams(lambda_cap=0.5))
    assert s.lam == 0.0 and s.stance == "neutral" and s.source == "manual"


def test_the_cap_is_the_configured_one():
    s = apply_stance(_computed(), "chase", LeagueParams(lambda_cap=0.2))
    assert s.lam == 0.2


def test_no_params_means_the_pinned_cap():
    from gaffer.league_mode import LAMBDA_CAP

    assert apply_stance(_computed(), "defend").lam == -LAMBDA_CAP


def test_manual_keeps_the_computed_gap_rival_and_cover():
    s = apply_stance(_computed(), "defend", LeagueParams(lambda_cap=0.5))
    assert s.gap == 12 and s.weeks_left == 30
    assert s.rival_name == "Ten Hag Hive"
    assert s.z == 1.1 and s.sigma_m == 14.0
    assert s.cover_weights == {7: 0.6}


def test_the_input_is_not_mutated():
    before = _computed()
    apply_stance(before, "neutral")
    assert before.lam == 0.31 and before.stance == "chase"


def test_an_unknown_stance_is_refused_by_name():
    with pytest.raises(ValueError, match="stance"):
        apply_stance(_computed(), "attack")


def test_source_defaults_to_auto_on_a_bare_strategy():
    assert Strategy(0.0, 0, 1, "neutral", "the field").source == "auto"


def test_advise_applies_the_stance_after_computing_it():
    """The one protected-file change of the cycle, pinned by text: the call
    sits after ``compute_strategy`` in the league block."""
    text = Path("src/gaffer/advise.py").read_text()
    assert "apply_stance(" in text
    assert text.index("compute_strategy(") < text.index("apply_stance(")
