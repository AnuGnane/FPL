"""scripts/v20d_runs.py, v20d's per-Thursday lever lines (holiday F-16).

A temporary tree: an advise log, a price log and advice payloads, for a
banked run with a drop sale, a run that did not bank, and a run banked a day
early, so each of the table's rows is seen to be reached.
"""

from __future__ import annotations

import json
import sys

import pandas as pd

from gaffer.data import store
from gaffer.price_log import PRICE_LOG_COLS, PRICE_LOG_PATH

sys.path.insert(0, "scripts")

import v20d_runs  # noqa: E402 — scripts/ is not a package; the path insert must come first

# Thursdays in UTC: 09-17 (GW5), 09-24 (GW6), 10-01 (GW7).
GW5, GW6, GW7 = "2026-09-17", "2026-09-24", "2026-10-01"


def _row(day, code, pct, calibrating=False):
    direction = "drop" if pct < 0 else ("rise" if pct > 0 else "flat")
    return {"snap_date": day, "code": code, "now_cost": 50,
            "price_change_percent": pct, "direction": direction,
            "calibrating": calibrating}


def _prices(rows):
    return pd.DataFrame(rows, columns=PRICE_LOG_COLS)


def _payload(gw, stamp, sells, charge):
    return {"gw": gw, "generated_at": stamp, "sells": [{"code": c} for c in sells],
            "plan_by_gw": [{"gw": gw, "sells": [{"code": c} for c in sells],
                            "trace": {"gw": gw, "price_charge": charge}},
                           {"gw": gw + 1, "sells": [], "trace": None}]}


def _log(*chunks):
    return "\n".join(chunks) + "\n"


def _header(gw):
    return f"=== GW{gw} — deadline 2026-09-19T10:00:00Z ==="


def test_a_banked_run_with_a_charged_drop_sale_reads_live():
    prices = _prices([_row(GW5, 1, -80.0), _row(GW5, 2, 10.0)])
    payloads = [_payload(5, f"{GW5}T17:02:00+00:00", [1], 0.42)]
    runs, row = v20d_runs.reading(_log("Trained on 9 rows.", _header(5)),
                                  payloads, prices)
    assert len(runs) == 1
    run = runs[0]
    assert run["rows_that_day"] == 2 and run["drop_sells"] == [1]
    assert run["log_failure"] is None and run["log_runs"] == 1
    assert run["lever"] == "banked, drop sale charged"
    assert row["row"] == "live" and row["short"] is True and row["runs"] == 1


def test_a_run_whose_step_failed_is_the_first_row_whatever_the_price_log_holds():
    prices = _prices([_row(GW6, 1, -80.0)])
    text = _log(_header(5), "price reading not banked: timed out", _header(6))
    payloads = [_payload(6, f"{GW6}T17:00:00+00:00", [1], 0.4)]
    runs, row = v20d_runs.reading(text, payloads, prices)
    assert runs[0]["log_failure"] == "price reading not banked: timed out"
    assert runs[0]["lever"] == "step: not banked"
    assert row["row"] == "step"


def test_a_failure_line_belongs_to_the_header_below_it_not_above():
    text = _log("price reading not banked: x", _header(5), _header(6))
    logged = v20d_runs.log_runs(text)
    assert logged[5]["failures"] == ["price reading not banked: x"]
    assert logged[6]["failures"] == []


def test_a_run_banked_a_day_early_is_the_first_row():
    prices = _prices([_row("2026-09-30", 1, -80.0)])
    payloads = [_payload(7, f"{GW7}T17:00:00+00:00", [1], 0.0)]
    runs, row = v20d_runs.reading(_log(_header(7)), payloads, prices)
    assert runs[0]["rows_that_day"] == 0
    assert runs[0]["last_banked_before"] == "2026-09-30"
    assert runs[0]["lever"] == "step: banked a different day"
    assert row["row"] == "step"


