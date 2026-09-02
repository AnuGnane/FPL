"""The standing evaluation harness: how good is the model, on what yardstick.

Three things live here that nothing else in the codebase had. First, metrics
*stratified by what actually happened* — a single MAE is dominated by the
players who scored nothing, which every model gets right, so it flatters
everything equally and can never tell two models apart where it matters.
Second, calibration-first scoring of the probability heads: a p60 that is
right on average and wrong in every bin is worse than useless to a MILP that
multiplies by it. Third, one persistent artifact (``reports/evaluation.json``)
so a number from three weeks ago is still there to regress against.

Everything expensive is imported inside the function that needs it: the web
layer imports this module just to read the artifact and must not pay for
LightGBM to do it.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from gaffer.artifacts import REPORTS
from gaffer.config import load_config
from gaffer.errors import GafferError
from gaffer.io import atomic_write

RETURN_CATEGORIES = ["zeros", "blanks", "tickers", "haulers", "all"]
"""OpenFPL's return buckets, defined on *actual* points, plus the pooled cut.

Zeros (0), Blanks (1-2), Tickers (3-4), Haulers (5+). Keeping the exact
boundaries is what makes the published numbers in :data:`REFERENCES`
comparable at all.
"""


def categorize(points) -> np.ndarray:
    """Return bucket per row, from actual points."""
    a = np.asarray(points, dtype="float64")
    out = np.full(a.shape, "haulers", dtype=object)
    out[a <= 0] = "zeros"
    out[(a >= 1) & (a <= 2)] = "blanks"
    out[(a >= 3) & (a <= 4)] = "tickers"
    return out


def _paired(pred, actual) -> tuple[np.ndarray, np.ndarray]:
    """Prediction/outcome arrays with the non-finite rows dropped.

    Positional, not index-aligned: every ``predict`` in this codebase returns
    one row per input row in input order, and pandas would happily align two
    frames with different indexes into nonsense.
    """
    p = np.asarray(pred, dtype="float64")
    y = np.asarray(actual, dtype="float64")
    ok = np.isfinite(p) & np.isfinite(y)
    return p[ok], y[ok]


def stratified_metrics(pred, actual) -> dict[str, dict[str, float]]:
    """RMSE and MAE per return category plus ``all``, with row counts.

    An empty category reports zeros rather than NaN: the artifact is JSON and
    a NaN there is neither valid JSON nor readable in the UI. ``n`` is the
    field that says whether the numbers mean anything.

    Non-finite pairs are dropped for the same reason: a single NaN ``ep`` —
    one player missing a component — would otherwise turn its whole category's
    RMSE and MAE into NaN and take the artifact down with it. Dropping is
    honest here because ``n`` reports how many rows survived.
    """
    p, a = _paired(pred, actual)
    cats = categorize(a)
    out: dict[str, dict[str, float]] = {}
    for name in RETURN_CATEGORIES:
        sel = np.ones(a.shape, dtype=bool) if name == "all" else cats == name
        n = int(sel.sum())
        err = p[sel] - a[sel]
        out[name] = {
            "rmse": round(float(np.sqrt((err ** 2).mean())), 3) if n else 0.0,
            "mae": round(float(np.abs(err).mean()), 3) if n else 0.0,
            "n": n,
        }
    return out


RELIABILITY_BINS = 10
LOG_LOSS_EPS = 1e-15
"""Clip for the log: a head that returns a hard 0 or 1 must not make the
whole metric infinite on a single wrong row."""


def log_loss(pred, actual) -> float:
    """Mean binary cross-entropy. NaN on an empty input, never an exception."""
    p, y = _paired(pred, actual)
    if p.size == 0:
        return float("nan")
    p = np.clip(p, LOG_LOSS_EPS, 1.0 - LOG_LOSS_EPS)
    return float(-(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)).mean())


def reliability(pred, actual, bins: int = RELIABILITY_BINS) -> list[dict]:
    """Reliability curve: per equal-width probability bin, ``n``, the mean
    prediction and the observed frequency.

    A head is calibrated when ``pred`` and ``obs`` match bin by bin, which is
    what the optimizer actually depends on — it multiplies by these numbers.
    Empty bins are omitted rather than emitted as zeros, so the curve never
    dives to the origin for a head whose predictions all sit in one place.
    """
    p, y = _paired(pred, actual)
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1], right=False), 0, bins - 1)
    out = []
    for b in range(bins):
        sel = idx == b
        n = int(sel.sum())
        if n == 0:
            continue
        out.append({"n": n, "pred": round(float(p[sel].mean()), 4),
                    "obs": round(float(y[sel].mean()), 4)})
    return out


def brier(pred, actual) -> float:
    """Mean squared error on a probability. NaN on empty, never an exception.

    Log loss and Brier disagree about what a confident mistake is worth — log
    loss is unbounded, Brier is not — and the optimizer multiplies by these
    probabilities rather than by their logs. Both are reported so a head that
    is sharp and a head that is calibrated can be told apart.
    """
    p, y = _paired(pred, actual)
    if p.size == 0:
        return float("nan")
    return float(((p - y) ** 2).mean())


MIN_CALIBRATION_SAMPLES = 30
"""Below this a head reports ``insufficient`` instead of a curve.

Ten reliability bins over twenty rows is a picture of the sampling noise, and
a trend line drawn through pictures of noise is worse than no trend line: it
is a number people act on. Thirty is the smallest count at which the bins say
anything at all, and the payload says which side of it each head fell.
"""


def calibration_head(pred, actual) -> dict:
    """One head's calibration, in a shape that is the same either way.

    ``status`` carries the "not enough data" case rather than a missing key,
    so nothing downstream — pydantic, the card, a later script — has to branch
    on whether ``brier`` exists.
    """
    p, y = _paired(pred, actual)
    n = int(p.size)
    if n < MIN_CALIBRATION_SAMPLES:
        return {"status": "insufficient", "n": n, "brier": None,
                "log_loss": None, "reliability": []}
    b, ll = brier(p, y), log_loss(p, y)
    return {"status": "scored", "n": n,
            "brier": None if np.isnan(b) else round(b, 4),
            "log_loss": None if np.isnan(ll) else round(ll, 4),
            "reliability": reliability(p, y)}


def head_metrics(pred, actual) -> dict:
    """One probability head's scoreline: log loss plus its reliability curve.

    A head with nothing to score reports ``log_loss: None`` rather than NaN:
    ``None`` is JSON's null and survives the round trip to the UI, where NaN
    is not JSON at all.
    """
    ll = log_loss(pred, actual)
    return {"log_loss": None if np.isnan(ll) else round(ll, 4),
            "reliability": reliability(pred, actual)}


EVALUATION_PATH = REPORTS / "evaluation.json"
"""One artifact, three independent keys.

