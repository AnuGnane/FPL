"""The Friday briefing and the Tuesday debrief.

Everything this module reports has been on disk for cycles. The advice, the
availability frame, the presser verdicts, the price predictor, the decision
ledger, the league simulation history and the biggest misses are all banked,
all readable, and all findable only by opening the tool and clicking through
four hubs. That is the gap: a manager who forgets to look on a Friday evening
does not get told, and a system that only answers when polled is not a
companion.

So this module joins the seven and says two sentences on a schedule. Friday at
17:00, after the pressers and before the deadline: what the plan is, who is
flagged, what moves tonight, and one differential. Tuesday at 09:30, after the
09:00 review job has banked the week: how it went, what it cost, and where the
league sits now.

Three constraints shape all of it.

**A section whose input is missing is absent, not empty.** "Last week: no
data" is a sentence about the tool; the absence of a section is a sentence
about the season, and a manager reading a digest on his phone deserves the
second one. Every builder below returns ``None`` rather than an empty section,
and the assembler drops the ``None``s.

**Nothing here writes anything but its own artifact.** The ledger's own
appender holds a lock and is that store's only writer, and the review job that
calls it runs half an hour before the Tuesday digest. A digest that re-graded
a gameweek in order to report on it would be a second writer on a locked store
on a schedule, which is the kind of bug that shows up once in November and
takes a weekend. Every input here comes through a loader that already never
raises. A test asserts this module's source names no writer at all.

**Nothing here may raise.** The caller is a launchd job with nowhere to report
a traceback. :func:`run_digest` has one ``except`` and returns ``None``.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from gaffer import artifacts
from gaffer.artifacts import (data_warning, ingested_through, latest_gw,
                              load_advice, load_availability, load_snapshot,
                              upcoming_gw)
from gaffer.errors import GafferError
from gaffer.watchlist import watch_targets

DIGEST_KINDS = ("friday", "tuesday")

NOTIFY_TIMEOUT_S = 10
"""Seconds to wait for ``osascript``. Long enough for a cold Notification
Centre, short enough that a hung binary cannot wedge a launchd job."""

DOUBT_VERDICTS = {"doubt", "out", "major_doubt"}
"""The classifier verdicts worth waking somebody about. ``fit`` and an absent
verdict are both "nothing to say"."""


# --- the store --------------------------------------------------------

def digest_path(kind: str) -> Path:
    """``reports/digest_{kind}.json``, resolved at call time."""
    return artifacts.REPORTS / f"digest_{kind}.json"


def save_digest(kind: str, payload: dict) -> Path:
    """Write one digest through a temp file and ``os.replace``.

    Replace rather than append. A digest is about *now*, the ledger already
    keeps the season's history properly, and a log of forty Fridays is a file
    nobody reads that costs a schema decision.
    """
    artifacts.REPORTS.mkdir(parents=True, exist_ok=True)
    path = digest_path(kind)
    # The temp name carries the pid: two digests writing at once (the Friday
    # job and a hand-run ``gaffer digest``) would otherwise share one temp
    # file, and the loser's ``finally`` would unlink the winner's write out
    # from under it. ``os.replace`` is still what makes the swap atomic.
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=1, allow_nan=False))
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def load_digest(kind: str) -> dict | None:
    """One banked digest, or ``None``. Never raises."""
    path = digest_path(kind)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001 — a corrupt digest is no digest
        print(f"digest {kind} unreadable, ignoring it: {exc}")
        return None
    return payload if isinstance(payload, dict) else None


# --- section helpers --------------------------------------------------

def _section(key: str, title: str, bits: list[str | None]) -> dict | None:
    """One section, or ``None`` when nothing survived.

    The single place the absent-not-empty rule is enforced, so a builder can
    hand in a list with holes in it and get either a section worth rendering
    or nothing at all.
    """
    kept = [str(bit) for bit in bits if bit]
    return {"key": key, "title": title, "bits": kept} if kept else None


def _text(row, field: str) -> str:
    """One string cell, or ``""``. Null-safe for every flavour of null.

    ``reports/availability_gw*.parquet`` stores ``status`` and ``llm_verdict``
    as pandas ``string``, so an unclassified player arrives as ``pd.NA`` — and
    ``pd.NA or ""`` calls ``NAType.__bool__``, which raises "boolean value of
    NA is ambiguous" and takes the whole briefing with it. Three nulls reach
    these frames (``None`` from JSON, ``float('nan')`` from a numpy column,
    ``pd.NA`` from a nullable one) and ``pd.isna`` is the only test that
    answers all three without evaluating truthiness.
    """
    value = getattr(row, field, None)
    return "" if value is None or pd.isna(value) else str(value)


def _flag(row, field: str) -> bool:
    """One boolean cell, or ``False``. ``pd.NA`` is not yet ``True``.

    Same hazard as :func:`_text`: ``override`` and ``price_change_calibrating``
    are nullable booleans, and ``bool(pd.NA)`` raises rather than returning
    anything. An unrecorded flag is a flag that is not set.
    """
    value = getattr(row, field, None)
    return False if value is None or pd.isna(value) else bool(value)


def _number(row, field: str) -> float | None:
    """One numeric cell, or ``None``. ``pd.NA`` never reaches ``float()``."""
    value = getattr(row, field, None)
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _names() -> dict[int, str]:
    """``{code: name}`` from the bootstrap snapshot, or ``{}``.

    An absent snapshot is a clone that has never refreshed, which is a normal
    state and not worth a line in a launchd log; only a snapshot that exists
    and will not read is reported.
    """
    from gaffer.data import store

    if not store.exists("live/players.parquet"):
        return {}
    try:
        players = load_snapshot("live/players.parquet")
        return {int(r.code): str(r.name) for r in players.itertuples()}
    except Exception as exc:  # noqa: BLE001 — a name is not worth a failure
        print(f"digest: player snapshot unreadable ({exc})")
        return {}


def _advice(gw: int | None) -> dict | None:
    if gw is None:
        return None
    try:
        return load_advice(int(gw))
    except Exception as exc:  # noqa: BLE001
        print(f"digest: no advice payload for GW{gw} ({exc})")
        return None


def _behind_bit(gw: int | None, upcoming: int | None) -> str | None:
    """The one sentence a briefing about last week's plan owes the manager.

    ``latest_gw`` is the newest *solved* gameweek and ``upcoming_gw`` is the
    next deadline, and the briefing had been reading the first and warning off
    the second without ever comparing them: a Friday after the GW5 deadline
    with only a GW5 solve on disk briefed the GW5 plan, counted down to a
    deadline that had passed, and said nothing about GW6 at all.

    Either helper answering ``None`` is not a claim in either direction — a
    clone with no solve state and a pre-season with no next event both land
    there — so the bit is absent rather than guessed.
    """
    if gw is None or upcoming is None:
        return None
    try:
        behind = int(upcoming) > int(gw)
    except (TypeError, ValueError):
        return None
    if not behind:
        return None
    return (f"This plan is for GW{int(gw)}; GW{int(upcoming)} is the next "
            f"deadline — run `gaffer advise`.")


def _deadline_bits(gw: int | None) -> list[str | None]:
    """How long is left, from the events snapshot rather than the network."""
    if gw is None:
        return []
    try:
        events = load_snapshot("live/events.parquet")
        row = events[pd.to_numeric(events["gw"], errors="coerce") == int(gw)]
        if row.empty:
            return []
        when = pd.to_datetime(row["deadline_time"].iloc[0], utc=True,
                              format="mixed")
        # A null or unparseable stamp parses to NaT rather than raising, so
        # the guard above lets it through and everything below throws:
        # ``NaT.strftime`` is a ValueError, and NaT arithmetic is nan, which
        # fails both hour guards and reaches ``round(nan / 24)``. Either one
        # escapes the whole briefing. An absent countdown is the section-level
        # degradation this module promises instead.
        if pd.isna(when):
            return []
    except Exception as exc:  # noqa: BLE001
        print(f"digest: no deadline for GW{gw} ({exc})")
        return []
    hours = (when - pd.Timestamp.now(tz="UTC")).total_seconds() / 3600.0
    stamp = when.strftime("%a %d %b %H:%M UTC")
    if hours < 0:
        # A digest generated after the deadline is still worth writing — it is
        # what a Saturday morning re-run produces — and saying "in -3 hours"
        # would be worse than saying nothing about the countdown.
        return [f"GW{gw} deadline was {stamp}."]
    if hours < 48:
        return [f"GW{gw} deadline {stamp} — {round(hours)} hours away."]
    return [f"GW{gw} deadline {stamp} — {round(hours / 24)} days away."]


def _flagged_bits(gw: int | None, watched: dict[int, str],
                  names: dict[int, str]) -> list[str | None]:
    """Watched players the availability pass or a presser is unhappy about.

    Restricted to the watch set on purpose: an injury list of the whole league
    is a website, and this is a message about the manager's own week.
    """
    if gw is None or not watched:
        return []
    bits: list[str | None] = []
    try:
        avail = load_availability(int(gw))
    except Exception as exc:  # noqa: BLE001
        print(f"digest: no availability for GW{gw} ({exc})")
        avail = None
    if avail is not None and "code" in getattr(avail, "columns", []):
        codes = pd.to_numeric(avail["code"], errors="coerce")
        rows = avail[codes.isin(list(watched))]
        for row in rows.itertuples():
            code = int(getattr(row, "code"))
            name = names.get(code, str(code))
            status = _text(row, "status")
            chance = _number(row, "chance_of_playing")
            verdict = _text(row, "llm_verdict")
            pieces = []
            if status and status != "a":
                pieces.append(f"status {status}")
            if chance is not None and chance < 100.0:
                pieces.append(f"{int(chance)}% to play")
            if verdict in DOUBT_VERDICTS:
                pieces.append(f"news says {verdict}")
            if pieces:
                bits.append(f"{name} — {', '.join(pieces)}"
                            f" ({watched.get(code, 'watchlist')})")
    bits.extend(_presser_bits(gw, watched, names))
    return bits


def _presser_bits(gw: int, watched: dict[int, str],
                  names: dict[int, str]) -> list[str]:
    """Anything the press-conference log said about a watched player."""
    try:
        from gaffer.data.news.presser_log import load_presser_log

        log = load_presser_log()
    except Exception as exc:  # noqa: BLE001
        print(f"digest: no presser log ({exc})")
        return []
    if log is None or log.empty or "code" not in log.columns:
        return []
    rows = log[(pd.to_numeric(log["gw"], errors="coerce") == int(gw))
               & (pd.to_numeric(log["code"],
                                errors="coerce").isin(list(watched)))]
    out = []
    for row in rows.itertuples():
        verdict = _text(row, "verdict")
        if verdict in DOUBT_VERDICTS:
            code = int(getattr(row, "code"))
            out.append(f"{names.get(code, str(code))} — the presser said "
                       f"{verdict}")
    return out


PLAYERS_PATH = "live/players.parquet"

PRICE_FIELDS = {"now_cost": "now_cost",
                "price_change_percent": "price_change_percent",
                "price_change_calibrating": "calibrating"}
"""``{bootstrap column: price-log column}``. The log's own names are the
short ones (:data:`gaffer.price_log.PRICE_LOG_COLS`); the bootstrap's are what
:func:`gaffer.prices.price_alerts` reads, so the join renames as it goes."""


def _file_stamp(rel: str) -> str | None:
    """One data file's mtime as an ISO instant, or ``None``."""
    from gaffer.data import store

    try:
        return datetime.fromtimestamp(
            (store.DATA_DIR / rel).stat().st_mtime,
            tz=timezone.utc).isoformat(timespec="seconds")
    except OSError:
        return None


