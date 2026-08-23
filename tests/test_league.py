import httpx

from gaffer.data.league import (
    effective_ownership,
    fetch_rival_entries,
    fetch_rival_picks,
)

RIVAL_PICKS = {
    101: [{"element": 1, "multiplier": 2}, {"element": 2, "multiplier": 1}],
    102: [{"element": 1, "multiplier": 1}, {"element": 3, "multiplier": 0}],
    103: [{"element": 2, "multiplier": 1}],
}


def test_effective_ownership_counts_captaincy_and_bench():
    eo = effective_ownership(RIVAL_PICKS)
    assert eo[1] == 100.0   # (2 + 1) / 3 rivals * 100
    assert eo[2] == round(2 / 3 * 100, 1)
    assert eo[3] == 0.0     # benched (multiplier 0) contributes nothing


def _standing(entry: int, rank: int) -> dict:
    return {
        "entry": entry,
        "entry_name": f"Team {entry}",
        "player_name": f"Player {entry}",
        "rank": rank,
        "last_rank": rank,
        "total": 100 - rank,
        "event_total": 50 - rank,
        "id": entry * 10,           # extra column that must be dropped
    }


class _FakeStandingsClient:
    """Two pages of classic-league standings; no network."""

    def __init__(self):
        self.pages_requested = []

    def get_league_standings(self, league_id, page=1):
        self.pages_requested.append(page)
        if page == 1:
            return {"standings": {"has_next": True,
                                  "results": [_standing(7, 1), _standing(8, 2)]}}
        return {"standings": {"has_next": False, "results": [_standing(9, 3)]}}


def test_fetch_rival_entries_paginates_and_excludes_self():
    client = _FakeStandingsClient()
    df = fetch_rival_entries(client, league_id=123, exclude_entry=8)

    assert client.pages_requested == [1, 2]           # followed has_next
    assert list(df["entry"]) == [7, 9]                # self excluded
    assert list(df.columns) == ["entry", "entry_name", "player_name", "rank",
                                "last_rank", "total", "event_total"]
    assert df.iloc[0]["entry_name"] == "Team 7"


class _FakePicksClient:
    """One entry 404s (picks not public yet / joined late), one succeeds."""

    def get_entry_picks(self, entry_id, gw):
        if entry_id == 404:
            raise httpx.HTTPStatusError(
                "Not Found",
                request=httpx.Request("GET", "http://x"),
                response=httpx.Response(404),
            )
        return {"picks": [{"element": 5, "multiplier": 2}]}


def test_fetch_rival_picks_skips_unavailable_entries():
    picks = fetch_rival_picks(_FakePicksClient(), [404, 7], gw=3)

    assert 404 not in picks
    assert picks == {7: [{"element": 5, "multiplier": 2}]}


def test_effective_ownership_empty():
    assert effective_ownership({}) == {}
