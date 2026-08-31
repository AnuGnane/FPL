"""Gate G1, D2: how much leak was there, and what did closing it cost?

Not a gate. Spec D2 is explicit that the as-of club ships whether or not eval
improves — a regression here would mean the old number was flattered by
leakage, which is a result and not a reason to withdraw. So there is no keep
rule to pre-register; what this script is, is the **measurement contract**
(plan A11):

* ``V9C_CLUB_COVERAGE`` — over the whole training frame: how many history
  rows matched a fixture, and how many of the matched rows carry a club that
  *differs* from the stamped ``team_code``. That second number is the leak,
  measured. If it is a handful of rows the eval delta will be noise, and
  saying so is the finding.
* ``V9C_CLUB_DEMO`` — the concrete demonstration G1 asks for, on the
  transferred player the driver picks *itself* (most diverging rows). Picking
  him automatically is the point: a hardcoded example can be chosen to
  flatter, and this one cannot.
* ``V9C_CLUB_DONE`` — ``evaluate_benchmark`` with the derivation off and on,
  in the same shape as ``scripts/v9c_rc_arm.py`` so the two cycles' tables sit
  beside each other.

Run it, watch it, read the lines::

    mkdir -p logs && caffeinate -i nohup .venv/bin/python scripts/v9c_club_eval.py \\
        > logs/v9c_club_eval.log 2>&1 &
    grep -e V9C_CLUB_COVERAGE -e V9C_CLUB_DEMO -e V9C_CLUB_DONE logs/v9c_club_eval.log

The "off" arm monkeypatches :func:`gaffer.features.bps.as_of_club_code` to
return the stamped ``team_code`` — the smallest possible intervention, and one
that runs the identical code path on both sides. As in Task 1's driver there
is a guard: if the two arms produce the same divergence count, the
intervention did not take, and the script exits rather than reporting a zero
delta that would read like a clean negative result.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import gaffer.evaluation as ev
from gaffer.features import bps
from gaffer.models import train as tr

_REAL = bps.as_of_club_code


def _stamped(df: pd.DataFrame, fixtures: pd.DataFrame) -> pd.Series:
    """The pre-v9c answer: whatever the store stamped on the row today."""
    return pd.to_numeric(df["team_code"], errors="coerce").fillna(0).astype(
        "int64")


def scores(payload: dict) -> dict:
    """The three numbers, in ``v9c_rc_arm.scores``'s shape."""
    table = payload["stratified"]["all"]
    return {"zeros": table["zeros"]["rmse"],
            "haulers": table["haulers"]["rmse"],
            "all": table["all"]["rmse"],
            "zeros_n": table["zeros"]["n"]}


def coverage(df: pd.DataFrame) -> dict:
    """Rows, matched rows, diverging rows — overall and per season.

    "Matched" is not directly observable off the finished frame, so it is read
    the way the derivation itself reads it: a row is matched when the derived
    club is one of the two sides of a fixture the join found. In practice the
    only unmatched rows are those that fell back, and a fallback row is
    exactly one whose derived club equals the stamped one *and* whose fixture
    lookup missed — indistinguishable from an unmoved player, which is why
    this reports the honest pair (fallback-or-unmoved, and diverging) rather
    than pretending to separate them.
    """
    club = pd.to_numeric(df["club_code"], errors="coerce")
    team = pd.to_numeric(df["team_code"], errors="coerce")
    diverging = (club.notna() & team.notna() & (club != team))
    per_season = {}
    for season, chunk in df.groupby("season_idx"):
        c = pd.to_numeric(chunk["club_code"], errors="coerce")
        t = pd.to_numeric(chunk["team_code"], errors="coerce")
        d = int((c.notna() & t.notna() & (c != t)).sum())
        per_season[int(season)] = {
            "rows": int(len(chunk)), "diverging": d,
            "diverging_frac": round(d / max(len(chunk), 1), 6)}
    return {"rows": int(len(df)),
            "club_code_present": int(club.notna().sum()),
            "diverging": int(diverging.sum()),
            "diverging_frac": round(int(diverging.sum())
                                    / max(len(df), 1), 6),
            "by_season": per_season}


def demo(df: pd.DataFrame) -> dict:
    """The transferred player with the most diverging rows, and his season."""
    club = pd.to_numeric(df["club_code"], errors="coerce")
    team = pd.to_numeric(df["team_code"], errors="coerce")
    mask = club.notna() & team.notna() & (club != team)
    if not mask.any():
        return {"found": False}
    counts = df.loc[mask].groupby("code").size().sort_values(ascending=False)
    code = int(counts.index[0])
    rows = df[df["code"] == code]
    season = int(rows.loc[mask.reindex(rows.index, fill_value=False),
                          "season_idx"].max())
    rows = rows[rows["season_idx"] == season].sort_values("gw")
    cols = [c for c in ("gw", "opp_code", "team_code", "club_code", "web_name",
                        "name") if c in rows.columns]
    return {"found": True, "code": code,
            "diverging_rows": int(counts.iloc[0]),
            "season_idx": season,
            "name": next((str(rows[c].iloc[0]) for c in ("web_name", "name")
                          if c in rows.columns), "?"),
            "table": rows[cols].to_dict("records")}


def main() -> None:
    out: dict = {}

    # --- the "off" arm: the stamped club, as it was before v9c ---------
    # Both bindings: ``train`` imports the name directly, so patching the
    # module attribute alone would leave ``load_training_frame`` calling the
    # real one and both arms would report the same frame. The guard below
    # would then refuse to report, which is the design working — but it is
    # cheaper to get it right here.
    bps.as_of_club_code = _stamped
    tr.as_of_club_code = _stamped
    try:
        off_frame, _, _ = tr.load_training_frame()
        out["coverage_off"] = coverage(off_frame)
        print("V9C_CLUB_COVERAGE off", json.dumps(out["coverage_off"]),
              flush=True)
        out["off"] = scores(ev.evaluate_benchmark())
        print("V9C_CLUB_DONE off", json.dumps(out["off"]), flush=True)
    finally:
        bps.as_of_club_code = _REAL
        tr.as_of_club_code = _REAL

    # --- the "on" arm: the derivation as it ships ----------------------
    on_frame, _, _ = tr.load_training_frame()
    out["coverage"] = coverage(on_frame)
    print("V9C_CLUB_COVERAGE on", json.dumps(out["coverage"]), flush=True)

    out["demo"] = demo(on_frame)
    print("V9C_CLUB_DEMO", json.dumps(out["demo"]), flush=True)

    if out["coverage"]["diverging"] == out["coverage_off"]["diverging"]:
        raise SystemExit(
            "the intervention did not take: both arms report "
            f"{out['coverage']['diverging']} diverging rows. The 'off' arm is "
            "supposed to monkeypatch bps.as_of_club_code away; if the "
            "training frame is built through a different import path, this "
            "measurement is worthless and must not be reported.")

    out["on"] = scores(ev.evaluate_benchmark())
    print("V9C_CLUB_DONE on", json.dumps(out["on"]), flush=True)

    out["delta"] = {k: round(out["on"][k] - out["off"][k], 4)
                    for k in ("zeros", "haulers", "all")}
    print("V9C_CLUB_DONE delta", json.dumps(out["delta"]), flush=True)

    Path("reports").mkdir(exist_ok=True)
    Path("reports/v9c_club_eval.json").write_text(json.dumps(out, indent=1,
                                                             default=str))


if __name__ == "__main__":
    main()
