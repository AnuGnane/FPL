"""Chip planner, history, health and the fixture ticker.

Everything here is disk-only since v18d §2, when the data-refresh job body
left for ``gaffer.refresh``: a job body is not a route. The chip
planner re-runs ``evaluate_chips`` against the saved pool: that is a handful
of small MILP solves, which is why it is a GET the page can afford to call
directly rather than a job.
"""

from __future__ import annotations

import json
import plistlib
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Query

from gaffer.artifacts import (
    REPORTS,
    advice_gws,
    advice_path,
    components_path,
    ingested_through,
    latest_gw,
    load_advice,
    load_solve_state,
    milp_pool,
    raw_ep_by,
    solve_kw_from_state,
)
from gaffer.assets import load_decision_priors
from gaffer.config import Config, config_in_force, invalidate, load_config
from gaffer.data import store
from gaffer.data.bootstrap import season_from_events
from gaffer.difficulty import rate_fixtures
from gaffer.errors import GafferError
from gaffer.optimize.chip_policy import (
    chip_thresholds_from_asset,
    chip_windows,
    load_chip_scenarios,
    threshold_with_source,
)
from gaffer.optimize.chips import chip_plan, evaluate_chips
from gaffer.optimize.milp import SolveInput
from gaffer.price_log import PRICE_LOG_PATH
from gaffer.web.schemas import (
    ArtifactItem,
    BackupHealth,
    CalibrationHealth,
    ChipPlan,
    ChipPlanRow,
    CoreInsightsHealth,
    CoreInsightsTable,
    Freshness,
    FreshnessRow,
    Health,
    History,
    HistoryRun,
    JobHealth,
    LaunchdHealth,
    ModelHealth,
    PricePoint,
    PriceSeries,
    SourceHealth,
    TeamModelHealth,
    Ticker,
    TickerCell,
    TickerTeam,
)

router = APIRouter(prefix="/api", tags=["meta"])

ADVISE_LOG = Path("logs/advise.log")
MODELS_DIR = Path("models")
PLIST_DIR = Path("scripts")
# `gaffer.snapshot.SNAPSHOT_PATH`, restated rather than imported (v19a §2.2):
# that module imports `gaffer.models.predict`, and pulling the LightGBM stack
# into a route module to read one string doubles this router's import cost.
# `PRICE_LOG_PATH` above is imported because its module is cheap. A rail in
# tests/test_v12_freshness.py asserts the two agree.
SNAPSHOT_PATH = "live/availability_log.parquet"
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
    for gw_seen in advice_gws():
        advice = load_advice(gw_seen)
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


# launchd's own numbering: 0 and 7 are both Sunday, 1 is Monday. The two
# spellings of Sunday are why this is a dict and not a list.
_WEEKDAYS = {0: "Sun", 1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri",
             6: "Sat", 7: "Sun"}

# v19a §2.3. Half an interval of grace before a job is called overdue: a
# nightly bank that starts at 23:15 and takes four minutes must not read as
# missed at 23:16 the next night, and a run that is a *whole* extra half-day
# late is no longer a slow start.
OVERDUE_FACTOR = 1.5


def _calendar_entries(payload: dict) -> list[dict]:
    """``StartCalendarInterval`` as a list, whichever way the plist spells it.

    launchd accepts a bare dict for one slot and an array for several, and
    both spellings are in ``scripts/`` today.
    """
    raw = payload.get("StartCalendarInterval")
    if isinstance(raw, dict):
        return [raw]
    return [entry for entry in (raw or []) if isinstance(entry, dict)]


def _schedule_sentence(entries: list[dict]) -> str:
    """The calendar entries as something a reader can check against a clock.

    Entry order is kept rather than sorted: a plist lists its slots in the
    order the author thinks about them ("Sat, Sun"), and re-sorting by
    launchd's weekday numbers would print the field job as "Sun, Sat" because
    Sunday is 0.
    """
    if not entries:
        return "on demand"
    times = [f"{int(e.get('Hour', 0)):02d}:{int(e.get('Minute', 0)):02d}"
             for e in entries]
    days = [_WEEKDAYS.get(int(e["Weekday"])) if e.get("Weekday") is not None
            else None for e in entries]
    if all(day is None for day in days):
        return "daily " + " and ".join(times)
    if all(day is not None for day in days) and len(set(times)) == 1:
        return f"{', '.join(days)} {times[0]}"
    return ", ".join(f"{day or 'daily'} {time}"
                     for day, time in zip(days, times))


