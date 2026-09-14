"""v18g §2.3 — the seam order of ``gather_inputs``, as behaviour.

Four rails (v5, v6, v8a and v8c) carried one verbatim copy each of a
source-text pin named ``test_run_advise_still_orders_every_protected_seam``,
because in their day ``run_advise`` could not be called. Since v17g §5 it
can, through ``tests/gather_harness.py``, which records the order every
seam was called in. This file is the union of what those four copies
asserted, over what the run did; the copies are gone. The one chain that
straddles the gather/build split — the league fetch before the tilt before
the pool — stays a text pin in ``tests/test_advise_source.py``, and the
tilt reaching the pool is behaviour in ``tests/test_advise.py``.

Mutation shown at the gate: swapping the ``pen_priors`` and
``news_availability`` lines in ``gather_inputs`` fails the first test.
"""
from __future__ import annotations

import pandas as pd

from gaffer.config import Config
from tests.gather_harness import gather

SEAMS = ("pen_priors", "news_availability", "Predictions.components",
         "write_shadow", "blend_attacking_odds", "apply_calibration",
         "ep_matrix")
"""The seven seams, in the order the four copies pinned: the penalty priors
feed the prediction, the news pass feeds it too, the shadow row is taken
off the raw components before the odds blend rewrites them, and the EP
matrix is assembled from the calibrated blend."""


def test_the_seven_seams_are_called_in_the_pinned_order(monkeypatch):
    _, order = gather(monkeypatch)
    positions = [order.index(name) for name in SEAMS]
    assert positions == sorted(positions), list(zip(SEAMS, positions))


def test_each_seam_is_called_exactly_once(monkeypatch):
    """A seam called twice would satisfy an ``index`` ordering by accident."""
    _, order = gather(monkeypatch)
    assert [order.count(name) for name in SEAMS] == [1] * len(SEAMS)


def test_the_league_is_read_after_the_ep_matrix_is_assembled(monkeypatch):
    """The v8c copy pinned ``fetch_rival_entries`` before the tilt; the tilt
    is in the build half, so the gather-side half of that claim is that the
    league block runs after the EP the tilt will shape exists."""
    _, order = gather(monkeypatch, cfg=Config(entry_id=1, league_id=5),
                      fetch_rival_entries=pd.DataFrame())
    assert order.index("ep_matrix") < order.index("fetch_rival_entries")


def test_a_failing_player_props_fetch_costs_the_blend_and_nothing_else(
        monkeypatch, capsys):
    """The copies pinned an ``except Exception`` within a few hundred
    characters of the blend. What it guards is the goalscorer-odds request:
    when that raises, the blend still runs — on no market — and the run
    reaches the end. The key here is a placeholder, never the real one."""
    class _Odds:
        def __init__(self, key):
            pass

        def get_epl_odds(self):
            return [{"id": "x"}]

        def get_player_goalscorer_odds(self, event_ids):
            raise RuntimeError("quota")

    def unusable(*a, **kw):
        raise RuntimeError("no odds frame either")

    cfg = Config(entry_id=1, league_id=0, odds_api_key="placeholder",
                 player_props=True)
    inputs, order = gather(monkeypatch, cfg=cfg, OddsClient=_Odds,
                           odds_frame=unusable, next_gw_event_ids=[])
    assert "player props unusable" in capsys.readouterr().out
    assert inputs.comp is not None
    assert order.index("Predictions.components") < order.index(
        "blend_attacking_odds") < order.index("ep_matrix")
