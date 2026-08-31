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

What it deliberately omits: *within-squad* correlation. Two players from the
same attack move together, so a real squad's week is a little wider than the
sum of its independent parts.

What it no longer omits is the correlation *between* squads, which was the
larger error by far and pointed the other way — see
:func:`field_exposures` and :data:`MEASURED_FIELD_CORRELATION`."""


MEASURED_FIELD_CORRELATION = 0.68
"""Mean pairwise correlation between two managers' weekly scores.

Measured on the 300-squad GW2 field sample under this module's own sigmas:
0.675 as an exact shared-owner covariance, 0.676 as the rank-one template
approximation :func:`field_exposures` actually simulates. The reviewer's
independent reading of the same sample put it at 0.589; both are the same
finding to a decimal that does not matter, which is that it is not zero and
is not small.

Managers are not independent draws. They own the same players — a template
squad in the top 10k overlaps another by nine or ten of fifteen — so a week
where the popular captain hauls is a good week for almost everybody at once,
and it moves nobody's *rank*. Simulating them as independent inflated every
margin: the mean pairwise weekly margin standard deviation on that sample is
12.0 points, and the independent model produced 22.0 — a fan 1.8x too wide,
which is 1.58x on the reviewer's numbers. A too-wide fan is not a
conservative error. It pushes every probability toward 0.5, understates a
leader's grip and overstates a trailer's chances, and it does so silently.

This constant is documentation, not a parameter: nothing reads it. The
exposures are computed per entry from the banked field sample, so a league of
unusually differentiated squads gets a lower correlation than a league of
template ones, which is the truth about that league rather than about this
number."""

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
    field_weights: dict[int, float] | None = None
    """``element -> the field's mean multiplier on him``
    (:func:`field_weights`), the template each entry's exposure to the shared
    weekly factor is measured against. ``None`` with no banked sample, which
    is the documented degradation to independence — see
    :data:`DEFAULT_FIELD_EXPOSURE`."""
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
    p_win_by_entry: dict[int, float | None] = field(default_factory=dict)
    """``entry id -> P(this manager wins the league)``, counted off the same
    ``scored`` matrix as everything else in this object.

    The panel's projected table used to build this itself, by renormalising
    each rival's ``1 - p_beat`` over the losing mass. That is not a
    probability of winning and it is not close to one: ``p_beat`` is
    *pairwise* — it says nothing about the eight other people the rival also
    has to beat — so a leader whose true win frequency was 0.82 rendered at
    0.45, and the error is largest exactly where the panel is most read.

    ``None`` for an entry whose squad could not be read (:func:`is_readable`).
    Otherwise the values are the win frequencies of one shared run and sum to
    one up to rounding, and :attr:`p_win` is this dict's entry for my own
    manager *by construction* rather than by coincidence."""


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


def is_readable(entry: Entry) -> bool:
    """Did anything at all come back for this manager's squad?

    ``build_inputs`` swallows a 404 on the picks endpoint and files the entry
    with ``picks=[]`` — a private entry, an entry that joined after the
    gameweek being read, an entry the API simply would not serve. That is the
    right degradation for *fetching* and a catastrophic one for *simulating*:
    an empty squad has a rate of zero, is floored at
    :data:`WEEKLY_SIGMA_FLOOR`, and therefore loses every simulated season it
    is entered in. A rival on 400 points would be beaten in 100% of draws and
    the card would say so with a straight face.

    So an unreadable entry is not simulated at all — see
    :func:`simulate_league`, which drops it from the rank and reports its
    ``p_beat`` as ``None`` — and :func:`lookup_notices` names it.
    """
    return bool(effective_picks(entry.picks))


def lookup_notices(entries: list[Entry],
                   ep_by: dict[int, float]) -> list[str]:
    """What the simulation could not look up, said out loud.

    Two different silences, and both used to be one.

    Every EP lookup in this module degrades to zero on a miss, because one
    unmodelled signing must not take the league card down. The failure mode
    that buys is an id-space mismatch — squads keyed by element against a
    frame keyed by code, say — which zeroes *everything* and still renders a
    confident probability. A miss count is the difference between a
    degradation and a lie.

    The other silence is an entry with *no squad at all*
    (:func:`is_readable`). It never reached this function before, because a
    squad of no picks has no picks to miss on: the loop below ran zero times,
    found nothing absent, and returned ``[]``. Counting them here is the half
    of the fix that is visible; dropping them from the rank is the half that
    is arithmetic.
    """
    misses, entries_hit, unknown = 0, 0, set()
    blind = 0
    for entry in entries:
        if not is_readable(entry):
            blind += 1
            continue
        absent = [element for element, _ in effective_picks(entry.picks)
                  if element not in ep_by]
        if absent:
            entries_hit += 1
            misses += len(absent)
            unknown |= set(absent)
    out: list[str] = []
    if blind:
        out.append(f"{blind} {'entry' if blind == 1 else 'entries'}' squads "
                   f"could not be read (private or joined late) — they are "
                   f"left out of the simulated race, not simulated as "
                   f"scoring nothing")
    if misses:
        sample = ", ".join(str(e) for e in sorted(unknown)[:5])
        out.append(f"{misses} picks across {entries_hit} entries name players "
                   f"this gameweek's component frame does not carry (elements "
                   f"{sample}{'...' if len(unknown) > 5 else ''}) — those "
                   f"picks are simulated as scoring nothing")
    return out


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
           pins: Pins) -> tuple[float, float, float]:
    """``(mu, sd_first_week, sd_remaining_weeks)`` over the season left.

    Two standard deviations rather than one because week one is pinnable and
    the rest are not, and because the shared factor of :func:`simulate_league`
    has to load on each block separately: a pin removes variance from week one
    only, and that removal must come out of the shared and idiosyncratic parts
    together. ``sqrt(sd_1 ** 2 + sd_rest ** 2)`` is the season sigma the
    engine used to return whole.

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
        return 0.0, 0.0, 0.0
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
    return mu, math.sqrt(max(var1, 0.0)), sd_week * math.sqrt(rest)


