"""scripts/v20d_brier.py, the price term's Brier against the base rate (holiday F-12).

A synthetic log on a temporary data directory: a fall, a hold, a gap day
and a missing next day, so each exclusion rule is seen to bite.
"""

from __future__ import annotations

import json
import sys

import pandas as pd
import pytest

from gaffer.data import store
from gaffer.price_log import PRICE_LOG_COLS, PRICE_LOG_PATH

sys.path.insert(0, "scripts")

import v20d_brier  # noqa: E402


def _row(day, code, cost, pct, calibrating=False):
    direction = "drop" if pct < 0 else ("rise" if pct > 0 else "flat")
    return {"snap_date": day, "code": code, "now_cost": cost,
            "price_change_percent": pct, "direction": direction,
            "calibrating": calibrating}


def _log(rows):
    return pd.DataFrame(rows, columns=PRICE_LOG_COLS)


SYNTHETIC = [
    # 10-01 -> 10-02: code 1 falls (p = 0.8), code 2 holds (p = 0.4).
    _row("2026-10-01", 1, 60, -80.0),
    _row("2026-10-01", 2, 50, -40.0),
    _row("2026-10-02", 1, 59, 0.0),
    _row("2026-10-02", 2, 50, -20.0),
    # 10-03 is a gap day, so 10-02's drop has no next day and is not scored.
    _row("2026-10-04", 3, 70, -150.0),
    # Code 3 has no row on 10-05: a missing next day for that code.
    _row("2026-10-05", 4, 45, 10.0),
]


def test_a_fall_and_a_hold_are_scored_and_the_gap_and_missing_days_are_not():
    out = v20d_brier.brier_reading(_log(SYNTHETIC))
    assert out["n"] == 2 and out["drop_rows"] == 2 and out["drop_days"] == 1
    assert out["falls"] == 1 and out["base_rate"] == 0.5
    # Term: ((0.8 - 1)^2 + (0.4 - 0)^2) / 2 = (0.04 + 0.16) / 2.
    assert out["brier_term"] == pytest.approx(0.1)
    assert out["brier_base"] == pytest.approx(0.25)
    assert out["verdict"].startswith("short: 1 drop-days")


def test_a_reading_past_a_hundred_percent_is_clipped_to_one():
    rows = [_row("2026-10-01", 1, 60, -130.0), _row("2026-10-02", 1, 59, 0.0)]
    out = v20d_brier.brier_reading(_log(rows))
    assert out["brier_term"] == 0.0


def test_calibrating_rows_are_left_out_as_the_term_leaves_them_out():
    rows = [_row("2026-10-01", 1, 60, -80.0, calibrating=True),
            _row("2026-10-02", 1, 59, 0.0)]
    out = v20d_brier.brier_reading(_log(rows))
    assert out["n"] == 0 and out["reason"]


def _many_days(fell_when_flagged: bool):
    """Thirty-one drop-days. Each day flags two fresh codes, one at 90% and
    one at 10%, and the next day's rows say which fell: the 90% one when the
    term is right, the 10% one when it is backwards."""
    rows = []
    start = pd.Timestamp("2026-08-31")
    for i in range(31):
        day = (start + pd.Timedelta(days=i)).date().isoformat()
        nxt = (start + pd.Timedelta(days=i + 1)).date().isoformat()
        high, low = 100 + 2 * i, 101 + 2 * i
        rows.append(_row(day, high, 60, -90.0))
        rows.append(_row(day, low, 50, -10.0))
        rows.append(_row(nxt, high, 59 if fell_when_flagged else 60, 0.0))
        rows.append(_row(nxt, low, 50 if fell_when_flagged else 49, 0.0))
    return _log(rows)


def test_over_thirty_drop_days_a_better_term_lets_the_default_stand():
    out = v20d_brier.brier_reading(_many_days(fell_when_flagged=True))
    assert out["drop_days"] >= 30
    assert out["brier_term"] < out["brier_base"]
    assert out["verdict"] == "term no worse than base rate: default stands"


def test_over_thirty_drop_days_a_worse_term_sends_a_ruling():
    out = v20d_brier.brier_reading(_many_days(fell_when_flagged=False))
    assert out["drop_days"] >= 30
    assert out["brier_term"] > out["brier_base"]
    assert out["verdict"] == "term worse than base rate: ruling to the user"


def test_a_missing_log_prints_the_line_with_n_zero_and_a_reason(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    assert v20d_brier.main() == 0
    line = capsys.readouterr().out.strip()
    assert line.startswith("V20D_BRIER ")
    payload = json.loads(line.removeprefix("V20D_BRIER "))
    assert payload["n"] == 0 and "no price log" in payload["reason"]


def test_a_one_day_log_is_short_and_says_so(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    (tmp_path / "live").mkdir()
    _log([_row("2026-10-01", 1, 60, -80.0)]).to_parquet(
        tmp_path / PRICE_LOG_PATH)
    v20d_brier.main()
    payload = json.loads(capsys.readouterr().out.removeprefix("V20D_BRIER "))
    assert payload["n"] == 0 and payload["reason"] == "fewer than two banked days"


def test_a_corrupt_log_prints_the_line_and_no_traceback(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    (tmp_path / "live").mkdir()
    (tmp_path / PRICE_LOG_PATH).write_bytes(b"not a parquet")
    assert v20d_brier.main() == 0
    payload = json.loads(capsys.readouterr().out.removeprefix("V20D_BRIER "))
    assert payload["n"] == 0 and "unreadable" in payload["reason"]


def test_the_script_writes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    (tmp_path / "live").mkdir()
    _log(SYNTHETIC).to_parquet(tmp_path / PRICE_LOG_PATH)
    before = sorted(p.name for p in tmp_path.rglob("*"))
    v20d_brier.main()
    assert sorted(p.name for p in tmp_path.rglob("*")) == before
