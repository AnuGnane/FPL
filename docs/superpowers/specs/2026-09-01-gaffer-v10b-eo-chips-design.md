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

### G1/G2 outcomes

_TBD by the cycle._
