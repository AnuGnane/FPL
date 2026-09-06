# gaffer v15 — leagues (every mini-league, one focus, a manual stance)

*Brainstormed and approved 2026-09-06 with the visual companion; the layout
the user chose is option B in
`.superpowers/brainstorm/65685-1788690419/content/league-layout.html`. A
feature cycle: the League hub shows every league the entry is in, one of
them drives the solver, and the user can override the stance the solver
takes. No change to how the focus league's λ is computed.*

## 0. Why

The user's words: "rework the league and show users all of the leagues
they are in not just one", "wondering how that may affect … the wider model
and its calculations if it … [tries] to capture lead in one league but would
behave differently if defending league in another", and "want to be able to
manually adjust if its wanting to chase/defend or just maximise points in
generalistic way".

Today one `fpl.league_id` drives everything: the standings, rivals, race,
sim and the λ that tilts the MILP candidate pool. The entry endpoint already
lists every classic league the entry is in (this entry: 13, of which 7 are
private), but nothing reads that list.

## 1. The decisions the user made

1. **Scope of "all leagues": private mini-leagues only.** The FPL entry
   payload's `league_type` flag (`x` private, `s` public/system) is the
   rule; no size threshold. Public leagues (Overall, country, club, sponsor)
   are shown as a rank line only.
2. **One focus league drives the solver.** No blending of stances across
   leagues. The other private leagues get the full race, rivals and what-if
   views but never influence picks.
3. **Manual override at full tilt.** A forced chase or defend uses λ at the
   existing `[league] lambda_cap`; neutral is λ = 0 (plain points-max); auto
   is today's behaviour.
4. **Set in the League hub, persisted through settings.** The focus and the
   stance are written through the existing settings endpoint into the
   overlay `config.local.toml`, so Model → Settings, the CLI and the solve
   job all see the same values.
5. **Layout B: an overview tab, then drill in.** A new first tab lists every
   league in one table; clicking a private row opens its race, rivals and
   what-if.

## 2. Approach, and the two rejected

**Focus league (chosen).** One squad can only be tilted one way, so exactly
one league's Strategy reaches the solver, as now. The multi-league work is
display plus a selector. One λ, replayable, no new formula, no change to
protected solver code beyond a single call.

*Blend (rejected for this cycle).* Per-league λ and cover tables merged by
weight. Chasing in one league and defending in another largely cancel, so
the blend drifts toward neutral; it needs a replay to justify and changes
protected code. Recorded as a later model-cycle experiment.

*Auto-focus (rejected).* The model picks the focus each week by the largest
reachable swing. The stance can flip week to week, which makes the plan hard
to trust.

## 3. Model and stance

### 3.1 Focus league

- Effective focus = `[league] focus` from the overlay if set and non-zero,
  else `[fpl] league_id`. Config load resolves this into the existing
  `Config.league_id` field, so `advise.py`, `league_sim`, the routers and
  the CLI find the focus without change.
- `fpl.league_id` is never rewritten. The settings overlay keeps its rule of
  never touching `config.toml` or the entry/league ids in it.

### 3.2 Stance override

- New Config field `stance: str = "auto"`, one of `auto | chase | defend |
  neutral`, read from `[league] stance`. Any other value fails config load
  with the same plain-message pattern as the other `[league]` fields.
- New pure function in `src/gaffer/league_mode.py`:

  ```python
  def apply_stance(strategy: Strategy, stance: str, params: LeagueParams) -> Strategy
  ```

  - `auto` → returns `strategy` unchanged, `source="auto"`.
  - `chase` → `lam = +params.lambda_cap`, `stance="chase"`.
  - `defend` → `lam = -params.lambda_cap`, `stance="defend"`.
  - `neutral` → `lam = 0.0`, `stance="neutral"`.
  - For the three manual cases `source="manual"`; `gap`, `weeks_left`,
    `rival_name`, `z`, `sigma_m` and `cover_weights` are kept as computed
    so reports still say where the user stands.
  - Sign convention is the one `compute_strategy` already uses: chase is
    λ > 0, defend is λ < 0.
