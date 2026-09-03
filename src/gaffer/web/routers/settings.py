"""GET/POST ``/api/settings`` — the nine settings the UI may edit.

Writes ``config.local.toml`` and **never** ``config.toml`` (spec §8: a UI that
edits ``config.toml`` is out of scope, and that file carries the odds API key).
The overlay is merged over the base by ``config.load_config`` and by the three
module-level readers — see ``config.py``'s ``_raw_with_overlay``.

Refusals use the what-if lab's ``{constraint, error, players}`` shape so the
client has one error shape for every write endpoint, exactly as
``routers/watchlist.py:25-30`` does. ``players`` is always empty here; a
setting is not a player, and inventing a second refusal shape for one endpoint
is how a UI ends up with two error renderers.
"""

from __future__ import annotations

import math
import tomllib
from pathlib import Path

import tomli_w
from fastapi import APIRouter, HTTPException

from gaffer.config import (LOCAL_OVERLAY, load_config, optimizer_top_n,
                           serving_config)
from gaffer.io import atomic_write
from gaffer.price_timing import owned_price_falls
from gaffer.web.schemas import SettingRow, SettingsPanel, SettingWrite
from gaffer.web.settings_keys import (BY_FIELD, WHITELIST, current_value,
                                      live_keys)

router = APIRouter(prefix="/api", tags=["settings"])

APPLY_NOTE = (
    "Saved to config.local.toml. A job started after this save reads the new "
    "value, and a page already open keeps the numbers it fetched — reload to "
    "see them change. A job already running mostly keeps the values it "
    "started with, but not entirely: the solver re-reads the candidate pool "
    "on every solve, so a long run can pick up a new pool size part-way "
    "through.")
"""The one sentence the tab renders verbatim about what a save reaches.

Hedged on purpose. The first draft said a running job keeps the values it
started with, full stop, and that is not true of every key: ``build_pool``
calls ``optimizer_top_n()`` per solve rather than taking a ``Config``, so a
multi-week plan that is still solving can cross a ``top_n`` save mid-run. A
note that overstates the isolation is worse than one that admits the seam,
because the reader who hits it has been told it cannot happen.
"""

BASE = "config.toml"


def _fail(constraint: str, error: str) -> HTTPException:
    return HTTPException(status_code=422,
                         detail={"constraint": constraint, "error": error,
                                 "players": []})


def _read(path: Path) -> tuple[dict, str | None]:
    """A TOML file as a dict, plus why it could not be read."""
    if not path.exists():
        return {}, None
    try:
        return tomllib.loads(path.read_text()), None
    except Exception as exc:  # noqa: BLE001 — a read is never worth a 500
        return {}, f"{path.name} is not readable TOML ({exc}) — ignored"


def _panel() -> SettingsPanel:
    # The base file's parse error is deliberately dropped: if config.toml will
    # not parse, `load_config` below raises and the early return names it in
    # its own words. Keeping a second copy here only to `or` it into a branch
    # that cannot be reached would be a line that looks like a fallback and is
    # not one.
    base_raw, _ = _read(Path(BASE))
    local_raw, local_err = _read(Path(LOCAL_OVERLAY))
    if not Path(BASE).exists():
        return SettingsPanel(
            rows=[], unavailable=[e.field for e in WHITELIST],
            overlay_error=("no config.toml — copy config.example.toml to "
                           "config.toml and set fpl.entry_id and "
                           "fpl.league_id"),
            apply_note=APPLY_NOTE)
    try:
        cfg = load_config()
    except Exception as exc:  # noqa: BLE001 — the tab must still render
        return SettingsPanel(rows=[], unavailable=[e.field for e in WHITELIST],
                             overlay_error=f"config.toml unreadable ({exc})",
                             apply_note=APPLY_NOTE)
    live = set(live_keys(cfg))
    rows = []
    for entry in WHITELIST:
        if entry.field not in live:
            continue
        if entry.toml_key in (local_raw.get(entry.section) or {}):
            source = "local"
        elif entry.toml_key in (base_raw.get(entry.section) or {}):
            source = "base"
        else:
            source = "default"
        rows.append(SettingRow(
            key=entry.field, label=entry.label, kind=entry.kind,
            # Through `current_value`, never `getattr(cfg, ...)`:
            # `price_timing` is not a Config field and never becomes one, so
            # a getattr here would drop the one row the reader kind exists for.
            value=current_value(entry, cfg), lo=entry.lo, hi=entry.hi,
            section=entry.section, help=entry.help, source=source))
    return SettingsPanel(
        rows=rows,
        unavailable=[e.field for e in WHITELIST if e.field not in live],
        overlay_error=local_err, apply_note=APPLY_NOTE)