def _price_log_overlay(players: pd.DataFrame,
                       players_stamp: str | None
                       ) -> tuple[pd.DataFrame | None, str | None]:
    """``players`` with the newest banked day's price fields, or ``(None,
    None)`` when the log has nothing fresher to say.

    ``data/live/players.parquet`` is only rewritten by ``advise`` and
    ``refresh-data``, but the nightly ``gaffer prices`` job banks the whole
    league's predictor readings every day. On a Friday whose last advise run
    was Tuesday the log is three days newer, and a movers card quoting Tuesday
    on a Friday evening is exactly the thing this cycle promised not to do.

    Names and teams stay on the left: the log deliberately banks no ``name``
    (a code is a stable key and a web name is not), so only the price columns
    cross over, and only for players the log actually has a row for.
    """
    from gaffer.data import store
    from gaffer.price_log import PRICE_LOG_PATH, load_price_log

    if not store.exists(PRICE_LOG_PATH):
        return None, None
    log = load_price_log()
    if log is None or log.empty or not {"snap_date", "code"} \
            .issubset(log.columns):
        return None, None
    days = log["snap_date"].astype(str)
    day = max(days)                      # ISO dates sort lexically
    # Date against date: the log's key is a UTC day, so "newer" can only be
    # decided to the day, and same-day ties go to the snapshot.
    if players_stamp is not None and day <= players_stamp[:10]:
        return None, None
    rows = log[days == day].assign(
        _code=pd.to_numeric(log.loc[days == day, "code"], errors="coerce"))
    rows = rows.dropna(subset=["_code"]).drop_duplicates("_code")
    if rows.empty or "price_change_percent" not in rows.columns:
        return None, None

    out = players.copy()
    codes = pd.to_numeric(out["code"], errors="coerce")
    for dst, src in PRICE_FIELDS.items():
        if src not in rows.columns:
            continue
        fresh = codes.map(dict(zip(rows["_code"], rows[src])))
        have = out[dst] if dst in out.columns else None
        out[dst] = fresh.where(fresh.notna(), have)
    return out, (_file_stamp(PRICE_LOG_PATH) or f"{day}T00:00:00+00:00")


