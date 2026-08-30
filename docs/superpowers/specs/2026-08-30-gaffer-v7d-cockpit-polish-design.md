# gaffer v7d — cockpit polish (design)

Date: 2026-08-30 · Branch: `feat/gaffer-v7d` · Cycle type: UX/serving (no model-quality gates)

## §0 Context and decisions

User approved the scope ("cover everything deferred and planned"): the five items parked
across v7-ui §12, v7-model §5 and v7c §7. The Z1 flip shipped separately (`826ff6b`).
Decisions taken on scouted facts:

- **D1** — Fast advise rides the existing `Config.scenarios_n` seam. `advise.py:734`
  guards the sweep on `cfg.scenarios_n > 0`; n=0 is the byte-pinned pre-v4c rail
  (`tests/test_v4c_degradation.py`), every consumer (CLI lines, report template,
  ThisWeek/WhyPanel) already degrades on optional scenario fields, and v7b proved the
  gate is a no-op under option (b) anyway. No protected file moves. Delivery is a new
  **job kind** `advise-fast` plus a CLI `--fast` flag — NOT a per-run POST body
  (`JobRunner.start` is zero-arg and `tests/test_web_jobs.py` is protected).
- **D2** — The pen card reads `reports/pen_tracker.json` off disk (the quality.py
  pattern: UI renders the artifact, CLI/job makes it), served from the existing
  quality router (no `app.py` change). A `track-pens` job kind lets the browser
  regenerate it.
- **D3** — Compare-card name treatment = the *interaction* half (the `titleSize` half
  shipped in v7-model as `18fca6b`): `Card` gains a `heading?: ReactNode` slot so
  ComparePanel can pass `<PlayerName>`, and the Players-explorer name column switches
  to `<PlayerName>` too ("a player's name, everywhere" is that component's own
  contract).
- **D4** — Light theme is a `[data-theme="light"]` CSS-variable override block; all
  colour consumption is already var-backed (zero hex outside theme.css, charts and
  `color-mix` included), so no component changes. Three-state preference
  (system/dark/light), persisted in `localStorage` behind try/catch, boot script in
  `index.html` to avoid flash. `theme.test.ts` asserts dark values by containment —
  they stay verbatim.

## §1 F1 — Fast advise (`--fast`, job kind `advise-fast`)

- `src/gaffer/cli.py` `advise` command gains `--fast` (typer flag): builds
  `dataclasses.replace(load_config(), scenarios_n=0)` and passes it to `run_advise`.
  Help text: "skip the scenario sweep (~5 min); serves the raw optimum".
