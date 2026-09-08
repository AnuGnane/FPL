from __future__ import annotations

import dataclasses
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import tomli_w

from gaffer.errors import GafferError
from gaffer.io import atomic_write

LLM_NO_TOOLS = ("Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,"
                "Task,NotebookEdit")
DEFAULT_LINEUP_PROVIDERS = ("ffs", "rotowire")
"""Predicted-XI sources, in the order they are fetched (v10 §F2a).

Order is cosmetic — the merge is by pessimism and not by precedence — but a
stable order keeps the printed coverage lines readable week to week.
"""

DEFAULT_LLM_COMMAND = ('claude -p --output-format json '
                       f'--disallowedTools "{LLM_NO_TOOLS}"')
"""The classifier's default posture: a language model with no hands.

Every text it reads is scraped web content — a quote off premierinjuries,
the bootstrap's ``news`` string — and prompt injection in a scraped field is
a solved attack, not a hypothetical. The model's job here is to return one
word from a fixed vocabulary, so it needs no tool at all, and the cheapest
way to be sure a sentence beginning "ignore your instructions and" cannot do
anything is to leave nothing for it to do.

It is a deny list, and a deny list has one honest weakness: a tool the CLI
ships after this line was written is not on it. The list is therefore a
floor rather than a proof, and the second half of the defence is that the
prompt asks for a JSON array and :func:`~gaffer.data.news.classifier
._extract_rows` drops anything that is not one.
"""


NO_CAP = 15
"""``[optimizer] max_hits`` / ``max_transfers`` value meaning "no cap".

The tree's idiom for unlimited — ``free_transfers=15`` is how every
from-scratch solve says it — so the two keys share it rather than inventing
a sentinel. ``max_transfers = 0`` is a real cap: bank, no moves at all.
"""

DEFAULT_TOP_N = {"GKP": 8, "DEF": 22, "MID": 26, "FWD": 14}
"""The candidate pool per position the solver has used since the first MILP
(v12 W1 §2.6). Here rather than in ``optimize/milp.py`` since v17e §2.1, so
that ``Config.solver_top_n`` can merge over it without ``config`` importing
the optimizer; ``milp`` imports it from here."""

BOUNDS: dict[str, tuple[float, float]] = {
    "horizon": (1, 8), "decay": (0.0, 1.0), "itb_value": (0.0, 1.0),
    "bench_curve": (0.0, 1.0), "lambda_cap": (0.0, 2.0), "top_n": (1, 200),
    "max_hits": (0, NO_CAP), "max_transfers": (0, NO_CAP),
    "hit_bar": (0.5, 0.95), "focus": (1, 99_999_999),
}
"""The one statement of every numeric setting's range (v17e §2.3). The
settings registry reads its ``lo``/``hi`` from here and the router
enforces all of it on a write; the loader enforces the three it always
did (the two caps and the bar). ``hit_bar``: below 0.5 a step up the
ladder would be taken on a coin toss; above 0.95 no step ever passes
(v16 §3.2). ``focus``'s ceiling is a numeric bound because the range
check needs one."""

HIT_BAR_LO, HIT_BAR_HI = BOUNDS["hit_bar"]

_SECTION = {"max_hits": "optimizer", "max_transfers": "optimizer",
            "hit_bar": "optimizer"}
"""The TOML table of the fields the loader checks, for the sentence. A
router that knows the section passes it instead."""


def out_of_range(field: str, value, section: str | None = None) -> str:
    """The one sentence for a value outside ``BOUNDS[field]`` (v17e §2.3):
    ``[optimizer] hit_bar = 1.2 — must be a number between 0.5 and 0.95``,
    with ``(15 means no cap)`` appended for the two caps. The loader raises
    it as :class:`GafferError`; the settings router returns it as the
    422's ``error``. "whole number" when both bounds are integers."""
    lo, hi = BOUNDS[field]
    section = section or _SECTION.get(field, "optimizer")
    kind = ("a whole number" if isinstance(lo, int) and isinstance(hi, int)
            else "a number")
    tail = f" ({NO_CAP} means no cap)" if field in ("max_hits",
                                                    "max_transfers") else ""
    return (f"[{section}] {field} = {value!r} — must be {kind} between "
            f"{lo} and {hi}{tail}")