def freshest_prices() -> tuple[pd.DataFrame | None, str | None, str]:
    """The newest price reading on disk: ``(frame, as_of, source)``.

    ``source`` is ``"price_log"`` when the nightly bank was newer than the
    bootstrap snapshot and ``"players"`` otherwise, and the caller is expected
    to say which one it served — a panel that quietly swapped its source would
    be making a different claim under the same label.

    Never raises. A missing snapshot is ``(None, None, "players")``, and every
    way the log can be unusable — absent, corrupt, missing columns, no day
    newer than the snapshot — lands on the snapshot alone, which is the
    behaviour that existed before the log did.

    It lives here rather than in the web router because both consumers need
    it and only one of them is allowed to import FastAPI.
    """
    from gaffer.data import store

    if not store.exists(PLAYERS_PATH):
        return None, None, "players"
    # The mtime is read before the parquet so a file that exists but will not
    # parse still reports its age rather than nothing.
    stamp = _file_stamp(PLAYERS_PATH)
    try:
        players = store.load(PLAYERS_PATH)
    except Exception as exc:  # noqa: BLE001 — a card is never worth a 500
        print(f"prices: player snapshot unreadable ({exc})")
        return None, stamp, "players"
    try:
        merged, log_stamp = _price_log_overlay(players, stamp)
    except Exception as exc:  # noqa: BLE001 — a bad log is no log
        print(f"prices: price log unusable, keeping the snapshot ({exc})")
        return players, stamp, "players"
    if merged is None:
        return players, stamp, "players"
    return merged, log_stamp, "price_log"