def simulate_league(inputs: SimInputs, *, n: int = SIM_N, seed: int = SIM_SEED,
                    rival_drift: float = 0.5,
                    pins: Pins | None = None) -> LeagueSim:
    """``n`` seeded seasons of this league, counted.

    **The managers are not drawn independently.** Every simulated week has one
    common factor — the field's week, good or bad — and each entry is exposed
    to it in proportion to how much of the field template it owns
    (:func:`field_exposures`). Entry ``i``'s deviation in a week is

    ``c_i * sd_i * F + sqrt(1 - c_i ** 2) * sd_i * E_i``

    with ``F`` shared and ``E_i`` its own, so its *total* variance is
    ``sd_i ** 2`` exactly as before and only the covariance structure changes:
    ``cov(i, j) = c_i c_j sd_i sd_j``. Nothing about any single entry's spread
    moves; what moves is every comparison between two of them, which is the
    only thing this module publishes.

    Two shared draws suffice for a whole season. The sum of ``W - 1``
    independent standard normals is ``sqrt(W - 1)`` times one, so weeks two
    onward collapse into a single shared ``G`` beside week one's ``F1`` —
    which is what keeps a 38-week, 50-entry league four numpy calls wide
    rather than 38 of them.

    With no banked field sample the exposures are
    :data:`DEFAULT_FIELD_EXPOSURE` — zero, independence, the old behaviour —
    and a notice says so.

    Deterministic per seed by construction: one ``SeedSequence`` per entry id
    plus one for the shared stream, so gate G2's reproducibility holds and the
    answer does not depend on the order the standings endpoint listed people
    in.

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
    exposures = field_exposures(entries, inputs.sigma_by_element,
                                inputs.field_weights)
    if not inputs.field_weights:
        notices.append(
            "no field sample is banked, so the managers are simulated as "
            "independent of one another — the real correlation is around "
            "0.68 and the margins below are roughly 1.8x too wide (run "
            "`gaffer field-scrape`)")
    mus, sd1s, sdrs, totals = [], [], [], []
    for entry in entries:
        mu, sd1, sd_rest = _mu_sd(entry, inputs, float(rival_drift), pins)
        mus.append(mu)
        sd1s.append(sd1)
        sdrs.append(sd_rest)
        totals.append(float(entry.total))
    # The field's own week, drawn once per simulation and shared by everybody:
    # ``shared[:, 0]`` is the pinnable first week and ``shared[:, 1]`` stands
    # for the sum of every week after it. Entry ids are 1-based in FPL, so 0
    # is a free key for a stream that belongs to no entry.
    shared = np.random.default_rng([int(seed), 0]).standard_normal((int(n), 2))
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
        own = rng.standard_normal((int(n), 2))
        c = float(exposures.get(int(entry.entry), DEFAULT_FIELD_EXPOSURE))
        idio = math.sqrt(max(1.0 - c * c, 0.0))
        block = c * shared + idio * own
        draws[:, column] = (totals[column] + mus[column]
                            + block[:, 0] * sd1s[column]
                            + block[:, 1] * sdrs[column])
    # A hair of the current total breaks exact ties in the leader's favour
    # without moving any real comparison: totals are integers, so 1e-6 of one
    # can never outrank a genuine point.
    scored = draws + np.asarray(totals) * 1e-9
    mine = scored[:, me:me + 1]
    # An entry whose squad never came back is not a competitor scoring zero;
    # it is a competitor nobody can see. Seeding it at zero and counting it
    # made every rank one place better than it is and every ``p_beat`` exactly
    # 1.0 — a 400-point leader read as private handed the card ``p_win`` 1.0.
    # It stays in the table with a null ``p_beat`` and a notice, and stays out
    # of the arithmetic. My own entry is never dropped: gaffer knows my squad,
    # and a headline about a race I am not in is not a headline.
    live = [i for i, e in enumerate(entries) if i == me or is_readable(e)]
    better = (scored[:, live] > mine).sum(axis=1)
    rank = better + 1
    rivals = [i for i in range(len(entries)) if i != me]
    live_rivals = [i for i in live if i != me]
    if live_rivals:
        # The same ``scored`` matrix the table and the rival rows are counted
        # off, so the fan cannot disagree with the headline about who is
        # ahead: the median margin is negative exactly when the median rank
        # is worse than first.
        margin = mine[:, 0] - scored[:, live_rivals].max(axis=1)
    else:
        margin = np.zeros(int(n))
    per_rival = [{"entry": int(entries[i].entry), "name": str(entries[i].name),
                  "p_beat": (round(float((mine[:, 0] > scored[:, i]).mean()), 4)
                             if i in set(live) else None)}
                 for i in rivals]
    quantiles = np.quantile(margin, MARGIN_QUANTILES)
    # Who actually won each simulated season. ``argmax`` is the stated
    # tie-break convention: the highest-scoring column, and on an exact float
    # tie the leftmost of them. That the tie never fires in practice is the
    # 1e-9 total nudge above — two continuous draws landing on the same double
    # is not a case worth splitting mass over — but the convention is written
    # down rather than left to whichever count happened to be taken first.
    # Counting winners here rather than folding ``p_beat`` is what makes the
    # column sum to one and makes my own row agree with the headline.
    winners = np.asarray(live)[scored[:, live].argmax(axis=1)]
    freq = np.bincount(winners, minlength=len(entries)) / float(n)
    live_set = set(live)
    p_win_by_entry = {int(e.entry): (round(float(freq[i]), 4)
                                     if i in live_set else None)
                      for i, e in enumerate(entries)}
    return LeagueSim(
        p_win=float(p_win_by_entry[int(entries[me].entry)] or 0.0),
        p_top3=round(float((rank <= 3).mean()), 4),
        exp_finish=round(float(rank.mean()), 3),
        per_rival=per_rival,
        margin_quantiles={k: round(float(v), 1)
                          for k, v in zip(MARGIN_KEYS, quantiles)},
        n=int(n), seed=int(seed), weeks_left=int(inputs.weeks_left),
        rival_drift=float(rival_drift), notices=notices,
        p_win_by_entry=p_win_by_entry)


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


DEFAULT_FIELD_EXPOSURE = 0.0
"""The exposure every entry gets when no field sample is banked.