@dataclass
class Config:
    entry_id: int
    league_id: int
    horizon: int = 3
    decay: float = 0.85
    vice_weight: float = 0.1
    bench_weight: float = 0.10
    ft_value: float = 1.5
    itb_value: float = 0.05
    hit_cost: int = 4
    # v12 W3 §4.3 (specs/2026-09-01-gaffer-v12-program-design.md). How far
    # behind the recommended plan an alternative may sit and still be worth
    # showing, in *objective* points — the frame the plans were solved in, not
    # raw EP. 0 turns the search off without spending a solve.
    #
    # An [optimizer] key, not a [solver] one: the spec names a section this
    # tree does not have, and the program-wide ruling is that solver knobs live
    # in [optimizer] under their own names.
    alt_plan_max_gap: float = 2.0
    # v13 §2.1 (specs/2026-09-04-gaffer-v13-transfer-ladder-design.md). The
    # manager's appetite, not a model parameter: the most hits and the most
    # transfers the solver may take in any one non-wildcard gameweek. The
    # Thursday advice, its scenario sweep, its alternative plans and its chip
    # table all solve under them (advise.py builds the one SolveInput they
    # inherit). NO_CAP means uncapped; max_transfers = 0 means bank.
    max_hits: int = 2
    max_transfers: int = NO_CAP
    # v16 §3.2 (specs/2026-09-06-gaffer-v16-restraint-brief-design.md). The
    # share of the ladder's shared draws in which a rung must beat the rung
    # below it before the served advice steps up to it. A policy knob, not a
    # model parameter: the ladder's probabilities decide, this says how sure
    # they have to be.
    hit_bar: float = 0.60
    train_seasons: list[str] = field(default_factory=list)
    current_season: str = "2026-27"
    # v17e §2.1. ``[model] xg_per_shot``; read key by key because [model] is
    # not a splatted section. Default off: the 2026-09-02 §3.5 season
    # replay with the head on lost 28 points on the mean.
    xg_per_shot: bool = False
    odds_api_key: str = ""
    player_props: bool = True
    ags_blend_weight: float = 0.5
    understat_enabled: bool = True
    # --- v4c decision layer ------------------------------------------------
    # Every one of these defaults to the pre-v4c behaviour. n = 0 means "solve
    # once, deterministically"; the two objective knobs are neutral elements.
    scenarios_n: int = 0
    scenarios_seed: int = 20260825
    transfer_threshold: float = 0.60
    irreversible_threshold: float = 0.75
    decision_priors: bool = True
    # v12 W3 §4.4 (specs/2026-09-01-gaffer-v12-program-design.md). Per
    # scenario, per player-gameweek, a Bernoulli on p_play: the sweep asks
    # "did he turn out" as an outcome rather than only as a variance.
    #
    # Default **on** since the 2026-09-02 §4.4 support gate: with the draw on,
    # captain support on the GW3 board fell 60.0 → 52.5 (drop 7.5 ≤ 10, 40/40
    # scenarios both arms). The season replay cannot see this lever (the
    # harness never passes p_play), so the live board is where it shows; set
    # false to sweep on expected minutes only.
    draw_availability: bool = True
    ft_use_penalty: float = 0.0
    bench_curve: list[float] | None = None
    # v12 W1 §2.6. Named for its TOML key rather than its subject, because
    # [optimizer] is splatted and the key *is* the keyword argument. The
    # default_factory is load-bearing rather than tidy: without it every
    # existing config.toml in the world, none of which has this key, stops
    # loading. What the solver actually gets is `solver_top_n()` (v17e §2.1),
    # which merges over the shipped default; this carries what the file said.
    top_n: dict[str, int] = field(
        default_factory=lambda: dict(DEFAULT_TOP_N))
    # v17e §2.1. Was a module-level reader popped out of [optimizer] before
    # the splat (v12 W2); a field now, splatted like every other key here.
    # Default on since the 2026-09-02 W2 gate: the term is a 0.008-point
    # tie-breaker and the replay with it live was byte-identical to main.
    price_timing: bool = True
    # --- v4d league mode ---------------------------------------------------
    # The z-dial's constants. Every default is the pinned value from the v4d
    # design, and league mode itself stays gated by league_id — there is no
    # new master switch. tier_eo is live-tracker display only and never
    # reaches the optimizer.
    z_scale: float = 1.5
    lambda_cap: float = 0.5
    sigma_floor: float = 8.0
    sigma_cap: float = 30.0
    sigma_min_weeks: int = 6
    z_deadband: float = 0.25
    tier_eo: bool = True
    tier_sample: int = 300
    # v8c. field_scrape schedules the tier sample the live tracker already
    # takes lazily; field_sample defaults to tier_sample rather than to a
    # number of its own, because one scrape serves both readers and two
    # sample sizes for one sample is a bug waiting for a Saturday.
    field_scrape: bool = True
    field_sample: int = 300
    sim_n: int = 2000
    rival_drift: float = 0.5
    # --- v15 leagues (specs/2026-09-06-gaffer-v15-leagues-design.md) ------
    # The manual stance: "auto" is the dial, the other three pin λ at the
    # cap (chase +, defend -) or at exactly 0.0 (neutral). Read from [league]
    # stance, which the League page writes through the settings overlay. The
    # focus league itself is not a new field: [league] focus, when set, is
    # resolved by load_config into league_id, so every reader of league_id
    # sees the focus without knowing the word.
    stance: str = "auto"
    # --- v5 news layer -----------------------------------------------------
    # Defaults are shipped-behaviour-ON, individually switchable. Every source
    # degrades to the official-flags path by itself (spec §7), so these exist
    # to turn off a *working* source, not to survive a broken one.
    # The Transfermarkt return curves are a committed asset rather than a
    # runtime source, so they carry no flag here.
    news_enabled: bool = True
    news_injuries: bool = True
    news_lineups: bool = True
    news_cache_hours: int = 6
    news_min_coverage: float = 0.5
    # --- v8a news layer ----------------------------------------------------
    # Two serve-time upgrades and one classifier, all readable by the news
    # seams themselves because ``advise`` is protected and cannot learn to
    # pass them. Defaults are the pre-v8a behaviour with one exception: the
    # notable-absence damp is ON, because it can only ever lower a number and
    # the case it catches — a regular quietly left out of the predicted XI —
    # is the one the layer exists for.
    news_llm_classifier: bool = False
    news_llm_shadow: bool = True
    news_llm_command: str = DEFAULT_LLM_COMMAND
    news_llm_timeout_s: int = 300
    news_lineup_absence: bool = True
    news_lineup_absence_damp: float = 0.75
    news_lineup_start_floor: float = 0.0
    # v8e. The user's own pins, applied last in the availability pass. On by
    # default: an empty store is a no-op, and a switch that has to be found
    # before a feature works is a feature nobody finds.
    news_overrides: bool = True
    # v17e §2.1 (was v10 §F2a's reader). Which predicted-XI providers may
    # speak; ``[]`` is the per-source kill switch. Cleaned by the loader
    # with ``_providers`` so a typo is dropped with a line, never raised on.
    news_lineup_providers: list[str] = field(
        default_factory=lambda: list(DEFAULT_LINEUP_PROVIDERS))
    # v8f. The only switch this cycle adds. On by default, for the reason the
    # override switch is: a notification nobody has to enable is the whole
    # feature, and a switch that must be found before the tool works is a
    # feature nobody finds. Off is for a machine that is not the user's own —
    # a server, a CI box, a shared laptop — where a launchd job firing
    # Notification Centre would be somebody else's surprise.
    digest_notify: bool = True
    # --- v12 W1 §2.1 backup ------------------------------------------------
    # Read key-by-key like [odds] and [league], not splatted: the TOML keys
    # are shorter than the field names (dir, rsync_target, keep) so the
    # section reads as prose. An empty `backup_dir` means ~/gaffer-backups —
    # `backup.backup_dir` resolves it, so the default lives in one place
    # rather than being spelled here and there.
    backup_dir: str = ""
    backup_rsync_target: str = ""
    backup_keep: int = 14
    # --- v12 W1 §2.8 LAN write protection -----------------------------------
    # Only ever consulted by `gaffer ui --lan`. Empty means "generate one at
    # startup and print it once" — never written back, because a tool that
    # edits the file holding your API key is a surprise nobody asked for.
    web_token: str = ""

    def solver_top_n(self) -> dict[str, int]:
        """``top_n`` merged over :data:`DEFAULT_TOP_N` with v12 W1's
        lenience: a position that is missing, non-integer, boolean or
        ≤ 0 keeps the shipped value; an unknown position is dropped; a
        value that is not a table at all is the default whole. A fresh dict
        per call, so a caller that mutates its pool cannot poison anyone
        else's (v17e §2.1). This is what the solver gets; ``top_n`` is
        what the file said."""
        out = dict(DEFAULT_TOP_N)
        table = self.top_n
        if not isinstance(table, dict):
            return out
        for pos in out:
            value = table.get(pos)
            if isinstance(value, bool) or not isinstance(value, int):
                continue
            if value > 0:
                out[pos] = int(value)
        return out


