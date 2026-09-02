from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from gaffer.errors import GafferError

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
    train_seasons: list[str] = field(default_factory=list)
    current_season: str = "2026-27"
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
    # loading. What the solver actually gets is `optimizer_top_n()`, which
    # merges over the shipped default; this carries what the file said.
    top_n: dict[str, int] = field(
        default_factory=lambda: {"GKP": 8, "DEF": 22, "MID": 26, "FWD": 14})
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


def load_config(path: Path | str = "config.toml") -> Config:
    file = Path(path)
    if not file.exists():
        # A fresh clone has no config.toml: it carries an API key, so it is
        # gitignored. Say what to do instead of raising FileNotFoundError,
        # which the web app would have turned into a 500.
        raise GafferError(
            f"no {file} — copy config.example.toml to config.toml and set "
            "fpl.entry_id and fpl.league_id")
    raw = tomllib.loads(file.read_text())
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
    # v12 W2 §3.4 (specs/2026-09-01-gaffer-v12-program-design.md). The
    # program's solver knobs live in [optimizer] and this section is splatted
    # wholesale, so a knob read by a module-level reader has to be lifted out
    # first or it arrives at Config.__init__ as an unexpected keyword. Popped
    # by name, so a *typo* under [optimizer] still raises loudly — and so that
    # W1's top_n, which is a real field, keeps travelling through the splat.
    optimizer = {k: v for k, v in raw.get("optimizer", {}).items()
                 if k not in NON_FIELD_OPTIMIZER_KEYS}
    return Config(
        entry_id=raw["fpl"]["entry_id"],
        league_id=raw["fpl"]["league_id"],
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
        digest_notify=bool(digest.get("notify", True)),
        backup_dir=str(backup.get("dir", "")),
        backup_rsync_target=str(backup.get("rsync_target", "")),
        backup_keep=int(backup.get("keep", 14)),
        web_token=str(web.get("token", "")),
    )


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


def lineup_providers(path: Path | str = "config.toml") -> list[str]:
    """Which predicted-XI providers may speak (v10 §F2a, plan A6).

    A per-source kill, which ``[news] lineups`` cannot be: that switch covers
    a source going silent, and a silent source needs no switch. This one
    covers a source going *wrong* — parsing, resolving, and lying — which the
    pessimistic merge in ``fetch_lineups`` turns into benched starters. ``[]``
    behaves exactly like ``lineups = false``; ``lineups = false``
    short-circuits in ``advise.py`` before this is read, so the two compose in
    the only order that makes sense.

    A module-level reader rather than a :class:`Config` field, which is a
    deviation from plan A6 with a reason the tree supplies: a 49th field would
    break ``len(dataclasses.fields(Config)) == 48`` in
    ``tests/test_v9c_degradation.py`` and ``tests/test_v9d_degradation.py``,
    both of which are protected this cycle. Every behaviour A6 argued for
    survives the move; only the storage does not. It is read at serve time by
    ``fetch_lineups``, the same seam ``serving_config`` exists for, because
    ``advise.py`` is protected and cannot forward it.

    Never raises. A missing file, a missing section and a corrupt TOML all
    give the shipped default, for the reason :func:`serving_config` gives.
    """
    try:
        raw = tomllib.loads(Path(path).read_text())
    except Exception:  # noqa: BLE001 — a serve-time reader never raises
        return list(DEFAULT_LINEUP_PROVIDERS)
    return _providers(raw.get("news", {}).get("lineup_providers"))


@lru_cache(maxsize=1)
def serving_config() -> Config:
    """The config as the *serve-time seams* read it — never raising.

    ``advise.py`` is protected, so v8a's fetcher- and availability-level
    switches cannot arrive as arguments; they are read here instead. Two
    consequences are deliberate. It is cached, because a fetcher must not
    re-read a TOML file per call. And it degrades to the dataclass defaults
    rather than raising, because a clone with no ``config.toml`` still has to
    predict — the loud "copy config.example.toml" error belongs to the CLI's
    own :func:`load_config` call, not to a news source.

    Tests that change ``config.toml`` under a running process call
    ``serving_config.cache_clear()``. So must anything else: the cache lives
    for the life of the process, so editing ``[news]`` while the web app is
    up changes nothing until it is restarted. That is the intended trade —
    a per-call TOML read on a serving path is worse — but it is a trap for
    anyone toggling a flag and watching for an effect.
    """
    try:
        return load_config()
    except Exception:  # noqa: BLE001 — serving never blocks on config
        return Config(entry_id=0, league_id=0)


NON_FIELD_OPTIMIZER_KEYS = ("price_timing",)
"""``[optimizer]`` keys that are **not** :class:`Config` fields.

``load_config`` splats ``[optimizer]`` wholesale, so a key here that nobody
pops is a ``TypeError`` out of ``Config.__init__`` on the next advise run.
``price_timing`` is read by a module-level reader instead — see
:func:`price_timing` for why a field was not available to it.

**One entry, and ``top_n`` is deliberately not the second.** W1 §2.6 ships
``top_n`` as a real ``Config`` field with a ``default_factory``, splatted from
this same section and read through ``optimizer_top_n()``; popping it here
would strip a configured pool size out of the constructor and hand every user
the dataclass default, silently. A key belongs in this tuple only when
``Config`` has no field of that name.

A **named** tuple and not a ``fields(Config)`` filter: a filter would also
swallow ``horizen = 6``, and a silently ignored typo in the horizon is a
season of quietly wrong advice.
"""


