# Gaffer v8g Honest Uncertainty Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** show the model's uncertainty the way a forecaster would. Four things the tool cannot do today — say how wide a point estimate is, say how often its probability heads have been right, say what its own record entitles it to claim, and compare two players on more than one axis at a time.

**Architecture:** a read-and-render cycle. One new serve-side module (`src/gaffer/uncertainty.py`) turns the scenario sweep's own σ table into a displayed band and two tail probabilities; one more (`src/gaffer/confidence.py`) turns the v8b decision ledger into a sentence with counts in it; one more (`src/gaffer/misses.py`) joins the banked components against banked results. Nothing trains, nothing solves, nothing writes a new store, no config key, no new job kind. Every number rides an existing payload additively, and every card is absent — not zeroed — when its input is absent.

**Tech Stack:** Python 3.12, uv, pandas/pyarrow, FastAPI + pydantic, pytest; React 19 + TypeScript + vitest + recharts 2.15.

**Prerequisite:** work on branch `feat/gaffer-v8g`. Authoritative spec: `docs/superpowers/specs/2026-08-31-gaffer-v8g-honest-uncertainty-design.md`. Measurement rules: `docs/superpowers/CONVENTIONS.md`.

**Protected — must show zero diffs at the end (Task 10 audits this):**
`src/gaffer/advise.py`, `src/gaffer/set_pieces.py`, `src/gaffer/optimize/**`,
`src/gaffer/web/jobs.py`, `src/gaffer/web/routers/jobs.py`,
`src/gaffer/web/routers/whatif.py`,
`tests/test_advise.py`, `tests/test_odds.py`, `tests/test_web_jobs.py`,
every pre-v8g `tests/test_*_degradation.py` (v6, v7*, v8a, v8b, v8c, v8d, v8e),
`scripts/s2_replay.py`.

