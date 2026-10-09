"""v20c's head half: does the Dixon-Coles clip cost calibration?

v20 spec §2 v20c "Head half". The folds are ``walk_forward_cs``'s
(half-season folds, Dixon-Coles fitted on every match strictly before the
fold, the fold predicted), re-implemented here because that function needs
an odds file and yields only ``p_cs_model`` (holiday F-13). Each fold is
fitted once and predicted twice, with ``dixon_coles.MU_BOUNDS`` off and at
the spec's ``(0.2, 3.5)``: the fit never reads the bound, only ``predict``
does, so one fit serves both sides. The module value is restored afterwards
whatever happens.

Scored on both sides: log-loss and Brier of ``p_cs`` against realised clean
sheets and MAE of ``e_gc`` against realised goals against, over all fixtures
and over the extreme subset, the fixtures whose *unclipped* ``p_cs`` lies
outside v19g's band (0.02, 0.85) or whose ``e_gc`` lies outside (0.15, 4.0)
(``tests/test_v19_degradation.py``'s ``P_CS_BAND``/``E_GC_BAND``).

The pass rule, pre-registered in the spec: overall log-loss not worse by more
than 0.001, the extreme subset's log-loss improved, and overall ``e_gc`` MAE
not worse. An empty extreme subset is no reading, not a pass: the clip had
nothing to bite on.

Read-only. It writes nothing and turns nothing on; a missing or unreadable
fixture history prints the line with ``n=0`` and a reason, never a
traceback, because the night shift transcribes the line into the spec's §6
whatever it says. With the clip on, ``predict`` prints its own
``DC_CLIP n=… of …`` lever line once per fold before that; the
``V20C_HEAD`` line, last, is the one to transcribe.

    uv run python scripts/v20c_head.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from gaffer.data import store
from gaffer.models import dixon_coles
from gaffer.models.dixon_coles import BLEND_FOLDS_PER_SEASON, DixonColesModel
from gaffer.models.team import build_team_gw

CLIP = (0.2, 3.5)
"""The spec's bound when the arm turns the clip on (v20 spec §2 v20c)."""

P_CS_BAND = (0.02, 0.85)
E_GC_BAND = (0.15, 4.0)
"""v19g's band, copied from ``tests/test_v19_degradation.py``; a script does
not import a test module."""

LOGLOSS_SLACK = 0.001
EPS = 1e-15

HISTORY_PATH = "history/fixtures.parquet"
LIVE_PATH = "live/fixtures.parquet"


def _empty(reason: str) -> dict:
    return {"n": 0, "n_extreme": 0, "clip_bit": 0, "folds": 0,
            "off": None, "on": None, "verdict": "no reading",
            "reason": reason}


def _scores(p_cs: np.ndarray, e_gc: np.ndarray, cs: np.ndarray,
            ga: np.ndarray) -> dict:
    if len(cs) == 0:
        return {"logloss": None, "brier": None, "mae_egc": None}
    p = np.clip(p_cs, EPS, 1.0 - EPS)
    logloss = -float(np.mean(cs * np.log(p) + (1.0 - cs) * np.log(1.0 - p)))
    return {"logloss": logloss,
            "brier": float(np.mean((p_cs - cs) ** 2)),
            "mae_egc": float(np.mean(np.abs(e_gc - ga)))}


def _rounded(side: dict) -> dict:
    """Six places for the printed line only; the verdict reads the raw
    floats, so a real but small move is never rounded into a tie."""
    return {subset: {k: (None if v is None else round(v, 6))
                     for k, v in scores.items()}
            for subset, scores in side.items()}


