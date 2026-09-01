"""v10b's degradation rails and its three pins.

Every rail here is a state a real machine reaches, and three of them are the
state *every* machine is in today: no field EO log on a clone that has never
run the scrape, no ``chip_scenarios.toml`` because nothing is scheduled to be
written into it, and a fixture list with no doubles and no blanks anywhere in
it.

Block 2 also stands in for a replay. Nothing on the training or decision path
moves this cycle, and §F2b — the one writer that could reach a decision —
writes nothing on today's data, so a replay would compare two identical arms.
The property a replay would have been trying to demonstrate is asserted here
directly, over the same ``chip_thresholds_from_asset`` call ``advise.py`` makes
(plan A16).
"""

from __future__ import annotations

import dataclasses

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.config import Config
from gaffer.data import store
from gaffer.data.chip_scenarios import write_chip_scenarios
from gaffer.data.field import latest_field_eo
from gaffer.data.fixtures import season_outlook
from gaffer.optimize.chip_policy import (chip_thresholds_from_asset,
                                         load_chip_scenarios)
from gaffer.web import field_frame
from gaffer.web.app import create_app
from gaffer.web.job_kinds import JOB_KINDS

CHIPS = ("wildcard", "bboost", "freehit", "3xc")


def _payload() -> dict:
    return {"gw": 2,
            "captain": {"code": 500, "name": "Salah", "ep": 8.4},
            "vice": {"code": 501, "name": "Haaland", "ep": 7.9},
            "xi": [{"code": 500, "name": "Salah", "ep": 8.4},
                   {"code": 501, "name": "Haaland", "ep": 7.9}],
            "bench": [], "buys": [], "sells": []}


@pytest.fixture()
def clone(tmp_path, monkeypatch):
    """A machine with a squad snapshot and nothing else."""
    monkeypatch.chdir(tmp_path)
    field_frame.clear_cache()
    (tmp_path / "data" / "live").mkdir(parents=True)
    store.save(pd.DataFrame({"code": [500, 501], "element": [411, 165],
                             "name": ["Salah", "Haaland"]}),
               "live/players.parquet")
    return tmp_path


# --- Block 1: §F1's byte-identity ----------------------------------------

def test_no_field_log_leaves_the_payload_byte_identical(clone):
    """The spec's rail, literally. Not "identical apart from one null" — the
    key is absent, which is what lets this be a plain equality."""
    payload = _payload()
    out = field_frame.with_field_frame(payload, 2)
    assert out == payload
    assert "captain_field" not in out


def test_a_log_with_no_row_for_the_captain_is_the_same_silence(clone):
    store.save(pd.DataFrame([{"season": "2026-27", "gw": 2,
                              "snap_date": "2026-08-31", "element": 77,
                              "eo": 50.0, "se": 2.0, "n": 300}]),
               "live/field_eo_log.parquet")
    field_frame.clear_cache()
    payload = _payload()
    assert field_frame.with_field_frame(payload, 2) == payload


def test_a_log_from_another_season_is_the_same_silence(clone):
    """Guard 3. Element 411 in 2025-26 is a different footballer, and the
    failure it would otherwise produce is not a missing number but a confident
    number about the wrong player."""
    store.save(pd.DataFrame([{"season": "2025-26", "gw": 38,
                              "snap_date": "2026-05-24", "element": 411,
                              "eo": 90.0, "se": 1.0, "n": 300}]),
               "live/field_eo_log.parquet")
    field_frame.clear_cache()
    payload = _payload()
    assert field_frame.with_field_frame(payload, 2) == payload


def test_no_log_and_no_events_is_no_key(clone):
    assert "captain_field" not in field_frame.with_field_frame(_payload(), 2)


def test_no_log_and_an_events_row_is_a_key_with_a_null_eo_and_no_percentage(
        clone):
    """Task 3's other half. The key appears because there *is* something to
    say — who the field is captaining — and the note prints no share, because
    the bootstrap says who and not how many."""
    store.save(pd.DataFrame([{"gw": 2, "most_captained": 165.0}]),
               "live/events.parquet")
    field_frame.clear_cache()
    frame = field_frame.with_field_frame(_payload(), 2)["captain_field"]
    assert frame["eo"] is None
    assert "%" not in frame["note"]


