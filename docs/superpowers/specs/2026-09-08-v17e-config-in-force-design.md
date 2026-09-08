# v17e — the config in force, one interface

Sub-cycle five of the deepening programme
(`plans/2026-09-07-v17-deepening-programme.md` §3, review card `#c5` of
`research/2026-09-07-architecture-review.html`). Branch
`v17e-config-in-force` off `main` at `f28fa20` (v17d's docs commit over the
merge `c6b049f`).

## 0. Why

Which value of a knob is in force depends today on which of seven readers a
module happened to call. `load_config(path)` parses loudly (41 sites);
`serving_config()` is the cached, never-raising view (18 sites); and four
private readers — `price_timing`, `xg_per_shot`, `lineup_providers`,
`optimizer_top_n` — open `config.toml` and the overlay themselves because
the keys they serve are not `Config` fields or are read where no `Config` is
in hand. Three process-lifetime caches sit behind them (`serving_config`,
`_optimizer_top_n`, `owned_price_falls`) and two modules clear them in two
different sets (`routers/settings.py` clears three, `routers/meta.py` two),
plus 25 test files. The settings router reads both TOML files itself to say
where a value came from. A bound is stated three times (`config.py`'s
constants and checker sentence, `settings_keys.py`'s literals, the router's
second refusal sentence). And the ladder card hard-codes `NO_CAP = 15`, nine
hit-bar stops and a `?? 0.6` default beside the settings registry that the
Settings tab uses correctly.

The deletion test: after this cycle, `serving_config`, the four readers,
`NON_FIELD_OPTIMIZER_KEYS`, `_raw_with_overlay`'s four extra callers, the
router's file reads, and the card's three constants are gone, and nothing
outside `config.py` opens either TOML file.

## 1. Gate, stated before anything runs (CONVENTIONS §2, §7, §10)

The orchestrator runs it on the branch; implementers never do. Four parts,
all required.

1. **Golden board.** `.venv/bin/pytest -q tests/test_golden_board.py
   tests/test_pipeline.py` passes with `tests/data/golden_board/` untouched
   at `77d1d59`'s bytes (`git diff --stat main -- tests/data/golden_board`
   prints nothing): 44 passed, none skipped. No key may differ. The
   header's `config` echo is compared on the keys it recorded (§2.7), and
   the three new fields' defaults must equal what the recorded
   `config.toml` says (`price_timing = true`; the other two absent, so
   defaults).
2. **The rail** `tests/test_v17e_config.py` passes: (a) the grep — no file
   under `src/gaffer` other than `config.py` contains `tomllib`,
   `config.toml` or `config.local.toml` as code (docstrings and comments
   excluded by stripping them before the search; `optimize/chip_policy.py`
   reads `data/chip_scenarios.toml` through `tomllib` and is the one named
   exemption, listed in the test with its path); (b) every `WHITELIST`
   entry with a numeric bound has `(lo, hi) == BOUNDS[field]`; (c) every
   `WHITELIST` entry reads through `config_in_force()` and, written through
   `POST /api/settings`, is read back changed through `config_in_force()`
   without any `cache_clear` call by the test; (d) the served `options` of
   `max_hits`, `max_transfers` and `hit_bar` carry the saved value when it
   is not offered, in order.
3. **The card.** `grep -n "HIT_BARS\|NO_CAP\|?? 0.6\|withCurrent"
   frontend/src/hubs/this-week/LadderCard.tsx` prints nothing, and
   `LadderCard.test.tsx` shows the three selects rendering server-supplied
   options (a row's option labelled `no cap`, one labelled `bank`, and a
   hit-bar option the fixture invents, none of which the card could know).
