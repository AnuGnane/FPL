"""On-disk artifacts the local web UI reads.

``advise`` already computes everything in here; these functions only persist
it. Two files per run land under ``reports/``:

* ``components_gw{N}.parquet`` — one row per (player, fixture) with every
  expected-points component, so "why 6.8?" can be answered offline.
* ``solve_state_gw{N}.parquet`` + ``solve_state_gw{N}.json`` — the candidate
  pool with **raw** (untilted) expected points, prices and squad state, plus
  the league tilt recorded separately. A what-if re-solve rebuilds the exact
  MILP from these without retraining or refetching anything.

The tilt is deliberately *not* baked into the stored expected points. Chips
and every displayed points number use raw values (see ``advise.run_advise``),
and ``league_mode.tilt_ep`` reproduces the tilted pool on demand from ``lam``
and ``league_eo`` — so one file serves both, and neither can drift from the
other.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from gaffer.errors import GafferError

REPORTS = Path("reports")

COMPONENT_COLS = [
    "code", "element", "name", "position", "team_code", "team_name",
    "gw", "opp_code", "opp_name", "was_home", "kickoff_time",
    "p_play", "p60", "e_goals", "e_assists", "p_defcon", "e_saves",
    "e_bonus", "e_cards", "p_cs", "e_gc", "p_cs_model", "e_gc_model",
    "odds_e_goals_against", "odds_weight", "pen_taker", "setpiece_taker",
    "ep_minutes", "ep_goals", "ep_assists", "ep_cs", "ep_gc", "ep_saves",
    "ep_defcon", "ep_bonus", "ep_cards", "ep_pensave",
    "ep_uncalibrated", "cal_delta", "ep",
]

POOL_COLS = ["code", "name", "position", "team_code", "cost", "sell",
             "owned", "gw", "ep_raw"]

SNAPSHOT_PLAYER_COLS = [
    "code", "element", "name", "position", "team_id", "team_code",
    "now_cost", "status", "news", "chance_of_playing",
    "selected_by_percent", "form", "points_per_game", "ep_next",
    "price_change_percent", "price_change_calibrating",
    "penalties_order", "direct_freekicks_order",
    "corners_and_indirect_freekicks_order",
]

NUMERIC_SNAPSHOT_COLS = ["chance_of_playing", "penalties_order",
                         "direct_freekicks_order",
                         "corners_and_indirect_freekicks_order"]


def components_path(gw: int) -> Path:
    return REPORTS / f"components_gw{gw}.parquet"


def solve_state_paths(gw: int) -> tuple[Path, Path]:
    return (REPORTS / f"solve_state_gw{gw}.parquet",
            REPORTS / f"solve_state_gw{gw}.json")


def components_frame(comp: pd.DataFrame, scoring: dict, cal,
                     players: pd.DataFrame,
                     teams: pd.DataFrame) -> pd.DataFrame:
    """Per-fixture component breakdown, named and ready to persist.

    ``cal`` is the calibration model or ``None``; the difference it makes is
    stored as its own column rather than folded silently into ``ep``.
    """
    from gaffer.models.assemble import (apply_calibration, assemble_ep,
                                        ep_breakdown)

    assembled = assemble_ep(comp, scoring)
    out = ep_breakdown(assembled, scoring)
    out["ep_uncalibrated"] = out["ep"]
    out["ep"] = apply_calibration(assembled, cal)["ep"].values
    out["cal_delta"] = out["ep"] - out["ep_uncalibrated"]
    name_of = dict(zip(players["code"], players["name"]))
    element_of = dict(zip(players["code"], players["element"]))
    team_name = dict(zip(teams["code"], teams["name"]))
    out["name"] = out["code"].map(name_of)
    out["element"] = out["code"].map(element_of)
    out["team_name"] = out["team_code"].map(team_name)
    out["opp_name"] = out["opp_code"].map(team_name)
    for col in COMPONENT_COLS:
        if col not in out.columns:
            out[col] = float("nan")
    return out[COMPONENT_COLS].reset_index(drop=True)


def save_components(frame: pd.DataFrame, gw: int) -> Path:
    REPORTS.mkdir(exist_ok=True)
    path = components_path(gw)
    frame.to_parquet(path, index=False)
    return path


def load_components(gw: int) -> pd.DataFrame:
    path = components_path(gw)
    if not path.exists():
        raise GafferError(
            f"no component breakdown for GW{gw} — run `gaffer advise` first")
    return pd.read_parquet(path)


@dataclass
class SolveState:
    """Everything the MILP needs to be re-run without models or network."""

    gw: int
    gws: list[int]
    deadline: str
    generated_at: str
    mode: str                        # "weekly" | "initial_squad"
    bank: int                        # 0.1m units
    free_transfers: int
    owned_codes: list[int]
    lam: float                       # league tilt strength, 0.0 when neutral
    league_eo: dict[int, float]      # code -> rival EO percent
    avail_by_gw: dict[int, list[str]]
    opt: dict                        # decay/bench_weight/.../horizon
    pool: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=POOL_COLS))


def pool_rows(pool: pd.DataFrame, players: pd.DataFrame,
              owned_codes: list[int], ep_by: dict,
              gws: list[int]) -> pd.DataFrame:
    """MILP pool -> one row per (candidate, gameweek) with **raw** EP."""
    name_of = dict(zip(players["code"], players["name"]))
    owned = {int(c) for c in owned_codes}
    rows = []
    for r in pool.itertuples():
        code = int(r.code)
        for g in gws:
            rows.append({"code": code,
                         "name": name_of.get(code, str(code)),
                         "position": str(r.position),
                         "team_code": int(r.team_code),
                         "cost": int(r.cost), "sell": int(r.sell),
                         "owned": code in owned, "gw": int(g),
                         "ep_raw": float(ep_by.get((code, int(g)), 0.0))})
    return pd.DataFrame(rows, columns=POOL_COLS)


def save_solve_state(state: SolveState) -> tuple[Path, Path]:
    """Pool to parquet, everything scalar to JSON beside it.

    JSON object keys are strings by definition, so ``league_eo`` and
    ``avail_by_gw`` are written stringly and converted back on load — a
    caller looking up ``league_eo[code]`` with an int must never silently
    miss.
    """
    REPORTS.mkdir(exist_ok=True)
    parquet, meta = solve_state_paths(state.gw)
    state.pool.to_parquet(parquet, index=False)
    meta.write_text(json.dumps({
        "gw": state.gw, "gws": [int(g) for g in state.gws],
        "deadline": state.deadline, "generated_at": state.generated_at,
        "mode": state.mode, "bank": int(state.bank),
        "free_transfers": int(state.free_transfers),
        "owned_codes": [int(c) for c in state.owned_codes],
        "lam": float(state.lam),
        "league_eo": {str(k): float(v) for k, v in state.league_eo.items()},
        "avail_by_gw": {str(g): list(c)
                        for g, c in state.avail_by_gw.items()},
        "opt": dict(state.opt),
    }, indent=1))
    return parquet, meta


def load_solve_state(gw: int) -> SolveState:
    parquet, meta = solve_state_paths(gw)
    if not meta.exists() or not parquet.exists():
        raise GafferError(
            f"no saved solve state for GW{gw} — run `gaffer advise` first")
    raw = json.loads(meta.read_text())
    return SolveState(
        gw=int(raw["gw"]), gws=[int(g) for g in raw["gws"]],
        deadline=str(raw["deadline"]),
        generated_at=str(raw["generated_at"]), mode=str(raw["mode"]),
        bank=int(raw["bank"]), free_transfers=int(raw["free_transfers"]),
        owned_codes=[int(c) for c in raw["owned_codes"]],
        lam=float(raw["lam"]),
        league_eo={int(k): float(v) for k, v in raw["league_eo"].items()},
        avail_by_gw={int(g): list(c)
                     for g, c in raw["avail_by_gw"].items()},
        opt=dict(raw["opt"]), pool=pd.read_parquet(parquet))


def latest_gw() -> int | None:
    """Newest gameweek with a saved solve state, or ``None`` if never run."""
    gws = []
    for path in REPORTS.glob("solve_state_gw*.json"):
        stem = path.stem.removeprefix("solve_state_gw")
        if stem.isdigit():
            gws.append(int(stem))
    return max(gws) if gws else None


def raw_ep_by(state: SolveState) -> dict[tuple[int, int], float]:
    """``{(code, gw): raw expected points}`` — the untilted numbers."""
    return {(int(r.code), int(r.gw)): float(r.ep_raw)
            for r in state.pool.itertuples()}


def milp_pool(state: SolveState, ep_by: dict[tuple[int, int], float],
              gws: list[int]) -> pd.DataFrame:
    """The frame ``optimize.milp.solve_plan`` expects, ep as ``{gw: pts}``."""
    one = state.pool.drop_duplicates("code")
    return pd.DataFrame({
        "code": [int(c) for c in one["code"]],
        "position": [str(p) for p in one["position"]],
        "team_code": [int(t) for t in one["team_code"]],
        "cost": [int(c) for c in one["cost"]],
        "sell": [int(s) for s in one["sell"]],
        "ep": [{int(g): float(ep_by.get((int(c), int(g)), 0.0)) for g in gws}
               for c in one["code"]],
    })


def load_snapshot(rel: str) -> pd.DataFrame:
    """A bootstrap snapshot written by :func:`save_snapshots`."""
    from gaffer.data import store

    if not store.exists(rel):
        raise GafferError(
            f"data/{rel} has not been written yet — run `gaffer advise` first")
    return store.load(rel)


def upcoming_gw(now: pd.Timestamp | None = None) -> int | None:
    """The gameweek whose deadline has not passed, from the events snapshot.

    Read from disk rather than the API so a stale-advice banner still renders
    with no network. ``None`` means every deadline in the snapshot is behind
    us — an end-of-season or a very old snapshot.
    """
    events = load_snapshot("live/events.parquet")
    ts = pd.Timestamp.now(tz="UTC") if now is None else now
    deadlines = pd.to_datetime(events["deadline_time"], utc=True,
                               format="mixed")
    future = events[deadlines > ts]
    return int(future["gw"].min()) if not future.empty else None


def ingested_through(season_idx: int | None = None) -> int | None:
    """Newest gameweek present in ``data/live/player_gw.parquet``.

    The one place anything asks "how much of this season has the model
    actually seen?". ``refresh_live`` drops every gameweek FPL has not marked
    ``data_checked``, so running ``gaffer advise`` on the evening of GW1
    leaves this at ``None`` — the model is predicting GW2 off last season
    alone, and every surface that shows advice needs to say so.

    ``season_idx`` restricts the answer to one season; the default takes the
    newest season in the file, which is the current one (``refresh_live``
    rewrites the whole table from today's bootstrap).
    """
    from gaffer.data import store

    if not store.exists("live/player_gw.parquet"):
        return None
    df = store.load("live/player_gw.parquet")
    if df.empty:
        return None
    if season_idx is None:
        df = df[df["season_idx"] == df["season_idx"].max()]
    else:
        df = df[df["season_idx"] == season_idx]
    gws = pd.to_numeric(df["gw"], errors="coerce").dropna()
    return int(gws.max()) if not gws.empty else None


DATA_WARNING_TAIL = ("FPL usually finalizes it the morning after the last "
                     "match; re-run gaffer advise after that")


def data_warning(upcoming: int | None, through: int | None) -> str | None:
    """The one warning string, shared by the CLI, the report and the API.

    ``None`` when the model has results for every gameweek before ``upcoming``
    — including the start of the season, when there is nothing to be missing.
    """
    if upcoming is None or upcoming <= 1:
        return None
    last_played = upcoming - 1
    if through is not None and through >= last_played:
        return None
    start = (through or 0) + 1
    span = f"GW{start}" if start >= last_played \
        else f"GW{start}-GW{last_played}"
    return f"model has no data for {span} — {DATA_WARNING_TAIL}"


def load_advice(gw: int) -> dict:
    """The advice payload ``run_advise`` wrote for ``gw``."""
    path = REPORTS / f"gw{gw}-advice.json"
    if not path.exists():
        raise GafferError(
            f"no advice for GW{gw} — run `gaffer advise` first")
    return json.loads(path.read_text())


def save_snapshots(players: pd.DataFrame, teams: pd.DataFrame,
                   events: pd.DataFrame, fixtures: pd.DataFrame) -> None:
    """Bootstrap tables the web layer reads when the FPL API is unreachable.

    ``data/live/fixtures.parquet`` holds only *finished* matches (it feeds Elo
    and the team model), so the fixture ticker needs its own copy of the whole
    list — hence ``fixtures_all``.
    """
    from gaffer.data import store

    snap = players[SNAPSHOT_PLAYER_COLS].copy()
    for col in NUMERIC_SNAPSHOT_COLS:
        snap[col] = pd.to_numeric(snap[col], errors="coerce")
    store.save(snap, "live/players.parquet")
    store.save(teams, "live/teams.parquet")
    store.save(events, "live/events.parquet")
    store.save(fixtures, "live/fixtures_all.parquet")