def _movers_bits(watched: dict[int, str],
                 names: dict[int, str]) -> list[str | None]:
    """Tonight's likely changes, off the freshest readings on disk."""
    if not watched:
        return []
    try:
        from gaffer.prices import price_alerts

        players, _as_of, _source = freshest_prices()
        if players is None or players.empty:
            return []
        alerts = price_alerts(players, list(watched))
    except Exception as exc:  # noqa: BLE001
        print(f"digest: no price readings ({exc})")
        return []
    out: list[str | None] = []
    for row in alerts.itertuples():
        code = int(getattr(row, "code"))
        caveat = " (FPL still calibrating him)" \
            if _flag(row, "calibrating") else ""
        percent = _number(row, "price_change_percent")
        out.append(f"{names.get(code, _text(row, 'name') or str(code))} may "
                   f"{_text(row, 'direction') or 'move'} tonight"
                   + (f" ({round(percent)}%)" if percent is not None else "")
                   + caveat)
    return out


# --- Friday -----------------------------------------------------------

def friday_briefing() -> dict:
    """What needs doing before the deadline.

    Never raises: every read below is a loader that already answers ``None``
    or an empty frame on failure, and the ones that are not are wrapped.
    """
    gw = None
    try:
        gw = latest_gw()
    except Exception as exc:  # noqa: BLE001
        print(f"digest: no advice on disk ({exc})")
    upcoming = None
    try:
        upcoming = upcoming_gw()
    except Exception as exc:  # noqa: BLE001
        print(f"digest: no upcoming gameweek ({exc})")
    names = _names()
    watched = watch_targets()
    advice = _advice(gw)

    sections = []
    # First, and before the plan it is about. Everything below this line —
    # the countdown, the move, the flags — is read off the *newest solved*
    # gameweek, and a Friday on which the deadline has rolled past it would
    # otherwise brief the manager confidently about last week. This is the
    # comparison ``web/routers/advice.py`` already makes for the staleness
    # strip (``behind = current > advice_gw``), said in the digest's voice.
    sections.append(_section("stale_plan", "This plan is a week behind",
                             [_behind_bit(gw, upcoming)]))
    sections.append(_section("deadline", "Deadline", _deadline_bits(gw)))

    if advice is not None:
        buys = ", ".join(str(p.get("name")) for p in advice.get("buys") or [])
        sells = ", ".join(str(p.get("name"))
                          for p in advice.get("sells") or [])
        captain = (advice.get("captain") or {}).get("name")
        hits = int(advice.get("hits") or 0)
        move = (f"{buys or 'nobody'} in, {sells or 'nobody'} out"
                + (f" — {hits} hit{'s' if hits != 1 else ''}" if hits else ""))
        sections.append(_section("move", "The plan", [
            move,
            f"Captain {captain}." if captain else None,
            f"{advice.get('expected_pts')} expected points from the XI."
            if advice.get("expected_pts") is not None else None]))

    sections.append(_section("flagged", "Watch out for",
                             _flagged_bits(gw, watched, names)))
    sections.append(_section("movers", "Prices tonight",
                             _movers_bits(watched, names)))

    if advice is not None:
        alts = advice.get("alternatives") or []
        top = alts[0] if alts else None
        sections.append(_section("differential", "One to consider", [
            f"{top.get('name')} — {round(float(top.get('ep') or 0.0), 2)} xPts"
            + (f", {top.get('league_eo')}% league ownership"
               if top.get("league_eo") is not None else "")
            if top else None]))

    try:
        warning = data_warning(upcoming, ingested_through())
    except Exception as exc:  # noqa: BLE001
        print(f"digest: no staleness reading ({exc})")
        warning = None
    sections.append(_section("staleness", "Data", [warning]))

    kept = [s for s in sections if s is not None]
    if advice is None:
        headline = ("No advice on disk — run `gaffer advise` before the "
                    "deadline.")
    else:
        cap = (advice.get("captain") or {}).get("name") or "nobody"
        buys = advice.get("buys") or []
        headline = (f"GW{gw}: captain {cap}, "
                    + (f"{len(buys)} transfer"
                       f"{'s' if len(buys) != 1 else ''}." if buys
                       else "no transfers."))
    return {"kind": "friday", "generated_at": _now(), "gw": gw,
            "headline": headline, "sections": kept}