- `Strategy` gains `source: str = "auto"`, appended and defaulted so
  positional callers keep working (same convention as the v4d fields).
- `advise.py` (protected): exactly one added call after `compute_strategy`
  at the league block (~line 715): `strategy = apply_stance(strategy,
  cfg.stance, params)`. The diff is shown to the user before commit.
  Chips are still scored on the untilted pool; reports still show raw EP;
  λ = 0 is still the exact points-max path.

### 3.3 Other leagues never tilt

A non-focus league's page computes its own `Strategy` with
`compute_strategy` for display only (§5.2). `apply_stance` is not applied
to it. The page labels it "would chase" / "would defend" / "would be
neutral".

## 4. Config and settings

### 4.1 Config

- `stance` added (§3.2). The focus reuses the `league_id` slot (§3.1). Net
  field count 57 → 58.
- `[league] focus` accepts a positive int; `0` or absent means "use
  `fpl.league_id`".

### 4.2 Settings whitelist (`src/gaffer/web/settings_keys.py`)

Two new rows in section `league`:

| field | toml_key | label | kind | bounds |
|---|---|---|---|---|
| `league_id` | `focus` | Focus league | `int` | lo 1, hi none |
| `stance` | `stance` | Stance | `choice` | `auto, chase, defend, neutral` |

- New kind `choice`: `SettingKey` gains `choices: tuple[str, ...] = ()`.
  `_checked` in `routers/settings.py` validates a `choice` value is a string
  in `choices`, else the existing 422 refusal shape. `SettingRow` (schema)
  gains `choices: list[str]`, empty for other kinds. The Model → Settings
  tab renders a `choice` row as a `Segmented` control.
- Reading: `current_value` already does `getattr(cfg, field)`, so "Focus
  league" reads the effective focus and "Stance" reads `cfg.stance`.
- Writing `value: None` removes the overlay key, as today: focus falls back
  to `fpl.league_id`, stance to `auto`.
- The module docstring's "entry/league ids are untouchable" sentence is
  reworded: `fpl.*` stays untouchable; `league.focus` is an overlay
  override of which league is the focus.

### 4.3 Focus validation

The settings endpoint accepts any positive int, like its other int rows.
The League overview (§5.1) returns `focus_warning` when the focus id is not
one of the entry's private leagues, and the hub shows it as a warn
`Callout` rather than refusing the page, so a typo in the overlay cannot
lock the user out.

## 5. API

### 5.1 New route: `GET /api/league/leagues`

Reads `client.get_entry(cfg.entry_id)["leagues"]["classic"]`.

Response `LeaguesOverview`:

```
focus_league_id: int
focus_name: str | None        # None when focus_warning is set
stance: "auto"|"chase"|"defend"|"neutral"   # cfg.stance
focus_warning: str | None     # "focus league 123 is not one of your private leagues"
private: list[PrivateLeagueRow]
public:  list[PublicLeagueRow]
gw: int
```

`PrivateLeagueRow`: `league_id, name, rank, last_rank, entries` (None when
`rank_count` is null), `started: bool` (`rank_count` non-null),
`gap: int | None`, `gap_kind: "ahead"|"behind"|None`, `would:
"chase"|"defend"|None`, `is_focus: bool`.

- `gap` comes from one standings page (page 1) of that league: rank 1 →
  `ahead`, `gap = my_total − second_total`, `would = "defend"`; otherwise
  `behind`, `gap = leader_total − my_total`, `would = "chase"`. If the
  user's row is not on page 1 the user's own total comes from the entry
  payload's `summary_overall_points`. A league with one entry, or not
  started, has `gap = None`, `would = None`.
- The `would` word is gap-sign only; the deadband and λ appear when the
  league is opened (§5.2). The hub labels the column "would".

`PublicLeagueRow`: `league_id, name, rank, last_rank, entries`.

- Rows are ordered: private by `rank` ascending then `entries` descending
  (the focus league is not pinned first; it carries `is_focus`); public by
  `entries` descending.
- Cached in-process for 5 minutes keyed by current gameweek (the pattern
  `league_sim.py` uses: module cache under a lock). Cost uncached is one
  entry call plus one standings page per started private league.
