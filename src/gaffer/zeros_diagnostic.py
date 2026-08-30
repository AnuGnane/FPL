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


def start_reliability(frame: pd.DataFrame,
                      bins: int = DNP_DECILES) -> list[dict]:
    """Predicted vs observed start rate per ``p_start`` decile.

    :func:`dnp_reliability`'s twin at the other end of the trichotomy, and the
    cut v8a's F1/F2 arms are actually about: a rotation feature earns its
    column by moving *which* players the model expects to start, and a pooled
    ``p_play`` curve averages that away. Read per stratum, it says whether an
    arm helped the fringe, the regulars or nobody.

    ``starts`` where the feed has it, ``minutes >= 60`` where it does not —
    the same inference :func:`gaffer.evaluation.start_truth` makes. Empty
    deciles are omitted, matching every other reliability curve here.
    """
    if "p_start" not in frame.columns or "minutes" not in frame.columns:
        return []
    from gaffer.evaluation import start_truth

    p = pd.to_numeric(frame["p_start"], errors="coerce").to_numpy(dtype=float)
    y = start_truth(frame).to_numpy(dtype=float)
    ok = np.isfinite(p) & np.isfinite(y)
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
    """The whole decomposition: overall, per stratum, plus the two curves."""
    parts = stratify(scored)
    strata = {name: _error(part) for name, part in parts.items()}
    strata["flagged"] = {"n": 0, "rmse": 0.0, "mae": 0.0, "mean_ep": 0.0,
                         "note": FLAGGED_NOTE}
    return {
        "overall": _error(scored),
        "strata": strata,
        "dnp_reliability": dnp_reliability(scored),
        # v8a F3: the same six sub-populations, read at the start mode. A
        # stratum whose zeros RMSE moved and whose start curve did not is an
        # arm that helped somewhere other than where it claimed to.
        "start_reliability": {name: start_reliability(part)
                              for name, part in parts.items()},
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
    lines.append("-- p_start calibration (per stratum, all rows)")
    for name, curve in payload.get("start_reliability", {}).items():
        if not curve:
            continue
        lines.append(f"   {name}")
        for row in curve:
            lines.append(f"     decile {row['decile']}  "
                         f"pred {row['pred']:.4f}  obs {row['obs']:.4f}  "
                         f"n {row['n']}")
    return "\n".join(lines)


def _holdout(holdout_slots: int = 10) -> pd.DataFrame:
    """The evaluation harness's own holdout rows, scored, with the strata
    features and ``p_dnp`` carried along.

    Deliberately a re-walk of :func:`gaffer.evaluation.evaluate_current`'s
    steps rather than a call into it: the harness returns metrics, and what is
    wanted here is the row-level frame those metrics were computed from, with
    the mode probabilities and the rotation features still attached.
    """
    from gaffer.assets import load_bootstrap_sample
    from gaffer.data.bootstrap import scoring_table
    from gaffer.evaluation import HOLDOUT_SLOTS, before_mask, holdout_boundary
    from gaffer.models.assemble import (apply_calibration, assemble_ep,
                                        ep_matrix)
    from gaffer.models.train import (load_training_frame,
                                     predict_components_simple, train_all)

    holdout_slots = holdout_slots or HOLDOUT_SLOTS
    df, tg, _ = load_training_frame()
    bs, bg = holdout_boundary(df, holdout_slots)
    before, tg_before = before_mask(df, bs, bg), before_mask(tg, bs, bg)
    models = train_all(df[before], tg[tg_before].dropna(subset=["elo_diff"]),
                       save=False)

    hold = df[~before].reset_index(drop=True)
    comp = predict_components_simple(models, hold)
    ep = ep_matrix(apply_calibration(
        assemble_ep(comp, scoring_table(load_bootstrap_sample())),
        models.get("calibration")))
    truth = hold.groupby(["code", "gw"], as_index=False).agg(
        total_points=("total_points", "sum"), minutes=("minutes", "sum"))
    # One row per player-fixture becomes one row per player-gameweek, so the
    # strata features are taken from the first fixture of the week: they are
    # player-and-week facts, identical across a double gameweek's two rows.
    modes = models["minutes"].predict_modes(hold)
    carry = hold[["code", "gw"]].copy()
    for col in ("season_start_share", "minutes_r5", "starts"):
        if col in hold.columns:
            carry[col] = pd.to_numeric(hold[col], errors="coerce")
    carry["p_dnp"] = modes["p_dnp"].values
    carry["p_start"] = modes["p_start"].values
    carry = carry.groupby(["code", "gw"], as_index=False).first()
    return ep.merge(truth, on=["code", "gw"], how="inner").merge(
        carry, on=["code", "gw"], how="left")


def run_diagnostic(holdout_slots: int = 10) -> dict:
    """Score the holdout, decompose it, print it, save it."""
    from gaffer.evaluation import git_sha, run_at

    payload = zeros_report(_holdout(holdout_slots))
    payload["run_at"] = run_at()
    payload["git_sha"] = git_sha()
    payload["holdout_slots"] = int(holdout_slots)
    print(format_diagnostic(payload), flush=True)
    save_diagnostic(payload)
    return payload