# --- Tuesday ----------------------------------------------------------

def tuesday_debrief() -> dict:
    """How last week actually went, off the ledger the review job banked."""
    from gaffer.review import load_ledger, season_summary

    ledger = load_ledger()
    row = ledger[-1] if ledger else None
    gw = int(row["gw"]) if row else None

    sections = []
    if row is not None:
        graded = [lane for lane in (row.get("lanes") or [])
                  if lane.get("delta_pts") is not None]
        worst = min(graded, key=lambda lane: lane["delta_pts"]) \
            if graded else None
        sections.append(_section("verdict", f"GW{gw}", [
            f"You scored {row.get('my_points')}; the model's plan scored "
            f"{row.get('model_points')}."
            if row.get("model_points") is not None else
            f"You scored {row.get('my_points')}.",
            f"Accuracy {row.get('accuracy')}."
            if row.get("accuracy") is not None else None,
            f"Worst lane: {worst['lane']} {worst['delta_pts']:+d} "
            f"({worst.get('label')})." if worst else None,
            f"{row.get('points_on_bench')} points left on the bench."
            if row.get("points_on_bench") is not None else None]))
        gap = (row.get("hindsight") or {}).get("gap")
        sections.append(_section("hindsight", "Hindsight XI", [
            f"The best eleven from your fifteen would have scored {gap} more."
            if gap is not None else None]))

    sections.append(_section("league", "League", _league_bits()))
    sections.append(_section("miss", "Biggest miss", _miss_bits()))

    summary = season_summary(ledger)
    if summary is not None:
        worst = summary.get("worst")
        sections.append(_section("season", "Season so far", [
            f"{len(summary.get('gws') or [])} gameweek"
            f"{'s' if len(summary.get('gws') or []) != 1 else ''} reviewed.",
            f"{summary.get('hindsight_gap')} points lost to bench and "
            f"armband across {summary.get('hindsight_gap_gws')} of them."
            if summary.get("hindsight_gap_gws") else None,
            f"Worst single decision so far: GW{worst.get('gw')} "
            f"{worst.get('lane')} ({worst.get('label')})."
            if worst else None]))

    kept = [s for s in sections if s is not None]
    if row is None:
        headline = ("The season has not been reviewed yet — run "
                    "`gaffer review`.")
    elif row.get("model_points") is None:
        # A ``no_advice`` week — GW1 of this season is one. The model did not
        # score badly, it never spoke, and "model None." reads as the first of
        # those while being a Python repr in a push notification.
        headline = (f"GW{gw}: you {row.get('my_points')} — no advice "
                    f"survived to compare.")
    else:
        headline = (f"GW{gw}: you {row.get('my_points')}, model "
                    f"{row.get('model_points')}.")
    return {"kind": "tuesday", "generated_at": _now(), "gw": gw,
            "headline": headline, "sections": kept}


