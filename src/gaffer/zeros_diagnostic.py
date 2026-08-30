"""Where the zeros-stratum error actually lives (v7-model spec §2.1).

The 2026-08-29 evaluation put zeros RMSE at 1.063 against a naive last-5
baseline's 1.042: the model over-forecasts players who end up playing no
minutes, and it does so badly enough that not modelling them at all would be
better. That is one number over 4929 rows, and it does not say *which* rows.

This decomposes it. Nothing here fits anything or gates anything — it is a
report, and its only job is to decide which intervention in spec §2.2 is
worth attempting. Strata are computed from leakage-safe training-frame
columns only (``season_start_share`` is shifted within the season,
``minutes_r5`` is a shifted rolling mean), so the decomposition is one a live
run could have made about itself.

The official-flag stratum spec §2.1 asks for is not derivable: status is a
live bootstrap field, the historical frame has no column for it, and the
banked ``reports/availability_gw*.parquet`` snapshots do not reach back into
the holdout. It is reported with ``n = 0`` and a note rather than faked, and
``recent_absence`` stands in for it — "was he already visibly out of the
picture" answered from stored features.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from gaffer.artifacts import REPORTS

FRINGE_SHARE = 0.3
"""``season_start_share`` below which a player is fringe rather than a regular.

Spec §2.1's threshold. The feature is the mean of ``starts`` over this
season's earlier matches, so 0.3 is "started under a third of the season so
far" — a rotation option, not a benchwarmer and not a nailed starter.
"""

COLD_START_GWS = 4
"""Gameweeks at the front of a season that count as a cold start.

Promoted clubs and new signings have no ``season_start_share`` worth reading
and the rolling windows are still full of last season, which is exactly where
a minutes model is expected to be worst.
"""

DNP_DECILES = 10

ZERO_STRATA = ("fringe", "regular", "cold_start", "settled",
               "recent_absence", "recent_presence")
"""The six derivable sub-populations, in complementary pairs.