def test_every_run_banked_and_no_drop_sale_is_no_evidence():
    prices = _prices([_row(d, 1, -50.0) for d in (GW5, GW6, GW7)]
                     + [_row(d, 2, 5.0) for d in (GW5, GW6, GW7)])
    payloads = [_payload(5, f"{GW5}T17:00:00+00:00", [2], None),
                _payload(6, f"{GW6}T17:00:00+00:00", [], None),
                _payload(7, f"{GW7}T17:00:00+00:00", [2], None)]
    text = _log(_header(5), _header(6), _header(7))
    runs, row = v20d_runs.reading(text, payloads, prices)
    assert [r["lever"] for r in runs] == ["banked, no drop sale"] * 3
    assert row == {"runs": 3, "short": False, "row": "no evidence", "reason": None}


def test_an_uncharged_drop_sale_is_the_reader_row_even_beside_a_charged_one():
    prices = _prices([_row(GW5, 1, -80.0), _row(GW6, 1, -80.0)])
    payloads = [_payload(5, f"{GW5}T17:00:00+00:00", [1], 0.3),
                _payload(6, f"{GW6}T17:00:00+00:00", [1], 0.0)]
    runs, row = v20d_runs.reading(_log(_header(5), _header(6)), payloads, prices)
    assert runs[1]["lever"] == "banked, drop sale uncharged"
    assert row["row"] == "reader"


def test_a_calibrating_drop_is_not_a_drop_sale():
    prices = _prices([_row(GW5, 1, -80.0, calibrating=True)])
    payloads = [_payload(5, f"{GW5}T17:00:00+00:00", [1], None)]
    runs, _ = v20d_runs.reading(_log(_header(5)), payloads, prices)
    assert runs[0]["drop_sells"] == [] and runs[0]["lever"] == "banked, no drop sale"


def test_only_the_earliest_thursday_payload_since_gw5_is_a_run():
    payloads = [_payload(5, f"{GW5}T19:30:00+00:00", [], None),   # a web re-run
                _payload(5, f"{GW5}T17:01:00+00:00", [], None),   # the plist's
                _payload(5, "2026-09-18T08:00:00+00:00", [], None),  # a Friday
                _payload(4, "2026-09-10T17:00:00+00:00", [], None)]  # before v19b
    runs = v20d_runs.thursday_runs(payloads)
    assert [r["generated_at"] for r in runs] == [f"{GW5}T17:01:00+00:00"]


def test_a_missing_log_reads_no_reading_with_its_reason():
    prices = _prices([_row(GW5, 1, -80.0)])
    payloads = [_payload(5, f"{GW5}T17:00:00+00:00", [1], 0.3)]
    runs, row = v20d_runs.reading(None, payloads, prices)
    assert runs[0]["lever"] == "no reading"
    assert "no advise log" in runs[0]["reason"]
    assert row["row"] is None and "GW[5]" in row["reason"]


def test_an_empty_tree_prints_both_lines_with_reasons_and_no_traceback(
        tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    assert v20d_runs.main() == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1 and out[0].startswith("V20D_ROW ")
    row = json.loads(out[0].removeprefix("V20D_ROW "))
    assert row["row"] is None and "no reports directory" in row["reason"]


def test_main_reads_a_whole_tree_and_tolerates_a_corrupt_report(
        tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "advise.log").write_text(_log(_header(5)))
    (tmp_path / "data" / "live").mkdir(parents=True)
    _prices([_row(GW5, 1, -80.0)]).to_parquet(tmp_path / "data" / PRICE_LOG_PATH)
    history = tmp_path / "reports" / "advice_history"
    history.mkdir(parents=True)
    (history / f"gw5-{GW5}T17:00:00+00:00.json").write_text(
        json.dumps(_payload(5, f"{GW5}T17:00:00+00:00", [1], 0.4)))
    (tmp_path / "reports" / "gw5-advice.json").write_text("{not json")
    assert v20d_runs.main() == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert [ln.split(" ", 1)[0] for ln in lines] == ["V20D_RUN", "V20D_ROW"]
    assert json.loads(lines[1].split(" ", 1)[1])["row"] == "live"