def _real(entry, number: float) -> float:
    """A float that TOML can write and the objective can use.

    ``tomli_w`` writes a bare ``nan``/``inf`` and ``tomllib`` reads them back,
    so ``decay = nan`` would reach the objective and turn every score into
    NaN — the guarded-parse-unguarded-arithmetic shape, one file further out.
    Refused here, where there is still somebody to tell.
    """
    if not math.isfinite(number):
        raise _fail("wrong_type", f"{entry.label} is a real number")
    return number


def _checked(entry, value):
    """The value as it will be written, or a refusal.

    ``bool`` is checked before ``int`` throughout: ``isinstance(True, int)``
    is True in Python, so ``horizon = true`` would otherwise reach the overlay
    as a boolean and come back out of tomllib as one.
    """
    kind = entry.kind
    if kind == "bool":
        if not isinstance(value, bool):
            raise _fail("wrong_type", f"{entry.label} is on or off")
        return value
    if kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise _fail("wrong_type", f"{entry.label} is a whole number")
        number = value
    elif kind == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise _fail("wrong_type", f"{entry.label} is a number")
        number = _real(entry, float(value))
    elif kind == "floats3":
        if (not isinstance(value, list) or len(value) != 3
                or any(isinstance(v, bool) or not isinstance(v, (int, float))
                       for v in value)):
            raise _fail("wrong_type",
                        f"{entry.label} is exactly three numbers, first to "
                        f"third outfield substitute — reset the row to fall "
                        f"back to one flat bench weight")
        for v in value:
            if not entry.lo <= _real(entry, float(v)) <= entry.hi:
                raise _fail("out_of_range",
                            f"each of {entry.label} is between {entry.lo} "
                            f"and {entry.hi}")
        return [float(v) for v in value]
    elif kind == "pool":
        wanted = ("GKP", "DEF", "MID", "FWD")
        if (not isinstance(value, dict) or set(value) != set(wanted)
                or any(isinstance(v, bool) or not isinstance(v, int)
                       for v in value.values())):
            raise _fail("wrong_type",
                        f"{entry.label} is a whole number for each of "
                        f"{', '.join(wanted)}")
        for v in value.values():
            if not entry.lo <= v <= entry.hi:
                raise _fail("out_of_range",
                            f"each of {entry.label} is between "
                            f"{int(entry.lo)} and {int(entry.hi)}")
        return {k: int(value[k]) for k in wanted}
    else:  # pragma: no cover — a kind with no branch is a wiring bug
        raise _fail("wrong_type", f"{entry.label} cannot be edited here")
    if entry.lo is not None and not entry.lo <= number <= entry.hi:
        raise _fail("out_of_range",
                    f"{entry.label} is between {entry.lo} and {entry.hi}")
    return number


def _write(raw: dict) -> None:
    """The overlay, atomically. Two saves in flight must not interleave.

    Through ``gaffer.io.atomic_write`` (W1 §2.11) rather than a seventh copy of
    the pid-temp + ``os.replace`` idiom — the helper exists so that copy is
    never written again. The tab saves one field at a time, so two writers
    racing on this file is a click, not a hypothetical.

    ``tomli_w.dumps`` rather than ``dump``: the helper owns the file handle,
    and the header comment has to go in front of the tables.
    """
    body = ("# Written by the gaffer web UI (v12 W5 §6.2).\n"
            "# Merged over config.toml, key by key. Safe to hand-edit; a key\n"
            "# that is not a config field is ignored with a printed line.\n\n"
            + tomli_w.dumps(raw))
    atomic_write(Path(LOCAL_OVERLAY), body)


@router.get("/settings", response_model=SettingsPanel)
def settings() -> SettingsPanel:
    return _panel()


@router.post("/settings", response_model=SettingsPanel)
def save(req: SettingWrite) -> SettingsPanel:
    entry = BY_FIELD.get(req.key)
    if entry is None or entry.field not in set(live_keys()):
        raise _fail("unknown_setting",
                    f"{req.key} is not a setting this page may change")
    raw, err = _read(Path(LOCAL_OVERLAY))
    if err:
        # Overwriting a file we could not read would discard whatever else the
        # user had put in it. Refuse and say where to look.
        raise _fail("overlay_unreadable", err)
    section = dict(raw.get(entry.section) or {})
    if req.value is None:
        # One reset branch for every kind, `bench_curve` included: TOML has no
        # null, and an empty list is a curve of the wrong length rather than
        # "no curve" (milp treats that as an error at solve time). Removing the
        # key is what falls back to one flat bench weight.
        section.pop(entry.toml_key, None)
    else:
        section[entry.toml_key] = _checked(entry, req.value)
    if section:
        raw[entry.section] = section
    else:
        raw.pop(entry.section, None)
    _write(raw)
    # Three serve-time caches are keyed on this file and every one of them
    # lives for the life of the process, so a save that did not drop them
    # would leave a seam on the old value with nothing on the page to say so.
    # `price_timing()` is uncached by design and needs no line here.
    serving_config.cache_clear()
    optimizer_top_n.cache_clear()
    owned_price_falls.cache_clear()
    return _panel()
