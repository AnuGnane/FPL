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

(Filled at cycle end.)