def _league_bits() -> list[str | None]:
    """Where the title race sits, and which way it moved.

    One simulated gameweek is a *level*, not a movement: reporting "+14pp"
    against nothing would invent a trend out of a first reading.
    """
    try:
        from gaffer.league_sim import load_sim_history

        history = load_sim_history()
    except Exception as exc:  # noqa: BLE001
        print(f"digest: no league sim history ({exc})")
        return []
    if not history:
        return []
    now = history[-1]
    current = float(now.get("p_win") or 0.0)
    bits = [f"Win probability {round(current * 100)}% after GW{now.get('gw')}."]
    if len(history) > 1:
        before = float(history[-2].get("p_win") or 0.0)
        delta = round((current - before) * 100)
        bits.append(f"{delta:+d}pp since GW{history[-2].get('gw')}.")
    return bits


def _miss_bits() -> list[str | None]:
    """The single largest forecast error of the newest scored week.

    Deliberately not the debrief's own gameweek. ``scoreable_gw`` is the
    largest week with *both* a components parquet and played rows, which is
    the only week a miss can be computed for; the reviewed week may predate
    the oldest components file on a clone, and a section that silently
    reported a different week than the heading claimed would be worse than no
    section. The bit names its gameweek for exactly that reason.
    """
    try:
        from gaffer.misses import biggest_misses, scoreable_gw

        target = scoreable_gw()
        if target is None:
            return []
        rows = biggest_misses(int(target))
    except Exception as exc:  # noqa: BLE001
        print(f"digest: no miss table ({exc})")
        return []
    if not rows:
        return []
    top = rows[0]
    direction = "over" if top["miss"] < 0 else "under"
    return [f"GW{target}: {top['name']} — forecast {top['ep']}, scored "
            f"{top['actual']}. The model {direction}rated him by "
            f"{abs(top['miss'])}."]


# --- the notification -------------------------------------------------

NOTIFY_SCRIPT = ("on run argv",
                 "display notification (item 1 of argv) "
                 "with title (item 2 of argv)",
                 "end run")
"""The AppleScript, with nothing user-controlled in it.

An earlier version escaped the title and body into the source with
``json.dumps``, on the theory that JSON and AppleScript string escaping agree
on every character that matters. They do not agree on one: JSON escapes
non-ASCII as ``\\uXXXX`` and AppleScript has no such escape, so the em dash in
:data:`TITLES` compiled to a syntax error and *every* notification this cycle
exited 1 with ``Expected “"” but found unknown token``. The class of bug is
the interpolation, not the em dash, so the fix removes the interpolation: an
``on run`` handler takes both halves as arguments after ``--``, where the
kernel carries them byte for byte and no quoting exists to get wrong.
"""