def _interval_hours(entries: list[dict]) -> float:
    """Hours between runs: a week or a day, split over the slots.

    A ``Weekday`` on *any* entry makes the whole job weekly — launchd fires
    each slot once a week — so a job with a Saturday and a Sunday run is
    168 / 2, not 24.
    """
    if not entries:
        return 0.0
    period = 168.0 if any(e.get("Weekday") is not None for e in entries) \
        else 24.0
    return period / len(entries)


def _log_path(payload: dict) -> str:
    """The ``>> logs/x.log`` the plist's command redirects into, or "".

    Parsed out of ``ProgramArguments`` because that is where it is: these
    plists run a shell line rather than setting ``StandardOutPath``, so the
    log this page wants to stat is inside a string, not a key.
    """
    for argument in payload.get("ProgramArguments") or []:
        if not isinstance(argument, str):
            continue
        match = re.search(r">>\s*(\S+\.log)", argument)
        if match:
            return match.group(1)
    return ""


_XML_COMMENT = re.compile(rb"<!--.*?-->", re.DOTALL)


def _load_plist(path: Path) -> dict:
    """One plist, read the way launchd reads it rather than the way expat does.

    Apple's parser tolerates a ``--`` inside an XML comment; expat, which
    ``plistlib`` uses, calls it not-well-formed and refuses the whole file.
    ``scripts/com.gaffer.core-insights.plist`` documents a ``--refresh`` flag
    in exactly such a comment, and ``plutil -lint`` passes it — so without the
    retry this page would report a job that runs twice a day as unreadable,
    which is the page lying about the thing it exists to watch.
    """
    raw = path.read_bytes()
    try:
        return plistlib.loads(raw)
    except Exception:  # noqa: BLE001 — the retry decides, not this line
        return plistlib.loads(_XML_COMMENT.sub(b"", raw))


def job_health(plist_dir: Path = PLIST_DIR, *, log_root: Path = Path("."),
               now=None) -> list[JobHealth]:
    """Every installed plist, its schedule and whether it has run lately.

    v19a §2.3: eight of the nine standing jobs had no reader at all, so a
    launchd agent that stopped being loaded showed up only as a number going
    quietly stale on some other page. The age is the redirect log's mtime,
    for :func:`freshness`' reason — the job appends a line every run, whatever
    it did, so the mtime is the run stamp.

    Never raises. This is on ``/api/health``, which a tab polls, so a plist
    somebody is halfway through editing is one row reading "unreadable" and
    not a 500 on the page they opened to find out what is wrong.
    """
    now = now or datetime.now(timezone.utc)
    rows: list[JobHealth] = []
    try:
        found = sorted(Path(plist_dir).glob("com.gaffer.*.plist"))
    except OSError:
        return []
    for path in found:
        label = path.name.removeprefix("com.gaffer.").removesuffix(".plist")
        try:
            payload = _load_plist(path)
            label = str(payload.get("Label", label)).removeprefix(
                "com.gaffer.")
        except Exception:  # noqa: BLE001 — an unreadable plist is a row
            rows.append(JobHealth(label=label, schedule="unreadable", log="",
                                  modified_at=None, age_hours=None,
                                  interval_hours=0.0, overdue=True))
            continue
        entries = _calendar_entries(payload)
        interval = _interval_hours(entries)
        log = _log_path(payload)
        present, modified_at, age_hours = _stat(Path(log_root) / log) \
            if log else (False, None, None)
        if present and modified_at is not None:
            # Recomputed against the caller's clock rather than `_stat`'s, so
            # a test can pin the boundary without touching the wall clock.
            age_hours = round(
                (now - datetime.fromisoformat(modified_at)).total_seconds()
                / 3600, 2)
        rows.append(JobHealth(
            label=label, schedule=_schedule_sentence(entries), log=log,
            modified_at=modified_at, age_hours=age_hours,
            interval_hours=interval,
            overdue=age_hours is None or age_hours > OVERDUE_FACTOR * interval))
    rows.sort(key=lambda row: row.label)
    return rows


