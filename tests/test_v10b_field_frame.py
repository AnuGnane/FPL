"""Where the captain stands against the top 10k, decided once.

A fourth serve-time decoration, in the shape ``web/identity.py`` established:
additive, non-mutating, and incapable of raising. It adds one key,
``captain_field``, and when there is nothing to say it adds **nothing at all**
— not a null. That is what makes §Gates' byte-identity rail literal instead of
"identical except for one key that is always None".

The three guards under test are the ones §Gates names, and they are three
distinct hazards:

* the payload speaks ``code`` and the log speaks ``element``, and the map
  between them comes off one snapshot row at a time (never an index, never a
  position);
* an element the log does not carry produces no framing, never a 0.0 that a
  reader would take for a measured differential (``schemas.py:411``);
* a log row from another season is not this season's player at all
  (plan A3, Task 1's keyword).
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.data import store
from gaffer.web import field_frame, identity


def _payload() -> dict:
    return {"gw": 2,
            "captain": {"code": 500, "name": "Salah", "ep": 8.4},
            "vice": {"code": 501, "name": "Haaland", "ep": 7.9},
            "xi": [{"code": 500, "name": "Salah", "ep": 8.4}],
            "bench": [], "buys": [], "sells": []}


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    """A snapshot that knows both id spaces, and a log that speaks elements."""
    monkeypatch.chdir(tmp_path)
    identity.clear_cache()
    field_frame.clear_cache()
    (tmp_path / "data" / "live").mkdir(parents=True)
    store.save(pd.DataFrame({"code": [500, 501], "element": [411, 165],
                             "team_code": [14, 43]}),
               "live/players.parquet")
    store.save(pd.DataFrame([
        {"season": "2026-27", "gw": 2, "snap_date": "2026-08-31",
         "element": 411, "eo": 62.4, "se": 2.8, "n": 300},
        {"season": "2026-27", "gw": 2, "snap_date": "2026-08-31",
         "element": 165, "eo": 11.0, "se": 1.9, "n": 300},
    ]), "live/field_eo_log.parquet")
    return tmp_path


def test_the_captain_gets_his_number_with_its_error(wired):
    out = field_frame.with_field_frame(_payload(), 2)
    assert out["captain_field"]["eo"] == 62.4
    assert out["captain_field"]["se"] == 2.8


def test_a_heavily_owned_captain_is_cover_and_the_sentence_says_so(wired):
    """``field_class`` is imported, not reimplemented (plan A15): two copies of
    a threshold pair is how "sword" comes to mean two things on one page."""
    out = field_frame.with_field_frame(_payload(), 2)
    assert out["captain_field"]["field_class"] == "shield"
    # "is cover", not "cover": both sentences name both sides ("cover, not
    # attack" / "attack, not cover"), so a bare substring would pass for
    # either and the test would assert only that a sentence exists.
    assert "is cover" in out["captain_field"]["note"]


def test_a_lightly_owned_captain_is_attack(wired):
    payload = _payload()
    payload["captain"] = {"code": 501, "name": "Haaland", "ep": 7.9}
    out = field_frame.with_field_frame(payload, 2)
    assert out["captain_field"]["field_class"] == "sword"
    assert "is attack" in out["captain_field"]["note"]


def test_a_captain_in_the_middle_gets_the_number_and_no_claim(wired):
    """Plan A15. ``field_class`` deliberately labels nothing between 15% and
    40%, and the sentence must not invent a side for him."""
    store.save(pd.DataFrame([{"season": "2026-27", "gw": 2,
                              "snap_date": "2026-08-31", "element": 411,
                              "eo": 27.0, "se": 2.1, "n": 300}]),
               "live/field_eo_log.parquet")
    field_frame.clear_cache()
    out = field_frame.with_field_frame(_payload(), 2)
    assert out["captain_field"]["field_class"] is None
    assert "27.0" in out["captain_field"]["note"]
    assert "is cover" not in out["captain_field"]["note"]
    assert "is attack" not in out["captain_field"]["note"]


def test_no_log_at_all_leaves_the_payload_exactly_as_it_arrived(tmp_path,
                                                               monkeypatch):
    """The §Gates rail. Not "a null key" — no key. A clone that has never run
    a scrape serves the bytes it served yesterday."""
    monkeypatch.chdir(tmp_path)
    field_frame.clear_cache()
    payload = _payload()
    assert field_frame.with_field_frame(payload, 2) == payload
    assert "captain_field" not in field_frame.with_field_frame(payload, 2)


def test_an_element_the_log_does_not_carry_is_an_absence_not_a_zero(wired):
    """``schemas.py:411``: 0.0 is a measured differential and unknown is not."""
    payload = _payload()
    payload["captain"] = {"code": 999, "name": "Nobody", "ep": 1.0}
    assert "captain_field" not in field_frame.with_field_frame(payload, 2)


def test_an_unknown_code_never_borrows_another_players_number(wired):
    """The wrong-player failure, asserted directly. A code with no snapshot row
    has no element, and no element is the end of it — there is no positional
    fallback to pick up the next row's."""
    payload = _payload()
    payload["captain"] = {"code": 502, "name": "Ghost", "ep": 5.0}
    out = field_frame.with_field_frame(payload, 2)
    assert "captain_field" not in out


def test_last_seasons_log_is_not_this_seasons_player(wired, monkeypatch):
    """Plan A3 guard 3, end to end. Element 411 is somebody else now."""
    store.save(pd.DataFrame([{"season": "2025-26", "gw": 38,
                              "snap_date": "2026-05-24", "element": 411,
                              "eo": 90.0, "se": 1.0, "n": 300}]),
               "live/field_eo_log.parquet")
    field_frame.clear_cache()
    assert "captain_field" not in field_frame.with_field_frame(_payload(), 2)


def test_the_payload_is_not_mutated(wired):
    """``identity.py:311-315``'s contract: the caller's dict is the one
    ``load_advice`` returned, and enriching it in place leaks the decoration
    into anything holding a reference."""
    payload = _payload()
    field_frame.with_field_frame(payload, 2)
    assert "captain_field" not in payload


def test_a_payload_with_no_captain_is_returned_untouched(wired):
    """``ThisWeek.tsx:82-84`` already survives an artifact with no armband;
    this must not be the thing that stops it."""
    assert field_frame.with_field_frame({"gw": 2, "xi": []}, 2) == {"gw": 2,
                                                                    "xi": []}


def test_an_unreadable_snapshot_is_silence(wired, monkeypatch):
    """The module's standing contract: a decoration that can 500 the page it
    decorates is worse than no decoration."""
    def boom(*_a, **_k):
        raise OSError("disk is on fire")
    monkeypatch.setattr(store, "load", boom)
    field_frame.clear_cache()
    payload = _payload()
    assert field_frame.with_field_frame(payload, 2) == payload


def test_the_route_serves_the_key(wired):
    """The composition at ``routers/advice.py:176-177``, asserted where a
    reader will look for it."""
    import inspect

    from gaffer.web.routers import advice as advice_router
    source = inspect.getsource(advice_router.latest)
    assert "with_field_frame" in source
