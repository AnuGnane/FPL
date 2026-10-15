"""scripts/league_blend.py, candidate 9's reading (holiday F-72).

Synthetic standings pages: a league where I trail the leader by a distance
the dial chases, one where I lead by a distance it defends, and one level
enough to read neutral. The client is a stand-in serving those pages, so no
network is touched.
"""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, "scripts")

import league_blend  # noqa: E402 — scripts/ is not a package; the path insert must come first

ME = 7


def _page(my_total: int, rival_totals: list[int]) -> dict:
    results = [{"entry": ME, "entry_name": "Mine", "player_name": "Me",
                "rank": 0, "last_rank": 0, "total": my_total,
                "event_total": 50}]
    results += [{"entry": 100 + i, "entry_name": f"R{i}",
                 "player_name": f"Rival {i}", "rank": 0, "last_rank": 0,
                 "total": t, "event_total": 50}
                for i, t in enumerate(rival_totals)]
    return {"standings": {"results": results}}


CHASE = _page(1000, [1150, 990])
DEFEND = _page(1150, [1000, 990])
LEVEL = _page(1000, [1000, 1000])


class _Client:
    def __init__(self, leagues: list[tuple[int, int, object]], gw: int = 30):
        self.leagues = leagues
        self.gw = gw

    def get_entry(self, entry_id):
        return {"summary_overall_points": 1000, "current_event": self.gw,
                "leagues": {"classic": [
                    {"id": lid, "name": f"L{lid}", "league_type": "x",
                     "rank_count": n} for lid, n, _ in self.leagues]
                    + [{"id": 1, "name": "Overall", "league_type": "s",
                        "rank_count": 9_000_000}]}}

    def get_league_standings(self, league_id, page=1):
        body = next(b for lid, _, b in self.leagues if lid == league_id)
        if isinstance(body, Exception):
            raise body
        return body


def _cfg(focus: int):
    return SimpleNamespace(entry_id=ME, league_id=focus)


def _reading(leagues, focus):
    return league_blend.blend_reading(_Client(leagues), _cfg(focus))


def test_the_synthetic_pages_read_as_the_stances_they_were_built_for():
    params = league_blend.LeagueParams()
    stance = {name: league_blend.league_strategy(
        page["standings"]["results"], my_entry=ME, my_total=0, gw=30,
        params=params)[1] for name, page in
        [("chase", CHASE), ("defend", DEFEND), ("neutral", LEVEL)]}
    assert stance == {"chase": "chase", "defend": "defend",
                      "neutral": "neutral"}


def test_two_leagues_pulling_against_the_focus_earn_a_replay():
    out = _reading([(10, 20, CHASE), (11, 20, DEFEND), (12, 20, DEFEND)],
                   focus=10)
    assert out["disagree"] == [11, 12]
    assert out["disagree_share"] == 1.0
    assert out["focus_lam"] > 0 > out["merged_lam"] - out["focus_lam"]
    assert out["gap"] >= league_blend.MERGE_GAP
    assert out["verdict"] == league_blend.REPLAY


def test_one_league_against_the_focus_is_not_enough():
    out = _reading([(10, 20, CHASE), (11, 20, DEFEND), (12, 20, LEVEL)],
                   focus=10)
    assert out["disagree"] == [11]
    assert out["disagree_share"] == 0.5
    assert out["verdict"] == league_blend.FOCUS_IS_BLEND


def test_a_big_league_weighs_no_more_than_the_focus():
    """Capped at the focus's entry count, two defending leagues of 500 pull
    exactly as hard as two of 20 would."""
    small = _reading([(10, 20, CHASE), (11, 20, DEFEND), (12, 20, DEFEND)],
                     focus=10)
    big = _reading([(10, 20, CHASE), (11, 500, DEFEND), (12, 500, DEFEND)],
                   focus=10)
    assert big["merged_lam"] == small["merged_lam"]


def test_a_lone_league_is_its_own_blend():
    out = _reading([(10, 20, CHASE)], focus=10)
    assert out["n"] == 1
    assert out["merged_lam"] == out["focus_lam"]
    assert out["disagree"] == [] and out["disagree_share"] is None
    assert out["verdict"] == league_blend.FOCUS_IS_BLEND


def test_an_unreadable_page_is_named_and_the_rest_still_blend():
    out = _reading([(10, 20, CHASE), (11, 20, {"standings": {}}),
                    (12, 20, httpx.ConnectError("refused"))], focus=10)
    assert [u["id"] for u in out["unread"]] == [11, 12]
    assert out["n"] == 1
    assert out["verdict"] == league_blend.FOCUS_IS_BLEND


def test_a_focus_whose_page_will_not_read_decides_nothing():
    out = _reading([(10, 20, {"standings": {}}), (11, 20, DEFEND)], focus=10)
    assert out["verdict"] == "none"
    assert "not among" in out["reason"]


def test_a_league_with_no_rival_on_its_page_is_unread_not_neutral():
    out = _reading([(10, 20, CHASE), (11, 2, _page(1000, []))], focus=10)
    assert [u["id"] for u in out["unread"]] == [11]


def test_no_private_league_prints_a_reason():
    out = _reading([], focus=10)
    assert out == {"n": 0, "verdict": "none",
                   "reason": "no started private league with a rival in it"}


@pytest.mark.parametrize("cfg, needle", [
    (None, "no readable config.toml"),
    (SimpleNamespace(entry_id=0, league_id=0), "no fpl.entry_id"),
])
def test_main_prints_one_line_and_exits_clean_without_a_league_to_read(
        monkeypatch, capsys, cfg, needle):
    def load():
        if cfg is None:
            raise league_blend.GafferError("no config.toml")
        return cfg

    monkeypatch.setattr(league_blend, "load_config", load)
    assert league_blend.main() == 0
    (line,) = capsys.readouterr().out.splitlines()
    assert line.startswith("LEAGUE_BLEND ")
    payload = json.loads(line.removeprefix("LEAGUE_BLEND "))
    assert payload["verdict"] == "none" and needle in payload["reason"]
