"""§F1a's denominator: what a typical XI's did-not-play rate actually is.

``xi_frailty = mean(1 - p_play over the XI) / POPULATION_DNP`` is only a
*modulator* around the calibrated bench curve if the divisor really is the
typical XI's rate. Invented, it would make the normalisation decorative and
would move every solve by a constant nobody chose deliberately.

Measured on the same footing as every other model number here — the 2024-25
walk-forward benchmark, one fit, then a gameweek at a time:

    for each gameweek of the test season:
        take the DEFAULT_TOP_N pool by horizon EP
        take the positionally-legal eleven with the highest EP
            (one GK, then greedy by EP inside XI_BOUNDS)
        record mean(1 - p_play) over those eleven, and the keeper's alone

    POPULATION_DNP = mean over gameweeks

Top-eleven-by-EP stands in for "the XI a points-max solver picks", and it is a
good stand-in for the reason it is cheap: the MILP chooses its XI from an
EP-ranked pool by EP, under constraints — budget, three-per-club — that are
close to orthogonal to availability.

Three numbers come out and all three matter. ``POPULATION_DNP`` is the
constant. ``gk_dnp`` is the keeper-only rate, printed so the next cycle can
split the constant if the two have diverged; v10 ships one number. And the
per-gameweek min/max says whether ``FRAILTY_CLAMP``'s (0.25, 2.0) would ever
have bound on real data — if it binds every week the clamp is doing the
deciding and the constant is wrong.

**A lever guard here too**, cheaper than the arm driver's but the same idea:
if ``comp`` has no ``p_play`` column, or ``p_play`` is constant across the
pool, the run exits rather than reporting a rate. A constant ``p_play`` would
give a ``POPULATION_DNP`` that makes every frailty exactly 1.0 forever — §F1
shipped and permanently inert, with nothing in any output to say so.

Run it, read the line::

    mkdir -p logs && caffeinate -i nohup .venv/bin/python scripts/v10_dnp.py \\
        > logs/v10_dnp.log 2>&1 &
    grep V10_DNP logs/v10_dnp.log
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import gaffer.evaluation as ev
from gaffer.optimize.milp import DEFAULT_TOP_N, XI_BOUNDS


def top_xi(pool: pd.DataFrame) -> pd.DataFrame:
    """The positionally-legal eleven with the highest EP, GK first.

    One keeper, then the minimum at every other position, then the best of
    what is left up to each position's ceiling — which is what "greedy by EP
    inside :data:`XI_BOUNDS`" means when the bounds are ranges rather than
    fixed counts. Not the MILP's own selection, and it does not need to be
    (plan A3): the constraints the MILP adds on top of this — budget,
    three-per-club — are close to orthogonal to availability, which is the
    only axis being measured.
    """
    ranked = pool.sort_values("ep", ascending=False)
    picked: list[int] = []
    for pos, (lo, _hi) in XI_BOUNDS.items():
        rows = ranked[ranked["position"] == pos]
        picked.extend(rows.index[:lo])
    remaining = 11 - len(picked)
    if remaining > 0:
        counts = {p: sum(1 for i in picked
                         if ranked.loc[i, "position"] == p)
                  for p in XI_BOUNDS}
        for i in ranked.index:
            if remaining == 0:
                break
            if i in picked:
                continue
            pos = ranked.loc[i, "position"]
            if counts.get(pos, 0) >= XI_BOUNDS[pos][1]:
                continue
            picked.append(i)
            counts[pos] = counts.get(pos, 0) + 1
            remaining -= 1
    return ranked.loc[picked]


def _pool(frame: pd.DataFrame) -> pd.DataFrame:
    """The ``DEFAULT_TOP_N`` slice of a gameweek's rows, by EP."""
    parts = []
    for pos, n in DEFAULT_TOP_N.items():
        rows = frame[frame["position"] == pos].sort_values(
            "ep", ascending=False)
        parts.append(rows.head(n))
    return pd.concat(parts, ignore_index=True) if parts else frame