def test_the_decoration_does_not_mutate_its_argument(clone):
    payload = _payload()
    field_frame.with_field_frame(payload, 2)
    assert "captain_field" not in payload


def test_a_payload_with_no_captain_comes_back_identical(clone):
    payload = {"gw": 2, "xi": [], "bench": []}
    assert field_frame.with_field_frame(payload, 2) == payload


def test_the_explorers_own_call_is_unchanged(clone):
    """Task 1's degradation direction, asserted here too because it is the
    thing a later cleanup would "simplify" away: ``routers/players.py`` calls
    ``latest_field_eo()`` with no arguments and must keep getting the largest
    gameweek in the file, season or no season."""
    store.save(pd.DataFrame([
        {"season": "2025-26", "gw": 38, "snap_date": "2026-05-24",
         "element": 411, "eo": 90.0, "se": 1.0, "n": 300},
        {"season": "2026-27", "gw": 2, "snap_date": "2026-08-31",
         "element": 411, "eo": 10.0, "se": 1.0, "n": 300},
    ]), "live/field_eo_log.parquet")
    assert latest_field_eo()[411]["eo"] == 90.0


# --- Block 2: §F2's byte-identity, and the replay this replaces ----------

def test_an_absent_scenario_file_leaves_every_threshold_exactly_as_it_was(
        clone):
    """The most valuable assertion in this file (plan A16). ``advise.py:
    735-736`` calls ``chip_thresholds_from_asset(priors,
    load_chip_scenarios())``; with no file that must equal the no-scenarios
    call for every (chip, gw) the season contains. This is the replay's job,
    done in a second and interpretable."""
    with_file = chip_thresholds_from_asset(None, load_chip_scenarios())
    without = chip_thresholds_from_asset(None)
    for chip in CHIPS:
        for gw in range(1, 39):
            assert with_file(chip, gw) == without(chip, gw)


def test_an_empty_dgw_table_is_indistinguishable_from_an_absent_file(clone,
                                                                     tmp_path):
    """The self-heal path. ``chip_policy.py:110-112`` reads a file with no
    ``[dgw]`` entries as ``{}``, so emptying the file cannot change a bar."""
    path = tmp_path / "chip_scenarios.toml"
    path.write_text("[dgw]\n")
    assert load_chip_scenarios(path) == {}
    seeded = chip_thresholds_from_asset(None, load_chip_scenarios(path))
    plain = chip_thresholds_from_asset(None)
    for chip in CHIPS:
        for gw in range(1, 39):
            assert seeded(chip, gw) == plain(chip, gw)


def test_a_fixture_list_with_no_doubles_writes_no_file(clone, tmp_path):
    path = tmp_path / "chip_scenarios.toml"
    ordinary = pd.DataFrame([
        {"gw": 1, "home_id": 1, "away_id": 2},
        {"gw": 1, "home_id": 3, "away_id": 4},
    ])
    assert write_chip_scenarios(ordinary, path=path) == 0
    assert not path.exists()


def test_todays_real_fixture_list_reports_nothing_to_do():
    """380 rows, ten fixtures a week, twenty teams once each. If this ever
    starts finding a double, check the detector before celebrating."""
    if not store.exists("live/fixtures_all.parquet"):
        pytest.skip("no fixture list on this clone")
    weeks = season_outlook(store.load("live/fixtures_all.parquet"))
    assert weeks
    assert all(not w["doubles"] and not w["blanks"] for w in weeks)


def test_the_outlook_on_a_bare_clone_is_a_200_that_says_why(tmp_path,
                                                            monkeypatch):
    monkeypatch.chdir(tmp_path)
    response = TestClient(create_app()).get("/api/fixtures/outlook")
    assert response.status_code == 200
    body = response.json()
    assert body["weeks"] == [] and body["note"]


