"""GET/POST ``/api/settings`` — the thirteen settings the UI may edit.

Writes ``config.local.toml`` and **never** ``config.toml`` (spec §8: a UI that
edits ``config.toml`` is out of scope, and that file carries the odds API key).
It does not open either file itself: the overlay is read and written through
``config.read_overlay`` / ``config.write_overlay`` and a row's provenance comes
from ``config.value_source``, because since v17e §2.8 no module but
``config.py`` opens either file — a second reader is a second answer to which
value is in force. What is left here is validation and the wire shapes.

The overlay is merged over the base by ``config.load_config``, which since
v17e §2.1 is the only reader there is: every key the tab writes is a
``Config`` field, and every serve-time read of one goes through
``config.config_in_force``. An overlay only the loader honoured would be a
switch that saves and changes nothing.

Refusals use the what-if lab's ``{constraint, error, players}`` shape so the
client has one error shape for every write endpoint, exactly as
``routers/watchlist.py:25-30`` does. ``players`` is always empty here; a
setting is not a player, and inventing a second refusal shape for one endpoint
is how a UI ends up with two error renderers.
"""

from __future__ import annotations

import math

from fastapi import APIRouter, HTTPException

from gaffer.config import (base_exists, invalidate, load_config, out_of_range,
                           read_overlay, value_source, write_overlay)
from gaffer.web.schemas import (SettingOption, SettingRow, SettingsPanel,
                                SettingWrite)
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
calls ``config_in_force().solver_top_n()`` per solve rather than taking the
``Config`` it was handed, so a
multi-week plan that is still solving can cross a ``top_n`` save mid-run. A
note that overstates the isolation is worse than one that admits the seam,
because the reader who hits it has been told it cannot happen.
"""

def _fail(constraint: str, error: str) -> HTTPException:
    return HTTPException(status_code=422,
                         detail={"constraint": constraint, "error": error,
                                 "players": []})


def _options(entry, value) -> list[SettingOption]:
    """The entry's options with the saved value inserted in order when it is
    not offered (v17e §2.5): a hand-edited ``max_hits = 5`` must not render a
    blank select, and the manager must be able to see what is in force before
    they change it.
    """
    if not entry.options:
        return []
    offered = [SettingOption(value=v, label=w) for v, w in entry.options]
    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
    if is_number and value not in {v for v, _ in entry.options}:
        offered.append(SettingOption(value=value, label=entry.label_for(value)))
        offered.sort(key=lambda option: option.value)
    return offered


def _panel() -> SettingsPanel:
    # The base file's parse error is deliberately dropped: if config.toml will
    # not parse, `load_config` below raises and the early return names it in
    # its own words. Keeping a second copy here only to `or` it into a branch
    # that cannot be reached would be a line that looks like a fallback and is
    # not one.
    if not base_exists():
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
    _, local_err = read_overlay()
    live = set(live_keys(cfg))
    rows = []
    for entry in WHITELIST:
        if entry.field not in live:
            continue
        # Through `current_value`, never `getattr(cfg, ...)`: the focus row
        # reads through a reader rather than the dataclass.
        value = current_value(entry, cfg)
        rows.append(SettingRow(
            key=entry.field, label=entry.label, kind=entry.kind,
            value=value, lo=entry.lo, hi=entry.hi,
            choices=list(entry.choices), options=_options(entry, value),
            section=entry.section, help=entry.help,
            source=value_source(entry.section, entry.toml_key)))
    return SettingsPanel(
        rows=rows,
        unavailable=[e.field for e in WHITELIST if e.field not in live],
        overlay_error=local_err, apply_note=APPLY_NOTE)


def _real(entry, number: float) -> float:
    """A float that TOML can write and the objective can use.

    ``config.write_overlay`` writes a bare ``nan``/``inf`` and the loader
    reads it straight back, so ``decay = nan`` would reach the objective and
    turn every score into NaN — the guarded-parse-unguarded-arithmetic shape,
    one file further out. Refused here, where there is still somebody to tell.
    """
    if not math.isfinite(number):
        raise _fail("wrong_type", f"{entry.label} is a real number")
    return number


def _checked(entry, value):
    """The value as it will be written, or a refusal.

    ``bool`` is checked before ``int`` throughout: ``isinstance(True, int)``
    is True in Python, so ``horizon = true`` would otherwise reach the overlay
    as a boolean and come back out of the loader as one. Every range refusal
    is :func:`gaffer.config.out_of_range`, so the sentence a manager reads is
    the sentence the loader raises (v17e §2.3).
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
                            out_of_range(entry.field, v, entry.section))
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
                            out_of_range(entry.field, v, entry.section))
        return {k: int(value[k]) for k in wanted}
    elif kind == "choice":
        if not isinstance(value, str) or value not in entry.choices:
            raise _fail("wrong_type",
                        f"{entry.label} is one of {', '.join(entry.choices)}")
        return value
    else:  # pragma: no cover — a kind with no branch is a wiring bug
        raise _fail("wrong_type", f"{entry.label} cannot be edited here")
    if entry.lo is not None and not entry.lo <= number <= entry.hi:
        raise _fail("out_of_range",
                    out_of_range(entry.field, number, entry.section))
    return number


@router.get("/settings", response_model=SettingsPanel)
def settings() -> SettingsPanel:
    return _panel()


@router.post("/settings", response_model=SettingsPanel)
def save(req: SettingWrite) -> SettingsPanel:
    entry = BY_FIELD.get(req.key)
    if entry is None or entry.field not in set(live_keys()):
        raise _fail("unknown_setting",
                    f"{req.key} is not a setting this page may change")
    raw, err = read_overlay()
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
    write_overlay(raw)
    # v17e §2.2: every cache keyed on the file, dropped in one call. A save
    # that did not drop them would leave a seam on the old value with nothing
    # on the page to say so.
    invalidate()
    return _panel()