def fold_predictions(tg: pd.DataFrame, xi: float = dixon_coles.DEFAULT_XI
                     ) -> pd.DataFrame:
    """Every played team-fixture of every fold after the first, predicted
    with the clip off and on: ``[cs, ga, p_cs_off, e_gc_off, p_cs_on,
    e_gc_on, _fold]``."""
    played = tg.dropna(subset=["ga"]).copy()
    played["_fold"] = (played["season_idx"].astype(int)
                       * BLEND_FOLDS_PER_SEASON
                       + (played["gw"].astype(int) > 19).astype(int))
    folds = sorted(played["_fold"].unique())
    saved = dixon_coles.MU_BOUNDS
    out = []
    try:
        for fold in folds[1:]:
            before = played[played["_fold"] < fold]
            current = played[played["_fold"] == fold]
            if before.empty or current.empty:
                continue
            model = DixonColesModel(xi=xi).fit(before)
            dixon_coles.MU_BOUNDS = None
            off = model.predict(current)
            dixon_coles.MU_BOUNDS = CLIP
            on = model.predict(current)
            block = pd.DataFrame({
                "cs": pd.to_numeric(current["cs"], errors="coerce")
                .to_numpy(dtype="float64"),
                "ga": pd.to_numeric(current["ga"], errors="coerce")
                .to_numpy(dtype="float64"),
                "p_cs_off": off["p_cs"].to_numpy(),
                "e_gc_off": off["e_gc"].to_numpy(),
                "p_cs_on": on["p_cs"].to_numpy(),
                "e_gc_on": on["e_gc"].to_numpy(),
                "_fold": fold})
            out.append(block)
    finally:
        dixon_coles.MU_BOUNDS = saved
    if not out:
        return pd.DataFrame(columns=["cs", "ga", "p_cs_off", "e_gc_off",
                                     "p_cs_on", "e_gc_on", "_fold"])
    return pd.concat(out, ignore_index=True)


def head_reading(tg: pd.DataFrame | None) -> dict:
    """The ``V20C_HEAD`` payload over a team-gameweek frame."""
    if tg is None or tg.empty:
        return _empty("fixture history is empty")
    frame = fold_predictions(tg).dropna(subset=["cs", "ga"])
    if frame.empty:
        return _empty("no fold with matches on both sides")

    cs, ga = frame["cs"].to_numpy(), frame["ga"].to_numpy()
    p_off, e_off = frame["p_cs_off"].to_numpy(), frame["e_gc_off"].to_numpy()
    p_on, e_on = frame["p_cs_on"].to_numpy(), frame["e_gc_on"].to_numpy()
    extreme = ((p_off < P_CS_BAND[0]) | (p_off > P_CS_BAND[1])
               | (e_off < E_GC_BAND[0]) | (e_off > E_GC_BAND[1]))
    bit = (p_off != p_on) | (e_off != e_on)

    off = {"all": _scores(p_off, e_off, cs, ga),
           "extreme": _scores(p_off[extreme], e_off[extreme],
                              cs[extreme], ga[extreme])}
    on = {"all": _scores(p_on, e_on, cs, ga),
          "extreme": _scores(p_on[extreme], e_on[extreme],
                             cs[extreme], ga[extreme])}
    n_extreme = int(extreme.sum())
    reason = None
    if n_extreme == 0:
        verdict = "no reading"
        reason = "no fixture outside the band, the clip bit nothing"
    else:
        rows = {
            "overall_logloss": (on["all"]["logloss"]
                                <= off["all"]["logloss"] + LOGLOSS_SLACK),
            "extreme_logloss": (on["extreme"]["logloss"]
                                < off["extreme"]["logloss"]),
            "overall_mae_egc": on["all"]["mae_egc"] <= off["all"]["mae_egc"],
        }
        failed = [k for k, ok in rows.items() if not ok]
        verdict = "pass" if not failed else "fail: " + ", ".join(failed)
    return {"n": int(len(frame)), "n_extreme": n_extreme,
            "clip_bit": int(bit.sum()),
            "folds": int(frame["_fold"].nunique()),
            "off": _rounded(off), "on": _rounded(on), "verdict": verdict,
            "reason": reason}


def load_team_gw() -> pd.DataFrame | None:
    """The banked fixtures (history plus the live season), one row per team
    per match; ``None`` when no history is on disk."""
    if not store.exists(HISTORY_PATH):
        return None
    fixtures = store.load(HISTORY_PATH)
    if store.exists(LIVE_PATH):
        fixtures = pd.concat([fixtures, store.load(LIVE_PATH)],
                             ignore_index=True)
    return build_team_gw(fixtures)


def main() -> int:
    try:
        tg = load_team_gw()
        payload = (_empty(f"no fixture history at "
                          f"{store.DATA_DIR / HISTORY_PATH}")
                   if tg is None else head_reading(tg))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        # A corrupt parquet raises ArrowInvalid (a ValueError); a frame
        # missing a column raises KeyError; a malformed kickoff_time raises
        # ValueError in the fit's to_datetime.
        payload = _empty(f"fixture history unreadable: {type(exc).__name__}")
    print(f"V20C_HEAD {json.dumps(payload, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