def test_the_matrix_is_unaffected_by_the_new_route(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    assert client.get("/api/fixtures/matrix").json() == {
        "gws": [], "teams": [], "source": "none"}


# --- Block 3: the element/code mismatch, in one place --------------------

def test_a_log_of_unknown_elements_maps_to_nothing_and_nobody_borrows(clone):
    """The wrong-player failure, asserted by walking the whole payload: not
    only is there no ``captain_field``, no entry anywhere gained a number."""
    store.save(pd.DataFrame([
        {"season": "2026-27", "gw": 2, "snap_date": "2026-08-31",
         "element": 9001, "eo": 88.0, "se": 1.0, "n": 300},
        {"season": "2026-27", "gw": 2, "snap_date": "2026-08-31",
         "element": 9002, "eo": 77.0, "se": 1.0, "n": 300},
    ]), "live/field_eo_log.parquet")
    field_frame.clear_cache()
    payload = _payload()
    out = field_frame.with_field_frame(payload, 2)
    assert out == payload
    for key in ("xi", "bench"):
        for entry in out[key]:
            assert "eo" not in entry and "field_eo" not in entry


def test_a_snapshot_with_no_element_column_is_silence_not_a_key_error(
        tmp_path, monkeypatch, capsys):
    """The older-bootstrap case, in ``_player_teams``' shape: a guard and a
    printed line, never a KeyError on the way out of a page."""
    monkeypatch.chdir(tmp_path)
    field_frame.clear_cache()
    (tmp_path / "data" / "live").mkdir(parents=True)
    store.save(pd.DataFrame({"code": [500], "team_code": [14]}),
               "live/players.parquet")
    store.save(pd.DataFrame([{"season": "2026-27", "gw": 2,
                              "snap_date": "2026-08-31", "element": 411,
                              "eo": 62.4, "se": 2.8, "n": 300}]),
               "live/field_eo_log.parquet")
    payload = _payload()
    assert field_frame.with_field_frame(payload, 2) == payload
    assert "element" in capsys.readouterr().out


def test_a_code_that_is_not_an_int_is_skipped_rather_than_coerced(clone):
    store.save(pd.DataFrame([{"season": "2026-27", "gw": 2,
                              "snap_date": "2026-08-31", "element": 411,
                              "eo": 62.4, "se": 2.8, "n": 300}]),
               "live/field_eo_log.parquet")
    field_frame.clear_cache()
    for bad in ("500", None, True):
        payload = _payload()
        payload["captain"] = {"code": bad, "name": "?", "ep": 1.0}
        assert "captain_field" not in field_frame.with_field_frame(payload, 2)


# --- Block 4: the counts -------------------------------------------------

def test_the_job_kinds_are_still_twelve():
    """Spec §0: §F2b is a writer inside refresh-data's body, not a thirteenth
    kind. A thirteenth would also need a row in ABANDON_TIMEOUT_S or
    SLOW_ABANDON_KINDS, which test_v9d_degradation.py pins as jointly
    exhaustive — and that file is protected."""
    assert len(JOB_KINDS) == 12


def test_the_config_gained_no_field():
    """Spec §0: nothing here is a knob. The season the field log is read for
    comes from the existing ``current_season``; the scenario path is a module
    constant in chip_policy."""
    assert len(dataclasses.fields(Config)) == 48


def test_the_route_count_moved_by_exactly_one(tmp_path, monkeypatch):
    """44 at the branch point (9499dd3), 45 now, and the one is the outlook.

    Pinned as a total *and* by name, in one test, so the number and the reason
    travel together: a count alone would let a route be added and another
    removed in one cycle, and a name alone would not notice a third arriving
    beside it.

    The two historical files that also pin this total —
    ``test_v10_degradation.py`` and ``test_v9d_degradation.py`` — were moved
    from 44 to 45 under orchestrator authorization, which is what those pins
    exist to force.
    """
    monkeypatch.chdir(tmp_path)
    paths = set(create_app().openapi()["paths"])
    assert len(paths) == 45
    assert {p for p in paths if p.startswith("/api/fixtures")} == {
        "/api/fixtures/matrix", "/api/fixtures/ticker",
        "/api/fixtures/outlook"}