def check_lever(frame: pd.DataFrame) -> None:
    """A rate measured off a column that says nothing is not a measurement."""
    if "p_play" not in frame.columns:
        raise SystemExit(
            "comp has no p_play column — the quantity POPULATION_DNP is the "
            "mean of does not exist on this frame, and any number printed "
            "below would be arithmetic on a default.")
    series = pd.to_numeric(frame["p_play"], errors="coerce")
    if not series.notna().any():
        raise SystemExit("p_play is entirely null on the benchmark pool.")
    if series.nunique(dropna=True) <= 1:
        raise SystemExit(
            "p_play is constant across the pool — a POPULATION_DNP measured "
            "off it would make every frailty exactly 1.0 forever, shipping "
            "F1 permanently inert with nothing in any output to say so.")
    print("V10_DNP_LEVER ok", flush=True)


def main() -> None:
    from gaffer.assets import load_bootstrap_sample
    from gaffer.data.bootstrap import scoring_table
    from gaffer.models.assemble import apply_calibration, assemble_ep, ep_matrix
    from gaffer.models.train import (load_training_frame,
                                     predict_components_simple, train_all)

    df, tg, _ = load_training_frame()
    train_df, test_df = ev.benchmark_split(df, ev.BENCHMARK_TRAIN_MAX_IDX,
                                           ev.BENCHMARK_TEST_IDX)
    train_tg, _ = ev.benchmark_split(tg, ev.BENCHMARK_TRAIN_MAX_IDX,
                                     ev.BENCHMARK_TEST_IDX)
    models = train_all(train_df, train_tg.dropna(subset=["elo_diff"]),
                       save=False)
    scoring = ev.benchmark_scoring(scoring_table(load_bootstrap_sample()))

    per_gw: list[dict] = []
    levered = False
    for gw in sorted(int(g) for g in test_df["gw"].dropna().unique()):
        rows = test_df[test_df["gw"] == gw].reset_index(drop=True)
        if rows.empty:
            continue
        comp = predict_components_simple(models, rows)
        if not levered:
            check_lever(comp)
            levered = True
        ep = ep_matrix(apply_calibration(assemble_ep(comp, scoring),
                                         models.get("calibration")))
        # "Did he turn out at all" is one outcome, so a doubled-up player's
        # p_play is the mean of his fixtures and not their sum — the same rule
        # news_shadow.shadow_rows applies for the same reason.
        pp = (comp.groupby(["code", "gw"], as_index=False)
              .agg(p_play=("p_play", "mean")))
        pos = (rows[["code", "position"]].drop_duplicates(subset=["code"]))
        frame = (ep.merge(pp, on=["code", "gw"], how="inner")
                 .merge(pos, on="code", how="inner"))
        frame = frame[pd.to_numeric(frame["p_play"],
                                    errors="coerce").notna()]
        if frame.empty:
            continue
        xi = top_xi(_pool(frame))
        if len(xi) < 11:
            print(f"gw{gw}: only {len(xi)} legal slots — skipped", flush=True)
            continue
        dnp = float((1.0 - xi["p_play"]).mean())
        keeper = xi[xi["position"] == "GKP"]
        gk_dnp = float(1.0 - keeper["p_play"].iloc[0]) if not keeper.empty \
            else float("nan")
        per_gw.append({"gw": gw, "dnp": round(dnp, 5),
                       "gk_dnp": round(gk_dnp, 5)})
        print(f"gw{gw}: dnp {dnp:.4f} gk {gk_dnp:.4f}", flush=True)

    if not per_gw:
        raise SystemExit("no gameweek produced a legal XI — nothing measured.")
    rates = [r["dnp"] for r in per_gw]
    gks = [r["gk_dnp"] for r in per_gw if r["gk_dnp"] == r["gk_dnp"]]
    payload = {
        "population_dnp": round(sum(rates) / len(rates), 4),
        "gk_dnp": round(sum(gks) / len(gks), 4) if gks else None,
        "gw_min": round(min(rates), 4),
        "gw_max": round(max(rates), 4),
        "gws": len(per_gw),
        "per_gw": per_gw,
    }
    print("V10_DNP", json.dumps({k: v for k, v in payload.items()
                                 if k != "per_gw"}), flush=True)
    Path("reports").mkdir(exist_ok=True)
    Path("reports/v10_dnp.json").write_text(json.dumps(payload, indent=1))


if __name__ == "__main__":
    main()
