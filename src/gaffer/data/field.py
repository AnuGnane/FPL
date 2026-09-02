"""The sampled field: the top-10k squads, kept, and their EO over time.

``tier_eo`` has sampled ~300 top-10k entries on every live poll since v7a and
thrown the squads away the moment it had an average. v8c keeps them. Two
stores, deliberately different in kind:

``data/raw/field/{season}/gw{N}.json``
    the sampled squads for one finished gameweek. A permanent per-gameweek
    fact, cached exactly like :func:`gaffer.data.league.fetch_rival_picks_history`
    caches a rival's played squad — it will never change, so a re-run costs no
    API calls at all. **Anonymous by construction**: the entry ids are dropped
    at the fetch boundary and replaced by the entry's index in the sample, so
    the file records what the field owned and not who owned it.

``data/live/field_eo_log.parquet``
    one row per (gameweek, scrape day, element). The growing instrument: EO
    with its standard error and its sample size, so "Haaland was 62% owned in
    the top 10k in GW7" is answerable in December. ``snapshot.py``'s
    append-by-rewrite idiom, keyed on (gw, snap_date) so a hand re-run is free.

Nothing here raises for a caller that is scheduled. :func:`run_field_scrape`
is the launchd body and swallows everything, exactly as
:func:`gaffer.snapshot.run_snapshot` does.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd

from gaffer.data import store
from gaffer.data.tier_eo import (RAW_TIER, TIER_SAMPLE, TIER_SEED,
                                 eo_from_picks, fetch_sample_picks,
                                 read_tier_cache, tier_cache_path,
                                 write_tier_cache)
from gaffer.io import atomic_save, atomic_write
from gaffer.snapshot import snap_date

RAW_FIELD = Path("data/raw/field")
"""Beside ``data/raw/league`` and ``data/raw/tier_eo``, not under ``live/``:
these are raw API payloads, not derived frames."""

FIELD_EO_PATH = "live/field_eo_log.parquet"

FIELD_EO_COLS = ["season", "gw", "snap_date", "element", "eo", "se", "n"]
"""``element``, not ``code``: the sample is picks straight off the API and a
pick names a season-scoped element. Joining to ``code`` is the *reader's* job
(``players.parquet`` carries both), because a code lookup at write time would
silently drop every player who left the game since the scrape."""

SAMPLE_PICK_KEYS = ("element", "position", "multiplier")
"""The only fields copied out of a pick. Everything else the API sends — and
in particular anything that could identify the entry — is dropped here."""

FIELD_REUSE_HOURS = 1.0
"""D7's courtesy window. A tier-EO cache file younger than this was written by
the live tracker minutes ago; the scrape reuses its numbers for the EO log
rather than firing another ~455 requests at the same endpoint in the same
hour. See :func:`run_field_scrape`."""


def field_sample_path(season: str, gw: int,
                      raw_dir: Path | str = RAW_FIELD) -> Path:
    return Path(raw_dir) / str(season) / f"gw{int(gw)}.json"


def save_field_sample(picks: list[list[dict]], gw: int, season: str,
                      raw_dir: Path | str = RAW_FIELD, *,
                      overwrite: bool = False) -> Path:
    """Bank one gameweek's sampled squads. Idempotent, atomic, anonymous.

    A file that already exists is left exactly as it was rather than
    rewritten: the sample is drawn from a seeded slot list against a *live*
    standings page, so a second draw a day later is a different 300 people,
    and quietly replacing the banked one would rewrite history to match
    whenever the job last happened to run.

    ``overwrite`` is ``--force``'s path and nothing else's. Without it the
    flag was half a flag: :func:`run_field_scrape` fetched a fresh sample,
    paid the ~455 requests for it, then handed it to this function, which
    silently kept the old file and printed a line saying how many entries had
    been scraped. The caller has said in so many words that it wants the bank
    replaced, so it is.
    """
    path = field_sample_path(season, gw, raw_dir)
    if path.exists() and not overwrite:
        return path
    payload = {
        "season": str(season), "gw": int(gw), "n": len(picks),
        "entries": [
            {"i": i,
             "picks": [{k: int(p.get(k, 0)) for k in SAMPLE_PICK_KEYS}
                       for p in entry]}
            for i, entry in enumerate(picks)],
    }
    atomic_write(path, json.dumps(payload))
    return path


def load_field_sample(season: str, gw: int,
                      raw_dir: Path | str = RAW_FIELD
                      ) -> list[list[dict]] | None:
    """The banked squads, or ``None`` when the gameweek was never scraped.

    ``None`` rather than ``[]`` because the scrape's idempotence check reads
    the difference: an empty list is "we sampled and nobody was readable",
    which is a fact worth not re-fetching.
    """
    path = field_sample_path(season, gw, raw_dir)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text())
    except Exception:  # noqa: BLE001 — a corrupt bank is a missing bank
        return None
    return [list(entry.get("picks") or [])
            for entry in payload.get("entries") or []]


def field_eo_rows(table: dict[int, dict], gw: int, season: str,
                  day: str | None = None) -> pd.DataFrame:
    """A tier-EO table -> dated log rows, one per element.

    Dtypes are forced here rather than left to pyarrow's inference, the same
    trade :func:`gaffer.snapshot.snapshot_rows` makes: a gameweek where every
    ``se`` came back 0.0 and one where they are floats would otherwise write
    two incompatible schemas into one growing file.
    """
    rows = [{"season": str(season or ""), "gw": int(gw),
             "snap_date": str(day or snap_date()),
             "element": int(element), "eo": float(cell.get("eo", 0.0)),
             "se": float(cell.get("se", 0.0)), "n": int(cell.get("n", 0))}
            for element, cell in sorted(table.items())]
    out = pd.DataFrame(rows, columns=FIELD_EO_COLS)
    for col in ("season", "snap_date"):
        out[col] = out[col].astype("object").astype("string")
    for col in ("gw", "element", "n"):
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0) \
            .astype("int64")
    for col in ("eo", "se"):
        out[col] = pd.to_numeric(out[col], errors="coerce").astype("float64")
    return out[FIELD_EO_COLS]


def append_field_eo(rows: pd.DataFrame) -> int:
    """Rewrite the log with ``rows`` replacing the same (gw, snap_date) keys.

    :func:`gaffer.snapshot.append_snapshot`'s trade, one key wider: parquet
    has no append, a few hundred rows a week is cheap to re-emit, and
    replacement rather than accumulation is what makes a hand re-run free. The
    key is the *pair* because two gameweeks are scraped on two days but a
    Saturday and a Sunday pass over one gameweek are two rows for one fact and
    only the later one should stand.

    :func:`gaffer.io.atomic_save` reads ``store.DATA_DIR`` at call time rather
    than binding it at import, so a test that redirects the data directory
    redirects both paths together.
    """
    if rows.empty:
        return 0
    existing = (store.load(FIELD_EO_PATH) if store.exists(FIELD_EO_PATH)
                else pd.DataFrame(columns=FIELD_EO_COLS))
    for col in FIELD_EO_COLS:
        if col not in existing.columns:
            existing[col] = None
    keys = set(zip(rows["gw"].astype(int).tolist(),
                   rows["snap_date"].astype(str).tolist()))
    kept = existing[[(int(g), str(d)) not in keys
                     for g, d in zip(existing["gw"], existing["snap_date"])]]
    frames = [f[FIELD_EO_COLS] for f in (kept, rows) if not f.empty]
    merged = (pd.concat(frames, ignore_index=True) if frames
              else rows[FIELD_EO_COLS])
    atomic_save(merged, FIELD_EO_PATH)
    return int(len(rows))


def load_field_eo(*, season: str | None = None) -> pd.DataFrame:
    """Every banked row, or an empty frame with the right columns.

    v12 W1 §2.3: ``season`` narrows the log before anything reads it.
    Optional here and *required* on :func:`latest_field_eo`, deliberately —
    this one is the raw reader the scrape's own tests use to count what was
    banked, where "everything" is a legitimate question. The derived reader
    answers a question about *a* season, where it is not.

    A log with no ``season`` column is a log written before the column
    existed; a named season over such a log is empty, not "everything", for
    the same reason ``latest_field_eo`` has no fallback — "whatever is there"
    is exactly the answer the season keyword exists to prevent.
    """
    if not store.exists(FIELD_EO_PATH):
        return pd.DataFrame(columns=FIELD_EO_COLS)
    log = store.load(FIELD_EO_PATH)
    if season is None:
        return log
    if "season" not in log.columns:
        return log.iloc[0:0]
    # .copy(): a boolean mask over a loaded frame is a view, and a caller that
    # assigns a column into it earns a SettingWithCopyWarning it did not cause.
    return log[log["season"].astype(str) == str(season)].copy()


def latest_field_eo(gw: int | None = None, *,
                    season: str) -> dict[int, dict]:
    """``element -> {"eo", "se", "n", "gw"}`` for the newest scrape.

    One row per element, from the latest ``snap_date`` of the latest gameweek
    (or of ``gw`` when one is named). The sword/shield column reads this, and
    a column that showed a Saturday number beside a Sunday one would be a
    column nobody could reason about.

    ``season`` narrows the log to one season before any of that happens, and
    v12 W1 §2.3 made it **required**. See the comment below for why.

    Empty dict on any failure at all — no log, an unreadable log, a log with
    no rows. F4 is display, and a missing display column is the documented
    degradation (spec §4).
    """
    # v10b §F1a (specs/2026-09-01-gaffer-v10b-eo-chips-design.md, plan A3),
    # completed by v12 W1 §2.3 (specs/2026-09-01-gaffer-v12-program-design.md).
    # ``element`` is season-scoped — FIELD_EO_COLS says so — so a log holding
    # two seasons has two different footballers under one element id, and
    # ``max(gw)`` below picks the *larger gameweek number*, which after a
    # rollover is last season's. The keyword is required rather than optional
    # now, because an optional one is a keyword a caller can forget — and
    # ``routers/players.py`` forgot it for two cycles, recorded as a residual
    # twice, because the bug cannot fire until August.
    #
    # No fallback when the named season has no rows: "whatever is newest"
    # would restore exactly the failure this keyword exists to prevent.
    try:
        frame = load_field_eo(season=season).copy()
    except Exception:  # noqa: BLE001 — a display read never blocks a page
        return {}
    if frame.empty:
        return {}
    frame["gw"] = pd.to_numeric(frame["gw"], errors="coerce")
    frame = frame.dropna(subset=["gw"])
    if frame.empty:
        return {}
    want = int(gw) if gw is not None else int(frame["gw"].max())
    frame = frame[frame["gw"].astype(int) == want]
    if frame.empty:
        return {}
    day = max(str(d) for d in frame["snap_date"])
    frame = frame[frame["snap_date"].astype(str) == day]
    return {int(r.element): {"eo": float(r.eo), "se": float(r.se),
                             "n": int(r.n), "gw": want}
            for r in frame.itertuples()}


EO_CEILING = 200.0
"""The most an EO extrapolation may claim, in the log's own percent units.