def _notify(title: str, body: str) -> bool:
    """Show a macOS notification. ``True`` if it went out.

    Best-effort in the strongest sense: no ``osascript`` at all (a Linux CI
    box), a refused Notification Centre permission, a non-zero exit and a hang
    are each a printed line and a ``False``. ``shell=False`` throughout, and
    the two strings are ``argv`` entries rather than source.
    """
    argv = ["osascript"]
    for line in NOTIFY_SCRIPT:
        argv += ["-e", line]
    try:
        done = subprocess.run(argv + [body, title], capture_output=True,
                              timeout=NOTIFY_TIMEOUT_S, check=False)
        if done.returncode != 0:
            detail = (done.stderr or b"").decode("utf-8", "replace").strip()
            print(f"notification not shown: osascript exited "
                  f"{done.returncode}"
                  + (f" — {detail}" if detail else ""))
            return False
        return True
    except Exception as exc:  # noqa: BLE001 — never a reason to fail a job
        print(f"notification not shown: {exc}")
        return False


# --- the runner -------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def format_digest(payload: dict) -> str:
    """The one line the CLI and the launchd log both print."""
    return (f"{payload.get('kind', '?').title()} digest: "
            f"{payload.get('headline')} "
            f"({len(payload.get('sections') or [])} sections)")


TITLES = {"friday": "Gaffer — Friday briefing",
          "tuesday": "Gaffer — Tuesday debrief"}


def _bank_failure(kind: str, exc: BaseException) -> None:
    """Write the digest that says there is no digest. Never raises.

    The envelope is the ordinary one so the card and the schema need no
    special case; ``sections`` is empty and ``error`` carries the exception's
    type and message. No traceback: this artifact is read by a card on a
    phone, and the traceback is already in the job log.
    """
    reason = f"{type(exc).__name__}: {exc}"
    try:
        save_digest(kind, {"kind": kind, "generated_at": _now(), "gw": None,
                           "headline": f"{kind.title()} digest failed to "
                                       f"build — {reason}",
                           "sections": [], "error": reason})
    except Exception as write_exc:  # noqa: BLE001 — two failures, still no raise
        print(f"digest failure not written: {write_exc}")


def run_digest(kind: str, *, notify: bool = True) -> dict | None:
    """Build one digest, bank it, print one line, maybe notify.

    ``notify`` is an argument and not a config read on purpose: this module
    knows how to send a notification and has no opinion about whether it
    should, and the caller that reads ``[digest] notify`` is the CLI command
    and the job kind (plan A7).

    An unknown kind raises — it can only come from a typo in a plist or a
    hand-typed CLI flag, and guessing "friday" for "wednesday" would be a
    silently wrong digest on a schedule. Everything else is swallowed: a
    Friday with no network is a Friday with no briefing, not a traceback in
    ``logs/digest-friday.log``.
    """
    if kind not in DIGEST_KINDS:
        raise GafferError(
            f"unknown digest kind {kind!r} — expected one of "
            f"{', '.join(DIGEST_KINDS)}")
    try:
        payload = (friday_briefing() if kind == "friday"
                   else tuesday_debrief())
    except Exception as exc:  # noqa: BLE001 — a scheduled job never blocks
        # Never raise was only half of it. A Friday that died used to write
        # nothing, so the card fell back to its never-run empty state and the
        # crash lived only in a launchd log nobody opens — which is how gate
        # G1 found this by hand. The failure is a digest too: an artifact
        # with no sections and an ``error`` that names what happened.
        print(f"digest not built: {exc}")
        _bank_failure(kind, exc)
        return None
    try:
        save_digest(kind, payload)
    except Exception as exc:  # noqa: BLE001
        # The payload is still worth returning and printing: a read-only disk
        # should not also cost the user the sentence they were owed.
        print(f"digest not written: {exc}")
    print(format_digest(payload))
    if notify:
        _notify(TITLES[kind], payload["headline"])
    return payload
