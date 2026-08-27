"""Penalty-taker expected points, priced at prediction time (spec §1).

FPL's bootstrap publishes ``penalties_order`` per element, and the number is
serve-time-only: there is no archive of who was on penalties in October 2023,
so this term can never be backtested. That shapes everything here. The term is
small, bounded by a hard clamp, and instrumented — :func:`pen_notices` prints
every nonzero term worth reading so gate P1 can audit the live distribution
instead of replaying one.

**Scope: penalties only.** Direct free kicks and corners are surfaced in the
UI as context and get no EP term: the xA features already price established
takers, and a corner-taker delta is too small to validate.

**The double-count problem.** A player's xG features already contain the
penalties he historically took, so a naive additive term overpays the Salahs.
What is added is only the *increment* over what history priced in::

    ep_pen(p) = (share_now(p) - share_hist(p)) * team_pens_pg(t)
                * PEN_CONVERSION * goal_points(position) * p_play(p)

**How ``share_hist`` is measured, and why it is not what the spec says.** The
spec asks for ``pens_taken ~= goals - npg`` from Understat. Understat's
player-match parquet carries no goals and no npg — only ``us_npxg``, from
which :func:`gaffer.data.understat.match_player_rows` explicitly excludes
penalty shots. But ``models.train.attach_understat`` joins that column onto
FPL rows that *do* carry ``xg``, and FPL's ``expected_goals`` includes
penalties. The gap between them is a penalty, priced at :data:`PEN_XG`.

**Why the gap is counted in events, not accumulated.** Two different xG models
disagree by a few hundredths on open play, and a floored gap
(``max(0, xg - us_npxg)``) turns that disagreement into one-sided noise that
scales with shot volume: summed raw, three seasons of it produced ~730 league
"penalties" against a real ~394, put 14% of them on defenders, and diluted an
every-week taker's share to 0.41. So the gap is *thresholded* instead. A
player-match is credited with ``(gap + 0.29) // 0.79`` penalties: a gap under
half a penalty's xG counts zero, one plausible spot kick (~0.79) counts one,
~1.58 counts two. Rounding noise no longer accumulates, because noise below
half a penalty is not a penalty.

Nothing here does I/O, loads a model or touches the network. Everything is
handed in.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

PEN_CONVERSION = 0.78
"""Share of penalties that are scored. A constant, not a fitted number."""

PEN_XG = 0.79
"""xG a penalty is worth in both public models, near enough.

Used only as the divisor turning an xG gap back into a count of penalties, so
a few percent of error here is a few percent of error on a ratio's numerator
and denominator alike.
"""

SHARE_ORDER_2 = 0.15
"""What the second name on the list is worth.

Not a claim that he takes 15% of his club's penalties. It is a hedge against
the first taker being rotated, subbed or injured, which is the only way the
second name ever steps up.
"""

EP_CLAMP = (-0.3, 0.8)
"""Hard bound on the term, in expected points.

A safety bound rather than a modelling choice: taker orders are serve-time
data of the same class as news, no historical backtest can validate the term,
and an unbounded term multiplied by a 10-point keeper goal would be the one
place this could do real damage.

It bounds the **model-side** increment — what this module adds to ``e_goals``
before anything else touches the frame. On a row the anytime-scorer market
covers, ``blend_attacking_odds`` then takes a weighted average of the market's
expectation and the model's, so only ``(1 - w)`` of this increment survives
into the delivered EP. That is by design: the AGS price already contains the
taker's penalty duty, and adding the full model increment on top of it would
count the same spot kick twice. ``run_advise`` rescales the recorded
``ep_pen_taker`` by the same ``(1 - w)`` so the number in the components file
is the number that was delivered.
"""

ATTACK_MULT_CLAMP = (0.6, 1.6)
"""Bound on a club's attack strength relative to the league mean."""

PEN_EVENT_MIN_XG = 0.5
"""Gap below which a player-match is credited with no penalty at all.

Half a penalty's xG. Two xG models disagreeing about open play produce gaps of
a few hundredths; a spot kick produces ~0.79. Nothing real lives in between,
so the threshold is set where the two populations do not overlap.
"""

LEAGUE_PENS_PG = 0.13
"""League penalties per team-game. A constant, and always the served number.

Roughly 100 penalties across 760 team-games, which is what the Premier League
has run at for years. It is *not* fitted, because the event estimator here
cannot measure an absolute rate faithfully: on the real three-season window it
returns 0.097/game against a true ~0.13, losing about a quarter of the
penalties to Understat coverage gaps and to the ±0.3 tail of xG-model
disagreement, which pushes genuine spot kicks under
:data:`PEN_EVENT_MIN_XG`. Lowering that threshold recovers the number without
recovering the measurement — the sweep runs 0.5 -> 0.097, 0.35 -> 0.123,
0.30 -> 0.140 — so tuning it would only be fitting the constant back through
a biased instrument.

The estimator is kept for ``share_hist``, where the same detection loss sits
in the numerator and the denominator of a within-club ratio and cancels. The
fitted rate is still computed and printed as a drift notice, so a future
season moving away from 0.13 would be visible rather than silent.
"""