``eo_from_picks`` counts a captain twice (``tier_eo.py:154-179``), so a player
every sampled entry starts and captains reads 200. Triple captain can push a
single sample past it — the live log's maximum is 214.7 — but a *projection*
that assumed a chip week would be inventing one, so the clamp sits at the
ceiling the ordinary week can produce. v12 §3.3's "clamped to [0, 1]" is a
fraction-unit clamp on a percent quantity and would floor the whole instrument
at 1.0 (plan A4).
"""


def _samples_by_gw(frame: pd.DataFrame) -> dict[int, dict[int, float]]:
    """``{gw: {element: eo}}`` from each gameweek's latest snapshot day.

    The latest day per gameweek, for :func:`latest_field_eo`'s reason: a
    Saturday number beside a Sunday one is a pair nobody can reason about.
    """
    out: dict[int, dict[int, float]] = {}
    for gw, part in frame.groupby("gw"):
        day = max(str(d) for d in part["snap_date"])
        rows = part[part["snap_date"].astype(str) == day]
        out[int(gw)] = {int(r.element): float(r.eo) for r in rows.itertuples()}
    return out


def _pair_samples(by_gw: dict[int, dict[int, float]], want: int | None
                  ) -> tuple[int, int | None]:
    """``(gw, earlier_gw)`` — the two gameweeks whose samples are compared.

    **The grain decision, isolated to one function** (plan A4). The spec asks
    for two snapshot days of one gameweek; the log cannot hold them and the
    difference would not mean drift if it did, because picks are frozen after
    the deadline. Gameweek to gameweek is the only interval over which field
    ownership moves — and the only one anybody can observe, since next week's
    picks are not public until next week's deadline has passed.

    ``None`` for the earlier gameweek when there is no earlier sample, which
    is the whole of the "no trend" path.
    """
    if not by_gw:
        raise KeyError("no samples")
    gw = int(want) if want is not None else max(by_gw)
    if gw not in by_gw:
        raise KeyError(gw)
    earlier = [g for g in by_gw if g < gw]
    return gw, (max(earlier) if earlier else None)


def field_eo_trend(season: str, gw: int | None) -> dict[int, dict]:
    """``element -> {"eo_first", "eo_last", "delta", "gws_between",
    "deadline_eo", "trend_available"}`` for one season.

    v12 §3.3, at the gameweek grain the log actually has (plan A4).
    ``deadline_eo`` is ``eo_last`` plus one gameweek of the observed drift,
    clamped to ``[0, EO_CEILING]``. With no earlier sample there is no drift
    to project: ``trend_available`` is ``False``, ``delta`` is ``None`` — not
    ``0.0``, which is the different and stronger claim that the field did not
    move — and ``deadline_eo`` is ``eo_last`` unchanged.

    An element the earlier gameweek never sampled also gets no trend.
    ``eo_from_picks`` omits anyone no sampled entry started, so his absence
    means "nobody had him", and differencing against an implied zero would
    read every promoted bench player as a forty-point riser.

    ``season`` is required and positional: element ids are re-issued every
    August, and the same integer is a different footballer on the other side
    of a rollover. ``gw`` carries **no default** for the same guard's sake —
    with one, ``field_eo_trend(3)`` is a legal call in which ``3`` silently
    becomes the *season* and the answer is an empty map rather than an error.
    ``None`` still means "the newest gameweek in the season", but a caller has
    to say so. Empty dict on any failure at all, which is
    :func:`latest_field_eo`'s contract and for its reason — this is display.
    """
    try:
        log = load_field_eo()
    except Exception:  # noqa: BLE001 — a display read never blocks a page
        return {}
    if log is None or log.empty or "season" not in log.columns:
        return {}
    frame = log[log["season"].astype(str) == str(season)].copy()
    if frame.empty:
        return {}
    frame["gw"] = pd.to_numeric(frame["gw"], errors="coerce")
    frame = frame.dropna(subset=["gw"])
    if frame.empty:
        return {}
    by_gw = _samples_by_gw(frame)
    try:
        want, earlier = _pair_samples(by_gw, gw)
    except KeyError:
        return {}

    latest = by_gw[want]
    before = by_gw.get(earlier) if earlier is not None else None
    span = (want - earlier) if earlier is not None else 0
    out: dict[int, dict] = {}
    for element, eo_last in latest.items():
        eo_first = before.get(element) if before else None
        if eo_first is None or span <= 0:
            out[element] = {"eo_first": None, "eo_last": eo_last,
                            "delta": None, "gws_between": None,
                            "deadline_eo": eo_last, "trend_available": False}
            continue
        delta = round(eo_last - eo_first, 1)
        projected = round(min(EO_CEILING, max(0.0, eo_last + delta / span)), 1)
        out[element] = {"eo_first": eo_first, "eo_last": eo_last,
                        "delta": delta, "gws_between": int(span),
                        "deadline_eo": projected, "trend_available": True}
    return out


def fetch_field_sample(client, gw: int, *, sample: int = TIER_SAMPLE,
                       seed: int = TIER_SEED, season: str = "",
                       raw_dir: Path | str = RAW_FIELD, use_bank: bool = True
                       ) -> tuple[list[list[dict]], dict[int, dict]]:
    """``(squads, eo_table)`` for one gameweek, from the bank or from the API.

    The bank is consulted first, so calling this twice for one gameweek costs
    nothing — which is what makes the scrape idempotent and what makes a
    replay over banked weeks free. The EO table is recomputed from the squads
    rather than stored beside them: it is a five-line reduction of data we
    already have, and two copies of a derived number is two copies to get out
    of step.

    ``use_bank=False`` is ``--force``'s path: the caller has said in so many
    words that it wants a fresh draw, and consulting the bank there would make
    the flag a no-op.
    """
    banked = load_field_sample(season, gw, raw_dir) if use_bank else None
    if banked is not None:
        return banked, eo_from_picks(banked)
    picks = fetch_sample_picks(client, gw, sample, seed)
    return picks, eo_from_picks(picks)


def scrape_gw(events: pd.DataFrame, now=None) -> int | None:
    """The gameweek to scrape: the last one whose deadline has passed.

    Post-deadline is the whole point — picks are 404 before it and public
    after it — so this is deliberately *not*
    :func:`gaffer.snapshot.next_unfinished_gw`, which answers a question about
    the news cycle. A Saturday 12:30 run lands on the gameweek being played
    right now, which is exactly the squad we want a record of.

    ``None`` before the season's first deadline, or for an events frame with
    no readable deadline at all.
    """
    if "deadline_time" not in events.columns or events.empty:
        return None
    when = pd.to_datetime(now, errors="coerce", utc=True) if now is not None \
        else pd.Timestamp.now(tz="UTC")
    deadlines = pd.to_datetime(events["deadline_time"], errors="coerce",
                               utc=True)
    passed = events[deadlines.notna() & (deadlines <= when)]
    if passed.empty:
        return None
    return int(pd.to_numeric(passed["gw"], errors="coerce").max())


MAX_FIELD_SAMPLE = 1000
"""Hard ceiling on the scheduled scrape's sample size.