``current`` and ``benchmark`` are different protocols and ``decomposition``
is a pair of replays that takes hours; each is written on its own and none of
them may take the others down with it, so writes merge rather than replace.
"""


def run_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_sha() -> str:
    """Short HEAD sha, or ``"unknown"``.

    Which commit produced a number is half of what makes it comparable to the
    next one, and a missing git is never a reason to fail an evaluation.
    """
    try:
        done = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return done.stdout.strip() if done.returncode == 0 else "unknown"


def _reject_constant(name: str) -> None:
    """Refuse the bare ``NaN``/``Infinity`` literals Python's json accepts.

    They are not JSON, nothing else can read them back, and any artifact
    carrying one was written before the encoder learned to refuse them — so
    it is exactly the corrupt-artifact case, handled where that already is.
    """
    raise ValueError(f"{name} is not valid JSON")


def _read_artifact() -> dict:
    """The artifact's JSON, with a decode error stated in domain terms.

    Both callers read the same file and both are reached from the web layer,
    where an escaping ``ValueError`` is a bare 500 that says nothing about
    what to do next.
    """
    try:
        return json.loads(EVALUATION_PATH.read_text(),
                          parse_constant=_reject_constant)
    except ValueError as exc:
        raise GafferError(
            f"{EVALUATION_PATH} is not readable JSON — it may be corrupt or "
            f"mid-write; re-run `gaffer evaluate` to rebuild it ({exc})"
        ) from exc


def load_evaluation() -> dict:
    """The whole artifact. Missing or corrupt file is a domain error."""
    if not EVALUATION_PATH.exists():
        raise GafferError(
            "no evaluation on disk — run `gaffer evaluate` first")
    return _read_artifact()


def save_evaluation(key: str, payload: dict) -> Path:
    """Merge ``payload`` in under ``key``, leaving the other keys alone.

    Written atomically: a reader either sees the whole previous artifact or
    the whole new one, never the half-written middle. Evaluation runs take
    hours and the web layer reads this file on every request, so the two do
    overlap.
    """
    stored: dict = {}
    if EVALUATION_PATH.exists():
        stored = _read_artifact()
    stored[key] = payload
    # allow_nan=False: NaN/Infinity are a Python extension that no other JSON
    # reader accepts. Letting one through here buys a valid-looking artifact
    # that only fails weeks later, as a 500 from /api/quality, a long way from
    # whatever produced the NaN. Serialised before the temp file is opened, so
    # a rejected payload leaves nothing behind at all.
    text = json.dumps(stored, indent=1, allow_nan=False)
    REPORTS.mkdir(exist_ok=True)
    atomic_write(EVALUATION_PATH, text)
    return EVALUATION_PATH


HOLDOUT_SLOTS = 10
"""Gameweek slots held out in current mode.

The same ten as :data:`gaffer.models.train.CALIBRATION_HOLDOUT_GWS`, and for
the same reason: long enough to say something, short enough that the inner
model still sees nearly all of the newest season. Splitting on slots rather
than seasons also keeps components whose stats only exist in the newest
season (``tackles``/``cbi``) from losing every eligible training row.
"""

STARTER_MINUTES = 60
"""What counts as a start, matching ``evaluate_predictions``."""


def before_mask(frame: pd.DataFrame, season_idx: int, gw: int) -> pd.Series:
    """Rows strictly before the ``(season_idx, gw)`` slot."""
    return ((frame["season_idx"] < season_idx)
            | ((frame["season_idx"] == season_idx) & (frame["gw"] < gw)))


def holdout_boundary(df: pd.DataFrame,
                     holdout_slots: int = HOLDOUT_SLOTS) -> tuple[int, int]:
    """First held-out ``(season_idx, gw)`` slot, counting from the end."""
    slots = (df[["season_idx", "gw"]].drop_duplicates()
             .sort_values(["season_idx", "gw"]))
    if len(slots) <= holdout_slots:
        raise GafferError(
            f"only {len(slots)} gameweek slots in the frame — need more than "
            f"{holdout_slots} to hold one out")
    row = slots.iloc[-holdout_slots]
    return int(row["season_idx"]), int(row["gw"])


def baseline_metrics(hold: pd.DataFrame, col: str,
                     truth: pd.DataFrame) -> dict[str, dict[str, float]]:
    """A naive predictor scored on exactly the model's yardstick.

    ``col`` is a leakage-safe rolling column: ``total_points_r5`` is the
    last-five-match mean and ``total_points_r38`` is the mean of the player's
    last 38 *matches*, which rolls straight across season boundaries and so is
    not a season-to-date average — early in a season most of its window is
    last season's form. Between them they bracket the two horizons a human
    would eyeball. A double
    gameweek's two rows carry a near-identical rolling average, so taking the
    first is right where the truth frame has already summed the fixtures.
    """
    b = (hold[["code", "gw", col]].rename(columns={col: "ep"}).dropna()
         .groupby(["code", "gw"], as_index=False).agg(ep=("ep", "first")))
    j = b.merge(truth, on=["code", "gw"], how="inner")
    return stratified_metrics(j["ep"], j["total_points"])


def start_truth(hold: pd.DataFrame) -> pd.Series:
    """Did he start, as a 0/1 float, one value per row.

    ``starts`` where the feed recorded it, and ``minutes >= 60`` where it did
    not — the same inference :func:`gaffer.features.engineer._mode_rate_parts`
    makes for the shrunken start rate, and for the same reason: the column
    postdates part of the archive, and a hole would blank the metric for a
    whole season rather than for the rows that are actually unknown.
    """
    # ``get`` with a default rather than a bare one: a holdout frame without
    # ``minutes`` would hand ``to_numeric`` a None and raise, and a metric is
    # not worth an exception. The default carries ``hold``'s index so the
    # fallback stays row-aligned rather than collapsing to nothing.
    blank = pd.Series(float("nan"), index=hold.index, dtype="float64")
    mins = pd.to_numeric(hold.get("minutes", blank),
                         errors="coerce").fillna(0.0)
    inferred = (mins >= STARTER_MINUTES).astype("float64")
    if "starts" not in hold.columns:
        return inferred
    return (pd.to_numeric(hold["starts"], errors="coerce").fillna(inferred)
            .astype("float64"))


def evaluate_current(holdout_slots: int = HOLDOUT_SLOTS) -> dict:
    """Score the model on the last ``holdout_slots`` gameweek slots.

    Components are refit on everything strictly before the boundary and the
    held-out slots are predicted through the same assemble/calibrate seam the
    weekly advice uses, so what is measured here is what a live run would
    have produced. The probability heads are read straight off the models
    rather than off the assembled points: ``p_cs`` in the simple component
    path is a constant, so the clean-sheet head has to be scored against the
    team model's own output on the held-out team-gameweeks.
    """
    from gaffer.assets import load_bootstrap_sample
    from gaffer.data.bootstrap import scoring_table
    from gaffer.models.assemble import apply_calibration, assemble_ep, ep_matrix
    from gaffer.models.team import odds_blend_weight
    from gaffer.models.train import (load_training_frame,
                                     predict_components_simple, train_all)

    df, tg, _ = load_training_frame()
    bs, bg = holdout_boundary(df, holdout_slots)
    df_before, tg_before = before_mask(df, bs, bg), before_mask(tg, bs, bg)
    models = train_all(df[df_before],
                       tg[tg_before].dropna(subset=["elo_diff"]), save=False)

    hold = df[~df_before].reset_index(drop=True)
    scoring = scoring_table(load_bootstrap_sample())
    comp = predict_components_simple(models, hold)
    ep = ep_matrix(apply_calibration(assemble_ep(comp, scoring),
                                     models.get("calibration")))
    truth = hold.groupby(["code", "gw"], as_index=False).agg(
        total_points=("total_points", "sum"), minutes=("minutes", "sum"))
    scored = ep.merge(truth, on=["code", "gw"], how="inner")
    starters = scored[scored["minutes"] >= STARTER_MINUTES]

    mp = models["minutes"].predict(hold)
    # The trichotomy itself, not another function of it: p_play is a sum of
    # two modes, and an arm that sharpens the start/cameo split while leaving
    # the sum alone is invisible in p_play's log loss (v8a spec §3).
    modes = models["minutes"].predict_modes(hold)
    hold_tg = tg[~tg_before].dropna(subset=["elo_diff"]).reset_index(drop=True)
    tp = models["team"].predict(hold_tg)
    return {
        "run_at": run_at(),
        "git_sha": git_sha(),
        "holdout_slots": int(holdout_slots),
        # The weight actually in force for this run — a blended clean sheet
        # is only interpretable next to it.
        "odds_blend_weight": odds_blend_weight(),
        "stratified": {
            "all": stratified_metrics(scored["ep"], scored["total_points"]),
            "starters": stratified_metrics(starters["ep"],
                                           starters["total_points"]),
        },
        "heads": {
            "p_play": head_metrics(mp["p_play"],
                                   (hold["minutes"] > 0).astype(float)),
            "p60": head_metrics(
                mp["p60"], (hold["minutes"] >= STARTER_MINUTES).astype(float)),
            "p_start": head_metrics(modes["p_start"], start_truth(hold)),
            "cs": head_metrics(tp["p_cs"], hold_tg["cs"].astype(float)),
        },
        "baselines": {
            "last5": baseline_metrics(hold, "total_points_r5", truth),
            # Not a season PPG: the window is the last 38 matches wherever
            # they fall, season boundaries included.
            "last38_ppg": baseline_metrics(hold, "total_points_r38", truth),
        },
    }


SHADOW_PLAYED_MINUTES = 0
"""Minutes above which a player counts as having played at all.

