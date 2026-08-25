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
"""Decay rate per day, ~1-year half-life — the published Dixon-Coles value.

Measured on the current-mode holdout over the grid {0.003, 0.0065, 0.01}:
CS log loss 0.5510 / 0.5506 / 0.5505 — flat to within noise on ~200 held-out
team-gameweeks, so the published value stays. See the v4b spec's Outcome
table."""

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


PARAM_BOUNDS = (-3.0, 3.0)
"""Bracket on log attack/defence. exp(3) = 20 goals expected — no real team
is anywhere near it, and the bound keeps L-BFGS-B out of the flat regions a
club with three matches of history can otherwise wander into."""

GAMMA_BOUNDS = (-1.0, 1.0)
MAX_ITER = 500
PROMOTED_FALLBACK_TEAMS = 3
"""How many bottom finishers the promoted-team prior averages. Three is the
number that go down, so it is exactly the group the promoted clubs replace."""


def _unpack(theta: np.ndarray, n: int):
    """Free parameter vector -> (attack, defence, gamma, rho).

    Attack carries only ``n - 1`` free values; the last is minus their sum,
    which *is* the mean(log attack) = 0 constraint. Reparameterizing rather
    than adding an equality constraint keeps the problem inside L-BFGS-B,
    which is bound-constrained only and much faster than the alternatives.
    """
    free = theta[:n - 1]
    attack = np.empty(n)
    attack[:n - 1] = free
    attack[n - 1] = -free.sum()
    defence = theta[n - 1:2 * n - 1]
    return attack, defence, float(theta[2 * n - 1]), float(theta[2 * n])


def _tau_vec(x: np.ndarray, y: np.ndarray, lam: np.ndarray, mu: np.ndarray,
             rho: float) -> np.ndarray:
    """:func:`tau_correction` over whole arrays of matches."""
    out = np.ones_like(lam)
    out = np.where((x == 0) & (y == 0), 1.0 - lam * mu * rho, out)
    out = np.where((x == 0) & (y == 1), 1.0 + lam * rho, out)
    out = np.where((x == 1) & (y == 0), 1.0 + mu * rho, out)
    out = np.where((x == 1) & (y == 1), 1.0 - rho, out)
    return out


def _nll(theta, hi, ai, hg, ag, lgh, lga, w, n) -> float:
    """Negative time-weighted log likelihood of every match at once."""
    attack, defence, gamma, rho = _unpack(theta, n)
    log_lam = attack[hi] + defence[ai] + gamma
    log_mu = attack[ai] + defence[hi]
    lam, mu = np.exp(log_lam), np.exp(log_mu)
    # A tau driven negative by an extreme rho would make the log undefined;
    # clipping turns that into a very bad likelihood instead of a crash, and
    # the optimizer walks back out on its own.
    tau = np.clip(_tau_vec(hg, ag, lam, mu, rho), 1e-10, None)
    ll = np.log(tau) + hg * log_lam - lam - lgh + ag * log_mu - mu - lga
    return -float(np.dot(w, ll))