The sample costs roughly one request per entry plus the standings pages it
takes to enumerate them: 300 entries is the ~455 requests D7's courtesy
window is written around, so 1,000 is already about 1,500 requests against a
public API in one burst. ``[league] field_sample`` above this is a typo, not
an instruction, and the clamp is here rather than in ``config.py`` because it
is a property of *this* job's politeness and not of the number."""


def banked_scrape_gw(now=None) -> int | None:
    """:func:`scrape_gw` against the events snapshot already on disk.

    The point is to answer "which gameweek?" with *zero* API requests, so the
    already-banked no-op path can exit before a client is ever built. Every
    Sunday run in a week the Saturday one worked takes this path, and
    ``advise`` refreshes the snapshot far more often than a gameweek turns
    over. ``None`` when there is no snapshot; the caller then pays for the
    bootstrap, which is the only case where it is unavoidable.
    """
    try:
        from gaffer.artifacts import load_snapshot

        return scrape_gw(load_snapshot("live/events.parquet"), now=now)
    except Exception:  # noqa: BLE001 — no snapshot is not an error here
        return None


def _tier_cache_age_s(gw: int, raw_dir: Path | str = RAW_TIER) -> float | None:
    """Seconds since the live tracker last wrote this gameweek's tier cache,
    or ``None`` when it never has."""
    path = tier_cache_path(gw, raw_dir)
    if not path.exists():
        return None
    return max(0.0, time.time() - path.stat().st_mtime)