The Brier score's outcome is "did he turn out", not "did he start": a
one-minute cameo is a two-point appearance and a returning injury's whole
question. The 60-minute threshold belongs to ``p60``, not here.
"""


def score_news_shadow(shadow: pd.DataFrame,
                      actuals: pd.DataFrame) -> dict:
    """Gate N2's readout: news predictions vs flags-only, on played weeks.

    Brier on "played at all" and MAE on minutes, computed for both sides of
    each shadow row and reported per gameweek and cumulatively. Gameweeks
    with no actuals yet are simply absent — the log is written every week and
    scored whenever the results land.

    This measures the *availability layer* and nothing else: both sides come
    off the same model run, so any difference between the columns is the news
    layer's doing by construction.
    """
    if shadow is None or shadow.empty or actuals is None or actuals.empty:
        return {"run_at": run_at(), "git_sha": git_sha(), "rows": 0,
                "overall": {}, "by_gw": []}
    # Gameweek 5 comes round every year, so the log's key is the season's as
    # well where the column exists. Logs banked before it does keep the old
    # two-part key rather than being dropped.
    key = (["season", "gw", "code"] if "season" in shadow.columns
           else ["gw", "code"])
    # v10 §F2b: the third side exists only when the classifier has spoken, and
    # "has spoken" is decided on the rows where it *could* have. A column that
    # is a copy of ``p_play_news`` means every verdict was informational, and a
    # third Brier identical to the first would read as a result rather than as
    # silence. A pre-v10 log has no column at all and takes exactly the path it
    # always did.
    #
    # The null rows are the case a log spanning the upgrade actually presents:
    # ``write_shadow`` back-fills every column SHADOW_COLS gained, so weeks
    # banked before v10 read back as NaN. Those rows are not equal to
    # ``p_play_news`` either — NaN is equal to nothing — so gating on
    # inequality alone would admit a side whose Brier is NaN over the whole
    # log, and ``save_evaluation`` serialises with ``allow_nan=False``. The
    # cost of getting this wrong is not a wrong number in the N2 readout; it is
    # no readout at all.
    sides = ["news", "flags"]
    if "p_play_presser" in shadow.columns:
        told = shadow[shadow["p_play_presser"].notna()]
        if not told.empty and not told["p_play_presser"].equals(
                told["p_play_news"]):
            sides.append("presser")
    cols = key + ["p_play_news", "p_play_flags", "e_min_news", "e_min_flags"]
    if "presser" in sides:
        cols = cols + ["p_play_presser"]
    truth = (actuals.groupby(["gw", "code"], as_index=False)
             .agg(minutes=("minutes", "sum")))
    joined = (shadow[cols].groupby(key, as_index=False).last()
              .merge(truth, on=["gw", "code"], how="inner"))
    if joined.empty:
        return {"run_at": run_at(), "git_sha": git_sha(), "rows": 0,
                "overall": {}, "by_gw": []}
    played = (joined["minutes"] > SHADOW_PLAYED_MINUTES).astype(float)
    for side in sides:
        joined[f"_brier_{side}"] = (joined[f"p_play_{side}"] - played) ** 2
        # The presser side is a p_play factor and has no minutes counterpart:
        # would_factor damps the probability of appearing, not an expected
        # minutes total, so there is no e_min_presser to score.
        if f"e_min_{side}" in joined.columns:
            joined[f"_ae_{side}"] = (joined[f"e_min_{side}"]
                                     - joined["minutes"]).abs()

    def _summary(frame: pd.DataFrame) -> dict:
        out = {f"brier_{s}": round(float(frame[f"_brier_{s}"].mean()), 4)
               for s in sides if s != "presser"}
        out.update({f"mae_{s}": round(float(frame[f"_ae_{s}"].mean()), 3)
                    for s in sides if f"_ae_{s}" in frame.columns})
        out["rows"] = int(len(frame))
        # The presser side scores its own rows and reports its own count. The
        # two numbers are read together or not at all: a Brier over one row and
        # a Brier over two hundred are not the same evidence, and the shared
        # ``rows`` above belongs to the other two sides, which score every row.
        # A stretch with no verdicts in it carries no key rather than a null
        # one — the same silence a pre-v10 log gets.
        if "presser" in sides:
            scored = frame[frame["p_play_presser"].notna()]
            if not scored.empty:
                out["brier_presser"] = round(
                    float(scored["_brier_presser"].mean()), 4)
                out["rows_presser"] = int(len(scored))
        return out

    by_gw = []
    for gw in sorted(int(g) for g in joined["gw"].unique()):
        week = joined[joined["gw"] == gw]
        row = {"gw": gw, **_summary(week)}
        upto = joined[joined["gw"] <= gw]
        cum = _summary(upto)
        row["cum_brier_news"] = cum["brier_news"]
        row["cum_brier_flags"] = cum["brier_flags"]
        row["cum_mae_news"] = cum["mae_news"]
        row["cum_mae_flags"] = cum["mae_flags"]
        if "brier_presser" in cum:
            row["cum_brier_presser"] = cum["brier_presser"]
        by_gw.append(row)

    return {"run_at": run_at(), "git_sha": git_sha(),
            "rows": int(len(joined)), "overall": _summary(joined),
            "by_gw": by_gw}


ACTUALS_PATH = "live/player_gw.parquet"
"""This season's played rows. Carries no ``season`` column, which is why
:func:`evaluate_news_shadow` cuts the *log* to one season before joining."""

ACTUALS_COLS = ["gw", "code", "minutes"]


def news_actuals() -> pd.DataFrame:
    """The results frame every availability report is graded against.

    Lifted out of :func:`evaluate_news_shadow` so v12 §3.1 and §3.2 grade
    against the same rows this gate has always used, rather than against a
    second reader that agrees with it until the day it does not.

    An empty frame carries the join keys, so a caller may merge on them
    without checking first.
    """
    from gaffer.data import store

    if not store.exists(ACTUALS_PATH):
        return pd.DataFrame(columns=ACTUALS_COLS)
    return store.load(ACTUALS_PATH)


def evaluate_news_shadow() -> dict:
    """:func:`score_news_shadow` over the banked log and the live results.

    The log spans seasons; the truth does not. ``live/player_gw.parquet`` is
    this season's results and carries no season column, so last season's GW5
    row would join this season's GW5 minutes — a different fixture, often a
    different club — and quietly corrupt the N2 readout at the rollover. The
    cut is made here rather than in the scorer, which stays season-agnostic
    and scores whatever it is handed.

    A config that will not load, or a log banked before the season column
    existed, leaves the log whole: the filter sharpens the readout, it is not
    a gate on producing one.
    """
    from gaffer.news_shadow import load_shadow

    actuals = news_actuals()
    shadow = load_shadow()
    try:
        season = str(load_config().current_season)
        if season and shadow is not None and "season" in shadow.columns:
            shadow = shadow[shadow["season"].astype(str) == season]
    except Exception as e:  # noqa: BLE001 — a readout is better than none
        print(f"news-shadow: scoring every season ({e})")
    return score_news_shadow(shadow, actuals)


CALIBRATION_NOTE = ("Run `gaffer evaluate --calibration` after a graded "
                    "gameweek.")
"""What an empty report says instead of nothing. The report is CLI-only —
``JOB_KINDS`` maps a kind to a zero-argument callable, so there is no flag to
pass through a job (plan A14) — which makes the sentence part of the payload."""

CALIBRATION_HEADS = ("p_play", "p60", "p_cs", "p_haul")
"""The four banked probabilities this report grades, in payload order."""

PER_GW_HEADS = ("p_play", "p60", "p_haul")
"""The three that a single gameweek has the rows to say anything about."""

PER_GW_OMITTED = {
    "p_cs": ("graded per club-fixture — about 20 a gameweek, below the "
             f"{MIN_CALIBRATION_SAMPLES}-sample floor — so it is scored in "
             "the cumulative row only"),
}
"""Why the per-gameweek table has three columns and the cumulative row four.