**Import-only:** `src/gaffer/journal.py`, `src/gaffer/backtest.py`, and the whole of `src/gaffer/optimize/` — this cycle imports exactly four names from `optimize.scenarios` (`sigma_for`, `scenario_noise`, `recentred_mean`, `xmins_by_player_gw`) plus two constants (`NOISE_FLOOR_XMINS`, `NOISE_DENOM`), which are the same names `advise.py` and `sensitivity.py` already import. `set_pieces.py` is protected and is **read only for its exports** — nothing in this cycle imports from it (A8 explains why the radar's set-piece axis reads the bootstrap queue orders instead).

If a task appears to need an edit inside a protected or import-only file, the plan is wrong: stop and report rather than editing.

**No protected edit this cycle.** v8g adds **zero** job kinds. The count pin stays at **10** in all four places that assert it (`tests/test_web_job_kinds_v8b.py:16`, `tests/test_v8b_degradation.py:214`, `tests/test_v8c_degradation.py:193`, `tests/test_v8d_degradation.py:176`, `tests/test_v8e_degradation.py:188`) and Task 8's rail asserts the same number a sixth time. If a task finds itself wanting a job kind, the plan is wrong: stop and report.

**Staging rule:** every `git add` below names exact files. Never `git add -A`. Never stage `data/`, `reports/`, `models/`, `logs/`, `.claude/` or `config.toml`. v8g commits no data asset.

**Gate rule (CONVENTIONS.md §7):** implementers build the driver and never run the gates. Task 10 is the checklist, unfilled.

**Suite baselines:** 2325 python tests; 406 frontend tests + 1 skipped, across 58 files. Every task's final run must leave the pre-existing suites green.

**Commit trailer — every commit:**

```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
```

---

## Ambiguities the spec left open, and how this plan settles them

Ten things the spec does not pin, decided here once so no task has to decide them twice.

**A1 — which distribution the band and the two tail probabilities come from.** Not a normal centred on the headline EP. The distribution is exactly the one `optimize.scenarios.noise_ep` draws from, centre included: `X = max(0, mu + σ·Z)`, where on the calibrated path `σ = sigma_for(table, ep, xmins)` and `mu = recentred_mean(ep, σ)`, and on the heuristic path `mu = ep` and `σ = ep · (92 − xmins) / 134`. The recentring matters and is the reason the band cannot be drawn from `ep ± zσ` by hand: the calibrated σ is *absolute*, so on a low-EP player the clip at zero is a one-way ratchet, and `noise_ep` shifts the mean down to compensate. A band drawn around `ep` while the sweep draws around `mu` would be a picture of a distribution the optimizer does not use — which is the exact dishonesty this cycle exists to remove.

Consequence to state rather than discover: `ep_lo`/`ep_hi` are the p25/p75 of `X`, and `(ep_lo + ep_hi) / 2` is therefore **not** the headline EP on the calibrated path. That is correct and it is what "the model's own noise model implies" means. The UI labels the pair "p25–p75", never "±".

`p_haul = P(X ≥ 10) = 1 − Φ((10 − mu)/σ)` and `p_blank = P(X ≤ 2) = Φ((2 − mu)/σ)`. The atom at zero falls inside the blank tail automatically, since `2 > 0`. Both are labelled crude in the UI: they price a *forecast-error* distribution, not football's own variance, so `p_haul` is systematically low for a nailed-on premium and the tooltip says so.

**A2 — what a band is keyed on.** `(code, gw)`, never `(code, fixture)`. That is `noise_ep`'s key and `xmins_by_player_gw`'s key, and a double gameweek is one answer to "how uncertain is he this week", not two. `ComponentPlayer.ep` is a *horizon* sum (the components parquet carries every gameweek in the solve horizon), so a band around it would bracket a number no cell of the σ table ever saw. `ComponentPlayer` therefore also gains `ep_gw` — the requested gameweek's EP alone — and that is the number the band brackets. Additive, so nothing that reads `ep` changes.

**A3 — a player with no minutes model gets no band at all.** `null`, not a band of width zero. `noise_ep` passes a cell with no xMins entry through untouched on exactly this reasoning — "we have no minutes prediction for him" is not the claim "his minutes are certain" — and a σ of 0.0 rendered as a band would make the least-known player in the pool look like the most certain. Every one of the six payload fields is nullable and the UI prints an em dash.

**A4 — where the explorer's xMins comes from, and why its band is recomputed rather than reused.** `/api/players` builds `ep_next` from the **solve state pool**'s `ep_raw`, while `/api/components/{gw}` builds its EP from the components parquet. They are the same quantity by construction but they are two reads, and a band must bracket the number on the screen. So `routers/players.py` takes xMins from `xmins_by_player_gw(load_components(state.gw))` and calls `band_for` on the *pool's* `ep_next` — not on the components' `ep`, and not by looking a band up out of the components map. A missing or unreadable components parquet blanks the four columns and never 500s: the explorer has to render on a clone that has only ever run a solve.

**A5 — the confidence tiers, and the sign of `delta_pts`.** `review._lane` scores "my choice minus the model's", so a captaincy lane with `delta_pts < 0` is a week the model's captain **beat** mine, `> 0` is a week mine beat the model's, and `aligned` weeks are neither (I made the model's own pick). Three tiers over the gradeable count `n` — lanes where `delta_pts is not None`:

- `n < 4` → **early**: "Too early to grade — the model's captain has been comparable to yours in {n} of {reviewed} reviewed gameweeks."
- `n ≥ 4` and `wins > losses` → **backed**: "The model's captain outscored yours in {wins} of {n} comparable gameweeks ({aligned} you agreed on)."
- `n ≥ 4` otherwise → **mixed**, same counts, plus "— it has not earned the armband yet."

Four is the bar because three graded weeks cannot separate a real edge from a coin. No percentages anywhere: the tiers quote counts, which is the whole point of D3. The ledger currently holds one reviewed gameweek, so gate G1 exercises the **early** branch for real.

**A6 — what σ the sensitivity card's honesty line compares the margin against.** Not a σ on a whole plan, which the table cannot price. The margin separates two *signatures*, and two signatures differ in a handful of named players, so the relevant noise is the noise on those players: `decision_sigma = sqrt(Σ σᵢ²)` over the symmetric difference of `modal.buys ∪ modal.sells ∪ {modal.captain}` and the same set for `runner_up`, each σᵢ from A1's distribution at that player's first-horizon-gameweek EP and xMins. In quadrature because the sweep draws each cell independently — `noise_ep` takes one standard normal per cell and adds no cross-player correlation. `None` when there is no runner-up, no components file, or an empty difference; the card then prints its existing margin line unchanged.

**A7 — which gameweek "biggest misses" is about.** The largest gameweek that has **both** a components parquet and played rows in `data/live/player_gw.parquet`. Not `latest_gw()`, which is normally the *upcoming* week and has no results at all; not "the last finished gameweek", which may predate the oldest components file on a fresh clone. The intersection is computable from two globs and one column, it is empty on a clone that has never ingested results, and an empty intersection is an absent card.

**A8 — what the radar's five axes read, and why none of them is a new endpoint.** ComparePanel already fetches `/api/components/{gw}` and `/api/fixtures/matrix`, and already receives `PlayerRow[]`. Every axis falls out of those three:

| Axis | Source | Raw value |
| --- | --- | --- |
| Attacking | components | `(Goals + Assists) / ep` over the requested gameweek's fixtures |
| Minutes security | components | `fixtures[0].minutes.p_play` |
| Set pieces | `PlayerRow` | `penalties_order`/`free_kicks_order`/`corners_order`, scored 1.0 / 0.6 / 0.4 for first choice, half that for second, summed and capped at 1 |
| Fixtures | fixture matrix | `1 − mean(next 3 cells)`, reading `defence` for GKP/DEF and `attack` for MID/FWD |
| Form | `PlayerRow` | `mean(last4)` |

`set_pieces.py` is protected and is not imported: its `share_now` is a *penalty* share fitted for the EP term, whereas this axis is a three-duty summary that no model consumes. Duplicating a scoring rule the model does not use is cheaper and safer than reaching into a protected module for one that means something else.

**A9 — what the axes are normalized against.** The explorer's currently-filtered rows, passed down as a new optional `pool` prop from `Players.tsx` (`rows ?? []`). Not the selected two-to-four, which would make every comparison read 0 vs 100; not a server-side league-wide percentile, which is a new endpoint the spec forbids. Each axis is min-maxed over the pool to 0–100, a degenerate pool (one row, or every value equal) maps to 50 rather than to a divide-by-zero, and the caption states the normalization verbatim — "0–100 against the {n} players currently listed in Explorer" — because a normalized axis with an unstated denominator is a number pretending to be a fact. With no pool prop at all the radar normalizes against the selected players and says so.

**A10 — the calibration cards extend the existing Quality tab rather than replacing it.** `QualityTab.tsx` already draws a "Calibration" card with reliability curves for `p_play`, `p60` and `cs`. v8g does three things to it and adds two cards: `p_start` joins the `HEADS` list (it has been in `evaluate_current`'s payload since v8a and nothing rendered it), each curve gains the y=x perfect-calibration reference line it has always been missing and a bin-count line under it, and the scatter and misses arrive as new self-fetching sections on `PensSection`'s pattern — their own `apiGet`, their own empty state, so one missing artifact cannot blank the other's card.

---

## File structure

| File | Status | Responsibility |
| --- | --- | --- |
| `src/gaffer/uncertainty.py` | Create | T1: the distribution, the band, the two tails. |
| `tests/test_uncertainty.py` | Create | T1. |
| `src/gaffer/web/schemas.py` | Modify (`PlayerRow` L365-400, `ComponentPlayer` L552-565, `SensitivityReport` L1143-1158, append) | T2/T3/T4. |
| `src/gaffer/web/routers/components.py` | Modify (imports L20-23, body L108-144) | T2: bands on `ComponentPlayer`. |
| `src/gaffer/web/routers/players.py` | Modify (imports L15-19, `players` L103-164) | T2: bands on `PlayerRow`. |
| `tests/test_web_uncertainty.py` | Create | T2. |
| `src/gaffer/confidence.py` | Create | T3: the ledger-derived tiers. |
| `tests/test_confidence.py` | Create | T3. |
| `src/gaffer/web/routers/confidence.py` | Create | T3: `GET /api/confidence`. |
| `src/gaffer/web/routers/sensitivity.py` | Modify (L14-46) | T3: `decision_sigma`. |
| `src/gaffer/web/app.py` | Modify (L26-29 import, L67-84 includes) | T3/T4: two new routers. |
| `tests/test_web_confidence.py` | Create | T3. |
| `src/gaffer/misses.py` | Create | T4: the components-vs-results join. |
| `tests/test_misses.py` | Create | T4. |
| `src/gaffer/web/routers/misses.py` | Create | T4: `GET /api/misses`. |
| `tests/test_web_misses.py` | Create | T4. |
| `frontend/src/types.ts` | Modify (L179-200, L412-427, L516-523, L977-990, append) | T5/T6/T7. |
| `frontend/src/hubs/model/QualityTab.tsx` | Modify | T5: p_start, the diagonal, scatter, misses. |
| `frontend/src/hubs/model/QualityTab.test.tsx` | Modify | T5. |
| `frontend/src/hubs/this-week/SquadTable.tsx` | Modify | T6: the range column and the two chips. |
| `frontend/src/hubs/this-week/SquadTable.test.tsx` | Modify | T6. |
| `frontend/src/hubs/this-week/ConfidenceLine.tsx` | Create | T6. |
| `frontend/src/hubs/this-week/ConfidenceLine.test.tsx` | Create | T6. |
| `frontend/src/hubs/ThisWeek.tsx` | Modify (L99-131, L188-208) | T6. |
| `frontend/src/hubs/Players.tsx` | Modify (L65-120, L217) | T6/T7: range column, pool prop. |
| `frontend/src/hubs/planning/SensitivityCard.tsx` | Modify (L22-31) | T6: the σ honesty line. |
| `frontend/src/hubs/players/CompareRadar.tsx` | Create | T7. |
| `frontend/src/hubs/players/CompareRadar.test.tsx` | Create | T7. |
| `frontend/src/hubs/players/ComparePanel.tsx` | Modify | T6/T7: bands in the card, the radar. |
| `frontend/src/hubs/players/ComparePanel.test.tsx` | Modify | T6/T7. |
| `tests/test_v8g_degradation.py` | Create | T8: G2. |
| `README.md` | Modify | T9. |

---

## Task 1 — the distribution the sweep already draws from

**Files:**
- Create `src/gaffer/uncertainty.py`
- Create `tests/test_uncertainty.py`

- [ ] **Write the failing test.** Create `tests/test_uncertainty.py`:

```python
"""EP bands: the scenario sweep's own noise model, read out instead of drawn.

The whole risk in this module is inventing a second noise model by accident.
Every test here is really the same test — that what the band says is what
``noise_ep`` would do — asked from a different angle: the calibrated path with
its recentred mean, the heuristic path without one, the absent asset, the
player with no minutes model, and the two tail probabilities that have to be
read off the *same* distribution as the band rather than off the headline EP.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

import gaffer.optimize.scenarios as sc
from gaffer.uncertainty import (BAND_Z, BLANK_POINTS, HAUL_POINTS, Band,
                                band_for, bands_by_player_gw, shipped_table,
                                xmins_by_player_gw)

TABLE = {"ep_edges": [0.0, 2.0, 4.0, 6.0], "xmins_edges": [0.0, 30.0, 60.0],
         "sigma": {"2_2": 1.5}, "ep_marginal": {"2": 2.0}, "global": 3.0}


def test_no_xmins_is_no_band_at_all(monkeypatch):
    """A3. ``noise_ep`` passes such a cell through untouched, and a zero-width
    band would draw the least-known player as the most certain one."""
    assert band_for(5.0, None, table=TABLE) is None


@pytest.mark.parametrize("xmins", [float("nan"), "nonsense", None])
def test_an_unusable_xmins_is_no_band(xmins):
    assert band_for(5.0, xmins, table=TABLE) is None


def test_a_zero_ep_player_has_no_spread(monkeypatch):
    """``noise_ep`` leaves an EP of zero at zero: every clipped draw round it
    is non-negative, so any noise would invent points."""
    band = band_for(0.0, 80.0, table=TABLE)
    assert band == Band(sigma=0.0, ep_lo=0.0, ep_hi=0.0, p_haul=0.0,
                        p_blank=1.0)


def test_the_calibrated_band_is_centred_on_the_recentred_mean(monkeypatch):
    """A1: the sweep draws round ``recentred_mean``, not round ``ep``, so the
    band has to as well — otherwise it pictures a distribution nothing uses."""
    ep, xmins = 5.0, 80.0
    band = band_for(ep, xmins, table=TABLE)
    sigma = sc.sigma_for(TABLE, ep, xmins)
    mu = sc.recentred_mean(ep, sigma)
    assert band.sigma == pytest.approx(round(sigma, 3))
    assert band.ep_lo == pytest.approx(round(mu - BAND_Z * sigma, 2))
    assert band.ep_hi == pytest.approx(round(mu + BAND_Z * sigma, 2))
    # And that is not the same as a band round the headline: the whole reason
    # the pair is labelled p25-p75 rather than "plus or minus".
    assert band.ep_lo + band.ep_hi != pytest.approx(2 * ep)


def test_the_heuristic_band_is_centred_on_the_ep(monkeypatch):
    """The heuristic scale is multiplicative and vanishes with the EP it is
    applied to, so ``noise_ep`` does not recentre it and neither does this."""
    ep, xmins = 5.0, 80.0
    band = band_for(ep, xmins, table=None)
    sigma = ep * (sc.NOISE_FLOOR_XMINS - xmins) / sc.NOISE_DENOM
    assert band.sigma == pytest.approx(round(sigma, 3))
    assert band.ep_lo + band.ep_hi == pytest.approx(2 * ep, abs=0.01)


def test_no_asset_is_the_heuristic_value_for_value(monkeypatch):
    """The asset-optionality rail, at this module's front door: a clone with
    no scenario_noise.json must produce the pre-v6 scale exactly."""
    monkeypatch.setattr("gaffer.uncertainty.scenario_noise", lambda: None)
    ep, xmins = 4.0, 20.0
    band = band_for(ep, xmins)
    want = ep * (sc.NOISE_FLOOR_XMINS - xmins) / sc.NOISE_DENOM
    assert band.sigma == pytest.approx(round(want, 3))


def test_a_nailed_on_starter_is_narrower_than_a_rotation_risk():
    """The claim the squad table makes visually, asserted as arithmetic."""
    nailed = band_for(5.0, 88.0, table=None)
    rotated = band_for(5.0, 30.0, table=None)
    assert nailed.ep_hi - nailed.ep_lo < rotated.ep_hi - rotated.ep_lo


def test_the_band_never_goes_below_zero():
    """A negative floor on an expected-points band is not a worse player, it
    is an incoherent one."""
    band = band_for(0.4, 5.0, table=None)
    assert band.ep_lo == 0.0


def test_the_tails_are_read_off_the_same_distribution_as_the_band():
    ep, xmins = 6.0, 80.0
    band = band_for(ep, xmins, table=TABLE)
    sigma = sc.sigma_for(TABLE, ep, xmins)
    mu = sc.recentred_mean(ep, sigma)
    cdf = lambda z: 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))  # noqa: E731
    assert band.p_haul == pytest.approx(
        round(1.0 - cdf((HAUL_POINTS - mu) / sigma), 4))
    assert band.p_blank == pytest.approx(
        round(cdf((BLANK_POINTS - mu) / sigma), 4))


def test_a_premium_hauls_more_often_than_a_defender():
    premium = band_for(8.0, 88.0, table=None)
    defender = band_for(3.5, 88.0, table=None)
    assert premium.p_haul > defender.p_haul
    assert premium.p_blank < defender.p_blank


def test_a_degenerate_sigma_answers_in_certainties():
    """σ of exactly zero is not a division to attempt: the distribution is a
    point mass and the two tails are 1 or 0 by inspection."""
    band = band_for(12.0, sc.NOISE_FLOOR_XMINS, table=None)
    assert band.sigma == 0.0
    assert band.p_haul == 1.0 and band.p_blank == 0.0


# --- the frame helper --------------------------------------------------

COMP = pd.DataFrame([
    {"code": 11, "gw": 5, "ep": 3.0, "p_play": 0.95, "p60": 0.9},
    {"code": 11, "gw": 5, "ep": 2.5, "p_play": 0.95, "p60": 0.9},
    {"code": 11, "gw": 6, "ep": 4.0, "p_play": 0.95, "p60": 0.9},
    {"code": 22, "gw": 5, "ep": 1.0, "p_play": 0.30, "p60": 0.2},
])


def test_a_double_gameweek_sums_its_ep_and_averages_its_xmins():
    """``xmins_by_player_gw``'s rule, which this must not contradict: xMins is
    a nailedness score and a nailed-on starter with two fixtures is exactly as
    nailed on as one with a single fixture."""
    bands = bands_by_player_gw(COMP, table=None)
    xm = xmins_by_player_gw(COMP)
    assert bands[(11, 5)] == band_for(5.5, xm[(11, 5)], table=None)
    assert (11, 6) in bands and (22, 5) in bands


def test_a_frame_with_no_minutes_model_bands_nothing():
    frame = COMP.drop(columns=["p_play", "p60"])
    assert bands_by_player_gw(frame, table=None) == {}


@pytest.mark.parametrize("frame", [
    pd.DataFrame(), pd.DataFrame({"code": [1]}), None])
def test_an_unusable_frame_bands_nothing(frame):
    assert bands_by_player_gw(frame, table=None) == {}


def test_the_shipped_table_is_the_one_the_sweep_serves(monkeypatch):
    """One seam, so a rail that pins the sweep's asset also pins the band's."""
    monkeypatch.setattr("gaffer.uncertainty.scenario_noise", lambda: TABLE)
    assert shipped_table() is TABLE


def test_the_band_agrees_with_a_million_draws_of_noise_ep():
    """The end-to-end claim, checked against the thing itself rather than
    against the formula that produced it. A Monte Carlo of ``noise_ep`` must
    land inside a couple of hundredths of the quantiles this module reports —
    if it does not, the two have drifted apart and the band is a fiction."""
    ep, xmins = 5.0, 55.0
    band = band_for(ep, xmins, table=TABLE)
    rng = np.random.default_rng(11)
    draws = np.array([sc.noise_ep({(1, 1): ep}, {(1, 1): xmins}, rng,
                                  table=TABLE)[(1, 1)]
                      for _ in range(20000)])
    assert np.quantile(draws, 0.25) == pytest.approx(band.ep_lo, abs=0.05)
    assert np.quantile(draws, 0.75) == pytest.approx(band.ep_hi, abs=0.05)
    assert (draws >= HAUL_POINTS).mean() == pytest.approx(band.p_haul,
                                                          abs=0.02)
    assert (draws <= BLANK_POINTS).mean() == pytest.approx(band.p_blank,
                                                           abs=0.02)
```

Run it: `uv run pytest -q tests/test_uncertainty.py` — expect `ModuleNotFoundError`.

- [ ] **Implement.** Create `src/gaffer/uncertainty.py`:

```python
"""EP bands and haul/blank probabilities: the sweep's noise model, displayed.

The optimizer has always had an opinion about how wrong each of its numbers
is — the scenario sweep perturbs every EP cell by its own σ and re-solves
forty times, and that σ is the difference between a transfer that survives
thirty-eight of those worlds and one that survives twelve. Until now the
opinion was consumed and thrown away: the sweep printed a move frequency, and
the number on the squad table was still a bare point estimate with no width.

This module reads the same σ out and shows it. Nothing here is a new model,
and that constraint is the whole design. The distribution is not "a normal
around the EP" — it is literally the one :func:`gaffer.optimize.scenarios.
noise_ep` draws from, ``max(0, mu + σ·Z)``, with ``mu`` the recentred mean on
the calibrated path and the EP itself on the heuristic one. A band drawn any
other way would picture a distribution the optimizer does not use, which is
exactly the dishonesty the feature exists to remove.

Two consequences worth stating rather than discovering.

The band is **not symmetric about the headline EP** on the calibrated path.
The calibrated σ is absolute, so the clip at zero pushes only upward, and
``recentred_mean`` shifts the centre down so the clipped draw still averages
the forecast. That is why every label in the UI reads "p25-p75" and never
"plus or minus".

``p_haul`` and ``p_blank`` are **crude and labelled crude**. They price
forecast error, not football: the σ table says how much the model's own
estimate moves, not how much the ball does. A nailed-on premium's real haul
rate is higher than what comes out of here. The number is still worth showing
because it is consistent with what the optimizer assumes, and "what the
model's own noise model implies" is a claim this tool can actually stand
behind.

Serve-time only. Nothing here is a trained feature, nothing is banked, and
nothing writes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from gaffer.optimize.scenarios import (NOISE_DENOM, NOISE_FLOOR_XMINS,
                                       recentred_mean, scenario_noise,
                                       sigma_for, xmins_by_player_gw)

__all__ = ["BAND_Z", "BLANK_POINTS", "HAUL_POINTS", "Band", "band_for",
           "bands_by_player_gw", "shipped_table", "xmins_by_player_gw"]

BAND_Z = 0.6744897501960817
"""The standard normal's 75th percentile: the half-width of an interquartile
range in units of σ.

p25-p75 rather than a 90% interval on purpose. A quartile band is a claim
about the ordinary week — half the time he lands inside it — which is the
question a manager picking a captain is actually asking. A 90% band on a
rotation risk spans nearly the whole plausible range and tells nobody
anything.
"""

HAUL_POINTS = 10.0
"""What counts as a haul. The community's number, and the one the evaluation's
own return categories already use."""

BLANK_POINTS = 2.0
"""What counts as a blank: an appearance and nothing else. Not zero — a player
who came on and did nothing has blanked from a manager's point of view, and
distinguishing him from an unused substitute is the minutes model's job, not
this one's."""

_SQRT_2 = math.sqrt(2.0)

_SHIPPED = object()
"""Sentinel for "resolve the shipped asset yourself".

:func:`band_for` cannot use ``None`` for this the way ``noise_ep`` does,
because ``None`` is also the perfectly ordinary answer "there is no table,
use the heuristic" — and a caller that has already resolved the asset once
for a whole pool must be able to pass that answer down without every player
re-entering the loader.
"""


def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / _SQRT_2))


@dataclass(frozen=True)
class Band:
    """One player-gameweek's spread, as the sweep would draw it.

    ``ep_lo``/``ep_hi`` are quantiles, not a symmetric interval — see the
    module docstring. ``sigma`` travels with them so a caller can say how wide
    the uncertainty is without re-deriving it, and so gate G1 can spot-check
    that a boom-bust attacker carries a larger one than a keeper at equal EP.
    """

    sigma: float
    ep_lo: float
    ep_hi: float
    p_haul: float
    p_blank: float


def shipped_table() -> dict | None:
    """The σ table the scenario sweep serves, or ``None`` for the heuristic.

    One seam, so a rail that pins the sweep's asset optionality also pins this
    module's. Cached by :func:`gaffer.optimize.scenarios.scenario_noise`, so
    calling it once per request rather than once per player is a courtesy
    rather than a necessity — but a pool is several thousand rows and the
    lookup through the cache is not free.
    """
    return scenario_noise()


def _moments(ep: float, xmins: float,
             table: dict | None) -> tuple[float, float]:
    """``(mu, sigma)`` of the clipped normal ``noise_ep`` draws for this cell.

    The branch is `noise_ep`'s branch, in the same order and on the same
    condition, because the two must never disagree about which scale applies
    to a given player.
    """
    sigma = sigma_for(table, ep, xmins)
    if sigma is None:
        # The pre-v6 heuristic: multiplicative, vanishing with the EP it is
        # applied to, and so needing no recentring.
        return ep, ep * (NOISE_FLOOR_XMINS - xmins) / NOISE_DENOM
    return recentred_mean(ep, sigma), float(sigma)


def band_for(ep, xmins, table=_SHIPPED) -> Band | None:
    """One player-gameweek's band, or ``None`` when there is nothing to say.

    ``None`` for a player with no xMins — no minutes model, or a frame that
    never carried one. That is not a band of width zero: ``noise_ep`` passes
    such a cell through untouched precisely because "we have no minutes
    prediction for him" is a different claim from "his minutes are certain",
    and a zero-width band would draw the least-known player in the pool as the
    most certain one on the page.

    ``table`` omitted means "resolve the shipped asset"; ``table=None`` means
    "use the heuristic" and is how a caller pins the degraded arm. Pass a
    resolved table to price a whole pool off one load.
    """
    if table is _SHIPPED:
        table = shipped_table()
    if xmins is None:
        return None
    try:
        value, xm = float(ep), float(xmins)
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or math.isnan(xm):
        return None
    if value <= 0.0:
        # An EP of zero has no spread to report and no haul to price. Blank is
        # a certainty rather than a probability, and saying so is more use
        # than an em dash.
        return Band(sigma=0.0, ep_lo=0.0, ep_hi=0.0, p_haul=0.0, p_blank=1.0)

    xm = min(max(xm, 0.0), NOISE_FLOOR_XMINS)
    mu, sigma = _moments(value, xm, table)
    if not sigma > 0.0:
        # A genuinely nailed-on 90-plus-minute starter under the heuristic.
        # The distribution is a point mass, and dividing by it is neither
        # necessary nor possible.
        point = max(0.0, mu)
        return Band(sigma=0.0, ep_lo=round(point, 2), ep_hi=round(point, 2),
                    p_haul=1.0 if point >= HAUL_POINTS else 0.0,
                    p_blank=1.0 if point <= BLANK_POINTS else 0.0)
    return Band(
        sigma=round(sigma, 3),
        ep_lo=round(max(0.0, mu - BAND_Z * sigma), 2),
        ep_hi=round(mu + BAND_Z * sigma, 2),
        p_haul=round(1.0 - _norm_cdf((HAUL_POINTS - mu) / sigma), 4),
        p_blank=round(_norm_cdf((BLANK_POINTS - mu) / sigma), 4))


def bands_by_player_gw(comp: pd.DataFrame | None,
                       table=_SHIPPED) -> dict[tuple[int, int], Band]:
    """``{(code, gw): Band}`` for a component frame.

    Keyed on ``(code, gw)`` and not on ``(code, fixture)``: that is
    ``noise_ep``'s key and ``xmins_by_player_gw``'s key, and a double
    gameweek is one answer to "how uncertain is he this week" rather than two.
    EP is therefore **summed** across a double's fixtures while xMins is
    averaged — his EP really does double, so his absolute noise doubles with
    it, but he is exactly as nailed on either way.

    ``{}`` for anything unusable: no frame, no ``ep``, no minutes model. An
    empty map is a page with no bands on it, which is the correct degraded
    render.
    """
    if comp is None or not isinstance(comp, pd.DataFrame) or comp.empty:
        return {}
    if not {"code", "gw", "ep"}.issubset(comp.columns):
        return {}
    xmins = xmins_by_player_gw(comp)
    if not xmins:
        return {}
    if table is _SHIPPED:
        table = shipped_table()

    frame = pd.DataFrame({
        "code": comp["code"].astype(int), "gw": comp["gw"].astype(int),
        "ep": pd.to_numeric(comp["ep"], errors="coerce").fillna(0.0)})
    totals = frame.groupby(["code", "gw"], as_index=False)["ep"].sum()

    out: dict[tuple[int, int], Band] = {}
    for row in totals.itertuples():
        key = (int(row.code), int(row.gw))
        band = band_for(float(row.ep), xmins.get(key), table=table)
        if band is not None:
            out[key] = band
    return out
```

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_uncertainty.py tests/test_v6_degradation.py
```

- [ ] **Commit.**

```bash
git add src/gaffer/uncertainty.py tests/test_uncertainty.py && git commit -m "$(cat <<'EOF'
feat: EP bands from the scenario sweep's own noise model

Not a new distribution — literally the one noise_ep draws from, recentred
mean included, read out as p25/p75 plus P(haul) and P(blank).

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 2 — the bands ride the two payloads that carry an EP

**Files:**
- Modify `src/gaffer/web/schemas.py`
- Modify `src/gaffer/web/routers/components.py`
- Modify `src/gaffer/web/routers/players.py`
- Create `tests/test_web_uncertainty.py`

- [ ] **Write the failing test.** Create `tests/test_web_uncertainty.py`:

```python
"""Bands on the two payloads that already carry an expected-points number.

Additive, in the strict sense: every field these endpoints served before must
come back byte-identical, and the new ones must be *absent* rather than zero
whenever their input is. The second half of that is the part worth testing —
a band of 0.0-0.0 on a player the minutes model has never seen is a stronger
and more wrong claim than no band at all.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import SolveState, save_components, save_solve_state
from gaffer.web.app import create_app

GW = 5

COMPONENTS = pd.DataFrame([
    {"code": 11, "element": 1, "name": "Saka", "position": "MID",
     "team_code": 3, "team_name": "Arsenal", "gw": GW, "opp_code": 4,
     "opp_name": "City", "was_home": 1.0, "kickoff_time": "2026-09-01T14:00",
     "p_play": 0.95, "p60": 0.9, "ep": 5.0, "ep_goals": 2.0,
     "ep_assists": 1.0, "ep_minutes": 2.0},
    {"code": 11, "element": 1, "name": "Saka", "position": "MID",
     "team_code": 3, "team_name": "Arsenal", "gw": GW + 1, "opp_code": 5,
     "opp_name": "Spurs", "was_home": 0.0, "kickoff_time": "2026-09-08T14:00",
     "p_play": 0.95, "p60": 0.9, "ep": 4.0, "ep_goals": 1.5,
     "ep_assists": 0.5, "ep_minutes": 2.0},
    {"code": 22, "element": 2, "name": "Sub", "position": "FWD",
     "team_code": 4, "team_name": "City", "gw": GW, "opp_code": 3,
     "opp_name": "Arsenal", "was_home": 0.0,
     "kickoff_time": "2026-09-01T14:00", "p_play": 0.25, "p60": 0.1,
     "ep": 1.2, "ep_goals": 0.8, "ep_minutes": 0.4},
])

PLAYERS = pd.DataFrame({
    "code": [11, 22], "element": [1, 2], "name": ["Saka", "Sub"],
    "position": ["MID", "FWD"], "team_id": [1, 2], "team_code": [3, 4],
    "now_cost": [100, 60], "status": ["a", "a"], "news": ["", ""],
    "chance_of_playing": [None, None], "selected_by_percent": [40.0, 2.0],
    "form": [5.0, 1.0], "points_per_game": [5.0, 1.0],
    "ep_next": [5.0, 1.2], "price_change_percent": [0.0, 0.0],
    "price_change_calibrating": [False, False],
    "penalties_order": [1.0, None], "direct_freekicks_order": [None, None],
    "corners_and_indirect_freekicks_order": [1.0, None]})

TEAMS = pd.DataFrame({"code": [3, 4], "id": [1, 2],
                      "name": ["Arsenal", "City"],
                      "short_name": ["ARS", "MCI"]})

POOL = pd.DataFrame([
    {"code": 11, "name": "Saka", "position": "MID", "team_code": 3,
     "cost": 100, "sell": 100, "owned": True, "gw": GW, "ep_raw": 5.0},
    {"code": 11, "name": "Saka", "position": "MID", "team_code": 3,
     "cost": 100, "sell": 100, "owned": True, "gw": GW + 1, "ep_raw": 4.0},
    {"code": 22, "name": "Sub", "position": "FWD", "team_code": 4,
     "cost": 60, "sell": 60, "owned": False, "gw": GW, "ep_raw": 1.2},
])


def _state() -> SolveState:
    return SolveState(
        gw=GW, gws=[GW, GW + 1], deadline="2026-09-01T11:00:00Z",
        generated_at="2026-08-31T09:00:00Z", mode="weekly", bank=0,
        free_transfers=1, owned_codes=[11], lam=0.0, league_eo={},
        avail_by_gw={GW: [], GW + 1: []},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.0, "horizon": 2, "hit_cost": 4,
             "max_transfers": 2, "bank_weight": 0.0},
        pool=POOL)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    TEAMS.to_parquet(tmp_path / "data/live/teams.parquet", index=False)
    (tmp_path / "reports").mkdir()
    save_components(COMPONENTS, GW)
    save_solve_state(_state())
    return TestClient(create_app())


def _player(body: dict, code: int) -> dict:
    return next(p for p in body["players"] if p["code"] == code)


# --- /api/components/{gw} ---------------------------------------------

def test_the_band_brackets_the_gameweeks_own_ep_not_the_horizon(client):
    """A2: ``ep`` is a horizon sum, so the band is drawn round ``ep_gw``."""
    body = client.get(f"/api/components/{GW}").json()
    saka = _player(body, 11)
    assert saka["ep"] == pytest.approx(9.0)      # 5.0 + 4.0, unchanged
    assert saka["ep_gw"] == pytest.approx(5.0)
    assert saka["ep_lo"] < saka["ep_gw"] < saka["ep_hi"]


def test_a_rotation_risk_carries_a_wider_band_than_a_starter(client):
    body = client.get(f"/api/components/{GW}").json()
    starter, sub = _player(body, 11), _player(body, 22)
    starter_width = starter["ep_hi"] - starter["ep_lo"]
    sub_width = sub["ep_hi"] - sub["ep_lo"]
    # Per point of EP: the sub's EP is smaller, so compare the relative width.
    assert sub_width / sub["ep_gw"] > starter_width / starter["ep_gw"]


def test_the_tails_come_back_as_probabilities(client):
    saka = _player(client.get(f"/api/components/{GW}").json(), 11)
    assert 0.0 <= saka["p_haul"] <= 1.0
    assert 0.0 <= saka["p_blank"] <= 1.0
    assert saka["sigma"] > 0.0


def test_a_frame_with_no_minutes_model_serves_no_bands(client, tmp_path):
    """A3 end to end: nulls, not zeros, and the rest of the payload intact."""
    save_components(COMPONENTS.drop(columns=["p_play", "p60"]), GW)
    saka = _player(client.get(f"/api/components/{GW}").json(), 11)
    assert saka["ep"] == pytest.approx(9.0)
    assert saka["ep_lo"] is None and saka["ep_hi"] is None
    assert saka["p_haul"] is None and saka["p_blank"] is None
    assert saka["sigma"] is None
    # ``ep_gw`` is arithmetic on the frame, not on the noise model, so it
    # survives a frame that carries no minutes at all.
    assert saka["ep_gw"] == pytest.approx(5.0)


def test_the_code_filter_still_narrows_the_payload(client):
    body = client.get(f"/api/components/{GW}?codes=22").json()
    assert [p["code"] for p in body["players"]] == [22]
    assert body["players"][0]["ep_lo"] is not None


# --- /api/players ------------------------------------------------------

def test_the_explorer_bands_the_number_it_shows(client):
    """A4: the band brackets ``ep_next``, which comes from the pool, not from
    the components frame."""
    from gaffer.uncertainty import band_for, xmins_by_player_gw

    rows = client.get("/api/players").json()
    saka = next(r for r in rows if r["code"] == 11)
    want = band_for(saka["ep_next"],
                    xmins_by_player_gw(COMPONENTS)[(11, GW)])
    assert saka["ep_lo"] == pytest.approx(want.ep_lo)
    assert saka["ep_hi"] == pytest.approx(want.ep_hi)
    assert saka["p_haul"] == pytest.approx(want.p_haul)
    assert saka["p_blank"] == pytest.approx(want.p_blank)


def test_a_clone_with_no_components_still_lists_players(client, tmp_path):
    """The explorer has to render on a clone that has only ever solved."""
    (tmp_path / f"reports/components_gw{GW}.parquet").unlink()
    rows = client.get("/api/players").json()
    saka = next(r for r in rows if r["code"] == 11)
    assert saka["ep_next"] == pytest.approx(5.0)
    assert saka["ep_lo"] is None and saka["p_haul"] is None


def test_an_unreadable_components_file_is_a_missing_band_not_a_500(
        client, tmp_path):
    (tmp_path / f"reports/components_gw{GW}.parquet").write_text("garbage")
    response = client.get("/api/players")
    assert response.status_code == 200
    assert all(r["ep_lo"] is None for r in response.json())
```

Run it: expect `KeyError`/`None` mismatches on the new fields.

- [ ] **Widen the schemas.** In `src/gaffer/web/schemas.py`, append to `PlayerRow` (after `last4`, L395-400):

```python
    ep_lo: float | None = None
    """p25 of the noise model's distribution for ``ep_next`` — see
    :mod:`gaffer.uncertainty`. Deliberately **not** ``ep_next`` minus
    something: the calibrated path recentres, so the pair is quartiles rather
    than a symmetric interval, and the UI labels it that way.

    ``None`` — never ``ep_next`` — when the components frame carries no
    minutes model for him, or is absent altogether. A zero-width band on the
    least-known player in the pool would read as certainty."""
    ep_hi: float | None = None
    p_haul: float | None = None
    """``P(points >= 10)`` under the same distribution. Crude by construction:
    it prices *forecast* error, not football's own variance."""
    p_blank: float | None = None
    """``P(points <= 2)`` under the same distribution."""
```

and to `ComponentPlayer` (after `fixtures`, L552-565):

```python
    ep_gw: float | None = None
    """Expected points for the *requested* gameweek alone.

    ``ep`` above is a horizon sum — the components parquet carries every
    gameweek in the solve horizon — so it is not a number the σ table has ever
    seen. The band brackets this one instead (plan A2)."""
    sigma: float | None = None
    """The scenario sweep's own σ for this player-gameweek, in points."""
    ep_lo: float | None = None
    """p25 / p75 of the distribution ``noise_ep`` draws from. ``None``, never
    zero, when the frame carries no minutes model for him."""
    ep_hi: float | None = None
    p_haul: float | None = None
    p_blank: float | None = None
```

- [ ] **Serve them from the components router.** In `src/gaffer/web/routers/components.py`, extend the import block (L20-23):

```python
from gaffer.artifacts import load_components
from gaffer.errors import GafferError
from gaffer.uncertainty import bands_by_player_gw
from gaffer.web.schemas import (Component, ComponentFixture, ComponentPlayer,
                                ComponentsBreakdown, MinutesOutput)
```

Then, immediately after the `codes` filter (L106) and before `players: list[ComponentPlayer] = []`:

```python
    # One resolution of the σ asset for the whole payload rather than one per
    # player: the loader is cached but the lookup through it is not free at
    # pool scale. Keyed (code, gw) because that is the sweep's own key — a
    # double gameweek is one answer to "how uncertain is he this week".
    bands = bands_by_player_gw(frame)
```

and replace the `players.append(...)` block at the tail of the loop (L137-143) with:

```python
        head = rows.iloc[0]
        band = bands.get((int(code), int(gw)))
        players.append(ComponentPlayer(
            code=int(code), name=str(head["name"]),
            position=str(head["position"]),
            team_name=_text(head["team_name"]),
            ep=round(float(sum(f.ep for f in fixtures)), 2),
            # The band brackets the requested gameweek, so the payload has to
            # carry that gameweek's own EP beside the horizon sum above.
            ep_gw=round(float(sum(f.ep for f in fixtures
                                  if f.gw == int(gw))), 2),
            sigma=None if band is None else band.sigma,
            ep_lo=None if band is None else band.ep_lo,
            ep_hi=None if band is None else band.ep_hi,
            p_haul=None if band is None else band.p_haul,
            p_blank=None if band is None else band.p_blank,
            fixtures=fixtures))
```

- [ ] **Serve them from the players router.** In `src/gaffer/web/routers/players.py`, extend the import block (L15-19) with:

```python
from gaffer.uncertainty import band_for, shipped_table, xmins_by_player_gw
```

Add a helper beside `_last4` (after L81):

```python
def _xmins_first_gw(gw: int) -> dict[int, float]:
    """``{code: expected minutes}`` for the horizon's first gameweek.

    Pure display, so an absent or unreadable components parquet is an empty
    map rather than an exception: the explorer must render on a clone that has
    solved but never banked a breakdown, and a player list with no bands on it
    is a correct degraded page.
    """
    try:
        comp = load_components(gw)
    except Exception as exc:  # noqa: BLE001 — a band is never worth a 500
        print(f"players explorer: no component breakdown for bands ({exc})")
        return {}
    try:
        return {code: xm for (code, g), xm in
                xmins_by_player_gw(comp).items() if int(g) == int(gw)}
    except Exception as exc:  # noqa: BLE001
        print(f"players explorer: component breakdown unusable ({exc})")
        return {}
```

In `players()`, after `last4 = _last4()` (L118):

```python
    # A4: the band has to bracket the number on the screen, and the number on
    # the screen is the pool's ep_raw — not the components frame's ep. So the
    # frame supplies only xMins and the band is computed on ep_next.
    xmins = _xmins_first_gw(first_gw)
    noise = shipped_table()
```

and inside the row loop, immediately before `rows.append(PlayerRow(`:

```python
        band = band_for(round(ep_next.get(code, 0.0), 2), xmins.get(code),
                        table=noise)
```

then append to the `PlayerRow(...)` construction, after `last4=last4.get(code, [])`:

```python
            last4=last4.get(code, []),
            ep_lo=None if band is None else band.ep_lo,
            ep_hi=None if band is None else band.ep_hi,
            p_haul=None if band is None else band.p_haul,
            p_blank=None if band is None else band.p_blank))
```

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_web_uncertainty.py tests/test_web_components.py \
  tests/test_web_players.py tests/test_uncertainty.py
```

- [ ] **Commit.**

```bash
git add src/gaffer/web/schemas.py src/gaffer/web/routers/components.py \
  src/gaffer/web/routers/players.py tests/test_web_uncertainty.py \
  && git commit -m "$(cat <<'EOF'
feat: EP bands and haul/blank tails on the components and players payloads

Additive and nullable throughout: no minutes model means no band, not a band
of width zero.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 3 — confidence from the record, and the margin against the noise

**Files:**
- Create `src/gaffer/confidence.py`
- Create `tests/test_confidence.py`
- Create `src/gaffer/web/routers/confidence.py`
- Modify `src/gaffer/web/routers/sensitivity.py`
- Modify `src/gaffer/web/schemas.py`
- Modify `src/gaffer/web/app.py`
- Create `tests/test_web_confidence.py`

- [ ] **Write the failing test.** Create `tests/test_confidence.py`:

```python
"""Confidence framing: prose the ledger entitles the tool to write.

The failure mode this guards is the one every consumer FPL tool has — a
percentage next to a recommendation, computed from nothing. So the tests are
mostly about refusal: with one reviewed gameweek the answer is "too early",
with four it quotes four, and there is no branch anywhere that produces a
number the ledger did not count.
"""

from __future__ import annotations

import pytest

from gaffer.confidence import MIN_GRADED, captain_confidence


def _gw(gw: int, delta: int | None, *, aligned: bool = False) -> dict:
    return {"gw": gw, "lanes": [
        {"lane": "transfers", "delta_pts": 3},
        {"lane": "captaincy", "delta_pts": delta, "aligned": aligned},
    ]}


def test_an_empty_ledger_is_too_early_and_says_zero():
    out = captain_confidence([])
    assert out["tier"] == "early"
    assert out["graded"] == 0 and out["reviewed"] == 0
    assert "0 of 0" in out["text"]


def test_one_reviewed_gameweek_is_still_too_early():
    """The live state as this cycle ships. G1 exercises exactly this."""
    out = captain_confidence([_gw(1, -2)])
    assert out["tier"] == "early"
    assert out["graded"] == 1 and out["reviewed"] == 1
    assert "1 of 1" in out["text"]
    assert "too early" in out["text"].lower()


def test_an_ungraded_lane_counts_as_reviewed_but_not_as_graded():
    """"The model's captain was not in your eleven" is not evidence either
    way, and must not be scored as agreement."""
    ledger = [_gw(1, None), _gw(2, -3), _gw(3, 1), _gw(4, -1), _gw(5, -2)]
    out = captain_confidence(ledger)
    assert out["reviewed"] == 5 and out["graded"] == 4


def test_four_graded_weeks_reaches_a_verdict():
    ledger = [_gw(g, -2) for g in range(1, MIN_GRADED + 1)]
    out = captain_confidence(ledger)
    assert out["tier"] == "backed"
    assert out["wins"] == MIN_GRADED and out["losses"] == 0
    assert f"{MIN_GRADED} of {MIN_GRADED}" in out["text"]


def test_the_sign_convention_is_mine_minus_the_models():
    """``review._lane`` scores my choice minus the model's, so a negative
    delta is a week the model was right and a positive one is a week I was."""
    ledger = [_gw(1, -2), _gw(2, -1), _gw(3, 5), _gw(4, 4)]
    out = captain_confidence(ledger)
    assert out["wins"] == 2 and out["losses"] == 2
    assert out["tier"] == "mixed"
    assert "not earned the armband" in out["text"]


def test_an_aligned_week_is_neither_a_win_nor_a_loss():
    """I picked the model's own captain: there is nothing to compare."""
    ledger = [_gw(1, 0, aligned=True), _gw(2, 0, aligned=True),
              _gw(3, -3), _gw(4, -1)]
    out = captain_confidence(ledger)
    assert out["aligned"] == 2
    assert out["wins"] == 2 and out["losses"] == 0
    assert "2 you agreed on" in out["text"]


def test_a_ledger_row_with_no_captaincy_lane_is_skipped_not_crashed():
    out = captain_confidence([{"gw": 1, "lanes": []}, {"gw": 2}])
    assert out["reviewed"] == 0 and out["tier"] == "early"


def test_junk_in_the_ledger_never_raises():
    """The ledger is a file on disk that a laptop may have died mid-write to,
    and a captain card is not worth a 500."""
    out = captain_confidence(["nonsense", {"lanes": "no"}, None])
    assert out["tier"] == "early" and out["reviewed"] == 0


def test_the_text_never_contains_a_percentage():
    """D3's whole point: tiers quote counts, not manufactured confidence."""
    for ledger in ([], [_gw(1, -1)], [_gw(g, -1) for g in range(1, 9)]):
        assert "%" not in captain_confidence(ledger)["text"]
```

- [ ] **Implement.** Create `src/gaffer/confidence.py`:

```python
"""Confidence framing, derived from the banked record and nothing else.

Every consumer FPL tool prints a confidence number, and none of them can say
where it came from. This module exists so that this one can: the only inputs
are counts out of ``reports/decision_ledger.json``, the only outputs are
sentences containing those counts, and there is no branch anywhere that
manufactures a percentage.

The tiering is deliberately coarse. Three graded gameweeks cannot separate a
real captaincy edge from a coin, so below :data:`MIN_GRADED` the answer is not
a weaker claim, it is a refusal to make one — "too early to grade", with the
count that makes the refusal checkable. Above it the sentence still quotes
counts rather than a rate, because "outscored yours in 5 of 7" is a fact and
"71% confident" is a decoration.

Read-only, never raises, and never a reason for a 500: the ledger is a file a
laptop can die mid-write to, and a captain card is not worth an error page.
"""

from __future__ import annotations

MIN_GRADED = 4
"""Gradeable gameweeks below which the tool declines to have an opinion.

Four rather than three because three weeks of a binary comparison is one draw
short of being able to say anything at all, and one short of the point where
the honest sentence stops being "come back later".
"""

TIERS = ("early", "mixed", "backed")
"""Ascending. ``early`` is a refusal, not a low score."""


def _lane(row, name: str) -> dict | None:
    """One named lane out of one ledger row, or ``None``.

    Defensive at every level because the caller is the web layer and the
    argument came off disk: a row that is not a dict, a ``lanes`` that is not
    a list, a lane that is not a dict.
    """
    if not isinstance(row, dict):
        return None
    lanes = row.get("lanes")
    if not isinstance(lanes, list):
        return None
    for lane in lanes:
        if isinstance(lane, dict) and lane.get("lane") == name:
            return lane
    return None


def captain_confidence(ledger) -> dict:
    """What the ledger entitles the captain card to say.

    ``delta_pts`` on a captaincy lane is *my* points minus the *model's*
    (``review._lane``), so a negative delta is a week the model's armband beat
    mine and a positive one is a week mine beat the model's. An ``aligned``
    week is neither: I picked the model's own captain, so there is nothing to
    compare and counting it as agreement-therefore-success would be scoring
    the tool against itself.

    ``reviewed`` counts gameweeks that carry a captaincy lane at all;
    ``graded`` counts the ones where it was comparable. The gap between them
    is the "the model's captain was not in your eleven" weeks, and it is
    reported rather than hidden — a season of ungraded lanes looks exactly
    like a season of agreement in any summary that collapses the two.
    """
    reviewed = graded = wins = losses = aligned = 0
    for row in ledger or []:
        lane = _lane(row, "captaincy")
        if lane is None:
            continue
        reviewed += 1
        delta = lane.get("delta_pts")
        if delta is None:
            continue
        graded += 1
        if lane.get("aligned"):
            aligned += 1
        elif float(delta) < 0:
            wins += 1
        elif float(delta) > 0:
            losses += 1

    if graded < MIN_GRADED:
        tier = "early"
        text = (f"Too early to grade — the model's captain has been "
                f"comparable to yours in {graded} of {reviewed} reviewed "
                f"gameweeks.")
    else:
        tier = "backed" if wins > losses else "mixed"
        text = (f"The model's captain outscored yours in {wins} of {graded} "
                f"comparable gameweeks ({aligned} you agreed on)")
        text += ("." if tier == "backed"
                 else " — it has not earned the armband yet.")
    return {"tier": tier, "reviewed": reviewed, "graded": graded,
            "wins": wins, "losses": losses, "aligned": aligned, "text": text}
```

- [ ] **Write the endpoint test.** Create `tests/test_web_confidence.py`:

```python
"""``/api/confidence`` and the sensitivity card's noise comparison.

Both are read paths on pages that already work, so neither may ever fail: an
unreviewed season, a corrupt ledger and a clone with no reports directory all
come back as a 200 whose sentence says so.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import SolveState, save_components, save_solve_state
from gaffer.web.app import create_app

GW = 5

COMPONENTS = pd.DataFrame([
    {"code": 11, "element": 1, "name": "Saka", "position": "MID",
     "team_code": 3, "team_name": "Arsenal", "gw": GW, "opp_code": 4,
     "opp_name": "City", "was_home": 1.0, "kickoff_time": None,
     "p_play": 0.95, "p60": 0.9, "ep": 5.0},
    {"code": 22, "element": 2, "name": "Sub", "position": "FWD",
     "team_code": 4, "team_name": "City", "gw": GW, "opp_code": 3,
     "opp_name": "Arsenal", "was_home": 0.0, "kickoff_time": None,
     "p_play": 0.3, "p60": 0.1, "ep": 1.5},
])

POOL = pd.DataFrame([
    {"code": 11, "name": "Saka", "position": "MID", "team_code": 3,
     "cost": 100, "sell": 100, "owned": True, "gw": GW, "ep_raw": 5.0},
    {"code": 22, "name": "Sub", "position": "FWD", "team_code": 4,
     "cost": 60, "sell": 60, "owned": False, "gw": GW, "ep_raw": 1.5},
])

SENSITIVITY = {
    "gw": GW, "k": 40, "completed": 40, "failures": 0, "seed": 7,
    "horizon": 1, "generated_at": "2026-08-31T09:00:00Z", "frequencies": [],
    "modal": {"count": 30, "buys": [{"code": 11, "name": "Saka"}],
              "sells": [], "captain": None, "hits": 0, "value": 60.0},
    "runner_up": {"count": 10, "buys": [{"code": 22, "name": "Sub"}],
                  "sells": [], "captain": None, "hits": 0, "value": 59.4},
    "margin": 0.6, "verdict": "…"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    save_components(COMPONENTS, GW)
    save_solve_state(SolveState(
        gw=GW, gws=[GW], deadline="2026-09-01T11:00:00Z",
        generated_at="2026-08-31T09:00:00Z", mode="weekly", bank=0,
        free_transfers=1, owned_codes=[11], lam=0.0, league_eo={},
        avail_by_gw={GW: []},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.0, "horizon": 1, "hit_cost": 4,
             "max_transfers": 2, "bank_weight": 0.0},
        pool=POOL))
    return TestClient(create_app())


def _ledger(tmp_path, rows):
    (tmp_path / "reports/decision_ledger.json").write_text(
        json.dumps({"gws": rows}))


def test_an_unreviewed_season_is_a_200_saying_so(client):
    body = client.get("/api/confidence").json()
    assert body["captain"]["tier"] == "early"
    assert body["captain"]["graded"] == 0
    assert "too early" in body["captain"]["text"].lower()


def test_a_corrupt_ledger_is_an_unreviewed_one(client, tmp_path):
    (tmp_path / "reports/decision_ledger.json").write_text("{not json")
    assert client.get("/api/confidence").json()["captain"]["tier"] == "early"


def test_a_graded_season_quotes_its_counts(client, tmp_path):
    _ledger(tmp_path, [
        {"gw": g, "lanes": [{"lane": "captaincy", "delta_pts": -2,
                             "aligned": False}]}
        for g in range(1, 6)])
    body = client.get("/api/confidence").json()
    assert body["captain"]["tier"] == "backed"
    assert "5 of 5" in body["captain"]["text"]


# --- the sensitivity noise comparison ---------------------------------

def test_the_report_carries_the_noise_on_the_players_that_separate_the_plans(
        client, tmp_path):
    """A6: quadrature over the symmetric difference, from the same σ the
    bands use."""
    import math

    from gaffer.uncertainty import band_for, xmins_by_player_gw

    (tmp_path / f"reports/sensitivity_gw{GW}.json").write_text(
        json.dumps(SENSITIVITY))
    body = client.get("/api/sensitivity").json()
    xm = xmins_by_player_gw(COMPONENTS)
    want = math.sqrt(sum(band_for(ep, xm[(code, GW)]).sigma ** 2
                         for code, ep in ((11, 5.0), (22, 1.5))))
    assert body["decision_sigma"] == pytest.approx(round(want, 3))


def test_no_runner_up_is_no_comparison(client, tmp_path):
    payload = {**SENSITIVITY, "runner_up": None, "margin": None}
    (tmp_path / f"reports/sensitivity_gw{GW}.json").write_text(
        json.dumps(payload))
    assert client.get("/api/sensitivity").json()["decision_sigma"] is None


def test_no_components_file_is_no_comparison(client, tmp_path):
    (tmp_path / f"reports/sensitivity_gw{GW}.json").write_text(
        json.dumps(SENSITIVITY))
    (tmp_path / f"reports/components_gw{GW}.parquet").unlink()
    body = client.get("/api/sensitivity")
    assert body.status_code == 200
    assert body.json()["decision_sigma"] is None


def test_the_rest_of_the_sensitivity_payload_is_untouched(client, tmp_path):
    (tmp_path / f"reports/sensitivity_gw{GW}.json").write_text(
        json.dumps(SENSITIVITY))
    body = client.get("/api/sensitivity").json()
    assert body["available"] is True
    assert body["margin"] == pytest.approx(0.6)
    assert body["modal"]["count"] == 30
```

- [ ] **Add the schemas.** In `src/gaffer/web/schemas.py`, append:

```python
class ConfidenceTier(BaseModel):
    """One record-derived claim, with the counts that back it.

    ``text`` is the whole product — a sentence quoting counts. The counts are
    carried beside it so a caller can style the tier without re-parsing prose,
    never so it can compute a rate: the absence of a percentage anywhere in
    this model is the point of it (spec D3).
    """

    tier: Literal["early", "mixed", "backed"] = "early"
    reviewed: int = 0
    graded: int = 0
    """Reviewed gameweeks where the lane was actually comparable. The gap
    between this and ``reviewed`` is the weeks the model's captain was not in
    the eleven, which is not evidence either way."""
    wins: int = 0
    losses: int = 0
    aligned: int = 0
    text: str = ""


class Confidence(BaseModel):
    captain: ConfidenceTier = Field(default_factory=ConfidenceTier)
```

and add one field to `SensitivityReport`, after `margin` (L1157):

```python
    decision_sigma: float | None = None
    """The scenario sweep's own noise on the players that separate the two
    plans, in quadrature (plan A6).

    Computed at serve time from the banked components frame rather than stored
    in the report, so a report swept before this field existed still gets the
    line. ``None`` when there is no runner-up, no components frame, or nothing
    in the symmetric difference — the card then prints its margin unqualified,
    which is what it did before."""
```

- [ ] **Write the confidence router.** Create `src/gaffer/web/routers/confidence.py`:

```python
"""GET /api/confidence — what the banked record entitles the tool to claim.

Never an error, for the review router's reason: an ungraded season is not a
degraded state, it is the state every season begins in. So every failure —
no ledger, a corrupt one, a reports directory that does not exist — is a 200
carrying the "too early" sentence with a count of zero in it, which is both
true and the thing the card should say.

No arithmetic here at all: :mod:`gaffer.confidence` does the counting and this
reads a file.
"""

from __future__ import annotations

from fastapi import APIRouter

from gaffer.confidence import captain_confidence
from gaffer.web.schemas import Confidence, ConfidenceTier

router = APIRouter(prefix="/api", tags=["confidence"])


@router.get("/confidence", response_model=Confidence)
def confidence() -> Confidence:
    from gaffer.review import load_ledger

    try:
        ledger = load_ledger()
    except Exception as exc:  # noqa: BLE001 — a bad ledger is an empty one
        print(f"confidence: ledger unavailable ({exc})")
        ledger = []
    return Confidence(captain=ConfidenceTier(**captain_confidence(ledger)))
```

- [ ] **Compute the decision σ.** In `src/gaffer/web/routers/sensitivity.py`, extend the imports:

```python
import math

from fastapi import APIRouter, Query

from gaffer.artifacts import latest_gw, load_components
from gaffer.sensitivity import load_sensitivity
from gaffer.uncertainty import band_for, shipped_table, xmins_by_player_gw
from gaffer.web.schemas import SensitivityReport
```

Add, after the router definition:

```python
def _plan_codes(plan) -> set[int]:
    """Every player one signature names: its buys, its sells, its captain.

    The captain is in there because an armband is a decision the sweep can
    disagree about, and a margin between two plans that differ only in who
    wears it is separated by exactly that player's noise.
    """
    if not isinstance(plan, dict):
        return set()
    out: set[int] = set()
    for key in ("buys", "sells"):
        for row in plan.get(key) or []:
            if isinstance(row, dict) and row.get("code") is not None:
                out.add(int(row["code"]))
    captain = plan.get("captain")
    if isinstance(captain, dict) and captain.get("code") is not None:
        out.add(int(captain["code"]))
    return out


def decision_sigma(payload: dict, gw: int) -> float | None:
    """Noise on the players that separate the modal plan from the runner-up.

    Plan A6. Not a σ on a whole plan — the table cannot price one, and it does
    not need to: two signatures differ in a handful of named players, so the
    noise that could flip the comparison is the noise on those players and
    nothing else. Summed in quadrature because ``noise_ep`` draws one
    independent standard normal per cell and adds no cross-player correlation.

    ``None`` for every case where the comparison cannot be made honestly: no
    runner-up, no banked components frame, no minutes model, or two signatures
    whose named players happen to coincide. The card then prints its margin
    line exactly as it did before this field existed.
    """
    modal, runner_up = payload.get("modal"), payload.get("runner_up")
    if not modal or not runner_up:
        return None
    codes = _plan_codes(modal) ^ _plan_codes(runner_up)
    if not codes:
        return None
    try:
        comp = load_components(gw)
    except Exception as exc:  # noqa: BLE001 — an honesty line is not a 500
        print(f"sensitivity: no components frame for the noise line ({exc})")
        return None
    try:
        xmins = xmins_by_player_gw(comp)
        ep = (comp[comp["gw"].astype(int) == int(gw)]
              .groupby("code")["ep"].sum().to_dict())
    except Exception as exc:  # noqa: BLE001
        print(f"sensitivity: components frame unusable ({exc})")
        return None

    table = shipped_table()
    total = 0.0
    seen = 0
    for code in codes:
        band = band_for(ep.get(code, 0.0), xmins.get((int(code), int(gw))),
                        table=table)
        if band is None:
            continue
        total += band.sigma ** 2
        seen += 1
    return round(math.sqrt(total), 3) if seen else None
```

and thread it through both return paths of `sensitivity()`, replacing L37-46:

```python
    banked = payload.get("gw")
    sigma = decision_sigma(payload, int(banked) if banked is not None
                           else wanted)
    if current is not None and banked is not None and int(banked) != current:
        # Served, but not as this week's: the numbers are real and the card is
        # entitled to show what it is refusing to headline.
        return SensitivityReport(available=False, decision_sigma=sigma, **{
            **fields,
            "notice": f"that sensitivity report is GW{int(banked)}'s and the "
                      f"saved board is GW{current} — re-run the sweep to see "
                      f"how much of *this* plan survives"})
    return SensitivityReport(available=True, decision_sigma=sigma, **fields)
```

- [ ] **Register the router.** In `src/gaffer/web/app.py`, extend the import (L26-29) with `confidence` in alphabetical position, and add `app.include_router(confidence.router)` after `app.include_router(components.router)`.

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_confidence.py tests/test_web_confidence.py \
  tests/test_web_sensitivity.py tests/test_review.py tests/test_web_review.py
```

- [ ] **Commit.**

```bash
git add src/gaffer/confidence.py src/gaffer/web/routers/confidence.py \
  src/gaffer/web/routers/sensitivity.py src/gaffer/web/schemas.py \
  src/gaffer/web/app.py tests/test_confidence.py tests/test_web_confidence.py \
  && git commit -m "$(cat <<'EOF'
feat: confidence framing from the ledger, and the margin against the noise

Three tiers that quote counts and never a percentage; below four graded
gameweeks the answer is a refusal, not a weaker claim.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 4 — the biggest misses, joined off disk

**Files:**
- Create `src/gaffer/misses.py`
- Create `tests/test_misses.py`
- Create `src/gaffer/web/routers/misses.py`
- Modify `src/gaffer/web/app.py`
- Create `tests/test_web_misses.py`

- [ ] **Write the failing test.** Create `tests/test_misses.py`:

```python
"""The week's biggest forecast errors, joined off two banked artifacts.

The interesting question is not the arithmetic, it is *which gameweek*: the
newest components file is normally next week's and has no results at all,
while the newest results may predate the oldest components file on a clone
that has just been set up. So the subject under test is mostly the
intersection, and the empty intersection.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.artifacts import save_components
from gaffer.misses import MISS_ROWS, biggest_misses, scoreable_gw


def _components(gw: int, rows) -> pd.DataFrame:
    return pd.DataFrame([
        {"code": code, "element": code, "name": name, "position": pos,
         "team_code": 3, "team_name": "Arsenal", "gw": gw, "opp_code": 4,
         "opp_name": "City", "was_home": 1.0, "kickoff_time": None,
         "p_play": 0.9, "p60": 0.8, "ep": ep}
        for code, name, pos, ep in rows])


RESULTS = pd.DataFrame([
    {"code": 11, "gw": 5, "total_points": 16, "minutes": 90},
    {"code": 22, "gw": 5, "total_points": 1, "minutes": 12},
    {"code": 33, "gw": 5, "total_points": 6, "minutes": 90},
])

PLAYERS = pd.DataFrame({
    "code": [11, 22, 33], "element": [11, 22, 33],
    "name": ["Saka", "Sub", "Gabriel"], "position": ["MID", "FWD", "DEF"],
    "now_cost": [100, 60, 55]})


@pytest.fixture()
def banked(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    RESULTS.to_parquet(tmp_path / "data/live/player_gw.parquet", index=False)
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    save_components(_components(5, [(11, "Saka", "MID", 5.5),
                                    (22, "Sub", "FWD", 2.0),
                                    (33, "Gabriel", "DEF", 4.0)]), 5)
    # Next week's file, written by the most recent advise run: newer, and
    # with nothing played in it.
    save_components(_components(6, [(11, "Saka", "MID", 6.0)]), 6)
    return tmp_path


def test_the_scoreable_gameweek_is_the_newest_one_with_both(banked):
    """A7: not the newest components file, which is next week's."""
    assert scoreable_gw() == 5


def test_no_results_at_all_is_no_scoreable_gameweek(banked):
    (banked / "data/live/player_gw.parquet").unlink()
    assert scoreable_gw() is None


def test_no_components_at_all_is_no_scoreable_gameweek(banked):
    for gw in (5, 6):
        (banked / f"reports/components_gw{gw}.parquet").unlink()
    assert scoreable_gw() is None


def test_the_misses_are_sorted_by_absolute_error(banked):
    rows = biggest_misses(5)
    assert [r["code"] for r in rows] == [11, 33, 22]
    assert rows[0]["miss"] == pytest.approx(10.5)   # 16 actual, 5.5 forecast
    assert rows[2]["miss"] == pytest.approx(-1.0)


def test_every_row_carries_its_context(banked):
    row = biggest_misses(5)[0]
    assert row["name"] == "Saka" and row["position"] == "MID"
    assert row["price"] == pytest.approx(10.0)
    assert row["actual"] == 16 and row["ep"] == pytest.approx(5.5)
    assert row["minutes"] == 90


def test_a_double_gameweek_is_one_row(banked):
    """Two fixtures, one forecast for the week and one points total."""
    save_components(pd.concat([
        _components(5, [(11, "Saka", "MID", 3.0)]),
        _components(5, [(11, "Saka", "MID", 2.5)])], ignore_index=True), 5)
    rows = [r for r in biggest_misses(5) if r["code"] == 11]
    assert len(rows) == 1 and rows[0]["ep"] == pytest.approx(5.5)


def test_a_player_with_no_result_row_is_left_out_not_zeroed(banked):
    """An inner join, on purpose: a player the results frame does not cover
    has not scored nought, he is unknown."""
    save_components(_components(5, [(11, "Saka", "MID", 5.5),
                                    (99, "Ghost", "MID", 7.0)]), 5)
    assert 99 not in {r["code"] for r in biggest_misses(5)}


def test_the_list_is_capped(banked):
    save_components(_components(5, [(c, f"P{c}", "MID", 1.0)
                                    for c in range(1, 40)]), 5)
    results = pd.DataFrame([{"code": c, "gw": 5, "total_points": c,
                             "minutes": 90} for c in range(1, 40)])
    results.to_parquet(banked / "data/live/player_gw.parquet", index=False)
    assert len(biggest_misses(5)) == MISS_ROWS


def test_a_missing_player_snapshot_still_lists_the_misses(banked):
    """Names and prices are context, not the finding."""
    (banked / "data/live/players.parquet").unlink()
    rows = biggest_misses(5)
    assert rows[0]["code"] == 11
    assert rows[0]["name"] == "11" and rows[0]["price"] is None


def test_an_unscoreable_gameweek_is_an_empty_list(banked):
    assert biggest_misses(6) == []
    assert biggest_misses(99) == []
```

- [ ] **Implement.** Create `src/gaffer/misses.py`:

```python
"""The week's biggest forecast errors, joined from two banked artifacts.

A calibration page that only ever shows aggregates is a page nobody argues
with. The reliability curves say the heads are well calibrated in the mean;
this says *who* the model got most wrong last week, which is the number a
manager can check against his own memory of the football.

Nothing is computed that was not already on disk: ``reports/components_gw{N}
.parquet`` holds what was forecast, ``data/live/player_gw.parquet`` holds what
happened, and the join is an inner one because a player the results frame does
not cover has not scored nought — he is unknown, and printing him at zero
would put the tool's worst-looking miss on a player who was never in the
data.
"""

from __future__ import annotations

import re

import pandas as pd

from gaffer import artifacts

MISS_ROWS = 12
"""How many rows the card shows.

Enough that the tail is visible and few enough that it stays a list somebody
reads. Both directions are kept — the over-forecasts are the ones that cost
transfers, the under-forecasts are the ones that cost captaincies.
"""

_COMPONENTS_RE = re.compile(r"components_gw(\d+)\.parquet$")

PLAYER_GW = "live/player_gw.parquet"
PLAYERS = "live/players.parquet"


def component_gws() -> list[int]:
    """Every gameweek with a banked component breakdown, ascending."""
    out = []
    for path in artifacts.REPORTS.glob("components_gw*.parquet"):
        match = _COMPONENTS_RE.search(path.name)
        if match:
            out.append(int(match.group(1)))
    return sorted(out)


def _results() -> pd.DataFrame | None:
    from gaffer.data import store

    if not store.exists(PLAYER_GW):
        return None
    try:
        return store.load(PLAYER_GW)
    except Exception as exc:  # noqa: BLE001 — a card is not worth a 500
        print(f"misses: results frame unreadable ({exc})")
        return None


def scoreable_gw() -> int | None:
    """The newest gameweek that has **both** a forecast and a result.

    Not :func:`gaffer.artifacts.latest_gw`, which is normally the *upcoming*
    week: its components file is the whole point of the advice run and its
    results do not exist yet. Not "the last finished gameweek" either — on a
    fresh clone that may predate every components file on disk. The
    intersection is the only definition that is right in both directions, and
    it is empty exactly when there is nothing honest to show (plan A7).
    """
    live = _results()
    if live is None or live.empty or "gw" not in live.columns:
        return None
    played = set(pd.to_numeric(live["gw"], errors="coerce")
                 .dropna().astype(int))
    both = played & set(component_gws())
    return max(both) if both else None


def _context() -> tuple[dict[int, str], dict[int, str], dict[int, float]]:
    """``(names, positions, prices)`` from the bootstrap snapshot.

    Empty maps when there is no snapshot: the miss is the finding and the name
    is the context, so a clone without a player list still gets its list —
    with codes where the names would be.
    """
    try:
        players = artifacts.load_snapshot(PLAYERS)
    except Exception as exc:  # noqa: BLE001
        print(f"misses: player snapshot unreadable ({exc})")
        return {}, {}, {}
    names = {int(r.code): str(r.name) for r in players.itertuples()}
    positions = {int(r.code): str(r.position) for r in players.itertuples()}
    prices = {int(r.code): round(int(r.now_cost) / 10, 1)
              for r in players.itertuples()}
    return names, positions, prices


def biggest_misses(gw: int) -> list[dict]:
    """The ``MISS_ROWS`` largest ``|actual - ep|`` for one gameweek.

    ``ep`` is summed across the gameweek's fixtures and ``total_points`` with
    it, so a double gameweek is one row: the forecast was for the week and so
    was the return.

    ``[]`` for every absent input. Never raises — the caller is a card on a
    page whose other cards are fine.
    """
    try:
        comp = artifacts.load_components(int(gw))
    except Exception:  # noqa: BLE001 — an absent forecast is an absent card
        return []
    live = _results()
    if live is None or live.empty:
        return []
    if not {"code", "gw", "ep"}.issubset(comp.columns):
        return []
    if not {"code", "gw", "total_points"}.issubset(live.columns):
        return []

    forecast = (pd.DataFrame({
        "code": comp["code"].astype(int), "gw": comp["gw"].astype(int),
        "ep": pd.to_numeric(comp["ep"], errors="coerce").fillna(0.0)})
        .query("gw == @gw").groupby("code", as_index=False)["ep"].sum())
    if forecast.empty:
        return []

    played = live[pd.to_numeric(live["gw"], errors="coerce") == int(gw)]
    if played.empty:
        return []
    actual = pd.DataFrame({
        "code": played["code"].astype(int),
        "total_points": pd.to_numeric(played["total_points"],
                                      errors="coerce").fillna(0.0),
        "minutes": pd.to_numeric(played.get("minutes", 0),
                                 errors="coerce").fillna(0.0),
    }).groupby("code", as_index=False).sum()

    joined = forecast.merge(actual, on="code", how="inner")
    if joined.empty:
        return []
    joined["miss"] = joined["total_points"] - joined["ep"]
    joined = joined.reindex(
        joined["miss"].abs().sort_values(ascending=False).index)

    names, positions, prices = _context()
    return [{
        "code": int(r.code),
        "name": names.get(int(r.code), str(int(r.code))),
        "position": positions.get(int(r.code), ""),
        "price": prices.get(int(r.code)),
        "ep": round(float(r.ep), 2),
        "actual": int(r.total_points),
        "minutes": int(r.minutes),
        "miss": round(float(r.miss), 2),
    } for r in joined.head(MISS_ROWS).itertuples()]
```

- [ ] **Write the endpoint test.** Create `tests/test_web_misses.py`:

```python
"""``/api/misses``: a 200 for every state, including having nothing to say.

The card's contract is spec D1's — absent inputs mean an absent card, never a
card of zeros — and the only way the frontend can tell the difference is a
null gameweek. So that is what is asserted here.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import save_components
from gaffer.web.app import create_app

COMPONENTS = pd.DataFrame([
    {"code": 11, "element": 11, "name": "Saka", "position": "MID",
     "team_code": 3, "team_name": "Arsenal", "gw": 5, "opp_code": 4,
     "opp_name": "City", "was_home": 1.0, "kickoff_time": None,
     "p_play": 0.9, "p60": 0.8, "ep": 5.5}])

RESULTS = pd.DataFrame([{"code": 11, "gw": 5, "total_points": 16,
                         "minutes": 90}])

PLAYERS = pd.DataFrame({"code": [11], "element": [11], "name": ["Saka"],
                        "position": ["MID"], "now_cost": [100]})


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    return TestClient(create_app())


def test_a_clone_with_nothing_banked_is_an_empty_card(client):
    body = client.get("/api/misses").json()
    assert body == {"gw": None, "rows": []}


def test_results_without_a_forecast_are_still_an_empty_card(client, tmp_path):
    RESULTS.to_parquet(tmp_path / "data/live/player_gw.parquet", index=False)
    assert client.get("/api/misses").json()["gw"] is None


def test_a_scored_week_comes_back_named(client, tmp_path):
    RESULTS.to_parquet(tmp_path / "data/live/player_gw.parquet", index=False)
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    save_components(COMPONENTS, 5)
    body = client.get("/api/misses").json()
    assert body["gw"] == 5
    assert body["rows"][0]["name"] == "Saka"
    assert body["rows"][0]["miss"] == pytest.approx(10.5)


def test_an_explicit_gameweek_is_honoured(client, tmp_path):
    RESULTS.to_parquet(tmp_path / "data/live/player_gw.parquet", index=False)
    save_components(COMPONENTS, 5)
    assert client.get("/api/misses?gw=6").json() == {"gw": None, "rows": []}
```

- [ ] **Add the schema.** In `src/gaffer/web/schemas.py`, append:

```python
class MissRow(BaseModel):
    """One player-gameweek the forecast got most wrong.

    ``miss`` is ``actual - ep``, so it is signed: a positive one is a player
    the model under-rated and a negative one is a transfer it may have talked
    somebody into. Both directions are shown, which is why the card sorts on
    the absolute value and prints the sign.
    """

    code: int
    name: str
    position: str = ""
    price: float | None = None
    ep: float
    actual: int
    minutes: int = 0
    miss: float


class Misses(BaseModel):
    gw: int | None = None
    """``None`` when no gameweek has both a banked forecast and a banked
    result. That is an absent card, not a card of zeros (spec D1)."""
    rows: list[MissRow] = Field(default_factory=list)
```

- [ ] **Write the router.** Create `src/gaffer/web/routers/misses.py`:

```python
"""GET /api/misses — the biggest forecast errors of the last scored week.

Never an error and never a 404. A clone that has never ingested a result is
not a broken install, so the answer is a 200 with a null gameweek, which the
Quality tab renders as no card at all.

All the work is in :mod:`gaffer.misses`; this chooses the gameweek and shapes
the payload.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from gaffer.misses import biggest_misses, scoreable_gw
from gaffer.web.schemas import Misses, MissRow

router = APIRouter(prefix="/api", tags=["misses"])


@router.get("/misses", response_model=Misses)
def misses(gw: int | None = Query(
        default=None,
        description="Gameweek to score; the newest scoreable one when "
                    "omitted.")) -> Misses:
    try:
        wanted = scoreable_gw() if gw is None else int(gw)
        rows = [] if wanted is None else biggest_misses(wanted)
    except Exception as exc:  # noqa: BLE001 — one card, never the page
        print(f"misses: unavailable ({exc})")
        return Misses()
    if not rows:
        return Misses()
    return Misses(gw=wanted, rows=[MissRow(**row) for row in rows])
```

- [ ] **Register it.** In `src/gaffer/web/app.py`, add `misses` to the router import and `app.include_router(misses.router)` after `app.include_router(meta.router)`.

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_misses.py tests/test_web_misses.py \
  tests/test_web_quality.py
```

- [ ] **Commit.**

```bash
git add src/gaffer/misses.py src/gaffer/web/routers/misses.py \
  src/gaffer/web/schemas.py src/gaffer/web/app.py tests/test_misses.py \
  tests/test_web_misses.py && git commit -m "$(cat <<'EOF'
feat: the week's biggest forecast misses, joined off the banked artifacts

Scored on the newest gameweek that has both a forecast and a result, which is
neither the newest components file nor the newest result.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 5 — the calibration cards

**Files:**
- Modify `frontend/src/types.ts`
- Modify `frontend/src/hubs/model/QualityTab.tsx`
- Modify `frontend/src/hubs/model/QualityTab.test.tsx`

- [ ] **Write the failing test.** Append to `frontend/src/hubs/model/QualityTab.test.tsx` (keeping every existing test and the file's existing mock setup; the new block assumes the file's established `apiGet` mocking idiom — read the top of the file and follow it):

```tsx
describe('v8g calibration', () => {
  it('draws a reliability curve for p_start, which nothing rendered before',
    async () => {
      renderQuality({ current: currentWithHeads(['p_play', 'p60', 'cs',
                                                 'p_start']) })
      expect(await screen.findByLabelText('P(starts) reliability'))
        .toBeInTheDocument()
    })

  it('omits a head the evaluation does not carry', async () => {
    renderQuality({ current: currentWithHeads(['p_play']) })
    await screen.findByLabelText('P(plays) reliability')
    expect(screen.queryByLabelText('P(starts) reliability')).toBeNull()
  })

  it('says how many observations each curve rests on', async () => {
    renderQuality({ current: currentWithHeads(['p_play']) })
    // The bins carry n; a curve over forty rows and one over forty thousand
    // look identical without it.
    expect(await screen.findByText(/over 300 observations/)).toBeInTheDocument()
  })

  it('plots forecast against outcome for every finished gameweek', async () => {
    mockHistory({ runs: [
      { gw: 1, deadline: '', captain: 'Saka', buys: [], sells: [], hits: 0,
        expected_pts: 55.2, actual_pts: 61 },
      { gw: 2, deadline: '', captain: 'Saka', buys: [], sells: [], hits: 0,
        expected_pts: 58.0, actual_pts: null },
    ] })
    renderQuality({})
    const chart = await screen.findByLabelText('forecast against outcome')
    expect(chart).toBeInTheDocument()
    // GW2 has not been played; a point at zero would be a 58-point miss the
    // model never made.
    expect(screen.getByText(/1 finished gameweek/)).toBeInTheDocument()
  })

  it('shows no scatter at all when nothing has been played', async () => {
    mockHistory({ runs: [
      { gw: 1, deadline: '', captain: '', buys: [], sells: [], hits: 0,
        expected_pts: 55.2, actual_pts: null }] })
    renderQuality({})
    await screen.findByText(/Nothing evaluated yet|Holdout/)
    expect(screen.queryByLabelText('forecast against outcome')).toBeNull()
  })

  it('lists the biggest misses with their sign', async () => {
    mockMisses({ gw: 5, rows: [
      { code: 11, name: 'Saka', position: 'MID', price: 10.0, ep: 5.5,
        actual: 16, minutes: 90, miss: 10.5 },
      { code: 22, name: 'Sub', position: 'FWD', price: 6.0, ep: 7.0,
        actual: 1, minutes: 12, miss: -6.0 },
    ] })
    renderQuality({})
    expect(await screen.findByText('Saka')).toBeInTheDocument()
    expect(screen.getByText('+10.5')).toBeInTheDocument()
    expect(screen.getByText('-6.0')).toBeInTheDocument()
  })

  it('renders no misses card when no week has been scored', async () => {
    mockMisses({ gw: null, rows: [] })
    renderQuality({})
    await screen.findByText(/Nothing evaluated yet|Holdout/)
    expect(screen.queryByText(/Biggest misses/)).toBeNull()
  })
})
```

- [ ] **Add the types.** In `frontend/src/types.ts`, extend `HeadMetrics`' neighbourhood (after `ReliabilityBin`, L406-416) — no change to the interfaces themselves — and append:

```ts
export interface MissRow {
  code: number
  name: string
  position: string
  price: number | null
  ep: number
  actual: number
  minutes: number
  /** actual - ep, signed. Positive is a player the model under-rated;
   *  negative is one it may have talked somebody into buying. */
  miss: number
}

export interface MissesData {
  /** null when no gameweek has both a banked forecast and a banked result —
   *  an absent card, not a card of zeros. */
  gw: number | null
  rows: MissRow[]
}

export interface ConfidenceTier {
  tier: 'early' | 'mixed' | 'backed'
  reviewed: number
  graded: number
  wins: number
  losses: number
  aligned: number
  /** The whole product: a sentence quoting counts. Never a percentage. */
  text: string
}

export interface ConfidenceData {
  captain: ConfidenceTier
}
```

- [ ] **Implement.** In `frontend/src/hubs/model/QualityTab.tsx`:

Extend the recharts import (L2-5):

```tsx
import {
  CartesianGrid, Line, LineChart as RLineChart, ReferenceLine,
  ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from 'recharts'
```

Extend the type import (L11-14) with `HistoryData`, `MissRow`, `MissesData`.

Add `p_start` to `HEADS` (L26-30) — **third**, between `p60` and `cs`, so the three minutes heads read together:

```tsx
const HEADS: Array<[string, string]> = [
  ['p_play', 'P(plays)'],
  ['p60', 'P(60+ minutes)'],
  // v8a has emitted this since the trichotomy landed and nothing rendered it.
  // p_play is a sum of two modes, so a model that sharpens the start/cameo
  // split while leaving the sum alone is invisible in the two above.
  ['p_start', 'P(starts)'],
  ['cs', 'P(clean sheet)'],
]
```

Replace `Reliability` (L97-119) with:

```tsx
/**
 * One head's reliability curve, against the line it is trying to be.
 *
 * The diagonal is the whole chart. A calibration plot without y = x on it
 * asks the reader to imagine the reference and then judge distance from it by
 * eye, which is exactly the judgement the picture exists to make unnecessary:
 * above the line the head is under-confident, below it over-confident, and
 * the size of the gap is the size of the error the optimizer inherits when it
 * multiplies by these numbers.
 *
 * The observation count is printed rather than drawn. A curve fitted on forty
 * rows and one fitted on forty thousand are the same shape on screen and are
 * not the same evidence.
 */
function Reliability({ label, head }: { label: string; head: HeadMetrics }) {
  const points = head.reliability
  const n = points.reduce((total, bin) => total + bin.n, 0)
  return (
    <div className="mb-3">
      <p className="label">
        {label} — log loss {head.log_loss ?? 'n/a'}
      </p>
      <div aria-label={`${label} reliability`}>
        <ResponsiveContainer width="100%" height={220}>
          <RLineChart data={points}>
            <CartesianGrid stroke="var(--color-divider)" vertical={false} />
            <XAxis dataKey="pred" type="number" domain={[0, 1]}
                   stroke="var(--color-text-muted)" />
            <YAxis type="number" domain={[0, 1]}
                   stroke="var(--color-text-muted)" />
            <Tooltip contentStyle={{ background: 'var(--color-card)',
                                     border: '1px solid var(--color-border)' }} />
            {/* Perfect calibration. Drawn as a segment rather than a
                ReferenceLine because a diagonal reference needs two points
                and recharts' ReferenceLine takes a single axis value. */}
            <Line data={[{ pred: 0, ideal: 0 }, { pred: 1, ideal: 1 }]}
                  dataKey="ideal" dot={false} isAnimationActive={false}
                  stroke="var(--color-text-muted)" strokeDasharray="4 4"
                  strokeWidth={1} />
            <Line type="monotone" dataKey="obs" dot={false}
                  stroke="var(--color-sage)" strokeWidth={2} />
          </RLineChart>
        </ResponsiveContainer>
      </div>
      <p className="text-text-faint">
        {`${points.length} populated bins over ${n} observations. Above the `
          + 'dashed line the head is under-confident; below it, over-confident.'}
      </p>
    </div>
  )
}
```

Add the two new sections above `export default function QualityTab`:

```tsx
/**
 * Forecast against outcome, one point per finished gameweek.
 *
 * Its own fetch, on PensSection's pattern: /api/history is a different
 * artifact with its own "nothing banked yet" state, and folding it into
 * /api/quality would let one missing file blank the other's card.
 *
 * A gameweek with no official points yet is dropped rather than plotted at
 * zero — an unplayed week charted at the origin is a fifty-point miss the
 * model never made, which is the single most misleading thing this card
 * could do.
 */
function ScatterSection() {
  const [runs, setRuns] = useState<HistoryData['runs'] | null>(null)

  useEffect(() => {
    apiGet<HistoryData>('/api/history')
      .then((body) => setRuns(body.runs ?? []))
      .catch(() => setRuns([]))
  }, [])

  const points = (runs ?? [])
    .filter((r) => r.actual_pts !== null)
    .map((r) => ({ gw: r.gw, expected: r.expected_pts,
                   actual: r.actual_pts as number }))
  if (points.length === 0) return null

  const top = Math.ceil(Math.max(
    ...points.map((p) => Math.max(p.expected, p.actual)), 10) / 10) * 10

  return (
    <Card title="Forecast against outcome" className="mt-4">
      <p className="mb-3 text-text-muted">
        {`Each point is one finished gameweek: what the advice run expected `
          + `from the eleven it picked, against what that eleven actually `
          + `scored. ${points.length} finished gameweek`
          + `${points.length === 1 ? '' : 's'}. Above the dashed line the `
          + 'week beat the forecast.'}
      </p>
      <div aria-label="forecast against outcome">
        <ResponsiveContainer width="100%" height={260}>
          <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid stroke="var(--color-divider)" />
            <XAxis type="number" dataKey="expected" name="expected"
                   domain={[0, top]} stroke="var(--color-text-muted)" />
            <YAxis type="number" dataKey="actual" name="actual"
                   domain={[0, top]} stroke="var(--color-text-muted)" />
            <ZAxis range={[60, 60]} />
            <Tooltip
              cursor={{ strokeDasharray: '3 3' }}
              contentStyle={{ background: 'var(--color-card)',
                              border: '1px solid var(--color-border)' }} />
            <ReferenceLine segment={[{ x: 0, y: 0 }, { x: top, y: top }]}
                           stroke="var(--color-text-muted)"
                           strokeDasharray="4 4" />
            <Scatter data={points} fill="var(--color-sage)" />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

const MISS_COLUMNS: Column<MissRow>[] = [
  { key: 'name', header: 'Player', primary: true, value: (r) => r.name,
    render: (r) => (
      <span className="flex items-center gap-1.5">
        <PlayerName code={r.code} name={r.name} />
        <PosBadge pos={r.position} variant="dot" />
      </span>
    ) },
  { key: 'price', header: 'Price', numeric: true, value: (r) => r.price,
    render: (r) => fmtNum(r.price, 1) },
  { key: 'ep', header: 'Forecast', primary: true, numeric: true,
    value: (r) => r.ep, render: (r) => fmtNum(r.ep) },
  { key: 'actual', header: 'Scored', primary: true, numeric: true,
    value: (r) => r.actual, render: (r) => r.actual },
  { key: 'minutes', header: 'Mins', numeric: true, value: (r) => r.minutes,
    render: (r) => r.minutes },
  { key: 'miss', header: 'Miss', primary: true, numeric: true,
    value: (r) => Math.abs(r.miss),
    render: (r) => (
      <span className={r.miss >= 0 ? 'num text-sage' : 'num text-rust'}>
        {`${r.miss >= 0 ? '+' : ''}${r.miss.toFixed(1)}`}
      </span>
    ) },
]

/**
 * Who the model got most wrong last week.
 *
 * The aggregates above say the heads are calibrated in the mean, which is a
 * claim nobody can check against their own memory of the football. This is
 * the card a manager argues with, so it keeps both signs: an over-forecast is
 * a transfer the tool may have talked somebody into, an under-forecast is a
 * captaincy it talked them out of.
 */
function MissesSection() {
  const [data, setData] = useState<MissesData | null>(null)

  useEffect(() => {
    apiGet<MissesData>('/api/misses').then(setData).catch(() => setData(null))
  }, [])

  if (!data || data.gw === null || data.rows.length === 0) return null
  return (
    <Card title={`Biggest misses — GW${data.gw}`} className="mt-4">
      <p className="mb-3 text-text-muted">
        Forecast against what he actually scored, largest gap first. A positive
        miss is a player the model under-rated.
      </p>
      <DataTable
        columns={MISS_COLUMNS}
        rows={data.rows}
        rowKey={(r) => r.code}
        rowLabel={(r) => r.name}
        initialSort="miss"
        empty={<p className="text-text-muted">Nothing scored yet.</p>}
      />
    </Card>
  )
}
```

Add `PlayerName` and `PosBadge` to the kit import (L7-10), and render the two sections in `QualityTab`'s tail (L476-486), before `<PensSection />`:

```tsx
      <ScatterSection />
      <MissesSection />
      <PensSection />
```

- [ ] **Verify.**

```bash
cd frontend && npx tsc --noEmit && npx vitest run src/hubs/model/QualityTab.test.tsx
```

- [ ] **Commit.**

```bash
git add frontend/src/types.ts frontend/src/hubs/model/QualityTab.tsx \
  frontend/src/hubs/model/QualityTab.test.tsx && git commit -m "$(cat <<'EOF'
feat: calibration evidence on the Quality tab

p_start's curve (emitted since v8a, never rendered), the y=x reference every
reliability plot was missing, forecast-vs-outcome per finished gameweek, and
last week's biggest misses.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 6 — bands where the decisions are made

**Files:**
- Modify `frontend/src/types.ts`
- Modify `frontend/src/hubs/this-week/SquadTable.tsx` and its test
- Create `frontend/src/hubs/this-week/ConfidenceLine.tsx` and its test
- Modify `frontend/src/hubs/ThisWeek.tsx`
- Modify `frontend/src/hubs/Players.tsx`
- Modify `frontend/src/hubs/players/ComparePanel.tsx` and its test
- Modify `frontend/src/hubs/planning/SensitivityCard.tsx`

- [ ] **Write the failing tests.** Create `frontend/src/hubs/this-week/ConfidenceLine.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ConfidenceLine from './ConfidenceLine'
import * as client from '../../api/client'

function mock(body: unknown) {
  vi.spyOn(client, 'apiGet').mockResolvedValue(body as never)
}

describe('ConfidenceLine', () => {
  it('prints the sentence the ledger produced', async () => {
    mock({ captain: { tier: 'backed', reviewed: 6, graded: 5, wins: 4,
                      losses: 1, aligned: 0,
                      text: 'The model’s captain outscored yours in 4 of '
                        + '5 comparable gameweeks (0 you agreed on).' } })
    render(<ConfidenceLine />)
    expect(await screen.findByText(/4 of 5 comparable gameweeks/))
      .toBeInTheDocument()
  })

  it('renders the too-early branch as prose, not as a warning', async () => {
    mock({ captain: { tier: 'early', reviewed: 1, graded: 1, wins: 1,
                      losses: 0, aligned: 0,
                      text: 'Too early to grade — the model’s '
                        + 'captain has been comparable to yours in 1 of 1 '
                        + 'reviewed gameweeks.' } })
    render(<ConfidenceLine />)
    expect(await screen.findByText(/Too early to grade/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('renders nothing at all when the endpoint cannot answer', async () => {
    vi.spyOn(client, 'apiGet').mockRejectedValue(new Error('down'))
    const { container } = render(<ConfidenceLine />)
    await waitFor(() => expect(container).toBeEmptyDOMElement())
  })
})
```

Append to `frontend/src/hubs/this-week/SquadTable.test.tsx` (following the file's existing render helper):

```tsx
describe('v8g bands', () => {
  it('prints the quartile range beside the point estimate', () => {
    renderTable([row({ code: 1, ep: 5.4, epLo: 4.1, epHi: 6.8 })])
    expect(screen.getByText('4.1–6.8')).toBeInTheDocument()
  })

  it('prints an em dash for a player with no minutes model', () => {
    renderTable([row({ code: 1, ep: 5.4, epLo: null, epHi: null })])
    // Not "5.4–5.4": no band is a different claim from a band of width zero.
    expect(screen.queryByText('5.4–5.4')).toBeNull()
  })

  it('chips a genuine haul chance and not a negligible one', () => {
    renderTable([row({ code: 1, pHaul: 0.22 }),
                 row({ code: 2, pHaul: 0.02 })])
    expect(screen.getAllByTitle(/chance of 10\+ points/)).toHaveLength(1)
  })

  it('chips a serious blank risk', () => {
    renderTable([row({ code: 1, pBlank: 0.55 })])
    expect(screen.getByTitle(/chance of 2 points or fewer/))
      .toBeInTheDocument()
  })
})
```

Append to `frontend/src/hubs/players/ComparePanel.test.tsx`:

```tsx
it('shows the band beside each compared player’s xPts', async () => {
  renderCompare([playerRow({ code: 11, ep_next: 5.4, ep_lo: 4.1,
                             ep_hi: 6.8 }),
                 playerRow({ code: 22, ep_next: 3.0, ep_lo: null,
                             ep_hi: null })])
  expect(await screen.findByText('4.1–6.8')).toBeInTheDocument()
})
```

- [ ] **Add the types.** In `frontend/src/types.ts`, append to `PlayerRow` (after `last4`, L179-200):

```ts
  /** p25 of the scenario sweep's own noise on `ep_next`. Null — never
   *  `ep_next` — when the minutes model has nothing to say about him. Not a
   *  symmetric interval: the calibrated path recentres, so the pair is
   *  quartiles and the UI labels it that way. */
  ep_lo: number | null
  ep_hi: number | null
  /** P(10+ points) and P(2 or fewer) under the same distribution. Crude by
   *  construction: they price forecast error, not football's variance. */
  p_haul: number | null
  p_blank: number | null
```

and to `ComponentPlayer` (L516-523):

```ts
  /** The requested gameweek's EP alone. `ep` above is a horizon sum, which is
   *  not a number the σ table has ever seen — this is the one the band
   *  brackets. */
  ep_gw: number | null
  sigma: number | null
  ep_lo: number | null
  ep_hi: number | null
  p_haul: number | null
  p_blank: number | null
```

and to `SensitivityReport` (L977-990):

```ts
  /** The sweep's own noise on the players that separate the modal plan from
   *  the runner-up, in quadrature. Null when there is no comparison to make. */
  decision_sigma: number | null
```

- [ ] **Implement the confidence line.** Create `frontend/src/hubs/this-week/ConfidenceLine.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import type { ConfidenceData } from '../../types'

/**
 * What the banked record entitles the captain card to claim.
 *
 * Prose, and prose only. The whole reason this component exists is that every
 * other tool prints a confidence percentage computed from nothing, so there
 * is deliberately no bar, no colour scale and no number here that the ledger
 * did not count — the server sends a sentence and this renders it.
 *
 * Its own fetch, and a silent one: an unreachable endpoint renders nothing.
 * The captain's name above it is still correct without this line, and a red
 * error strip next to an armband would read as a problem with the armband.
 */
export default function ConfidenceLine() {
  const [data, setData] = useState<ConfidenceData | null>(null)

  useEffect(() => {
    apiGet<ConfidenceData>('/api/confidence').then(setData)
      .catch(() => setData(null))
  }, [])

  if (!data?.captain?.text) return null
  return (
    <p className="mt-2 text-text-muted" data-testid="captain-confidence">
      {data.captain.text}
    </p>
  )
}
```

- [ ] **Implement the squad table columns.** In `frontend/src/hubs/this-week/SquadTable.tsx`, extend `SquadRow`:

```tsx
export interface SquadRow {
  code: number
  name: string
  position: string
  ep: number
  /** p25/p75 of the sweep's noise on `ep`. Null for a player with no minutes
   *  model — an em dash, never a zero-width band. */
  epLo: number | null
  epHi: number | null
  pHaul: number | null
  pBlank: number | null
  xmins: number | null
  ownership: number
  leagueEo: number
  simPct: number | null
  last4: number[]
  news: string
  chanceOfPlaying: number | null
  penalties: boolean
}
```

Add above `columnsFor`:

```tsx
/** Below this, "he might haul" is not news: it is the ordinary tail every
 *  forward carries, and a chip on every row is a chip on no row. */
const HAUL_CHIP = 0.15
/** Above this, the likeliest single outcome is a blank, which is worth saying
 *  out loud beside a starting place. */
const BLANK_CHIP = 0.35

function pct(value: number): string {
  return `${Math.round(value * 100)}%`
}
```

Insert a `range` column immediately after the `ep` column, and fold the two chips into the existing name cell's badge run:

```tsx
  { key: 'range', header: 'Range', numeric: true,
    value: (r) => (r.epHi === null || r.epLo === null
      ? null : r.epHi - r.epLo),
    render: (r) => (r.epLo === null || r.epHi === null
      ? <span className="num text-text-muted">—</span>
      : (
        <span className="num text-text-secondary"
              title="p25–p75 of the scenario sweep's own noise on this
                     forecast. Not a plus-or-minus: the calibrated path
                     recentres, so the pair is quartiles.">
          {`${r.epLo.toFixed(1)}–${r.epHi.toFixed(1)}`}
        </span>
      )) },
```

and inside the name column's `render`, after the `penalties` badge:

```tsx
        {r.pHaul !== null && r.pHaul >= HAUL_CHIP && (
          <Badge variant="positive"
                 title={`${pct(r.pHaul)} chance of 10+ points under the `
                   + 'sweep’s noise model — forecast error only, not '
                   + 'football’s own variance, so read it as a floor'}>
            {`haul ${pct(r.pHaul)}`}
          </Badge>
        )}
        {r.pBlank !== null && r.pBlank >= BLANK_CHIP && (
          <Badge variant="negative"
                 title={`${pct(r.pBlank)} chance of 2 points or fewer under `
                   + 'the sweep’s noise model'}>
            {`blank ${pct(r.pBlank)}`}
          </Badge>
        )}
```

- [ ] **Wire ThisWeek.** In `frontend/src/hubs/ThisWeek.tsx`, import `ConfidenceLine`, and extend the `squad` mapping (L101-120) — pulling the component player out once rather than three times:

```tsx
  const squad: SquadRow[] = [...advice.xi, ...advice.bench].map((p) => {
    const row = byCode.get(p.code)
    const comp = components?.players.find((c) => c.code === p.code)
    const move = [...advice.buys, ...advice.sells]
      .find((m) => m.code === p.code)
    return {
      code: p.code,
      name: p.name,
      position: p.position ?? row?.position ?? '',
      ep: p.ep,
      // The band comes off the components payload, which keys it (code, gw) —
      // the sweep's own key. Null flows straight through: no minutes model
      // means no band, not a band of width zero.
      epLo: comp?.ep_lo ?? null,
      epHi: comp?.ep_hi ?? null,
      pHaul: comp?.p_haul ?? null,
      pBlank: comp?.p_blank ?? null,
      xmins: comp?.fixtures[0]?.minutes.xmins ?? null,
      ownership: row?.ownership ?? NaN,
      leagueEo: row?.league_eo ?? NaN,
      simPct: move?.frequency ?? null,
      last4: row?.last4 ?? [],
      news: row?.news ?? '',
      chanceOfPlaying: row?.chance_of_playing ?? null,
      penalties: (row?.penalties_order ?? 0) === 1,
    }
  })
```

and render the line under the pitch, inside the "Starting XI" card, after `<PitchView ... />` (L210-214):

```tsx
        <PitchView
          xi={advice.xi.map((p) => ({ ...p, position: p.position ?? '' }))}
          captain={advice.captain.code}
          vice={advice.vice.code}
        />
        <ConfidenceLine />
```

- [ ] **Wire the explorer.** In `frontend/src/hubs/Players.tsx`, add a `range` column immediately after the `ep_next` column (L86):

```tsx
    { key: 'range', header: 'Range', numeric: true,
      value: (r) => (r.ep_hi === null || r.ep_lo === null
        ? null : r.ep_hi - r.ep_lo),
      render: (r) => (r.ep_lo === null || r.ep_hi === null
        ? <span className="num text-text-muted">—</span>
        : (
          <span className="num text-text-secondary"
                title="p25–p75 of the scenario sweep's own noise on this
                       forecast">
            {`${r.ep_lo.toFixed(1)}–${r.ep_hi.toFixed(1)}`}
          </span>
        )) },
```

and pass the pool down to compare (L217), which Task 7 consumes:

```tsx
              : <ComparePanel gw={gw} players={selected} pool={rows ?? []} />}
```

- [ ] **Show the band in compare.** In `frontend/src/hubs/players/ComparePanel.tsx`, inside the per-player `<dl>` (L108-112), replace the xPts pair with:

```tsx
                  <dt className="label">xPts</dt>
                  <dd className="num text-right text-text">
                    {fmtNum(player.ep_next)}
                    {player.ep_lo !== null && player.ep_hi !== null && (
                      <span className="ml-1 text-text-muted"
                            title="p25–p75 of the scenario sweep's own noise">
                        {`${player.ep_lo.toFixed(1)}–`
                          + `${player.ep_hi.toFixed(1)}`}
                      </span>
                    )}
                  </dd>
```

- [ ] **Qualify the sensitivity margin.** In `frontend/src/hubs/planning/SensitivityCard.tsx`, replace `marginLine` (L22-31):

```tsx
/** The margin is signed and the sign is the whole sentence: it is
 *  modal-minus-runner-up, so a negative one means the plan the sweep reached
 *  most often is priced *below* one it reached less often, which is the
 *  opposite recommendation and must not be printed as "behind".
 *
 *  The noise qualifier is the v8g honesty line. `decision_sigma` is the
 *  sweep's own σ on the players that actually separate the two plans, in
 *  quadrature — so a margin inside it is a margin the forecast error could
 *  have produced on its own, and saying "0.6 ahead" without saying that is
 *  the false precision this cycle exists to remove. Only ever said when it is
 *  true: a margin larger than the noise gets the bare sentence. */
function marginLine(margin: number | null,
                    sigma: number | null = null): string {
  if (margin === null) return 'Every re-solve reached the same decision.'
  const inside = sigma !== null && sigma > 0 && Math.abs(margin) < sigma
  const caveat = inside
    ? ` — smaller than the ${fmtNum(sigma, 1)}-point noise on the players `
      + 'that separate the two plans, so the ranking is not solid'
    : ''
  if (margin < 0) {
    return `The best differing plan is ${fmtNum(-margin, 1)} expected points `
      + `ahead${caveat}${inside ? '' : ' — the most frequent plan is not the '
        + 'highest-scoring one'}.`
  }
  return `The best differing plan is ${fmtNum(margin, 1)} expected points `
    + `behind${caveat}.`
}
```

and update its single call site to pass `data?.decision_sigma ?? null` as the second argument.

- [ ] **Verify.**

```bash
cd frontend && npx tsc --noEmit && npx vitest run
```

- [ ] **Commit.**

```bash
git add frontend/src/types.ts frontend/src/hubs/ThisWeek.tsx \
  frontend/src/hubs/Players.tsx \
  frontend/src/hubs/this-week/ConfidenceLine.tsx \
  frontend/src/hubs/this-week/ConfidenceLine.test.tsx \
  frontend/src/hubs/this-week/SquadTable.tsx \
  frontend/src/hubs/this-week/SquadTable.test.tsx \
  frontend/src/hubs/players/ComparePanel.tsx \
  frontend/src/hubs/players/ComparePanel.test.tsx \
  frontend/src/hubs/planning/SensitivityCard.tsx && git commit -m "$(cat <<'EOF'
feat: EP bands, haul/blank chips and the confidence line where decisions happen

The squad table and the explorer print p25-p75 beside every forecast, the
captain card says what the ledger entitles it to, and a margin inside the
noise says so.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 7 — the compare radar

**Files:**
- Create `frontend/src/hubs/players/CompareRadar.tsx`
- Create `frontend/src/hubs/players/CompareRadar.test.tsx`
- Modify `frontend/src/hubs/players/ComparePanel.tsx` and its test

- [ ] **Write the failing test.** Create `frontend/src/hubs/players/CompareRadar.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import CompareRadar, { AXES, axisValues, normalize } from './CompareRadar'
import type { ComponentsBreakdown, FixtureMatrixData, PlayerRow } from
  '../../types'

function player(over: Partial<PlayerRow>): PlayerRow {
  return {
    code: 1, element: 1, name: 'A', position: 'MID', team_code: 3,
    team_name: 'Arsenal', price: 10, ep_next: 5, ep_horizon: 10,
    ownership: 10, league_eo: 10, field_eo: null, field_class: null,
    available: true, status: 'a', news: '', chance_of_playing: null,
    penalties_order: null, free_kicks_order: null, corners_order: null,
    in_squad: false, last4: [], ep_lo: null, ep_hi: null, p_haul: null,
    p_blank: null, ...over,
  }
}

const COMPONENTS: ComponentsBreakdown = {
  gw: 5,
  players: [{
    code: 1, name: 'A', position: 'MID', team_name: 'Arsenal', ep: 5,
    ep_gw: 5, sigma: 1, ep_lo: 4, ep_hi: 6, p_haul: 0.1, p_blank: 0.2,
    fixtures: [{ gw: 5, opponent: 'City', home: true, kickoff_time: null,
                 components: [{ label: 'Goals', points: 2 },
                              { label: 'Assists', points: 1 },
                              { label: 'Minutes', points: 2 }],
                 pen_taker: null, minutes: { p_play: 0.9, p60: 0.8 },
                 ep: 5 }],
  }],
}

const MATRIX: FixtureMatrixData = {
  from: 5, teams: [{ code: 3, name: 'Arsenal', short_name: 'ARS',
                     cells: [{ gw: 5, opponent: 'MCI', home: true,
                               attack: 0.2, defence: 0.8 }] }],
} as FixtureMatrixData

describe('normalize', () => {
  it('spreads a pool across 0 to 100', () => {
    expect(normalize(1, [1, 3, 5])).toBe(0)
    expect(normalize(5, [1, 3, 5])).toBe(100)
    expect(normalize(3, [1, 3, 5])).toBe(50)
  })

  it('puts a degenerate pool in the middle rather than dividing by zero', () => {
    // A9: one player, or a pool where every value is identical. 50 says "no
    // information", which is true; 0 or 100 would be a verdict.
    expect(normalize(4, [4])).toBe(50)
    expect(normalize(4, [4, 4, 4])).toBe(50)
  })

  it('clamps a value from outside its own pool', () => {
    expect(normalize(9, [1, 3, 5])).toBe(100)
  })
})

describe('axisValues', () => {
  it('reads attacking share off the components, not off a new endpoint', () => {
    const v = axisValues(player({ code: 1 }), COMPONENTS, MATRIX, 5)
    expect(v.attacking).toBeCloseTo(0.6)   // (2 + 1) / 5
  })

  it('reads minutes security off the first fixture', () => {
    expect(axisValues(player({ code: 1 }), COMPONENTS, MATRIX, 5).minutes)
      .toBeCloseTo(0.9)
  })

  it('scores set-piece duty by queue position across all three duties', () => {
    const both = axisValues(
      player({ penalties_order: 1, corners_order: 1 }), null, null, 5)
    const one = axisValues(player({ penalties_order: 2 }), null, null, 5)
    expect(both.setPieces).toBeGreaterThan(one.setPieces)
    expect(both.setPieces).toBeLessThanOrEqual(1)
  })

  it('reads a defender’s fixtures off the defence score', () => {
    const def = axisValues(player({ position: 'DEF' }), null, MATRIX, 5)
    const mid = axisValues(player({ position: 'MID' }), null, MATRIX, 5)
    // Easy to score against (attack 0.2), hard to keep out (defence 0.8):
    // the same fixture is a good one for a midfielder and a bad one for a
    // defender, and one number cannot say both.
    expect(mid.fixtures).toBeGreaterThan(def.fixtures)
  })

  it('has an opinion about nothing when nothing has been fetched', () => {
    const v = axisValues(player({}), null, null, 5)
    expect(v.attacking).toBe(0)
    expect(v.fixtures).toBe(0.5)   // no matrix is not a hard fixture
  })
})

describe('CompareRadar', () => {
  it('draws one series per compared player', () => {
    render(<CompareRadar gw={5}
                         players={[player({ code: 1, name: 'A' }),
                                   player({ code: 2, name: 'B' })]}
                         pool={[]} components={COMPONENTS} matrix={MATRIX} />)
    expect(screen.getByLabelText('player comparison radar'))
      .toBeInTheDocument()
  })

  it('states what the axes are normalized against', () => {
    render(<CompareRadar gw={5}
                         players={[player({ code: 1 }), player({ code: 2 })]}
                         pool={[player({ code: 1 }), player({ code: 2 }),
                                player({ code: 3 })]}
                         components={COMPONENTS} matrix={MATRIX} />)
    expect(screen.getByText(/against the 3 players currently listed/))
      .toBeInTheDocument()
  })

  it('falls back to the selection when no pool was handed down', () => {
    render(<CompareRadar gw={5}
                         players={[player({ code: 1 }), player({ code: 2 })]}
                         pool={[]} components={COMPONENTS} matrix={MATRIX} />)
    expect(screen.getByText(/against the 2 players being compared/))
      .toBeInTheDocument()
  })

  it('captions a comparison across positions rather than suppressing it', () => {
    render(<CompareRadar gw={5}
                         players={[player({ code: 1, position: 'GKP' }),
                                   player({ code: 2, position: 'FWD' })]}
                         pool={[]} components={COMPONENTS} matrix={MATRIX} />)
    expect(screen.getByText(/different jobs/i)).toBeInTheDocument()
    // Captioned, not hidden: the chart is still the fastest way to see that
    // they are not comparable.
    expect(screen.getByLabelText('player comparison radar')).toBeInTheDocument()
  })

  it('says nothing about positions when they match', () => {
    render(<CompareRadar gw={5}
                         players={[player({ code: 1, position: 'MID' }),
                                   player({ code: 2, position: 'MID' })]}
                         pool={[]} components={COMPONENTS} matrix={MATRIX} />)
    expect(screen.queryByText(/different jobs/i)).toBeNull()
  })

  it('has exactly the five axes the spec names', () => {
    expect(AXES.map(([key]) => key)).toEqual([
      'attacking', 'minutes', 'setPieces', 'fixtures', 'form'])
  })
})
```

- [ ] **Implement.** Create `frontend/src/hubs/players/CompareRadar.tsx`:

```tsx
import {
  Legend, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart,
  ResponsiveContainer, Tooltip,
} from 'recharts'
import type {
  ComponentsBreakdown, FixtureMatrixData, PlayerRow,
} from '../../types'

const SERIES_COLOURS = ['var(--color-sage)', 'var(--color-info)',
  'var(--color-rust)', 'var(--color-text-muted)']

/** How far ahead the fixture axis looks. Three, because that is the horizon a
 *  transfer is normally justified over and the one the fixture matrix's own
 *  colouring is read at. */
const FIXTURE_WEEKS = 3

/** Set-piece duty, scored by what each duty is actually worth in points.
 *  Penalties are a goal most times they are taken; corners are a chance of an
 *  assist. Second choice is half of first, because a deputy takes them only
 *  when the first choice is off the pitch. */
const DUTY_WEIGHT: Record<string, number> = {
  penalties: 1.0, freeKicks: 0.6, corners: 0.4,
}

export const AXES: Array<[string, string]> = [
  ['attacking', 'Attacking'],
  ['minutes', 'Minutes'],
  ['setPieces', 'Set pieces'],
  ['fixtures', 'Fixtures'],
  ['form', 'Form'],
]

export interface AxisValues {
  attacking: number
  minutes: number
  setPieces: number
  fixtures: number
  form: number
}

/**
 * Rescale one raw axis value against the pool, to 0-100.
 *
 * A degenerate pool — one player, or every value identical — maps to 50
 * rather than dividing by zero or picking an end. Fifty says "this axis
 * separates nobody here", which is true; zero or a hundred would be a verdict
 * the data does not support.
 */
export function normalize(value: number, pool: number[]): number {
  if (pool.length === 0) return 50
  const lo = Math.min(...pool)
  const hi = Math.max(...pool)
  if (!(hi > lo)) return 50
  const clamped = Math.min(Math.max(value, lo), hi)
  return Math.round(((clamped - lo) / (hi - lo)) * 100)
}

function duty(order: number | null, weight: number): number {
  if (order === 1) return weight
  if (order === 2) return weight / 2
  return 0
}

/**
 * The five raw axis values for one player, before normalization.
 *
 * Every one of them comes off something ComparePanel has already fetched
 * (plan A8) — there is no new endpoint in this feature and no import from
 * `set_pieces.py`, whose penalty share is a fitted input to the EP term
 * rather than a summary of a player's three set-piece duties.
 *
 * Missing inputs answer 0, except fixtures, which answers 0.5: an unfetched
 * fixture matrix is not a hard run of games, and drawing it as one would put
 * a spike in the chart that nothing in the data put there.
 */
export function axisValues(player: PlayerRow,
                           components: ComponentsBreakdown | null,
                           matrix: FixtureMatrixData | null,
                           gw: number): AxisValues {
  const comp = components?.players.find((p) => p.code === player.code)
  const week = (comp?.fixtures ?? []).filter((f) => f.gw === gw)
  const attackingPts = week.reduce((total, fixture) => total
    + fixture.components
      .filter((c) => c.label === 'Goals' || c.label === 'Assists')
      .reduce((sum, c) => sum + c.points, 0), 0)
  const weekEp = week.reduce((total, f) => total + f.ep, 0)

  const cells = (matrix?.teams.find((t) => t.code === player.team_code)?.cells
    ?? []).slice(0, FIXTURE_WEEKS)
  const defensive = player.position === 'GKP' || player.position === 'DEF'
  const difficulty = cells.length === 0 ? 0.5
    : cells.reduce((total, c) => total
      + (defensive ? c.defence : c.attack), 0) / cells.length

  return {
    attacking: weekEp > 0 ? attackingPts / weekEp : 0,
    minutes: week[0]?.minutes.p_play ?? 0,
    setPieces: Math.min(1, duty(player.penalties_order,
                                DUTY_WEIGHT.penalties)
      + duty(player.free_kicks_order, DUTY_WEIGHT.freeKicks)
      + duty(player.corners_order, DUTY_WEIGHT.corners)),
    // Difficulty runs 0 easiest to 1 hardest; the axis runs the other way,
    // because every other axis on this chart is "more is better".
    fixtures: 1 - difficulty,
    form: player.last4.length === 0 ? 0
      : player.last4.reduce((a, b) => a + b, 0) / player.last4.length,
  }
}

export interface CompareRadarProps {
  gw: number
  players: PlayerRow[]
  /** The explorer's currently-filtered rows, for normalization. Empty falls
   *  back to the selection, and the caption says which was used. */
  pool: PlayerRow[]
  components: ComponentsBreakdown | null
  matrix: FixtureMatrixData | null
}

/**
 * Five axes, overlaid.
 *
 * The reason a radar earns its place here and almost nowhere else: comparing
 * two players is genuinely a five-dimensional question, and the bar chart
 * beside it answers only the first dimension. A midfielder who out-scores
 * another on EP while losing on minutes security and set pieces is a
 * different bet, and that shape is what the reader is after.
 *
 * Two rules keep it honest. The normalization is stated in the caption rather
 * than implied — an axis scaled against an unnamed denominator is a number
 * pretending to be a fact. And a comparison across positions is **captioned,
 * not suppressed**: a goalkeeper against a forward is not a bug in the
 * selection, it is a comparison whose axes measure different jobs, and the
 * chart is the fastest way to see that.
 */
export default function CompareRadar(
  { gw, players, pool, components, matrix }: CompareRadarProps,
) {
  const reference = pool.length > 0 ? pool : players
  const raw = new Map(players.map(
    (p) => [p.code, axisValues(p, components, matrix, gw)]))
  const poolValues = reference.map((p) => axisValues(p, components, matrix, gw))

  const data = AXES.map(([key, label]) => {
    const column = poolValues.map((v) => v[key as keyof AxisValues])
    const row: Record<string, string | number> = { axis: label }
    for (const player of players) {
      row[player.name] = normalize(
        raw.get(player.code)![key as keyof AxisValues], column)
    }
    return row
  })

  const positions = new Set(players.map((p) => p.position))
  return (
    <div>
      <div aria-label="player comparison radar">
        <ResponsiveContainer width="100%" height={300}>
          <RadarChart data={data} outerRadius="72%">
            <PolarGrid stroke="var(--color-divider)" />
            <PolarAngleAxis dataKey="axis" stroke="var(--color-text-muted)" />
            <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
            <Tooltip contentStyle={{ background: 'var(--color-card)',
                                     border: '1px solid var(--color-border)' }} />
            <Legend />
            {players.map((player, i) => (
              <Radar key={player.code} name={player.name}
                     dataKey={player.name} fillOpacity={0.15}
                     fill={SERIES_COLOURS[i % SERIES_COLOURS.length]}
                     stroke={SERIES_COLOURS[i % SERIES_COLOURS.length]} />
            ))}
          </RadarChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-2 text-text-faint">
        {`Each axis is scaled 0–100 against the ${reference.length} players `
          + `currently ${pool.length > 0 ? 'listed in Explorer'
            : 'being compared'}. Attacking is the share of this gameweek’s `
          + 'expected points coming from goals and assists; fixtures is the '
          + `next ${FIXTURE_WEEKS} weeks, read off defensive difficulty for `
          + 'keepers and defenders and attacking difficulty for everyone else.'}
      </p>
      {positions.size > 1 && (
        <p className="mt-1 text-text-muted">
          {`These players do different jobs — ${[...positions].join(', ')} — `
            + 'so the axes are not measuring the same thing on each of them. '
            + 'Read the shapes, not the overlap.'}
        </p>
      )}
    </div>
  )
}
```

- [ ] **Mount it.** In `frontend/src/hubs/players/ComparePanel.tsx`, add `pool` to the props:

```tsx
export interface ComparePanelProps {
  gw: number
  players: PlayerRow[]
  /** The explorer's currently-filtered rows, so the radar's axes can be
   *  normalized against a pool rather than against the two to four names the
   *  reader happens to have ticked. Optional: the panel renders without it
   *  and the radar's caption says which reference it used. */
  pool?: PlayerRow[]
}

export default function ComparePanel(
  { gw, players, pool = [] }: ComparePanelProps,
) {
```

and insert the radar card between the components card and the per-player grid (after L90):

```tsx
      <Card title="Profile" className="mb-4">
        <CompareRadar gw={gw} players={players} pool={pool}
                      components={components} matrix={matrix} />
      </Card>
```

with `import CompareRadar from './CompareRadar'` at the top.

- [ ] **Verify.**

```bash
cd frontend && npx tsc --noEmit && npx vitest run
```

- [ ] **Commit.**

```bash
git add frontend/src/hubs/players/CompareRadar.tsx \
  frontend/src/hubs/players/CompareRadar.test.tsx \
  frontend/src/hubs/players/ComparePanel.tsx \
  frontend/src/hubs/players/ComparePanel.test.tsx && git commit -m "$(cat <<'EOF'
feat: five-axis compare radar, normalized against the listed pool

Attacking share, minutes security, set-piece duty, three-week fixtures and
form — every axis off a payload the panel already fetched. A cross-position
comparison is captioned, not suppressed.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 8 — the degradation rails (gate G2)

**Files:**
- Create `tests/test_v8g_degradation.py`

- [ ] **Write the rails.** Create `tests/test_v8g_degradation.py`:

```python
"""v8g's degraded states, pinned (spec G2).

Every card this cycle adds is a claim about the model's own uncertainty, which
makes a *wrong* card worse than no card: a band of width zero on a player
nobody has modelled, or a calibration curve drawn from an empty artifact, says
the tool is certain about something it has never measured. So the whole rail
set is about absence — absent artifact, absent minutes model, absent ledger,
absent σ asset — and about the one thing that must not change at all, which is
the number of job kinds.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import gaffer.optimize.scenarios as sc
from gaffer.artifacts import SolveState, save_components, save_solve_state
from gaffer.web.app import create_app

GW = 5

COMPONENTS = pd.DataFrame([
    {"code": 11, "element": 11, "name": "Saka", "position": "MID",
     "team_code": 3, "team_name": "Arsenal", "gw": GW, "opp_code": 4,
     "opp_name": "City", "was_home": 1.0, "kickoff_time": None,
     "p_play": 0.95, "p60": 0.9, "ep": 5.0}])

PLAYERS = pd.DataFrame({
    "code": [11], "element": [11], "name": ["Saka"], "position": ["MID"],
    "team_id": [1], "team_code": [3], "now_cost": [100], "status": ["a"],
    "news": [""], "chance_of_playing": [None], "selected_by_percent": [40.0],
    "form": [5.0], "points_per_game": [5.0], "ep_next": [5.0],
    "price_change_percent": [0.0], "price_change_calibrating": [False],
    "penalties_order": [1.0], "direct_freekicks_order": [None],
    "corners_and_indirect_freekicks_order": [None]})

TEAMS = pd.DataFrame({"code": [3, 4], "id": [1, 2],
                      "name": ["Arsenal", "City"],
                      "short_name": ["ARS", "MCI"]})

POOL = pd.DataFrame([
    {"code": 11, "name": "Saka", "position": "MID", "team_code": 3,
     "cost": 100, "sell": 100, "owned": True, "gw": GW, "ep_raw": 5.0}])


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    TEAMS.to_parquet(tmp_path / "data/live/teams.parquet", index=False)
    save_components(COMPONENTS, GW)
    save_solve_state(SolveState(
        gw=GW, gws=[GW], deadline="2026-09-01T11:00:00Z",
        generated_at="2026-08-31T09:00:00Z", mode="weekly", bank=0,
        free_transfers=1, owned_codes=[11], lam=0.0, league_eo={},
        avail_by_gw={GW: []},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.0, "horizon": 1, "hit_cost": 4,
             "max_transfers": 2, "bank_weight": 0.0},
        pool=POOL))
    return tmp_path, TestClient(create_app())


# --- rail 1: no evaluation artifact, no calibration cards --------------

def test_no_evaluation_is_a_422_with_a_sentence_not_a_page_of_zeros(app):
    """The Quality tab's existing contract, re-pinned because v8g adds cards
    to that tab and a new card must not invent its own empty state."""
    _, client = app
    response = client.get("/api/quality")
    assert response.status_code == 422
    assert "gaffer evaluate" in response.json()["detail"]


def test_an_evaluation_with_no_p_start_head_serves_the_others(app):
    """v8a's head is optional: an artifact written before it existed must
    still render its three older curves."""
    tmp_path, client = app
    (tmp_path / "reports/evaluation.json").write_text(json.dumps({
        "current": {"run_at": "x", "git_sha": "y", "holdout_slots": 10,
                    "stratified": {"all": {}}, "baselines": {"last5": {}},
                    "heads": {"p_play": {"log_loss": 0.4,
                                         "reliability": []}}}}))
    heads = client.get("/api/quality").json()["current"]["heads"]
    assert set(heads) == {"p_play"}


# --- rail 2: no components, no bands ----------------------------------

def test_no_components_file_means_no_bands_and_an_unchanged_headline(app):
    tmp_path, client = app
    (tmp_path / f"reports/components_gw{GW}.parquet").unlink()
    rows = client.get("/api/players").json()
    assert rows[0]["ep_next"] == pytest.approx(5.0)
    assert rows[0]["ep_lo"] is None and rows[0]["ep_hi"] is None
    assert rows[0]["p_haul"] is None and rows[0]["p_blank"] is None


def test_no_minutes_model_means_no_bands_on_the_breakdown(app):
    tmp_path, client = app
    save_components(COMPONENTS.drop(columns=["p_play", "p60"]), GW)
    player = client.get(f"/api/components/{GW}").json()["players"][0]
    assert player["ep"] == pytest.approx(5.0)
    for field in ("ep_lo", "ep_hi", "p_haul", "p_blank", "sigma"):
        assert player[field] is None, field


def test_a_band_is_never_a_zero_width_stand_in(app):
    """The rail behind A3, stated as the thing it forbids: an un-modelled
    player must not come back looking like the most certain one on the page."""
    tmp_path, client = app
    save_components(COMPONENTS.drop(columns=["p_play", "p60"]), GW)
    player = client.get(f"/api/components/{GW}").json()["players"][0]
    assert player["ep_lo"] != player["ep_hi"] or player["ep_lo"] is None


# --- rail 3: no ledger, the "too early" branch ------------------------

def test_an_empty_ledger_is_the_too_early_branch(app):
    _, client = app
    body = client.get("/api/confidence").json()
    assert body["captain"]["tier"] == "early"
    assert body["captain"]["graded"] == 0
    assert "%" not in body["captain"]["text"]


def test_a_corrupt_ledger_is_the_too_early_branch(app):
    tmp_path, client = app
    (tmp_path / "reports/decision_ledger.json").write_text("{half-written")
    assert client.get("/api/confidence").json()["captain"]["tier"] == "early"


def test_three_graded_gameweeks_still_decline_to_grade(app):
    """MIN_GRADED is a bar, not a suggestion."""
    from gaffer.confidence import MIN_GRADED

    tmp_path, client = app
    (tmp_path / "reports/decision_ledger.json").write_text(json.dumps({
        "gws": [{"gw": g, "lanes": [{"lane": "captaincy", "delta_pts": -2,
                                     "aligned": False}]}
                for g in range(1, MIN_GRADED)]}))
    assert client.get("/api/confidence").json()["captain"]["tier"] == "early"


# --- rail 4: no σ asset, the pre-v6 heuristic exactly -----------------

def test_no_noise_asset_bands_on_the_pre_v6_heuristic_exactly(monkeypatch):
    """v6's rail, copied forward to the new consumer. The band module is the
    second reader of that asset, and a clone without the file has to produce
    the same scale here as the sweep does there."""
    import gaffer.uncertainty as unc

    monkeypatch.setattr(unc, "scenario_noise", lambda: None)
    ep, xmins = 4.0, 20.0
    band = unc.band_for(ep, xmins)
    want = ep * (sc.NOISE_FLOOR_XMINS - xmins) / sc.NOISE_DENOM
    assert band.sigma == pytest.approx(round(want, 3))
    # And the centre is the EP itself: the heuristic scale is multiplicative
    # and vanishes with the EP, so ``noise_ep`` does not recentre it.
    assert band.ep_lo + band.ep_hi == pytest.approx(2 * ep, abs=0.01)


def test_an_unreadable_noise_asset_bands_on_the_heuristic(monkeypatch):
    def boom():
        raise OSError("disk")

    import gaffer.uncertainty as unc

    monkeypatch.setattr(sc, "CALIBRATED_NOISE_DEFAULT", True)
    monkeypatch.setattr(sc, "load_scenario_noise", boom)
    sc.scenario_noise.cache_clear()
    try:
        assert unc.shipped_table() is None
        assert unc.band_for(4.0, 20.0) is not None
    finally:
        sc.scenario_noise.cache_clear()


def test_the_band_module_reads_the_asset_through_one_seam():
    """If a second loader ever appears here, the rail above stops pinning
    anything: it monkeypatches exactly one name."""
    import inspect

    import gaffer.uncertainty as unc

    src = inspect.getsource(unc)
    assert "load_scenario_noise" not in src
    assert src.count("def shipped_table") == 1


# --- rail 5: no scored week, no misses card ---------------------------

def test_no_results_frame_is_an_absent_misses_card(app):
    _, client = app
    body = client.get("/api/misses").json()
    assert body == {"gw": None, "rows": []}


def test_results_for_an_unforecast_week_are_an_absent_card(app):
    tmp_path, client = app
    pd.DataFrame([{"code": 11, "gw": 99, "total_points": 8,
                   "minutes": 90}]).to_parquet(
        tmp_path / "data/live/player_gw.parquet", index=False)
    assert client.get("/api/misses").json()["gw"] is None


# --- rail 6: no sensitivity report, no noise line ---------------------

def test_no_sensitivity_report_carries_no_decision_sigma(app):
    _, client = app
    body = client.get("/api/sensitivity").json()
    assert body["available"] is False
    assert body["decision_sigma"] is None


# --- rail 7: v8g adds no job kinds ------------------------------------

def test_v8g_adds_no_job_kinds():
    """The pin five other degradation suites already assert, asserted a sixth
    time from this cycle's own file so a v8g task that reaches for a job kind
    fails in its own suite rather than in somebody else's."""
    from gaffer.web.job_kinds import JOB_KINDS

    assert len(JOB_KINDS) == 10


def test_v8g_added_no_config_key():
    """Spec D5: no config. A key added here would be a switch nobody finds
    and a degraded state nobody tests."""
    import dataclasses

    from gaffer.config import Config

    assert not [f.name for f in dataclasses.fields(Config)
                if "band" in f.name or "uncertainty" in f.name
                or "confidence" in f.name]


# --- rail 8: protected ordering, forward -----------------------------

def test_the_availability_pass_still_ends_with_the_override(app):
    """v8e's ordering pin, carried forward: v8g touches none of that path and
    the rail says so out loud rather than by omission."""
    import inspect

    from gaffer.models import availability

    src = inspect.getsource(availability.apply_availability)
    assert "_override_first_gw(out)" in src


def test_the_band_module_never_writes(app):
    """Serve-time only. A module that banked anything would be a train/serve
    seam nobody asked for."""
    import inspect

    import gaffer.uncertainty as unc

    src = inspect.getsource(unc)
    for forbidden in ("to_parquet", "write_text", "save_", "open("):
        assert forbidden not in src, forbidden
```

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_v8g_degradation.py
uv run pytest -q
```

Full suite green, and **2325 + the new tests**, with every pre-existing test unmodified. If a pre-v8g degradation file needs a change, the plan is wrong: stop and report.

- [ ] **Commit.**

```bash
git add tests/test_v8g_degradation.py && git commit -m "$(cat <<'EOF'
test: v8g degradation rails

Absent artifact, absent minutes model, absent ledger, absent sigma asset — and
the job-kind pin that says this cycle added none.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 9 — the documentation

**Files:**
- Modify `README.md`

- [ ] **Write it.** In `README.md`, add a subsection under `## Local web UI`, after `### Sensitivity and drafts (v8e)`:

```markdown
### Uncertainty and calibration (v8g)

Every expected-points number in the tool now carries the spread the optimizer
already assumed it had.

**Bands.** The squad table and the player explorer print a `Range` column
beside `xPts` — the p25 and p75 of the same noise distribution the scenario
sweep perturbs the board with. It is quartiles, not a plus-or-minus: on the
calibrated path the noise is absolute and the sweep shifts its centre down so
a clipped draw still averages the forecast, so the band is not symmetric about
the headline. A nailed-on starter's range is narrow and a rotation risk's is
wide, which is the entire point.

A player with no minutes model shows an em dash, not a range of zero width.
"We have no minutes prediction for him" is a different claim from "his minutes
are certain", and the second is the one that loses money.

**Haul and blank.** A player with a real chance of ten-plus points, or a real
chance of two or fewer, gets a chip on his row. Both come off the same
distribution as the band, which means both are **crude**: they price how wrong
the *forecast* might be, not how much football itself varies. Read `haul 18%`
as a floor.

**Captain confidence.** Under the pitch, one sentence about what the graded
record actually says: *"the model's captain outscored yours in 4 of 5
comparable gameweeks"*. Below four graded gameweeks it declines to have an
opinion and says how many it has. There is no percentage anywhere in it,
because there is nothing to compute one from.

**Sensitivity margin.** When the gap between the sweep's two candidate plans
is smaller than the noise on the players that separate them, the sensitivity
card says so instead of printing the gap as though it settled anything.

**Model → Quality** gains three things: a reliability curve for `P(starts)`
(the model has emitted it since v8a and nothing rendered it), a y = x
reference on every calibration curve with the observation count under it, a
scatter of forecast against outcome for every finished gameweek, and a table
of last week's biggest misses with the sign kept — a positive miss is a player
the model under-rated, a negative one is a transfer it may have talked you
into.

Every one of those cards is **absent** rather than empty when its artifact is
missing. Nothing here needs a new command, a new job or a config key: it all
reads what `gaffer advise`, `gaffer evaluate` and `gaffer review` have already
banked.

**Compare radar.** Ticking two to four players in Explorer now draws an
overlaid radar over attacking share, minutes security, set-piece duty,
three-week fixtures and form, each axis scaled 0–100 against the players
currently listed. Comparing a goalkeeper with a forward is allowed and
captioned: the axes measure different jobs, and the chart is the quickest way
to see that.
```

Also add the three new modules to `## Where things live`, in the file's existing table style:

```markdown
| `src/gaffer/uncertainty.py` | EP bands and haul/blank tails, off the scenario sweep's own σ table |
| `src/gaffer/confidence.py` | Ledger-derived confidence tiers — counts, never percentages |
| `src/gaffer/misses.py` | The last scored week's biggest forecast errors |
```

- [ ] **Verify.** Read the rendered section back and check every claim against what shipped — in particular that the README does not promise a card the code does not build.

- [ ] **Commit.**

```bash
git add README.md && git commit -m "$(cat <<'EOF'
docs: v8g uncertainty and calibration

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 10 — the gate checklist and the audit (orchestrator-run)

Implementers **build** this and do not run it (CONVENTIONS.md §7). Leave every box unticked.

**Files:** none. This task produces no commit of its own unless the audit finds a diff to revert.

### The protected-file audit

```bash
git diff --stat main...HEAD -- \
  src/gaffer/advise.py src/gaffer/set_pieces.py src/gaffer/optimize \
  src/gaffer/web/jobs.py src/gaffer/web/routers/jobs.py \
  src/gaffer/web/routers/whatif.py \
  tests/test_advise.py tests/test_odds.py tests/test_web_jobs.py \
  tests/test_v6_degradation.py tests/test_v7_degradation.py \
  tests/test_v7b_degradation.py tests/test_v7c_degradation.py \
  tests/test_v7d_degradation.py tests/test_v8a_degradation.py \
  tests/test_v8b_degradation.py tests/test_v8c_degradation.py \
  tests/test_v8d_degradation.py tests/test_v8e_degradation.py \
  scripts/s2_replay.py
```

Must print **nothing**. Anything at all is a plan violation: revert the file and report which task touched it.

```bash
git diff --stat main...HEAD -- data reports models logs config.toml
```

Must print nothing.

### Suites

```bash
uv run pytest -q                      # 2325 + v8g's, all green
cd frontend && npx tsc --noEmit
cd frontend && npx vitest run          # 406 + v8g's, 1 skipped
cd frontend && npm run build
```

### G1 — live render (orchestrator, on the real server)

- [ ] Bands visible on the This Week squad table, and **plausible**: pick two players at comparable EP — one boom-bust attacker, one goalkeeper — and confirm the attacker's range is the wider of the two. Record both ranges.
- [ ] A player with no minutes model (or a components file temporarily moved aside) shows an em dash in `Range`, not `0.0–0.0`.
- [ ] Model → Quality renders every calibration card off the real `reports/evaluation.json`: four reliability curves including `P(starts)`, each with the diagonal and an observation count; the forecast-vs-outcome scatter with one point per finished gameweek; the biggest-misses table naming a real player.
- [ ] The confidence line under the pitch quotes the **true** ledger count. With one reviewed gameweek that is the "too early to grade — … in 1 of 1 reviewed gameweeks" branch. Exercise it for real rather than with a fixture, and record the sentence verbatim.
- [ ] The radar renders for two comparable midfielders, and captions a GKP-vs-FWD comparison with the "different jobs" line while still drawing.
- [ ] The sensitivity card's margin line: confirm it either carries the noise qualifier or does not, and that which one it carries matches the served `decision_sigma`.

### G2 — rails

- [ ] `uv run pytest -q tests/test_v8g_degradation.py` green.

### G3 — suites and audit

- [ ] All four suite commands above green at the recorded baselines.
- [ ] Both audit commands print nothing.

### Security ritual (CONVENTIONS.md §8)

```bash
git diff main...HEAD | grep -iE "api[_-]?key|secret|token|password|Bearer "
git show main:config.toml     # must fail
```

### Spec outcome

- [ ] Fill §4 of `docs/superpowers/specs/2026-08-31-gaffer-v8g-honest-uncertainty-design.md` with what shipped, the two spot-checked ranges from G1, and the confidence sentence the live ledger produced.