@router.get("/meta/freshness", response_model=Freshness)
def freshness() -> Freshness:
    """When each of the seven standing jobs last wrote something.

    v12 W1 §2.9 (specs/2026-09-01-gaffer-v12-program-design.md); prices and
    the availability snapshot joined in v19a §2.2, because the two nightly
    banks were the ones whose silence nothing on any page reported. Drawn at
    the top of every hub, so it must never error and never block: seven stats
    and, at worst, one config read that is allowed to fail on its own.

    All seven are mtimes. Each of these artifacts is rewritten whole by the job
    that writes it, so the mtime *is* the run stamp — where a timestamp parsed
    out of a file's contents can be stale inside a file that was just
    rewritten, which is the harder lie to notice.

    The cadence travels with the row (v19a §2.2) rather than sitting in a
    table keyed by source: a second home for the schedule is a second thing to
    forget when a plist moves.
    """
    def _row(source: str, path: Path | None, *,
             cadence_hours: float) -> FreshnessRow:
        if path is None:
            return FreshnessRow(source=source, cadence_hours=cadence_hours)
        # A file that vanishes between the glob and the stat is a grey row, not
        # a 500 — `_stat` swallows that, for both readers at once.
        present, modified, age = _stat(path)
        return FreshnessRow(source=source,
                            path=str(path) if present else None,
                            modified_at=modified, age_hours=age,
                            cadence_hours=cadence_hours)

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

    # v17f §1 part 4: the advice filename is spelled only in ``artifacts``, so
    # the row is the *highest gameweek*'s file rather than the newest mtime.
    # They are the same file in practice — advise writes for the gameweek it is
    # planning and never backfills an older one — and a re-run of an earlier
    # gameweek is a debugging session, not the run this strip is reporting.
    gws = advice_gws()

    return Freshness(rows=[
        _row("refresh", store.DATA_DIR / "live" / "player_gw.parquet",
             cadence_hours=168),
        _row("odds", _newest(store.DATA_DIR / "live" / "odds", "gw*.parquet"),
             cadence_hours=168),
        _row("field", store.DATA_DIR / "live" / "field_eo_log.parquet",
             cadence_hours=168),
        _row("advise", advice_path(gws[-1]) if gws else None,
             cadence_hours=168),
        _row("backup", backup_newest, cadence_hours=24),
        _row("prices", store.DATA_DIR / PRICE_LOG_PATH, cadence_hours=24),
        _row("snapshot", store.DATA_DIR / SNAPSHOT_PATH, cadence_hours=24),
    ])


def calibration_health() -> CalibrationHealth | None:
    """The fitted EP calibration's per-position deltas (v19g §2.1).

    Read through the model's own loader rather than a bare ``joblib.load``
    here, so this cannot drift from where training writes. The import is
    inside the function for the reason ``SNAPSHOT_PATH`` above is restated:
    unpickling reaches ``gaffer.models.calibrate``, and a route module that
    pulls the models package in at import time pays for it on every worker
    start whether or not anyone opens the Health tab.

    Never raises — ``/api/health`` is polled by an open tab, so a missing
    artifact, an unreadable one and a pickle written by an older build are all
    ``None`` rather than a 500 on the page somebody opened to find out what
    was wrong.
    """
    try:
        from gaffer.models.calibrate import MIN_ROWS, POSITION_GROUPS
        from gaffer.models.persistence import load_model, model_exists

        if not model_exists("calibration"):
            return None
        model = load_model("calibration")
        by_pos = {str(pos): float(delta)
                  for pos, delta in dict(model.by_pos).items()}
    except Exception:  # noqa: BLE001 — no artifact is a valid state here
        return None
    # `POSITION_GROUPS` order, not the dict's: the four groups are read as a
    # row and a row whose columns move between polls is unreadable.
    fitted = [pos for pos in POSITION_GROUPS if pos in by_pos]
    saved_at = None
    try:
        meta_path = MODELS_DIR / "calibration.meta.json"
        if meta_path.exists():
            saved_at = json.loads(meta_path.read_text()).get("saved_at")
    except Exception:  # noqa: BLE001 — a stamp is never worth the page
        saved_at = None
    return CalibrationHealth(
        by_pos=by_pos, fitted_positions=fitted,
        missing=[pos for pos in POSITION_GROUPS if pos not in by_pos],
        min_rows=int(MIN_ROWS),
        saved_at=str(saved_at) if saved_at is not None else None)