A clean sheet is one event per club per fixture, so a gameweek supplies about
twenty rows against :data:`MIN_CALIBRATION_SAMPLES`'s thirty. A per-gameweek
``p_cs`` column could therefore never read anything but "not enough data" —
a column of refusals that looks like a defect in the model rather than an
arithmetic certainty about the grain. Lowering the floor for this one head was
the alternative and is worse: thirty is already the point at which ten
reliability bins start to mean anything, and a team-grain exception would put
the loosest evidence in the report under the most confident-looking heading.
The rows are not thrown away — they pool into the cumulative row, which is
where a clean-sheet trend was always going to become readable."""


def _calibration_empty(note: str, season: str | None = None) -> dict:
    """A well-formed payload with nothing in it. August is a real state."""
    return {"run_at": run_at(), "git_sha": git_sha(), "season": season,
            "gameweeks": [], "cumulative": {
                h: calibration_head([], []) for h in CALIBRATION_HEADS},
            "omitted": {"p_start": "not banked"},
            "per_gw_omitted": dict(PER_GW_OMITTED), "excluded": [],
            "missing": [], "note": note}


def _column(frame: pd.DataFrame, name: str) -> pd.Series:
    """``frame[name]`` as floats, or an all-NaN column of the same length.

    A banked artifact from an older ``COMPONENT_COLS`` is missing a head, not
    broken: ``_paired`` drops the non-finite rows and the head reports
    ``insufficient`` rather than taking the whole report down.
    """
    if name not in frame.columns:
        return pd.Series(float("nan"), index=frame.index, dtype="float64")
    return pd.to_numeric(frame[name], errors="coerce")


FIXTURE_KEYS = ("code", "opp_code", "kickoff_time")
"""The grain both sides of the calibration join are read at.

The banked components are one row *per player-fixture* — ``advise`` builds
them positionally off the fixture frame precisely so a double gameweek is two
rows — and ``live/player_gw.parquet`` is the same grain before anything
aggregates it. Merging on ``code`` alone grades each of a DGW player's two
prediction rows against the pair's totals, which invents outcomes: 90 minutes
across two 45-minute legs reads as a 60-minute appearance that happened in
neither, and a return in each leg reads as a haul in both. ``advise`` already
joins predictions to fixtures on this key; so does this.

``kickoff_time`` is here because ``(code, opp_code)`` **is not a key**. A
double gameweek in which a club draws the same opponent twice — a rearranged
league fixture landing beside the scheduled one, which is the ordinary way a
DGW comes about — gives that club's players two rows per side with identical
codes. The inner merge then pairs each prediction with both outcomes: ``n``
doubles, every one of that player's rows is graded twice, once against a match
it was not a forecast of, and :func:`_club_clean_sheets` collapses two
club-fixtures into one club-fixture whose conceded is the max of both. The
kickoff separates them, and it is the only column that can: nothing else on
either frame distinguishes the two legs.

Both sides carry it — components off the fixture frame, ``player_gw`` as the
API's ISO string — so :func:`_key` normalises rather than assuming a dtype.
"""

FIXTURE_CODE_KEYS = ("code", "opp_code")
"""The subset of :data:`FIXTURE_KEYS` that is a club/player code, not a stamp.

