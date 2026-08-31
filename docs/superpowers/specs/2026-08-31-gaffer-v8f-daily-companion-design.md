# gaffer v8f — daily companion

Date: 2026-08-31. Parent: `2026-08-30-gaffer-v8-research-proposal.md` (cycle 7 of 7 — the queue closes). Lean cycle.
Goal: turn gaffer from a tool you poll into a system that watches for you — price history + tonight's movers, a starred watchlist, two scheduled digests with a local notification, and a real EP-mover retrain diff.

## 0. Decisions

- **D1 — Price source: FPL's own predictor fields, banked daily.** `gaffer prices` is currently stateless stdout over `price_change_percent`/`price_change_calibrating` (official predictor — the third-party feeds are commoditized by it, per the research). v8f: (a) new append-only `data/live/price_log.parquet` (snapshot.py idiom; one row per player per UTC day: code, now_cost, price_change_percent, direction, calibrating, snap_date; idempotent, atomic) appended by the nightly `prices` job and any manual run; (b) `price_alerts` surfaced in the web API at last (schema + types + a "Tonight's movers" card on This Week, watch-set = squad + plan players + watchlist); (c) the CLI keeps its stdout contract.
- **D2 — Watchlist clones the pin pattern.** `reports/watchlist.json` (list of codes + optional note, atomic), `GET/POST/DELETE /api/watchlist`, a star column in the explorer beside the pin column (same button idiom), and watched players join the price-alert watch set and the digest's flagged-players section. No separate alert rules engine this cycle — the digest IS the alert delivery.
- **D3 — Digests are artifacts + cards + a best-effort local notification.** New module `src/gaffer/digest.py`: `friday_briefing(cfg) -> dict` (deadline countdown from events, the advised move + captain from the latest advice, flagged/doubtful players from availability + presser verdicts, tonight's movers from D1, one differential from `alternatives`, staleness warning) and `tuesday_debrief(cfg) -> dict` (the newest reviewed ledger row: lanes + labels + accuracy, hindsight XI gap, league sim p_win movement since last GW, biggest miss). Both: structured JSON to `reports/digest_friday.json` / `reports/digest_tuesday.json` (replace-on-write, atomic), one printed summary line, never raise. Notification: `_notify(title, body)` via `osascript -e 'display notification ...'` — best-effort, swallowed on failure, behind `[digest] notify = true` (macOS-local, no new deps, no external service). CLI `gaffer digest --kind friday|tuesday`; job kinds `digest-friday`/`digest-tuesday` (11th/12th — THREE protected job-kind pins will need the deliberate orchestrator update, 10→12); plists: Friday 17:00, Tuesday 09:30 (after the 09:00 review); installer loop + echo updated.
- **D4 — The retrain diff gets real EP movers.** `save_components` (artifacts.py, unprotected) retains a single predecessor: before overwriting `components_gw{N}.parquet` it copies the existing file to `components_gw{N}_prev.parquet` (bounded, one slot). New `ep_movers(gw, threshold=0.5) -> list` diffs prev vs current per (code, first-gw) EP; `GET /api/advice/diff` payload gains `ep_movers` (additive); the WhyPanel DiffStrip renders "N players moved ≥ 0.5 EP" with the top three named. First run after merge has no prev ⇒ absent, not empty-claimed.
- **D5 — UI.** This Week gains the Digest card (renders whichever digest artifact is newest, DiffStrip `bits[]` prose idiom — no markdown dep) and the Tonight's-movers strip inside it; the explorer gains the star column; DiffStrip extends per D4. No new hubs/tabs.

## 1. Gates (orchestrator-run)

- **G1 (live)** — real runs: `gaffer prices` appends the price log (row count = players; idempotent same-day); `gaffer digest --kind friday` writes the artifact, prints one line, fires (or best-effort-skips) the notification, and the This Week card renders it; `gaffer digest --kind tuesday` reflects the real GW1 ledger row; star a player via the API and see it in the digest's watch section; ep_movers absent-with-honesty on the first post-merge advise, present after a second.
- **G2 (rails)** — `tests/test_v8f_degradation.py`: price log unwritable ⇒ prices still prints, returns None-ish, never raises; watchlist absent/corrupt ⇒ empty, explorer intact; digest with missing inputs (no advice / no ledger / no sim history) ⇒ sections absent, artifact still written, never raises; notify=false ⇒ zero osascript calls (spy); prev-components absent ⇒ ep_movers absent; job-kind pins (12 after the authorized update); protected-ordering pins forward.
- **G3 (suites + audit)** — full suites, tsc, build, zero protected diffs (except the authorized three pin lines).

## 2. Constraints

Protected list as prior cycles; journal.py/backtest.py import-only. The three job-kind count pins (v8b/v8c/v8d rails) go 10→12 via the deliberate orchestrator-authorized update — the plan writes a STOP for it (v8e precedent). Digest jobs must be idempotent (JobRegistry abandon semantics). Never stage data/, reports/, models/, logs/, config.toml. Config: `[digest] notify = true` only.

## 3. Out of scope

Third-party price predictor feeds (official is banked; revisit only if its accuracy disappoints over a season); push beyond the local notification (ntfy/email — user can ask later); alert *rules* engine (thresholded EP-swing alerts etc. — the digest covers the need; rules later if wanted); solver price-timing tiebreaker (needs a season of banked price log to justify; the log starts accruing now); Season-in-Review (May artifact, reads everything this queue banked).

## 4. Outcome

Shipped 2026-08-31 on `feat/gaffer-v8f`. All five decisions landed as designed.

- **D1** — `data/live/price_log.parquet` banks one row per player per UTC day
  (append-only, atomic, idempotent; the snapshot.py idiom). The nightly
  `prices` job and any manual run append; the CLI stdout contract is unchanged.
  `price_alerts` now reaches the web API (schema + types) and the "Tonight's
  movers" card on This Week, over the watch set squad ∪ plan ∪ watchlist.
- **D2** — `reports/watchlist.json` (codes + optional note, atomic) with
  `GET/POST/DELETE /api/watchlist` and a ☆ column in the explorer cloned from
  the pin column. Watched players join the price-alert watch set and the
  digest's flagged section. No rules engine: the digest is the delivery.
- **D3** — `src/gaffer/digest.py` with `friday_briefing(cfg)` and
  `tuesday_debrief(cfg)`, both pure readers over existing artifacts, both
  writing structured JSON (`reports/digest_friday.json` /
  `reports/digest_tuesday.json`, replace-on-write, atomic), printing one line,
  and never raising. `_notify` shells `osascript` with argv (no string
  interpolation) behind `[digest] notify`. CLI `gaffer digest --kind
  friday|tuesday`; job kinds 11 and 12; plists Friday 17:00 and Tuesday 09:30.
- **D4** — `save_components` retains one predecessor as
  `components_gw{N}_prev.parquet`; `ep_movers(gw, threshold=0.5)` diffs prev vs
  current per (code, first-gw) EP; `GET /api/advice/diff` gained `ep_movers`
  additively and the DiffStrip names the top three. Absent — not
  empty-claimed — on the first run after merge.
- **D5** — This Week gained the Digest card (newest artifact wins, DiffStrip
  `bits[]` prose idiom) with the movers strip inside it; explorer gained the
  star column; DiffStrip extended. No new hubs or tabs.

**Review: FIX-FIRST, no blockers.** Four IMPORTANTs, all fixed:

- I1 — `_deadline_bits` parsed the deadline with a guard but then did
  arithmetic on the result unguarded: a NaT deadline produced a NaT countdown
  rather than an absent section.
- I2 — the DigestCard join doubled periods on bits that already ended in one.
- I3 — the differential rendered a raw float instead of the formatted EP.
- I4 — the frontend `Digest` type omitted the `error` field the failure path
  actually writes.

**Live evidence (G1).** `gaffer prices` banked 626 rows and re-running the same
day left the count at 626. Both digests built on real GW1 data, each printing
its line and delivering a macOS notification. A player starred through the
explorer appeared in the movers watch set and in the Friday briefing. `gaffer
advise` reported no movers on the first run (no predecessor) and named five
real movers on the second.

**Residuals / deferred.** Nits, recorded not fixed: N3 the `.tmp` filename in
`save_digest`/`save_watchlist` races between concurrent writers (`os.replace`
keeps each write atomic; pid suffix later); N4 the CLI `prices` path leaves
`price_alerts` unwrapped and `prices.py:27` indexes `price_change_calibrating`
unguarded on a bootstrap missing it; N5 the Friday digest can brief a stale GW
when `latest_gw() != upcoming_gw()` — wants a one-line "run `gaffer advise`"
bit; N6 `ep_movers` loads components twice. Queue-wide residuals still open:
the `llm_classifier` and `lineup_start_floor` serving flips remain
evidence-first decisions for later; the solver price-timing tiebreaker waits on
a season of banked price log (which starts accruing now); Season-in-Review is a
May artifact.

**User action required.** Re-run `scripts/install_automation.sh` to load the
four new plists — `field`, `review`, `digest-friday`, `digest-tuesday`.

## 5. Gate checklist (built by the implementer, run by the orchestrator — filled)

CONVENTIONS.md §7: the implementer builds this and does not run G1. The G3
numbers below were first measured on the branch at Task 10 and are restated
here at the post-review counts (the I1–I4 fix round added tests).

### G3 — suites, types, build, protected audit

```bash
uv run pytest -q
cd frontend && npx tsc --noEmit && npx vitest run && npm run build
```

- [x] Python suite: **2634 passed** (baseline 2468 on `main`; v8f adds 166).
- [x] Frontend: **456 passed, 1 skipped** across 61 files (baseline 441 + 1
      skipped; v8f adds 15).
- [x] `npx tsc --noEmit`: clean. `npm run build`: built, no errors.
- [x] Protected diff — must be empty:

```bash
git diff main --stat -- src/gaffer/advise.py src/gaffer/set_pieces.py \
  'src/gaffer/optimize/**' src/gaffer/web/jobs.py \
  src/gaffer/web/routers/jobs.py src/gaffer/web/routers/whatif.py \
  tests/test_advise.py tests/test_odds.py tests/test_web_jobs.py \
  scripts/s2_replay.py
```

      Measured: **empty**.

- [x] Authorized pin diff — the deliberate updates and nothing else:

```bash
git diff main -- tests/test_v8b_degradation.py tests/test_v8c_degradation.py \
  tests/test_v8d_degradation.py tests/test_v8e_degradation.py \
  tests/test_v8g_degradation.py tests/test_web_job_kinds.py \
  tests/test_web_job_kinds_v8b.py tests/test_web_job_kinds_v8c.py
```

      Measured: six `10 -> 12` job-kind count assertions (the v8b, v8c, v8d,
      v8e and v8g degradation rails plus `test_web_job_kinds_v8b.py`), one
      `47 -> 48` config-key assertion (v8g), and two sorted-list pins gaining
      `digest-friday` / `digest-tuesday` (`test_web_job_kinds.py` and
      `test_web_job_kinds_v8c.py`) — each with its authorising comment, and
      nothing else.

- [x] Security ritual (CONVENTIONS.md §8): `git diff main` greps clean for
      keys, tokens and private-key headers; `git show main:config.toml` fails
      (`path 'config.toml' exists on disk, but not in 'main'`).

### G1 — live runs (real season, not fixtures)

- [x] `gaffer prices` — the alert list prints as it always did;
      `data/live/price_log.parquet` gains one row per player. Run it twice and
      confirm the row count does not double. Measured: **626 rows**, still 626
      after the second same-day run.
- [x] `gaffer digest --kind friday` — writes `reports/digest_friday.json`,
      prints one line, shows (or best-effort-skips) a notification. Open This
      Week and confirm the Digest card renders it. Built on real GW1 data;
      the macOS notification was delivered.
- [x] `gaffer digest --kind tuesday` — reflects the **real** GW1 ledger row,
      with its actual lanes and accuracy, not a placeholder. Notification
      delivered.
- [x] Star a player through the explorer's ☆ button; confirm he appears in
      `GET /api/prices/movers` with `source: "watchlist"` (if he is near a
      threshold) and in the next Friday briefing's flagged section. The starred
      player appeared in the movers watch set and in the briefing.
- [x] `gaffer advise` once: the diff strip says nothing about movers
      (`ep_movers_count` null). Run it again: the strip names the players that
      moved. Measured: absent on the first run, **5 real movers** named on the
      second.
- [ ] `./scripts/install_automation.sh`, then `launchctl list | grep
      com.gaffer` shows seven jobs including the two digests. **Outstanding
      user action** — the four new plists (`field`, `review`, `digest-friday`,
      `digest-tuesday`) load only when the user re-runs the installer.

### G2 — rails

```bash
uv run pytest -q tests/test_v8f_degradation.py
uv run pytest -q tests/test_v6_degradation.py tests/test_v8a_degradation.py \
  tests/test_v8b_degradation.py tests/test_v8c_degradation.py \
  tests/test_v8d_degradation.py tests/test_v8e_degradation.py \
  tests/test_v8g_degradation.py
```

- [x] v8f rails: **23 passed**. Pre-existing rails: **121 passed**.

One adaptation is recorded in that file rather than left as a surprise.
`test_a_corrupt_watchlist_leaves_the_explorer_alone` asserts *invariance*
instead of a 200: `/api/players` answers a clone that has never solved with
its own structured 422 ("no candidate pool yet — run `gaffer advise` first")
whether or not anything is starred, so the rail compares the explorer's answer
before and after the store is corrupted and additionally pins that it never
becomes a 500. Pinning the 200 would have pinned somebody else's contract, and
would have needed a solve state the rail has no business building.