``flagged``/``unflagged`` would be a fourth pair and is reported separately,
empty, with the reason — see the module docstring.
"""

FLAGGED_NOTE = ("no availability snapshot covers the holdout slots — official "
                "status is a live bootstrap field and is not stored "
                "historically, so this stratum is not derivable")


def _mask(frame: pd.DataFrame, column: str, test) -> pd.Series:
    """``test`` applied to a numeric ``column``, or all-False when it is absent.

    A stratum built on a column the frame does not carry is *unknown*, not
    empty-because-nobody-qualified, and the two have to look different in the
    report. Reporting ``n = 0`` for both is the honest compromise: the count
    is what says whether the numbers mean anything.
    """
    if column not in frame.columns:
        return pd.Series(False, index=frame.index)
    return test(pd.to_numeric(frame[column], errors="coerce"))


def stratify(scored: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """The scored holdout frame split into :data:`ZERO_STRATA`."""
    fringe = _mask(scored, "season_start_share", lambda s: s < FRINGE_SHARE)
    regular = _mask(scored, "season_start_share", lambda s: s >= FRINGE_SHARE)
    cold = _mask(scored, "gw", lambda s: s <= COLD_START_GWS)
    absent = _mask(scored, "minutes_r5", lambda s: s <= 0.0)
    present = _mask(scored, "minutes_r5", lambda s: s > 0.0)
    return {
        "fringe": scored[fringe],
        "regular": scored[regular],
        "cold_start": scored[cold],
        "settled": scored[~cold],
        "recent_absence": scored[absent],
        "recent_presence": scored[present],
    }


def dnp_reliability(frame: pd.DataFrame,
                    bins: int = DNP_DECILES) -> list[dict]:
    """Predicted vs observed DNP rate per ``p_dnp`` decile.

    The DNP mode's own calibration curve, which the pooled ``p_play``
    reliability in :func:`gaffer.evaluation.head_metrics` cannot show: a head
    that is right on average and wrong in every bin is exactly the failure a
    recalibration fixes, and it is invisible in a single log loss.

    Empty deciles are omitted rather than emitted as zeros, matching
    :func:`gaffer.evaluation.reliability`.
    """
    if "p_dnp" not in frame.columns or "minutes" not in frame.columns:
        return []
    p = pd.to_numeric(frame["p_dnp"], errors="coerce").to_numpy(dtype=float)
    y = (pd.to_numeric(frame["minutes"], errors="coerce").fillna(0.0)
         .to_numpy(dtype=float) <= 0.0).astype(float)
    ok = np.isfinite(p)
    p, y = p[ok], y[ok]
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1], right=False), 0, bins - 1)
    out = []
    for b in range(bins):
        sel = idx == b
        n = int(sel.sum())
        if n == 0:
            continue
        out.append({"decile": b, "n": n,
                    "pred": round(float(p[sel].mean()), 4),
                    "obs": round(float(y[sel].mean()), 4)})
    return out


def _error(frame: pd.DataFrame) -> dict:
    """RMSE, MAE, mean EP and row count over the *zeros* rows of ``frame``.

    Zeros are defined on the outcome exactly as
    :func:`gaffer.evaluation.categorize` defines them (``total_points <= 0``),
    so a number here is comparable to the harness's own stratum without any
    translation. ``mean_ep`` is carried because over-forecasting is the whole
    hypothesis and RMSE alone cannot show its sign.
    """
    zeros = frame[pd.to_numeric(frame["total_points"],
                                errors="coerce").fillna(0.0) <= 0.0]
    n = int(len(zeros))
    if n == 0:
        return {"n": 0, "rmse": 0.0, "mae": 0.0, "mean_ep": 0.0}
    err = (pd.to_numeric(zeros["ep"], errors="coerce").fillna(0.0)
           - pd.to_numeric(zeros["total_points"], errors="coerce").fillna(0.0))
    return {"n": n,
            "rmse": round(float(np.sqrt((err ** 2).mean())), 4),
            "mae": round(float(err.abs().mean()), 4),
            "mean_ep": round(float(pd.to_numeric(zeros["ep"],
                                                 errors="coerce").mean()), 4)}


def zeros_report(scored: pd.DataFrame) -> dict:
    """The whole decomposition: overall, per stratum, plus the DNP curve."""
    strata = {name: _error(part) for name, part in stratify(scored).items()}
    strata["flagged"] = {"n": 0, "rmse": 0.0, "mae": 0.0, "mean_ep": 0.0,
                         "note": FLAGGED_NOTE}
    return {
        "overall": _error(scored),
        "strata": strata,
        "dnp_reliability": dnp_reliability(scored),
        "fringe_share": FRINGE_SHARE,
        "cold_start_gws": COLD_START_GWS,
    }


DIAGNOSTIC_PATH = REPORTS / "zeros_diagnostic.json"


def save_diagnostic(payload: dict) -> Path:
    """Write the report. ``reports/`` is gitignored — this never enters git."""
    REPORTS.mkdir(exist_ok=True)
    DIAGNOSTIC_PATH.write_text(json.dumps(payload, indent=1, allow_nan=False))
    return DIAGNOSTIC_PATH


def format_diagnostic(payload: dict) -> str:
    """The report as a table a human reads in a terminal."""
    o = payload["overall"]
    lines = [f"=== zeros diagnostic (run_at {payload.get('run_at')}, "
             f"sha {payload.get('git_sha')}) ===",
             f"overall  n {o['n']:6d}  rmse {o['rmse']:7.4f}  "
             f"mae {o['mae']:7.4f}  mean_ep {o['mean_ep']:7.4f}",
             "-- strata (zeros rows only)"]
    for name, m in payload["strata"].items():
        line = (f"   {name:17s} n {m['n']:6d}  rmse {m['rmse']:7.4f}  "
                f"mae {m['mae']:7.4f}  mean_ep {m['mean_ep']:7.4f}")
        if m.get("note"):
            line += f"  [{m['note']}]"
        lines.append(line)
    lines.append("-- p_dnp calibration (all rows)")
    for row in payload["dnp_reliability"]:
        lines.append(f"   decile {row['decile']}  pred {row['pred']:.4f}  "
                     f"obs {row['obs']:.4f}  n {row['n']}")
    return "\n".join(lines)
