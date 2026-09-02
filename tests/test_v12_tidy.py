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
