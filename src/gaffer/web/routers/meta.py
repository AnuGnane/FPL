"""Chip planner, history, health and the fixture ticker.

Everything here is disk-only except the explicit data-refresh job. The chip
planner re-runs ``evaluate_chips`` against the saved pool: that is a handful
of small MILP solves, which is why it is a GET the page can afford to call
directly rather than a job.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from gaffer.artifacts import (REPORTS, ingested_through, latest_gw,
                              load_advice, load_snapshot, load_solve_state,
                              milp_pool, raw_ep_by)
from gaffer.data import store
from gaffer.data.elo import compute_elo, expected_score
from gaffer.data.odds import poisson_win_prob
from gaffer.errors import GafferError
from gaffer.optimize.chips import chip_plan, evaluate_chips
from gaffer.optimize.milp import SolveInput
from gaffer.web.jobs import ADVISE_TIMEOUT_S, JobQueueFull
from gaffer.web.schemas import (ArtifactItem, ChipPlan, ChipPlanRow, Health,
                                History, HistoryRun, JobAccepted,
                                LaunchdHealth, ModelHealth, PricePoint,
                                PriceSeries, SourceHealth, Ticker, TickerCell,
                                TickerTeam)

router = APIRouter(prefix="/api", tags=["meta"])

ADVISE_LOG = Path("logs/advise.log")
MODELS_DIR = Path("models")
DATA_SOURCES = [("history", "history/player_gw.parquet"),
                ("player_gw", "live/player_gw.parquet"),
                ("fixtures", "live/fixtures.parquet"),
                ("players", "live/players.parquet")]


def _state():
    gw = latest_gw()
    if gw is None:
        raise GafferError("nothing on disk yet — run `gaffer advise` first")
    return load_solve_state(gw)


@router.get("/chips/plan", response_model=ChipPlan)
def chips_plan() -> ChipPlan:
    state = _state()
    ep_by = raw_ep_by(state)          # chips are priced in raw points
    pool = milp_pool(state, ep_by, state.gws)
    solve_state = SolveInput(owned_codes=state.owned_codes, bank=state.bank,
                             free_transfers=state.free_transfers,
                             gws=state.gws)
    # A state saved by an older build can be missing an ``opt`` key, and a
    # pool that no longer holds every owned player makes the free-hit
    # from-scratch solve infeasible. Both are recoverable by re-running the
    # advice, so say that rather than returning a 500.
    try:
        opt = {k: state.opt[k] for k in ("decay", "bench_weight",
                                         "vice_weight", "ft_value",
                                         "itb_value", "hit_cost")}
        table = evaluate_chips(pool, solve_state,
                               avail_by_gw=state.avail_by_gw, **opt)
    except (RuntimeError, KeyError) as exc:
        raise GafferError(
            "chip evaluation failed for this saved state — re-run "
            f"`gaffer advise` ({exc})") from exc
    rows = [] if table.empty else chip_plan(table, now_gw=state.gws[0])
    return ChipPlan(gw=state.gw, chips=[ChipPlanRow(**row) for row in rows])


def _actual_points(advice: dict, live: pd.DataFrame) -> int | None:
    """XI points as picked, captain doubled — no autosubs, as ``live_gw``."""
    gw_rows = live[live["gw"] == int(advice["gw"])]
    if gw_rows.empty:
        return None
    points = dict(zip(gw_rows["code"], gw_rows["total_points"]))
    xi = [int(p["code"]) for p in advice.get("xi", [])]
    if not xi:
        return None
    captain = int((advice.get("captain") or {}).get("code", 0))
    return int(sum(int(points.get(c, 0)) for c in xi)
               + int(points.get(captain, 0)))


@router.get("/history", response_model=History)
def history() -> History:
    live = (store.load("live/player_gw.parquet")
            if store.exists("live/player_gw.parquet")
            else pd.DataFrame(columns=["code", "gw", "total_points",
                                       "value"]))
    runs = []
    for path in sorted(REPORTS.glob("gw*-advice.json")):
        stem = path.stem.removeprefix("gw").removesuffix("-advice")
        if not stem.isdigit():
            continue
        advice = load_advice(int(stem))
        runs.append(HistoryRun(
            gw=int(advice["gw"]), deadline=str(advice["deadline"]),
            captain=str((advice.get("captain") or {}).get("name", "")),
            buys=[str(b["name"]) for b in advice.get("buys", [])],
            sells=[str(s["name"]) for s in advice.get("sells", [])],
            hits=int(advice.get("hits", 0)),
            expected_pts=float(advice.get("expected_pts", 0.0)),
            actual_pts=_actual_points(advice, live)))
    runs.sort(key=lambda r: -r.gw)

    prices: list[PriceSeries] = []
    gw = latest_gw()
    if gw is not None and not live.empty and "value" in live.columns:
        state = load_solve_state(gw)
        names = dict(zip(state.pool["code"], state.pool["name"]))
        for code in state.owned_codes:
            rows = live[live["code"] == code].sort_values("gw")
            if rows.empty:
                continue
            prices.append(PriceSeries(
                code=int(code), name=str(names.get(code, code)),
                points=[PricePoint(gw=int(r.gw),
                                   price=round(float(r.value) / 10, 1))
                        for r in rows.itertuples()]))

    backtests: list[dict] = []
    if store.exists("live/backtest_log.parquet"):
        backtests = store.load("live/backtest_log.parquet") \
            .to_dict("records")
    return History(runs=runs, prices=prices, backtests=backtests)


def _stat(path: Path) -> tuple[bool, str | None, float | None]:
    if not path.exists():
        return False, None, None
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    age = (datetime.now(timezone.utc) - modified).total_seconds() / 3600
    return True, modified.isoformat(), round(age, 2)


@router.get("/health", response_model=Health)
def health() -> Health:
    from gaffer.config import load_config

    sources = []
    for name, rel in DATA_SOURCES:
        present, modified, age = _stat(store.DATA_DIR / rel)
        sources.append(SourceHealth(source=name, path=f"data/{rel}",
                                    present=present, modified_at=modified,
                                    age_hours=age))
    odds_dir = store.DATA_DIR / "live" / "odds"
    odds_files = sorted(odds_dir.glob("gw*.parquet")) if odds_dir.is_dir() \
        else []
    present, modified, age = _stat(odds_files[-1]) if odds_files \
        else (False, None, None)
    sources.append(SourceHealth(source="odds", path="data/live/odds/",
                                present=present, modified_at=modified,
                                age_hours=age))

    models = []
    for meta in sorted(MODELS_DIR.glob("*.meta.json")):
        payload = json.loads(meta.read_text())
        models.append(ModelHealth(name=meta.name.removesuffix(".meta.json"),
                                  saved_at=payload.pop("saved_at", None),
                                  metrics=payload))

    log_present, log_modified, _ = _stat(ADVISE_LOG)
    last_line = None
    if log_present:
        lines = [ln.strip() for ln in ADVISE_LOG.read_text().splitlines()
                 if ln.strip()]
        last_line = lines[-1] if lines else None

    try:
        odds_key = bool(load_config().odds_api_key)
    except Exception:  # noqa: BLE001 — no config.toml is a valid state here
        odds_key = False

    model_health = None
    health_file = REPORTS / "health.json"
    if health_file.exists():
        model_health = json.loads(health_file.read_text())

    artifacts = []
    for path in sorted(REPORTS.glob("*")):
        if path.is_file():
            artifacts.append(ArtifactItem(name=f"reports/{path.name}",
                                          bytes=path.stat().st_size))
    return Health(data=sources, data_through_gw=ingested_through(),
                  models=models,
                  launchd=LaunchdHealth(log=str(ADVISE_LOG),
                                        present=log_present,
                                        modified_at=log_modified,
                                        last_line=last_line),
                  odds_key_present=odds_key, model_health=model_health,
                  artifacts=artifacts)


def _odds_lookup() -> dict[tuple[int, int, int], tuple[float, float]]:
    """``(team, gw, opp)`` -> ``(goals for, against)`` from banked odds."""
    odds_dir = store.DATA_DIR / "live" / "odds"
    if not odds_dir.is_dir():
        return {}
    out: dict[tuple[int, int, int], tuple[float, float]] = {}
    for path in sorted(odds_dir.glob("gw*.parquet")):
        frame = pd.read_parquet(path)
        for row in frame.itertuples():
            out[(int(row.team_code), int(row.gw), int(row.opp_code))] = (
                float(row.odds_e_goals_for), float(row.odds_e_goals_against))
    return out


@router.get("/fixtures/ticker", response_model=Ticker)
def ticker(weeks: int = Query(8, ge=1, le=20)) -> Ticker:
    teams = load_snapshot("live/teams.parquet")
    fixtures = load_snapshot("live/fixtures_all.parquet")
    code_of = dict(zip(teams["team_id"], teams["code"]))
    short_of = dict(zip(teams["code"], teams["short_name"]))

    upcoming = fixtures[~fixtures["finished"].astype(bool)].copy()
    gws = sorted(int(g) for g in upcoming["gw"].dropna().unique())[:weeks]
    upcoming = upcoming[upcoming["gw"].isin(gws)]

    odds = _odds_lookup()
    elo_final: dict[int, float] = {}
    if store.exists("live/fixtures.parquet"):
        finished = store.load("live/fixtures.parquet")
        if not finished.empty:
            elo_final = compute_elo(finished).attrs["final"]

    used_odds = False
    cells: dict[int, list[TickerCell]] = {int(c): [] for c in teams["code"]}
    for fx in upcoming.sort_values("gw").itertuples():
        home_code = code_of.get(int(fx.home_id))
        away_code = code_of.get(int(fx.away_id))
        if home_code is None or away_code is None:
            continue
        # Rate the fixture once from the home side: home advantage belongs to
        # the fixture, not to each half of it, so the away side takes the
        # complement rather than a second call that would hand *both* teams
        # the boost.
        home_elo_win = expected_score(elo_final.get(home_code, 1500.0),
                                      elo_final.get(away_code, 1500.0),
                                      home=True)
        for own, other, home, elo_win in (
                (home_code, away_code, True, home_elo_win),
                (away_code, home_code, False, 1.0 - home_elo_win)):
            priced = odds.get((own, int(fx.gw), other))
            if priced is not None:
                used_odds = True
                win = poisson_win_prob(priced[0], priced[1])
            else:
                win = elo_win
            cells[own].append(TickerCell(
                gw=int(fx.gw), opponent=str(short_of.get(other, "")),
                home=home, difficulty=round(min(max(1.0 - win, 0.0), 1.0), 3)))

    rows = []
    for team in teams.itertuples():
        mine = cells[int(team.code)]
        mean = round(sum(c.difficulty for c in mine) / len(mine), 3) if mine \
            else 0.0
        rows.append(TickerTeam(code=int(team.code), name=str(team.name),
                               short_name=str(team.short_name), cells=mine,
                               mean_difficulty=mean))
    rows.sort(key=lambda t: t.mean_difficulty)
    return Ticker(gws=gws, source="odds" if used_odds else "elo", teams=rows)


def run_data_refresh() -> dict:
    """Pull the live season and re-write the bootstrap snapshots."""
    from gaffer.advise import fixture_frame, save_live_fixtures
    from gaffer.api.client import FPLClient
    from gaffer.artifacts import save_snapshots
    from gaffer.config import load_config
    from gaffer.data.bootstrap import build_events, build_players, build_teams
    from gaffer.data.live import refresh_live

    cfg = load_config()
    season_idx = len(cfg.train_seasons)
    client = FPLClient()
    frame = refresh_live(client, cfg.current_season, season_idx)
    raw = client.get_bootstrap()
    teams = build_teams(raw)
    fixtures = fixture_frame(client.get_fixtures())
    # The finished-only copy too, exactly as `advise` writes it: it is what
    # the ticker's Elo reads and what /api/health grades as "fixtures", so a
    # refresh that skipped it would leave both stale for ever.
    save_live_fixtures(fixtures, teams, season_idx)
    save_snapshots(build_players(raw), teams, build_events(raw), fixtures)
    return {"rows": int(len(frame))}


@router.post("/data/refresh", status_code=202, response_model=JobAccepted)
def data_refresh(request: Request):
    try:
        job_id = request.app.state.jobs.submit(run_data_refresh,
                                               timeout_s=ADVISE_TIMEOUT_S)
    except JobQueueFull as exc:
        return JSONResponse(status_code=429, content={"detail": str(exc)})
    return JobAccepted(job_id=job_id)