- FPL failures raise `GafferError` → the router's existing readable 422
  with a retry button.

### 5.2 Existing routes take a league

`race`, `rivals`, `rivals/{entry_id}` and `sim` gain an optional query
`league_id: int | None = None`; `whatif`'s request body gains
`league_id: int | None`. `None` means the focus.

- **Focus league:** unchanged behaviour. `race()` reads λ from the solve
  state as now. Its response gains `focus: true`, `league_name`, and
  `stance_source` (`cfg.stance == "auto"` → `"auto"` else `"manual"`).
- **Other league:** `race()` fetches that league's standings and rival
  history (`fetch_rival_entries`, `fetch_rival_history`, disk-cached per
  gameweek as today) and calls `compute_strategy` with
  `LeagueParams.from_config(cfg)`. `lam`, `stance`, `gap`, `lam_explained`
  come from that Strategy; `focus: false`; `league_name`; `stance_source`
  `"auto"`. Trajectory, standings and win probability are built exactly as
  for the focus league.
- `rivals()` and `rival()` read the chosen league's standings; the rival
  picks cache under `data/raw/league` is already keyed by entry and
  gameweek, so nothing collides.
- `sim()` and `whatif()` key their in-process cache on
  `(league_id, gw, mtimes)`; the cold-cache 204 rule for `cached_only`
  stays.
- A `league_id` that is not one of the entry's private leagues → 422
  `GafferError("league 123 is not one of your private leagues")`.

### 5.3 Paging fix (display path only)

`_standings` in `routers/league.py` pages until the user's own row is
present, then fetches one page more, instead of stopping at 50 rows. This
is the standings the race, rivals and overview show. `fetch_rival_entries`
in `data/league.py`, which feeds `compute_strategy` and the sim, keeps its
current top-50 behaviour so the focus league's λ and cover table are
computed exactly as before this cycle. Evidence for the display fix: in the
138-entry focus league the user was 80th the week before this design and
the race would have shown a page they were not on.

### 5.4 Route pin

One new path: 48 → 49.

## 6. League hub

### 6.1 Tabs and URL

Tabs `leagues | race | rivals | whatif`; default `leagues`. A second URL
param `league=<id>` chooses which league the other three tabs show; unset
means the focus. Both params use `useTabParam`'s replace semantics; unknown
values fall back.

### 6.2 Leagues tab (`frontend/src/hubs/league/LeaguesTab.tsx`)

The overview from layout B, in ledger table constants:

- **Private table.** Columns: League, Rank, Of, Move (rank delta since last
  week, `Chip` up/down, "—" when unknown), Gap (`+9 on 2nd` / `−12 to 1st`,
  tabular), Would (`would chase` / `would defend`, muted; for the focus row
  the live word and λ from the race payload if loaded, else the `would`
  word), and an action cell: `focus` chip (accent) on the focus row, a ghost
  `Button` "make focus" on the others. A not-started league shows "not
  started" in Gap and no action. Clicking the name opens the race with
  `?tab=race&league=<id>`.
- **Stance control.** Beneath the private table: label "Stance · focus
  league", a `Segmented` with Auto / Chase / Defend / Neutral, current value
  from the overview. Auto's segment reads "Auto · chase" (the live word)
  when the focus race payload is loaded.
- **Public table.** League, Rank, Of, Move. Tabular numerals, no actions.
- **Writes.** "make focus" posts `{key: "league_id", value: <id>}`; the
  stance control posts `{key: "stance", value: "<word>"}`; both to
  `/api/settings`, then refetch the overview and the race. A failed write
  shows the existing `Toast` and leaves the control on the old value.
- **Warning.** `focus_warning` renders as a warn `Callout` above the table.
- **Empty.** No private leagues → `EmptyState` "You are in no private
  leagues", public table still shown.

### 6.3 Race, Rivals, What-if for a chosen league

- `PageHeader` shows the league name; a back link "‹ Leagues" returns to
  the overview.
- When `focus` is false, a note `Callout` above the race chart: "Plan is set
  by <focus name> (<its stance>). Here you would <chase/defend/be neutral>,
  λ <value>." When the focus has a manual stance the note says "(manual
  <stance>)".