def price_timing(path: Path | str = "config.toml") -> bool:
    """``[optimizer] price_timing`` (v12 §3.4).

    Default **on** since the 2026-09-02 W2 gate: the term is a 0.008-point
    tie-breaker and the replay with it live was byte-identical to main
    (pre-registered outcome); set ``false`` to drop it. Live only when the
    price log carries today's reading — the scheduled advise banks one first.

    A module-level reader rather than a :class:`Config` field, for
    :func:`lineup_providers`' reason: another field moves
    ``len(dataclasses.fields(Config))``, which several **protected**
    degradation files pin, and W1 §2.6 has already paid that toll once for
    ``top_n``. Paying it twice in one program for a flag nobody sets is not a
    trade this workstream is entitled to make. See
    :data:`NON_FIELD_OPTIMIZER_KEYS`, which is what stops this key reaching
    ``Config.__init__`` through the ``[optimizer]`` splat — and note that
    ``top_n``, which *is* a field, must not be listed there.

    Never raises. A missing file, a missing section and corrupt TOML all give
    the shipped default: this is read on the solve path, and a solve must not
    die of a config file.
    """
    try:
        raw = tomllib.loads(Path(path).read_text())
    except Exception:  # noqa: BLE001 — a solve-path reader never raises
        return True
    return bool(raw.get("optimizer", {}).get("price_timing", True))


def xg_per_shot(path: Path | str = "config.toml") -> bool:
    """``[model] xg_per_shot`` (v12 §3.5).

    Default **off**. The 2026-09-02 §3.5 RMSE-bucket arm said keep (hauler
    5.207 → 5.203, inside the 0.019 spread) but the season replay with the head
    on scored [1874, 1834, 1799] against main's [1854, 1875, 1862] — −28 on the
    mean, beyond the control spread, with the seed spread tripled (75 vs 21).
    The outcome measure wins; set ``true`` to fit the head anyway.

    A module-level reader for :func:`price_timing`'s reason. Never raises: a
    training run must not die of a config file, and the default is the
    shipped behaviour.

    ``[model]`` rather than ``[optimizer]``, and that section is *not*
    splatted into :class:`Config`, so this key needs no entry in
    :data:`NON_FIELD_OPTIMIZER_KEYS`.
    """
    try:
        raw = tomllib.loads(Path(path).read_text())
    except Exception:  # noqa: BLE001 — a training reader never raises
        return False
    return bool(raw.get("model", {}).get("xg_per_shot", False))


def optimizer_top_n(path: Path | str = "config.toml") -> dict[str, int]:
    """``[optimizer] top_n`` merged over the shipped default.

    Cached, for the reason :func:`serving_config` is: ``build_pool`` calls this
    on every solve and a per-solve TOML read on the serving path is the cost
    this reader was added to avoid. Same trap, same remedy — a test (or
    anything else) that edits ``config.toml`` under a running process calls
    ``optimizer_top_n.cache_clear()``. The returned dict is a fresh copy each
    call so a caller that mutates its pool sizes cannot poison the cache.

    v12 W1 §2.6. Never raises: a missing file, a missing section, a corrupt
    TOML, a typo'd position and a non-numeric value all degrade to the shipped
    value for that position. A config error that silently shrank the solver's
    candidate pool would change the advice without saying so, and the symptom
    — a plan that never mentions a player — looks nothing like its cause.

    Merged rather than replaced so a user tuning one position does not have to
    restate the other three, and unknown keys are dropped so a typo cannot
    contribute an empty position to a pool that then reads as intentional.

    Separate from ``Config.top_n``, which comes through ``[optimizer]``'s
    splat and carries exactly what the file said. That one is what the
    Settings tab edits; this one is what the solver gets. ``build_pool`` has
    no ``Config`` in hand and cannot be given one without an ``optimize/**``
    signature change, which is the other half of why this reader exists.
    """
    # Keyed on the absolute path, so the default relative "config.toml" is a
    # different cache entry per working directory rather than one entry that
    # follows a chdir into somebody else's tree.
    return dict(_optimizer_top_n(str(Path(path).resolve())))


@lru_cache(maxsize=8)
def _optimizer_top_n(path: str) -> dict[str, int]:
    """:func:`optimizer_top_n`'s cache. Never call this one directly — it hands
    back the cached dict itself, and a mutation of it would be permanent."""
    from gaffer.optimize.milp import DEFAULT_TOP_N

    out = dict(DEFAULT_TOP_N)
    try:
        raw = tomllib.loads(Path(path).read_text())
        table = raw.get("optimizer", {}).get("top_n", {})
    except Exception:  # noqa: BLE001 — serve-time readers never raise
        return out
    if not isinstance(table, dict):
        return out
    for pos in out:
        value = table.get(pos)
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        if value > 0:
            out[pos] = int(value)
    return out


# The cache lives on the private reader, but callers should not have to know
# that: `optimizer_top_n.cache_clear()` is what a test reaches for, by analogy
# with `serving_config.cache_clear()`, so it is what it gets.
optimizer_top_n.cache_clear = _optimizer_top_n.cache_clear
optimizer_top_n.cache_info = _optimizer_top_n.cache_info
