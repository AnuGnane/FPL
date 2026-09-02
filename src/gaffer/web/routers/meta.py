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
from fastapi import APIRouter, Query

from gaffer.artifacts import (REPORTS, ingested_through, latest_gw,
                              load_advice, load_snapshot, load_solve_state,
                              milp_pool, raw_ep_by, solve_kw_from_state)
from gaffer.data import store
from gaffer.data.bootstrap import season_from_events
from gaffer.data.elo import compute_elo, expected_score
from gaffer.data.odds import poisson_win_prob
from gaffer.errors import GafferError
from gaffer.assets import load_decision_priors
from gaffer.config import Config, load_config, optimizer_top_n
from gaffer.price_timing import owned_price_falls
from gaffer.optimize.chip_policy import (chip_thresholds_from_asset,
                                         chip_windows, load_chip_scenarios,
                                         threshold_with_source)
from gaffer.optimize.chips import chip_plan, evaluate_chips
from gaffer.optimize.milp import SolveInput
from gaffer.web.schemas import (ArtifactItem, BackupHealth, ChipPlan,
                                ChipPlanRow, CoreInsightsHealth,
                                CoreInsightsTable, Freshness, FreshnessRow,
                                Health, History, HistoryRun, LaunchdHealth,
                                ModelHealth, PricePoint, PriceSeries,
                                SourceHealth, Ticker, TickerCell, TickerTeam)

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
        opt = solve_kw_from_state(state)
        table = evaluate_chips(pool, solve_state,
                               avail_by_gw=state.avail_by_gw, **opt)
    except (RuntimeError, KeyError) as exc:
        raise GafferError(
            "chip evaluation failed for this saved state — re-run "
            f"`gaffer advise` ({exc})") from exc
    # v10b §F2c. `chip_thresholds_from_asset(priors, load_chip_scenarios())`
    # is advise.py:735-736's expression character for character, deliberately:
    # the bar the Outlook draws has to be the bar the advise run actually
    # solved against, not a second opinion computed a different way on the
    # same page.
    priors = load_decision_priors() if load_config().decision_priors else None
    thresholds = chip_thresholds_from_asset(priors, load_chip_scenarios())
    rows = [] if table.empty else chip_plan(table, now_gw=state.gws[0],
                                            thresholds=thresholds)
    for row in rows:
        # The trajectory, looped here rather than emitted from chip_plan's
        # week rows: `thresholds` is a plain (chip, gw) -> float callable, and
        # widening those rows would be an optimize/** edit for a display
        # field (plan A9). Aligned by index with `weeks`.
        row["thetas"] = [round(float(thresholds(row["chip"], w["gw"])), 2)
                         for w in row["weeks"]]
        # v12 W3 §4.2 (specs/2026-09-01-gaffer-v12-program-design.md): the same
        # lookup, asked why rather than only how much.
        row["threshold_source"] = threshold_with_source(
            thresholds, row["chip"], state.gws[0])[1]
        # (from_gw, last_gw) — the first element is the gameweek asked about,
        # not the window's opening.
        row["window"] = list(chip_windows(state.gws[0]))
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
    """``(present, modified_at, age_hours)``, or three absences.

    The ``stat`` is guarded here rather than at each call site, because the
    race is in this function: ``exists()`` and ``stat()`` are two syscalls, and
    a refresh job that rewrites its output in between deletes the file
    underneath the second one. Both readers below — the freshness strip, drawn
    on every page in the app, and ``/api/health`` — must cost one row for that
    rather than a 500.
    """
    if not path.exists():
        return False, None, None
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return False, None, None
    modified = datetime.fromtimestamp(stamp, tz=timezone.utc)
    age = (datetime.now(timezone.utc) - modified).total_seconds() / 3600
    return True, modified.isoformat(), round(age, 2)