- `src/gaffer/web/job_kinds.py`: `run_train_and_advise_fast()` — same body as the
  advise kind but with `scenarios_n=0` via `dataclasses.replace`; registered as
  `advise-fast`. `tests/test_web_job_kinds.py` count assertion 5→7 (with F2's kind).
  New kind tests go in `tests/test_web_job_kinds_v7c.py`'s companion style — extend
  that file (not protected).
- Frontend: `types.ts` `JOB_KINDS` + labels (`advise-fast`: "Fast advise");
  `ThisWeek.tsx` header gets the Fast advise `JobButton` beside Run advise (same
  `onDone={load}`); `types.test.ts` count updated.
- `config.example.toml` `[scenarios]` comment gains one line noting `n = 0` disables
  the sweep and `--fast` / the Fast advise button do it per-run.

## §2 F2 — Pen tracker card in the Model hub

- Backend: `GET /api/pens` on the quality router (`src/gaffer/web/routers/quality.py`)
  returning `PenTracker(**json.loads(tracker_path().read_text()))`; missing file →
  `GafferError("no pen tracker report — run gaffer track-pens")` (app-wide 422 →
  EmptyState). Schemas in `web/schemas.py`: `PenTrackerGw` (all gw_block fields
  optional except `gw`, plus `error: str | None` — the union collapses into one
  optional-field model), `PenTrackerTotals`, `PenTracker` (`season`, `gws`,
  `season_totals`, `notes`).
- Job kind `track-pens` wrapping `pen_tracker.track_pens` + `save_tracker` (prints the
  one-line summary; returns `{"gws": n}`).
- Frontend: `PensSection` in `QualityTab.tsx` following the existing section pattern —
  its own `apiGet('/api/pens')` fetch, `EmptyState action="gaffer track-pens"` on 422.
  Card "Penalty term — {season}": season-totals stat row (pens taken, taker hit rate,
  pens/team-game vs served 0.13, predicted EP vs realized pen points), per-GW
  `DataTable` (gw, instrument badge — `pens_missed_only` gets a rust "floor" badge —
  covered rows, pens, hit rate), error-block rows rendered as a muted "unreadable"
  row, `notes` as faint footer lines. Model hub header gains the `track-pens`
  `JobButton` (`label="Track pens"`, `onDone={reloadQuality}`).

## §3 F3 — Snapshot button

- `types.ts`: add `snapshot` ("Snapshot news") to `JOB_KINDS`/labels; `types.test.ts`
  updated (the union grows 4→7 this cycle: snapshot, advise-fast, track-pens).
- `Model.tsx` header: `JobButton kind="snapshot" onDone={reloadHealth}` beside Refresh
  data (Health tab stays buttonless by its documented design; the header is the one
  control lane). Single-flight 409 message already handled by `useJobStream`.

## §4 F4 — Compare-card name treatment (interaction half)

- `kit/Card.tsx`: optional `heading?: ReactNode` prop, rendered inside the `<h3>` in
  place of the title string when given (`title` remains for the aria/key path — when
  both given, `heading` wins visually; keep the h3 element regardless for a11y, as the
  existing docstring demands).
- `ComparePanel.tsx`: `heading={<PlayerName code={player.code} name={player.name} />}`
  with `titleSize="lg"` kept and `PosBadge` still in `action`. The name becomes the
  standard click-to-explain control.
- `Players.tsx` explorer name column: plain text → `<PlayerName code name />` (no pos
  dot — the explorer has its own position column).
- Add the missing co-located `PlayerName.test.tsx` (renders name, opens ExplainModal
  on click) — the kit's one untested component.

## §5 F5 — Light theme

- `theme.css`: after the `@theme` block, a `[data-theme="light"]` block overriding
  every `--color-*` token (surfaces, text, sage/rust/info, four position hues).
  Palette targets: base `#f4f5f7`, card `#ffffff`, border `#d9dce2`, divider
  `#e7e9ee`, text `#191c22`, secondary `#3d434e`, muted `#6b7280`, faint `#9aa1ab`;
  sage `#3f7a44`, rust `#b0532f`, info `#2f6b96`; pos GKP `#96731f`, DEF `#2867a5`,
  MID `#6f51b8`, FWD `#b04f78`. Implementer may nudge values but every text token
  must hold ≥ 4.5:1 contrast on `card` (verify with a small contrast check in the
  theme test). Dark declarations keep their exact spelling (theme.test.ts containment).
- Three-state preference: `"system" | "dark" | "light"`. `system` = no `data-theme`
  attribute + a `@media (prefers-color-scheme: light)` mirror of the light block
  guarded `:root:not([data-theme="dark"])`; explicit choices set
  `data-theme` on `<html>`. New `kit/useTheme.ts` (read/write localStorage key
  `gaffer-theme` in try/catch, apply attribute, default system) + `kit/ThemeToggle.tsx`
  (compact three-way segmented control, icon + label, aria-labelled).
- Placement: desktop — sidebar footer under the nav (AppShell desktop branch); mobile —
  an icon-only button appended to the bottom tab bar row (7th slot, `aria-label`).
  `AppShell.test.tsx` / `responsive.test.tsx` matchMedia stubs extended as needed.
- `index.html`: tiny inline boot script setting `data-theme` from localStorage before
  first paint (try/catch, no-op on failure).
- `body` keeps its explicit token background (already `var(--color-base)`).

## §6 Constraints

Protected (zero diffs): `src/gaffer/advise.py`, `src/gaffer/set_pieces.py`,
`src/gaffer/optimize/**`, `tests/test_advise.py`, `tests/test_odds.py`,
`tests/test_web_jobs.py`, `tests/test_*_degradation.py`, `scripts/s2_replay.py`.
`JobRunner`/routes unchanged (new kinds only). The built bundle
(`src/gaffer/web/static/`) is regenerated by `npm run build` as the final task and
committed (it ships in the wheel).

## §7 Gates (orchestrator-run)

- **G1 fast:** `uv run gaffer advise --fast` completes with no "Scenarios:" line and
  materially faster than a swept run; unit tests pin `scenarios_n=0` threading in both
  CLI and job kind. (Side effect accepted: one extra advice-history entry on stale
  pre-GW2 data.)
- **G2 pens:** `GET /api/pens` serves the live artifact; missing-file path 422s with
  the track-pens sentence (unit).
- **G3 theme/UI:** `npm test` green, `tsc -b` clean, `npm run build` succeeds; toggle
  flips `data-theme` and persists across reload (vitest, localStorage stubbed);
  contrast assertions pass for the light palette.
- **G4:** full pytest green; protected audit empty; job-kind counts consistent
  backend (7) and frontend (7); rebuilt bundle committed; UI server restarted and
  smoked (`/api/pens`, snapshot button visible).

## §8 Out of scope

Per-run job options via POST body (needs protected-test surgery); Model-hub
"Preferences" page; theming the report HTML template; the v7c residuals
(track_pens total-failure overwrite, MULTISEED_DONE recovery).

## §9 Outcome

(filled at cycle close)
