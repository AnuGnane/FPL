"""The shadow price of a banked free transfer.

``ft_value = 1.5`` is one number standing in for a function of two variables.
A transfer banked in GW6 with one in hand is an option on thirty-two weeks of
opportunities; the same transfer banked in GW36 with five in hand is an option
on two weeks you were going to spend anyway. Pricing them identically is why
the optimizer banks when it should spend and spends when it should bank, and
why the hit rule — take a hit when the gain beats four points — is wrong in
both directions: the true bar is ``hit_cost + lambda(k, t)``, because a hit
does not only cost four points, it also does not consume the FT you were
holding.

The DP is deliberately tiny. State ``(k, t)``: k free transfers held, t
gameweeks remaining. Each week the best available transfer is worth a draw
``s`` from a calibrated surplus distribution; you may spend ``j`` of your k
transfers on that week's board, and then one FT arrives, capped at five with
the overflow lost::

    V(k, 0) = 0
    V(k, t) = E_s[ max_{0 <= j <= k} ( s * W(j) + V(min(k - j + 1, cap), t-1) ) ]

which for k = 0 collapses to the "nothing to spend" line ``V(0, t) =
V(min(1, cap), t - 1)``. The shadow price is the difference between adjacent
states, ``lambda(k, t) = V(k, t) - V(k-1, t)``.

``W(j)`` is the only modelling choice here, and it is the one that makes the
whole table non-trivial. A one-transfer-per-week model prices the *second*
banked transfer at exactly zero — with an FT arriving every week you are never
constrained, so holding two is worth precisely what holding one is worth, and
every lambda above k = 1 collapses. What a bank is actually for is spending
several transfers in one week, and the second transfer you make on a given
board is worth less than the first because you took the best one first. ``W``
is that within-week concavity: the j-th transfer of a week is worth ``s / j``,
so ``W(j)`` is the j-th harmonic number. Harmonic rather than a tuned decay
because it introduces no constant to be wrong about, and the qualitative
claims the table is used for — decreasing in k, decaying in t, the fifth
transfer nearly worthless — hold for any concave ``W``.

The surplus distribution is empirical — a list of per-week best-single-transfer
gains from replay (see ``calibrate_decisions``) — so the expectation is a plain
mean over samples and there is no distributional assumption to be wrong about.
"""

from __future__ import annotations

FT_CAP = 5
"""Maximum banked free transfers. FPL's rule since 2024-25; the overflow is
lost, which is what makes the fifth transfer worth so much less than the
fourth."""


def within_week_value(j: int) -> float:
    """Multiplier on the week's best-transfer surplus for making ``j`` moves.

    The j-th harmonic number: the first transfer of a week is worth the full
    draw, the second half of it, the third a third. Concave, parameter-free,
    and zero at ``j = 0``.
    """
    return sum(1.0 / i for i in range(1, int(j) + 1))


def value_table(surplus: list[float], weeks: int,
                cap: int = FT_CAP) -> dict[tuple[int, int], float]:
    """``V(k, t)`` by backward value iteration.

    ``surplus`` is an empirical sample of the weekly best-single-transfer
    gain; the expectation is the plain mean over it. Negative samples are kept
    rather than filtered — nobody is *forced* to transfer, and the ``j = 0``
    branch of the maximum is what encodes that, so filtering would
    double-count the option.
    """
    if not surplus:
        raise ValueError(
            "lambda DP needs a non-empty surplus distribution — an empty one "
            "prices every free transfer at zero, which turns the objective "
            "into 'always take the hit'")
    w = [within_week_value(j) for j in range(cap + 1)]
    v: dict[tuple[int, int], float] = {(k, 0): 0.0 for k in range(cap + 1)}
    for t in range(1, weeks + 1):
        for k in range(cap + 1):
            # Spend j, then the weekly arrival takes you to k - j + 1 (capped,
            # overflow lost).
            after = [v[(min(k - j + 1, cap), t - 1)] for j in range(k + 1)]
            v[(k, t)] = sum(
                max(s * w[j] + after[j] for j in range(k + 1))
                for s in surplus) / len(surplus)
    return v


def lambda_table(surplus: list[float], weeks: int,
                 cap: int = FT_CAP) -> dict[tuple[int, int], float]:
    """``lambda(k, t) = V(k, t) - V(k-1, t)`` for k in 1..cap.

    Clamped at zero. The DP is monotone in k by construction, but a
    pathological surplus sample plus floating-point noise can produce a
    negative sliver, and a negative shadow price would tell the MILP to throw
    transfers away.
    """
    v = value_table(surplus, weeks, cap)
    return {(k, t): max(0.0, v[(k, t)] - v[(k - 1, t)])
            for k in range(1, cap + 1) for t in range(1, weeks + 1)}


class LambdaLookup:
    """A ``lambda(k, t)`` table with sane behaviour off its edges.

    Empty means "no calibration shipped", and every lookup is zero — the
    caller's cue to fall back to the flat ``ft_value``. Off-table ``k`` and
    ``t`` clamp to the nearest row rather than raising: a horizon that runs
    past GW38 in the last week of the season is normal, not exceptional.
    """

    def __init__(self, table: dict[tuple[int, int], float]):
        self._t = dict(table)
        self._ks = sorted({k for k, _ in self._t}) if self._t else []
        self._ts = sorted({t for _, t in self._t}) if self._t else []

    @property
    def empty(self) -> bool:
        return not self._t

    def __call__(self, k: int, t: int) -> float:
        if not self._t or k <= 0:
            return 0.0
        kk = min(max(int(k), self._ks[0]), self._ks[-1])
        tt = min(max(int(t), self._ts[0]), self._ts[-1])
        return float(self._t.get((kk, tt), 0.0))

    def bank_value(self, k: int, t: int) -> float:
        """Total value of holding ``k`` transfers — what a wildcard destroys."""
        return sum(self(j, t) for j in range(1, int(k) + 1))