- `WhatIfSim` and `FieldPanel` pass the chosen league id to their calls.
- The race chart, standings table and rivals table are unchanged.

### 6.4 This Week

The gap tile keeps `advice.strategy` for gap and stance and adds the focus
league's name from `/api/league/leagues` as its caption, plus a `Chip`
"manual" when the overview's `stance` is not `auto`. Until the overview
loads the caption is "League". No other hub changes.

### 6.5 Ledger rules

Every new piece uses the v14 kit (`table.ts` constants, `Chip`,
`Segmented`, `Callout`, `Button`, `EmptyState`, `PageHeader`). The tokens
rules test in `frontend/src/kit/tokens.test.ts` applies unchanged; no raw
hex, no rounded-full, no font-mono outside the two allowed files.

## 7. CLI

No new command. `gaffer advise` and `gaffer league` pick up the focus and
the stance through Config. `gaffer league`'s "set fpl.league_id" message is
reworded to mention the focus.

## 8. Tests

### 8.1 Python

- `tests/test_league_stance.py`: `apply_stance` for each stance; λ equals
  ±cap / 0; `source`; computed `gap`, `rival_name`, `cover_weights`
  preserved; `auto` returns the same object values.
- Config: `[league] focus` overrides `fpl.league_id`; `0`/absent falls
  back; `stance` default `auto`; bad stance fails load with a message.
- Settings: `choice` kind validates and rejects; rows carry `choices`;
  `focus` and `stance` rows appear in `live_keys()`.
- `tests/test_web_league_overview.py` with a fake client: private/public
  split by `league_type`; not-started league; `ahead`/`behind` gap signs;
  own total from the entry payload when off page 1; `focus_warning`; cache
  by gameweek; ordering.
- Router: `race?league_id=` for a non-focus league computes its own
  Strategy and reports `focus: false`; unknown league → 422; `sim` cache
  keyed by league; `_standings` pages to the user's row.
- Pins: `tests/test_v13_degradation.py` Config 57 → 58,
  `tests/test_v11_degradation.py` routes 48 → 49, JOB_KINDS stays 12.
  Suite ends strictly above 4110 passed, nothing failing.

### 8.2 Frontend

- `LeaguesTab.test.tsx`: rows, focus chip, "make focus" posts the right
  body and refetches, stance segmented posts, warning callout, not-started
  row, empty state.
- `League.test.tsx`: default tab `leagues`; `league` param drives the
  race fetch; header name and back link; non-focus note callout.
- `SettingsTab.test.tsx`: `choice` row renders as segmented and posts.
- `ThisWeek.test.tsx`: caption shows the focus name; manual chip.
- `tokens.test.ts` unchanged and passing.

## 9. Protected files and sign-off

- `src/gaffer/advise.py`: one added call (§3.2). Shown to the user before
  commit.
- `tests/test_v13_degradation.py` and `tests/test_v11_degradation.py`: one
  number and one docstring line each (§8.1). The user approved both moves
  on 2026-09-06; the orchestrator makes these edits, not a subagent.
- No other protected file changes. `optimize/**`, `set_pieces.py`,
  `web/jobs.py`, `routers/whatif.py`, `scripts/s2_replay.py` untouched.

## 10. Process and gate

Same as v14. Branch `v15-leagues`; superpowers:writing-plans then
superpowers:subagent-driven-development with Opus implementers and the
orchestrator reviewing every task. Screenshot gate through the companion
for the League hub (all four tabs, a non-focus league open) and This Week,
dark and light. Then ff-merge, push, the security ritual (odds key grep with
the corrected extraction, `config.toml` untracked), GUIDE, ROADMAP and
memory updates.

## 11. Out of scope

- Blended stance across leagues (recorded for a model cycle).
- Head-to-head leagues (`leagues.h2h`, empty for this entry).
- A CLI overview command.
- Any change to how the focus league's λ is computed, the deadband, or
  the cover tilt.
- Per-league stance overrides: the stance applies to the focus league
  only, since only the focus reaches the solver.
