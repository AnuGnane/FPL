"""The second currency: what a decision did to my title odds.

A captaincy that cost two points and no ground is a different week from one
that cost two points and the league. Everything here is about the *pairing* —
same seed, same n, same drift, one squad swapped — and about what happens
when the engine cannot answer.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.config import Config
from gaffer.review import PWIN_LANES, picks_from_squad, price_lanes

CFG = Config(entry_id=1, league_id=5, current_season="2026-27", sim_n=200)

MINE = {"xi": [100, 101], "bench": [102], "captain": 100, "vice": 101,
        "hits": 0, "chip": None}


class FakeSim:
    """A stand-in for ``LeagueSim`` carrying only what the pricing reads."""

    def __init__(self, p_win):
        self.p_win = p_win


def test_the_pick_dicts_carry_the_position_effective_picks_needs():
    """``league_sim.effective_picks`` rebuilds the multipliers from
    ``position`` — 1-11 started, 12-15 benched — because a stored week's own
    multipliers are chip arithmetic. A counterfactual squad without positions
    would fall through to the capped-multiplier branch and score its bench."""
    picks = picks_from_squad(MINE, {100: 7, 101: 8, 102: 9})
    assert [p["position"] for p in picks] == [1, 2, 12]
    assert [p["element"] for p in picks] == [7, 8, 9]
    assert picks[0]["is_captain"] is True
    assert picks[1]["is_vice_captain"] is True
    assert [p["multiplier"] for p in picks] == [2, 1, 0]


def test_a_player_with_no_element_is_dropped_rather_than_faked():
    """The sim keys on elements; a code with no element this season is a
    player who left the game, and inventing an id for him would price
    somebody else's squad."""
    picks = picks_from_squad(MINE, {100: 7, 101: 8})
    assert [p["element"] for p in picks] == [7, 8]


def test_only_the_two_lanes_the_engine_can_see_are_priced():
    """``effective_picks`` strips the bench and the chip, so those two lanes
    cannot move a win probability however they are simulated. Pricing them
    would be two Monte Carlo runs to rediscover a zero."""
    assert PWIN_LANES == ("transfers", "captaincy")


def test_each_priced_lane_is_my_odds_less_the_models():
    """The sign convention, matching ``delta_pts``: mine minus the model's,
    so a negative number is a decision that cost me. The baseline is the
    first run; every counterfactual follows it."""
    answers = iter([0.30, 0.25])

    def _sim(inputs, **kw):
        return FakeSim(next(answers))

    out, notice = price_lanes(
        CFG, _fake_inputs(), MINE,
        {"transfers": {"xi": [101], "bench": [], "captain": 101,
                       "vice": 101, "hits": 0, "chip": None}},
        {100: 7, 101: 8, 102: 9}, simulate=_sim)
    assert notice is None
    assert out["transfers"] == pytest.approx(5.0)


def test_every_run_uses_the_same_seed_and_the_same_n():
    """A paired comparison. Two draws of one seed differ by the seed, and a
    difference of seeds is not a difference of decisions (CONVENTIONS.md
    §1)."""
    seen = []

    def _sim(inputs, **kw):
        seen.append((kw["seed"], kw["n"], kw["rival_drift"]))
        return FakeSim(0.3)

    price_lanes(CFG, _fake_inputs(), MINE,
                {"captaincy": dict(MINE, captain=101)},
                {100: 7, 101: 8, 102: 9}, simulate=_sim)
    assert len(set(seen)) == 1
    assert seen[0][1] == 200


def test_an_unpriceable_lane_is_absent_rather_than_zero():
    out, _ = price_lanes(CFG, _fake_inputs(), MINE, {"transfers": None},
                         {100: 7}, simulate=lambda i, **k: FakeSim(0.3))
    assert "transfers" not in out


def test_a_league_with_no_me_in_it_prices_nothing_and_says_so():
    """``build_inputs`` flags my entry by id. If nothing in the standings is
    mine there is no squad to swap and the whole pricing is meaningless."""
    inputs = _fake_inputs(mine=False)
    out, notice = price_lanes(CFG, inputs, MINE, {"captaincy": MINE},
                              {100: 7}, simulate=lambda i, **k: FakeSim(0.3))
    assert out == {}
    assert "your entry is not in the simulated league" in notice


def test_an_engine_that_raises_degrades_to_points_only_with_a_notice():
    """Spec F2: the engine calls are isolated so a dead client or an absent
    parquet costs the second currency and nothing else."""
    def _boom(inputs, **kw):
        raise RuntimeError("no component frame for GW1")

    out, notice = price_lanes(CFG, _fake_inputs(), MINE, {"captaincy": MINE},
                              {100: 7}, simulate=_boom)
    assert out == {}
    assert "no component frame for GW1" in notice


def _fake_inputs(mine=True):
    """A ``SimInputs`` with two entries, one of them me."""
    from gaffer.league_sim import Entry, SimInputs

    return SimInputs(
        entries=[Entry(entry=1, name="You FC", total=100, picks=[],
                       is_me=mine),
                 Entry(entry=2, name="Rival", total=110, picks=[])],
        ep_by_element={7: 6.0, 8: 3.0, 9: 4.0},
        sigma_by_element={7: 5.0, 8: 4.0, 9: 4.0}, weeks_left=36)


def test_the_gameweek_grade_prices_its_lanes_when_the_components_exist(
        tmp_path, monkeypatch):
    """The whole path, over the ``test_web_league_sim`` fixture: banked
    components, a fake standings endpoint, and a real Monte Carlo."""
    from tests.test_web_league_sim import FakeClient, _artifacts

    monkeypatch.chdir(tmp_path)
    _artifacts(tmp_path)
    from gaffer.data import store
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    store.save(pd.DataFrame([
        {"season_idx": 4, "gw": 3, "code": 100, "element": 7,
         "position": "MID", "total_points": 9, "minutes": 90},
        {"season_idx": 4, "gw": 3, "code": 101, "element": 8,
         "position": "DEF", "total_points": 2, "minutes": 90},
    ]), "live/player_gw.parquet")

    from gaffer.league_sim import build_inputs
    inputs = build_inputs(CFG, FakeClient(), gw=3)
    out, notice = price_lanes(
        CFG, inputs, {"xi": [100], "bench": [101], "captain": 100,
                      "vice": 100, "hits": 0, "chip": None},
        {"captaincy": {"xi": [101], "bench": [100], "captain": 101,
                       "vice": 101, "hits": 0, "chip": None}},
        {100: 7, 101: 8})
    assert notice is None
    assert isinstance(out["captaincy"], float)


def test_a_gameweek_with_no_banked_components_is_absent_with_a_notice(
        tmp_path, monkeypatch):
    """GW1's case, and the one G1 checks for: ``reports/components_gw1.parquet``
    does not exist and never will, so GW1 is graded in points alone."""
    from tests.test_web_league_sim import FakeClient

    from gaffer.review import price_lanes_for_gw

    monkeypatch.chdir(tmp_path)

    out, notice = price_lanes_for_gw(CFG, FakeClient(), 1, MINE, {}, {})
    assert out == {}
    assert "GW1" in notice
