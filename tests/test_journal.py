"""The decision journal: what the model said against what you actually did.

A computed join, never manual entry (spec §6.4). Source A is the banked advice
history, source B is the FPL entry API, and the scoring is realized points of
each side's XI and captain.
"""

import json

import pandas as pd
import pytest

from gaffer.artifacts import ADVICE_HISTORY
from gaffer.data import store
from gaffer.journal import (JOURNAL_PATH, build_journal, latest_run_per_gw,
                            xi_points)


class FakeClient:
    def __init__(self, picks):
        self._picks = picks
        self.asked = []

    def get_entry_picks(self, entry_id, gw):
        self.asked.append((entry_id, gw))
        if gw not in self._picks:
            raise RuntimeError(f"no picks for GW{gw}")
        return {"picks": self._picks[gw]}


def _advice(gw, xi_codes, captain_code, buys=()):
    return {
        "gw": gw,
        "xi": [{"code": c, "name": f"P{c}"} for c in xi_codes],
        "captain": {"code": captain_code, "name": f"P{captain_code}"},
        "buys": [{"code": c, "name": f"P{c}"} for c in buys],
        "sells": [],
    }


@pytest.fixture()
def tree(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    ADVICE_HISTORY.mkdir(parents=True, exist_ok=True)
    (ADVICE_HISTORY / "gw3-2026-08-20T09:00:00.json").write_text(
        json.dumps(_advice(3, [1, 2], 1)))
    (ADVICE_HISTORY / "gw3-2026-08-21T09:00:00.json").write_text(
        json.dumps(_advice(3, [1, 3], 3, buys=[3])))
    store.save(pd.DataFrame([
        {"code": 1, "gw": 3, "total_points": 4, "value": 100},
        {"code": 2, "gw": 3, "total_points": 2, "value": 50},
        {"code": 3, "gw": 3, "total_points": 9, "value": 80},
    ]), "live/player_gw.parquet")
    store.save(pd.DataFrame([
        {"code": 1, "element": 11, "name": "P1", "position": "MID",
         "team_id": 1, "team_code": 300, "now_cost": 100, "status": "a",
         "news": "", "chance_of_playing": None, "selected_by_percent": 1.0,
         "form": 1.0, "points_per_game": 1.0, "ep_next": 1.0,
         "price_change_percent": 0.0, "price_change_calibrating": False,
         "penalties_order": None, "direct_freekicks_order": None,
         "corners_and_indirect_freekicks_order": None},
        {"code": 2, "element": 12, "name": "P2", "position": "DEF",
         "team_id": 1, "team_code": 300, "now_cost": 50, "status": "a",
         "news": "", "chance_of_playing": None, "selected_by_percent": 1.0,
         "form": 1.0, "points_per_game": 1.0, "ep_next": 1.0,
         "price_change_percent": 0.0, "price_change_calibrating": False,
         "penalties_order": None, "direct_freekicks_order": None,
         "corners_and_indirect_freekicks_order": None},
        {"code": 3, "element": 13, "name": "P3", "position": "FWD",
         "team_id": 1, "team_code": 300, "now_cost": 80, "status": "a",
         "news": "", "chance_of_playing": None, "selected_by_percent": 1.0,
         "form": 1.0, "points_per_game": 1.0, "ep_next": 1.0,
         "price_change_percent": 0.0, "price_change_calibrating": False,
         "penalties_order": None, "direct_freekicks_order": None,
         "corners_and_indirect_freekicks_order": None},
    ]), "live/players.parquet")
    return tmp_path


def test_xi_points_doubles_the_captain():
    assert xi_points([1, 2], 1, {1: 4, 2: 2}) == 10
    assert xi_points([1, 2], 2, {1: 4, 2: 2}) == 8


def test_xi_points_treats_an_unscored_player_as_zero():
    assert xi_points([1, 9], 1, {1: 4}) == 8


def test_the_newest_run_of_a_gameweek_is_the_one_scored(tree):
    runs = latest_run_per_gw()
    assert set(runs) == {3}
    # Friday's re-run, not Thursday's: it is the last thing the model said
    # before that deadline.
    assert runs[3]["captain"]["code"] == 3


def test_the_journal_scores_the_model_against_what_you_actually_did(tree):
    client = FakeClient({3: [{"element": 11, "is_captain": True,
                              "multiplier": 2, "position": 1},
                             {"element": 12, "is_captain": False,
                              "multiplier": 1, "position": 2}]})
    out = build_journal(client, entry_id=7)
    row = out["rows"][0]
    assert row["gw"] == 3
    # Model: P1 (4) + P3 (9) with P3 captained -> 4 + 9 + 9 = 22
    assert row["model_pts"] == 22
    # Actual: P1 (4, captained) + P2 (2) -> 4 + 4 + 2 = 10
    assert row["actual_pts"] == 10
    assert row["delta"] == 12
    assert row["model_captain"] == "P3"
    assert row["actual_captain"] == "P1"


def test_the_cumulative_series_runs_alongside_the_rows(tree):
    client = FakeClient({3: [{"element": 11, "is_captain": True,
                              "multiplier": 2, "position": 1}]})
    out = build_journal(client, entry_id=7)
    assert out["cumulative"] == [{"gw": 3, "model": 22, "actual": 8,
                                  "delta": 14}]


def test_the_model_transfers_are_listed(tree):
    client = FakeClient({3: [{"element": 11, "is_captain": True,
                              "multiplier": 2, "position": 1}]})
    out = build_journal(client, entry_id=7)
    assert out["rows"][0]["model_buys"] == ["P3"]


def test_a_gameweek_the_api_cannot_answer_is_skipped_not_fatal(tree):
    client = FakeClient({})
    out = build_journal(client, entry_id=7)
    assert out["rows"] == [] and out["cumulative"] == []


def test_a_gameweek_with_no_results_yet_is_skipped(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    ADVICE_HISTORY.mkdir(parents=True, exist_ok=True)
    (ADVICE_HISTORY / "gw9-2026-08-20T09:00:00.json").write_text(
        json.dumps(_advice(9, [1], 1)))
    out = build_journal(FakeClient({}), entry_id=7)
    assert out["rows"] == []


def test_a_cold_clone_builds_an_empty_journal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    out = build_journal(FakeClient({}), entry_id=7)
    assert out == {"rows": [], "cumulative": [], "built_at": out["built_at"]}


# --- the run that was current *before* the deadline -------------------------
#
# The journal asks "what did the model say going into that gameweek". A run
# banked after kickoff knows the team news, and scoring it against what you
# played flatters the model with information you never had.


def _straddling(tmp_path, monkeypatch, deadline="2026-08-21T11:00:00+00:00"):
    """Two runs of GW3: one before the deadline, one after it."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    ADVICE_HISTORY.mkdir(parents=True, exist_ok=True)
    before = _advice(3, [1, 2], 1)
    before["deadline"] = deadline
    after = _advice(3, [1, 3], 3, buys=[3])
    after["deadline"] = deadline
    (ADVICE_HISTORY / "gw3-2026-08-21T09:00:00.json").write_text(
        json.dumps(before))
    (ADVICE_HISTORY / "gw3-2026-08-21T19:00:00.json").write_text(
        json.dumps(after))
    return before, after


def test_the_newest_run_before_the_deadline_wins(tmp_path, monkeypatch):
    _straddling(tmp_path, monkeypatch)
    runs = latest_run_per_gw()
    # 09:00 is before the 11:00 deadline; 19:00 is after and must not win just
    # for being newest.
    assert runs[3]["captain"]["code"] == 1
    assert runs[3]["post_deadline"] is False


def test_the_newest_of_several_pre_deadline_runs_wins(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    ADVICE_HISTORY.mkdir(parents=True, exist_ok=True)
    for stamp, captain in (("07:00:00", 1), ("09:00:00", 2)):
        payload = _advice(3, [1, 2], captain)
        payload["deadline"] = "2026-08-21T11:00:00+00:00"
        (ADVICE_HISTORY / f"gw3-2026-08-21T{stamp}.json").write_text(
            json.dumps(payload))
    runs = latest_run_per_gw()
    assert runs[3]["captain"]["code"] == 2
    assert runs[3]["post_deadline"] is False


def test_an_all_post_deadline_gameweek_falls_back_and_says_so(tmp_path,
                                                              monkeypatch):
    """Better a flagged row than no row: the comparison is still worth
    drawing, it just cannot claim to be what the model knew in advance."""
    _straddling(tmp_path, monkeypatch, deadline="2026-08-21T06:00:00+00:00")
    runs = latest_run_per_gw()
    assert runs[3]["captain"]["code"] == 3       # newest, both are late
    assert runs[3]["post_deadline"] is True


def test_a_run_without_a_deadline_keeps_the_old_newest_wins_rule(tree):
    """Artifacts banked before the deadline was written into the payload."""
    runs = latest_run_per_gw()
    assert runs[3]["captain"]["code"] == 3
    assert runs[3]["post_deadline"] is False


def test_an_unparseable_deadline_does_not_lose_the_gameweek(tmp_path,
                                                            monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    ADVICE_HISTORY.mkdir(parents=True, exist_ok=True)
    payload = _advice(3, [1, 2], 1)
    payload["deadline"] = "not a date"
    (ADVICE_HISTORY / "gw3-2026-08-21T09:00:00.json").write_text(
        json.dumps(payload))
    runs = latest_run_per_gw()
    assert runs[3]["captain"]["code"] == 1
    assert runs[3]["post_deadline"] is False


def test_the_journal_row_carries_the_post_deadline_flag(tmp_path, monkeypatch):
    _straddling(tmp_path, monkeypatch, deadline="2026-08-21T06:00:00+00:00")
    store.save(pd.DataFrame([
        {"code": 1, "gw": 3, "total_points": 4, "value": 100},
        {"code": 3, "gw": 3, "total_points": 9, "value": 80},
    ]), "live/player_gw.parquet")
    store.save(pd.DataFrame([
        {"code": 1, "element": 11, "name": "P1", "position": "MID",
         "team_id": 1, "team_code": 300, "now_cost": 100, "status": "a",
         "news": "", "chance_of_playing": None, "selected_by_percent": 1.0,
         "form": 1.0, "points_per_game": 1.0, "ep_next": 1.0,
         "price_change_percent": 0.0, "price_change_calibrating": False,
         "penalties_order": None, "direct_freekicks_order": None,
         "corners_and_indirect_freekicks_order": None},
    ]), "live/players.parquet")
    client = FakeClient({3: [{"element": 11, "is_captain": True,
                              "multiplier": 2, "position": 1}]})
    out = build_journal(client, entry_id=7)
    assert out["rows"][0]["post_deadline"] is True


# --- caching --------------------------------------------------------------


def test_an_empty_journal_is_cached_too(tmp_path, monkeypatch):
    """Cold state is the *common* state early in a season, and not caching it
    meant every page view of the Journal tab went back to the FPL API for the
    same nothing."""
    from gaffer.journal import load_journal

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    out = load_journal(FakeClient({}), entry_id=7)
    assert out["rows"] == []
    assert JOURNAL_PATH.exists()
    assert json.loads(JOURNAL_PATH.read_text())["built_at"] == out["built_at"]


def test_a_cached_empty_journal_is_served_without_asking_the_api(tmp_path,
                                                                 monkeypatch):
    from gaffer.journal import load_journal

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    load_journal(FakeClient({}), entry_id=7)
    client = FakeClient({})
    load_journal(client, entry_id=7)
    assert client.asked == []


def test_the_cache_is_written_whole_or_not_at_all(tmp_path, monkeypatch):
    """A reader that catches the file mid-write gets malformed JSON and throws
    the cache away; the write goes to a temporary file and is renamed."""
    from gaffer.journal import load_journal

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    seen = []
    real_replace = __import__("os").replace
    monkeypatch.setattr("gaffer.journal.os.replace",
                        lambda src, dst: seen.append((src, dst))
                        or real_replace(src, dst))
    load_journal(FakeClient({}), entry_id=7)
    assert seen and str(seen[0][1]).endswith("journal.json")
    assert str(seen[0][0]) != str(seen[0][1])
    # No temporary file left behind.
    assert [p.name for p in JOURNAL_PATH.parent.iterdir()] == ["journal.json"]
