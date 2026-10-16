"""scripts/trace_gap.py, the trace's unattributed share (holiday F-86).

A temporary tree of advice payloads: a current file with two traced weeks,
its history copy (the same ``gw`` and ``generated_at``, read once), a week
whose gain could not be priced, an unreadable file and a payload with no
trace, so every reason is seen to be reached.
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "scripts")

import trace_gap  # noqa: E402 — scripts/ is not a package; the path insert must come first


def _week(gw, xpts, *, ep_gain=1.0, hit_cost=0.0, ft_use_penalty=0.0,
          price_charge=None, traced=True):
    week = {"gw": gw, "expected_pts": xpts}
    if traced:
        week["trace"] = {"gw": gw, "ep_gain": ep_gain, "hit_cost": hit_cost,
                         "ft_use_penalty": ft_use_penalty,
                         "price_charge": price_charge, "ft_shadow": 1.5,
                         "bank_value": 0.2}
    return week


def _advice(gw, weeks, stamp="2026-10-01T17:00:00Z"):
    return {"gw": gw, "generated_at": stamp, "plan_by_gw": weeks}


def _tree(tmp_path, current=None, history=None, raw=None):
    reports = tmp_path / "reports"
    (reports / "advice_history").mkdir(parents=True)
    for name, payload in (current or {}).items():
        (reports / name).write_text(json.dumps(payload))
    for name, payload in (history or {}).items():
        (reports / "advice_history" / name).write_text(json.dumps(payload))
    for name, text in (raw or {}).items():
        (reports / name).write_text(text)
    return reports


def test_the_sum_is_the_gain_less_the_three_charges():
    """ft_shadow and bank_value are valuations, not charges, so they stay
    out of the sum whatever they hold."""
    from gaffer.served import ServedWeek
    week = ServedWeek.model_validate(_week(5, 50.0, ep_gain=4.0, hit_cost=4.0,
                                           ft_use_penalty=0.5,
                                           price_charge=0.25))
    attributed = 4.0 - 4.0 - 0.5 - 0.25
    assert trace_gap.week_share(week) == (50.0 - attributed) / 50.0


def test_an_unpriced_gain_or_no_trace_is_not_read_as_zero():
    from gaffer.served import ServedWeek
    assert trace_gap.week_share(
        ServedWeek.model_validate(_week(5, 50.0, ep_gain=None))) is None
    assert trace_gap.week_share(
        ServedWeek.model_validate(_week(5, 50.0, traced=False))) is None
    assert trace_gap.week_share(
        ServedWeek.model_validate(_week(5, 0.0))) is None


def test_a_file_reads_its_weeks_and_a_history_copy_is_read_once(tmp_path):
    payload = _advice(5, [_week(5, 50.0, ep_gain=2.0), _week(6, 40.0, ep_gain=0.0)])
    reports = _tree(tmp_path, current={"gw5-advice.json": payload},
                    history={"gw5-20261001T170000.json": payload})
    rows, summary = trace_gap.read_all(reports)
    assert len(rows) == 1
    row = rows[0]
    assert row["gw"] == 5 and row["weeks_traced"] == 2
    assert row["min"] == round(48 / 50, 4) and row["max"] == 1.0
    assert row["share"] == round((48 + 40) / 90, 4)
    assert summary["files"] == 1 and summary["weeks"] == 2
    assert summary["spread"] == round(1.0 - 48 / 50, 4)
    assert summary["verdict"] == "ruling"


def test_a_spread_at_the_bar_or_above_holds(tmp_path):
    reports = _tree(tmp_path, current={
        "gw5-advice.json": _advice(5, [_week(5, 50.0, ep_gain=0.0)]),
        "gw6-advice.json": _advice(6, [_week(6, 50.0, ep_gain=5.0)],
                                   stamp="2026-10-08T17:00:00Z")})
    _, summary = trace_gap.read_all(reports)
    assert summary["spread"] == 0.1
    assert summary["verdict"] == "hold"


def test_every_reason_prints_a_line_and_not_a_traceback(tmp_path, capsys):
    reports = _tree(
        tmp_path,
        current={"gw7-advice.json": _advice(7, [_week(7, 50.0, ep_gain=None)]),
                 "gw8-advice.json": _advice(8, [_week(8, 50.0, traced=False)]),
                 "gw9-advice.json": {"gw": "nine"},
                 "gw10-advice.json": {"gw": [1], "generated_at": "x"}},
        raw={"gw4-advice.json": "{not json"})
    trace_gap.main(reports)
    lines = capsys.readouterr().out.splitlines()
    gaps = [json.loads(ln.removeprefix("TRACE_GAP ")) for ln in lines
            if ln.startswith("TRACE_GAP ")]
    assert [g["reason"] for g in gaps] == [
        "unreadable advice",
        "unreadable: JSONDecodeError",
        "no traced week with a priced gain",
        "no traced week with a priced gain",
        "unreadable advice"]
    summary = json.loads(lines[-1].removeprefix("TRACE_GAPS "))
    assert summary["files"] == 0 and summary["skipped"] == 5
    assert summary["verdict"] == "hold"
    assert "reason" in summary


def test_no_reports_directory_is_a_line_with_a_reason(tmp_path, capsys):
    trace_gap.main(tmp_path / "reports")
    out = capsys.readouterr().out.strip()
    assert out.startswith("TRACE_GAPS ")
    assert json.loads(out.removeprefix("TRACE_GAPS "))["reason"] == (
        f"no {tmp_path / 'reports'}/ directory")
