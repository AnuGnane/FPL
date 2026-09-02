"""A degraded run does not get to delete a good one.

`track_pens` never raises — it is a standing report and a report that dies on one
bad file is a report nobody runs — so every failure comes back as a *shape*: a
gameweek block carrying `error`, or a report with no gameweeks and one note. Both
shapes are then written straight over reports/pen_tracker.json, and a season of
tracking is gone because one parquet would not read.

`calibrate_noise` already refuses in this situation and this mirrors it, including
the part that is easy to get wrong: **the refusal only fires when there is
something to protect.** A first run on a cold clone must write its empty report,
or the file never comes into existence at all.
"""

from __future__ import annotations

import json

import pytest
import typer

from gaffer import cli


@pytest.fixture()
def clone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    return tmp_path


def _banked(clone, text="the good one"):
    path = clone / "reports" / "pen_tracker.json"
    path.write_text(json.dumps({"season": "2026-27", "gws": [{"gw": 1}],
                                "season_totals": {"note": text},
                                "notes": []}))
    return path


def _report(monkeypatch, report):
    monkeypatch.setattr("gaffer.pen_tracker.track_pens", lambda season: report)


def test_a_run_whose_every_gameweek_is_broken_refuses(clone, monkeypatch,
                                                      capsys):
    path = _banked(clone)
    _report(monkeypatch, {"season": "2026-27", "notes": [],
                          "season_totals": {},
                          "gws": [{"gw": 1, "error": "bad parquet"},
                                  {"gw": 2, "error": "bad parquet"}]})
    with pytest.raises(typer.Exit) as exc:
        cli.track_pens_cmd(season="2026-27")
    assert exc.value.exit_code == 1
    out = capsys.readouterr().out
    assert "refused to overwrite" in out
    assert "pen_tracker.json" in out
    assert "2 rows degraded" in out
    assert json.loads(path.read_text())["season_totals"]["note"] == \
        "the good one"


def test_one_good_gameweek_among_the_broken_is_enough_to_write(clone,
                                                               monkeypatch):
    """The partial case is the one `safe_gw_block` was built for: one bad week
    is that week's problem, and the season line still covers the rest. Refusing
    here would throw away the very degradation the tracker handles well.

    The surviving block and the season line carry the keys `format_tracker`
    prints, because this run gets as far as printing — the two refusal tests
    do not, which is why theirs can be sketches.
    """
    path = _banked(clone)
    good = {"gw": 2, "predicted_ep_pen_taker": 1.5, "pens_taken": 2.0,
            "pens_by_first_choice": 1.0, "taker_hit_rate": 0.5,
            "pens_per_team_game": 0.1, "instrument": "npxg"}
    totals = {"note": "the new one", "predicted_ep_pen_taker": 1.5,
              "realized_pen_points": 2.0, "gws": 1, "pens_taken": 2.0,
              "team_games": 20, "league_pens_pg_served": 0.12}
    _report(monkeypatch, {"season": "2026-27", "notes": [],
                          "season_totals": totals,
                          "gws": [{"gw": 1, "error": "bad"}, good]})
    cli.track_pens_cmd(season="2026-27")
    assert json.loads(path.read_text())["season_totals"]["note"] == \
        "the new one"


def test_an_empty_report_refuses_and_says_which_note_caused_it(clone,
                                                              monkeypatch,
                                                              capsys):
    """The second hazard, which the spec does not name: no gameweeks at all,
    because the live parquet is missing. Same loss, different cause."""
    path = _banked(clone)
    _report(monkeypatch, {"season": "2026-27", "gws": [], "season_totals": {},
                          "notes": ["no live season on disk — run "
                                    "`gaffer refresh` first"]})
    with pytest.raises(typer.Exit):
        cli.track_pens_cmd(season="2026-27")
    out = capsys.readouterr().out
    assert "the report is empty" in out
    assert "no live season on disk" in out
    assert json.loads(path.read_text())["season_totals"]["note"] == \
        "the good one"


def test_a_first_run_on_a_cold_clone_writes_its_empty_report(clone,
                                                             monkeypatch):
    """The half that makes the refusal safe. With nothing banked there is
    nothing to protect, and refusing would mean the file is never created."""
    _report(monkeypatch, {"season": "2026-27", "gws": [], "season_totals": {},
                          "notes": ["no finished gameweek in the live season "
                                    "yet"]})
    cli.track_pens_cmd(season="2026-27")
    assert (clone / "reports" / "pen_tracker.json").exists()


def test_a_first_run_whose_every_week_is_broken_also_writes(clone,
                                                            monkeypatch):
    """Same rule, other shape. Nothing banked, so the degraded report is the
    best available answer and hiding it would leave no artifact at all."""
    _report(monkeypatch, {"season": "2026-27", "notes": [],
                          "season_totals": {},
                          "gws": [{"gw": 1, "error": "bad"}]})
    cli.track_pens_cmd(season="2026-27")
    assert (clone / "reports" / "pen_tracker.json").exists()


def test_an_unreadable_banked_report_does_not_block_the_write(clone,
                                                              monkeypatch):
    """A corrupt file is not something worth protecting, and a refusal here
    would wedge the command with no way out but deleting the file by hand —
    which is exactly the state the refusal is meant to spare the user."""
    (clone / "reports" / "pen_tracker.json").write_text("{not json")
    _report(monkeypatch, {"season": "2026-27", "notes": [],
                          "season_totals": {},
                          "gws": [{"gw": 1, "error": "bad"}]})
    cli.track_pens_cmd(season="2026-27")
    assert json.loads(
        (clone / "reports" / "pen_tracker.json").read_text())["gws"]