class DixonColesModel:
    """P(clean sheet) and E[goals conceded] from a fitted scoreline model.

    Interface-compatible with :class:`gaffer.models.team.TeamModel`: same
    ``fit(team_gw)`` input frame, same ``predict(team_gw)`` output columns
    ``[code, season_idx, gw, p_cs, e_gc]``. That parity is the whole point —
    it makes the swap a single constructor site in
    :func:`gaffer.models.train.train_all` and leaves the protected
    ``blend_team_odds(`` -> ``comp.merge(tp`` seam untouched.

    ``fit`` takes the *team-gw* frame rather than a fixture frame, even
    though the model is fundamentally about matches, because that is what the
    training path already has in hand; the home rows are folded back into
    matches internally.
    """

    def __init__(self, xi: float = DEFAULT_XI, cap: int = GOAL_CAP):
        self.xi = float(xi)
        self.cap = int(cap)

    @staticmethod
    def matches_from_team_gw(tg: pd.DataFrame) -> pd.DataFrame:
        """Fold the two rows per match back into one.

        ``build_team_gw`` doubles every fixture so each team owns a row; the
        home rows alone carry the whole match, opponent and both scorelines
        included.
        """
        home = tg[tg["home"] == 1.0]
        return pd.DataFrame({
            "season_idx": home["season_idx"].to_numpy(),
            "gw": home["gw"].to_numpy(),
            "kickoff_time": home["kickoff_time"].to_numpy(),
            "home_code": home["code"].to_numpy(),
            "away_code": home["opp_code"].to_numpy(),
            "home_goals": pd.to_numeric(home["gf"], errors="coerce").to_numpy(),
            "away_goals": pd.to_numeric(home["ga"], errors="coerce").to_numpy(),
        }).dropna(subset=["home_goals", "away_goals"]).reset_index(drop=True)

    def _fallback(self, matches: pd.DataFrame, codes: list,
                  attack: np.ndarray, defence: np.ndarray) -> None:
        """Prior for a club with no top-flight history: the mean of the
        bottom three finishers' parameters.

        A promoted side is, on the evidence, about as good as the sides it
        replaced, and that is a far better opening prior than either the
        league mean (too generous) or the worst team (too harsh).
        """
        index = {c: i for i, c in enumerate(codes)}
        latest = matches[matches["season_idx"] == matches["season_idx"].max()]
        # Only the clubs that actually played in the latest season have a
        # table position in it. Seeding every code the fit ever saw leaves a
        # side relegated seasons ago sitting on zero points, and three such
        # ghosts then win "bottom three" ahead of the teams really down there.
        present = set(latest["home_code"]) | set(latest["away_code"])
        points: dict = {c: 0.0 for c in codes if c in present}
        for m in latest.itertuples():
            if m.home_goals > m.away_goals:
                points[m.home_code] += 3.0
            elif m.home_goals < m.away_goals:
                points[m.away_code] += 3.0
            else:
                points[m.home_code] += 1.0
                points[m.away_code] += 1.0
        order = sorted(points, key=lambda c: (points[c], c))
        bottom = order[:PROMOTED_FALLBACK_TEAMS]
        self.bottom_codes_ = bottom
        self.fallback_attack_ = float(np.mean([attack[index[c]] for c in bottom]))
        self.fallback_defence_ = float(
            np.mean([defence[index[c]] for c in bottom]))

    def fit(self, tg: pd.DataFrame) -> "DixonColesModel":
        """Weighted MLE over every completed match in the frame.

        Each match is weighted ``exp(-xi * days)`` back from the newest
        kickoff present, so the fit is always anchored on the data's own end
        rather than on wall-clock now — which is what makes a backtest at an
        earlier cut behave like a live run at that date.
        """
        from scipy.optimize import minimize
        from scipy.special import gammaln

        matches = self.matches_from_team_gw(tg)
        codes = sorted(set(matches["home_code"]) | set(matches["away_code"]))
        index = {c: i for i, c in enumerate(codes)}
        n = len(codes)
        hi = matches["home_code"].map(index).to_numpy()
        ai = matches["away_code"].map(index).to_numpy()
        hg = matches["home_goals"].to_numpy(dtype="float64")
        ag = matches["away_goals"].to_numpy(dtype="float64")
        lgh, lga = gammaln(hg + 1.0), gammaln(ag + 1.0)
        kt = pd.to_datetime(matches["kickoff_time"], utc=True, format="mixed")
        days = (kt.max() - kt).dt.total_seconds().to_numpy() / 86400.0
        weights = np.exp(-self.xi * days)

        x0 = np.concatenate([np.zeros(2 * n - 1), [0.25], [0.0]])
        bounds = ([PARAM_BOUNDS] * (2 * n - 1) + [GAMMA_BOUNDS] + [RHO_BOUNDS])
        res = minimize(_nll, x0,
                       args=(hi, ai, hg, ag, lgh, lga, weights, n),
                       method="L-BFGS-B", bounds=bounds,
                       options={"maxiter": MAX_ITER})
        attack, defence, gamma, rho = _unpack(res.x, n)
        self.codes_ = codes
        self.attack_ = {c: float(attack[index[c]]) for c in codes}
        self.defence_ = {c: float(defence[index[c]]) for c in codes}
        self.gamma_, self.rho_ = gamma, rho
        self.converged_ = bool(res.success)
        self._fallback(matches, codes, attack, defence)
        return self

    def _params(self, code) -> tuple[float, float]:
        """Attack/defence for one club, promoted fallback where unseen."""
        return (self.attack_.get(code, self.fallback_attack_),
                self.defence_.get(code, self.fallback_defence_))

    def predict(self, tg: pd.DataFrame) -> pd.DataFrame:
        """One row per input row: code, season_idx, gw, p_cs, e_gc.

        Byte-for-byte the same contract as :meth:`TeamModel.predict`, and
        positional like every other component: a double gameweek's two
        fixtures stay two rows, because the caller stitches on position and
        would otherwise attach one fixture's clean sheet to both.

        A row whose ``home`` is missing is treated as neutral (no home
        advantage either way) rather than raising — the simple component path
        hands over frames without it.
        """
        out = tg[["code", "season_idx", "gw"]].copy().reset_index(drop=True)
        rows = tg.reset_index(drop=True)
        home = (pd.to_numeric(rows["home"], errors="coerce").fillna(0.5)
                if "home" in rows.columns
                else pd.Series(0.5, index=rows.index, dtype="float64"))
        p_cs, e_gc = [], []
        for code, opp, is_home in zip(rows["code"], rows["opp_code"], home):
            att, dfn = self._params(code)
            opp_att, opp_dfn = self._params(opp)
            # gamma is the *home* team's edge; a neutral 0.5 splits it, which
            # is what a frame with no home flag deserves.
            lam = math.exp(att + opp_dfn + self.gamma_ * float(is_home))
            mu = math.exp(opp_att + dfn
                          + self.gamma_ * (1.0 - float(is_home)))
            stats = fixture_outcomes(lam, mu, self.rho_, self.cap)
            p_cs.append(stats["p_cs_home"])
            e_gc.append(stats["e_gc_home"])
        out["p_cs"] = p_cs
        out["e_gc"] = e_gc
        return out