MAX_PENS_PER_MATCH = 2.0
"""Per-match cap on the estimator. Three penalties in a match happens about
once a decade; an estimate above two is model disagreement, not a hat-trick
of spot kicks."""

PEN_SEASONS = 3
"""Seasons of history the share is measured over: the last two plus the
current one, as spec §1 asks."""

GOAL_POINTS = {"GKP": 10.0, "DEF": 6.0, "MID": 5.0, "FWD": 4.0}
"""Points per goal by position.

A module constant rather than a threaded-through scoring table, because
``predict_components`` does not have the scoring table in hand and giving it
one would mean moving a line in ``run_advise`` for no gain. A test pins it
against ``scoring_table(load_bootstrap_sample())["goals_scored"]``, so a rule
change breaks the suite rather than drifting silently.
"""

NOTICE_MIN_EP = 0.05
"""Terms below this are not worth a line in the log (gate P1)."""

ZERO_COLS = ("share_now", "share_hist", "goals", "ep")


@dataclass
class PenPriors:
    """A season-scale reading of who takes his club's penalties.

    ``share_hist`` is ``{code: share in [0, 1]}`` and is deliberately *sparse*
    — a player with no history is absent, which reads as zero, which is where
    the term is maximal. That is the intent: the model is blindest about a
    taker it has never seen take one.
    """

    share_hist: dict[int, float] = field(default_factory=dict)
    league_pens_pg: float = LEAGUE_PENS_PG
    team_games: int = 0


def share_now(order) -> pd.Series:
    """Bootstrap queue position -> share of his club's penalties, today."""
    v = pd.to_numeric(pd.Series(order), errors="coerce")
    out = pd.Series(0.0, index=v.index, dtype="float64")
    out[v == 1] = 1.0
    out[v == 2] = SHARE_ORDER_2
    return out


def pen_estimate(frame: pd.DataFrame) -> pd.Series | None:
    """Per player-match count of penalty *events* taken, or ``None``.

    A whole number, not a fraction of one. ``(gap + PEN_XG -
    PEN_EVENT_MIN_XG) // PEN_XG`` credits a gap of half a penalty or more with
    one penalty, a gap of one-and-a-half with two, and anything smaller with
    none — so a hundredth of xG-model disagreement contributes nothing at all
    instead of contributing a hundredth of a penalty several thousand times
    over.

    ``None`` — not an all-zero series — when either column is absent, so the
    caller can tell "no data" from "no penalties" and decline to build priors
    at all.
    """
    if frame is None or not {"xg", "us_npxg"}.issubset(frame.columns):
        return None
    total = pd.to_numeric(frame["xg"], errors="coerce")
    open_play = pd.to_numeric(frame["us_npxg"], errors="coerce")
    gap = ((total - open_play).where(total.notna() & open_play.notna())
           .clip(lower=0.0).fillna(0.0))
    events = np.floor((gap.to_numpy(dtype="float64")
                       + (PEN_XG - PEN_EVENT_MIN_XG)) / PEN_XG)
    return pd.Series(np.clip(events, 0.0, MAX_PENS_PER_MATCH),
                     index=frame.index, dtype="float64")