LOCAL_OVERLAY = "config.local.toml"
"""The overlay the Settings tab owns (v12 W5 §6.2).

Read *after* ``config.toml`` and merged over it key by key. It exists so the
UI has a file it may write without ever touching ``config.toml``, which
carries the odds API key and is gitignored for that reason. Spec §8 forbids a
UI that edits ``config.toml``; this is the file it edits instead.
"""

BASE_FILE = "config.toml"


def base_exists() -> bool:
    """Whether the working directory has a ``config.toml`` at all — the
    state a cold clone is in (v17e §2.8)."""
    return Path(BASE_FILE).exists()


def _read_toml(path: Path) -> tuple[dict, str | None]:
    """A TOML file as a dict, plus why it could not be read."""
    if not path.exists():
        return {}, None
    try:
        return tomllib.loads(path.read_text()), None
    except Exception as exc:  # noqa: BLE001 — a read is never worth a 500
        return {}, f"{path.name} is not readable TOML ({exc}) — ignored"


def read_overlay() -> tuple[dict, str | None]:
    """``config.local.toml`` parsed, or ``({}, why)`` when it is unreadable;
    ``({}, None)`` when absent (v17e §2.8). The settings router's read."""
    return _read_toml(Path(LOCAL_OVERLAY))


def write_overlay(raw: dict) -> None:
    """The overlay, atomically, with the header comment (v12 W5 §6.2;
    moved here in v17e §2.8 so no module but this one writes the file).
    Through ``gaffer.io.atomic_write`` rather than another copy of the
    pid-temp + ``os.replace`` idiom; ``tomli_w.dumps`` rather than ``dump``
    because the helper owns the file handle and the comment goes first."""
    body = ("# Written by the gaffer web UI (v12 W5 §6.2).\n"
            "# Merged over config.toml, key by key. Safe to hand-edit; a key\n"
            "# that is not a config field is ignored with a printed line.\n\n"
            + tomli_w.dumps(raw))
    atomic_write(Path(LOCAL_OVERLAY), body)


