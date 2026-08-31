"""``build_inputs``: what the simulation is fed, and what it does without.

The seam between artifacts on disk and the pure engine. Everything here is
about degradation — a missing field store, a rival whose picks are private, a
gameweek nobody has advised — because every one of those is a Tuesday, not an
outage.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.artifacts import COMPONENT_COLS
from gaffer.config import Config
from gaffer.data import store
from gaffer.errors import GafferError
from gaffer.league_sim import (build_inputs, element_eps,
                               field_rate_from_sample)

STANDINGS = {"standings": {"has_next": False, "results": [
    {"entry": 1, "entry_name": "You FC", "player_name": "Me", "rank": 2,
     "last_rank": 2, "total": 106, "event_total": 55},
    {"entry": 2, "entry_name": "Ten Hag Hive", "player_name": "Riv",
     "rank": 1, "last_rank": 1, "total": 190, "event_total": 60}]}}

MY_PICKS = {"picks": [{"element": 7, "position": 1, "multiplier": 2},
                      {"element": 8, "position": 2, "multiplier": 1}]}
RIVAL_PICKS = {"picks": [{"element": 8, "position": 1, "multiplier": 2}]}


class FakeClient:
    def __init__(self, private=()):
        self.private = set(private)

    def get_league_standings(self, league_id, page=1):
        return STANDINGS

    def get_entry_picks(self, entry_id, gw):
        if entry_id in self.private:
            raise RuntimeError("private entry")
        return MY_PICKS if entry_id == 1 else RIVAL_PICKS


def _comp() -> pd.DataFrame:
    rows = []
    for gw in (3, 4):
        for code, element, ep, p_play, p60 in ((100, 7, 6.0, 0.95, 0.9),
                                               (101, 8, 3.0, 0.8, 0.6)):
            row = {c: float("nan") for c in COMPONENT_COLS}
            row.update({"code": code, "element": element, "gw": gw, "ep": ep,
                        "p_play": p_play, "p60": p60, "name": "x",
                        "position": "MID", "team_code": 1, "team_name": "T",
                        "opp_code": 2, "opp_name": "O", "was_home": True,
                        "kickoff_time": "2026-09-12T14:00:00Z"})
            rows.append(row)
    return pd.DataFrame(rows, columns=COMPONENT_COLS)


@pytest.fixture()
def here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr("gaffer.data.field.RAW_FIELD",
                        tmp_path / "data/raw/field")
    return tmp_path


def test_the_ep_per_element_is_the_mean_over_the_horizon():
    """Two gameweeks in the frame, so a player's per-*week* rate is his total
    over two. A sum here would make a three-week horizon look like a
    three-times-better squad."""
    out = element_eps(_comp())
    assert out[7] == pytest.approx(6.0)
    assert out[8] == pytest.approx(3.0)


def test_a_double_gameweek_counts_twice_in_one_week():
    comp = pd.concat([_comp(), _comp().head(1)], ignore_index=True)
    assert element_eps(comp)[7] == pytest.approx(9.0)


def test_an_empty_component_frame_is_an_empty_map():
    assert element_eps(pd.DataFrame(columns=COMPONENT_COLS)) == {}


def test_the_field_rate_is_the_mean_squad_over_the_sample():
    """One entry captains a 6.0 player (12) plus a 3.0 (15); the other plays
    the 3.0 alone (3). The template is the average manager, so 9."""
    sample = [[{"element": 7, "multiplier": 2},
               {"element": 8, "multiplier": 1}],
              [{"element": 8, "multiplier": 1}]]
    assert field_rate_from_sample(sample, {7: 6.0, 8: 3.0}) \
        == pytest.approx(9.0)


def test_no_sample_is_none_rather_than_zero():
    """``None`` turns drift off; 0.0 would tell every rival to converge on a
    squad that scores nothing, which is the opposite claim."""
    assert field_rate_from_sample(None, {7: 6.0}) is None
    assert field_rate_from_sample([], {7: 6.0}) is None


def test_the_inputs_name_me_and_every_rival(here, monkeypatch):
    monkeypatch.setattr("gaffer.artifacts.latest_gw", lambda: 5)
    monkeypatch.setattr("gaffer.artifacts.load_components",
                        lambda gw: _comp())
    ins = build_inputs(Config(entry_id=1, league_id=5), FakeClient())
    assert [e.entry for e in ins.entries] == [1, 2]
    assert [e.is_me for e in ins.entries] == [True, False]
    assert ins.entries[1].total == 190


def test_the_squads_are_the_last_scored_gameweeks(here, monkeypatch):
    """Picks are public for finished gameweeks only, so the plan gameweek
    minus one — the same rule ``league.py::_last_scored_gw`` uses."""
    seen = []

    class _Client(FakeClient):
        def get_entry_picks(self, entry_id, gw):
            seen.append(gw)
            return super().get_entry_picks(entry_id, gw)

    monkeypatch.setattr("gaffer.artifacts.latest_gw", lambda: 5)
    monkeypatch.setattr("gaffer.artifacts.load_components",
                        lambda gw: _comp())
    build_inputs(Config(entry_id=1, league_id=5), _Client())
    assert set(seen) == {4}


def test_weeks_left_counts_the_season_out_from_the_plan_gameweek(here,
                                                                 monkeypatch):
    monkeypatch.setattr("gaffer.artifacts.latest_gw", lambda: 5)
    monkeypatch.setattr("gaffer.artifacts.load_components",
                        lambda gw: _comp())
    ins = build_inputs(Config(entry_id=1, league_id=5), FakeClient())
    assert ins.weeks_left == 34          # gameweeks 5 through 38


def test_a_private_rival_keeps_his_place_with_an_empty_squad(here,
                                                             monkeypatch):
    """He is still in the league and his total still counts; he simply has no
    modellable squad, and the sigma floor gives him a season anyway."""
    monkeypatch.setattr("gaffer.artifacts.latest_gw", lambda: 5)
    monkeypatch.setattr("gaffer.artifacts.load_components",
                        lambda gw: _comp())
    ins = build_inputs(Config(entry_id=1, league_id=5),
                       FakeClient(private=(2,)))
    assert [e.entry for e in ins.entries] == [1, 2]
    assert ins.entries[1].picks == []


def test_no_field_sample_turns_drift_off(here, monkeypatch):
    monkeypatch.setattr("gaffer.artifacts.latest_gw", lambda: 5)
    monkeypatch.setattr("gaffer.artifacts.load_components",
                        lambda gw: _comp())
    ins = build_inputs(Config(entry_id=1, league_id=5), FakeClient())
    assert ins.field_rate is None


def test_a_banked_field_sample_becomes_the_template(here, monkeypatch):
    from gaffer.data.field import save_field_sample

    save_field_sample([[{"element": 7, "position": 1, "multiplier": 2}]],
                      4, "2026-27")
    monkeypatch.setattr("gaffer.artifacts.latest_gw", lambda: 5)
    monkeypatch.setattr("gaffer.artifacts.load_components",
                        lambda gw: _comp())
    ins = build_inputs(Config(entry_id=1, league_id=5,
                              current_season="2026-27"), FakeClient())
    assert ins.field_rate == pytest.approx(12.0)


def test_no_advice_at_all_is_a_readable_refusal(here, monkeypatch):
    monkeypatch.setattr("gaffer.artifacts.latest_gw", lambda: None)
    with pytest.raises(GafferError, match="gaffer advise"):
        build_inputs(Config(entry_id=1, league_id=5), FakeClient())


def test_no_league_id_is_a_readable_refusal(here, monkeypatch):
    monkeypatch.setattr("gaffer.artifacts.latest_gw", lambda: 5)
    with pytest.raises(GafferError, match="league_id"):
        build_inputs(Config(entry_id=1, league_id=0), FakeClient())
