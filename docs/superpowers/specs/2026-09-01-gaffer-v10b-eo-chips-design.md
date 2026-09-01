# gaffer v10b — EO framing + season chip planner

Date: 2026-09-02. Branch: `feat/gaffer-v10b` off `b0cdc4e` (v10).

Both features are FRAMING and PLANNING layers. Neither changes what the
solver decides. Chips stay priced on the raw untilted pool — the
advise.py:798-806 boundary is defended, not crossed.

## §0 Constraints (standing)

- Implementation by Opus subagents; orchestrator reviews and runs gates.
- **Protected files**: `src/gaffer/advise.py`, `set_pieces.py`,
  `optimize/**`, `web/jobs.py`, `web/routers/whatif.py`,
  `tests/test_advise.py`, `test_odds.py`, `test_web_jobs.py`, all
  pre-existing `tests/test_*_degradation.py`, `scripts/s2_replay.py`.
  `journal.py` / `backtest.py` import-only. **No protected edits are
  anticipated this cycle; if the plan finds one is needed it STOPs.**
- Never stage `data/`, `reports/`, `models/`, `logs/`, `.claude/`,
  `config.toml`, `src/gaffer/web/static/`. Never `git add -A`.
- Pins: `JOB_KINDS` stays 12; `Config` stays 48 (nothing here needs a key);
  route count moves only by the §F2 endpoint and is pinned in
  `tests/test_v10b_degradation.py`.

## §F1 — EO framing ("points vs the field")

Three ownership notions exist and are deliberately distinct (data/tier_eo.py
docstring): `league_eo` (my rivals, captain-weighted), tier/field EO
(top-10k sample, `data/live/field_eo_log.parquet`, keyed by **element**),
and global `selected_by_percent`. What is missing is the framing surface.

- **F1a field EO into This Week.** Squad rows (ThisWeek.tsx:127-128 is the
  insertion point) gain the top-10k EO beside league EO; served via
  `latest_field_eo` (data/field.py:202 — `{}` on any failure), element→code
  through the existing mappers (the id-space split is the known hazard:
  league_sim router `_elements_by_code` :222). The captain block gains one
  framing sentence built server-side: the captain's field EO with its ±SE,
  and whether the pick is cover or attack — reuse `field_class` semantics
  (web/routers/players.py:95-123: shield ≥40% owned-and-field-high,
  sword/differential ≤15%). Absent field data → the sentence simply absent
  (never 0.0-as-fact — schemas.py:406-411 convention).
- **F1b bootstrap captaincy proxy.** Ingest `most_captained` (and
  `most_selected`) from the bootstrap events feed into the existing events
  snapshot columns (additive, artifacts.py SNAPSHOT convention), so the
  field's modal captain is known without the 455-call tier sample; shown in
  the captain framing when tier EO is absent (early season, scrape off,
  courtesy window). Column additive to the parquet — absent-safe readers.
- **F1c EO lens on the pitch view.** A This Week toggle tinting each
  PlayerCard by its served `field_class` quadrant (shield/sword/threat,
  already computed per player in the explorer payload — the pitch payload
  gains the same optional field). Off by default; pure presentation.

## §F2 — season chip planner

The dossier's finding: `chip_policy.py` has a finished, tested, **unused**
DGW seam — `load_chip_scenarios` + `apply_dgw_scenarios` (:93-135) reading
`data/chip_scenarios.toml`, which does not exist on disk and awaits fixture
projections. And there is no DGW/BGW detector anywhere.

- **F2a DGW/BGW detector.** New pure function (suggested home:
  `src/gaffer/data/fixtures.py` or beside the ticker logic — planner's
  call): over `data/live/fixtures_all.parquet` (full season, 380 rows),
  `fixtures_per_team_per_gw` → per-gw `{team_code: n}`; blanks = teams at
  0 in a gw that has fixtures for others, doubles ≥ 2. Serve via
  **one** new endpoint `GET /api/fixtures/outlook`: per remaining gw, the
  double/blank teams (codes + shorts) and a per-team fixture-count row —
  the ticker/matrix stay untouched.
