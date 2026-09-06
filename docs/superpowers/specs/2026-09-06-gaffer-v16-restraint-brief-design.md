# gaffer v16 — restraint and the brief (the ladder picks the rung, an LLM writes the week)

*Brainstormed and approved 2026-09-06 in the terminal, straight after v15
merged. A model-and-application cycle: the transfer ladder's probabilities
choose how many changes to make, a structured note records why the user
deviated, and a grounded LLM brief replaces the template digest. First
cycle since v4c to change which transfers the tool commits to, so it
carries a season replay.*

## 0. Why

The user's words: "I ideally don't want to be making multiple changes every
week unless there's a strategy to it and want to better understand why it's
saying to make said transfer … happy with current state as more of an auto
pilot but want to further develop it into more of a natural advisor and also
maybe better integrate llms". For GW4 they brought in Gibbs-White and Isak
and sold Fernandes and Rice, one hit, against a served plan of three moves
and two hits.

What the tree does today (2026-09-06):

- The solver plans three gameweeks with geometric decay 0.85 and plans
  transfers in every week, but only week one is acted on. A hit costs 4
  objective points and is taken whenever the discounted three-week gain
  beats 4 plus the free transfer's shadow value. With `max_hits` at "no cap"
  (the user's overlay) that pricing is the only brake. There is no notion of
  a strategy across weeks.
- The v13 ladder scores bank / free-transfers-only / 1 / 2 / 3 hits on one
  shared matrix of 2,000 outcome draws. In GW3 it ranked the served two-hit
  plan near the bottom: the single free transfer beat the bank in 79% of
  draws and was the most likely best rung (34%); the served rung was 12%.
  The advice ignored its own ladder.
- Explanation is a per-move accounting trace on the Planning board, a
  per-player component modal, one captain sentence and a template digest.
  The only LLM call is the presser classifier, off by default. The Review
  tab grades the user's actual moves but has nowhere to record why they
  deviated.

## 1. The decisions the user made

1. **Restraint is a policy on the ladder**, not a hit cap or a longer
   horizon.
2. **A written brief first**; the in-app chat is a later cycle once briefs
   have shown the LLM says true things about the artifacts.
3. **The chosen rung becomes the advice everywhere** — This Week, the
   journal, the Review grading, the CLI report — with the objective's own
   plan kept visible beside it.
4. **A structured deviation note**: a reason code from a fixed list plus
   optional text, per gameweek.
5. **Step up only when the step earns it**: from the bank, one rung at a
   time, a step is taken when the higher rung beats the rung below in at
   least `hit_bar` of the shared draws; the walk stops at the first refusal.
6. **Ladder inside advise** (approach 1 of three), one protected diff, a
   season replay as the gate.

## 2. Approach, and the two rejected

**Ladder inside advise (chosen).** Every advise run solves the ladder after
the main solve and the sweep, the restraint walk picks the rung, and the
advice payload's week-one plan is that rung's plan. Journal, Review, the CLI
report and This Week read the payload, so they follow. The brief is a
separate job.

*A post-processor job (rejected).* Advise untouched, a second job rewrites
the banked advice. Two writers of one artifact, the CLI prints the
pre-restraint plan, and a run that dies between the two serves stale advice
as if restrained.

*Restraint in the sweep gate (rejected).* Change `optimize/policy.py`'s
thresholds to use ladder probabilities. Deepest protected change, and it
entangles two mechanisms that answer different questions (noise robustness
vs appetite).

## 3. The restraint rule (`src/gaffer/ladder.py`)

### 3.1 Steps

- Rungs are solved and scored as today: `bank`, `hits0`, `hits1`, `hits2`,
  `hits3`, `open` (kept only when it spends more than three hits), on one
  shared `LADDER_DRAWS = 2000` matrix of outcome draws; duplicate rungs
  collapse, so a step is always between two different plans.
- Restraint walks `RUNG_ORDER` from `bank`. For each adjacent pair of
  *distinct* solved rungs (below, above) it computes
  `share = mean(score_above > score_below)` over the shared draws, on raw
  undecayed horizon points (`horizon_pts`, what the ladder already scores).
- A step is **taken** when `share >= hit_bar`; the walk **stops** at the
  first refused step. The chosen rung is the last one reached. The
  free-transfer step (`bank` → `hits0`) uses the same bar.
- The user's caps bound the walk: a rung above `max_hits` / `max_transfers`
  is never stepped to, whatever the draws say. With the caps at "no cap"
  the walk may reach `hits3` or `open`.

### 3.2 The bar

- New Config field `hit_bar: float = 0.60`, read from `[optimizer]
  hit_bar`, bounds `[0.5, 0.95]` (below 0.5 a step would be taken on a coin
  toss; above 0.95 no step ever passes). Refused by name at config load
  outside the bounds, like `max_hits`.
- Settings whitelist row "Hit bar" (`float`, lo 0.5, hi 0.95, section
  `optimizer`); also editable on the ladder card beside the two caps, which
  writes through `/api/settings` and rebuilds, exactly as the caps do.

### 3.3 Reasons

For every step, taken or refused, one reason string drawn from what the
ladder already has, in this precedence:

1. `flagged`: an extra sell of that step has `p_play < 0.5` in the plan
   gameweek — "Rice is 0% to play".
2. `price`: an extra sell is flagged to fall tonight in the banked price
   log — "van Ewijk is 96% to drop tonight".
3. `fixtures`: the extra buy's mean fixture difficulty over the horizon is
   at least one grade easier than the extra sell's — "Gibbs-White's next
   three average 2.3 against Fernandes's 3.7".
4. `chip`: a chip is planned inside the horizon on the higher rung.
5. `points`: none of the above — "expected points alone".

Reasons are descriptive, never a second gate: the share decides. The brief
reads them; nothing else interprets them.

### 3.4 Output

`reports/ladder_gw{n}.json` gains:

```
bar: float
chosen: str                       # rung key
steps: list[{from, to, share, taken, reason, reason_kind}]
```

and each rung row keeps its full first-week plan (`xi`, `bench`, `captain`,
`vice`, `buys`, `sells`, `hits`, `expected_pts`) so the chosen rung can
supply the advice. The ladder's API function returns the same.

## 4. The advice becomes the chosen rung (`src/gaffer/advise.py`, protected)

- **Order.** After the solve, the sweep and the solve-state save, exactly as
  now, advise calls `build_ladder(gw)` and `restrain(ladder, cfg)`, then
  assembles the payload.
- **The payload's plan is the chosen rung's**: `buys`, `sells`, `hits`,
  `xi`, `bench`, `expected_pts`, `vice`, and `plan_by_gw` for every horizon
  week (each rung is a full horizon solve, so weeks two and three are the
  rung's own, not the objective's). The sweep's modal
  captain stands unless he is not in the rung's XI, in which case the rung's
  captain is used and `captain_note` says "captain from the restrained plan;
  the sweep's choice (X) is not in it". `chip_table`, `strategy`,
  `win_probs`, `price_alerts`, `threats`, `alternatives`, `scenarios`,
  `move_frequencies` are unchanged.
- **Two new payload blocks.**
  `objective`: `{buys, sells, hits, expected_pts}` — the solver's own
  week-one plan. `restraint`: `{chosen, bar, steps, agrees: bool, note}`
  where `agrees` is whether the chosen rung's moves equal the objective's.
- **`raw_optimum_agrees`** keeps its meaning (sweep gate vs deterministic
  optimum); the Sims column keeps showing the sweep frequency for the rung's
  moves, which may be low for a move the sweep rarely made — that is
  information, not a contradiction.
- **Failure.** If no rung solves, or the ladder raises, the payload is the
  objective's plan, `restraint.note` says why, `restraint.chosen` is `null`.
  A ladder fault can never leave the user without advice.
- **The trace follows the served plan.** The solve state is saved before
  the ladder runs and is unchanged; the Planning board's "Why this move"
  trace is computed for the plan the payload serves (the rung's), and the
  objective's moves are traced beside it only when they differ.
- **Journal and Review** grade against the payload's buys/sells and so
  follow without change. `journal.json`'s "model buys" are the rung's.
- **CLI report** prints the chosen rung line ("restraint: 1 free transfer;
  the hit was refused, 46% — expected points alone") and, when the rung
  differs from the objective, one line "the objective wanted: …".
- **Ladder job**: the ladder card's Rebuild still works; a rebuild after
  advise re-walks with the current bar and caps and its `chosen` may differ
  from the served advice, which the card states ("served advice was the
  hits0 rung at bar 0.60; this rebuild at 0.70 chooses bank").

## 5. The deviation note

- **Store.** `reports/decisions.json`, `{gw: {reason, text, at}}`, written
  through `gaffer.io.atomic_write` under a module lock. `reason` is one of
  `REASONS = ("injury", "fixtures", "eye_test", "price", "chip", "rival",
  "gut", "other")`; `text` at most 280 characters, may be empty; `at` UTC
  ISO.
- **Routes.** `GET /api/decisions/{gw}` (404-free: an absent note is `{gw,
  reason: null, text: "", at: null}`), `POST /api/decisions/{gw}` with
  `{reason, text}`; refuses an unknown reason, text over 280, or a `gw`
  later than the next deadline's gameweek, in the settings endpoint's
  `{constraint, error, players}` refusal shape.
- **This Week panel** "What I did and why" under the moves card: a
  `Segmented` of the eight reasons and one input line, a Save button.
  Editable from the advised gameweek's deadline until that gameweek's
  Review grading is banked, then read-only with the grade beside it. Before
  the deadline it shows "opens at the deadline".
- **Review tab**: the transfers lane shows the reason chip and the text
  under the grade. A "by reason" table at the foot: per reason code, count
  and mean `delta_pts` over the season, from the ledger joined to
  `decisions.json`. Rows with no note count under "no note".
- **The brief** quotes the previous gameweek's note beside its grade.

## 6. The brief (`src/gaffer/brief.py`)

### 6.1 Content, in order

1. The chosen rung and every step, taken or refused, with its share and
   reason.
2. The moves, each with its discounted gain from the trace and the sweep's
   frequency.
3. The captain, the sweep's captain frequency, the captain note.
4. The league: focus league, stance (and whether manual), gap, λ.
5. A chip if one is within its threshold in the chip table.
6. Last gameweek's grade per lane, the user's deviation note quoted.
7. Any data warning from the payload.

Six to twelve sentences. Plain prose, no headers, no bullet lists.

### 6.2 Facts document

`build_facts(gw) -> dict`: from `reports/gw{n}-advice.json`,
`ladder_gw{n}.json`, `sensitivity_gw{n}.json`, the trace (computed via the
existing `trace` module from the solve state), `decision_ledger.json`'s
latest row, `decisions.json`. Every number is rounded to the precision the
UI shows (points 1 dp, shares whole percent, λ 2 dp) so the truth check
compares like with like. Player names are the payload's display names.

### 6.3 The call

Through `cfg.news_llm_command` — the same `claude -p --output-format json
--disallowedTools …` no-tools command the classifier uses — with a fixed
prompt (`BRIEF_PROMPT_VERSION = 1`, salted into the cache key) that says:
write the brief from these facts only; use no number and no name that is
not in them; British English; no headers. The cache key is the advice run
stamp + prompt version, under the classifier's cache directory, so a page
rebuild never re-asks. Timeout `cfg.news_llm_timeout_s`.

### 6.4 The truth check (mechanical, before banking)

- Every numeric token in the prose (integers, decimals, percents, signed
  values) must appear in the facts document's rendered values, allowing
  the facts' own rounding and a trailing "%" or "pts".
- Every capitalised token sequence that matches a player-name pattern must
  be a name in the facts.
- A failure bans the brief: nothing is written, `reports/brief_gw{n}.json`
  is absent, the log line names the offending sentence, and the card serves
  the template digest with "the brief did not pass its check this week".

### 6.5 Banking and serving

- `reports/brief_gw{n}.json`: `{gw, run_stamp, prose, facts, model_command,
  prompt_version, checked_at}`.
- `GET /api/brief` → the newest brief or `{gw, prose: null, fallback:
  <digest panel>, note}`.
- **Job kind `brief`** (`run_brief`): started automatically by the web
  `advise` / `advise-fast` job on success (job chaining in `job_kinds.py`),
  and by a button on the card. Never inside `run_advise` itself. A missing
  command, a non-zero exit or a timeout is a finished job with a note, not
  an error.
- **This Week**: `BriefCard` replaces `DigestCard`'s prose when a brief
  exists; the two digest buttons stay. The Friday digest's `headline` is the
  brief's first sentence when a brief exists.

## 7. Gates

- **R1 — season replay.** Three seed bases with `scripts/v7b_replay.py`'s
  multi-seed harness; a `restraint` arm patches `backtest.solve_plan` with
  "solve the rung specs, score the draws, walk the bar, return the chosen
  plan", against the unmodified objective arm. Reported per arm: season
  points, hits taken, transfers made, and the per-seed spread. **Pass:**
  restraint's mean season points are not below the objective's by more than
  the three-seed spread, AND hits taken fall. A fail is reported in the
  spec's final section and the user decides. Bands unavailable in a replay
  week fall back to the ladder's sigma fallback and the count is reported.
- **R2 — the brief on real artifacts.** One real run on the GW3 (or newest)
  artifacts; the truth check passes; the user reads it. Prose wrong in a way
  the check cannot see changes the prompt before merge.
- **R3 — screenshots** through the companion, dark and light: This Week
  (restrained moves, the objective line, the decision panel, the brief
  card), the ladder card with bar and steps, Review with a note beside a
  grade, Settings.

## 8. Pins and protected files

- Config fields 58 → **59** (`hit_bar`). Routes 49 → **51**
  (`/api/decisions/{gw}`, `/api/brief`). Job kinds 12 → **13** (`brief`).
  Each is one number and a docstring line in a protected degradation test,
  edited by the orchestrator only. Approved by the user 2026-09-06.
- `src/gaffer/advise.py`: the block in §4, shown to the user before commit.
- The replay uses `scripts/v7b_replay.py` (unprotected), never
  `scripts/s2_replay.py`.
- No change to `optimize/**`, `set_pieces.py`, `web/jobs.py`,
  `routers/whatif.py`.

## 9. Tests

- `ladder.py`: the walk on synthetic score matrices (take / refuse / stop at
  first refusal / cap bounds / collapsed rung skipped / no rung solved);
  each reason kind in precedence order; output fields.
- Config: `hit_bar` default, bounds, refusal by name; the settings row.
- `advise` assembly: through the existing advise test fixtures (protected
  `tests/test_advise.py` is not edited; a new `tests/test_v16_restraint.py`
  exercises the payload with a stubbed ladder): rung plan replaces week one,
  objective block kept, captain fallback, no-rung fallback.
- Decisions: store round-trip, refusals, the deadline rule, the by-reason
  tally.
- Brief: `build_facts` shape; the truth check on crafted prose (a foreign
  number fails, a rounded fact passes, a foreign name fails); the command
  runner with a fake command (success, non-zero, timeout); the cache;
  the job chain fires once on success and not on failure.
- Frontend: ladder card bar control and steps; This Week objective line,
  decision panel states, BriefCard with prose and with fallback; Review
  note and the by-reason table; tokens rules unchanged.
- Suites end strictly above 4170 Python and 893 frontend, nothing failing.

## 10. Process

Same as v15: spec → plan → branch `v16-restraint` → Opus implementers under
Fable's review → R1 replay run by the orchestrator → R2 → R3 → merge,
security ritual, GUIDE, ROADMAP, memory.

## 11. Out of scope

- The in-app chat (next cycle, gated on briefs read).
- Any change to horizon, decay, `hit_cost`, `ft_value` or the sweep's
  thresholds.
- Reason codes beyond the eight; tallies beyond count and mean points per
  code.
- Notifications beyond the Friday headline.
- A blended league stance (still v15's candidate 9).