4. **Screenshots** `frontend/scripts/shots.sh v17e`: `this-week-lower`
   (3400 px, reaching the ladder card's selects) and `settings`, dark and
   light, approved by the user.

Verdict rule: all four pass → merge. Any fails → §4 of the programme: ship
nothing, record the numbers in §10, leave the branch.

The suites: `.venv/bin/pytest -q` and `cd frontend && npx tsc --noEmit &&
npx vitest run` green, `npm run types -- --check` clean.

## 2. The decisions the grilling settled

### 2.1 The four readers become fields (Config 59 → 62)

`Config` gains three fields; `top_n` is already one.

| Field | Table, key | Default | Loader rule |
|---|---|---|---|
| `price_timing: bool` | `[optimizer] price_timing` | `True` | splatted like every `[optimizer]` key; `NON_FIELD_OPTIMIZER_KEYS` and the pop delete |
| `xg_per_shot: bool` | `[model] xg_per_shot` | `False` | read key by key (`[model]` is not splatted); `bool(...)` |
| `news_lineup_providers: list[str]` | `[news] lineup_providers` | `["ffs", "rotowire"]` | cleaned by `_providers` exactly as today: unknown names dropped with a line, a non-list falls back with a line, `[]` honoured as the kill switch |

Named `news_lineup_providers` for the same reason every other `[news]`
field carries the prefix. `tests/test_v10_degradation.py` pins that name
absent and its own docstring says the refusal's cause was retired by v12 W1
and "losing it a second time would have to be on the merits"; the merits
are §0. Ruling in §7.

`top_n` stays the field it is (what the file said, merged one level by the
overlay). What the solver gets is one accessor on the dataclass:

```python
def solver_top_n(self) -> dict[str, int]:
    """``top_n`` merged over ``DEFAULT_TOP_N`` with v12 W1's lenience: a
    position that is missing, non-integer, boolean or ≤ 0 keeps the shipped
    value; an unknown position is dropped. A fresh dict per call."""
```

`DEFAULT_TOP_N` moves from `optimize/milp.py` to `config.py` (milp imports
it from there; `optimize/**` is orchestrator-only, ruling in §7), so
`config.py` imports nothing from the optimizer. `build_pool` reads
`config_in_force().solver_top_n()` when handed no pool.

Why fields and not accessors on a second view type: a `ConfigInForce(cfg,
raw)` wrapper would keep the pin at 59 by carrying the raw dict beside the
dataclass, which is two types for every serve-time site to learn and the
merged TOML living on in memory. The pin exists so a field cannot appear
silently; three named fields in one commit is the case it was written for.

### 2.2 One read, one invalidation; `load_config` stays the parser

```python
def load_config(path: Path | str = "config.toml") -> Config   # unchanged: the parser; raises
def config_in_force() -> Config                                # cached; never raises
def invalidate() -> None                                       # the one clearing
```

- `load_config(path)` is the implementation: parse `path` with the overlay
  merged, validate, raise `GafferError` on a missing file or a bad value.
  The CLI keeps calling it loudly, and tests keep pointing it at
  `tmp_path`. Its 41 sites do not move.
- `config_in_force()` is `serving_config` renamed and re-documented: the
  cwd's `config.toml` with `config.local.toml` merged over it, cached for
  the life of the process, degrading to `Config(entry_id=0, league_id=0)`
  on any failure, because a clone with no `config.toml` still has to
  predict. Every `serving_config()` site (18 in `src/`, one in
  `scripts/v12_w3_support.py`) becomes `config_in_force()`. `serving_config`
  and `serving_config.cache_clear` are deleted, not aliased: a name that
  survives is a name someone will keep reading through.
- `invalidate()` clears the view's cache and every cache keyed on the
  file: today `_owned_price_falls` in `price_timing.py` (which reads the
  switch through the view and the parquet log; its own `cache_clear`
  stays as the price-log clear the nightly `gaffer prices` run needs).
  `_optimizer_top_n`'s cache no longer exists. `routers/settings.py`'s
  three clears become one `invalidate()`; `routers/meta.py`'s health poll
  calls `invalidate()` before it reads, for the reason its comment gives
  (the page a user opens after a hand edit). `golden_cwd` calls
  `invalidate()` on both sides.
- Tests: every `serving_config.cache_clear()` and
  `optimizer_top_n.cache_clear()` becomes `invalidate()`. Unprotected files
  are the implementer's; the protected ones are listed in §7.

Two adapters, one seam: the loud read for a person at a terminal, the quiet
read for a fetcher mid-solve. A third (`config_in_force(strict=True)`) was
rejected as 41 moved sites for one name fewer.

`focus_league()` stays: the whitelist may never name `league_id` (v12 W5
secrets pin), so the focus row reads the *effective* league id through a
reader. It reads `config_in_force().league_id` rather than `load_config()`
so a cold clone reads 0 by the same path as everything else. It is the one
`source="reader"` entry left.

### 2.3 Bounds stated once; one refusal sentence

`config.py` gains:

```python
BOUNDS: dict[str, tuple[float, float]] = {
    "horizon": (1, 8), "decay": (0.0, 1.0), "itb_value": (0.0, 1.0),
    "bench_curve": (0.0, 1.0), "lambda_cap": (0.0, 2.0), "top_n": (1, 200),
    "max_hits": (0, NO_CAP), "max_transfers": (0, NO_CAP),
    "hit_bar": (0.5, 0.95), "focus": (1, 99_999_999),
}
HIT_BAR_LO, HIT_BAR_HI = BOUNDS["hit_bar"]

def out_of_range(field: str, value) -> str:
    """The one sentence for a value outside ``BOUNDS[field]``:
    ``[optimizer] hit_bar = 1.2 — must be a number between 0.5 and 0.95``,
    with ``(15 means no cap)`` appended for the two caps. The loader raises
    it as ``GafferError``; the settings router returns it as the 422's
    ``error``."""
```

The section prefix comes from the whitelist's `section` where the field is
whitelisted and from a small `_SECTION` map in `config.py` otherwise (the
two caps and the bar are checked by the loader and whitelisted, so the map
holds just those three today). `_check_caps` and `_check_hit_bar` keep
their type rules and use `out_of_range` for the sentence. The loader checks
what it checks today and no more: a `horizon = 10` in `config.toml` loads
today and still loads; `BOUNDS` is the one statement, the router enforces
all of it on a write, the loader enforces the three it always did.

`SettingKey.lo`/`hi` are no longer typed per entry: the dataclass gets a
`bounds` property returning `BOUNDS.get(field)`, and `WHITELIST` entries
drop their two literals. `routers/settings.py`'s `_checked` keeps every
type rule and replaces its three range sentences with `out_of_range`
(`floats3` and `pool` say "each of" by passing the offending element; the
sentence is the same shape).

### 2.4 `SettingKey.options` and `SettingRow.options`

```python
@dataclass(frozen=True)
class SettingKey:
    ...
    options: tuple[tuple[int | float, str], ...] = ()
    """The values a select offers, with the word for each; empty for a row
    that is typed rather than picked. The served row also carries the saved
    value when it is not one of these (§2.5)."""
```

Set on three entries, with today's card values and words:

| Entry | options |
|---|---|
| `max_hits` | `(0,"0"), (1,"1"), (2,"2"), (3,"3"), (NO_CAP,"no cap")` |
| `max_transfers` | `(0,"bank"), (1,"1"), …, (5,"5"), (NO_CAP,"no cap")` |
| `hit_bar` | `(0.5,"50%"), (0.55,"55%"), (0.6,"60%"), (0.65,"65%"), (0.7,"70%"), (0.75,"75%"), (0.8,"80%"), (0.9,"90%"), (0.95,"95%")` |

`schemas.py`:

```python
class SettingOption(BaseModel):
    value: float | int
    label: str

class SettingRow(BaseModel):
    ...
    options: list[SettingOption] = Field(default_factory=list)
    """What a select offers, in order, the saved value included (§2.5).
    Empty for a row the tab types into."""
```

`choices` (the strings of a `kind == "choice"` row) stays as v15 shipped
it; folding it into `options` would move the Segmented control and the v15
rails for nothing this cycle needs.

Types regenerated (`cd frontend && npm run types`), `schemas.json` and
`types.generated.ts` committed with the schema change.

### 2.5 The server inserts the saved value

`_panel()` builds `options` per row as the entry's tuple with the current
value inserted in sorted order when it is not already there, labelled by
`str(value)` for the caps and `f"{round(value*100)}%"` for the bar (the
entry's `label_for(value)` — a one-line callable on `SettingKey`, default
`str`; the bar's is the percent). A hand-edited `max_hits = 5` or
`hit_bar = 0.62` therefore arrives as an option the card can select, and
`withCurrent` leaves the card. `SettingsTab` does not render `options`: it
is the full-range editor and keeps its number inputs.

### 2.6 The ladder card renders the settings rows

`LadderCard` fetches `GET /api/settings` once on mount, beside
`/api/ladder`, keeps the three rows it needs by `key`, and renders each
select from `row.options` (`value` and `label` verbatim) with `row.value`
selected. `setSetting` posts as today and rebuilds; after the rebuild's
reload the card re-fetches the settings rows so the selects show the value
the server holds. The `?? 0.6` default goes: the bar select's value is the
`hit_bar` row's value, and until the rows arrive the selects are disabled
with no options. `NO_CAP`, `HIT_BARS` and `withCurrent` are deleted;
`capText` stays (it prints the payload's cap, not a setting).
`ThisWeek.test.tsx`'s route mock answers `/api/settings` with a three-row
panel; `LadderCard.test.tsx` mocks it the same way and gains the options
test §1.3 names. A settings fetch that fails leaves the ladder table
rendered and the three selects disabled with the failure in the card's
callout: the ladder is the card, the selects are its controls.

v17h will fold this fetch into `usePageData`; this cycle adds one request
to This Week and says so.

### 2.7 The golden board and the three new fields

`asdict(golden_config())` gains three keys. The header on disk does not
have them and the fixture is untouched by rule, so
`test_the_header_config_is_golden_config` compares on the header's keys
(`{k: v for k, v in asdict(...).items() if k in header["config"]} ==
header["config"]`) and asserts the three absent ones hold the defaults the
recorded `config.toml` implies. `write_golden_toml` drops its special
`price_timing = true` line: `price_timing` joins `_TOML_LAYOUT["optimizer"]`
last, so the written file is byte-identical; `[model] xg_per_shot` and
`[news] lineup_providers` join the layout so the round-trip test covers
them (`[model]` is a new table in the layout). The scratch tree's
`config.toml` is the fixture's copy and is not rewritten by this cycle.

### 2.8 The settings router stops opening files

`config.py` gains the overlay's file operations, so the router keeps
validation and the wire shapes only:

```python
def read_overlay() -> tuple[dict, str | None]
    """``config.local.toml`` parsed, or ``({}, why)`` when it is unreadable;
    ``({}, None)`` when absent."""
def write_overlay(raw: dict) -> None
    """Atomically, with the header comment, through ``gaffer.io.atomic_write``."""
def value_source(section: str, key: str) -> Literal["local", "base", "default"]
    """Which file the in-force value of ``[section] key`` comes from."""
def base_exists() -> bool
```

`_panel()`'s two `_read` calls and `_table` become `value_source` per row;
`save`'s read and `_write` become `read_overlay` / `write_overlay`. The
router's sentences (`no config.toml — copy config.example.toml …`,
`config.toml unreadable (…)`) stay in the router; only the file access
moves. The `tomllib`/`tomli_w` imports leave the router, which is what
makes §1.2(a) a grep and not a review.

## 3. Approach, and the two rejected

Chosen: fields for the four, one cached view with one clearing, bounds and
options on the registry, file access in `config.py` only, the card over
the rows. Rejected: (i) a `ConfigInForce` wrapper type (§2.1); (ii)
`config_in_force(strict=True)` replacing `load_config` (§2.2). Also
considered and left: an mtime-keyed self-invalidating cache. It would make
`invalidate()` unnecessary for hand edits, but a solve mid-run would then
cross an edit silently, which `APPLY_NOTE` promises mostly does not
happen; explicit invalidation at the two write/poll sites keeps that
promise legible.

## 4. The interface

`src/gaffer/config.py` after this cycle exports: `Config` (62 fields,
`solver_top_n()`), `load_config`, `config_in_force`, `invalidate`,
`focus_league`, `BOUNDS`, `HIT_BAR_LO`, `HIT_BAR_HI`, `NO_CAP`,
`DEFAULT_TOP_N`, `DEFAULT_LINEUP_PROVIDERS`, `DEFAULT_LLM_COMMAND`,
`LLM_NO_TOOLS`, `LOCAL_OVERLAY`, `SPLATTED_SECTIONS`, `out_of_range`,
`read_overlay`, `write_overlay`, `value_source`, `base_exists`. Gone:
`serving_config`, `price_timing`, `xg_per_shot`, `lineup_providers`,
`optimizer_top_n`, `NON_FIELD_OPTIMIZER_KEYS`.

Call sites that change (all mechanical renames unless noted):

| Site | Today | After |
|---|---|---|
| `price_timing.py:64,168` | `price_timing()` | `config_in_force().price_timing` |
| `models/train.py:580` | `xg_per_shot()` | `config_in_force().xg_per_shot` |
| `data/news/lineups.py:492` | `lineup_providers()` | `cfg.news_lineup_providers` (cfg already in hand) |
| `optimize/milp.py:993` (orchestrator) | `optimizer_top_n()` | `config_in_force().solver_top_n()`; `DEFAULT_TOP_N` imported from `config` |
| `routers/meta.py:312-318` | two clears, `optimizer_top_n()` | `invalidate()`, `config_in_force().solver_top_n()` |
| `routers/settings.py` | three clears, own file reads | `invalidate()`, §2.8 |
| 18 `serving_config()` sites | | `config_in_force()` |
| `ladder.py:720` etc. | `NO_CAP, serving_config` | `NO_CAP, config_in_force` |
| `settings_keys.py` | literals, `reader="gaffer.config:price_timing"` | `bounds` from `BOUNDS`, `price_timing` becomes `source="config"`, `options` on three |
| `golden_client.py` | `serving_config.cache_clear()` ×2, the special line | `invalidate()`, layout entries |

## 5. What sits behind the seam

Behind `config_in_force()`: the cwd, the two files, the overlay merge, the
three checks, the fallback config. Behind `invalidate()`: which caches are
keyed on the file. Behind `BOUNDS`/`out_of_range`: the numbers and the
words. Behind `options`: what a select offers and how a value is worded.
Nothing else in the tree needs to know any of it.

## 6. Tests

New: `tests/test_v17e_config.py` — the rail (§1.2), plus: the three fields
load from their tables with the loader rules of §2.1; `solver_top_n()`'s
lenience on the same TOML bodies `test_v12_top_n.py` uses today;
`invalidate()` drops a stale view and a stale price-fall table;
`value_source` for local, base, default; `out_of_range` for a cap, the bar
and a float. Frontend: `LadderCard.test.tsx` renders options from the rows
and posts as before; `SettingsTab.test.tsx` unchanged except the fixture
gains `options: []`.

Moved, same bodies: `test_v12_top_n.py`'s reader tests become
`load_config(...).solver_top_n()` tests; `test_v12_price_timing.py`'s
switch tests read `load_config(path).price_timing` and the "does not reach
the constructor" test inverts (it does now, and `hasattr` is the claim);
`test_v10_config_providers.py`'s tests read `news_lineup_providers`;
`test_v12_xg_per_shot.py:153` reads the field. `test_the_health_card_
reflects_a_config_edit_because_it_clears_the_cache` keeps its two halves
through `invalidate()`.

Dead: every test whose subject was a path-taking reader's own file handling
(a corrupt `nothing.toml` handed to `price_timing`); the loader's own tests
cover that once.

## 7. Pins and protected files

`Config` fields 59 → 62 in `tests/test_v13_degradation.py`, its own commit,
the three names added to the by-name assertion. Routes 51 and job kinds 12
unchanged. `tests/test_v12_w1_degradation.py` (the meta-rail) unchanged:
the pin stays in the v13 file.

Orchestrator-only diffs, each with its ruling:

| File | Lines | Change | Ruling |
|---|---|---|---|
| `tests/test_v13_degradation.py` | 31-35, 207-216 | 59 → 62 with names; `invalidate()` in the fixture | the pin moves by plan |
| `tests/test_v10_degradation.py` | 33, 434-437 | the absence pin becomes a presence pin on `news_lineup_providers` with the default; import changes | the docstring reopens the question on the merits; §0 |
| `tests/test_v12_w2_degradation.py` | 195-196 | the two `not in names` become `in names` with the defaults asserted | same |
| `tests/test_v12_w5_degradation.py` | 21, 33-52, 250 | `invalidate()`; line 250 unchanged (a kwarg on a solver call, not the reader) | rename |
| `tests/test_v8e_degradation.py` | 17, 39-48 | `invalidate()` | rename |
| `tests/test_web_job_kinds_v8f.py` | 94-101 | `invalidate()` | rename |
| `tests/test_v12_w5_settings.py` | 58-75 | readers == `["focus"]`; `price_timing` is a field, as the message told the next cycle to do | the rail's own instruction |
| `src/gaffer/optimize/milp.py` | 136, 985-993 | `DEFAULT_TOP_N` imported from `config`; `solver_top_n()` | one read site |
| `tests/test_v6_degradation.py`, `test_v7_model_degradation.py`, `test_v8g_degradation.py` | their `cache_clear` lines | `invalidate()` | rename (verified by grep at plan time; a file with none is skipped) |

`tests/test_v12_w5_settings.py` is not in CLAUDE.md's protected list but
carries a rail with a pin; treated as protected for the one test.

## 8. Process

Spec → plan (`plans/2026-09-08-v17e-config-in-force.md`) →
superpowers:subagent-driven-development. Implementers never open
`config.toml`, never run the golden `--record`/`--write`, never touch a §7
file. The pin commit and the §7 diffs are the orchestrator's. The gate
(§1) runs once the branch is green, then screenshots, then the user's
approval, ff-merge, push, the security ritual, docs, tracker, memory.

## 9. Out of scope

Renaming any TOML key. The overlay's file format. Merging `choices` into
`options`. `SettingsTab` rendering selects. An mtime-keyed cache. Folding
the card's settings fetch into a page hook (v17h). `report.html.j2`'s
literal hit price (v17b's open item).

## 10. Outcome

_(filled by the orchestrator after the gate)_
