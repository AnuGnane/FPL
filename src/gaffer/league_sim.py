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
from gaffer.data.field import load_field_sample
from gaffer.errors import GafferError
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

OUTCOME_VAR_PER_EP = 3.2
"""Points of *outcome* variance per point of expected points, per player-week.

The number the simulation was missing. ``optimize.scenarios``' table prices
**estimation** σ — how far gaffer's own forecast moves when the ensemble is
reseeded — and ``calibrate_noise.composite_table`` says out loud what that
scale is: "cell 0_0 = 0.018 over 62% of the rows". That is the right quantity
for "would this transfer survive my forecast being wrong" and the wrong one
for "how does this manager's season come out", where what varies is football.
Fed to the league card unaccompanied it put all fifty entries of league
1794743 on :data:`WEEKLY_SIGMA_FLOOR`, made every entry's spread identical,
and turned a Monte Carlo into long division: ``p_beat`` came back as exactly
0.0 and exactly 1.0 and ``p_win`` as exactly 0.0.

Measured, not asserted. Over the last three seasons of
``data/history/player_gw.parquet``, taking each player-season's own mean as
his rate and the deviations from it as his week, ``Var / mean`` is flat in
the rate:

======================  ======  ======
mean points per GW      Var/μ   n
======================  ======  ======
0-1                     2.67    23588
1-2                     3.23    15962
2-3                     3.22    10833
3-4                     3.42     6893
4-5                     3.42     2177
5+                      4.07      646
======================  ======  ======

3.2 is the mass-weighted middle of that. A mean-proportional variance is also
the shape the underlying counts have — goals and assists are near-Poisson and
carry most of the spread — so this is a one-parameter fit to a form the game
already has, not a curve chosen to fit.

What it deliberately omits: *correlation*. Two players from the same attack,
or a captain doubling a haul, move together, so a real squad's week is a
little wider than the sum of its independent parts. The consequence is a
simulation that is slightly over-confident, in a module that publishes its n
and its seed and whose floor is still there."""

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
    expected points and the standard deviation of what he actually scores in
    one week (:func:`element_sigmas`), averaged over whatever horizon the
    component frame covers. ``field_rate`` is the sampled field's
    mean weekly rate under the same numbers, or ``None`` when the field store
    has nothing for this gameweek; drift is then off whatever ``rival_drift``
    says, which is the documented degradation.
    """

    entries: list[Entry]
    ep_by_element: dict[int, float]
    sigma_by_element: dict[int, float]
    weeks_left: int
    field_rate: float | None = None
    notices: list[str] = field(default_factory=list)
    """Degradations the caller should print rather than swallow — see
    :func:`lookup_notices`. A lookup that misses returns zero points, which is
    a perfectly confident answer to the wrong question; the notice is what
    stops a silent id-space mismatch from rendering as a headline."""


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
    notices: list[str] = field(default_factory=list)


XI_SIZE = 11
"""Picks at a higher ``position`` than this are the bench."""


def effective_picks(picks: list[dict]) -> list[tuple[int, int]]:
    """``(element, multiplier)`` as an *ordinary* week would score this squad.

    A stored snapshot is one week of history, and a week in which a chip was
    played does not describe the manager's ability in any other week. The
    entry API returns the chip's arithmetic literally: a bench-boost week
    carries ``multiplier`` 1 on all fifteen picks, a triple-captain week
    carries 3 on the armband. Read as a *rate*, the first hands a rival four
    extra players for the whole rest of the season and the second hands him a
    permanent third captain — which is exactly what happened to the six
    bench-boosters in league 1794743, whose weekly rates came out 9 to 13
    points high and whose ``p_beat`` came out at 0.0.

    So the multipliers are rebuilt from the thing that is not a chip: the
    ``position`` field, which is 1-11 for the eleven who started and 12-15 for
    the bench in every snapshot, chip or no chip. Starters score once, the
    bench scores nothing, and one armband doubles. The armband goes to the
    captain when he started and to the vice when he did not, which is FPL's
    own rule and stops a benched captain from doubling points nobody scored.

    Snapshots with no ``position`` at all — older fixtures, a hand-built field
    sample — have nothing to normalise against, so their stored multipliers
    stand, capped at 2 so a triple captain is still not permanent.
    """
    rows = [(int(p["element"]), int(p.get("multiplier", 0) or 0),
             p.get("position"), bool(p.get("is_captain")),
             bool(p.get("is_vice_captain")))
            for p in picks]
    if any(position is None for _, _, position, _, _ in rows):
        return [(element, min(mult, 2)) for element, mult, _, _, _ in rows
                if mult > 0]
    starters = [r for r in rows if int(r[2]) <= XI_SIZE]
    armband = next((r for r in starters if r[3]), None)
    if armband is None:
        armband = next((r for r in starters if r[4]), None)
    if armband is None:
        # No flags in the snapshot: the doubled pick is the armband, and if
        # none of the eleven is doubled the squad simply has no captain.
        armband = next((r for r in starters if r[1] >= 2), None)
    return [(r[0], 2 if r is armband else 1) for r in starters]


def entry_rate(entry: Entry, ep_by: dict[int, float]) -> float:
    """One entry's expected points in one gameweek.

    Multiplier-weighted through :func:`effective_picks`, so the bench
    contributes nothing and the captain contributes twice — which is exactly
    how FPL scores an ordinary week, and exactly what ``effective_ownership``
    already assumes. A pick whose element the component frame does not carry
    contributes nothing rather than raising: a rival who bought a player
    gaffer has never modelled must not take the league card down. That it is
    silent here is why :func:`lookup_notices` exists.
    """
    return float(sum(mult * float(ep_by.get(element, 0.0))
                     for element, mult in effective_picks(entry.picks)))


def entry_sigma(entry: Entry, sigma_by: dict[int, float]) -> float:
    """One entry's weekly standard deviation, floored.

    Variances add and the captain's points are doubled before they are added,
    so his *variance* enters four times. The floor is
    :data:`WEEKLY_SIGMA_FLOOR` — see its docstring for why zero is not an
    acceptable answer.
    """
    var = sum((mult * float(sigma_by.get(element, 0.0))) ** 2
              for element, mult in effective_picks(entry.picks))
    return max(math.sqrt(max(var, 0.0)), WEEKLY_SIGMA_FLOOR)


def lookup_notices(entries: list[Entry],
                   ep_by: dict[int, float]) -> list[str]:
    """What the simulation could not look up, said out loud.

    Every EP lookup in this module degrades to zero on a miss, because one
    unmodelled signing must not take the league card down. The failure mode
    that buys is an id-space mismatch — squads keyed by element against a
    frame keyed by code, say — which zeroes *everything* and still renders a
    confident probability. A miss count is the difference between a
    degradation and a lie.
    """
    misses, entries_hit, unknown = 0, 0, set()
    for entry in entries:
        absent = [element for element, _ in effective_picks(entry.picks)
                  if element not in ep_by]
        if absent:
            entries_hit += 1
            misses += len(absent)
            unknown |= set(absent)
    if not misses:
        return []
    sample = ", ".join(str(e) for e in sorted(unknown)[:5])
    return [f"{misses} picks across {entries_hit} entries name players this "
            f"gameweek's component frame does not carry (elements {sample}"
            f"{'...' if len(unknown) > 5 else ''}) — those picks are "
            f"simulated as scoring nothing"]


def _week_one(entry: Entry, ins: SimInputs, pins: Pins) -> tuple[float, float]:
    """``(mean, variance)`` for the first simulated week under ``pins``.

    A pinned player's contribution stops being a random variable: his mean
    becomes the declared score times his multiplier and his variance leaves
    the sum entirely. That is what makes "if Haaland blanks" a *pin* rather
    than a re-weighting — the scenario is asserted, not sampled.
    """
    captain = pins.captain_override
    picks = effective_picks(entry.picks)
    swap_captain = (entry.is_me and captain is not None
                    and any(element == int(captain) for element, _ in picks)
                    and any(mult >= 2 for _, mult in picks))
    blank_captain = (not entry.is_me
                     and pins.rival_captain_blanks is not None
                     and int(pins.rival_captain_blanks) == int(entry.entry))
    mean, var = 0.0, 0.0
    for element, mult in picks:
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
                         rival_drift=float(rival_drift),
                         notices=list(inputs.notices))
    # ``build_inputs`` already banked these; a hand-built ``SimInputs`` (a
    # test, the what-if panel's re-run) has not. Deduped rather than
    # recomputed-or-not so both paths report the same list once.
    notices = list(dict.fromkeys(
        list(inputs.notices)
        + lookup_notices(entries, inputs.ep_by_element)))
    me = next((i for i, e in enumerate(entries) if e.is_me), None)
    if me is None:
        # Falling back to entry zero answers a confident question about
        # somebody else's season, which is worse than answering none.
        notices.append(
            "no entry in this league is flagged as your entry — the headline "
            "is the first entry in the standings, not yours")
        me = 0
    mus, sds, totals = [], [], []
    for entry in entries:
        mu, sd = _mu_sd(entry, inputs, float(rival_drift), pins)
        mus.append(mu)
        sds.append(sd)
        totals.append(float(entry.total))
    # One stream per *entry*, keyed on the entry id rather than on the column
    # it happens to occupy. A single ``(n, entries)`` matrix is one call
    # instead of fifty, but it hands column j whatever the standings endpoint
    # put in row j — and that endpoint's order is not stable: two reads of
    # league 1794743 a minute apart swapped two entries on equal totals and
    # moved p_win from 0.212 to 0.189 on the *same seed*. A seed that only
    # reproduces when the API agrees with itself is not the honesty label
    # this module says it is. ``[seed, entry]`` is a SeedSequence, so the
    # streams are independent by construction rather than by offset.
    draws = np.empty((int(n), len(entries)))
    for column, entry in enumerate(entries):
        rng = np.random.default_rng([int(seed), int(entry.entry)])
        draws[:, column] = (totals[column] + mus[column]
                            + rng.standard_normal(int(n)) * sds[column])
    # A hair of the current total breaks exact ties in the leader's favour
    # without moving any real comparison: totals are integers, so 1e-6 of one
    # can never outrank a genuine point.
    scored = draws + np.asarray(totals) * 1e-9
    mine = scored[:, me:me + 1]
    better = (scored > mine).sum(axis=1)
    rank = better + 1
    rivals = [i for i in range(len(entries)) if i != me]
    if rivals:
        # The same ``scored`` matrix the table and the rival rows are counted
        # off, so the fan cannot disagree with the headline about who is
        # ahead: the median margin is negative exactly when the median rank
        # is worse than first.
        margin = mine[:, 0] - scored[:, rivals].max(axis=1)
    else:
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
        rival_drift=float(rival_drift), notices=notices)


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
    """``element -> the weekly standard deviation of his actual score``.

    Two variances, added because they are variances of independent things —
    the same quadrature ``calibrate_noise.composite_table`` argues for, and
    for the same reason:

    * **Outcome.** :data:`OUTCOME_VAR_PER_EP` times his expected points. This
      is football: whether the goal goes in, whether the clean sheet holds,
      who takes the bonus. It is the term that was missing, and it is the one
      that matters — it is an order of magnitude larger than the other.
    * **Estimation.** :func:`gaffer.optimize.scenarios.sigma_for` over the
      shipped table, falling back cell by cell, exactly as ``noise_ep`` does,
      to the pre-v6 heuristic ``ep * (92 - xmins) / 134``. Both are imported
      by name; nothing in ``optimize/**`` is edited or reached into (spec D4).
      This is how far gaffer's own forecast of him moves, which is a real but
      small part of how far *he* moves.

    A player with no minutes prediction loses only the estimation term. He
    keeps the outcome term, because "we cannot predict his minutes" has never
    meant "his score is settled" — dropping him entirely, as this used to,
    handed him zero variance and left :data:`WEEKLY_SIGMA_FLOOR` to paper over
    it at the entry level.

    Per *gameweek*, like :func:`element_eps`: variances are summed within a
    week — a double gameweek really is two fixtures' worth of noise — and
    averaged over the weeks the frame covers.
    """
    if comp is None or comp.empty or "element" not in comp.columns:
        return {}
    table = scenario_noise()
    xmins = xmins_by_player_gw(comp)
    ep_col = pd.to_numeric(comp["ep"], errors="coerce").fillna(0.0)
    weeks = max(int(pd.to_numeric(comp["gw"], errors="coerce").nunique()), 1)
    est_var: dict[int, float] = {}
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
        est_var[element] = (est_var.get(element, 0.0)
                            + max(float(sigma), 0.0) ** 2)
    out: dict[int, float] = {}
    for element, ep_value in element_eps(comp).items():
        var = (OUTCOME_VAR_PER_EP * max(float(ep_value), 0.0)
               + est_var.get(element, 0.0) / weeks)
        out[element] = math.sqrt(max(var, 0.0))
    return out


SEASON_GWS = 38
"""Gameweeks in a season. The remaining-weeks count is ``38 - gw + 1``: the
gameweek being planned is still to be played."""


def element_eps(comp: pd.DataFrame) -> dict[int, float]:
    """``element -> expected points per gameweek`` over the horizon.

    The *mean* over the distinct gameweeks the frame covers, not the sum: a
    three-week horizon would otherwise read as a squad three times as good,
    and the simulation multiplies this by the weeks left itself. A double
    gameweek stays doubled, because two fixtures in one week really are twice
    the points in that week.
    """
    if comp is None or comp.empty or "element" not in comp.columns:
        return {}
    frame = pd.DataFrame({
        "element": pd.to_numeric(comp["element"], errors="coerce"),
        "gw": pd.to_numeric(comp["gw"], errors="coerce"),
        "ep": pd.to_numeric(comp["ep"], errors="coerce").fillna(0.0)})
    frame = frame.dropna(subset=["element", "gw"])
    if frame.empty:
        return {}
    weeks = max(int(frame["gw"].nunique()), 1)
    grouped = frame.groupby("element", as_index=False)["ep"].sum()
    return {int(r.element): float(r.ep) / weeks for r in grouped.itertuples()}


def field_rate_from_sample(sample: list[list[dict]] | None,
                           ep_by: dict[int, float]) -> float | None:
    """The sampled field's mean weekly rate, or ``None`` with no sample.

    The template a drifting rival converges on: what the average top-10k
    manager's squad is worth per week under gaffer's own expected points. That
    it is scored with *our* EP and not with theirs is the point — the question
    is "how much better than the crowd is this squad, by the only yardstick we
    have".

    ``None`` rather than 0.0 for an absent or empty sample: zero would tell
    every rival to converge on a squad that scores nothing, which is not a
    degradation of the model but an inversion of it.
    """
    if not sample:
        return None
    rates = [sum(mult * float(ep_by.get(element, 0.0))
                 for element, mult in effective_picks(squad))
             for squad in sample]
    return float(sum(rates) / len(rates)) if rates else None


def build_inputs(cfg, client, *, gw: int | None = None) -> SimInputs:
    """Assemble a :class:`SimInputs` from artifacts on disk plus fresh league
    data.

    Reads only what ``advise`` already wrote — the component frame for EP and
    sigma — and fetches only what is not an artifact: standings, and each
    entry's squad from the last *scored* gameweek (picks are 404 before a
    deadline, the same rule ``league.py::_last_scored_gw`` follows). Nothing
    is re-solved and nothing is re-trained: spec D4's whole point is that the
    MC is a reader.

    The field template comes from the banked sample for that same scored
    gameweek; when there is none — a fresh clone, a week the scrape missed —
    it is ``None`` and drift is off however the config is set. That is the
    documented degradation and one of G3's rails.
    """
    if not getattr(cfg, "league_id", 0):
        raise GafferError(
            "set fpl.league_id in config.toml to use the league simulation")
    plan_gw = int(gw) if gw is not None else artifacts.latest_gw()
    if plan_gw is None:
        raise GafferError("no saved advice — run `gaffer advise` first")
    comp = artifacts.load_components(plan_gw)
    ep_by = element_eps(comp)
    sigma_by = element_sigmas(comp)
    squad_gw = max(1, int(plan_gw) - 1)

    rows, page = [], 1
    while True:
        data = client.get_league_standings(cfg.league_id, page)
        rows.extend(data["standings"]["results"])
        if not data["standings"].get("has_next") or len(rows) >= 50:
            break
        page += 1
    # No re-sort: the standings endpoint already returns the league in its own
    # order, and re-ranking it here would quietly disagree with the table the
    # user is looking at whenever the API's tie-break is not "total, desc".

    entries: list[Entry] = []
    for row in rows:
        entry_id = int(row["entry"])
        try:
            picks = list(client.get_entry_picks(entry_id, squad_gw)["picks"])
        except Exception:  # noqa: BLE001 — joined late / private / 404
            picks = []      # still in the league, simply unmodellable
        entries.append(Entry(entry=entry_id, name=str(row["entry_name"]),
                             total=int(row["total"]), picks=picks,
                             is_me=entry_id == int(cfg.entry_id)))

    sample = load_field_sample(str(getattr(cfg, "current_season", "") or ""),
                               squad_gw)
    return SimInputs(entries=entries, ep_by_element=ep_by,
                     sigma_by_element=sigma_by,
                     weeks_left=max(0, SEASON_GWS - int(plan_gw) + 1),
                     field_rate=field_rate_from_sample(sample, ep_by),
                     notices=lookup_notices(entries, ep_by))


def format_multi_seed(report: dict, league_id: int) -> str:
    """The printed multi-seed table. One line per seed, then the aggregate."""
    lines = [f"League simulation — league {league_id}, "
             f"n={report['n']} per seed, drift={report['rival_drift']}",
             f"{'seed':>10}  {'P(win)':>8}"]
    for seed, value in zip(report["seeds"], report["p_win"]):
        lines.append(f"{'seed ' + str(seed):>10}  {value:>8.3f}")
    lines.append(f"{'mean':>10}  {report['p_win_mean']:>8.3f}   "
                 f"spread {report['p_win_spread']:.3f}")
    lines.append(f"{'P(top 3)':>10}  {report['p_top3_mean']:>8.3f}   "
                 f"expected finish {report['exp_finish_mean']:.2f}")
    lines.append("")
    lines.append("The spread is this instrument's honesty label, not a "
                 "verdict: it says how much of the headline is the seed. "
                 "There is no pass bar (spec §5, G2).")
    return "\n".join(lines)