def _table(raw: dict, section: str) -> dict:
    """One section of a parsed file, or ``{}`` if it is not a table:
    ``optimizer = 5`` parses, and a membership test on an ``int`` was a 500
    on the tab whose job is to say the overlay is wrong."""
    value = raw.get(section)
    return value if isinstance(value, dict) else {}


def value_source(section: str, key: str) -> str:
    """Which file the in-force value of ``[section] key`` comes from:
    ``"local"`` (the overlay), ``"base"`` (``config.toml``) or
    ``"default"`` (the dataclass). Three different facts: only a local
    value can be reset (v17e §2.8)."""
    local, _ = read_overlay()
    if key in _table(local, section):
        return "local"
    base, _ = _read_toml(Path(BASE_FILE))
    if key in _table(base, section):
        return "base"
    return "default"


SPLATTED_SECTIONS = ("optimizer", "data")
"""Sections :func:`load_config` splats straight into ``Config(...)``.

A key here that is not a dataclass field is a ``TypeError``, and
:func:`config_in_force` catches that by falling all the way back to
``Config(entry_id=0, league_id=0)`` — discarding the user's real config
without a word. So the overlay drops unknown keys in these sections rather
than letting one typo silently re-point the news layer at entry 0. Every other
section is read key-by-key and ignores what it does not recognise already.
"""


