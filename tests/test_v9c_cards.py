"""The red-card term, which has been zero since the day it was written.

``card_penalty`` reads ``rc_r38`` and multiplies it by -3. ``ROLL_STATS``
rolled ``yc`` and not ``rc``, so the key never existed, and ``_rate``'s
defensive ``row.get(key, 0.0)`` — written to survive a player with no card
history — turned a missing *column* into a clean zero for every player in
every gameweek. A defence against sparse data absorbed a defect in the
feature list, and nothing failed.

These tests are the ones that would have caught it: not "does the formula
multiply by -3" (it always did) but "is there a number here to multiply".
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.data.live import CANONICAL_COLS
from gaffer.features.engineer import ROLL_STATS, add_player_rolling
from gaffer.models.components import card_penalty


def _sent_off_then_played(n: int = 6) -> pd.DataFrame:
    """One player, one red card in his first match, five clean ones after."""
    return pd.DataFrame({
        "code": [1] * n,
        "season_idx": [3] * n,
        "gw": list(range(1, n + 1)),
        "rc": [1.0] + [0.0] * (n - 1),
        "yc": [0.0] * n,
        "minutes": [90.0] * n,
    })


def test_rc_is_rolled_like_every_other_disciplinary_stat():
    """The one-line finding. ``yc`` was there; ``rc`` was not."""
    assert "rc" in ROLL_STATS
    assert "yc" in ROLL_STATS


def test_rc_is_stored_so_the_feature_costs_no_new_ingest():
    """``data/live.py`` has renamed ``red_cards -> rc`` and banked it since
    the store was written. This was never a missing *column*, only a missing
    list entry."""
    assert "rc" in CANONICAL_COLS


def test_the_rolling_window_exists_and_is_shifted_off_the_current_row():
    rolled = add_player_rolling(_sent_off_then_played())
    assert "rc_r38" in rolled.columns
    # Row 0 sees no prior match at all.
    assert pd.isna(rolled["rc_r38"].iloc[0])
    # Row 1 sees exactly the sending-off.
    assert rolled["rc_r38"].iloc[1] == 1.0
    # And it decays as clean matches accumulate, rather than sticking.
    assert rolled["rc_r38"].iloc[5] < rolled["rc_r38"].iloc[1]


def test_the_red_term_now_actually_fires():
    """The whole finding, in one assertion. Before this cycle both rows
    returned the same number."""
    sent_off = pd.Series({"yc_r38": 0.0, "rc_r38": 0.2})
    clean = pd.Series({"yc_r38": 0.0, "rc_r38": 0.0})
    assert card_penalty(sent_off) < card_penalty(clean)
    # -3 * 0.2, read through float arithmetic: approx, not ==.
    assert card_penalty(sent_off) == pytest.approx(-0.6)


def test_a_player_with_no_card_history_is_still_a_clean_zero():
    """``_rate``'s NaN guard is still doing its real job — the one it was
    written for — now that it is no longer covering for a missing column."""
    assert card_penalty(pd.Series({"yc_r38": float("nan"),
                                   "rc_r38": float("nan")})) == 0.0


def test_no_model_feature_list_gains_a_card_column(monkeypatch):
    """Plan A2, asserted rather than assumed: the five new columns reach the
    deterministic ``card_penalty`` and nothing that is fitted. If a future
    cycle puts an ``rc_*`` column into a model's inputs, this cycle's whole
    argument for a cheap arm stops holding, and this is where that is
    discovered."""
    from gaffer.models.attacking import ATTACK_FEATURES
    from gaffer.models.components import (BONUS_FEATURES, DEFCON_FEATURES,
                                          SAVES_FEATURES)
    from gaffer.models.team import TEAM_FEATURES
    from gaffer.models.train import MINUTES_FEATURES

    for name, cols in (("minutes", MINUTES_FEATURES),
                       ("attacking", ATTACK_FEATURES),
                       ("defcon", DEFCON_FEATURES),
                       ("saves", SAVES_FEATURES),
                       ("bonus", BONUS_FEATURES),
                       ("team", TEAM_FEATURES)):
        assert not [c for c in cols if c.startswith("rc_")], name


def test_feature_columns_names_the_new_block_so_advise_strips_it():
    """``advise.py:548`` strips ``feature_columns()`` off the training frame
    before re-deriving. A rolled column missing from that list would survive
    the strip and be re-derived beside itself, and pandas would hand every
    later ``df[col]`` a two-column frame."""
    from gaffer.features.engineer import feature_columns

    assert "rc_r38" in feature_columns()
