"""The v6 penalty term measured forward: takers predicted vs pens taken."""

from __future__ import annotations

import json

import pandas as pd

from gaffer.pen_tracker import (attach_npxg, finished_gws, format_tracker,
                                gw_block, predicted_ep, realized_pens,
                                save_tracker, season_totals, track_pens,
                                tracker_path)


def _week() -> pd.DataFrame:
    """One finished gameweek of live rows: two clubs, two spot kicks.

    Code 10 is his club's first-choice taker and scored one (xg 1.05 against
    an open-play 0.20 — a 0.85 gap, one penalty's worth). Code 12 has no
    recorded order and missed one.
    """
    return pd.DataFrame({
        "gw": [1, 1, 1],
        "code": [10, 11, 12],
        "name": ["First Choice", "Second Name", "Other Club"],
        "position": ["MID", "FWD", "DEF"],
        "team_code": [3, 3, 7],
        "opp_code": [7, 7, 3],
        "kickoff_time": ["2026-08-22T14:00:00Z"] * 3,
        "xg": [1.05, 0.20, 0.30],
        "pens_missed": [0, 0, 1],
        "penalties_order": [1.0, 2.0, None]})


def _understat() -> pd.DataFrame:
    return pd.DataFrame({
        "season": ["2026-27"] * 3,
        "season_idx": [4] * 3,
        "code": [10, 11, 12],
        "date": ["2026-08-22"] * 3,
        "us_npxg": [0.20, 0.20, 0.30]})


def _events() -> pd.DataFrame:
    return pd.DataFrame({"gw": [1, 2, 3], "finished": [True, False, False]})


def _with_understat(monkeypatch, tmp_path, us=None):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    store_mod.save(_understat() if us is None else us,
                   "history/understat_player.parquet")


def test_finished_gameweeks_are_the_ones_the_league_has_played():
    assert finished_gws(_events()) == [1]


def test_an_events_frame_without_the_column_yields_nothing():
    assert finished_gws(pd.DataFrame({"gw": [1]})) == []


def test_the_understat_join_lands_on_the_uk_match_date(tmp_path, monkeypatch):
    """Understat carries no gameweek number, so the key is the player and the
    date — unique even in a double gameweek."""
    _with_understat(monkeypatch, tmp_path)
    out = attach_npxg(_week(), "2026-27")
    assert list(out["us_npxg"]) == [0.20, 0.20, 0.30]
    assert len(out) == 3


def test_a_season_understat_has_never_seen_is_no_join(tmp_path, monkeypatch):
    _with_understat(monkeypatch, tmp_path)
    assert attach_npxg(_week(), "2028-29") is None