def _overlay(raw: dict, base: Path) -> dict:
    """``config.toml``'s tables with ``config.local.toml``'s merged over them.

    A sibling of ``base``, never of the working directory: every test in this
    tree passes a ``tmp_path`` config, and a relative path would read the
    developer's own overlay into the fixture.

    Merged one level *inside* a section as well as across it, wherever both
    sides of a key are tables. ``[optimizer] top_n`` is the case that forced
    it: it is a table of four positions, and a whole-value overwrite would let
    an overlay saying ``top_n = {GKP = 3}`` silently drop the three pool sizes
    ``config.toml`` had set. The Settings tab always writes all four, but a
    hand-edited overlay is exactly the file somebody writes one line into. One
    level and no deeper: nothing in this config nests further, and a general
    deep merge would be a rule no reader could predict from the file.

    A *scalar* at the top level is dropped rather than merged, with the same
    printed line an unknown key gets, unless the base holds a scalar at that
    key too — only scalar-over-scalar is a merge. ``optimizer = 5`` used to
    replace the whole ``[optimizer]`` table and take ``load_config`` down with
    it, which :func:`config_in_force` turns into
    ``Config(entry_id=0, league_id=0)`` — every real setting the manager has,
    discarded over one line. The rule does not ask whether the base declares
    the section, because ``load_config`` does ``raw.get(section, {})`` per
    table and a scalar there would raise ``AttributeError`` on the solve path
    — the one place that must not.

    Never raises. A missing overlay is the normal case; an unparseable one is
    ignored with a printed line, because one bad write from the Settings tab
    must not stop every job on the machine. The line is the only signal there
    is, so it names the file and says the word "ignored".
    ``routers/settings.py`` builds its own sentence for the same condition and
    does not read this one; what keeps the two in step is a test asserting
    both name the file and both say "ignored".
    """
    local = Path(base).parent / LOCAL_OVERLAY
    if not local.exists():
        return raw
    try:
        extra = tomllib.loads(local.read_text())
    except Exception as exc:  # noqa: BLE001 — a bad overlay is not a crash
        print(f"config: {local} is not readable TOML ({exc}) — ignored, "
              f"using {base} alone")
        return raw
    allowed = {f.name for f in dataclasses.fields(Config)}
    out = dict(raw)
    for section, values in extra.items():
        if not isinstance(values, dict):
            if section in out and not isinstance(out[section], dict):
                # Scalar over scalar: the base already says this key is a bare
                # value, so the overlay saying so too is an ordinary override.
                out[section] = values
                continue
            # A scalar where a section belongs. `optimizer = 5` from a
            # hand-edit replaced the whole `[optimizer]` table, and
            # `load_config`'s `**optimizer` splat then raised `AttributeError:
            # 'int' object has no attribute 'items'` — which `config_in_force`
            # catches by handing back `Config(entry_id=0, league_id=0)`: the
            # manager's entire real config gone over one bad line in a file the
            # UI writes. Dropped with the key guard's own sentence below,
            # because it is the key guard's own fact — the overlay said
            # something the config cannot mean. Dropped whether or not the base
            # declares the section: `load_config` does `raw.get(section, {})`
            # per table, so letting `optimizer = 5` through against a base with
            # no `[optimizer]` would raise on the solve path instead.
            print(f"config: {local} sets [{section}] to something that is not "
                  f"a table, which is not a config section — ignored")
            continue
        if not isinstance(out.get(section), (dict, type(None))):
            out[section] = values
            continue
        merged = dict(out.get(section) or {})
        for key, value in values.items():
            if section in SPLATTED_SECTIONS and key not in allowed:
                print(f"config: {local} sets [{section}] {key}, which is not "
                      f"a config field — ignored")
                continue
            prior = merged.get(key)
            # One level in. A table over a table merges key by key, so a
            # partial `top_n` keeps the positions it did not mention; anything
            # else replaces, which is what a scalar or a list has to do.
            merged[key] = ({**prior, **value}
                           if isinstance(prior, dict) and isinstance(value,
                                                                     dict)
                           else value)
        out[section] = merged
    return out