Zero: independence, exactly as the engine behaved before the shared factor
existed. There is a temptation to hard-code something like 0.8 here — the
sample says that is roughly what a template squad's exposure is — but a
constant borrowed from a league we have not looked at is a correlation
asserted rather than measured, and the whole point of the finding is that
this term is large. So the no-sample path keeps the wide fan and *says so*:
the notice names the degradation and the card's provenance line reads
"independence assumed — fan wide". Run ``gaffer field-scrape`` and it goes
away."""


def field_weights(sample: list[list[dict]] | None) -> dict[int, float] | None:
    """``element -> the field's mean multiplier on him``, or ``None``.

    The template squad, written as a portfolio rather than as a list: a player
    started by 62% of the sample and captained by 20% of it carries 0.82. It
    is the same reduction :func:`field_rate_from_sample` takes a scalar out
    of, kept in vector form because :func:`field_exposures` needs the shape.
    """
    if not sample:
        return None
    weights: dict[int, float] = {}
    for squad in sample:
        for element, mult in effective_picks(squad):
            weights[element] = weights.get(element, 0.0) + float(mult)
    n = float(len(sample)) or 1.0
    return {element: value / n for element, value in weights.items()}


def field_exposures(entries: list[Entry], sigma_by: dict[int, float],
                    weights: dict[int, float] | None) -> dict[int, float]:
    """``entry id -> its correlation with the field's week``, in ``[0, 1]``.

    The one number the shared-factor model needs. Treat one gameweek as a
    vector of independent player surprises, each with variance
    ``sigma_e ** 2``. A squad is a weighted sum of them; so is the field
    template (:func:`field_weights`). The correlation between the two is then
    ordinary covariance arithmetic:

    ``c_i = sum_e m_ie f_e sigma_e^2 / (sd_i * sqrt(sum_e f_e^2 sigma_e^2))``

    and that is all this is. No constant is fitted and nothing is tuned: a
    squad built entirely out of template players comes out near 1, a squad of
    genuine differentials comes out low, and the mean of ``c_i c_j`` over the
    GW2 sample is 0.676 against an exact shared-owner correlation of 0.675
    (:data:`MEASURED_FIELD_CORRELATION`). The rank-one approximation is that
    good because there really is one dominant direction — the template — and
    it is why one shared draw per week is enough.

    Why the *template* rather than the exact pairwise covariance: a single
    common factor keeps the simulation one matrix of normals wide instead of a
    Cholesky factorisation per run, and it degrades to a stated scalar when
    there is no sample. The exact matrix would buy the fraction of the
    correlation that is not template-shaped, which the sample says is under a
    percentage point.

    ``sd_i`` here is the *unfloored* quadrature, because
    :data:`WEEKLY_SIGMA_FLOOR` is a guard against a degenerate squad and not a
    description of one; dividing by it would report a template squad of
    unknown players as uncorrelated with the template.
    """
    if not weights:
        return {int(e.entry): DEFAULT_FIELD_EXPOSURE for e in entries}
    var_field = sum(w ** 2 * float(sigma_by.get(element, 0.0)) ** 2
                    for element, w in weights.items())
    if var_field <= 0.0:
        return {int(e.entry): DEFAULT_FIELD_EXPOSURE for e in entries}
    out: dict[int, float] = {}
    for entry in entries:
        picks = effective_picks(entry.picks)
        var = sum((mult * float(sigma_by.get(element, 0.0))) ** 2
                  for element, mult in picks)
        cov = sum(mult * float(weights.get(element, 0.0))
                  * float(sigma_by.get(element, 0.0)) ** 2
                  for element, mult in picks)
        if var <= 0.0:
            out[int(entry.entry)] = DEFAULT_FIELD_EXPOSURE
            continue
        out[int(entry.entry)] = min(
            1.0, max(0.0, cov / math.sqrt(var * var_field)))
    return out


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
                     field_weights=field_weights(sample),
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