Named so :func:`_key` can coerce the two families correctly instead of running
``to_numeric`` over a timestamp column and turning every kickoff into NaN.
"""


def _key(frame: pd.DataFrame) -> pd.DataFrame:
    """``frame`` with :data:`FIXTURE_KEYS` coerced to one comparable dtype.

    The two sides are read off different parquets written by different code
    paths, and an ``int64`` column merged against an ``Int64`` one silently
    matches nothing. ``kickoff_time`` is the same hazard in a second dialect:
    ``player_gw`` banks the API's ``"2026-08-21T19:00:00Z"`` string and the
    components carry whatever dtype the fixture frame held, so both go through
    ``to_datetime(..., utc=True)`` and are compared as instants.

    **Rows whose kickoff will not parse are dropped**, alongside the rows with
    no code, and that is a deliberate reading of the guarded-parse lesson
    rather than the obvious one. ``errors="coerce"`` leaves them ``NaT``, and
    the tempting assumption is that ``NaT`` simply fails to match and drops
    itself. It does not: pandas merges treat null keys as equal to each other
    (verified on 3.0.5), so a handful of unparseable rows on each side would
    inner-join into exactly the cartesian this key was added to remove. Fail
    closed and drop them; :func:`_join_is_per_fixture` then checks what is
    left, so a week losing rows this way cannot pass as a clean join.
    """
    out = frame.copy()
    for col in FIXTURE_CODE_KEYS:
        out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")
    # ``format="mixed"`` because the two sides genuinely are: one column is
    # the API's ISO strings, the other whatever dtype the fixture frame held.
    # It also keeps pandas from printing its infer-the-format warning on every
    # week that contains one unparseable stamp — a warning that would train a
    # reader to ignore the log where the coerce is the interesting part.
    out["kickoff_time"] = pd.to_datetime(out["kickoff_time"], format="mixed",
                                         errors="coerce", utc=True)
    return out.dropna(subset=list(FIXTURE_KEYS))


def _join_is_per_fixture(frame: pd.DataFrame) -> bool:
    """Is ``frame`` at most one row per :data:`FIXTURE_KEYS` tuple?

    Asked of each side *before* the merge, because an inner join on a
    non-unique key is silently multiplicative and there is no reading of the
    result that recovers what happened. The kickoff makes duplicates a real
    defect rather than a schedule quirk: two rows with the same player, the
    same opponent and the same instant are two records of one fixture, and
    grading against both counts one outcome twice.

    A ``False`` here excludes the gameweek with its reason rather than raising.
    The report grades every other week in the same pass, and one malformed
    parquet taking the whole calibration page down would be a worse trade than
    a row in ``excluded`` saying exactly which week and why.
    """
    return not frame.duplicated(subset=list(FIXTURE_KEYS)).any()


def _club_clean_sheets(joined: pd.DataFrame) -> pd.DataFrame:
    """One row per club-fixture: the banked ``p_cs`` and what actually happened.

    The outcome is the *team's*, derived to match ``models.team``'s canonical
    ``cs = (ga == 0)``. It cannot be read off a player row, because FPL's
    per-player ``clean_sheets`` is an award, not a result: it is 0 for everyone
    under 60 minutes even when the club conceded nothing. Taking one arbitrary
    row's value therefore turns row order into the answer — on real GW1 data
    ``first(cs)`` and ``max(cs)`` disagree for 14% of club-fixtures.

    ``max(cs)`` is not the fix either, and the same GW1 data says so: a
    substitute who came on after the goal has 60+ minutes and none conceded
    *while on the pitch*, so he is awarded a clean sheet his club did not keep
    — two of that week's twenty clubs. What holds is goals conceded: FPL counts
    a player's ``gc`` only while he is on the pitch, so every row's value is a
    lower bound on the club's total and can never exceed it. The club's figure
    is the maximum over its rows, and ``ga == 0`` is then the definition
    ``models/team.py`` fits against.

    **Two decisions inside that, stated rather than implied.**

    *Which rows the maximum runs over: all of them.* An earlier version
    maximised over the 60-minute rows only, on the argument that a player who
    saw most of the match saw every goal. That argument is a near-certainty and
    not a guarantee — a 60-minute player missed up to thirty minutes and any
    goal inside them, and the keeper's 90 is what usually rescues it, not
    anything the filter enforces. Since no row can over-count, adding the
    shorter appearances can only move the maximum *towards* the club's true
    total and never past it, so the wider maximum is the strictly closer
    estimate. The residual exposure is a mislabelled row — a stale
    ``team_code`` filing an opponent's player under this club — which
    over-counts; that hazard existed under the 60-minute rule too for any
    stray who played an hour, and the fixture-grain key (opponent *and*
    kickoff) is what keeps it rare.

    *What the 60-minute rule still does: it gates existence, not the value.* A
    club-fixture with no 60-minute row anywhere is dropped rather than guessed
    — that is a stray row, not a club's match — but once the club-fixture is
    real, every one of its rows is allowed to speak to the conceded count.

    Grouped at :data:`FIXTURE_KEYS`' club grain, kickoff included: a club that
    meets the same opponent twice in one gameweek played two matches, and
    ``(team_code, opp_code)`` alone would fold them into one club-fixture whose
    conceded is the worse of the two and whose clean sheet belongs to neither.
    """
    needed = {"team_code", "opp_code", "kickoff_time"}
    if not needed <= set(joined.columns):
        return pd.DataFrame({"p_cs": [], "clean_sheet": []}, dtype="float64")
    work = pd.DataFrame({
        "team_code": joined["team_code"], "opp_code": joined["opp_code"],
        "kickoff_time": joined["kickoff_time"],
        "minutes": _column(joined, "minutes"), "gc": _column(joined, "gc"),
        "p_cs": _column(joined, "p_cs")})
    club_keys = ["team_code", "opp_code", "kickoff_time"]
    # The 60-minute rule as an existence gate: a club-fixture qualifies if any
    # of its rows saw an hour, and then keeps *all* of its rows for the
    # maximum. See this function's docstring for why the value is read wider
    # than the gate.
    played = work[work["minutes"] >= STARTER_MINUTES]
    if played.empty:
        return pd.DataFrame({"p_cs": [], "clean_sheet": []}, dtype="float64")
    real = set(map(tuple, played[club_keys].to_numpy()))
    work = work[[tuple(row) in real for row in work[club_keys].to_numpy()]]
    by_club = work.groupby(club_keys, as_index=False).agg(
        # p_cs is a club-level column repeated on every player row; max rather
        # than first only so a stray NaN row cannot decide it.
        p_cs=("p_cs", "max"), conceded=("gc", "max"))
    by_club["clean_sheet"] = (by_club["conceded"] == 0).astype("float64")
    # A club whose goals-conceded column is missing entirely has no outcome —
    # NaN, which _paired drops — rather than a free clean sheet.
    by_club.loc[by_club["conceded"].isna(), "clean_sheet"] = float("nan")
    return by_club


POST_HOC_REASON = "artifact written after the gameweek's first kickoff"
"""Why a banked file is refused, named where both the report and its tests
can read it. The wording is the boundary: *first*, not last."""


def _first_kickoff_ns(gw: int) -> int | None:
    """Nanoseconds of the gameweek's **first** kickoff, or ``None`` if unknown.

    The first, because that is the moment after which any part of the file
    could be hindsight. A gameweek is played over three days and
    ``save_components`` rewrites every player's row at once, so a Sunday
    morning advise run — ordinary behaviour — banks Saturday's finished
    fixtures alongside Sunday's unplayed ones. A guard on the last kickoff
    passes that file; a guard on the first does not.

    ``None`` is an exclusion, not a pass: see :func:`evaluate_calibration`'s
    post-hoc guard, which fails closed.
    """
    from gaffer.data import store

    try:
        if not store.exists("live/fixtures_all.parquet"):
            return None
        fixtures = store.load("live/fixtures_all.parquet")
        week = fixtures[fixtures["gw"].astype("Int64") == int(gw)]
        stamps = pd.to_datetime(week["kickoff_time"], errors="coerce",
                                utc=True).dropna()
        if stamps.empty:
            return None
        return int(stamps.min().value)
    except Exception as exc:  # noqa: BLE001 — unknown is an exclusion
        print(f"calibration: no kickoff information for GW{gw} ({exc})")
        return None


def evaluate_calibration(season: str | None = None) -> dict:
    """Per-gameweek reliability for the probabilities the optimizer used.

    **The predictions are banked, not refitted, and that is the whole design.**
    ``advise.py`` writes ``reports/components_gw{N}.parquet`` on the weekly run,
    before the gameweek is played, and it carries ``p_play``, ``p60``, ``p_cs``
    and the ``e_goals``/``e_assists`` that ``models.assemble.p_haul`` turns into
    the attacking-haul probability (``p_attacking_haul`` at the web boundary
    since v9c). Those are the numbers the solver actually multiplied by that
    week — the only version of "is the model calibrated" that anyone can act on.
    Refitting strictly-before would grade a *different* model from the one that
    served, and ``evaluate_current`` already exists for that protocol; putting
    both on one Brier trend would make the slope partly an artefact of which
    protocol each week used.

    ``p_start`` is absent from ``COMPONENT_COLS`` — the minutes trichotomy is
    never banked — so it is omitted and the payload says why, rather than being
    silently missing. ``p_cs`` is graded, but only cumulatively: see
    :data:`PER_GW_OMITTED` for why a per-gameweek column of it could never say
    anything.

    **A gameweek whose artifact was written after the whistle is not graded.**
    ``save_components`` writes ``gw{N}`` whatever today's date is, so re-running
    ``advise`` against a finished gameweek replaces an as-of prediction with a
    hindsight one and nothing in the file records that it happened. The only
    signal is the file's mtime against the gameweek's *first* kickoff, so that
    is the guard, and it fails closed: no kickoff information is also an
    exclusion. The first kickoff and not the last, because the file is written
    whole: a Sunday-morning re-run banks Saturday's played fixtures in the same
    frame as Sunday's unplayed ones, and every stamp between the two whistles
    would pass a last-kickoff guard.
    A false exclusion loses a row; a false inclusion invents a result.

    Completed gameweeks are those present in ``live/player_gw.parquet``, which
    is the data_checked gate the rest of the pipeline already uses. Both sides
    are read at **player-fixture grain** (:data:`FIXTURE_KEYS`), never at
    gameweek grain: a double gameweek's two prediction rows are two separate
    forecasts and grading either against the pair's totals invents outcomes
    that happened in no fixture.

    **``p60`` is graded unconditionally** (plan A13). Spec §4 writes its
    outcome as "minutes >= 60 *given played*", but the parenthetical does not
    match the quantity: ``MinutesModel.predict`` computes
    ``p60 = p_start * P(60+ | start)``, an unconditional probability, which is
    how the assemble path uses it and how :func:`evaluate_current` already
    scores it. Filtering the outcome rows to ``minutes > 0`` while leaving the
    prediction unconditional would make the head look badly under-confident for
    a reason entirely the scorer's.
    """
    from gaffer.artifacts import components_path, load_components
    from gaffer.data import store
    from gaffer.models.assemble import p_haul

    if not store.exists("live/player_gw.parquet"):
        return _calibration_empty(
            "No graded gameweeks yet — `live/player_gw.parquet` is absent. "
            + CALIBRATION_NOTE, season)
    truth_all = store.load("live/player_gw.parquet")
    if season is not None and "season" in truth_all.columns:
        truth_all = truth_all[truth_all["season"].astype(str) == str(season)]
    if truth_all.empty:
        return _calibration_empty(
            "No graded gameweeks yet. " + CALIBRATION_NOTE, season)

    rows: list[dict] = []
    excluded: list[dict] = []
    # ``missing`` is one fact only: no banked artifact for that gameweek.
    # Everything else a gameweek can fail on is an excluded entry carrying
    # its own reason.
    missing: list[int] = []
    pooled: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {
        h: [] for h in CALIBRATION_HEADS}

    for gw in sorted(int(g) for g in truth_all["gw"].dropna().unique()):
        path = components_path(gw)
        if not path.exists():
            missing.append(gw)
            continue
        first_kickoff = _first_kickoff_ns(gw)
        if first_kickoff is None:
            excluded.append({"gw": gw, "reason": "kickoff unknown"})
            continue
        if path.stat().st_mtime_ns > first_kickoff:
            excluded.append({"gw": gw, "reason": POST_HOC_REASON})
            continue
        try:
            comp = load_components(gw)
        except Exception as exc:  # noqa: BLE001 — one unreadable week only
            excluded.append({"gw": gw, "reason": f"unreadable ({exc})"})
            continue

        truth = truth_all[truth_all["gw"].astype("Int64") == gw]
        if not set(FIXTURE_KEYS) <= set(comp.columns) & set(truth.columns):
            excluded.append({"gw": gw, "reason": "no per-fixture key"})
            continue
        if "team_code" not in comp.columns:
            # Asked of the *components*, not of the joined frame. The merge
            # suffixes collisions as ``_truth`` and keeps the left name, so a
            # components file with no team_code hands _club_clean_sheets the
            # truth side's stamped club instead — which grades p_cs, a banked
            # club-level prediction, against clubs the prediction never named.
            # A week that cannot say whose prediction it is is excluded.
            excluded.append({"gw": gw, "reason": "components carry no club"})
            continue
        keyed_comp, keyed_truth = _key(comp), _key(truth)
        # Both sides checked *before* the merge, because an inner join on a
        # non-unique key multiplies rather than errors and the result cannot
        # be told apart from a genuinely larger week.
        unique = {"components": _join_is_per_fixture(keyed_comp),
                  "graded rows": _join_is_per_fixture(keyed_truth)}
        if not all(unique.values()):
            side = ", ".join(name for name, ok in unique.items() if not ok)
            excluded.append(
                {"gw": gw,
                 "reason": f"duplicate rows per player-fixture ({side})"})
            continue
        joined = keyed_comp.merge(keyed_truth, on=list(FIXTURE_KEYS),
                                  how="inner", suffixes=("", "_truth"))
        if joined.empty:
            # Not "missing": the artifact is there. The two facts have
            # different causes and different fixes — one is an advise run
            # that never happened, the other a file whose codes do not
            # match the graded week — so they are reported apart.
            excluded.append(
                {"gw": gw, "reason": "banked components joined no graded rows"})
            continue

        # One clean sheet is one event and eleven player rows: graded at
        # club-fixture grain, or a well-covered club counts eleven times.
        by_club = _club_clean_sheets(joined)
        # Recomputed through the same function assemble_ep called at solve
        # time, not approximated: the banked components carry the inputs.
        #
        # Only for the rows that have them. p_haul maps a missing input to
        # lam = 0 and returns 0.0, which is the right answer at solve time —
        # a player with no attacking estimate is worth nothing to the
        # optimizer — and a fabricated one here: an artifact banked before
        # e_goals existed would grade as a head that was confidently certain
        # nothing would happen, against weeks in which it did. A prediction
        # that was never made is NaN, and _paired drops it.
        e_goals, e_assists = _column(joined, "e_goals"), _column(
            joined, "e_assists")
        has_inputs = e_goals.notna() & e_assists.notna()
        haul_pred = pd.Series(float("nan"), index=joined.index,
                              dtype="float64")
        if has_inputs.any():
            haul_pred.loc[has_inputs] = [
                p_haul(g, a) for g, a in zip(e_goals[has_inputs],
                                             e_assists[has_inputs])]
        pairs = {
            "p_play": (_column(joined, "p_play"), joined["minutes"] > 0),
            "p60": (_column(joined, "p60"),
                    joined["minutes"] >= STARTER_MINUTES),
            "p_cs": (by_club["p_cs"], by_club["clean_sheet"]),
            "p_haul": (haul_pred,
                       (joined["goals"] + joined["assists"]) >= 2),
        }
        heads = {name: calibration_head(*pairs[name]) for name in PER_GW_HEADS}
        for name, pair in pairs.items():
            pooled[name].append(_paired(*pair))

        # ``n`` is the week's joined player-fixture rows and nothing more —
        # how much data the gameweek had, not how much any head graded. The
        # two diverge and are meant to: p_cs is scored at club-fixture grain
        # (about twenty rows against several hundred) and p_haul drops every
        # row whose artifact predates ``e_goals``. Each head therefore carries
        # its **own** n out of ``calibration_head``, and that is the number the
        # card prints beside each cell. Reading this one as a per-head count
        # would overstate every head in the row.
        rows.append({"gw": gw, "n": int(len(joined)), "heads": heads})

    cumulative = {}
    for name in CALIBRATION_HEADS:
        pairs = pooled[name]
        pred = np.concatenate([p for p, _ in pairs]) if pairs else np.array([])
        actual = np.concatenate([y for _, y in pairs]) if pairs else np.array([])
        cumulative[name] = calibration_head(pred, actual)

    note = None
    if not rows:
        note = ("Nothing graded yet — no banked components matched a completed "
                "gameweek. " + CALIBRATION_NOTE)
    return {"run_at": run_at(), "git_sha": git_sha(), "season": season,
            "gameweeks": rows, "cumulative": cumulative,
            # Named with its reason rather than silently absent: a reader who
            # cannot see p_start would otherwise conclude it is calibrated.
            "omitted": {"p_start": "not banked"},
            # Not the same refusal as ``omitted``: p_cs *is* graded, just not
            # at a grain one gameweek has the rows for.
            "per_gw_omitted": dict(PER_GW_OMITTED),
            "excluded": excluded, "missing": missing, "note": note}


BENCHMARK_TRAIN_MAX_IDX = 1
"""Newest season the benchmark may train on: season_idx 1 = 2023-24."""

BENCHMARK_TEST_IDX = 2
BENCHMARK_TEST_SEASON = "2024-25"
"""The season OpenFPL published its test numbers on."""

REFERENCES = {
    # OpenFPL, arXiv:2508.09992 — per-return-category RMSE and MAE on
    # 2024-25, the same categories used here. FPL Review's numbers are the
    # ones published alongside them in that paper, not measured by us.
    "openfpl": {
        "zeros": {"rmse": 0.818, "mae": 0.427},
        "blanks": {"rmse": 1.291, "mae": 0.749},
        "tickers": {"rmse": 1.517, "mae": 1.127},
        "haulers": {"rmse": 5.142, "mae": 4.317},
    },
    "fplreview": {
        "zeros": {"rmse": 0.689, "mae": 0.237},
        "blanks": {"rmse": 1.189, "mae": 0.597},
        "tickers": {"rmse": 1.594, "mae": 1.227},
        "haulers": {"rmse": 5.172, "mae": 4.381},
    },
}

BENCHMARK_CAVEAT = (
    "Same test season (2024-25) and the same return categories, but OpenFPL "
    "trained on four seasons (2020-21 to 2023-24) against our two, and the "
    "feature sets differ. Treat these as a yardstick, not a controlled "
    "comparison.")


def benchmark_split(df: pd.DataFrame,
                    max_train_idx: int = BENCHMARK_TRAIN_MAX_IDX,
                    test_idx: int = BENCHMARK_TEST_IDX
                    ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """``(train, test)`` for the published-numbers benchmark.

    A hard season split, not a slot split: the comparison is only meaningful
    if the model has seen nothing at all from the test season during fitting.
    The test frame's own features are still leakage-safe within the season —
    every rolling column shifts one match back — which is exactly the
    walk-forward the benchmark wants.
    """
    return (df[df["season_idx"] <= max_train_idx],
            df[df["season_idx"] == test_idx])


BENCHMARK_ABSENT_RULES = ("defensive_contribution",)
"""Scoring rules the 2024-25 season did not have.