def _raw_with_overlay(path: Path | str) -> dict:
    """``config.toml`` parsed, with ``config.local.toml`` merged over it.

    The one place the merge happens, and since v17e §2.1 ``load_config`` is
    its only caller: the keys that used to need their own readers are fields.

    Raises whatever reading or parsing ``path`` raises — ``load_config``
    phrases the missing-file error and :func:`config_in_force` degrades.
    """
    file = Path(path)
    return _overlay(tomllib.loads(file.read_text()), file)


def _providers(raw) -> list[str]:
    """A ``[news] lineup_providers`` value -> a clean list of known names.

    A typo in a TOML file must not take advice down, so an unknown name is
    dropped with a line rather than raised on, and a value that is not a list
    at all falls back to the default. An explicit empty list is honoured —
    that is the kill switch, not a mistake.
    """
    if raw is None:
        return list(DEFAULT_LINEUP_PROVIDERS)
    if not isinstance(raw, (list, tuple)):
        print(f"config: [news] lineup_providers is not a list ({raw!r}) — "
              f"using {list(DEFAULT_LINEUP_PROVIDERS)}")
        return list(DEFAULT_LINEUP_PROVIDERS)
    out = []
    for name in raw:
        key = str(name).strip().casefold()
        if key in DEFAULT_LINEUP_PROVIDERS:
            out.append(key)
        elif key:
            print(f"config: unknown predicted-XI provider {key!r} — ignored")
    return out


def _check_caps(cfg: "Config") -> None:
    """v13 §2.1: both caps are whole numbers in ``0..NO_CAP``, refused by
    name. Checked here rather than in ``__post_init__`` so a ``Config`` built
    in a test with a deliberate bad value can still exist; the file is where
    a wrong number comes from."""
    for key in ("max_hits", "max_transfers"):
        value = getattr(cfg, key)
        lo, hi = BOUNDS[key]
        if (isinstance(value, bool) or not isinstance(value, int)
                or not lo <= value <= hi):
            raise GafferError(out_of_range(key, value))


def _check_stance(cfg: "Config") -> None:
    """v15 §3.2: the stance is one of four words, refused by name."""
    from gaffer.league_mode import STANCES

    if cfg.stance not in STANCES:
        raise GafferError(
            f"[league] stance = {cfg.stance!r} — must be one of "
            f"{', '.join(STANCES)}")


def _check_hit_bar(cfg: "Config") -> None:
    """v16 §3.2: a real number inside ``BOUNDS["hit_bar"]``, refused by
    name, like the caps."""
    value = cfg.hit_bar
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not HIT_BAR_LO <= float(value) <= HIT_BAR_HI):
        raise GafferError(out_of_range("hit_bar", value))


