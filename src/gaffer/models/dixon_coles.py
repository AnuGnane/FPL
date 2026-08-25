"""Dixon-Coles: one coherent scoreline distribution per fixture.

The GBM team head predicts P(clean sheet) and E[goals conceded] as two
unrelated numbers from rolling form and an Elo gap, and v4a measured what
that costs: CS log loss 0.6190, the worst-calibrated head in the model. The
trouble is structural rather than a tuning problem. A clean sheet is a
*scoreline* event, the -0.5/goal deduction is the same distribution's mean,
and the saves context is its shape; a classifier and a regressor fitted
side by side can and do disagree about all three.

Dixon & Coles (1997) model the two goal counts directly: every team carries
an attack strength and a defence strength, the home side gets a fixed
advantage, and a low-score correction ``rho`` fixes independent Poisson's
well-known under-prediction of 0-0 and 1-1. Fitting is weighted maximum
likelihood with an exponential decay on match age, so last month counts for
more than two seasons ago without anyone hand-picking a window.

The class deliberately mirrors :class:`gaffer.models.team.TeamModel`'s
``fit``/``predict`` contract exactly, so the switch is one constructor site
and the protected ``blend_team_odds(`` -> ``comp.merge(tp`` seam in
``advise.predict_components`` never moves.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

GOAL_CAP = 10
"""Highest scoreline modelled. P(11+ goals for one side) is ~1e-8 at EPL
rates, and the pmf is renormalized anyway, so the truncation costs nothing
measurable and bounds every sum in here."""

DEFAULT_XI = 0.0065
"""Decay rate per day, ~1-year half-life — the published starting point.
Task 10 measures the grid {0.003, 0.0065, 0.01} and pins the winner here."""

RHO_BOUNDS = (-0.4, 0.4)
"""Bracket for the low-score correction. Real fits land near -0.1; the bound
is what stops the optimizer wandering into the region where the corrected
pmf can go negative."""


def tau_correction(x: int, y: int, lam: float, mu: float,
                   rho: float) -> float:
    """Dixon-Coles' low-score dependence factor for one scoreline.

    Independent Poisson under-predicts 0-0 and 1-1 and over-predicts 1-0 and
    0-1; ``tau`` reweights exactly those four cells and leaves every other
    scoreline alone.
    """
    if x == 0 and y == 0:
        return 1.0 - lam * mu * rho
    if x == 0 and y == 1:
        return 1.0 + lam * rho
    if x == 1 and y == 0:
        return 1.0 + mu * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def _poisson_pmf(mu: float, cap: int = GOAL_CAP) -> np.ndarray:
    mu = max(float(mu), 1e-9)
    return np.array([math.exp(-mu) * mu ** k / math.factorial(k)
                     for k in range(cap + 1)])


def scoreline_pmf(lam: float, mu: float, rho: float,
                  cap: int = GOAL_CAP) -> np.ndarray:
    """``P[x, y]`` for home ``x`` goals and away ``y`` goals.

    Clipped at zero and renormalized: an extreme ``rho`` against an extreme
    ``lam*mu`` can push the 0-0 cell negative, and a negative probability
    downstream is a crash waiting for a quiet fixture. Renormalization also
    absorbs the truncation at ``cap``.
    """
    ph, pa = _poisson_pmf(lam, cap), _poisson_pmf(mu, cap)
    out = np.outer(ph, pa)
    out[0, 0] *= tau_correction(0, 0, lam, mu, rho)
    out[0, 1] *= tau_correction(0, 1, lam, mu, rho)
    out[1, 0] *= tau_correction(1, 0, lam, mu, rho)
    out[1, 1] *= tau_correction(1, 1, lam, mu, rho)
    out = np.clip(out, 0.0, None)
    total = out.sum()
    return out / total if total > 0 else np.full(out.shape,
                                                 1.0 / out.size)


def fixture_outcomes(lam: float, mu: float, rho: float,
                     cap: int = GOAL_CAP) -> dict[str, float]:
    """Everything downstream needs, read off one scoreline distribution.

    Clean sheets, the goals-conceded mean behind the -0.5/goal deduction,
    result probabilities for the fixture ticker and the 2+ conceded band all
    come from the same joint pmf, so they cannot contradict each other the
    way a separate classifier and regressor could.
    """
    pmf = scoreline_pmf(lam, mu, rho, cap)
    goals = np.arange(cap + 1, dtype="float64")
    home_marg, away_marg = pmf.sum(axis=1), pmf.sum(axis=0)
    idx_h, idx_a = np.indices(pmf.shape)
    return {
        "p_cs_home": float(pmf[:, 0].sum()),
        "p_cs_away": float(pmf[0, :].sum()),
        "e_gc_home": float((away_marg * goals).sum()),
        "e_gc_away": float((home_marg * goals).sum()),
        "p_home_win": float(pmf[idx_h > idx_a].sum()),
        "p_draw": float(pmf[idx_h == idx_a].sum()),
        "p_away_win": float(pmf[idx_h < idx_a].sum()),
        "p_gc2_home": float(pmf[:, 2:].sum()),
        "p_gc2_away": float(pmf[2:, :].sum()),
    }
