"""The standalone seed aggregator: banked reports -> one multi-seed reading."""

from __future__ import annotations

import json
import sys

import pytest

sys.path.insert(0, "scripts")

import seed_stats  # noqa: E402
import v7b_replay  # noqa: E402


def _report(path, total, base):
    payload = {"total": total, "config": {"seed_base": base}}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_a_report_gives_up_its_total_and_its_seed_base(tmp_path):
    path = _report(tmp_path / "a.json", 1876, 20260901)
    assert seed_stats.read_report(path) == (1876, 20260901)


def test_a_report_with_no_recorded_base_still_reads(tmp_path):
    """Reports predating --seed-base carry no config block; the total is what
    the aggregate needs."""
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"total": 1799}), encoding="utf-8")
    assert seed_stats.read_report(path) == (1799, None)


def test_the_aggregate_is_the_mean_spread_and_range(tmp_path, capsys):
    """The v7b heuristic trio, read back off disk: one number per run, and a
    spread of 115 points that no arm gap in the cycle came close to."""
    paths = [_report(tmp_path / "a.json", 1876, 20260901),
             _report(tmp_path / "b.json", 1901, 20260915),
             _report(tmp_path / "c.json", 1786, 20260825)]
    out = seed_stats.main(paths)
    assert out == {"totals": [1876, 1901, 1786], "mean": 1854.3,
                   "spread": 115, "range": [1786, 1901],
                   "seed_bases": [20260901, 20260915, 20260825]}
    printed = capsys.readouterr().out.strip().splitlines()
    assert "total=1876" in printed[0]
    assert json.loads(printed[-1]) == out


def test_the_aggregator_and_the_driver_agree_key_for_key():
    """Six lines of arithmetic exist in two places so the aggregator stays
    importable without lightgbm. This is what stops the copy drifting."""
    outs = [{"total": 1876}, {"total": 1901}, {"total": 1786}]
    bases = [20260901, 20260915, 20260825]
    assert seed_stats.aggregate([o["total"] for o in outs], bases) == \
        v7b_replay.multiseed_summary(outs, bases)


def test_no_arguments_is_a_usage_error():
    with pytest.raises(SystemExit):
        seed_stats.main([])
