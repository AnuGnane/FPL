"""Gate §4.4: does the availability draw collapse the captain's support?

Spec §4.4's rule, pre-registered: scenario support for the live captain must
not fall below its current value by more than 10 points on the same inputs.
The number is what S1 recorded as the failure signature of a sweep gone wrong
— captain support 92% -> 22%, after which the gate found no move that cleared
threshold on its own and advised a plan carrying -20 in hits. So this is not a
generic sanity check; it is that failure, watched for by name.

Two arms on **one board**: the saved solve state, the same seed, the same
noise stream, differing only in whether availability was drawn. The board is
built exactly as ``sensitivity.run_sensitivity`` builds it — saved state, raw
EP, cover, tilt, ``milp_pool``, ``solve_kw_from_state`` — because a support
number measured on a different board than the advice ran on is a number about
nothing.

**The lever guard**, this repo's twice-learned lesson (v10 plan A3): before
anything is measured, the driver checks that p_play covers the pool and that
the on-arm actually blanked at least one cell. If it did not, both arms are
the same arm and the delta below is a decorated zero. It exits rather than
printing one.

Run it, watch it, read the line::

    mkdir -p logs && caffeinate -i nohup .venv/bin/python \\
        scripts/v12_w3_support.py > logs/v12_w3_support.log 2>&1 &
    grep -e W3_SUPPORT_LEVER -e W3_SUPPORT_DONE logs/v12_w3_support.log
"""

from __future__ import annotations

import json
import sys

import numpy as np

from gaffer.artifacts import (latest_gw, load_advice, load_components,
                              load_solve_state, milp_pool, raw_ep_by,
                              solve_kw_from_state)
from gaffer.league_mode import cover_from_eo, tilt_ep
from gaffer.optimize.milp import SolveInput
from gaffer.optimize.policy import captain_frequency_of
from gaffer.optimize.scenarios import (availability_draw, move_frequencies,
                                       run_scenarios, xmins_by_player_gw)

N = 40
"""The advice path's own sweep size, not sensitivity's twenty. The gate is
about the sweep that decides."""


def _p_play(comp, gws: list[int]) -> dict[int, dict[int, float]]:
    """``advise.py``'s expression, for the same reason it is a mean:
    "did he turn out at all" is one outcome across a double gameweek."""
    if "p_play" not in comp.columns:
        return {}
    out: dict[int, dict[int, float]] = {}
    grouped = (comp.groupby(["code", "gw"], as_index=False)
               .agg(p_play=("p_play", "mean")))
    for row in grouped.itertuples():
        if int(row.gw) in gws:
            out.setdefault(int(row.code), {})[int(row.gw)] = float(row.p_play)
    return out


def main() -> None:
    gw = latest_gw()
    if gw is None:
        raise SystemExit("no saved solve state — run `gaffer advise` first")
    state = load_solve_state(gw)
    advice = load_advice(gw)
    horizon = state.opt.get("horizon") or len(state.gws)
    gws = state.gws[:max(1, int(horizon))]
    ep_by = raw_ep_by(state)
    cover = (state.cover if state.cover is not None
             else cover_from_eo(state.league_eo))
    pool = milp_pool(state, tilt_ep(ep_by, cover, state.lam), gws)
    opt = solve_kw_from_state(state)
    comp = load_components(gw)
    xmins = xmins_by_player_gw(comp)
    p_play = _p_play(comp, gws)
    solve_state = SolveInput(owned_codes=state.owned_codes, bank=state.bank,
                             free_transfers=state.free_transfers, gws=gws)

    # --- the lever guard --------------------------------------------------
    if not xmins:
        raise SystemExit(
            "no expected minutes on this board: every scenario draws the same "
            "EP and the support numbers below would be 100% by construction.")
    priced = sum(len(cell) for cell in pool["ep"])
    covered = sum(1 for code, cell in zip(pool["code"], pool["ep"])
                  for g in cell if int(g) in (p_play.get(int(code)) or {}))
    blanked = len(availability_draw(pool, p_play, np.random.default_rng(1)))
    if not covered or not blanked:
        raise SystemExit(
            f"the lever is disconnected: {covered} of {priced} priced cells "
            f"carry a p_play and one draw blanked {blanked} of them, so the "
            f"two arms below are the same arm.")
    print("W3_SUPPORT_LEVER", json.dumps(
        {"priced": priced, "covered": covered, "blanked_one_draw": blanked}),
        flush=True)

    # --- the two arms -----------------------------------------------------
    # The advice path's own per-gameweek seed, not sensitivity's million-clear
    # offset: this gate is about the sweep that decided, so it replays that
    # sweep's draws. ``SolveState.opt`` does not carry the seed — it holds the
    # solver bundle — so it comes from the config, exactly as advise reads it.
    from gaffer.config import serving_config

    seed = int(serving_config().scenarios_seed) + int(gw)
    captain = int(advice["captain"]["code"])
    out = {"gw": int(gw), "captain": captain, "seed": seed, "n": N}
    for arm, draw in (("off", False), ("on", True)):
        run = run_scenarios(pool, solve_state, xmins, n=N, seed=seed,
                            p_play=p_play, draw_availability=draw, **opt)
        freqs = move_frequencies(run.plans)
        support = captain_frequency_of(freqs, captain)
        out[f"support_{arm}"] = None if support is None else round(
            support * 100, 1)
        out[f"completed_{arm}"] = int(run.completed)
    if out["support_off"] is None or out["support_on"] is None:
        # The live captain not appearing in an arm at all is a support of
        # zero for this gate's purpose: he was never chosen.
        out["support_off"] = out["support_off"] or 0.0
        out["support_on"] = out["support_on"] or 0.0
    out["drop_pts"] = round(out["support_off"] - out["support_on"], 1)
    out["passes"] = bool(out["drop_pts"] <= 10.0)
    print("W3_SUPPORT_DONE", json.dumps(out), flush=True)
    sys.exit(0 if out["passes"] else 1)


if __name__ == "__main__":
    main()
