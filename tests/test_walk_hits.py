"""scripts/walk_hits.py, the walk's hits against the objective's (holiday F-25).

A temporary tree of advice payloads: a week above the objective's hits, a
week below, a week equal, a file with no objective block, and last season's
file, so every relation and every reason is seen to be reached.
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "scripts")

import walk_hits  # noqa: E402 — scripts/ is not a package; the path insert must come first


def _advice(gw, hits, wanted, *, stamp="2026-09-20T17:00:00Z", steps=None,
            chosen="hits1", objective=True):
    payload = {"gw": gw, "generated_at": stamp, "hits": hits,
               "restraint": {"chosen": chosen, "bar": 0.55,
                             "steps": steps if steps is not None else
                             [{"below": "bank", "above": "ft1", "share": 0.7, "taken": True},
                              {"below": "ft1", "above": "hits1", "share": 0.6025,
                               "taken": True},
                              {"below": "hits1", "above": "hits2", "share": 0.4,
                               "taken": False, "reason": "too close to call"}]}}
    if objective:
        payload["objective"] = {"buys": [], "sells": [], "hits": wanted}
    return payload


def _tree(tmp_path, payloads):
    reports = tmp_path / "reports"
    reports.mkdir()
    for gw, payload in payloads.items():
        (reports / f"gw{gw}-advice.json").write_text(json.dumps(payload))
    return reports


def _lines(capsys):
    out = capsys.readouterr().out.splitlines()
    return out, json.loads(out[-1].split(" ", 1)[1])


def test_a_season_reads_above_below_and_equal_and_names_the_weeks(tmp_path, capsys):
    reports = _tree(tmp_path, {
        4: _advice(4, 1, 0),
        5: _advice(5, 0, 1, chosen="ft1", steps=[
            {"below": "bank", "above": "ft1", "share": 0.8, "taken": True},
            {"below": "ft1", "above": "hits1", "share": 0.5, "taken": False,
             "reason": "too close to call"}]),
        6: _advice(6, 0, 0, chosen=None, steps=[]),
        7: _advice(7, 1, 1, objective=False),
    })
    walk_hits.main(reports)
    out, summary = _lines(capsys)
    rows = [json.loads(line.split(" ", 1)[1]) for line in out[:-1]]
    assert [line.split(" ", 1)[0] for line in out] == ["WALK_HITS_GW"] * 4 + ["WALK_HITS"]
    by_gw = {r["gw"]: r for r in rows}
    assert by_gw[4]["relation"] == "above" and by_gw[4]["last_taken_share"] == 0.6025
    assert by_gw[5]["relation"] == "below" and by_gw[5]["last_taken_share"] == 0.8
    assert by_gw[6]["relation"] == "equal" and by_gw[6]["chosen"] == "bank"
    assert by_gw[6]["last_taken_share"] is None
    assert by_gw[7] == {"gw": 7, "reason": "no objective block"}
    assert summary["read"] == 3 and summary["skipped"] == 1
    assert (summary["above"], summary["below"], summary["equal"]) == (1, 1, 1)
    assert summary["above_gws"] == [4] and summary["below_gws"] == [5]
    assert summary["verdict"] == "hold"


def test_the_label_is_read_through_narrated(tmp_path):
    rows, _ = walk_hits.read_season(_tree(tmp_path, {4: _advice(4, 1, 0)}))
    assert rows[0]["label"]


def test_three_weeks_above_make_the_rule_worth_an_arm(tmp_path):
    reports = _tree(tmp_path, {gw: _advice(gw, 1, 0) for gw in (3, 4, 5)})
    _, summary = walk_hits.read_season(reports)
    assert summary["above_gws"] == [3, 4, 5] and summary["verdict"] == "arm"


def test_last_seasons_file_is_not_this_seasons(tmp_path):
    reports = _tree(tmp_path, {
        30: _advice(30, 1, 0, stamp="2026-04-01T17:00:00Z"),
        4: _advice(4, 0, 0, stamp="2026-09-20T17:00:00Z"),
    })
    rows, summary = walk_hits.read_season(reports)
    assert [r["gw"] for r in rows] == [4]
    assert summary["season_from"] == "2026-07-01" and summary["above"] == 0


def test_a_missing_reports_directory_prints_the_line_with_a_reason(tmp_path, capsys):
    walk_hits.main(tmp_path / "reports")
    out, summary = _lines(capsys)
    assert len(out) == 1 and out[0].startswith("WALK_HITS ")
    assert summary["read"] == 0 and "no " in summary["reason"]


def test_an_unreadable_file_is_named_not_raised(tmp_path):
    reports = _tree(tmp_path, {4: _advice(4, 1, 0)})
    (reports / "gw5-advice.json").write_text("{not json")
    rows, summary = walk_hits.read_season(reports)
    assert rows[1] == {"gw": 5, "reason": "unreadable: JSONDecodeError"}
    assert summary["read"] == 1 and summary["skipped"] == 1


def test_an_empty_reports_directory_says_so(tmp_path):
    (tmp_path / "reports").mkdir()
    _, summary = walk_hits.read_season(tmp_path / "reports")
    assert summary["read"] == 0 and "gw{n}-advice.json" in summary["reason"]


def test_a_restraint_block_narrated_cannot_read_is_named_not_raised(tmp_path):
    broken = _advice(4, 1, 0, steps=[{"below": "bank", "above": "ft1", "share": 0.3,
                                      "taken": False}])
    rows, summary = walk_hits.read_season(_tree(tmp_path, {4: broken}))
    assert rows == [{"gw": 4, "reason": "unreadable advice: KeyError"}]
    assert summary["read"] == 0


def test_an_advice_with_no_restraint_block_reads_no_walk_not_bank(tmp_path):
    payload = _advice(4, 0, 0)
    del payload["restraint"]
    rows, _ = walk_hits.read_season(_tree(tmp_path, {4: payload}))
    assert rows[0]["chosen"] is None and rows[0]["relation"] == "equal"


def test_a_nan_share_reads_null_so_the_line_stays_json(tmp_path, capsys):
    payload = _advice(4, 1, 0, steps=[{"below": "bank", "above": "hits1",
                                       "share": float("nan"), "taken": True,
                                       "line": "written at bank time"}])
    walk_hits.main(_tree(tmp_path, {4: payload}))
    line = capsys.readouterr().out.splitlines()[0]
    assert "NaN" not in line and json.loads(line.split(" ", 1)[1])["last_taken_share"] is None