def test_no_understat_parquet_at_all_is_no_join(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    assert attach_npxg(_week(), "2026-27") is None


def test_the_xg_gap_instrument_counts_the_penalty_that_was_taken(
        tmp_path, monkeypatch):
    _with_understat(monkeypatch, tmp_path)
    events, instrument, covered = realized_pens(_week(), "2026-27")
    assert instrument == "xg_gap"
    assert list(events) == [1.0, 0.0, 0.0]
    assert covered == 3


def test_a_week_understat_has_not_reached_yet_falls_back(tmp_path,
                                                          monkeypatch):
    """The parquet covers the season but stops before this week — a mid-season
    backfill lag. The join returns a frame of NaN, and calling that an xg gap
    would report every taker as having taken nothing."""
    stale = _understat().assign(date=["2026-08-15"] * 3)
    _with_understat(monkeypatch, tmp_path, us=stale)
    events, instrument, covered = realized_pens(_week(), "2026-27")
    assert instrument == "pens_missed_only"
    assert covered == 0
    assert list(events) == [0.0, 0.0, 1.0]


def test_without_understat_it_degrades_to_pens_missed(tmp_path, monkeypatch):
    """A floor, not a count — every converted spot kick is invisible to the
    FPL feed alone — so the instrument is named and the two never mix."""
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    events, instrument, covered = realized_pens(_week(), "2026-27")
    assert instrument == "pens_missed_only"
    assert covered == 0
    assert list(events) == [0.0, 0.0, 1.0]


def test_a_frame_with_neither_signal_reports_no_penalties(tmp_path,
                                                          monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    bare = _week().drop(columns=["xg", "pens_missed"])
    events, instrument, covered = realized_pens(bare, "2026-27")
    assert instrument == "pens_missed_only"
    assert covered == 0
    assert list(events) == [0.0, 0.0, 0.0]


def test_the_component_file_gives_the_pen_term_that_was_served(tmp_path,
                                                               monkeypatch):
    from gaffer import artifacts

    monkeypatch.setattr(artifacts, "REPORTS", tmp_path)
    pd.DataFrame({"code": [10, 11], "gw": [1, 1],
                  "ep_pen_taker": [0.42, 0.0]}).to_parquet(
                      tmp_path / "components_gw1.parquet", index=False)
    assert predicted_ep(1) == {"rows": 2, "ep_pen_taker": 0.42, "takers": 1}


def test_a_gameweek_with_no_component_file_predicted_nothing(tmp_path,
                                                             monkeypatch):
    """The tracker covers a whole season and the earliest weeks of one
    predate the artifact — that is a zero, not an error."""
    from gaffer import artifacts

    monkeypatch.setattr(artifacts, "REPORTS", tmp_path)
    assert predicted_ep(1) == {"rows": 0, "ep_pen_taker": 0.0, "takers": 0}


def _live(monkeypatch, tmp_path, understat=True):
    """A whole finished gameweek on disk: live rows, events, components."""
    from gaffer import artifacts
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(artifacts, "REPORTS", tmp_path / "reports")
    (tmp_path / "reports").mkdir(exist_ok=True)
    store_mod.save(_week(), "live/player_gw.parquet")
    store_mod.save(_events(), "live/events.parquet")
    if understat:
        store_mod.save(_understat(), "history/understat_player.parquet")
    pd.DataFrame({"code": [10], "gw": [1], "ep_pen_taker": [0.42]}).to_parquet(
        tmp_path / "reports" / "components_gw1.parquet", index=False)


def test_a_gameweek_block_pairs_the_prediction_with_what_happened(
        tmp_path, monkeypatch):
    _live(monkeypatch, tmp_path)
    block = gw_block(_week(), 1, "2026-27")
    assert block["gw"] == 1
    assert block["instrument"] == "xg_gap"
    assert block["predicted_ep_pen_taker"] == 0.42
    assert block["predicted_takers"] == 1
    assert block["pens_taken"] == 1.0
    assert block["pens_by_first_choice"] == 1.0
    assert block["taker_hit_rate"] == 1.0
    assert block["team_games"] == 2
    assert block["covered_rows"] == 3
    assert block["pens_per_team_game"] == 0.5
    # one penalty, MID, 0.78 converted x 5 points a goal
    assert block["realized_pen_points"] == 3.9


def test_team_games_count_fixtures_not_the_stamped_club(tmp_path, monkeypatch):
    """``team_code`` in the live rows is retro-stamped to the player's *current*
    club (``data/live.py`` player_meta), so a January transfer makes his August
    row look like a third fixture that never happened. ``opp_code`` is the real
    opponent of the match he actually played."""
    _live(monkeypatch, tmp_path)
    moved = _week()
    moved.loc[1, "team_code"] = 99
    block = gw_block(moved, 1, "2026-27")
    assert block["team_games"] == 2


def test_a_week_with_no_penalties_has_no_hit_rate(tmp_path, monkeypatch):
    """Zero over zero is not zero — it is "nothing to say yet", and a 0.0 hit
    rate would read as the taker model being wrong every time."""
    _live(monkeypatch, tmp_path)
    quiet = _week().assign(xg=[0.2, 0.2, 0.3], pens_missed=[0, 0, 0])
    block = gw_block(quiet, 1, "2026-27")
    assert block["pens_taken"] == 0.0
    assert block["taker_hit_rate"] is None
    assert block["pens_per_team_game"] == 0.0


def test_the_season_totals_add_the_blocks_up(tmp_path, monkeypatch):
    _live(monkeypatch, tmp_path)
    totals = season_totals([gw_block(_week(), 1, "2026-27")])
    assert totals["gws"] == 1
    assert totals["instruments"] == ["xg_gap"]
    assert totals["pens_taken"] == 1.0
    assert totals["taker_hit_rate"] == 1.0
    assert totals["league_pens_pg_served"] == 0.13
    assert totals["realized_pen_points"] == 3.9


def test_the_tracker_covers_every_finished_gameweek(tmp_path, monkeypatch):
    """Gate G3: GW1 is finished, GW2 and GW3 are not, and only the played
    week may appear."""
    _live(monkeypatch, tmp_path)
    report = track_pens(season="2026-27")
    assert report["season"] == "2026-27"
    assert [b["gw"] for b in report["gws"]] == [1]
    assert report["season_totals"]["pens_taken"] == 1.0
    assert report["notes"] == []


def test_a_degraded_instrument_is_named_in_the_report(tmp_path, monkeypatch):
    _live(monkeypatch, tmp_path, understat=False)
    report = track_pens(season="2026-27")
    assert report["gws"][0]["instrument"] == "pens_missed_only"
    assert any("pens_missed" in note for note in report["notes"])


def test_one_bad_gameweek_does_not_cost_the_other_one(tmp_path, monkeypatch):
    """A truncated week's row set, or a component file half written, is one
    gameweek's problem. Degrading the whole season's report to a note would
    throw away every week that read fine."""
    from gaffer import artifacts
    from gaffer import pen_tracker
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(artifacts, "REPORTS", tmp_path / "reports")
    (tmp_path / "reports").mkdir(exist_ok=True)
    two = pd.concat([_week(), _week().assign(gw=2)], ignore_index=True)
    store_mod.save(two, "live/player_gw.parquet")
    store_mod.save(pd.DataFrame({"gw": [1, 2, 3],
                                 "finished": [True, True, False]}),
                   "live/events.parquet")
    store_mod.save(_understat(), "history/understat_player.parquet")
    real_block = pen_tracker.gw_block

    def poisoned(week, gw, season):
        if gw == 2:
            raise RuntimeError("components_gw2.parquet is truncated")
        return real_block(week, gw, season)

    monkeypatch.setattr(pen_tracker, "gw_block", poisoned)
    report = pen_tracker.track_pens(season="2026-27")
    assert [b["gw"] for b in report["gws"]] == [1, 2]
    assert report["gws"][0]["pens_taken"] == 1.0
    assert "truncated" in report["gws"][1]["error"]
    assert report["season_totals"]["gws"] == 1
    assert any("gw2" in note for note in report["notes"])


def test_no_live_season_on_disk_is_an_empty_report(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    report = track_pens(season="2026-27")
    assert report["gws"] == []
    assert report["season_totals"] == {}
    assert report["notes"]


def test_a_broken_artifact_degrades_instead_of_raising(tmp_path, monkeypatch):
    """A season tracker that dies on one bad file is a tracker nobody runs."""
    from gaffer import pen_tracker
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    store_mod.save(_week(), "live/player_gw.parquet")
    store_mod.save(_events(), "live/events.parquet")

    def boom(events):
        raise RuntimeError("events parquet is truncated")

    monkeypatch.setattr(pen_tracker, "finished_gws", boom)
    report = pen_tracker.track_pens(season="2026-27")
    assert report["gws"] == []
    assert any("truncated" in note for note in report["notes"])


def test_the_report_is_written_atomically(tmp_path, monkeypatch):
    from gaffer import artifacts

    monkeypatch.setattr(artifacts, "REPORTS", tmp_path / "reports")
    path = save_tracker({"season": "2026-27", "gws": [], "season_totals": {},
                         "notes": []})
    assert path == tracker_path()
    assert json.loads(path.read_text())["season"] == "2026-27"
    assert not list(path.parent.glob("*.tmp"))


def test_the_printed_table_names_the_instrument_and_the_season(tmp_path,
                                                               monkeypatch):
    _live(monkeypatch, tmp_path)
    text = format_tracker(track_pens(season="2026-27"))
    assert "2026-27" in text
    assert "xg_gap" in text
    assert "season:" in text