- **F2b populate the seam.** A writer (part of the `refresh-data` job body,
  not a new kind) derives `data/chip_scenarios.toml` from the detector:
  `[dgw] {gw} = 1.0` for every *scheduled* double actually present in
  fixtures_all; no speculative entries. Absent file or empty detector
  output = today's behaviour byte-for-byte (already chip_policy's
  degradation path — rail it). The file is a data artifact: never staged.
- **F2c Season chips outlook view.** ChipsTab gains an "Outlook" segment
  beside the table/wildcard toggle: per chip — its θ trajectory
  (`stopping_thresholds`), the GW19 first-set expiry (`chip_windows`,
  2026-27 grants two of every chip), detected DGW/BGW weeks ahead, and
  the current gain vs θ. Labelled as planning, not advice. Honest empty
  state for the current reality (GW2, no doubles announced): "No doubles
  or blanks are scheduled yet — rearrangements usually start appearing
  around the cup rounds."
- Served numbers come from the existing `/api/chips/plan` (meta.py:49-71)
  plus the new outlook endpoint; no solver re-runs beyond what that
  endpoint already does.

## Non-goals

- No EO term in any objective; no chip decision changes; no rival squad
  re-modelling; no new job kinds; no scraping beyond what exists.

## §Gates

- **G1** — suite green (3047 py + 562 fe baseline); `tests/test_v10b_degradation.py`
  pins (kinds 12, Config 48, routes +1) and rails: empty field log →
  payload byte-identical to today where the framing is absent; absent
  chip_scenarios.toml → chip thresholds byte-identical; a fixtures_all with
  no doubles → outlook says so and chip_scenarios gains no [dgw] entries;
  element/code mismatch guard (a field log with unknown elements maps to
  nothing, never to the wrong player).
- **G2** — adversarial review, fix-first, re-verify; merge ritual.
- **No replay** — nothing on the training or decision path changes; the
  detector and writer are read-only over fixtures and additive data. That
  reasoning recorded here deliberately.

### G1 — suites, rails, pins (measured by the implementer)

- [x] `uv run pytest -q` — 3130 passed (main baseline 3047 + 83 new)
- [x] `npx tsc --noEmit` — clean
- [x] `npx vitest run` — 591 passed, 1 skipped (baseline 562 + 29 new)
- [x] `npm run build` — clean
- [x] Protected diff EMPTY — `advise.py`, `set_pieces.py`, `optimize/**`,
      `web/jobs.py`, `routers/whatif.py`, `test_advise.py`, `test_odds.py`,
      `test_web_jobs.py`, `s2_replay.py` all zero. §F2c's θ trajectory is
      built at the router from a callable rather than inside
      `optimize/chips.py` (plan A9), so the one candidate for an
      `optimize/**` edit dissolved as planned.
- [x] Pins: job kinds still 12, config fields still 48, OpenAPI paths
      44 → 45 and the one is `/api/fixtures/outlook`
- [x] Rails: empty field log → advice payload byte-identical and no
      `captain_field` key; no log but an events row → a key with a null `eo`
      and a note carrying no percentage; absent `chip_scenarios.toml` →
      `chip_thresholds_from_asset` identical for every chip in every
      gameweek; a fixture list with no doubles → outlook says so and no
      `[dgw]` entry is written; a field log of unknown elements maps to
      nothing and no player borrows a number
- [x] `data/chip_scenarios.toml` absent from the branch diff; no path under
      `data/`, `reports/`, `models/`, `logs/`, `config.toml` or
      `web/static/` appears in it; key-grep clean; `git show main:config.toml`
      fails

**Two protected pin edits, authorized by the orchestrator.**
`tests/test_v10_degradation.py` and `tests/test_v9d_degradation.py` both
pinned the OpenAPI path total at a bare `44`, and both are protected. The
implementer STOPped at that finding rather than widening the diff, per §0;
authorization was then given on the reasoning that an absolute pin exists
precisely to force a deliberate route addition through review, and that
contorting the API shape to dodge it would be serving the pin instead of the
product. Each file moves `44 → 45` with a provenance comment naming
`/api/fixtures/outlook`; v9d keeps its `/api/model` subset assertion, which is
v9d's own claim about v9d's own cycle; neither test is renamed. Nothing else
in either file changed.

### G2 — review and merge (orchestrator only)

- [ ] Adversarial review, fix-first, re-verify.
- [ ] Merge ritual: ff-only, push, `git show main:config.toml` fails, key-grep
      empty.

