"""FPL's own modal captain, ingested and framed for the week it belongs to.

§F1b. Two keys in ``build_events`` and a fallback in the framing, and the whole
of it turns on plan A5's finding: ``most_captained`` is **live, not lagging**.
FPL publishes it for the gameweek that is open and ``null`` for every gameweek
beyond it, so the honest sentence names the gameweek and a payload served on
Friday for GW3 must never print GW2's modal captain as if it were this week's.

The value is an ``element``, so it crosses the same id-space split the
captain's own EO does, and it takes the same guards. A ``.get(..., 0)``
anywhere on this path would put element 0 into the frame; element 0 maps to
nobody, and the column would read exactly like a working one.
"""

from __future__ import annotations

import json

import pandas as pd

from gaffer.artifacts import save_snapshots
from gaffer.data import store
from gaffer.data.bootstrap import build_events, build_players, build_teams
from gaffer.web import field_frame

SAMPLE = "src/gaffer/assets/bootstrap_sample.json"


def _raw() -> dict:
    with open(SAMPLE) as fh:
        return json.load(fh)


def test_build_events_carries_both_modes():
    """The shipped sample already has them, so the fixture is a fact rather
    than an invention: element 411 on event 1."""
    events = build_events(_raw())
    assert "most_captained" in events.columns
    assert "most_selected" in events.columns
    row = events[events["gw"] == 1].iloc[0]
    assert int(row["most_captained"]) == 411
    assert int(row["most_selected"]) == 411


def test_a_gameweek_fpl_has_not_opened_is_null_and_stays_null():
    """Plan A5. Not 0, which names element 0 — a player who does not exist."""
    events = build_events(_raw())
    later = events[events["gw"] == 2].iloc[0]
    assert pd.isna(later["most_captained"])
    assert pd.isna(later["most_selected"])


def test_save_snapshots_writes_them_through(tmp_path, monkeypatch):
    """Events are saved whole (``artifacts.py:398``), unlike players, which go
    through SNAPSHOT_PLAYER_COLS. Asserted rather than trusted, because a later
    cycle that adds an events allowlist would drop the column in silence."""
    raw = _raw()   # before the chdir: SAMPLE is a repo-relative path
    monkeypatch.chdir(tmp_path)
    save_snapshots(build_players(raw), build_teams(raw), build_events(raw),
                   pd.DataFrame(columns=["gw", "home_id", "away_id"]))
    saved = store.load("live/events.parquet")
    assert int(saved[saved["gw"] == 1].iloc[0]["most_captained"]) == 411


def _wire(tmp_path, monkeypatch, *, events=None, field_log=True):
    monkeypatch.chdir(tmp_path)
    field_frame.clear_cache()
    (tmp_path / "data" / "live").mkdir(parents=True)
    # A configured clone: the framing reads the season off ``load_config`` and
    # frames nothing without one, so the two keys ``load_config`` requires are
    # what makes this tmpdir a clone rather than a cold checkout. The season
    # itself is the dataclass default, which is what the log rows below use.
    (tmp_path / "config.toml").write_text(
        "[fpl]\nentry_id = 1\nleague_id = 1\n")
    store.save(pd.DataFrame({"code": [500, 501], "element": [411, 165],
                             "name": ["Salah", "Haaland"]}),
               "live/players.parquet")
    if field_log:
        store.save(pd.DataFrame([
            {"season": "2026-27", "gw": 2, "snap_date": "2026-08-31",
             "element": 411, "eo": 62.4, "se": 2.8, "n": 300}]),
            "live/field_eo_log.parquet")
    if events is not None:
        store.save(events, "live/events.parquet")


def _payload() -> dict:
    return {"gw": 2, "captain": {"code": 500, "name": "Salah", "ep": 8.4},
            "xi": [], "bench": []}


def test_an_events_parquet_with_neither_column_reads_as_absent(tmp_path,
                                                               monkeypatch):
    """``pen_tracker.finished_gws``' guard shape: the column check comes before
    the row access, so a parquet banked before this cycle is a missing column
    and never a KeyError."""
    _wire(tmp_path, monkeypatch,
          events=pd.DataFrame([{"gw": 2, "finished": False}]))
    out = field_frame.with_field_frame(_payload(), 2)
    assert "most_captained" not in out["captain_field"]


def test_the_framing_names_the_gameweek_it_has(tmp_path, monkeypatch):
    """GW3's row is null, so a payload for GW3 carries no modal captain — the
    modal captain of GW2 is not this week's."""
    _wire(tmp_path, monkeypatch, events=pd.DataFrame([
        {"gw": 2, "most_captained": 411.0},
        {"gw": 3, "most_captained": None}]))
    out = field_frame.with_field_frame({**_payload(), "gw": 3}, 3)
    # No field row for GW3 either, so there is nothing at all to say.
    assert "captain_field" not in out


def test_the_modal_captain_goes_through_the_same_element_guard(tmp_path,
                                                               monkeypatch):
    """An element with no snapshot row is an absence, not a name."""
    _wire(tmp_path, monkeypatch,
          events=pd.DataFrame([{"gw": 2, "most_captained": 9999.0}]))
    out = field_frame.with_field_frame(_payload(), 2)
    assert "most_captained" not in out["captain_field"]


def test_the_modal_captain_resolves_to_a_code(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch,
          events=pd.DataFrame([{"gw": 2, "most_captained": 165.0}]))
    out = field_frame.with_field_frame(_payload(), 2)
    assert out["captain_field"]["most_captained"] == {"code": 501,
                                                      "name": "Haaland",
                                                      "gw": 2}


def test_with_no_tier_eo_the_modal_captain_still_says_something(tmp_path,
                                                               monkeypatch):
    """The spec's actual use: no field log, but a bootstrap. The key is
    present, ``eo`` is null, and the note says who the field is captaining
    instead of what percentage owns ours — with no percentage anywhere in it,
    because there is no percentage to print."""
    _wire(tmp_path, monkeypatch, field_log=False,
          events=pd.DataFrame([{"gw": 2, "most_captained": 165.0}]))
    out = field_frame.with_field_frame(_payload(), 2)
    assert out["captain_field"]["eo"] is None
    assert out["captain_field"]["most_captained"]["name"] == "Haaland"
    assert "%" not in out["captain_field"]["note"]


def test_no_log_and_no_events_is_still_no_key(tmp_path, monkeypatch):
    """Task 2's rule, unchanged: the key is absent when there is nothing to
    say, and "nothing to say" is both halves missing."""
    _wire(tmp_path, monkeypatch, field_log=False)
    payload = _payload()
    assert field_frame.with_field_frame(payload, 2) == payload
