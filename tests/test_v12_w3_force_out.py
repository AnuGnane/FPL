"""§4.1: "sell this player", and the proof that saying nothing changes nothing.

Two halves. The first is the constraint: a forced-out player is gone from
every horizon week, the bank receives his sell price (which is what separates
this from ``locked_out``, where he simply vanishes), and a contradiction is
refused by name rather than by the solver's word "Infeasible".

The second is the regression guard the workstream was asked for. Comparing two
solved plans would only prove the *answers* matched, and the failure this
guards against — a constraint emitted for an empty list, shifting every
auto-generated constraint name after it — does not change an answer. So the
LP itself is captured: ``_solve_once`` hands the built problem to
``milp._solve`` as one argument, which a monkeypatch can write out with
``writeLP``. ``tests/data/v12_w3_milp_golden.lp`` was generated from
``milp.py`` **before** this cycle touched it, and the rail is byte equality
against that file.

Regenerating the golden is a deliberate act, not a fix: it is only valid from a
commit whose LP-building code is unchanged. A failure here after a PuLP
upgrade is a formatting change; a failure here after an ``optimize`` edit is
the thing the file exists to catch.

One thing the capture must neutralise. Since W2 §3.4 ``solve_plan`` reads
``price_timing.owned_price_falls(state.owned_codes)``, which consults
``config.toml`` and ``data/live/price_log.parquet`` and caches on the snapshot
date. A golden generated through that would be a golden of *today's price log*
— it would pass on the day it was written and fail every day after. So the
reader is patched to ``{}`` (its own off-switch value) and its cache cleared,
which is exactly the arithmetic the pre-W2 code did.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from gaffer.errors import GafferError
from gaffer.optimize import milp
from gaffer.optimize.milp import SolveInput, solve_plan

GOLDEN = Path("tests/data/v12_w3_milp_golden.lp")

GWS = [1, 2]
KW = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
          itb_value=0.05, hit_cost=4, bench_curve=[0.21, 0.06, 0.002])
OWNED = [1, 2, 5, 6, 7, 8, 9, 14, 15, 16, 17, 18, 22, 23, 24]


def _pool() -> pd.DataFrame:
    """A pinned pool, defined here and imported by nothing.

    The golden is a function of these numbers, so a pool that drifts is a
    golden that fails for a reason that has nothing to do with the solver.
    """
    rows, code = [], 1
    for pos, n in [("GKP", 4), ("DEF", 9), ("MID", 10), ("FWD", 7)]:
        for i in range(n):
            rows.append({"code": code, "position": pos,
                         "team_code": (code % 6) + 1,
                         "cost": 40 + i, "sell": 40 + i,
                         "ep": {1: 1.0 + (code % 7) * 0.3,
                                2: 2.0 + (code % 5) * 0.2}})
            code += 1
    return pd.DataFrame(rows)


def _state(**kw) -> SolveInput:
    base = dict(owned_codes=list(OWNED), bank=0, free_transfers=2, gws=GWS)
    return SolveInput(**{**base, **kw})


def _capture_lp(tmp_path: Path, state: SolveInput, **kw) -> list[str]:
    """Every LP ``solve_plan`` builds for this call, as text."""
    from gaffer import price_timing

    out: list[str] = []
    real = milp._solve

    def spy(prob):
        path = tmp_path / f"model{len(out)}.lp"
        path.parent.mkdir(parents=True, exist_ok=True)
        prob.writeLP(str(path))
        out.append(path.read_text())
        real(prob)

    price_timing.owned_price_falls.cache_clear()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(milp, "_solve", spy)
        # The price term is live data (W2 §3.4). Held at its off-switch value
        # so the capture is a function of this file's fixture and nothing else.
        # Cleared either side because the real reader caches on
        # (snap_date, owned) and this file shares that key with its neighbours.
        mp.setattr(price_timing, "owned_price_falls", lambda owned: {})
        solve_plan(_pool(), state, **KW, **kw)
    price_timing.owned_price_falls.cache_clear()
    return out


def write_golden() -> None:
    """Regenerate the golden. Run from a commit with milp.py unedited::

        .venv/bin/python -c "import tests.test_v12_w3_force_out as t; \\
            t.write_golden()"
    """
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    text = _capture_lp(tmp, _state())[0]
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(text)
    print(f"wrote {GOLDEN} ({len(text)} bytes)")


# --- the regression guard -------------------------------------------------

def test_the_lp_capture_is_stable_on_one_code_base(tmp_path):
    """Asked first, so a golden mismatch below is never blamed on the
    instrument. Two captures of the same solve on the same code must be the
    same bytes, or nothing else in this file means anything."""
    a = _capture_lp(tmp_path / "a", _state())
    b = _capture_lp(tmp_path / "b", _state())
    assert a == b


def test_an_empty_force_out_builds_the_pre_change_lp_byte_for_byte(tmp_path):
    """The brief's guard. ``tests/data/v12_w3_milp_golden.lp`` came off the
    code as it stood before ``force_out`` existed."""
    captured = _capture_lp(tmp_path, _state())
    assert len(captured) == 1
    assert captured[0] == GOLDEN.read_text()


def test_a_populated_force_out_does_change_the_lp(tmp_path):
    """The other direction, and the reason the test above is not vacuous: if
    the constraint were never emitted at all, both assertions would pass."""
    captured = _capture_lp(tmp_path, _state(force_out=[1]))
    assert captured[0] != GOLDEN.read_text()


# --- the constraint -------------------------------------------------------

def test_a_forced_out_player_is_in_no_gameweek_of_the_horizon():
    plan = solve_plan(_pool(), _state(force_out=[5]), **KW)
    for gp in plan.gw_plans:
        assert 5 not in gp.squad
        assert 5 not in gp.xi


def test_a_forced_out_player_is_sold_in_the_first_week_and_not_later():
    """Continuity spends the ownership immediately; a sale in week two would
    mean he was owned in week one, which the constraint forbids."""
    plan = solve_plan(_pool(), _state(force_out=[5]), **KW)
    assert 5 in plan.gw_plans[0].sells
    assert all(5 not in gp.sells for gp in plan.gw_plans[1:])


def test_the_bank_receives_the_sale_which_is_what_locked_out_never_did():
    """The distinction the module note now carries, priced exactly.

    Both instructions take player 5 out of the squad and both make the solver
    buy a replacement. Only one of them pays for it. On this fixture the
    difference is the whole difference: ``force_out`` solves, ``locked_out``
    is infeasible, and handing the banned solve player 5's sell price — 40,
    the money the sale would have raised — makes it feasible and lands it on
    the identical answer.
    """
    sold = solve_plan(_pool(), _state(force_out=[5]), **KW)
    assert len(sold.gw_plans[0].squad) == 15
    assert 5 in sold.gw_plans[0].sells
    # The forced sale funds a replacement the ban cannot afford: the banned
    # solve never had 5's sell value to spend.
    assert sold.gw_plans[0].buys
    with pytest.raises(RuntimeError, match="MILP not optimal"):
        solve_plan(_pool(), _state(locked_out=[5]), **KW)
    # 40 is player 5's `sell`. Given it as bank, the ban reaches the same
    # squad — which is the proof that the money is the only thing that differs.
    funded = solve_plan(_pool(), _state(locked_out=[5], bank=40), **KW)
    assert funded.gw_plans[0].buys == sold.gw_plans[0].buys


def test_forcing_out_a_player_you_do_not_own_is_not_an_error():
    """He is already out. A no-op constraint is the honest answer — refusing
    would make the board's "must sell" button illegal on a row the plan had
    already sold."""
    assert 12 not in OWNED                      # in the pool, never owned
    plan = solve_plan(_pool(), _state(force_out=[12]), **KW)
    assert all(12 not in gp.squad for gp in plan.gw_plans)


def test_a_code_outside_the_pool_is_refused_by_name():
    with pytest.raises(GafferError, match="force_out: player code 9999"):
        solve_plan(_pool(), _state(force_out=[9999]), **KW)


def test_locking_in_and_forcing_out_the_same_player_is_refused_by_name():
    """The solver would say "MILP not optimal: Infeasible" and name nobody."""
    with pytest.raises(GafferError, match="also locked in"):
        solve_plan(_pool(), _state(locked_in=[5], force_out=[5]), **KW)


def test_forcing_out_more_than_the_budget_can_replace_stays_infeasible():
    """Spec §4.1's infeasible case. It is a RuntimeError from ``_solve_once``,
    which ``routers/whatif.py`` already turns into the payload naming the
    constraints — Task 2 adds ``force_out`` to that sentence."""
    # The three cheapest owned midfielders. Their replacements cost more than
    # their sale raises, and the fixture's budget has 14 (0.1m) of slack.
    poor = _state(bank=0, force_out=[14, 15, 16])
    with pytest.raises(RuntimeError, match="MILP not optimal"):
        solve_plan(_pool(), poor, **KW)


def test_force_out_survives_a_second_pass(tmp_path):
    """§F1a's re-weighted pass re-solves the same problem with pins taken from
    pass one. A constraint that lived only in pass one would be silently
    dropped by every p_play-carrying caller."""
    pool = _pool()
    p_play = {int(c): {g: 0.5 + (int(c) % 5) * 0.1 for g in GWS}
              for c in pool["code"]}
    plan = solve_plan(pool, _state(force_out=[5]), **KW, p_play=p_play)
    assert all(5 not in gp.squad for gp in plan.gw_plans)