def team_model_health() -> TeamModelHealth | None:
    """The newest banked components' goals-conceded band (v19g §2.2).

    ``p_cs_model``, ``e_gc_model`` and ``odds_weight`` are per club-fixture
    but the file is per player, so the frame is reduced first. The key is
    ``(team_code, gw, opp_code)`` and not ``(team_code, gw)``: a double
    gameweek gives a club two fixtures in one week, and keying on the week
    alone would count one of them and hide the other — which is the week the
    reading matters most.

    Never raises, for :func:`calibration_health`'s reason.
    """
    try:
        from gaffer.misses import component_gws

        gws = component_gws()
        if not gws:
            return None
        frame = pd.read_parquet(components_path(gws[-1]))
        needed = ["team_code", "gw", "opp_code", "p_cs_model", "e_gc_model"]
        if any(col not in frame.columns for col in needed):
            return None
        fixtures = frame.drop_duplicates(
            subset=["team_code", "gw", "opp_code"])
        e_gc = pd.to_numeric(fixtures["e_gc_model"], errors="coerce").dropna()
        p_cs = pd.to_numeric(fixtures["p_cs_model"], errors="coerce").dropna()
        if e_gc.empty or p_cs.empty:
            return None
        # A missing `odds_weight` column is every fixture priced with no
        # market, which is the same news as a column of zeros and is reported
        # as such rather than as an absence.
        if "odds_weight" in fixtures.columns:
            weight = pd.to_numeric(fixtures["odds_weight"], errors="coerce")
            zero = int((weight.isna() | (weight == 0)).sum())
        else:
            zero = int(len(fixtures))
        return TeamModelHealth(
            gw=int(fixtures["gw"].max()),
            min_e_gc_model=round(float(e_gc.min()), 3),
            max_p_cs_model=round(float(p_cs.max()), 3),
            fixtures=int(len(fixtures)), zero_odds_fixtures=zero)
    except Exception:  # noqa: BLE001 — a diagnostic never takes the page down
        return None


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
    # `load_config` here rather than `config_in_force`, on purpose: this is the
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
    # what this install is doing. `config_in_force` never raises, so the try
    # is belt and braces for an unforeseeable read.
    try:
        # `invalidate()` first, for the reason the season banner reads
        # `load_config` rather than `config_in_force`: this is the page a user
        # opens *after* editing `[optimizer] top_n`, and a cached reader would
        # keep showing the old pool sizes until the process restarted. One
        # TOML read per health poll is cheap; a card that will not update is
        # a card that teaches the user their edit did nothing.
        #
        # The clear is process-wide, not this call's: `build_pool` reads the
        # same cached view, so the first solve after any health poll pays one
        # TOML read too. That is the whole cost, and it is the right way round
        # — a solve that picks up the edited value is what a user who just
        # edited it expects. `invalidate()` also drops the price-timing table,
        # which is cached on the same terms and goes stale on the same events
        # (v12 W2 §3.4, one call since v17e §2.2).
        invalidate()
        solver_top_n = config_in_force().solver_top_n()
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
    # ``season_config`` above is this payload's one config read. A third read
    # here could disagree with it if the file changed mid-request, and one
    # health line saying 2026-27 beside another saying 2025-26 is a bug report
    # nobody can reproduce. A clone with no config.toml still knows which
    # season the collector would fetch, because Config's own default says so;
    # naming it beats a blank, since "not collected yet (—)" tells the reader
    # nothing.
    season = str(season_config or getattr(Config, "current_season", ""))
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
                  calibration=calibration_health(),
                  team_model=team_model_health(),
                  launchd=LaunchdHealth(log=str(ADVISE_LOG),
                                        present=log_present,
                                        modified_at=log_modified,
                                        last_line=last_line),
                  jobs=job_health(),
                  odds_key_present=odds_key, model_health=model_health,
                  artifacts=artifacts, season_ok=season_ok,
                  season_config=season_config,
                  season_ingested=season_ingested,
                  solver_top_n=solver_top_n,
                  last_backup=last_backup,
                  core_insights=core_insights)


@router.get("/fixtures/ticker", response_model=Ticker)
def ticker(weeks: int = Query(8, ge=1, le=20)) -> Ticker:
    # A shape adapter over ``gaffer.difficulty`` since v18d §2: the rating
    # moved to the core because the ladder and the identity decorator need it
    # and must not import the web layer. The order the core returns — teams by
    # mean difficulty, cells by gameweek — is the order served.
    rated = rate_fixtures(weeks)
    return Ticker(
        gws=rated.gws, source=rated.source,
        teams=[TickerTeam(code=team.code, name=team.name,
                          short_name=team.short_name,
                          mean_difficulty=team.mean_difficulty,
                          cells=[TickerCell(gw=cell.gw,
                                            opponent=cell.opponent,
                                            home=cell.home,
                                            difficulty=cell.difficulty)
                                 for cell in team.cells])
               for team in rated.teams])
