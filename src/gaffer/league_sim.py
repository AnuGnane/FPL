"""The mini-league Monte Carlo: who actually wins this thing.

``league_mode.win_probability`` answers one pairwise question with a fixed
sigma of 18 and a normal approximation: "do I finish above *him*". That is not
the question the league card is asking. Winning a ten-team league is not
beating the leader — it is beating all nine at once, with everyone's squad,
everyone's captain and everyone's transfers in play, and no product of pairwise
normals gets there.

So: simulate the thing. Every entry gets a mean and a standard deviation for
the remaining season, the season is one seeded draw per entry per simulation,
and the answers fall out of counting. What the engine deliberately is *not*:

* not a squad simulator. Rival transfer *prediction* is parked (spec §7); what
  is modelled is drift — over a season a rival's squad converges on the field
  template, and ``rival_drift`` says how far. At 0 nobody transfers at all,
  which is an exactly-checkable degenerate case rather than a rhetorical one.
* not week-correlated. Player noise is independent week to week, the same
  assumption ``optimize.scenarios.noise_ep`` documents and for the same
  reason: minutes risk really is close to independent once the fixture is
  known.
* not part of advice. Nothing here reaches the tilt or the MILP. ``advise.py``
  and ``optimize/**`` are zero-diff this cycle; the sigma table is read
  through ``scenarios``' public names and nothing else (spec D4).

Every published number carries its ``n``, its ``seed`` and its
``rival_drift``, because a probability nobody can reproduce is a decoration.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from gaffer import artifacts
from gaffer.optimize.scenarios import (NOISE_DENOM, NOISE_FLOOR_XMINS,
                                       scenario_noise, sigma_for,
                                       xmins_by_player_gw)

SIM_N = 2000
SIM_SEED = 20260831
"""The router's fixed seed. One seed serves the card so a page refresh does
not reshuffle the headline; the CLI's ``--seeds`` is where the honesty label
comes from (CONVENTIONS.md §1)."""

WEEKLY_SIGMA_FLOOR = 6.0
"""Points of weekly standard deviation no entry falls below.

