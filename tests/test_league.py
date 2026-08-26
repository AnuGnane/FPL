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


class _EmptyStandingsClient:
    """A league with no standings yet (freshly created / pre-GW1)."""

    def get_league_standings(self, league_id, page=1):
        return {"standings": {"has_next": False, "results": []}}


def test_fetch_rival_entries_handles_empty_league():
    df = fetch_rival_entries(_EmptyStandingsClient(), league_id=1,
                             exclude_entry=8)
    assert df.empty
    assert list(df.columns) == [
        "entry", "entry_name", "player_name", "rank", "last_rank",
        "total", "event_total"]
    # downstream: no rivals -> no picks -> no EO, no crash
    assert fetch_rival_picks(_FakePicksClient(), df["entry"].tolist(), gw=3) == {}
    assert effective_ownership({}) == {}


# --- v4d: entry history for the sigma estimator ----------------------------

import json

from gaffer.api.client import FPLClient
from gaffer.data.league import fetch_rival_history


def _history_transport(points_by_entry: dict[int, list[int]], calls: list):
    """entry/{id}/history/ for a handful of entries; no network."""

    def handler(request: httpx.Request) -> httpx.Response:
        parts = request.url.path.rstrip("/").split("/")
        entry = int(parts[-2])
        calls.append(entry)
        pts = points_by_entry.get(entry)
        if pts is None:
            return httpx.Response(404, json={"detail": "Not found."})
        current = [{"event": i + 1, "points": p,
                    "total_points": sum(pts[:i + 1])}
                   for i, p in enumerate(pts)]
        return httpx.Response(200, json={"current": current, "past": [],
                                         "chips": []})

    return httpx.MockTransport(handler)


def test_fetch_rival_history_returns_entry_gw_points(tmp_path):
    calls: list[int] = []
    client = FPLClient(raw_dir=tmp_path / "raw",
                       transport=_history_transport({1: [50, 60, 70],
                                                     7: [40, 80, 55]}, calls))
    df = fetch_rival_history(client, [1, 7], gw=3,
                             raw_dir=tmp_path / "league")
    assert list(df.columns) == ["entry", "gw", "points"]
    assert len(df) == 6
    assert set(df["entry"]) == {1, 7}
    assert int(df[(df["entry"] == 7) & (df["gw"] == 2)]["points"].iloc[0]) == 80


def test_fetch_rival_history_stops_at_the_requested_gameweek(tmp_path):
    """A GW that is underway must not leak a half-scored week into sigma."""
    calls: list[int] = []
    client = FPLClient(raw_dir=tmp_path / "raw",
                       transport=_history_transport({1: [50, 60, 70]}, calls))
    df = fetch_rival_history(client, [1], gw=2, raw_dir=tmp_path / "league")
    assert set(df["gw"]) == {1, 2}


def test_fetch_rival_history_skips_an_entry_with_no_history(tmp_path):
    calls: list[int] = []
    client = FPLClient(raw_dir=tmp_path / "raw", retries=1,
                       transport=_history_transport({1: [50, 60]}, calls))
    df = fetch_rival_history(client, [1, 999], gw=2,
                             raw_dir=tmp_path / "league")
    assert set(df["entry"]) == {1}


def test_fetch_rival_history_caches_per_gameweek(tmp_path):
    calls: list[int] = []
    cache = tmp_path / "league"
    client = FPLClient(raw_dir=tmp_path / "raw",
                       transport=_history_transport({1: [50, 60]}, calls))
    first = fetch_rival_history(client, [1], gw=2, raw_dir=cache)
    assert calls == [1]
    assert json.loads((cache / "history-gw2.json").read_text())
    second = fetch_rival_history(client, [1], gw=2, raw_dir=cache)
    assert calls == [1]                       # served from disk, no re-fetch
    assert second.equals(first)


def test_fetch_rival_history_of_nobody_is_an_empty_frame(tmp_path):
    calls: list[int] = []
    client = FPLClient(raw_dir=tmp_path / "raw",
                       transport=_history_transport({}, calls))
    df = fetch_rival_history(client, [], gw=1, raw_dir=tmp_path / "league")
    assert df.empty and list(df.columns) == ["entry", "gw", "points"]