BLEND_FOLDS_PER_SEASON = 2
"""Walk-forward granularity for the blend-weight frame.

Refitting Dixon-Coles before every fixture would be honest and unusable; per
half-season it is 10 fits over five seasons, each on strictly earlier data.
The weight being estimated is one scalar, and it does not move at the
resolution the extra fidelity would buy.
"""


def walk_forward_cs(tg: pd.DataFrame, match_odds: pd.DataFrame,
                    xi: float = DEFAULT_XI) -> pd.DataFrame:
    """Out-of-sample model and odds clean-sheet probabilities, side by side.

    For each half-season fold after the first, Dixon-Coles is fitted on every
    match strictly before the fold and used to predict the fold's fixtures;
    the closing odds for the same fixtures are inverted to independent-Poisson
    mus and turned into ``p_cs_odds = exp(-mu_against)``, the identical
    assumption :func:`gaffer.models.team.blend_team_odds` makes at serve time.
    Realized ``cs`` comes along as the target.

    Returns ``[season_idx, gw, code, opp_code, p_cs_odds, p_cs_model, cs]``,
    two rows per priced fixture. An empty frame means there is nothing to fit
    a weight on — no odds file, or no fold with data on both sides.
    """
    from gaffer.data.odds import invert_odds

    empty = pd.DataFrame(columns=["season_idx", "gw", "code", "opp_code",
                                  "p_cs_odds", "p_cs_model", "cs"])
    if match_odds is None or match_odds.empty:
        return empty
    # Odds -> per-team expected goals against, once for the whole history.
    mus = [invert_odds(float(m.p_home), float(m.p_draw), float(m.p_away),
                       float(m.p_over25)) for m in match_odds.itertuples()]
    odds_rows = []
    for (mu_h, mu_a), m in zip(mus, match_odds.itertuples()):
        odds_rows.append({"season_idx": m.season_idx, "gw": m.gw,
                          "code": m.home_code, "opp_code": m.away_code,
                          "p_cs_odds": math.exp(-mu_a)})
        odds_rows.append({"season_idx": m.season_idx, "gw": m.gw,
                          "code": m.away_code, "opp_code": m.home_code,
                          "p_cs_odds": math.exp(-mu_h)})
    odds_cs = pd.DataFrame(odds_rows)

    played = tg.dropna(subset=["ga"]).copy()
    played["_fold"] = (played["season_idx"].astype(int) * BLEND_FOLDS_PER_SEASON
                       + (played["gw"].astype(int) > 19).astype(int))
    folds = sorted(played["_fold"].unique())
    out = []
    for fold in folds[1:]:
        before = played[played["_fold"] < fold]
        current = played[played["_fold"] == fold]
        if before.empty or current.empty:
            continue
        model = DixonColesModel(xi=xi).fit(before)
        pred = model.predict(current)
        block = current[["season_idx", "gw", "code", "opp_code", "cs"]].copy()
        block = block.reset_index(drop=True)
        block["p_cs_model"] = pred["p_cs"].to_numpy()
        out.append(block)
    if not out:
        return empty
    frame = pd.concat(out, ignore_index=True).merge(
        odds_cs, on=["season_idx", "gw", "code", "opp_code"], how="inner")
    frame["cs"] = pd.to_numeric(frame["cs"], errors="coerce").astype(float)
    return frame[["season_idx", "gw", "code", "opp_code", "p_cs_odds",
                  "p_cs_model", "cs"]]
