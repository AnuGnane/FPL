"""What is safe to delete, and the four things that are not.

Measured on the real tree before this was written: 33 backtest logs, 28 of them
paired with their report, five orphans totalling 54 KB. That is the whole prize,
and saying so here is the point — a delete command whose value is overstated is a
delete command that gets pointed at something bigger.

The four exclusions each exist because of a specific reader:

* `data/live/backtest_log.parquet` — no tag — is the shared log `run_backtest`
  writes and `/api/history` reads. The glob does not match it, which is luck
  rather than design, so it is asserted rather than assumed.
* only the `v7b_` prefix is swept. `scripts/s2_replay.py` writes
  `backtest_log_s2_<mode>.parquet` and writes **no companion report at all** —
  its evidence is an S2_ARM_DONE line in logs/. "No report ⇒ orphan" would delete
  every S2 arm the moment it was written.
* `logs/advise.log` is read by `/api/health` (LaunchdHealth.last_line). It is
  dated well outside the 30-day cutoff and would qualify within a week.
* the four named logs — availability, field EO, price, and any ledger — are never
  candidates, whatever their age.
"""

from __future__ import annotations

import pytest

from gaffer import tidy


@pytest.fixture()
def tree(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    (tmp_path / "logs").mkdir()
    return tmp_path


def _log(tree, name, size=100):
    path = tree / "data" / "live" / name
    path.write_bytes(b"x" * size)
    return path


def test_a_backtest_log_with_no_report_is_a_candidate(tree):
    _log(tree, "backtest_log_v7b_orphan.parquet")
    found = tidy.candidates()
    assert [p.name for p in found["backtests"]] == \
        ["backtest_log_v7b_orphan.parquet"]


def test_a_backtest_log_with_its_report_is_not(tree):
    _log(tree, "backtest_log_v7b_kept.parquet")
    (tree / "reports" / "v7b_kept.json").write_text("{}")
    assert tidy.candidates()["backtests"] == []


def test_the_shared_log_is_never_a_candidate(tree):
    """`/api/history` reads it. The glob does not match it either, and both
    facts are asserted because only one of them was designed."""
    _log(tree, "backtest_log.parquet")
    assert tidy.candidates()["backtests"] == []


def test_an_s2_arm_log_is_never_a_candidate(tree):
    """s2_replay writes no companion report — its evidence is an S2_ARM_DONE
    line in logs/ — so "no report" says nothing about it."""
    _log(tree, "backtest_log_s2_est.parquet")
    assert tidy.candidates()["backtests"] == []


def test_the_named_logs_are_never_candidates(tree):
    for name in ("availability_log.parquet", "field_eo_log.parquet",
                 "price_log.parquet", "presser_log.parquet"):
        _log(tree, name)
    found = tidy.candidates()
    assert found["backtests"] == []
    assert found["logs"] == []


def test_an_old_log_file_is_a_candidate(tree):
    import os
    import time

    path = tree / "logs" / "v7b_q3-f03.log"
    path.write_text("x" * 50)
    old = time.time() - 60 * 86400
    os.utime(path, (old, old))
    assert [p.name for p in tidy.candidates()["logs"]] == ["v7b_q3-f03.log"]


def test_a_recent_log_file_is_not(tree):
    (tree / "logs" / "prices.log").write_text("x")
    assert tidy.candidates()["logs"] == []


def test_the_advise_log_is_never_a_candidate_however_old(tree):
    """It is what `/api/health` shows as the launchd last line, and it is
    already outside the default cutoff — so without this exclusion the first
    `tidy --apply` blanks the Health page."""
    import os
    import time

    path = tree / "logs" / "advise.log"
    path.write_text("x")
    old = time.time() - 400 * 86400
    os.utime(path, (old, old))
    assert tidy.candidates()["logs"] == []


def test_the_dry_run_deletes_nothing_and_reports_the_total(tree, capsys):
    path = _log(tree, "backtest_log_v7b_orphan.parquet", size=2048)
    tidy.run_tidy(apply=False)
    assert path.exists()
    out = capsys.readouterr().out
    assert "backtest_log_v7b_orphan.parquet" in out
    assert "2.0 KB" in out or "0.0 MB" in out
    assert "--apply" in out


def test_apply_deletes_exactly_the_candidates(tree):
    doomed = _log(tree, "backtest_log_v7b_orphan.parquet")
    kept = _log(tree, "backtest_log_v7b_kept.parquet")
    (tree / "reports" / "v7b_kept.json").write_text("{}")
    tidy.run_tidy(apply=True)
    assert not doomed.exists()
    assert kept.exists()


def test_nothing_to_do_says_so_rather_than_printing_an_empty_list(tree,
                                                                  capsys):
    tidy.run_tidy(apply=False)
    assert "nothing to tidy" in capsys.readouterr().out


def test_the_cutoff_is_configurable_and_applies_only_to_logs(tree):
    """An orphaned backtest log is orphaned whatever its age: the report it
    would have been paired with is never going to appear."""
    import os
    import time

    _log(tree, "backtest_log_v7b_orphan.parquet")
    path = tree / "logs" / "old.log"
    path.write_text("x")
    old = time.time() - 10 * 86400
    os.utime(path, (old, old))
    assert len(tidy.candidates(older_than=30)["backtests"]) == 1
    assert tidy.candidates(older_than=30)["logs"] == []
    assert len(tidy.candidates(older_than=5)["logs"]) == 1


def test_a_negative_cutoff_is_refused(tree):
    """`--older-than -1` puts the cutoff in the future, which makes every log
    a candidate — including the one launchd is appending to right now. A
    delete command must not accept an argument whose only effect is to widen
    what it deletes past everything."""
    with pytest.raises(ValueError, match="negative"):
        tidy.candidates(older_than=-1)


def test_a_missing_logs_root_raises_rather_than_reporting_a_clean_tree(
        tmp_path, monkeypatch):
    """A glob over a directory that does not exist returns `[]`, and `[]`
    prints "nothing to tidy" — which is the same sentence a genuinely clean
    tree prints. The way to have no `logs/` is to run this from the wrong
    directory, so the false all-clear arrives exactly when it is least
    deserved."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError, match="project root"):
        tidy.candidates()


def test_the_cli_exits_non_zero_on_both_refusals(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    import gaffer.cli as cli

    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    wrong_dir = runner.invoke(cli.app, ["tidy"])
    assert wrong_dir.exit_code == 1
    assert "project root" in wrong_dir.stdout

    (tmp_path / "logs").mkdir()
    (tmp_path / "data" / "live").mkdir(parents=True)
    negative = runner.invoke(cli.app, ["tidy", "--older-than", "-1"])
    assert negative.exit_code == 1
    assert "negative" in negative.stdout


# The holiday's F-2 (ROADMAP candidate 7): superseded projection snapshots.
# One reader, review.grade_gw through artifacts.latest_projection_before, and
# grades are banked and never re-derived, so a graded week's other snapshots
# are dead and the one its row names is the re-check.

S = "2026-27"


def _snap(tree, season, gw, stamp, size=100):
    path = tree / "reports" / "projections" / f"{season}-gw{gw}-{stamp}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


def _ledger(tree, *rows):
    import json

    (tree / "reports" / "decision_ledger.json").write_text(
        json.dumps({"gws": list(rows)}))


def test_a_graded_weeks_other_snapshots_are_candidates_and_its_named_one_is_not(
        tree):
    early = _snap(tree, S, 5, "20261001T090000Z")
    named = _snap(tree, S, 5, "20261003T090000Z")
    late = _snap(tree, S, 5, "20261004T190000Z")
    _ledger(tree, {"season": S, "gw": 5,
                   "projection_snapshot": "20261003T090000Z"})
    found = [p.name for p in tidy.candidates()["projections"]]
    assert found == sorted([early.name, late.name])
    assert named.name not in found


def test_an_ungraded_week_keeps_every_snapshot(tree):
    """Review has not chosen yet, and choosing for it is the call the
    PROJECTIONS note refuses to make."""
    _snap(tree, S, 6, "20261008T090000Z")
    _snap(tree, S, 6, "20261009T090000Z")
    _ledger(tree, {"season": S, "gw": 5,
                   "projection_snapshot": "20261003T090000Z"})
    assert tidy.candidates()["projections"] == []


def test_no_ledger_means_no_projection_candidates(tree):
    _snap(tree, S, 5, "20261001T090000Z")
    _snap(tree, S, 5, "20261003T090000Z")
    assert tidy.candidates()["projections"] == []


def test_a_corrupt_ledger_names_nothing(tree):
    _snap(tree, S, 5, "20261001T090000Z")
    _snap(tree, S, 5, "20261003T090000Z")
    (tree / "reports" / "decision_ledger.json").write_text("{not json")
    assert tidy.candidates()["projections"] == []


def test_a_row_naming_no_snapshot_keeps_the_week(tree):
    _snap(tree, S, 5, "20261001T090000Z")
    _ledger(tree, {"season": S, "gw": 5, "projection_snapshot": None})
    assert tidy.candidates()["projections"] == []


def test_a_row_naming_a_snapshot_that_has_gone_keeps_the_rest(tree):
    """Deleting the siblings too would leave a later `review --gw` nothing."""
    _snap(tree, S, 5, "20261001T090000Z")
    _ledger(tree, {"season": S, "gw": 5,
                   "projection_snapshot": "20261003T090000Z"})
    assert tidy.candidates()["projections"] == []


def test_a_legacy_row_with_no_season_keeps_the_week(tree):
    """Reading it as the season in force would need the config, and a wrong
    guess here deletes. The next append_ledger writes the key on."""
    _snap(tree, S, 5, "20261001T090000Z")
    _snap(tree, S, 5, "20261003T090000Z")
    _ledger(tree, {"gw": 5, "projection_snapshot": "20261003T090000Z"})
    assert tidy.candidates()["projections"] == []


def test_the_season_is_matched_exactly(tree):
    """Last season's GW5 is not this season's GW5 (v19h §2.2)."""
    other = _snap(tree, "2025-26", 5, "20250901T090000Z")
    _snap(tree, S, 5, "20261003T090000Z")
    _ledger(tree, {"season": S, "gw": 5,
                   "projection_snapshot": "20261003T090000Z"})
    assert tidy.candidates()["projections"] == []
    assert other.exists()


def test_a_past_seasons_graded_week_is_swept_too(tree):
    """load_ledger keeps the season in force; the sweep reads every row."""
    dead = _snap(tree, "2025-26", 5, "20250901T090000Z")
    _snap(tree, "2025-26", 5, "20250903T090000Z")
    _ledger(tree, {"season": "2025-26", "gw": 5,
                   "projection_snapshot": "20250903T090000Z"},
            {"season": S, "gw": 5, "projection_snapshot": None})
    assert [p.name for p in tidy.candidates()["projections"]] == [dead.name]


def test_a_file_that_is_not_a_snapshot_name_is_never_a_candidate(tree):
    """A .parquet that projection_path did not write, and io.atomic_path's
    temp, which the glob never reaches."""
    _snap(tree, S, 5, "20261003T090000Z")
    stray = tree / "reports" / "projections" / "notes.parquet"
    stray.write_text("x")
    temp = tree / "reports" / "projections" / \
        f"{S}-gw5-20261001T090000Z.parquet.123.tmp"
    temp.write_text("x")
    _ledger(tree, {"season": S, "gw": 5,
                   "projection_snapshot": "20261003T090000Z"})
    assert tidy.candidates()["projections"] == []


def test_apply_deletes_superseded_snapshots_and_keeps_the_named_one(tree):
    doomed = _snap(tree, S, 5, "20261001T090000Z")
    kept = _snap(tree, S, 5, "20261003T090000Z")
    _ledger(tree, {"season": S, "gw": 5,
                   "projection_snapshot": "20261003T090000Z"})
    tidy.run_tidy(apply=True)
    assert not doomed.exists()
    assert kept.exists()
    assert (tree / "reports" / "decision_ledger.json").exists()


def test_the_paths_agree_with_the_writer_and_the_ledger():
    """tidy spells them out rather than importing; this is what holds them."""
    from gaffer import artifacts, review

    assert tidy.PROJECTIONS == artifacts.PROJECTIONS
    assert tidy.LEDGER == review.ledger_path()
    name = artifacts.projection_path(S, 12, "20261003T090000Z").name
    match = tidy.SNAPSHOT_NAME.match(name)
    assert (match["season"], int(match["gw"]), match["stamp"]) == \
        (S, 12, "20261003T090000Z")


def test_a_dry_run_lists_superseded_snapshots_and_deletes_none(tree, capsys):
    doomed = _snap(tree, S, 5, "20261001T090000Z")
    _snap(tree, S, 5, "20261003T090000Z")
    _ledger(tree, {"season": S, "gw": 5,
                   "projection_snapshot": "20261003T090000Z"})
    tidy.run_tidy(apply=False)
    assert doomed.exists()
    assert doomed.name in capsys.readouterr().out