Defensive contribution points arrived in 2025/26. The bundled scoring table
is always the *current* season's, so pricing 2024-25 expected points with it
hands every defender and midfielder points that season never awarded — a
systematic upward bias against the truth the benchmark scores against, and
against the published OpenFPL / FPL Review numbers alongside it.
"""


def benchmark_scoring(scoring: dict) -> dict:
    """``scoring`` restated to the test season's vintage.

    A copy with :data:`BENCHMARK_ABSENT_RULES` removed. ``assemble_ep`` reads
    the rules it may not find through ``s_opt``, which falls back to a no-op
    for a missing key, so dropping one simply drops that term from EP.
    Benchmark mode only: current mode is scored against the current season,
    where the rule is real.
    """
    return {k: v for k, v in scoring.items() if k not in BENCHMARK_ABSENT_RULES}


def evaluate_benchmark(max_train_idx: int = BENCHMARK_TRAIN_MAX_IDX,
                       test_idx: int = BENCHMARK_TEST_IDX) -> dict:
    """Train on the early seasons, predict every gameweek of the test season.

    One fit, then a gameweek at a time at a 1-gameweek horizon. Walking the
    gameweeks rather than predicting the season in one shot is not a
    formality: it is what keeps the loop honest about the horizon it claims,
    and it mirrors the replay's per-gameweek shape.
    """
    from gaffer.assets import load_bootstrap_sample
    from gaffer.data.bootstrap import scoring_table
    from gaffer.models.assemble import apply_calibration, assemble_ep, ep_matrix
    from gaffer.models.train import (load_training_frame,
                                     predict_components_simple, train_all)

    df, tg, _ = load_training_frame()
    train_df, test_df = benchmark_split(df, max_train_idx, test_idx)
    train_tg, _ = benchmark_split(tg, max_train_idx, test_idx)
    models = train_all(train_df, train_tg.dropna(subset=["elo_diff"]),
                       save=False)
    # The bundled table is the current season's; the test season is not.
    scoring = benchmark_scoring(scoring_table(load_bootstrap_sample()))

    parts = []
    for gw in sorted(int(g) for g in test_df["gw"].dropna().unique()):
        rows = test_df[test_df["gw"] == gw].reset_index(drop=True)
        if rows.empty:
            continue
        comp = predict_components_simple(models, rows)
        ep = ep_matrix(apply_calibration(assemble_ep(comp, scoring),
                                         models.get("calibration")))
        truth = rows.groupby(["code", "gw"], as_index=False).agg(
            total_points=("total_points", "sum"),
            minutes=("minutes", "sum"))
        parts.append(ep.merge(truth, on=["code", "gw"], how="inner"))
        print(f"benchmark gw{gw}: {len(parts[-1])} rows", flush=True)

    scored = pd.concat(parts, ignore_index=True)
    starters = scored[scored["minutes"] >= STARTER_MINUTES]
    return {
        "run_at": run_at(),
        "git_sha": git_sha(),
        "test_season": BENCHMARK_TEST_SEASON,
        "stratified": {
            "all": stratified_metrics(scored["ep"], scored["total_points"]),
            "starters": stratified_metrics(starters["ep"],
                                           starters["total_points"]),
        },
        "references": REFERENCES,
        "caveat": BENCHMARK_CAVEAT,
    }


DECOMPOSITION_HORIZONS = (1, 3)
DECOMPOSITION_SOURCES = ("model", "oracle")


def run_decomposition(season: str = "2025-26", start_gw: int = 5) -> dict:
    """Split the replay's shortfall into forecasting error and headroom.

    Four full replays — {model, oracle} x {h1, h3}. The two numbers that come
    out are the ones worth arguing about:

    ``forecast_gap_h3``
        ``oracle_h3 - model_h3``: everything a perfect forecast would add at
        the horizon the tool actually plans on. This is the size of the prize
        for model work.
    ``planning_ceiling``
        ``oracle_h3 - oracle_h1``: what looking three weeks ahead is worth
        when the forecast is already perfect — the absolute ceiling on
        multi-week planning, and usually a good deal smaller than people
        expect.

    Slow: the two model runs retrain every four gameweeks across a season.
    Run it under ``caffeinate -i``; machine sleep has killed long runs here
    before.
    """
    from gaffer import backtest

    cells: dict[str, dict] = {}
    for source in DECOMPOSITION_SOURCES:
        for horizon in DECOMPOSITION_HORIZONS:
            out = backtest.run_backtest(season=season, start_gw=start_gw,
                                        horizon=horizon, ep_source=source)
            cells[f"{source}_h{horizon}"] = {
                "total": int(out["total"]),
                "per_gw": float(out["per_gw"]),
                "hits": int(sum(int(r["hits"]) for r in out["log"])),
            }
            print(f"{source} h{horizon}: {out['total']}", flush=True)

    return {
        "run_at": run_at(),
        "git_sha": git_sha(),
        "season": season,
        "start_gw": int(start_gw),
        "cells": cells,
        "forecast_gap_h3": float(cells["oracle_h3"]["total"]
                                 - cells["model_h3"]["total"]),
        "planning_ceiling": float(cells["oracle_h3"]["total"]
                                  - cells["oracle_h1"]["total"]),
    }


def _format_news_shadow(payload: dict) -> str:
    """Gate N2's table: news against flags, per gameweek and cumulative."""
    if not payload.get("rows"):
        return ("news shadow: nothing to score yet — the log needs a "
                "completed gameweek.")
    lines = [f"news shadow ({payload['rows']} player-gameweeks)",
             "  gw   brier news / flags    mae news / flags"]
    for row in payload["by_gw"]:
        lines.append(
            f"  GW{row['gw']:<3} {row['brier_news']:.4f} / "
            f"{row['brier_flags']:.4f}      {row['mae_news']:.2f} / "
            f"{row['mae_flags']:.2f}")
    o = payload["overall"]
    lines.append(f"  all   {o['brier_news']:.4f} / "
                 f"{o['brier_flags']:.4f}      {o['mae_news']:.2f} / "
                 f"{o['mae_flags']:.2f}")
    return "\n".join(lines)