def load_config(path: Path | str = "config.toml") -> Config:
    file = Path(path)
    if not file.exists():
        # A fresh clone has no config.toml: it carries an API key, so it is
        # gitignored. Say what to do instead of raising FileNotFoundError,
        # which the web app would have turned into a 500.
        raise GafferError(
            f"no {file} — copy config.example.toml to config.toml and set "
            "fpl.entry_id and fpl.league_id")
    raw = _raw_with_overlay(file)
    odds = raw.get("odds", {})
    # [scenarios] is optional and its TOML keys are deliberately shorter than
    # the field names (n, seed), so it is read key-by-key like [odds] rather
    # than splatted. [optimizer] keeps splatting, so ft_use_penalty and
    # bench_curve need no line here.
    scen = raw.get("scenarios", {})
    league = raw.get("league", {})
    news = raw.get("news", {})
    digest = raw.get("digest", {})
    backup = raw.get("backup", {})
    web = raw.get("web", {})
    # v17e §2.1: every [optimizer] key is a field now, price_timing
    # included, so the section splats whole and a typo is still a TypeError.
    optimizer = dict(raw.get("optimizer", {}))
    cfg = Config(
        entry_id=raw["fpl"]["entry_id"],
        # v15 §3.1: the overlay's [league] focus wins over fpl.league_id when
        # it is set and non-zero. fpl.league_id itself is never rewritten.
        league_id=int(league.get("focus") or 0) or raw["fpl"]["league_id"],
        **optimizer,
        **raw.get("data", {}),
        # Read explicitly rather than splatted: [odds] is optional and its
        # TOML keys do not all match the dataclass field names. Both new
        # switches default on and degrade by themselves when the data or the
        # key is missing, so nobody has to edit config.toml to keep the old
        # behaviour.
        odds_api_key=odds.get("api_key", ""),
        player_props=bool(odds.get("player_props", True)),
        ags_blend_weight=float(odds.get("ags_blend_weight", 0.5)),
        understat_enabled=bool(
            raw.get("understat", {}).get("enabled", True)),
        scenarios_n=int(scen.get("n", 0)),
        scenarios_seed=int(scen.get("seed", 20260825)),
        transfer_threshold=float(scen.get("transfer_threshold", 0.60)),
        irreversible_threshold=float(
            scen.get("irreversible_threshold", 0.75)),
        decision_priors=bool(scen.get("decision_priors", True)),
        # v12 W3 §4.4: [scenarios] is read key-by-key rather than splatted, so
        # this line is required, and its default must match the dataclass's or
        # the two disagree about a fresh clone. On since the 2026-09-02 support
        # gate — see the field for the numbers.
        draw_availability=bool(scen.get("draw_availability", True)),
        z_scale=float(league.get("z_scale", 1.5)),
        lambda_cap=float(league.get("lambda_cap", 0.5)),
        sigma_floor=float(league.get("sigma_floor", 8.0)),
        sigma_cap=float(league.get("sigma_cap", 30.0)),
        sigma_min_weeks=int(league.get("sigma_min_weeks", 6)),
        z_deadband=float(league.get("z_deadband", 0.25)),
        tier_eo=bool(league.get("tier_eo", True)),
        tier_sample=int(league.get("tier_sample", 300)),
        field_scrape=bool(league.get("field_scrape", True)),
        field_sample=int(league.get("field_sample",
                                    league.get("tier_sample", 300))),
        sim_n=int(league.get("sim_n", 2000)),
        rival_drift=float(league.get("rival_drift", 0.5)),
        stance=str(league.get("stance", "auto")),
        # Read key-by-key like [odds] and [league]: the TOML keys are
        # deliberately shorter than the dataclass fields (enabled, injuries)
        # so the section reads as prose in config.toml.
        news_enabled=bool(news.get("enabled", True)),
        news_injuries=bool(news.get("injuries", True)),
        news_lineups=bool(news.get("lineups", True)),
        news_cache_hours=int(news.get("cache_hours", 6)),
        news_min_coverage=float(news.get("min_coverage", 0.5)),
        news_llm_classifier=bool(news.get("llm_classifier", False)),
        news_llm_shadow=bool(news.get("llm_shadow", True)),
        news_llm_command=str(news.get("llm_command", DEFAULT_LLM_COMMAND)),
        news_llm_timeout_s=int(news.get("llm_timeout_s", 300)),
        news_lineup_absence=bool(news.get("lineup_absence", True)),
        news_lineup_absence_damp=float(news.get("lineup_absence_damp", 0.75)),
        news_lineup_start_floor=float(news.get("lineup_start_floor", 0.0)),
        news_overrides=bool(news.get("overrides", True)),
        news_lineup_providers=_providers(news.get("lineup_providers")),
        xg_per_shot=bool(raw.get("model", {}).get("xg_per_shot", False)),
        digest_notify=bool(digest.get("notify", True)),
        backup_dir=str(backup.get("dir", "")),
        backup_rsync_target=str(backup.get("rsync_target", "")),
        backup_keep=int(backup.get("keep", 14)),
        web_token=str(web.get("token", "")),
    )
    _check_caps(cfg)
    _check_stance(cfg)
    _check_hit_bar(cfg)
    return cfg