An entry whose players are all missing from the component frame — a rival on a
squad of new signings, or a league read before the first advise run — would
otherwise have zero variance and a season that is a certainty. Six points is
about a third of the ~18 the old parametric model used for a whole squad, so
it is a floor rather than a second model."""

HAUL_SIGMA = 2.0
"""How many player-sigmas above his mean a "haul" pin puts a player. Two is
the conventional two-sigma event, and it is a *stated* convention rather than
a fitted one — the panel's job is to price a scenario the user names, not to
tell him how likely it was."""

MARGIN_QUANTILES = [0.05, 0.25, 0.5, 0.75, 0.95]
MARGIN_KEYS = ["p05", "p25", "p50", "p75", "p95"]

SIM_HISTORY = "league_sim_history.json"
"""Under ``artifacts.REPORTS``. Read at call time, not bound at import."""


@dataclass
class Entry:
    """One manager in the race, with the squad he last played."""

    entry: int
    name: str
    total: int
    picks: list[dict] = field(default_factory=list)
    is_me: bool = False


@dataclass
class SimInputs:
    """Everything the simulation needs, and nothing that fetches anything.

    ``ep_by_element`` and ``sigma_by_element`` are *per gameweek* — a player's
    expected points and estimation sigma for one week, averaged over whatever
    horizon the component frame covers. ``field_rate`` is the sampled field's
    mean weekly rate under the same numbers, or ``None`` when the field store
    has nothing for this gameweek; drift is then off whatever ``rival_drift``
    says, which is the documented degradation.
    """

    entries: list[Entry]
    ep_by_element: dict[int, float]
    sigma_by_element: dict[int, float]
    weeks_left: int
    field_rate: float | None = None


@dataclass
class Pins:
    """Events pinned into the first simulated week (spec D5).

    ``scores`` maps an element to the points he is *declared* to score that
    week, for every entry that owns him — which is the whole point: a blank
    from a 60%-owned captain is not a blank for me, it is a blank for
    everybody who owns him and a free hit for everybody who does not.
    """

    scores: dict[int, float] = field(default_factory=dict)
    captain_override: int | None = None
    rival_captain_blanks: int | None = None


@dataclass
class LeagueSim:
    """What one seeded run of the league says."""

    p_win: float
    p_top3: float
    exp_finish: float
    per_rival: list[dict]
    margin_quantiles: dict[str, float]
    n: int
    seed: int
    weeks_left: int
    rival_drift: float


def entry_rate(entry: Entry, ep_by: dict[int, float]) -> float:
    """One entry's expected points in one gameweek.

    Multiplier-weighted, so the bench (multiplier 0) contributes nothing and
    the captain contributes twice — which is exactly how FPL scores it, and
    exactly what ``effective_ownership`` already assumes. A pick whose element
    the component frame does not carry contributes nothing rather than raising:
    a rival who bought a player gaffer has never modelled must not take the
    league card down.
    """
    return float(sum(int(p.get("multiplier", 0))
                     * float(ep_by.get(int(p["element"]), 0.0))
                     for p in entry.picks))


def entry_sigma(entry: Entry, sigma_by: dict[int, float]) -> float:
    """One entry's weekly standard deviation, floored.

    Variances add and the captain's points are doubled before they are added,
    so his *variance* enters four times. The floor is
    :data:`WEEKLY_SIGMA_FLOOR` — see its docstring for why zero is not an
    acceptable answer.
    """
    var = sum((int(p.get("multiplier", 0))
               * float(sigma_by.get(int(p["element"]), 0.0))) ** 2
              for p in entry.picks)
    return max(math.sqrt(max(var, 0.0)), WEEKLY_SIGMA_FLOOR)


def _week_one(entry: Entry, ins: SimInputs, pins: Pins) -> tuple[float, float]:
    """``(mean, variance)`` for the first simulated week under ``pins``.

    A pinned player's contribution stops being a random variable: his mean
    becomes the declared score times his multiplier and his variance leaves
    the sum entirely. That is what makes "if Haaland blanks" a *pin* rather
    than a re-weighting — the scenario is asserted, not sampled.
    """
    captain = pins.captain_override
    swap_captain = (entry.is_me and captain is not None
                    and any(int(p["element"]) == int(captain)
                            for p in entry.picks)
                    and any(int(p.get("multiplier", 0)) >= 2
                            for p in entry.picks))
    blank_captain = (not entry.is_me
                     and pins.rival_captain_blanks is not None
                     and int(pins.rival_captain_blanks) == int(entry.entry))
    mean, var = 0.0, 0.0
    for pick in entry.picks:
        element = int(pick["element"])
        mult = int(pick.get("multiplier", 0))
        if swap_captain:
            # One armband, moved: the incumbent drops to a single share and
            # the named player takes the double. A bench player named as
            # captain is not offered by the panel and is not honoured here.
            if element == int(captain):
                mult = 2
            elif mult >= 2:
                mult = 1
        if mult <= 0:
            continue
        if blank_captain and mult >= 2:
            continue          # his armband scored nothing; his XI still plays
        if element in pins.scores:
            mean += mult * float(pins.scores[element])
            continue
        mean += mult * float(ins.ep_by_element.get(element, 0.0))
        var += (mult * float(ins.sigma_by_element.get(element, 0.0))) ** 2
    return mean, var


def _mu_sd(entry: Entry, ins: SimInputs, rival_drift: float,
           pins: Pins) -> tuple[float, float]:
    """The entry's mean and standard deviation over every remaining week.

    Week one is :func:`_week_one` — pinned, and the only week any event can
    reach. Weeks two onward are the entry's plain rate, plus, for a rival with
    a field template to converge on, a linear drift: in week ``w`` his rate is
    ``rate + (field - rate) * drift * w / W``. Summing that closed form rather
    than looping is what keeps a 50-entry league instant.

    My own entry never drifts. The template models *rivals* muddling toward
    the crowd; drifting gaffer's squad toward it would model gaffer as an
    average manager, which is the proposition the whole project disputes.
    """
    weeks = max(int(ins.weeks_left), 0)
    if weeks == 0:
        return 0.0, 0.0
    rate = entry_rate(entry, ins.ep_by_element)
    sd_week = entry_sigma(entry, ins.sigma_by_element)
    mean1, var1 = _week_one(entry, ins, pins)
    rest = weeks - 1
    mu = mean1 + rate * rest
    if (not entry.is_me and rest > 0 and rival_drift > 0.0
            and ins.field_rate is not None):
        # sum over w = 2..W of drift * (field - rate) * w / W
        weight = (weeks * (weeks + 1) / 2.0 - 1.0) / weeks
        mu += rival_drift * (float(ins.field_rate) - rate) * weight
    var = var1 + rest * sd_week ** 2
    return mu, math.sqrt(max(var, 0.0))


def simulate_league(inputs: SimInputs, *, n: int = SIM_N, seed: int = SIM_SEED,
                    rival_drift: float = 0.5,
                    pins: Pins | None = None) -> LeagueSim:
    """``n`` seeded seasons of this league, counted.

    One normal draw per entry per simulation, taken as a single
    ``(n, entries)`` array so the whole run is a handful of numpy calls.
    Deterministic per seed by construction — the generator is created here and
    used once — which is what gate G2 checks and what lets the router cache an
    answer without it changing under the user.

    Ties go to the higher current total, which is FPL's own rule and, when two
    draws land on the same float, the only tie-break available that is not a
    coin.
    """
    pins = pins or Pins()
    entries = list(inputs.entries)
    if not entries:
        return LeagueSim(p_win=0.0, p_top3=0.0, exp_finish=0.0, per_rival=[],
                         margin_quantiles={k: 0.0 for k in MARGIN_KEYS},
                         n=int(n), seed=int(seed),
                         weeks_left=int(inputs.weeks_left),
                         rival_drift=float(rival_drift))
    me = next((i for i, e in enumerate(entries) if e.is_me), 0)
    mus, sds, totals = [], [], []
    for entry in entries:
        mu, sd = _mu_sd(entry, inputs, float(rival_drift), pins)
        mus.append(mu)
        sds.append(sd)
        totals.append(float(entry.total))
    rng = np.random.default_rng(int(seed))
    draws = (np.asarray(totals) + np.asarray(mus)
             + rng.standard_normal((int(n), len(entries)))
             * np.asarray(sds))
    # A hair of the current total breaks exact ties in the leader's favour
    # without moving any real comparison: totals are integers, so 1e-6 of one
    # can never outrank a genuine point.
    scored = draws + np.asarray(totals) * 1e-9
    mine = scored[:, me:me + 1]
    better = (scored > mine).sum(axis=1)
    rank = better + 1
    rivals = [i for i in range(len(entries)) if i != me]
    if rivals:
        best_rival = scored[:, rivals].max(axis=1)
        margin = draws[:, me] - draws[:, rivals].max(axis=1)
    else:
        best_rival = mine[:, 0]
        margin = np.zeros(int(n))
    per_rival = [{"entry": int(entries[i].entry), "name": str(entries[i].name),
                  "p_beat": round(float((mine[:, 0] > scored[:, i]).mean()), 4)}
                 for i in rivals]
    quantiles = np.quantile(margin, MARGIN_QUANTILES)
    return LeagueSim(
        p_win=round(float((rank == 1).mean()), 4),
        p_top3=round(float((rank <= 3).mean()), 4),
        exp_finish=round(float(rank.mean()), 3),
        per_rival=per_rival,
        margin_quantiles={k: round(float(v), 1)
                          for k, v in zip(MARGIN_KEYS, quantiles)},
        n=int(n), seed=int(seed), weeks_left=int(inputs.weeks_left),
        rival_drift=float(rival_drift))


def multi_seed(inputs: SimInputs, seeds: list[int], *, n: int = SIM_N,
               rival_drift: float = 0.5, pins: Pins | None = None) -> dict:
    """The same league under several seed bases, with the spread reported.

    CONVENTIONS.md §1, applied to an instrument rather than to a replay: this
    is a new number and nobody knows yet how much of it is the seed. The
    spread is its published honesty label, printed by ``gaffer league-sim``
    and transcribed into the spec's G2 (spec §5) — there is no pass bar.
    """
    runs = [simulate_league(inputs, n=n, seed=int(s), rival_drift=rival_drift,
                            pins=pins) for s in seeds]
    values = [r.p_win for r in runs]
    return {"seeds": [int(s) for s in seeds], "n": int(n),
            "rival_drift": float(rival_drift), "p_win": values,
            "p_win_mean": round(sum(values) / len(values), 4) if values else 0.0,
            "p_win_spread": round(max(values) - min(values), 4) if values
            else 0.0,
            "p_top3_mean": round(sum(r.p_top3 for r in runs) / len(runs), 4)
            if runs else 0.0,
            "exp_finish_mean": round(sum(r.exp_finish for r in runs)
                                     / len(runs), 3) if runs else 0.0}


def history_path() -> Path:
    return artifacts.REPORTS / SIM_HISTORY


def load_sim_history() -> list[dict]:
    """Every gameweek's headline, oldest first. ``[]`` on any failure."""
    path = history_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text())
    except Exception:  # noqa: BLE001 — a corrupt history is a missing one
        return []
    rows = payload.get("gws") if isinstance(payload, dict) else payload
    return sorted([r for r in (rows or []) if "gw" in r],
                  key=lambda r: int(r["gw"]))