def _format_calibration(payload: dict) -> str:
    """The v9d §4 table: per-gameweek Brier per head, then the refusals.

    The exclusions are printed rather than summarised. A run that graded
    nothing has to say so on the terminal, or a reader takes an empty table
    for a clean one.
    """
    def cell(head: dict | None) -> str:
        if not head or head.get("status") != "scored":
            n = (head or {}).get("n", 0)
            return f"  n/a({n:>4})"
        return f"{head['brier']:8.4f}({head['n']:>4})"

    lines = [f"=== calibration (run_at {payload.get('run_at')}, "
             f"sha {payload.get('git_sha')}) ===",
             "  gw   " + "".join(f"{h:>14}" for h in CALIBRATION_HEADS)]
    for row in payload.get("gameweeks", []):
        heads = row.get("heads", {})
        # A head with no per-gameweek column prints a dash, not a zero count:
        # it was not scored at this grain rather than scored and empty.
        lines.append(f"  GW{row['gw']:<3} " + "".join(
            f"{'-':>14}" if h not in heads else cell(heads.get(h))
            for h in CALIBRATION_HEADS))
    cum = payload.get("cumulative", {})
    lines.append("  all   "
                 + "".join(cell(cum.get(h)) for h in CALIBRATION_HEADS))
    for head, why in (payload.get("omitted") or {}).items():
        lines.append(f"  omitted: {head} — {why}")
    for head, why in (payload.get("per_gw_omitted") or {}).items():
        lines.append(f"  per gameweek: {head} — {why}")
    for row in payload.get("excluded") or []:
        lines.append(f"  excluded: GW{row.get('gw')} — {row.get('reason')}")
    if payload.get("missing"):
        lines.append("  no banked components: "
                     + ", ".join(f"GW{g}" for g in payload["missing"]))
    if payload.get("note"):
        lines.append("  " + payload["note"])
    return "\n".join(lines)