def pen_priors(hist: pd.DataFrame | None) -> PenPriors | None:
    """Trailing penalty shares and the league rate, from the training frame.

    ``hist`` is ``load_training_frame()``'s player frame — the one that has
    already been through ``attach_understat``, so it carries ``us_npxg``
    beside FPL's ``xg``.

    ``None`` on anything that would make the answer a fiction: no frame, no
    columns, no estimated penalties at all. Never raises: this feeds a
    prediction-time term and an advice run must not die of it.
    """
    try:
        if hist is None or len(hist) == 0:
            return None
        need = {"code", "team_code", "season_idx", "gw", "opp_code"}
        if not need.issubset(hist.columns):
            return None
        seasons = sorted(pd.to_numeric(hist["season_idx"], errors="coerce")
                         .dropna().unique())[-PEN_SEASONS:]
        window = hist[hist["season_idx"].isin(seasons)]
        pens = pen_estimate(window)
        if pens is None or float(pens.sum()) <= 0.0:
            return None
        frame = pd.DataFrame({
            "code": pd.to_numeric(window["code"], errors="coerce"),
            "team_code": pd.to_numeric(window["team_code"], errors="coerce"),
            "pens": pens.to_numpy()}).dropna(subset=["code", "team_code"])
        by_player = frame.groupby(["code", "team_code"],
                                  as_index=False)["pens"].sum()
        by_team = (frame.groupby("team_code", as_index=False)["pens"].sum()
                   .rename(columns={"pens": "team_pens"}))
        joined = by_player.merge(by_team, on="team_code", how="left")
        joined["share"] = np.where(joined["team_pens"] > 0.0,
                                   joined["pens"] / joined["team_pens"], 0.0)
        # A player who changed clubs mid-window keeps his best club's share
        # rather than an average diluted by a club he no longer plays for.
        share = joined.groupby("code")["share"].max().clip(0.0, 1.0)
        # Only team-games a penalty *could* have been detected in may sit in
        # the denominator, and detection needs both columns: the event count
        # is a gap between FPL's xg and Understat's npxg, so a row missing
        # either one contributes nothing to the numerator and counting it
        # below would divide a real count of events by a fictional number of
        # matches. The rate itself is no longer served (see LEAGUE_PENS_PG) —
        # this only keeps the drift notice honest.
        covered = window[
            pd.to_numeric(window["xg"], errors="coerce").notna()
            & pd.to_numeric(window["us_npxg"], errors="coerce").notna()]
        games = covered[["season_idx", "gw", "team_code",
                         "opp_code"]].drop_duplicates()
        per_game = float(pens.sum()) / max(1, len(games))
        print(f"set pieces: estimated league pens/game {per_game:.3f} from "
              f"events; serving the constant {LEAGUE_PENS_PG}")
        return PenPriors(
            share_hist={int(k): float(v) for k, v in share.items()},
            league_pens_pg=LEAGUE_PENS_PG, team_games=int(len(games)))
    except Exception as exc:  # noqa: BLE001 — never blocks a prediction
        print(f"set pieces: no penalty history ({exc})")
        return None


def attack_multipliers(team_model) -> dict[int, float]:
    """``{team_code: attack strength / league mean}``, clamped.

    Reads ``DixonColesModel.attack_`` (log attack strengths from the fitted
    scoreline model). A ``TeamModel`` has no such attribute and yields ``{}``,
    which every caller reads as a flat multiplier of 1.0 — the degradation
    seam, and the reason this is a ``getattr`` rather than an isinstance.
    """
    attack = getattr(team_model, "attack_", None)
    if not attack:
        return {}
    strengths = {int(c): math.exp(float(a)) for c, a in attack.items()}
    mean = sum(strengths.values()) / len(strengths)
    if not mean > 0.0:
        return {}
    lo, hi = ATTACK_MULT_CLAMP
    return {c: min(max(s / mean, lo), hi) for c, s in strengths.items()}


def pen_table(comp: pd.DataFrame, players: pd.DataFrame,
              priors: PenPriors | None = None,
              attack_mult: dict[int, float] | None = None) -> pd.DataFrame:
    """``[share_now, share_hist, goals, ep]``, aligned to ``comp``'s index.

    ``goals`` is the increment to add to ``e_goals``; it is already rescaled
    so that ``p_play * goals * goal_points`` equals the **clamped** ``ep``
    exactly, which is what makes the clamp mean what it says once
    ``assemble_ep`` has multiplied everything back out.

    Every path that cannot produce a real number produces an all-zero table
    rather than a partial one: no priors, no order column, an order column
    that is entirely null. That is the byte-identical rail.
    """
    zeros = pd.DataFrame({c: pd.Series(0.0, index=comp.index,
                                       dtype="float64") for c in ZERO_COLS})
    if priors is None or len(comp) == 0:
        return zeros
    if players is None or "penalties_order" not in players.columns:
        return zeros
    order_of = dict(zip(players["code"],
                        pd.to_numeric(players["penalties_order"],
                                      errors="coerce")))
    now = share_now(comp["code"].map(order_of))
    now.index = comp.index
    if float(now.abs().sum()) == 0.0:
        return zeros
    hist = (comp["code"].map(priors.share_hist)
            .astype("float64").fillna(0.0))
    lo, hi = ATTACK_MULT_CLAMP
    mult = (comp["team_code"].map(attack_mult or {})
            .astype("float64").fillna(1.0).clip(lo, hi))
    p_play = pd.to_numeric(comp["p_play"], errors="coerce").fillna(0.0)
    goal_pts = comp["position"].map(GOAL_POINTS).astype("float64").fillna(0.0)
    goals = ((now - hist) * priors.league_pens_pg * mult * PEN_CONVERSION)
    raw = goals * goal_pts * p_play
    ep = raw.clip(EP_CLAMP[0], EP_CLAMP[1])
    raw_v = raw.to_numpy(dtype="float64")
    scale = np.where(raw_v != 0.0, ep.to_numpy(dtype="float64")
                     / np.where(raw_v != 0.0, raw_v, 1.0), 0.0)
    return pd.DataFrame({"share_now": now, "share_hist": hist,
                         "goals": goals * scale, "ep": ep})


