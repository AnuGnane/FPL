"""The eleven settings the UI may edit (v12 W5 §6.2; v13 added the two caps).

A whitelist, not a schema dump. Everything in ``Config`` that is not here is
untouchable from the web: the odds API key above all, and the web token beside
it — an endpoint that handed out or rewrote the app's own front door would be
worse than no settings page — but also the entry and league ids, the training
seasons, and every news switch whose failure mode is a silently degraded
availability pass.

Four of the spec's nine names do not name anything in this tree and are
mapped here rather than in prose (plan A4):

* ``bench_weights`` is ``bench_curve``;
* ``lambda_tilt`` is ``lambda_cap`` — λ itself is *computed* per gameweek and
  stored on the solve state, so there is nothing to configure but its cap;
* ``chip θ priors path`` is not a path. ``load_decision_priors`` reads a
  resource packaged with ``gaffer.assets`` (``assets/__init__.py:53-64``) and
  there is no filesystem location to point at; the only related knob is
  ``decision_priors``, which decides whether the asset is consulted at all;
* the spec's ``[solver]`` section does not exist. ``top_n`` and
  ``price_timing`` are ``[optimizer]`` keys (orchestrator ruling, 2026-09-02).

And one entry is not a ``Config`` field at all. ``price_timing`` is popped out
of ``[optimizer]`` before the splat and read by a module-level reader (grep
``NON_FIELD_OPTIMIZER_KEYS``), so its current value cannot come from
``getattr(cfg, ...)``. That is what :attr:`SettingKey.source` exists for:
``"config"`` reads the dataclass, ``"reader"`` imports a dotted path lazily.
Writing is identical either way — the overlay is a TOML file and the write
goes to ``[optimizer] price_timing`` exactly as it would for a field.

An entry whose reader cannot find it is dropped by :func:`live_keys` and named
in the panel's ``unavailable`` list, because a form that is quietly a field
shorter is a setting nobody can find and nobody knows is gone.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from gaffer.config import Config


@dataclass(frozen=True)
class SettingKey:
    field: str
    """The wire key. Also the ``Config`` field where ``source`` is
    ``"config"``."""
    section: str
    """The TOML table the overlay writes it into. ``optimizer``, ``league`` or
    ``scenarios`` — there is no ``solver`` table in this tree."""
    toml_key: str
    """The key inside that table. Not always the field name — ``[scenarios]``
    deliberately shortens its keys (``n``, ``seed``), so this is stated per
    entry rather than assumed."""
    label: str
    kind: str
    """``int`` | ``float`` | ``bool`` | ``floats3`` | ``pool``."""
    lo: float | None
    hi: float | None
    help: str
    source: str = "config"
    """``"config"`` — the value is ``getattr(load_config(), field)``, live iff
    ``field`` is a dataclass field. ``"reader"`` — the value comes from
    :attr:`reader`, because the key never becomes a field."""
    reader: str = ""
    """``"module.path:function"`` for a ``"reader"`` entry, called with no
    arguments. Imported lazily and per call, so a build whose reader is not
    there drops the row rather than failing to import at start-up."""


WHITELIST: tuple[SettingKey, ...] = (
    SettingKey("horizon", "optimizer", "horizon", "Horizon (gameweeks)",
               "int", 1, 8,
               "How many gameweeks the solver plans over."),
    SettingKey("decay", "optimizer", "decay", "Decay per gameweek",
               "float", 0.0, 1.0,
               "How much less a point in week two is worth than one in week "
               "one. 0.0 ignores every week after this one."),
    SettingKey("itb_value", "optimizer", "itb_value",
               "Value of money in the bank", "float", 0.0, 1.0,
               "Points per £1m held back. Priced in points, like the hit "
               "cost."),
    SettingKey("bench_curve", "optimizer", "bench_curve", "Bench weights",
               "floats3", 0.0, 1.0,
               "Three weights, first to third outfield substitute. Reset the "
               "row to fall back to one flat bench weight."),
    SettingKey("lambda_cap", "league", "lambda_cap", "λ tilt cap",
               "float", 0.0, 2.0,
               "The most the league tilt may push the pool. λ itself is "
               "computed each week; this is its ceiling."),
    SettingKey("decision_priors", "scenarios", "decision_priors",
               "Use calibrated θ/λ priors", "bool", None, None,
               "Off falls back to the flat pre-v4c thresholds. The asset "
               "ships with the package and has no path to configure."),
    SettingKey("top_n", "optimizer", "top_n", "Candidate pool per position",
               "pool", 1, 200,
               "How many players per position reach the solver. A smaller "
               "pool solves faster and can exclude a player you own. One key, "
               "read twice: it sets Config.top_n and the pool "
               "`optimizer_top_n()` hands the solver."),
    # Not a Config field: W2 pops it out of [optimizer] before the splat, so
    # `getattr(cfg, "price_timing")` would raise and a fields(Config) liveness
    # check would drop the row. The dotted path is the reader itself, which
    # lives beside the loader in gaffer/config.py rather than under
    # optimize/** — verified, not guessed.
    SettingKey("price_timing", "optimizer", "price_timing",
               "Charge price timing", "bool", None, None,
               "Charges a sell that is scheduled for a later week by the "
               "chance the player drops tonight. Never rewards a rise.",
               source="reader", reader="gaffer.config:price_timing"),
    SettingKey("draw_availability", "scenarios", "draw_availability",
               "Draw availability in the sweep", "bool", None, None,
               "Each scenario draws whether each player is available, so "
               "\"bought in N%\" reflects availability risk."),
    # v13 §2.3 (specs/2026-09-04-gaffer-v13-transfer-ladder-design.md). The
    # appetite. Also editable from the ladder card on the This Week hub,
    # which writes through this same endpoint.
    SettingKey("max_hits", "optimizer", "max_hits", "Max hits per week",
               "int", 0, 15,
               "15 = no cap. The Thursday advice, its sweep, its alternatives "
               "and its chip table all solve under this. The transfer ladder "
               "on the This Week hub edits it too."),
    SettingKey("max_transfers", "optimizer", "max_transfers",
               "Max transfers per week", "int", 0, 15,
               "15 = no cap; 0 = bank (no moves at all). Also edited from "
               "the transfer ladder."),
)

BY_FIELD = {entry.field: entry for entry in WHITELIST}


def _call_reader(entry: SettingKey):
    """A ``"reader"`` entry's current value, or ``KeyError`` if it has none.

    Imported per call rather than at module scope: a settings page that cannot
    be imported is worse than one that is a row shorter.
    """
    module, _, name = entry.reader.partition(":")
    try:
        import importlib

        return getattr(importlib.import_module(module), name)()
    except Exception as exc:  # noqa: BLE001 — an absent reader is a dropped row
        raise KeyError(entry.field) from exc


def current_value(entry: SettingKey, cfg):
    """One entry's value, however it has to be read. ``KeyError`` if absent."""
    if entry.source == "reader":
        return _call_reader(entry)
    if entry.field not in {f.name for f in dataclasses.fields(Config)}:
        raise KeyError(entry.field)
    return getattr(cfg, entry.field)


def live_keys(cfg=None) -> list[str]:
    """The whitelist entries this build can actually read a value for.

    Introspected per call rather than at import, for two reasons: the module is
    imported once per process and the answer must not be cached across a hot
    reload, and a ``"reader"`` entry's module may not be there at all — asking
    at import time would make that a start-up failure instead of a missing row.

    ``cfg`` is the already-loaded config when the caller has one; ``None``
    loads it, and a config that will not load leaves only the ``"reader"``
    entries live, which is the honest answer rather than an empty page.
    """
    if cfg is None:
        try:
            from gaffer.config import load_config

            cfg = load_config()
        except Exception:  # noqa: BLE001 — a read is never worth a 500
            cfg = None
    out = []
    for entry in WHITELIST:
        if entry.source == "config" and cfg is None:
            continue
        try:
            current_value(entry, cfg)
        except KeyError:
            continue
        out.append(entry.field)
    return out