def append_sim_history(sim: LeagueSim, gw: int, run_at: str) -> Path:
    """Bank one gameweek's headline, replacing any earlier row for that week.

    ``pen_tracker.save_tracker``'s atomic single-JSON idiom: a reader sees the
    whole previous file or the whole new one, never the half-written middle.
    Replacement rather than accumulation because a gameweek is re-simulated
    every time the advice changes, and a sparkline of six runs of GW7 is not a
    season.
    """
    rows = [r for r in load_sim_history() if int(r["gw"]) != int(gw)]
    rows.append({"gw": int(gw), "p_win": sim.p_win, "p_top3": sim.p_top3,
                 "exp_finish": sim.exp_finish, "run_at": str(run_at),
                 "n": sim.n, "seed": sim.seed})
    rows.sort(key=lambda r: int(r["gw"]))
    artifacts.REPORTS.mkdir(exist_ok=True)
    path = history_path()
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps({"gws": rows}, indent=1, allow_nan=False))
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def element_sigmas(comp: pd.DataFrame) -> dict[int, float]:
    """``element -> weekly estimation sigma``, from the component frame.

    The scale is the sweep's own: :func:`gaffer.optimize.scenarios.sigma_for`
    over the shipped estimation table, falling back — cell by cell, exactly as
    ``noise_ep`` does — to the pre-v6 multiplicative heuristic
    ``ep * (92 - xmins) / 134``. Both are imported by name; nothing in
    ``optimize/**`` is edited or reached into (spec D4).

    A player with no minutes prediction gets no sigma here, deliberately: "we
    cannot predict his minutes" is not "his minutes are certain", and
    :data:`WEEKLY_SIGMA_FLOOR` catches the entry-level consequence.
    """
    if comp is None or comp.empty or "element" not in comp.columns:
        return {}
    table = scenario_noise()
    xmins = xmins_by_player_gw(comp)
    ep_col = pd.to_numeric(comp["ep"], errors="coerce").fillna(0.0)
    weeks = max(int(pd.to_numeric(comp["gw"], errors="coerce").nunique()), 1)
    totals: dict[int, float] = {}
    for row, ep_value in zip(comp.itertuples(), ep_col):
        element = int(row.element) if not pd.isna(row.element) else None
        if element is None:
            continue
        xm = xmins.get((int(row.code), int(row.gw)))
        if xm is None:
            continue
        sigma = sigma_for(table, float(ep_value), float(xm))
        if sigma is None:
            sigma = float(ep_value) * (NOISE_FLOOR_XMINS - float(xm)) \
                / NOISE_DENOM
        totals[element] = totals.get(element, 0.0) + max(float(sigma), 0.0)
    return {element: value / weeks for element, value in totals.items()}
