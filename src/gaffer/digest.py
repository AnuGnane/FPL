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
import math
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
from gaffer.watchlist import load_watchlist, watch_targets

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
    tmp = path.with_name(path.name + ".tmp")
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
            status = str(getattr(row, "status", "") or "")
            chance = getattr(row, "chance_of_playing", None)
            verdict = str(getattr(row, "llm_verdict", "") or "")
            pieces = []
            if status and status != "a":
                pieces.append(f"status {status}")
            if chance is not None and not (isinstance(chance, float)
                                           and math.isnan(chance)) \
                    and float(chance) < 100.0:
                pieces.append(f"{int(float(chance))}% to play")
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
        verdict = str(getattr(row, "verdict", "") or "")
        if verdict and verdict in DOUBT_VERDICTS:
            code = int(getattr(row, "code"))
            out.append(f"{names.get(code, str(code))} — the presser said "
                       f"{verdict}")
    return out


def _movers_bits(watched: dict[int, str],
                 names: dict[int, str]) -> list[str | None]:
    """Tonight's likely changes, off the same banked snapshot the card uses."""
    if not watched:
        return []
    try:
        from gaffer.data import store
        from gaffer.prices import price_alerts

        if not store.exists("live/players.parquet"):
            return []
        alerts = price_alerts(store.load("live/players.parquet"),
                              list(watched))
    except Exception as exc:  # noqa: BLE001
        print(f"digest: no price readings ({exc})")
        return []
    out: list[str | None] = []
    for row in alerts.itertuples():
        code = int(getattr(row, "code"))
        caveat = " (FPL still calibrating him)" \
            if bool(getattr(row, "calibrating", False)) else ""
        out.append(f"{names.get(code, str(row.name))} may "
                   f"{row.direction} tonight "
                   f"({round(float(row.price_change_percent))}%)"
                   f"{caveat}")
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
    names = _names()
    watched = watch_targets()
    advice = _advice(gw)

    sections = []
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
            f"{top.get('name')} — {top.get('ep')} xPts"
            + (f", {top.get('league_eo')}% league ownership"
               if top.get("league_eo") is not None else "")
            if top else None]))

    try:
        warning = data_warning(upcoming_gw(), ingested_through())
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
            f"{len(summary.get('gws') or [])} gameweeks reviewed.",
            f"{summary.get('hindsight_gap')} points lost to bench and "
            f"armband across {summary.get('hindsight_gap_gws')} of them."
            if summary.get("hindsight_gap_gws") else None,
            f"Worst single decision so far: GW{worst.get('gw')} "
            f"{worst.get('lane')} ({worst.get('label')})."
            if worst else None]))

    kept = [s for s in sections if s is not None]
    headline = (f"GW{gw}: you {row.get('my_points')}, model "
                f"{row.get('model_points')}." if row is not None
                else "The season has not been reviewed yet — run "
                     "`gaffer review`.")
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

def _script(title: str, body: str) -> str:
    """The AppleScript one-liner, with both halves safely quoted.

    ``json.dumps`` rather than an f-string with quotes round it: a player
    called O'Brien, a watchlist note with a double quote in it, or a backslash
    anywhere would otherwise either break the script or — worse — change what
    it does. JSON string escaping and AppleScript string escaping agree on
    every character that matters here.
    """
    return (f"display notification {json.dumps(body)} "
            f"with title {json.dumps(title)}")


def _notify(title: str, body: str) -> bool:
    """Show a macOS notification. ``True`` if it went out.

    Best-effort in the strongest sense: no ``osascript`` at all (a Linux CI
    box), a refused Notification Centre permission, a non-zero exit and a hang
    are each a printed line and a ``False``. ``shell=False`` throughout — the
    argv list is the whole defence against everything ``_script`` quotes.
    """
    try:
        done = subprocess.run(["osascript", "-e", _script(title, body)],
                              capture_output=True, timeout=NOTIFY_TIMEOUT_S,
                              check=False)
        if done.returncode != 0:
            print(f"notification not shown: osascript exited "
                  f"{done.returncode}")
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
        print(f"digest not built: {exc}")
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