def set_piece_ep(comp: pd.DataFrame, players: pd.DataFrame,
                 priors: PenPriors | None = None,
                 attack_mult: dict[int, float] | None = None) -> pd.Series:
    """The clamped expected-points term, one value per component row."""
    return pen_table(comp, players, priors, attack_mult)["ep"]


def add_pen_ep(comp: pd.DataFrame, players: pd.DataFrame,
               priors: PenPriors | None = None,
               attack_mult: dict[int, float] | None = None) -> pd.DataFrame:
    """``comp`` with ``ep_pen_taker`` recorded and ``e_goals`` moved.

    The increment lands on ``e_goals`` rather than on ``ep`` directly because
    ``assemble_ep`` is the only place expected points are ever assembled, and
    a second addition site would be a second thing to keep in step with the
    scoring table, the calibration and ``ep_breakdown``.

    When the term is identically zero, ``e_goals`` is not touched at all —
    ``x + 0.0`` is bit-identical for a float, but not for every dtype pandas
    might be holding, and the rail is stated as *column for column*.
    """
    out = comp.copy()
    table = pen_table(out, players, priors, attack_mult)
    out["ep_pen_taker"] = table["ep"].to_numpy(dtype="float64")
    moved = table["goals"].to_numpy(dtype="float64")
    if "e_goals" in out.columns and bool((moved != 0.0).any()):
        out["e_goals"] = (out["e_goals"].to_numpy(dtype="float64") + moved)
    return out


BLEND_MARKER = "e_goals_odds"
"""Column ``blend_attacking_odds`` writes, non-null exactly where it blended.

Read rather than recomputed: "which rows did the market actually price" is a
question only the blend can answer, and rederiving it here from ``lambda_ags``
and ``p_play`` would be a second copy of that rule to keep in step.
"""


def rescale_pen_after_blend(comp: pd.DataFrame, weight: float) -> pd.DataFrame:
    """Restate ``ep_pen_taker`` as what the blend actually delivered.

    :func:`~gaffer.data.odds.blend_attacking_odds` replaces ``e_goals`` with
    ``w * market + (1 - w) * model`` on the rows it priced. The penalty
    increment was folded into the model half before that, so only ``(1 - w)``
    of it survives — deliberately, because the anytime-scorer price already
    contains the taker's penalty duty and adding the full increment on top
    would count the same spot kick twice.

    What was wrong was the *record*, not the arithmetic: ``ep_pen_taker`` went
    on saying it had delivered the whole term while half of it had been
    blended away, so the components file, the why-panel and gate P1's audit
    all read a number nobody's expected points contained. This rescales the
    record to match the delivery.

    An untouched frame — no marker column, no priced rows, no term — comes
    back unchanged, which is the byte-identical no-odds rail.
    """
    if ("ep_pen_taker" not in comp.columns
            or BLEND_MARKER not in comp.columns):
        return comp
    touched = pd.to_numeric(comp[BLEND_MARKER], errors="coerce").notna()
    if not bool(touched.any()):
        return comp
    out = comp.copy()
    kept = 1.0 - float(weight)
    values = out["ep_pen_taker"].to_numpy(dtype="float64").copy()
    values[touched.to_numpy()] *= kept
    out["ep_pen_taker"] = values
    return out


def pen_notices(comp: pd.DataFrame, players: pd.DataFrame,
                priors: PenPriors | None = None,
                attack_mult: dict[int, float] | None = None,
                min_ep: float = NOTICE_MIN_EP) -> list[str]:
    """One line per term worth reading — gate P1's whole instrument.

    Deduplicated by player: a double gameweek prices the term twice, but the
    audit is about *who* the term moved and by how much, and two identical
    lines say nothing the first one did not.
    """
    table = pen_table(comp, players, priors, attack_mult)
    if float(table["ep"].abs().sum()) == 0.0:
        return []
    name_of = dict(zip(players["code"], players["name"])) \
        if "name" in players.columns else {}
    frame = pd.DataFrame({"code": comp["code"].to_numpy(),
                          "ep": table["ep"].to_numpy(),
                          "share_now": table["share_now"].to_numpy(),
                          "share_hist": table["share_hist"].to_numpy()})
    frame = frame[frame["ep"].abs() >= float(min_ep)]
    frame = (frame.reindex(frame["ep"].abs().sort_values(ascending=False)
                           .index).drop_duplicates(subset=["code"]))
    return [f"set pieces: {name_of.get(int(r.code), int(r.code))} "
            f"{r.ep:+.2f} xPts (share now {r.share_now:.2f}, "
            f"history {r.share_hist:.2f})" for r in frame.itertuples()]