@router.get("/meta/freshness", response_model=Freshness)
def freshness() -> Freshness:
    """When each of the five standing jobs last wrote something.

    v12 W1 §2.9 (specs/2026-09-01-gaffer-v12-program-design.md). Drawn at the
    top of every hub, so it must never error and never block: five stats and,
    at worst, one config read that is allowed to fail on its own.

    All five are mtimes. Each of these artifacts is rewritten whole by the job
    that writes it, so the mtime *is* the run stamp — where a timestamp parsed
    out of a file's contents can be stale inside a file that was just
    rewritten, which is the harder lie to notice.
    """
    def _row(source: str, path: Path | None) -> FreshnessRow:
        if path is None:
            return FreshnessRow(source=source)
        # A file that vanishes between the glob and the stat is a grey row, not
        # a 500 — `_stat` swallows that, for both readers at once.
        present, modified, age = _stat(path)
        return FreshnessRow(source=source,
                            path=str(path) if present else None,
                            modified_at=modified, age_hours=age)

    def _newest(directory: Path, pattern: str) -> Path | None:
        try:
            if not directory.is_dir():
                return None
            found = sorted(directory.glob(pattern),
                           key=lambda p: p.stat().st_mtime)
        except OSError:
            return None
        return found[-1] if found else None

    backup_newest = None
    try:
        from gaffer.backup import NAME_GLOB, backup_dir

        backup_newest = _newest(backup_dir(load_config().backup_dir),
                                NAME_GLOB)
    except Exception:  # noqa: BLE001 — one grey row, never a broken strip
        backup_newest = None

    return Freshness(rows=[
        _row("refresh", store.DATA_DIR / "live" / "player_gw.parquet"),
        _row("odds", _newest(store.DATA_DIR / "live" / "odds", "gw*.parquet")),
        _row("field", store.DATA_DIR / "live" / "field_eo_log.parquet"),
        _row("advise", _newest(REPORTS, "gw*-advice.json")),
        _row("backup", backup_newest),
    ])


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

    # v12 W1 §2.4. Disk only, by this module's own contract: the events
    # snapshot is what the last refresh banked, so the comparison answers "is
    # the data on disk the data the config describes" — which is the state
    # that matters — without a network call on a page-load path.
    #
    # `load_config` here rather than `serving_config`, on purpose: this is the
    # page a user opens *after* editing `current_season`, and the cached
    # reader would keep showing the red banner until the process restarted.
    # One TOML read per health poll is cheap; a banner that will not clear is
    # not.
    season_ok = None
    try:
        season_config = load_config().current_season
    except Exception:  # noqa: BLE001 — no config.toml is a valid state here
        season_config = None
    try:
        season_ingested = season_from_events(
            store.load("live/events.parquet"))
    except Exception:  # noqa: BLE001 — no snapshot yet is a valid state too
        season_ingested = None
    if season_config and season_ingested:
        season_ok = season_config == season_ingested

    # v12 W1 §2.6. The four numbers that decide which players a solve is
    # allowed to consider at all, on the one page a user reads to find out
    # what this install is doing. `optimizer_top_n` never raises, so the try
    # is belt and braces for an unforeseeable read.
    try:
        # `cache_clear` first, for the reason the season banner reads
        # `load_config` rather than `serving_config`: this is the page a user
        # opens *after* editing `[optimizer] top_n`, and a cached reader would
        # keep showing the old pool sizes until the process restarted. One
        # TOML read per health poll is cheap; a card that will not update is
        # a card that teaches the user their edit did nothing.
        #
        # The clear is process-wide, not this call's: `build_pool` reads the
        # same cached `optimizer_top_n`, so the first solve after any health
        # poll pays one TOML read too. That is the whole cost, and it is the
        # right way round — a solve that picks up the edited value is what a
        # user who just edited it expects.
        optimizer_top_n.cache_clear()
        solver_top_n = optimizer_top_n()
        # v12 W2 §3.4. The price-timing table is cached on the same terms and
        # goes stale on the same events — an edited `[optimizer]` switch, and
        # a nightly `gaffer prices` run that banked a fresher day under a
        # long-lived server. One clear per health poll, same trade.
        owned_price_falls.cache_clear()
    except Exception:  # noqa: BLE001 — a health page never 500s
        solver_top_n = None

    # v12 W1 §2.1. Disk only, like everything else here: the newest archive in
    # the configured directory, or None for "never". A backup nobody can see
    # is a backup nobody notices has stopped running.
    last_backup = None
    try:
        from gaffer.backup import backup_dir, latest_backup

        found = latest_backup(backup_dir(load_config().backup_dir))
        last_backup = BackupHealth(**found) if found else None
    except Exception:  # noqa: BLE001 — no config, no directory: never is fine
        last_backup = None

    model_health = None
    health_file = REPORTS / "health.json"
    if health_file.exists():
        model_health = json.loads(health_file.read_text())

    artifacts = []
    for path in sorted(REPORTS.glob("*")):
        if path.is_file():
            artifacts.append(ArtifactItem(name=f"reports/{path.name}",
                                          bytes=path.stat().st_size))
    # v12 W4 §5.1. Rows and latest date per table, or an honest "never":
    # the collector is opt-in (a CLI run or its plist), so a clone that has
    # not run it must say what it is waiting for rather than render three
    # zeros that look like a measurement.
    from gaffer.data.core_insights import ci_path, season_table_stats
    try:
        season = str(load_config().current_season)
    except Exception:  # noqa: BLE001 — no config.toml is a valid state here
        # A clone with no config.toml still knows which season the collector
        # would fetch, because Config's own default says so. Naming it beats
        # a blank: "not collected yet (—)" tells the reader nothing.
        season = str(getattr(Config, "current_season", ""))
    stats = season_table_stats(season) if season else {}
    collected = bool(season) and any(
        store.exists(ci_path(season, table)) for table in stats)
    core_insights = CoreInsightsHealth(
        season=season,
        collected=collected,
        tables=[CoreInsightsTable(table=name, rows=int(v["rows"]),
                                  latest=v["latest"])
                for name, v in sorted(stats.items())] if collected else [],
        waiting_for=None if collected else
        "a collector run — `gaffer core-insights`, or install "
        "scripts/com.gaffer.core-insights.plist for 06:30 and 18:30 daily")

    return Health(data=sources, data_through_gw=ingested_through(),
                  models=models,
                  launchd=LaunchdHealth(log=str(ADVISE_LOG),
                                        present=log_present,
                                        modified_at=log_modified,
                                        last_line=last_line),
                  odds_key_present=odds_key, model_health=model_health,
                  artifacts=artifacts, season_ok=season_ok,
                  season_config=season_config,
                  season_ingested=season_ingested,
                  solver_top_n=solver_top_n,
                  last_backup=last_backup,
                  core_insights=core_insights)


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
    """Pull the live season and re-write the bootstrap snapshots.

    The body of the ``refresh-data`` job kind, started through
    ``POST /api/jobs/refresh-data``. The ``POST /api/data/refresh`` route that
    used to queue this on the legacy ``JobRegistry`` is gone: it was a second
    lane past the single-flight runner, and two concurrent refreshes rewrite
    the same parquet files underneath each other.
    """
    from gaffer.advise import fixture_frame, save_live_fixtures
    from gaffer.api.client import FPLClient
    from gaffer.artifacts import save_snapshots
    from gaffer.config import load_config
    from gaffer.data.bootstrap import build_events, build_players, build_teams
    from gaffer.data.chip_scenarios import write_chip_scenarios
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
    # v10b §F2b: the DGW hook v4c shipped has been waiting for data since
    # August. Derived here rather than in a new job kind because the fixture
    # list was just fetched and is in hand — a second kind would re-fetch it
    # to learn the same thing. Never raises; see the writer's docstring.
    write_chip_scenarios(fixtures,
                         dict(zip(teams["team_id"], teams["code"])))
    return {"rows": int(len(frame))}
