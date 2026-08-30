"""The standalone seed aggregator: banked reports -> one multi-seed reading."""

from __future__ import annotations

import json
import sys

import pytest

sys.path.insert(0, "scripts")

import seed_stats  # noqa: E402
import v7b_replay  # noqa: E402

ARM = {"arm": "heur", "n": 40, "chips": True, "priors": "current",
       "minutes": "current", "frame": "current", "noise_asset": None}


def _report(path, total, base, **overrides):
    """One banked v7b report: a total and the config echo it was run under."""
    config = dict(ARM, seed_base=base, tag=path.stem, **overrides)
    path.write_text(json.dumps({"total": total, "config": config}),
                    encoding="utf-8")
    return str(path)


def test_a_report_gives_up_its_total_its_seed_base_and_its_config(tmp_path):
    total, base, config = seed_stats.read_report(_report(tmp_path / "a.json",
                                                         1876, 20260901))
    assert (total, base) == (1876, 20260901)
    assert config["arm"] == "heur" and config["chips"] is True


def test_a_report_with_no_recorded_base_still_reads(tmp_path):
    """Reports predating --seed-base carry no config block; the total is what
    the aggregate needs."""
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"total": 1799}), encoding="utf-8")
    assert seed_stats.read_report(path) == (1799, None, None)


def test_the_aggregate_is_the_mean_spread_and_range(tmp_path, capsys):
    """The only same-arm banked pair: q1b 1876 and q1c 1901, spread 25."""
    paths = [_report(tmp_path / "q1b.json", 1876, 20260901),
             _report(tmp_path / "q1c.json", 1901, 20260915)]
    out = seed_stats.main(paths)
    assert out == {"totals": [1876, 1901], "mean": 1888.5,
                   "spread": 25, "range": [1876, 1901],
                   "seed_bases": [20260901, 20260915]}
    printed = capsys.readouterr().out.strip().splitlines()
    assert "total=1876" in printed[0]
    assert json.loads(printed[-1]) == out


def test_a_mixed_arm_trio_is_refused_rather_than_averaged(tmp_path, capsys):
    """v7b's q2-ctrl-heur is a chips-off/priors-off control. Averaging it with
    the two chips-on runs produced a "spread" of 115 that is an arm gap wearing
    a seed spread's clothes."""
    paths = [_report(tmp_path / "q1b.json", 1876, 20260901),
             _report(tmp_path / "q1c.json", 1901, 20260915),
             _report(tmp_path / "q2ctrl.json", 1786, 20260825,
                     chips=False, priors="off")]
    with pytest.raises(SystemExit) as exc:
        seed_stats.main(paths)
    assert exc.value.code == 2
    printed = capsys.readouterr().out
    assert "chips" in printed and "priors" in printed
    assert "q2ctrl.json" in printed
    assert "totals" not in printed


def test_a_report_with_no_config_will_not_mix_with_a_configured_one(tmp_path):
    """An unknown arm is not a matching arm: the pre-config report might be
    anything, and "probably the same" is how the 115 happened."""
    old = tmp_path / "old.json"
    old.write_text(json.dumps({"total": 1799}), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        seed_stats.main([_report(tmp_path / "a.json", 1876, 20260901),
                         str(old)])
    assert exc.value.code == 2


def test_configs_differing_only_in_seed_base_and_tag_aggregate(tmp_path,
                                                               capsys):
    """Those two fields are the point of a multi-seed run; everything else
    matching is what makes the spread a seed spread."""
    seed_stats.main([_report(tmp_path / "a.json", 1876, 20260901),
                     _report(tmp_path / "b.json", 1901, 20260915)])
    assert "totals" in capsys.readouterr().out


def test_a_missing_file_is_one_line_and_no_traceback(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        seed_stats.main([str(tmp_path / "nope.json")])
    assert exc.value.code == 2
    assert "nope.json" in capsys.readouterr().out


def test_the_aggregator_and_the_driver_agree_key_for_key():
    """Six lines of arithmetic exist in two places so the aggregator stays
    importable without lightgbm. This is what stops the copy drifting."""
    outs = [{"total": 1876}, {"total": 1901}]
    bases = [20260901, 20260915]
    assert seed_stats.aggregate([o["total"] for o in outs], bases) == \
        v7b_replay.multiseed_summary(outs, bases)


def test_no_arguments_is_a_usage_error():
    with pytest.raises(SystemExit):
        seed_stats.main([])