The live spot-checks for §F1 need a GW3 field scrape and a `refresh-data` run
before there is an EO row to show, so they are deferred to the orchestrator's
post-merge sequence rather than blocking the fix round; the degradation half —
the key absent rather than 0.0 — was verified on the real payload in their
place.

### No replay — recorded reasoning

Nothing on the training or decision path changes. §F1 is serve-time decoration
on an artifact already written; §F2a and §F2c are read-only over fixtures and
report the bar rather than moving it. §F2b is the one path that could reach a
decision, and on today's published list — ten fixtures in every one of
thirty-eight gameweeks — it writes nothing, so both arms would be the same arm.
That is v10's G2 again, and running it would buy three hours and a number
nobody could interpret. The property a replay would have demonstrated is
asserted directly in `tests/test_v10b_degradation.py` instead: an absent
`chip_scenarios.toml` produces identical thresholds to an absent scenario dict,
over the same `chip_thresholds_from_asset` call the advise run makes, for every
chip in every gameweek.

### Live spot-checks (orchestrator, on the dev server)

- [ ] This Week's header carries the captain's field EO with its ±SE and calls
      the pick cover or attack — and on a clone with no `field_eo_log.parquet`
      the sentence is simply absent rather than 0.0.
- [ ] The EO lens is off on load, tints the pitch when switched on, and is not
      offered in the table view.
- [ ] The Chips tab's Outlook segment shows the honest empty state on today's
      fixture list, names GW19 as the first-set expiry, and reads as planning.
- [ ] Run `refresh-data` and confirm `data/chip_scenarios.toml` is still
      absent, and that the run's row count is unchanged.
- [ ] `GET /api/fixtures/outlook` returns 38 weeks with `has_doubles: false`.
- [ ] Planning at 390px: the three-button strip wraps rather than pushes, and
      the Outlook's table scrolls inside its own container.

### Residuals

- The players explorer still reads `latest_field_eo()` with no season filter.
  Harmless while the log holds one season; wrong after a rollover, when
  element ids are re-issued and the same integer is a different footballer.
  One keyword when someone decides to make the change (plan A3).
- `advise.py`'s `captain_note` — the league-tilt armband sentence — is still
  written and still rendered nowhere. Surfacing it is a real and separate
  idea, deliberately not smuggled into this cycle (plan A4).
- Two code→element maps now exist: `league_sim._elements_by_code` and
  `web/field_frame`'s memoised one. Merging them would open a router this
  cycle otherwise never touches (plan A3).
- **`ThetaTrack` compares a wildcard's gain to θ on the wrong scale.** Each
  week's chip goes green when `gain >= theta`, which is exactly the comparison
  `optimize/chips.py:278` makes for `play_now` — so the strip is consistent
  with the number beside it and inconsistent with the wildcard's own
  arithmetic. A wildcard's `gain` is credited with *every horizon week from
  the week it is played onwards* (`chips.py:244-248`), so an early week is
  scored over more weeks and clears any flat bar almost regardless of the
  fixtures, while `per_week` is the rate the same file says to rank wildcards
  on. Inherited, not introduced: fixing it means deciding what a wildcard's
  bar means, which is a chip-policy question and not a rendering one.
- **`captain_field.most_captained` is served and rendered nowhere.** §F1b
  attaches the bootstrap's modal captain whenever it disagrees with — or
  stands in for — the tier sample, and `modal_note` words it, but the sentence
  only reaches the page through `note` on the EO-absent branch. When both are
  present the object rides along unread. Either This Week shows it beside the
  measured share or the key comes off the payload; leaving a served key with
  no reader is how a schema grows things nobody can delete.
- **The absolute route-count pin collides on every future route addition.**
  Three files now carry `len(paths) == 45` and two of them are protected, so
  every cycle that adds an endpoint pays the same authorization toll this one
  did — and the toll is paid by editing *historical* rails, which is exactly
  what "protected" is meant to prevent. v11 should consider one live-count pin
  in the current cycle's rail plus per-cycle **path-existence** assertions in
  each historical file: `test_v9d_degradation.py` asserting that
  `/api/model/calibration` is present says everything v9d actually claims, and
  says it without a number that a later cycle must come back and change.