def format_report(key: str, payload: dict) -> str:
    """The artifact as a table a human can read in a terminal.

    The JSON is the record; this is what makes a run worth watching while it
    happens. The caveat is printed as well as stored on purpose — a bare
    comparison to somebody else's published numbers invites exactly the wrong
    conclusion.
    """
    # The shadow table is its own report with its own header, so it is
    # answered before the generic header is built rather than after.
    if key == "news_shadow":
        return _format_news_shadow(payload)
    if key == "calibration":
        return _format_calibration(payload)
    lines = [f"=== {key} (run_at {payload.get('run_at')}, "
             f"sha {payload.get('git_sha')}) ==="]
    if payload.get("odds_blend_weight") is not None:
        lines.append(f"odds blend weight w = {payload['odds_blend_weight']:.2f}")
    if key == "decomposition":
        lines.append(f"{payload.get('season')} from GW{payload.get('start_gw')}")
        for name, cell in payload["cells"].items():
            lines.append(f"{name:10s} total {cell['total']:5d}  "
                         f"per_gw {cell['per_gw']:6.2f}  "
                         f"hits {cell['hits']}")
        lines.append(f"forecast_gap_h3   {payload['forecast_gap_h3']:8.1f}  "
                     "points better forecasting could still win")
        lines.append(f"planning_ceiling  {payload['planning_ceiling']:8.1f}  "
                     "most multi-week planning can ever be worth")
        return "\n".join(lines)

    for cut, table in payload.get("stratified", {}).items():
        lines.append(f"-- {cut}")
        for cat in RETURN_CATEGORIES:
            m = table[cat]
            lines.append(f"   {cat:9s} rmse {m['rmse']:7.3f}  "
                         f"mae {m['mae']:7.3f}  n {m['n']}")
    for name, table in payload.get("baselines", {}).items():
        lines.append(f"-- baseline {name}")
        for cat in RETURN_CATEGORIES:
            m = table[cat]
            lines.append(f"   {cat:9s} rmse {m['rmse']:7.3f}  "
                         f"mae {m['mae']:7.3f}  n {m['n']}")
    for source, table in payload.get("references", {}).items():
        lines.append(f"-- {source} (published)")
        for cat, m in table.items():
            lines.append(f"   {cat:9s} rmse {m['rmse']:7.3f}  "
                         f"mae {m['mae']:7.3f}")
    for head, m in payload.get("heads", {}).items():
        ll = m["log_loss"]
        lines.append(f"-- head {head}: log loss "
                     f"{'n/a' if ll is None else format(ll, '.4f')}, "
                     f"{len(m['reliability'])} reliability bins")
        for b in m["reliability"]:
            lines.append(f"   pred {b['pred']:.3f}  obs {b['obs']:.3f}  "
                         f"n {b['n']}")
    if payload.get("caveat"):
        lines.append(f"CAVEAT: {payload['caveat']}")
    return "\n".join(lines)
