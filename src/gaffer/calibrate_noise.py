"""Offline calibration of the scenario sweep's noise scale (spec §2).

``optimize/scenarios.noise_ep`` shipped with ``ep * (92 - xmins) / 134`` —
a community-standard formula that was never fitted to anything. It has the
right *shape* (almost all of FPL's forecast error is "did he play", not "how
well did he play") and an unknown *scale*, and the scale is what decides
whether a transfer surviving 32 of 40 noised worlds means anything.

So it is measured. On the walk-forward benchmark's own predictions — the same
train-on-2022-24, predict-every-week-of-2024-25 protocol ``evaluate --mode
benchmark`` runs — residuals ``points - ep`` are binned by predicted EP and by
expected minutes, and a standard deviation is fitted per cell. Cells too thin
to fit pool up to their EP bin's marginal, and that to the global residual σ.

The result ships as ``assets/scenario_noise.json``, in git, so a fresh clone
noises sensibly without ever running this. Absent, ``noise_ep`` uses the
heuristic and nothing else changes.

Like :mod:`gaffer.calibrate_decisions`, this module is deliberately isolated
from the advise path: nothing in ``advise.py`` imports it and it does no work
at import time.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

ASSET_PATH = Path("src/gaffer/assets/scenario_noise.json")

EP_EDGES = [0.0, 2.0, 3.0, 4.0, 6.0]
"""Left edges of the predicted-EP bins.

Five bins: the great mass of bench fodder under 2, then a bin per point up to
6, then everything above. Finer at the top because that is where the squad
decisions actually are, and where a mis-stated σ costs a captaincy.
"""

XMINS_EDGES = [0.0, 30.0, 60.0, 80.0]
"""Left edges of the expected-minutes bins.

60 is the threshold the game itself cares about (the appearance step) and 80
is where "nailed" starts. The top edge is set by what the binned quantity can
actually reach: :func:`bin_index` returns the largest ``i`` with
``value >= edges[i]``, and ``xmins_by_player_gw`` computes
``p_play * (45 + 45 * p60)``, whose live ceiling is about 84.8 — clearing 85
would need ``p60`` around 0.91 at ``p_play`` of 1. So every edge above ~85 was
unreachable, and the last bin of the grid was fitted on nothing while every
nailed-on starter crowded into the bin below it. At 80 the top bin is the
populated "nailed" one: 12.6% of the live board, 2682 observations of the fit
frame.
"""

MIN_CELL_OBS = 100
"""Observations a cell needs before its σ is trusted.

