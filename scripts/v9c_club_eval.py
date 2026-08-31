"""Gate G1, D2: how much leak was there, and what did closing it cost?

Not a gate. Spec D2 is explicit that the as-of club ships whether or not eval
improves — a regression here would mean the old number was flattered by
leakage, which is a result and not a reason to withdraw. So there is no keep
rule to pre-register; what this script is, is the **measurement contract**
(plan A11):

* ``V9C_CLUB_COVERAGE`` — over the whole training frame: the **fixture-join
  match rate**, measured before the fallback is applied, and how many of the
  matched rows carry a club that *differs* from the stamped ``team_code``.
  That second number is the leak, measured. If it is a handful of rows the
  eval delta will be noise, and saying so is the finding.

  The match rate is computed by re-running the join and counting the rows it
  actually resolved. An earlier version of this script reported
  ``club_code.notna()`` and called it coverage; that is 100 % by construction,
  because the fallback fills every row before anything downstream sees it.
  A metric that cannot come out below 100 % is not measuring anything.
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
from gaffer.features.bps import _fixture_lookup
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


def matched_mask(df: pd.DataFrame, fixtures: pd.DataFrame) -> pd.Series:
    """Which rows the fixture join actually resolved, *before* the fallback.

    This is the honest coverage number and it has to be computed here rather
    than read off the finished frame. ``as_of_club_code`` fills every
    unmatched row with the stamped ``team_code`` before it returns, so by the
    time anything downstream sees ``club_code`` there is nothing left to
    count: ``club_code.notna()`` is 100 % by construction and says nothing
    about how much of the history the fixture archive actually covers.

    So the lookup is rebuilt and the row keys are zipped exactly as the
    derivation zips them. A row is matched when its
    ``(season_idx, gw, kickoff_time, opp_code)`` names a fixture that is not
    ``None`` — the poisoned-duplicate case counts as unmatched, which is what
    it is.
    """
    lookup = _fixture_lookup(fixtures)
    rows = zip(pd.to_numeric(df["season_idx"], errors="coerce"),
               pd.to_numeric(df["gw"], errors="coerce"),
               df["kickoff_time"].astype("string"),
               pd.to_numeric(df["opp_code"], errors="coerce"))
    return pd.Series([lookup.get((s, g, k, o)) is not None
                      for s, g, k, o in rows], index=df.index)


def coverage(df: pd.DataFrame, fixtures: pd.DataFrame) -> dict:
    """Rows, matched rows, diverging rows — overall and per season."""
    club = pd.to_numeric(df["club_code"], errors="coerce")
    team = pd.to_numeric(df["team_code"], errors="coerce")
    matched = matched_mask(df, fixtures)
    diverging = (club.notna() & team.notna() & (club != team))
    per_season = {}
    for season, chunk in df.groupby("season_idx"):
        c = pd.to_numeric(chunk["club_code"], errors="coerce")
        t = pd.to_numeric(chunk["team_code"], errors="coerce")
        m = matched.reindex(chunk.index)
        d = int((c.notna() & t.notna() & (c != t)).sum())
        per_season[int(season)] = {
            "rows": int(len(chunk)),
            "matched": int(m.sum()),
            "match_rate": round(int(m.sum()) / max(len(chunk), 1), 6),
            "diverging": d,
            # Divergence is a fraction *of the matched rows*: an unmatched row
            # cannot diverge, so putting it in the denominator would dilute the
            # leak with rows that never had a chance to show it.
            "diverging_frac_of_matched": round(d / max(int(m.sum()), 1), 6)}
    return {"rows": int(len(df)),
            "matched": int(matched.sum()),
            "match_rate": round(int(matched.sum()) / max(len(df), 1), 6),
            "diverging": int(diverging.sum()),
            "diverging_frac_of_matched": round(
                int(diverging.sum()) / max(int(matched.sum()), 1), 6),
            "diverging_frac_of_all": round(int(diverging.sum())
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


def _fixtures_frame() -> pd.DataFrame:
    """The same fixture list ``load_training_frame`` joins against."""
    from gaffer.data import store

    fixtures = store.load("history/fixtures.parquet")
    if store.exists("live/fixtures.parquet"):
        fixtures = pd.concat([fixtures, store.load("live/fixtures.parquet")],
                             ignore_index=True)
    return fixtures


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
        out["coverage_off"] = coverage(off_frame, _fixtures_frame())
        print("V9C_CLUB_COVERAGE off", json.dumps(out["coverage_off"]),
              flush=True)
        out["off"] = scores(ev.evaluate_benchmark())
        print("V9C_CLUB_DONE off", json.dumps(out["off"]), flush=True)
    finally:
        bps.as_of_club_code = _REAL
        tr.as_of_club_code = _REAL

    # --- the "on" arm: the derivation as it ships ----------------------
    on_frame, _, _ = tr.load_training_frame()
    out["coverage"] = coverage(on_frame, _fixtures_frame())
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
