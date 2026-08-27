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
penalties. The gap between them is a penalty, priced at :data:`PEN_XG`. Two
different xG models disagree by a few hundredths on open play, so the raw gap
is noisy — which is why it is only ever used as a **ratio** of the club's own
total, where a systematic offset largely cancels, and why a negative gap is
floored at zero rather than being read as a negative penalty.

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
"""

ATTACK_MULT_CLAMP = (0.6, 1.6)
"""Bound on a club's attack strength relative to the league mean."""

LEAGUE_PENS_PG_BOUNDS = (0.05, 0.35)
"""Plausible range for league penalties per team-game.

The real number is around 0.13 (roughly 100 penalties across 760 team-games).
An estimate outside this range means the xG-gap estimator has gone wrong —
a season with no Understat coverage, say — and the fallback is used instead.
"""

LEAGUE_PENS_PG_FALLBACK = 0.13

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
    league_pens_pg: float = LEAGUE_PENS_PG_FALLBACK
    team_games: int = 0


def share_now(order) -> pd.Series:
    """Bootstrap queue position -> share of his club's penalties, today."""
    v = pd.to_numeric(pd.Series(order), errors="coerce")
    out = pd.Series(0.0, index=v.index, dtype="float64")
    out[v == 1] = 1.0
    out[v == 2] = SHARE_ORDER_2
    return out


def pen_estimate(frame: pd.DataFrame) -> pd.Series | None:
    """Per player-match estimate of penalties taken, or ``None``.

    ``None`` — not an all-zero series — when either column is absent, so the
    caller can tell "no data" from "no penalties" and decline to build priors
    at all.
    """
    if frame is None or not {"xg", "us_npxg"}.issubset(frame.columns):
        return None
    total = pd.to_numeric(frame["xg"], errors="coerce")
    open_play = pd.to_numeric(frame["us_npxg"], errors="coerce")
    gap = (total - open_play).where(total.notna() & open_play.notna())
    return (gap / PEN_XG).clip(lower=0.0,
                               upper=MAX_PENS_PER_MATCH).fillna(0.0)


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
        games = window[["season_idx", "gw", "team_code",
                        "opp_code"]].drop_duplicates()
        per_game = float(pens.sum()) / max(1, len(games))
        if not (LEAGUE_PENS_PG_BOUNDS[0] <= per_game
                <= LEAGUE_PENS_PG_BOUNDS[1]):
            print(f"set pieces: league penalty rate {per_game:.3f}/game is "
                  f"outside {LEAGUE_PENS_PG_BOUNDS} — using "
                  f"{LEAGUE_PENS_PG_FALLBACK}")
            per_game = LEAGUE_PENS_PG_FALLBACK
        return PenPriors(
            share_hist={int(k): float(v) for k, v in share.items()},
            league_pens_pg=float(per_game), team_games=int(len(games)))
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