Below this the cell is *recorded* in ``obs`` — the count is evidence about
where the data is thin — but left out of ``sigma``, so serving falls through
to the EP bin's marginal.
"""

SIGMA_MAX = 10.0
"""Refusal bound, matching ``optimize.scenarios.SIGMA_MAX``."""

REQUIRED_KEYS = ("version", "generated_at", "season", "ep_edges",
                 "xmins_edges", "sigma", "obs", "ep_marginal", "global")


def bin_index(value: float, edges: list[float]) -> int:
    """Which half-open bin ``value`` falls in. See
    :func:`gaffer.optimize.scenarios.bin_index` — the same rule, restated
    here so the fitting side does not import the serving side."""
    idx = 0
    for i, edge in enumerate(edges):
        if float(value) >= float(edge):
            idx = i
    return idx


def residual_rows(max_train_idx: int | None = None,
                  test_idx: int | None = None) -> pd.DataFrame:
    """``[code, gw, ep, xmins, points]`` over the benchmark's test season.

    Deliberately the *benchmark* protocol and not a fresh one: it is already
    the codebase's honest out-of-sample walk (a hard season split, features
    leakage-safe within the season, one gameweek at a time), and a second
    walk-forward here would be a second thing to keep in step with it.

    ``xmins`` comes from :func:`gaffer.optimize.scenarios.xmins_by_player_gw`
    — the same function the live sweep bins on, so a cell fitted here is the
    cell that will be read there.
    """
    from gaffer.assets import load_bootstrap_sample
    from gaffer.data.bootstrap import scoring_table
    from gaffer.errors import GafferError
    from gaffer.evaluation import (BENCHMARK_TEST_IDX,
                                   BENCHMARK_TRAIN_MAX_IDX,
                                   benchmark_scoring, benchmark_split)
    from gaffer.models.assemble import (apply_calibration, assemble_ep,
                                        ep_matrix)
    from gaffer.models.train import (load_training_frame,
                                     predict_components_simple, train_all)
    from gaffer.optimize.scenarios import xmins_by_player_gw

    max_train_idx = (BENCHMARK_TRAIN_MAX_IDX if max_train_idx is None
                     else max_train_idx)
    test_idx = BENCHMARK_TEST_IDX if test_idx is None else test_idx

    df, tg, _ = load_training_frame()
    train_df, test_df = benchmark_split(df, max_train_idx, test_idx)
    train_tg, _ = benchmark_split(tg, max_train_idx, test_idx)
    models = train_all(train_df, train_tg.dropna(subset=["elo_diff"]),
                       save=False)
    # The bundled scoring table is the current season's; the test season is
    # not — the same restatement evaluate_benchmark makes, and for the same
    # reason: a residual measured against points the season never awarded is
    # not a residual.
    scoring = benchmark_scoring(scoring_table(load_bootstrap_sample()))

    parts = []
    for gw in sorted(int(g) for g in test_df["gw"].dropna().unique()):
        rows = test_df[test_df["gw"] == gw].reset_index(drop=True)
        if rows.empty:
            continue
        comp = predict_components_simple(models, rows)
        ep = ep_matrix(apply_calibration(assemble_ep(comp, scoring),
                                         models.get("calibration")))
        xm = xmins_by_player_gw(comp)
        truth = rows.groupby(["code", "gw"], as_index=False).agg(
            points=("total_points", "sum"))
        joined = ep.merge(truth, on=["code", "gw"], how="inner")
        joined["xmins"] = [float(xm.get((int(c), int(g)), float("nan")))
                           for c, g in zip(joined["code"], joined["gw"])]
        parts.append(joined[["code", "gw", "ep", "xmins", "points"]])
        print(f"noise gw{gw}: {len(parts[-1])} rows", flush=True)

    if not parts:
        raise GafferError(
            "no benchmark rows to calibrate scenario noise on — run "
            "`gaffer build-history` and `gaffer train` first")
    return pd.concat(parts, ignore_index=True)


def fit_sigmas(rows: pd.DataFrame, ep_edges: list[float] | None = None,
               xmins_edges: list[float] | None = None,
               min_obs: int = MIN_CELL_OBS) -> dict:
    """Residuals -> the σ table, its observation counts and its fallbacks.

    ``ddof=0``: this is the standard deviation of the residuals that were
    actually observed, not an estimate of a parameter of some population they
    were drawn from, and at the cell sizes involved the difference is in the
    fourth decimal anyway.

    Rows with no ``xmins`` are dropped rather than binned at zero. A player
    the minutes model said nothing about is not a player expected to play no
    minutes, and folding him into the 0-30 cell would hand the sweep a σ built
    from a different question.
    """
    ep_edges = EP_EDGES if ep_edges is None else list(ep_edges)
    xmins_edges = XMINS_EDGES if xmins_edges is None else list(xmins_edges)
    frame = rows.dropna(subset=["ep", "xmins", "points"]).copy()
    frame["resid"] = (frame["points"].astype(float)
                      - frame["ep"].astype(float))
    frame["ep_bin"] = [bin_index(v, ep_edges) for v in frame["ep"]]
    frame["x_bin"] = [bin_index(v, xmins_edges) for v in frame["xmins"]]

    marginal: dict[str, float] = {}
    marginal_obs: dict[str, int] = {}
    for i, part in frame.groupby("ep_bin"):
        marginal[str(int(i))] = round(float(part["resid"].std(ddof=0)), 4)
        marginal_obs[str(int(i))] = int(len(part))

    sigma: dict[str, float] = {}
    obs: dict[str, int] = {}
    for (i, j), part in frame.groupby(["ep_bin", "x_bin"]):
        key = f"{int(i)}_{int(j)}"
        obs[key] = int(len(part))
        if len(part) >= int(min_obs):
            sigma[key] = round(float(part["resid"].std(ddof=0)), 4)

    return {
        "ep_edges": ep_edges,
        "xmins_edges": xmins_edges,
        "sigma": sigma,
        "obs": obs,
        "ep_marginal": marginal,
        "ep_marginal_obs": marginal_obs,
        "global": round(float(frame["resid"].std(ddof=0)), 4),
        "rows": int(len(frame)),
        "min_cell_obs": int(min_obs),
    }


def run_calibration(max_train_idx: int | None = None,
                    test_idx: int | None = None) -> dict:
    """Replay the benchmark season and assemble the asset payload."""
    from gaffer.evaluation import BENCHMARK_TEST_SEASON, git_sha, run_at

    rows = residual_rows(max_train_idx, test_idx)
    payload = fit_sigmas(rows)
    payload.update({
        "version": 1,
        "generated_at": run_at(),
        "git_sha": git_sha(),
        "season": BENCHMARK_TEST_SEASON,
    })
    return payload


def write_noise(payload: dict, path: Path | str = ASSET_PATH) -> Path:
    """Validate and write the asset.

    Validated before writing because a hollow σ table is worse than none at
    all: an absent asset degrades honestly to the heuristic, while a table of
    zeroes tells the sweep every forecast is certain and hands the MILP forty
    identical boards — forty scenarios agreeing 100% of the time about a
    transfer nobody tested.
    """
    missing = [k for k in REQUIRED_KEYS if k not in payload]
    if missing:
        raise ValueError(
            f"scenario noise payload is missing {missing[0]} (of {missing}) "
            "— refusing to write a partial asset")
    sigmas = dict(payload.get("sigma") or {})
    sigmas.update({f"marginal_{k}": v
                   for k, v in (payload.get("ep_marginal") or {}).items()})
    if not sigmas:
        raise ValueError(
            "scenario noise payload carries no fitted sigmas — every cell "
            "would fall through to the heuristic anyway")
    if payload.get("global") is not None:
        sigmas["global"] = payload["global"]
    for key, value in sigmas.items():
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"sigma {key} is not finite ({value})")
        if number <= 0.0:
            raise ValueError(f"sigma {key} is not positive ({value})")
        if number >= SIGMA_MAX:
            raise ValueError(
                f"sigma {key} is not below {SIGMA_MAX} ({value}) — a residual "
                "standard deviation that large is a broken fit, not a "
                "volatile player")
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return dest