@lru_cache(maxsize=1)
def config_in_force() -> Config:
    """The config in force: the working directory's ``config.toml`` with
    ``config.local.toml`` merged over it, cached for the life of the
    process, never raising (v17e §2.2).

    The one read for everything that is not a person at a terminal — a
    fetcher, the solver's pool, the ladder's bar, a router. Cached because a
    fetcher must not re-read a TOML file per call; degrading to the
    dataclass defaults because a clone with no ``config.toml`` still has to
    predict (the loud "copy config.example.toml" error belongs to the CLI's
    own :func:`load_config` call). :func:`invalidate` is the one clearing,
    and the two places that change or re-read the file under a running
    process — the settings router's save and the health poll — call it.
    """
    try:
        return load_config()
    except Exception:  # noqa: BLE001 — serving never blocks on config
        return Config(entry_id=0, league_id=0)


def invalidate() -> None:
    """Drop every cache keyed on the config file (v17e §2.2): the view, and
    the price-fall table that reads its switch through the view. Tests
    that write a ``config.toml`` under a running process call this; so
    does anything else that edits the file."""
    config_in_force.cache_clear()
    from gaffer.price_timing import owned_price_falls  # circular at import

    owned_price_falls.cache_clear()


def serving_config() -> Config:
    """Deleted in v17e Task 3; :func:`config_in_force` is the read."""
    return config_in_force()


# The view's own cache handle and not :func:`invalidate`, so the wrapper is
# exactly what it was until Task 3 deletes it: the two callers that also want
# the price-fall table dropped still spend their own line for it, and a test
# counting those clears counts the same number it always did.
serving_config.cache_clear = config_in_force.cache_clear
serving_config.cache_info = config_in_force.cache_info


def focus_league() -> int:
    """v15 §4.2 (plan R7): the effective focus league id, for the settings
    row's reader. ``[league] focus`` over ``fpl.league_id``, exactly as
    :func:`load_config` resolves ``Config.league_id``, read through the
    view so a cold clone reads 0 by the same path as everything else."""
    return int(config_in_force().league_id)


def price_timing(path: Path | str = "config.toml") -> bool:
    """Deleted in v17e Task 3; ``config_in_force().price_timing`` is the read."""
    try:
        return bool(load_config(path).price_timing)
    except Exception:  # noqa: BLE001
        return True


def xg_per_shot(path: Path | str = "config.toml") -> bool:
    """Deleted in v17e Task 3; ``config_in_force().xg_per_shot`` is the read."""
    try:
        return bool(load_config(path).xg_per_shot)
    except Exception:  # noqa: BLE001
        return False


def lineup_providers(path: Path | str = "config.toml") -> list[str]:
    """Deleted in v17e Task 3; the field is ``news_lineup_providers``."""
    try:
        return list(load_config(path).news_lineup_providers)
    except Exception:  # noqa: BLE001
        return list(DEFAULT_LINEUP_PROVIDERS)


def optimizer_top_n(path: Path | str = "config.toml") -> dict[str, int]:
    """Deleted in v17e Task 3; ``config_in_force().solver_top_n()`` is the read."""
    try:
        return load_config(path).solver_top_n()
    except Exception:  # noqa: BLE001
        return dict(DEFAULT_TOP_N)


optimizer_top_n.cache_clear = lambda: None