def run_field_scrape(cfg=None, gw: int | None = None, *, force: bool = False,
                     now=None) -> int | None:
    """Bank one gameweek's field sample and its EO. Rows logged, or ``None``.

    The launchd body, and therefore held to ``run_snapshot``'s contract: one
    printed line whatever happens, and no exception ever leaves this function.
    A missed Saturday is a far cheaper failure than a job that dies loudly at
    12:30 every weekend until somebody uninstalls it.

    Four early exits, each with its own sentence, because "nothing happened"
    has four different meanings here and a scheduled job's log is the only
    place anybody will read them:

    * the switch is off;
    * no deadline has passed yet (pre-season, or a scheduled run in an
      international break);
    * the gameweek is already banked — the idempotence line, and the one the
      Sunday run prints every week the Saturday run worked. It is checked
      against the gameweek :func:`banked_scrape_gw` reads off the events
      snapshot, *before* a client exists, so that exit costs no requests at
      all rather than one bootstrap;
    * D7's courtesy: the live tracker paid for this gameweek's ~455 requests
      inside the last :data:`FIELD_REUSE_HOURS`, so its numbers are logged and
      *nothing is fetched*. No squads are banked on that path, deliberately —
      the tier cache holds an aggregate and the sample store holds squads, and
      inventing the latter from the former is not available. The next run
      finds no bank and does the real work.

    Imports are local for ``cli.py --help``'s sake, the same reason
    :func:`gaffer.snapshot.run_snapshot` gives.
    """
    try:
        from gaffer.api.client import FPLClient
        from gaffer.config import load_config
        from gaffer.data.bootstrap import build_events

        cfg = cfg or load_config()
        if not getattr(cfg, "field_scrape", True) and not force:
            print("field scrape skipped: league.field_scrape is off")
            return None
        season = str(getattr(cfg, "current_season", "") or "")

        def _already_banked(week: int) -> int | None:
            if force:
                return None
            banked = load_field_sample(season, week, RAW_FIELD)
            if banked is None:
                return None
            print(f"field sample for gw{week} already banked "
                  f"({len(banked)} entries) — nothing fetched.")
            return 0

        # The gameweek from the events snapshot advise already wrote, so the
        # already-banked exit costs zero requests rather than one bootstrap.
        # That is the path every Sunday run takes in a week the Saturday run
        # worked, which is most of them.
        offline_gw = int(gw) if gw is not None else banked_scrape_gw(now=now)
        if offline_gw is not None and _already_banked(offline_gw) == 0:
            return 0

        client = FPLClient()
        if gw is None:
            gw = offline_gw if offline_gw is not None \
                else scrape_gw(build_events(client.get_bootstrap()), now=now)
        if gw is None:
            print("field scrape skipped: no gameweek deadline has passed yet")
            return None
        gw = int(gw)

        if _already_banked(gw) == 0:
            return 0

        age = _tier_cache_age_s(gw, RAW_TIER)
        if not force and age is not None and age < FIELD_REUSE_HOURS * 3600:
            table = read_tier_cache(gw, RAW_TIER) or {}
            day = snap_date()
            rows = append_field_eo(field_eo_rows(table, gw, season, day))
            print(f"Field scrape: reused the live tracker's tier-EO fetch "
                  f"for gw{gw} ({rows} EO rows at {day}); no squads sampled.")
            return rows

        picks, table = fetch_field_sample(
            client, gw,
            sample=min(int(getattr(cfg, "field_sample", TIER_SAMPLE)),
                       MAX_FIELD_SAMPLE),
            season=season, raw_dir=RAW_FIELD, use_bank=not force)
        if not picks:
            print(f"field scrape not written: no sampled entry had readable "
                  f"picks for gw{gw}")
            return None
        save_field_sample(picks, gw, season, RAW_FIELD, overwrite=force)
        write_tier_cache(table, gw, RAW_TIER)
        day = snap_date()
        rows = append_field_eo(field_eo_rows(table, gw, season, day))
        print(f"Field scrape: {len(picks)} entries{' (re-banked)' if force else ''}"
              f", {rows} EO rows for gw{gw} at {day}.")
        return rows
    except Exception as exc:  # noqa: BLE001 — a scheduled job never blocks
        print(f"field scrape not written: {exc}")
        return None
