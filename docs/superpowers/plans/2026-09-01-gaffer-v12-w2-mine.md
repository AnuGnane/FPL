# Gaffer v12 W2 Implementation Plan — mine what we have

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** read the four logs this project has been accruing for weeks and has
never once scored — the availability snapshot, the presser verdicts riding on
it, the field EO samples and the nightly price predictor — and turn each into a
number with an honest empty state in front of it. Plus one gated feature arm
that rides the next `gaffer train`.

**Architecture:** spec §3 has five items and **four of them are wrong about the
data**. Not wrong in ambition — wrong in a way that changes what the code must
be, and each one was measured rather than assumed:

- **§3.1 flag-latency** works as described, but every snapshot the log holds
  today is stamped with a gameweek whose deadline had *already passed*
  (`availability_log` starts 2026-08-30; GW2's deadline was 2026-08-28). So the
  report needs a **pre-deadline filter** the spec does not mention, and with
  that filter the report is empty today — which is exactly what its own
  14-snapshot gate says (A2).
- **§3.2 presser grading** says the verdict rows are the ones where `source` is
  `llm`. They are not: 160 of the 169 verdict-carrying rows say
  `source = premierinjuries` and 9 say `llm`. Filtering on `source` would grade
  5% of the evidence (A3). And its stated gate — "empty until GW2 is
  `data_checked`" — is **already satisfied** and still yields nothing, for the
  §3.1 reason: no verdict in the log was recorded before its gameweek's
  deadline. The real gate is **GW3** (A3).
- **§3.3 EO trend** cannot happen as written. Three separate reasons, any one
  of them fatal: the scrape's already-banked exit means a second same-gameweek
  sample is **never written** (`field.py:384-400`); post-deadline picks are
  frozen, so a Saturday/Sunday delta would be sampling noise rather than drift;
  and EO is banked in **percent** and can exceed 100 (captaincy doubles it —
  the live log's max is 214.7), so the spec's clamp to `[0, 1]` would zero the
  entire instrument. The honest version measures the trend **across
  gameweeks**, which is the only grain at which field EO moves at all (A4).
- **§3.4 price-timing** is arithmetically sound and, at the shipped
  `itb_value = 0.08`, worth **0.008 points** at its maximum — an order of
  magnitude *below* the solver's own optimality gap on a real horizon. It is a
  tie-breaker, not a term, and the plan says so in the code rather than letting
  a future reader discover it from a replay that shows zero diff (A6).
- **§3.5 xG-per-shot** is under-specified rather than wrong: `us_npxg90` and
  `us_shots90` are **windowed** (`_r3/_r5/_r10/_r38`), so "the feature" is four
  features plus four indicators, and the bar it names ("no other bucket worsens
  by more than its seed-spread") requires K≥3 seed bases by CONVENTIONS §1 —
  which the spec's "gated ablation on the next `train`" does not budget for
  (A7).

**What that adds up to:** W2 is *smaller on the server than it looks* — no new
route, no new job kind, no new Config field, and both new reports ride
`gaffer evaluate` and `/api/quality`, which already exist and are already
disk-only. And it is *larger in two places the spec does not name*: the
pre-deadline filter that both availability reports need, and the fact that
§3.3's reader has to be re-grained before it can be written at all.

**Tech Stack:** Python 3.12, uv, pandas/pyarrow, FastAPI + pydantic, tomllib,
pytest, LightGBM; React 19 + TypeScript + vitest + recharts.

**Branch:** `feat/gaffer-v12`, at `27f7933` (the spec commit). Authoritative
spec: `docs/superpowers/specs/2026-09-01-gaffer-v12-program-design.md`.
Measurement rules: `docs/superpowers/CONVENTIONS.md`.

```bash
git rev-parse --abbrev-ref HEAD      # feat/gaffer-v12
git rev-parse HEAD                   # 27f7933...  (the v12 spec commit)
```

**W2 runs after W1 has merged.** W1 §2.3 makes `season` a **required** keyword
on `latest_field_eo`, adds `[optimizer] top_n` **as a real `Config` field**
and adds the `[backup]` keys
(**program ruling, 2026-09-02: there is no `[solver]` section — every solver
knob lives in the existing `[optimizer]`, key names unchanged**). Every task
below is written against the post-W1 signature `latest_field_eo(gw=None, *,
season)`. Before Task 1, verify:

```bash
grep -n "def latest_field_eo" -A 3 src/gaffer/data/field.py
# expect: season: str  (required keyword, no default) — W1 §2.3
```

If `season` still carries `= None`, **stop and report**: W1 did not land and
Task 8's season guard would be asserting a keyword that is still optional.

**Protected — must show zero diffs at the end (Task 14 audits this):**
`src/gaffer/advise.py`, `src/gaffer/set_pieces.py`, `src/gaffer/optimize/**`,
`src/gaffer/web/jobs.py`, `src/gaffer/web/routers/whatif.py`,
`tests/test_advise.py`, `tests/test_odds.py`, `tests/test_web_jobs.py`,
**every** pre-existing `tests/test_*_degradation.py` — `test_degradation.py`,
v4c, v4d, v5, v6, v7_model, v8a, v8b, v8c, v8d, v8e, v8f, v8g, v9a, v9c, v9d,
v10, v10b, **v11**, and whatever W1 banks — `scripts/s2_replay.py`.

**Import-only:** `src/gaffer/journal.py`, `src/gaffer/backtest.py`. This
workstream imports from neither.

**Exactly one protected edit is authorized in W2, and it is Task 10**
(`src/gaffer/optimize/milp.py`, spec §3.4). Three line-groups, enumerated
there with before/after. It is a **STOP**: it does not run until the
orchestrator has read the enumeration and authorized it. Four other candidates
looked protected and are not:

1. §3.4's price-fall data looks like it belongs on `SolveInput` and therefore
   in every caller — including `advise.py`, which is protected. It does not:
   `solve_plan` reads it itself from an unprotected seam, the way
   `serving_config` exists for exactly this problem (A6).
2. §3.5's feature looks like an `advise.py` change, because `advise.py` names
   the columns it carries to serve time. It is not: `attach_understat`
   (`train.py:203`) is the single seam both the training frame and the
   prediction frame pass through, and `train.py` is unprotected (A7).
3. §3.3's `deadline_eo` looks like it belongs in `advise.py` beside the
   captain. It does not: `web/field_frame.py` is the serve-time decoration
   that already frames the captain against the field, and it is unprotected
   (A5).
4. Both new reports look like they need a route. They do not: `/api/quality`
   already serves whatever keys `reports/evaluation.json` holds, and the
   report writer is `save_evaluation` (A1).

**If a task nonetheless concludes a further protected edit is required, it
STOPs and reports rather than widening the diff.**

**Staging rule:** every `git add` below names exact files. Never `git add -A`.
Never stage `data/`, `reports/`, `models/`, `logs/`, `.claude/`, `config.toml`
or `src/gaffer/web/static/`.

**Gate rule (CONVENTIONS §7):** implementers build the drivers and never run
them. Task 12 builds the arm driver and does not launch it; Task 14 is the
checklist with G1/G2 unfilled.

**Frontend test runner: `npx vitest run`.** `npm test` maps to bare `vitest`,
which is watch mode, and it hangs an agent forever.

**Python: `.venv/bin/pytest` / `.venv/bin/python`.** There is no bare `python`
on PATH.

**Pins, measured at `27f7933`:**

| Pin | Value at `27f7933` | after W2 |
| --- | --- | --- |
| `len(JOB_KINDS)` | 12 | **12** — both reports are `gaffer evaluate` flags, and `JOB_KINDS` maps a kind to a **zero-argument** callable, so a flag cannot become a job (the `calibration` precedent, `evaluation.py:562-566`) |
| `len(dataclasses.fields(Config))` | 48 | **unchanged by W2** — W1 §2.6 makes `top_n` a field, so the number at W2's base is expected to be **49**; W2 adds none on top, because both its keys are module-level readers (A8) |
| `len(create_app().openapi()["paths"])` | 45 | **45** — no new route; both reports ride `/api/quality`, `deadline_eo` is an additive field |

```bash
# how all three were measured; re-run before Task 1 and stop if any has moved
.venv/bin/python -c "
import os, tempfile, dataclasses
os.chdir(tempfile.mkdtemp())
from gaffer.web.app import create_app
from gaffer.web.job_kinds import JOB_KINDS
from gaffer.config import Config
print(len(create_app().openapi()['paths']), len(JOB_KINDS),
      len(dataclasses.fields(Config)))"
# 45 12 48   (W1 may have moved the first and third — see below)
```

**W1 has legitimately moved two of these**, and that is not a failure: §2.9
adds `/api/meta/freshness` (routes → 46) and §2.6 makes `top_n` a real
`Config` field splatted from `[optimizer]` (fields → 49). **Re-measure at W2's
actual base commit and write the numbers into this table before Task 1.** What W2 asserts is not an absolute count — the
v11 route-pin restructure put the absolute route pin in
`tests/test_v11_degradation.py` and nowhere else, and that stays true. W2's
degradation file makes **absence claims** instead (Task 7).

**Suite baselines (ROADMAP, after v11: 3193 Python + 655 frontend).**
Re-measure at W2's base and write both numbers here, because every task's
final run is judged against them:

```bash
.venv/bin/pytest -q --collect-only | tail -1     # record: <N> tests collected
cd frontend && npx vitest run                    # record: <N> passed, N skipped
```

**Commit trailer — every commit:**

```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
```

---

## What the spec got wrong, what was measured, and how this plan settles it

Nine. Five of them change what gets built.

### A1 — neither report gets a file of its own, and neither gets a route

Spec §3.1 says the CLI "writes the same payload to
`reports/evaluate/flag_latency.json`". No such directory exists and nothing
would read it. The tree's standing pattern is one artifact with independent
keys: `save_evaluation(key, payload)` merges into `reports/evaluation.json`
(`evaluation.py:246-264`) through a temp file and `os.replace`, with
`allow_nan=False` so a NaN cannot produce a valid-looking artifact that 500s
`/api/quality` three weeks later. `GET /api/quality` then serves whatever keys
`Quality` declares (`routers/quality.py:32-48`), disk-only, no re-run.

**Settled: `save_evaluation("flag_latency", …)` and
`save_evaluation("presser_grades", …)`, two additive optional fields on
`Quality`, no new route and no new file.** Three reasons: the atomic-write and
NaN discipline already exists and would have to be re-implemented for a second
path; `/api/quality` is where the Model → Quality page already looks; and a
new route would move the pin the v11 restructure just finished consolidating.

The deviation from the spec's literal path is recorded in the README line
(Task 13).

### A2 — every snapshot in the log postdates its gameweek's deadline, so both reports need a pre-deadline filter the spec does not mention

Measured on 2026-09-01:

| gw | snap_date | rows | that gw's deadline |
| --- | --- | --- | --- |
| 2 | 2026-08-30 | 623 | 2026-08-28T17:30Z |
| 2 | 2026-08-31 | 626 | 2026-08-28T17:30Z |
| 3 | 2026-09-01 | 629 | 2026-09-04T17:30Z |

1878 rows, three dates. The gameweek stamped on a snapshot is
`next_unfinished_gw` (`snapshot.py:45-57`) — *the first gameweek not yet
finished* — and its docstring says why: a Saturday-evening snapshot still
belongs to that gameweek's news cycle. That is right for the news cycle and
wrong for latency: on 2026-08-30, GW2's deadline was two days gone, so "days
between the flag and the deadline" is **negative**.

**Settled: both reports filter to snapshots at or before their gameweek's
deadline, from `data/live/events.parquet`'s `deadline_time`, before anything
else happens.** A snapshot with no readable deadline for its gameweek is
dropped, not defaulted — a guessed deadline manufactures a lead time.

The consequence has to be stated rather than discovered on the page: **with
that filter, both reports are empty on today's log.** GW2's snapshots are all
post-deadline; GW3's single snapshot is pre-deadline but GW3 is not
`data_checked`. That is not a defect, it is the instrument reading zero, and
§3.1's own 14-date gate says the same thing in a different unit.

### A3 — the verdict rows are not the `llm` rows, and the gate is GW3 rather than GW2

Spec §3.2 says "for each row with a non-null `llm_verdict` (`source` is
`llm`…)". Both halves cannot be true at once. Measured:

| `source` | rows | rows with a verdict |
| --- | --- | --- |
| *(null)* | 965 | 0 |
| `lineups` | 673 | 0 |
| `premierinjuries` | 231 | **160** |
| `llm` | 9 | 9 |

`source` names *which news source produced the row*; the classifier's verdict
rides along on whatever row it was asked about. Filtering `source == "llm"`
grades 9 rows out of 169.

**Settled: the population is `llm_verdict.notna()`, full stop, and `source`
travels into the payload as a breakdown rather than as a filter.** The four
classes present are the four the spec names — `ruled_out` (110+9),
`assess` (34), `knock` (12), `rotation_risk` (4) — but the scorer reads the
classes **off the data**, sorted, rather than from a hard-coded tuple: a fifth
class arriving from a prompt change must show up as a row, not vanish.

**And the gate the spec names is already met and still yields nothing.** GW2 is
`data_checked` today — `data/live/player_gw.parquet` holds 626 GW2 rows,
19,723 minutes, and `review.py:140` says presence in that file *is* the
`data_checked` gate. The report is nevertheless empty, because of A2: every
GW2 verdict was recorded after GW2's deadline. **The honest gate is a
`data_checked` gameweek with at least one pre-deadline verdict, which today
means GW3.** The ROADMAP checkbox says GW3 (Task 13).

### A4 — §3.3 cannot be built at the day grain, for three independent reasons, and the honest grain is the gameweek

Measured: `data/live/field_eo_log.parquet` holds **123 rows, one gameweek
(GW2), one snap_date (2026-08-31)**.

1. **The collector never writes a second sample for one gameweek.**
   `run_field_scrape` checks `_already_banked` (`field.py:384-400`) *before it
   builds a client at all*, and returns 0. The Sunday plist fires
   (`scripts/com.gaffer.field.plist`, Weekday 6 and 0 at 12:30) and takes that
   exit every week the Saturday run worked — the docstring at `field.py:360`
   says so in as many words. So `append_field_eo`'s `(gw, snap_date)` key,
   which *could* hold two days, in practice holds one.
2. **Even with two, the delta would be sampling noise.** The scrape is
   deliberately post-deadline — picks 404 before it (`field.py:280-291`) — and
   post-deadline picks are frozen. Two samples of one locked gameweek differ
   only because ~300 entries were drawn twice. Extrapolating that difference
   toward a deadline is amplifying noise and calling it drift.
3. **The units are percent, not fraction, and the ceiling is not 1.0.**
   `eo_from_picks` returns `total / n * 100` with captaincy counted double
   (`tier_eo.py:154-179`), so the live log's maximum today is **214.7**. The
   spec's "clamped to [0, 1]" would floor the entire instrument to 1.0.

There is also a fourth fact that decides the grain: **the field's ownership of
the *upcoming* gameweek is not observable before its deadline.** Nobody's
picks are public until the deadline passes. So a "deadline EO" can only ever
be an extrapolation from one gameweek's observed EO to the next — which is
exactly the quantity that *does* move, week to week, as the field transfers.

**Settled: `field_eo_trend(season, gw)` compares the latest sample of `gw`
against the latest sample of the newest *earlier* gameweek in the log**, and
returns per code `eo_first`, `eo_last`, `delta`, `gws_between` and
`trend_available`. `deadline_eo = clip(eo_last + delta / gws_between, 0.0,
200.0)` — one gameweek forward, in percent, clamped at the ceiling the
sampler can actually produce (a doubled captain; a triple-captained one is a
handful of entries and cannot carry the aggregate past 200 in any sample this
project has taken). With fewer than two gameweeks in the log,
`trend_available=False`, `deadline_eo == eo_last`, and nothing on the page
draws an arrow.

The spec's field names are kept wherever they still mean the same thing, and
`hours_between` is **not** kept: `snap_date` is a date string with no clock in
it (`snapshot.py:36-42`), so an hours figure would be three fabricated
significant digits.

**Today's log therefore reports `trend_available=False` for every code, and
after the next weekend's scrape it reports a real trend for the first time.**
That is the honest state and the ROADMAP records it as data-gated (Task 13).

**This is the largest deviation in the plan and the orchestrator should read
it before Task 8 runs.** The day-grained alternative is implementable in the
same function shape — it is one predicate — and the plan is written so that
switching back is a change to `_pair_samples` and nothing else.

### A5 — `deadline_eo` reaches the page through the two serve-time seams that already read the EO log, and neither is protected

`latest_field_eo` has exactly two readers: `routers/players.py:149` (the
explorer's `Field%` column, which `ComparePanel.tsx:272-293` also renders with
its ±SE) and `web/field_frame.py:196` (the captain framing, whose whole reason
for existing is that `advise.py` is protected — `field_frame.py:1-16`).

**Settled: the trend rides both, as additive optional fields, and the advice
artifact's bytes never change.** `PlayerRow` gains `field_eo_deadline` and
`field_eo_delta`; `captain_field` gains the same two keys. Both are `None`
when there is no trend, never `0.0` — `schemas.py:406-412`'s standing contract
for this exact column, and a delta of zero is a real and different statement
("the field did not move on him").

### A6 — §3.4's term is worth 0.008 points and sits inside the solver's own optimality gap

The objective already prices money: `obj.append((itb_value / 10.0) *
bank[T[-1]])` (`milp.py:661`), where `bank` is in tenths of a million. So one
0.1m of bank is worth `itb_value / 10` points, and the spec's charge —
`p_fall × 0.1 × itb_value` — is *exactly* the value of the 0.1m a falling
player's sale loses. Internally consistent, and at the shipped
`itb_value = 0.08` (`config.example.toml:11`) worth **0.008 points at
p_fall = 1.0**.

`_solve` uses HiGHS with default settings (`milp.py:714-725`), whose default
relative MIP gap is 1e-4. On a three-week horizon the objective runs to a few
hundred points, so the solver is entitled to stop 0.02 points short of
optimal — **two and a half times the largest charge this term can levy.**

**Settled: the term ships exactly as specified but with its flag defaulting
off** (coordinator ruling, 2026-09-02 — CONVENTIONS §6: an arm that cannot
demonstrate an effect ships behind its flag, with the negative recorded rather
than the code deleted), **and the solver's gap is not touched.** The flip rule
is pre-registered in the W2 gate (Task 14, G1d) rather than decided after the
replay numbers are in, which is CONVENTIONS §2. Tightening the gap
would change every solve in the tree to make one epsilon decidable, which is a
far larger intervention than the term it serves. The consequences are stated
rather than hidden:

- the replay gate (tolerance 5) is expected to show **no diff at all**, and
  that is the *predicted* outcome, not a pass by luck;
- the unit test asserts the **coefficient** on the built problem, which is
  exact and gap-free;
- the behavioural test sets `itb_value = 5.0` in its own fixture so the charge
  is 0.5 points and the solver must respect it. That is a legitimate test of
  the mechanism at a knob setting the user could choose, and the test says so.

No term for rises: the ROADMAP's rejected list opens with "price-change
chasing" and spec §8 repeats it.

### A7 — §3.5 is four features and four indicators, and its bar needs three seed bases

`us_npxg90` and `us_shots90` do not exist as columns. What exists is
`us_npxg90_r{w}` and `us_shots90_r{w}` for `w in [3, 5, 10, 38]`
(`engineer.py:857-879`), both per-90 rates over the same window, so their
ratio is genuinely non-penalty xG per shot at that window.

**Settled: `XG_PER_SHOT_FEATURES` is eight columns — `us_npxg_per_shot_r{w}`
and `us_npxg_per_shot_missing_r{w}` for the four windows** — built in one
place, `attach_understat` (`train.py:203-235`), which both `load_training_frame`
and the prediction frame pass through. The columns are always built, like the
withdrawn v8a arms' builders (`train.py:100-103`: "the columns cost a fit
nothing"); only whether the *attacking model is told about them* is gated.

The bar the spec pre-registers — "the hauler bucket RMSE improves and no other
bucket worsens by more than its seed-spread" — names a seed-spread, and
CONVENTIONS §1 says a spread is measured over **K ≥ 3 seed bases** whose runs
differ in nothing but the seed. `AttackingModel` already takes a `seed`
(`attacking.py:42-52`). So the driver is a 3-seed × 2-arm matrix: six fits,
not one, and that is a bigger `train` than "rides on the next one".

### A8 — neither new config key can be a `Config` field, and the tree already has the pattern

`len(dataclasses.fields(Config)) == 48` is asserted at `27f7933` in **four
protected degradation files** (`test_v9c:323`, `test_v9d:421`, `test_v10:422`,
`test_v10b:266`) and in the unprotected `test_v10_config_providers.py:86`,
whose module docstring records the whole argument. `config.py:221-248`'s
`lineup_providers` is the shipped answer: a module-level reader that parses
`config.toml` itself, never raises, and returns the shipped default on a
missing file, a missing section or corrupt TOML.

**W1 §2.6 pays that toll once, for `top_n`** (amended plan, 2026-09-02): it is
a real `Config` field with a `default_factory`, splatted out of `[optimizer]`
and read through `optimizer_top_n()`, so the count is **49** at W2's base and
W1 owns whatever it did to the four protected pins. That does not make a
second field free. W2's two knobs are a flag nobody sets by default and a
training arm that is off until it clears a gate, and moving a pin that four
protected files assert — twice in one program, for those — is not a trade this
workstream is entitled to make.

**Settled: `price_timing(path="config.toml") -> bool` and
`xg_per_shot(path="config.toml") -> bool` are module-level readers in
`config.py`, following `lineup_providers` verbatim in shape.**

**And the program ruling of 2026-09-02 — no `[solver]` section, every solver
knob in the existing `[optimizer]` — puts a live grenade under that, which the
first draft of this plan did not have to defuse.** `load_config` does
`**raw.get("optimizer", {})` (`config.py:146`), so **every key under
`[optimizer]` is splatted straight into the `Config` constructor**. A
`price_timing` line there is not inert: it is
`TypeError: Config.__init__() got an unexpected keyword argument
'price_timing'` on the next `gaffer advise`, for anyone who copies the new
`config.example.toml`. `[model]` and `[backup]` are untouched by this —
neither is splatted — and `[news]`, `[league]`, `[scenarios]` and `[odds]` are
read key-by-key for precisely this reason.

**So Task 10 adds one more edit to `config.py`: the named non-field
`[optimizer]` keys are popped before the splat.** A named tuple rather than a
`fields(Config)` filter, because the loud failure on a *typo* under
`[optimizer]` is a feature worth keeping — a filter would swallow
`horizen = 6` in silence, and a mistyped horizon is a season of quietly wrong
advice.

**The tuple has exactly one entry, `price_timing`, and `top_n` is deliberately
not the second.** `top_n` *is* a field after W1; popping it would strip a
configured pool size out of the constructor and hand every user the dataclass
default, silently, because a smaller pool still solves. The invariant is
mechanical and Task 10 asserts it: **no name in `NON_FIELD_OPTIMIZER_KEYS` is
also a `Config` field.**

`price_timing` defaults **false** (coordinator ruling, 2026-09-02: CONVENTIONS
§6 beats spec §3.4's `true` — a term that cannot demonstrate an effect ships
off behind its flag, with a pre-registered rule for flipping it on: see Task
14's G1d). `xg_per_shot` defaults **false**, as spec §3.5 says, and stays
false unless the arm clears.

### A9 — the reports go on the Quality tab beside the news-shadow section, in its shape

`QualityTab.tsx:470-520` renders `NewsShadowSection` — a `Card` with a
verdict sentence in a bordered callout, a table inside `overflow-x-auto`, and
paired bars scaled per row. It is rendered only when `data.news_shadow &&
data.news_shadow.rows > 0` (`:851-852`), which means a fresh clone sees
nothing rather than an empty card.

**Settled: one `Card title="Availability signal"` holding both reports, and it
renders whenever the key is present — including when it is empty.** That is
deliberately *not* the news-shadow rule, and spec §1 is the reason: an empty
state must say what it is waiting for and when it will exist. The card
therefore prints, e.g., "3 of 14 snapshot days, and no covered gameweek is
data_checked yet" rather than not existing. `rows > 0` remains the gate on the
*tables*; the card and its sentence are unconditional.

---

## File map

| File | Create/Modify | Task |
| --- | --- | --- |
| `src/gaffer/evaluation.py` | Modify (`:532-559`, new `news_actuals`) | T1 |
| `src/gaffer/availability_eval.py` | **Create** | T1, T2, T3, T4 |
| `src/gaffer/cli.py` | Modify (`:528-568`) | T4 |
| `src/gaffer/web/schemas.py` | Modify (`:952-960`) | T5 |
| `src/gaffer/data/field.py` | Modify (append) | T8 |
| `src/gaffer/web/routers/players.py` | Modify (`:149`, `:161-176`) | T9 |
| `src/gaffer/web/field_frame.py` | Modify (`:236-284`) | T9 |
| `src/gaffer/config.py` | Modify (append two readers) | T10, T11 |
| `src/gaffer/price_timing.py` | **Create** | T10 |
| `src/gaffer/optimize/milp.py` | **Modify — PROTECTED (STOP)** | T10 |
| `src/gaffer/features/engineer.py` | Modify (`:840-880`) | T11 |
| `src/gaffer/models/train.py` | Modify (`:232`, `:491`) | T11 |
| `scripts/v12_xgps_arm.py` | **Create** | T12 |
| `config.example.toml` | Modify | T10, T11 |
| `frontend/src/types.ts` | Modify (`:559`, `:720`) | T6, T9 |
| `frontend/src/hubs/model/QualityTab.tsx` | Modify (`:845-856`) | T6 |
| `frontend/src/hubs/Players.tsx` | Modify (`:159-167`) | T9 |
| `tests/test_v12_actuals.py` | Create | T1 |
| `tests/test_v12_flag_latency.py` | Create | T2 |
| `tests/test_v12_presser_grades.py` | Create | T3 |
| `tests/test_v12_availability_cli.py` | Create | T4 |
| `tests/test_v12_quality_availability.py` | Create | T5 |
| `tests/test_v12_w2_degradation.py` | Create | T7, T14 |
| `tests/test_v12_field_eo_trend.py` | Create | T8 |
| `tests/test_v12_deadline_eo_api.py` | Create | T9 |
| `tests/test_v12_price_timing.py` | Create | T10 |
| `tests/test_v12_xg_per_shot.py` | Create | T11 |
| `frontend/src/hubs/model/QualityTab.test.tsx` | Modify | T6 |
| `frontend/src/hubs/Players.test.tsx` | Modify | T9 |
| `README.md` | Modify | T13 |
| `docs/superpowers/ROADMAP.md` | Modify | T13 |
| `docs/superpowers/specs/2026-09-01-gaffer-v12-program-design.md` | Modify (§3, W2 gate) | T13, T14 |

---

## Task 1 — one actuals loader, one deadline table, one coverage answer

**Files:**
- Modify `src/gaffer/evaluation.py` (extract `news_actuals` out of
  `evaluate_news_shadow`, `:546-559`)
- Create `src/gaffer/availability_eval.py`
- Create `tests/test_v12_actuals.py`

**Read A2 and A3 before starting.** Everything both reports do that is hard is
in this task: which rows are truth, which gameweeks count as graded, and which
snapshots are allowed to speak.

- [ ] **Write the failing test.** Create `tests/test_v12_actuals.py`:

```python
"""The three shared readers both availability reports stand on.

``news_actuals`` is lifted out of ``evaluate_news_shadow`` unchanged — spec
§3.2 says the presser report shares that loader, and sharing a loader means
one function, not two copies that agree today.

``deadlines`` and ``pre_deadline`` are the pair the spec does not mention and
neither report can do without. The availability log stamps each snapshot with
``next_unfinished_gw`` — the first gameweek not yet *finished* — so a Saturday
evening snapshot of a gameweek in play carries that gameweek's number even
though its deadline is two days gone. Measured on the live log: every GW2 row
is dated 2026-08-30 or 2026-08-31 against a deadline of 2026-08-28. "Days
before the deadline" over those rows is a negative number, and a histogram of
negative lead times is not a late flag, it is a category error.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer import availability_eval as ae


@pytest.fixture()
def events():
    return pd.DataFrame({
        "gw": [1, 2, 3],
        "deadline_time": ["2026-08-21T17:30:00Z", "2026-08-28T17:30:00Z",
                          "2026-09-04T17:30:00Z"],
    })


def test_deadlines_are_utc_timestamps_keyed_by_gameweek(events):
    out = ae.deadlines(events)
    assert out[2] == pd.Timestamp("2026-08-28T17:30:00Z")
    assert set(out) == {1, 2, 3}


def test_a_gameweek_with_an_unreadable_deadline_is_absent_not_guessed(events):
    """A guessed deadline manufactures a lead time out of nothing."""
    broken = events.assign(deadline_time=["2026-08-21T17:30:00Z", "soon",
                                          None])
    assert set(ae.deadlines(broken)) == {1}


def test_deadlines_of_a_frame_without_the_column_is_empty(events):
    assert ae.deadlines(events.drop(columns=["deadline_time"])) == {}
    assert ae.deadlines(pd.DataFrame()) == {}


def test_pre_deadline_keeps_only_snapshots_at_or_before_the_deadline(events):
    log = pd.DataFrame({
        "season": ["2026-27"] * 4,
        "gw": [2, 2, 2, 3],
        "snap_date": ["2026-08-26", "2026-08-28", "2026-08-30", "2026-09-01"],
        "code": [1, 1, 1, 1],
    })
    kept = ae.pre_deadline(log, ae.deadlines(events))
    assert list(kept["snap_date"]) == ["2026-08-26", "2026-08-28",
                                       "2026-09-01"]


def test_pre_deadline_computes_lead_days_from_midnight_utc(events):
    """``snap_date`` is a date with no clock in it, so the day is taken at
    00:00 UTC and the figure is the calendar distance to the deadline. Two
    decimals, because the deadline's own 17:30 is real and dropping it would
    make a Friday flag and a Thursday one the same number."""
    log = pd.DataFrame({"season": ["2026-27"], "gw": [2],
                        "snap_date": ["2026-08-26"], "code": [1]})
    kept = ae.pre_deadline(log, ae.deadlines(events))
    assert kept["lead_days"].iloc[0] == pytest.approx(2.73, abs=0.01)


def test_pre_deadline_drops_a_gameweek_with_no_deadline_at_all(events):
    log = pd.DataFrame({"season": ["2026-27"], "gw": [9],
                        "snap_date": ["2026-08-26"], "code": [1]})
    assert ae.pre_deadline(log, ae.deadlines(events)).empty


def test_checked_gws_is_presence_in_the_results_file():
    """``review.py:140``: presence in ``player_gw.parquet`` *is* the
    ``data_checked`` gate. Not a flag on the events frame — FPL sets that one
    late, and the results are the thing both reports actually join to."""
    actuals = pd.DataFrame({"gw": [1, 1, 2], "code": [1, 2, 1],
                            "minutes": [90, 0, 45]})
    assert ae.checked_gws(actuals) == {1, 2}
    assert ae.checked_gws(pd.DataFrame(columns=["gw"])) == set()
    assert ae.checked_gws(None) == set()


def test_news_actuals_reads_the_results_parquet(monkeypatch):
    from gaffer import evaluation
    from gaffer.data import store as store_mod

    frame = pd.DataFrame({"gw": [2], "code": [7], "minutes": [90]})
    monkeypatch.setattr(store_mod, "exists",
                        lambda p: p == "live/player_gw.parquet")
    monkeypatch.setattr(store_mod, "load", lambda p: frame)
    assert evaluation.news_actuals()["minutes"].iloc[0] == 90


def test_news_actuals_with_no_file_is_an_empty_frame_with_the_join_keys(
        monkeypatch):
    from gaffer import evaluation
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "exists", lambda p: False)
    out = evaluation.news_actuals()
    assert out.empty
    assert {"gw", "code", "minutes"} <= set(out.columns)
```

Run it: `.venv/bin/pytest -q tests/test_v12_actuals.py` — fails at import,
`ModuleNotFoundError: gaffer.availability_eval`.

- [ ] **Implement the extraction.** In `src/gaffer/evaluation.py`, above
`evaluate_news_shadow` (`:532`), add:

```python
ACTUALS_PATH = "live/player_gw.parquet"
"""This season's played rows. Carries no ``season`` column, which is why
:func:`evaluate_news_shadow` cuts the *log* to one season before joining."""

ACTUALS_COLS = ["gw", "code", "minutes"]


def news_actuals() -> pd.DataFrame:
    """The results frame every availability report is graded against.

    Lifted out of :func:`evaluate_news_shadow` so v12 §3.1 and §3.2 grade
    against the same rows this gate has always used, rather than against a
    second reader that agrees with it until the day it does not.

    An empty frame carries the join keys, so a caller may merge on them
    without checking first.
    """
    from gaffer.data import store

    if not store.exists(ACTUALS_PATH):
        return pd.DataFrame(columns=ACTUALS_COLS)
    return store.load(ACTUALS_PATH)
```

and replace the loader inside `evaluate_news_shadow` (`:549-551`):

```python
    actuals = news_actuals()
```

The local `from gaffer.data import store` at `:546` becomes unused for that
purpose but is still needed by nothing else in the function — delete it and
keep `from gaffer.news_shadow import load_shadow`.

- [ ] **Implement the new module.** Create `src/gaffer/availability_eval.py`:

```python
"""Grading the availability layer's *inputs*: flags, and the verdicts on them.

``gaffer.news_shadow`` grades what the news layer did to a probability. This
module grades the layer's raw material, out of the log ``gaffer snapshot`` has
been banking every day since v7c and nothing has ever read:

* **flag latency** (spec §3.1) — how much warning a status change gave before
  the deadline, and whether the player then started;
* **presser verdicts** (spec §3.2) — the classifier's four classes against
  what happened.

Both stand on the same three facts and the middle one is the one the spec
missed. The log stamps every snapshot with ``next_unfinished_gw`` — the first
gameweek not yet *finished* (``snapshot.py:45-57``) — so a snapshot taken
while a gameweek is being played carries that gameweek's number with its
deadline already behind it. A lead time computed over those rows is negative.
Every row therefore passes :func:`pre_deadline` first, and a gameweek whose
deadline is unreadable contributes nothing rather than a guess.

Nothing here raises for a caller that is a report: a missing log, a missing
results file and an events frame with no deadlines each produce a well-formed
payload with ``available: false`` and a sentence saying what is missing.
"""

from __future__ import annotations

import pandas as pd

from gaffer.evaluation import git_sha, news_actuals, run_at

MIN_SNAP_DATES = 14
"""Spec §3.1's first gate. Fourteen days is two full news cycles, which is the
shortest stretch over which "how much warning" is a distribution rather than
an anecdote."""


def deadlines(events: pd.DataFrame | None) -> dict[int, pd.Timestamp]:
    """``{gw: deadline}`` in UTC, for the gameweeks that have a readable one.

    A gameweek whose deadline will not parse is **absent**, not defaulted. The
    only use of this map is to decide whether a snapshot came in time, and a
    guessed deadline answers that question by inventing the answer.
    """
    if events is None or not isinstance(events, pd.DataFrame) \
            or events.empty or "deadline_time" not in events.columns:
        return {}
    gws = pd.to_numeric(events["gw"], errors="coerce")
    when = pd.to_datetime(events["deadline_time"], errors="coerce", utc=True)
    return {int(g): w for g, w in zip(gws, when)
            if pd.notna(g) and pd.notna(w)}


def pre_deadline(log: pd.DataFrame,
                 by_gw: dict[int, pd.Timestamp]) -> pd.DataFrame:
    """``log`` cut to snapshots taken at or before their gameweek's deadline,
    with ``lead_days`` attached.

    ``snap_date`` is a date string with no clock in it (``snapshot.py:36-42``),
    so the snapshot is taken at 00:00 UTC of that day. The deadline keeps its
    own time — 17:30 on most Fridays — because dropping it would make a
    Thursday flag and a Friday one the same number.
    """
    if log is None or log.empty:
        return log if log is not None else pd.DataFrame()
    out = log.copy()
    out["gw"] = pd.to_numeric(out["gw"], errors="coerce")
    out["_deadline"] = out["gw"].map(by_gw)
    out["_taken"] = pd.to_datetime(out["snap_date"], errors="coerce", utc=True)
    out = out[out["_deadline"].notna() & out["_taken"].notna()]
    out = out[out["_taken"] <= out["_deadline"]]
    if out.empty:
        return out.drop(columns=["_deadline", "_taken"])
    out["lead_days"] = ((out["_deadline"] - out["_taken"])
                        .dt.total_seconds() / 86400.0).round(2)
    out["gw"] = out["gw"].astype("int64")
    return out.drop(columns=["_deadline", "_taken"])


def checked_gws(actuals: pd.DataFrame | None) -> set[int]:
    """The gameweeks FPL has marked ``data_checked``, read the way the rest of
    the tree reads it: presence in the results frame (``review.py:140``).

    Not the events frame's flag. ``refresh_live`` drops every gameweek that
    flag is false for, so the results file *is* the flag, and reading the flag
    separately would let the two disagree about a gameweek mid-refresh.
    """
    if actuals is None or not isinstance(actuals, pd.DataFrame) \
            or actuals.empty or "gw" not in actuals.columns:
        return set()
    gws = pd.to_numeric(actuals["gw"], errors="coerce").dropna()
    return {int(g) for g in gws.unique()}


def _empty(kind: str, note: str, **extra) -> dict:
    """A well-formed payload with nothing in it and a sentence saying why.

    Spec §1: a view whose data does not exist yet says what it is waiting for.
    The sentence is built here rather than in the UI so the CLI, the API and
    the page all say the same thing.
    """
    return {"run_at": run_at(), "git_sha": git_sha(), "kind": kind,
            "available": False, "rows": 0, "note": note, **extra}
```

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_actuals.py tests/test_news_shadow.py
.venv/bin/pytest -q
```

Any news-shadow test that fails means the extraction was not behaviour-neutral:
**stop and report**.

- [ ] **Commit.**

```bash
git add src/gaffer/evaluation.py src/gaffer/availability_eval.py \
  tests/test_v12_actuals.py && git commit -m "$(cat <<'EOF'
feat: the shared readers both availability reports stand on

news_actuals is lifted out of evaluate_news_shadow rather than copied, because
spec §3.2 says the presser report shares that loader and sharing means one
function.

The pair the spec does not mention is the one neither report can do without.
The availability log stamps each snapshot with next_unfinished_gw — the first
gameweek not yet finished — so a snapshot taken while a gameweek is being
played carries that gameweek's number with its deadline already behind it.
Measured on the live log: every GW2 row is dated 2026-08-30 or 08-31 against a
deadline of 08-28. Both reports therefore filter to snapshots at or before the
deadline, and a gameweek whose deadline will not parse contributes nothing
rather than a guessed lead time.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 2 — the flag-latency scorer

**Files:**
- Modify `src/gaffer/availability_eval.py`
- Create `tests/test_v12_flag_latency.py`

**Read A2.** This is spec §3.1's arithmetic and nothing else: no I/O, no
config, one pure function over three frames.

- [ ] **Write the failing test.** Create `tests/test_v12_flag_latency.py`:

```python
"""Spec §3.1: how much warning a status change gave, and what happened next.

The unit is a (gw, code) whose status changed at least once in the
pre-deadline window. Its lead time is measured from the *first* change — the
first moment the log said something other than what it had been saying —
because that is the first moment a manager could have acted.

The outcome is "did he start", from ``evaluation.start_truth``, which reads
``starts`` where the feed has it and falls back to ``minutes >= 60``.

A "late flag" is a row where the final pre-deadline status and the outcome
disagree: the log said available and he did not start, or the log said
unavailable and he did. Ordered by lead days ascending, because the worst late
flag is the one that arrived latest.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer import availability_eval as ae

EVENTS = pd.DataFrame({
    "gw": [2, 3],
    "deadline_time": ["2026-08-28T17:30:00Z", "2026-09-04T17:30:00Z"],
})


def _log(rows):
    """``(gw, snap_date, code, status)`` tuples -> a snapshot-log frame."""
    return pd.DataFrame(
        [{"season": "2026-27", "gw": g, "snap_date": d, "code": c,
          "status": s, "chance_of_playing": p, "llm_verdict": None,
          "source": None}
         for g, d, c, s, p in rows])


def _actuals(rows):
    """``(gw, code, minutes, starts)`` tuples -> a results frame."""
    return pd.DataFrame(
        [{"gw": g, "code": c, "minutes": m, "starts": st}
         for g, c, m, st in rows])


def test_a_player_whose_status_never_changed_is_not_a_row():
    """The report is about changes. A player who was 'a' all week told the
    manager nothing new and has no lead time to measure."""
    log = _log([(3, "2026-09-01", 1, "a", 100.0),
                (3, "2026-09-02", 1, "a", 100.0)])
    out = ae.score_flag_latency(log, _actuals([(3, 1, 90, 1)]), EVENTS,
                                season="2026-27")
    assert out["rows"] == 0


def test_the_lead_time_is_measured_from_the_first_change():
    """Two changes; the first is the one a manager could have acted on."""
    log = _log([(3, "2026-08-30", 1, "a", 100.0),
                (3, "2026-09-01", 1, "d", 50.0),
                (3, "2026-09-03", 1, "i", 0.0)])
    out = ae.score_flag_latency(log, _actuals([(3, 1, 0, 0)]), EVENTS,
                                season="2026-27")
    assert out["rows"] == 1
    row = out["changes"][0]
    assert row["first_change"] == "2026-09-01"
    assert row["lead_days"] == pytest.approx(3.73, abs=0.01)
    assert row["final_status"] == "i"
    assert row["started"] is False


def test_post_deadline_snapshots_are_not_in_the_window():
    """A2. GW2's deadline is 2026-08-28; the live log's GW2 rows are all
    later, and a change 'seen' after the deadline gave nobody any warning."""
    log = _log([(2, "2026-08-30", 1, "a", 100.0),
                (2, "2026-08-31", 1, "i", 0.0)])
    out = ae.score_flag_latency(log, _actuals([(2, 1, 0, 0)]), EVENTS,
                                season="2026-27")
    assert out["rows"] == 0


def test_only_data_checked_gameweeks_are_scored():
    """Without the result there is no outcome to pair the lead time with, so
    the row waits rather than being scored against a zero."""
    log = _log([(3, "2026-09-01", 1, "a", 100.0),
                (3, "2026-09-02", 1, "i", 0.0)])
    out = ae.score_flag_latency(log, _actuals([(2, 1, 90, 1)]), EVENTS,
                                season="2026-27")
    assert out["rows"] == 0
    assert out["checked_covered_gws"] == []


def test_the_season_guard_drops_another_seasons_rows():
    """Element ids are re-issued every August and so is gameweek 3. The log
    outlives a rollover; the results file does not carry a season at all."""
    log = pd.concat([
        _log([(3, "2026-09-01", 1, "a", 100.0),
              (3, "2026-09-02", 1, "i", 0.0)]),
        _log([(3, "2025-09-01", 1, "a", 100.0),
              (3, "2025-09-02", 1, "i", 0.0)]).assign(season="2025-26")])
    out = ae.score_flag_latency(log, _actuals([(3, 1, 0, 0)]), EVENTS,
                                season="2026-27")
    assert out["rows"] == 1


def test_the_histogram_splits_lead_days_by_outcome():
    log = _log([(3, "2026-08-30", 1, "a", 100.0),
                (3, "2026-09-03", 1, "i", 0.0),      # 1.73 days -> "1-2d"
                (3, "2026-08-30", 2, "a", 100.0),
                (3, "2026-08-31", 2, "d", 50.0)])    # 4.73 days -> "3-5d"
    out = ae.score_flag_latency(log, _actuals([(3, 1, 0, 0), (3, 2, 90, 1)]),
                                EVENTS, season="2026-27")
    buckets = {b["bucket"]: b for b in out["histogram"]}
    assert buckets["1-2d"] == {"bucket": "1-2d", "started": 0, "missed": 1}
    assert buckets["3-5d"] == {"bucket": "3-5d", "started": 1, "missed": 0}
    assert sum(b["started"] + b["missed"] for b in out["histogram"]) == 2


def test_a_late_flag_is_a_disagreement_between_the_final_status_and_the_start():
    """Both directions. The log said 'i' and he started; the log said 'a' and
    he did not. Either way the manager was told the wrong thing."""
    log = _log([(3, "2026-08-30", 1, "a", 100.0),
                (3, "2026-09-03", 1, "i", 0.0),
                (3, "2026-08-30", 2, "i", 0.0),
                (3, "2026-09-03", 2, "a", 100.0)])
    out = ae.score_flag_latency(
        log, _actuals([(3, 1, 90, 1), (3, 2, 0, 0)]), EVENTS,
        season="2026-27")
    assert [r["code"] for r in out["late_flags"]] == [1, 2]
    assert out["late_flags"][0]["started"] is True
    assert out["late_flags"][0]["final_status"] == "i"


def test_late_flags_are_ordered_by_lead_days_and_capped_at_twenty():
    """Spec §3.1 asks for the twenty worst. The worst is the latest."""
    rows = []
    for i in range(25):
        rows += [(3, "2026-08-30", i, "a", 100.0),
                 (3, f"2026-09-{i % 3 + 1:02d}", i, "i", 0.0)]
    out = ae.score_flag_latency(
        _log(rows), _actuals([(3, i, 90, 1) for i in range(25)]), EVENTS,
        season="2026-27")
    leads = [r["lead_days"] for r in out["late_flags"]]
    assert len(leads) == 20
    assert leads == sorted(leads)


def test_the_gate_reports_both_numbers_even_when_it_refuses():
    """Spec §3.1: the empty state says both numbers. Three snapshot dates of
    fourteen, and how many covered gameweeks are graded."""
    log = _log([(3, "2026-09-01", 1, "a", 100.0),
                (3, "2026-09-02", 1, "i", 0.0)])
    out = ae.score_flag_latency(log, _actuals([(3, 1, 0, 0)]), EVENTS,
                                season="2026-27")
    assert out["available"] is False
    assert out["snap_dates"] == 2
    assert out["min_snap_dates"] == 14
    assert out["checked_covered_gws"] == [3]
    assert "2 of 14" in out["note"]


def test_the_gate_opens_on_fourteen_dates_and_one_graded_gameweek():
    rows = [(3, f"2026-08-{d:02d}", 1, "a", 100.0) for d in range(18, 32)]
    rows.append((3, "2026-09-01", 1, "i", 0.0))
    out = ae.score_flag_latency(_log(rows), _actuals([(3, 1, 0, 0)]), EVENTS,
                                season="2026-27")
    assert out["available"] is True
    assert out["snap_dates"] == 15
    assert out["rows"] == 1


def test_an_empty_log_is_a_refusal_and_never_a_crash():
    out = ae.score_flag_latency(pd.DataFrame(), pd.DataFrame(), EVENTS,
                                season="2026-27")
    assert out["available"] is False
    assert out["rows"] == 0
    assert out["histogram"] == []
    assert out["late_flags"] == []
```

Run it: `.venv/bin/pytest -q tests/test_v12_flag_latency.py` — fails,
`AttributeError: module 'gaffer.availability_eval' has no attribute
'score_flag_latency'`.

- [ ] **Implement.** Append to `src/gaffer/availability_eval.py`:

```python
LEAD_BUCKETS = ((0.0, 1.0, "<1d"), (1.0, 2.0, "1-2d"), (2.0, 3.0, "2-3d"),
                (3.0, 5.0, "3-5d"), (5.0, 7.0, "5-7d"),
                (7.0, float("inf"), "7d+"))
"""Half-open ``[lo, hi)`` bands, in the units a manager thinks in.

Under a day is "I found out on the way to the deadline"; over a week is "this
was never news". The boundaries are not fitted to anything and are not
supposed to be — they are a reading aid over a distribution the project has
never seen, and the raw ``changes`` rows are on the payload for anyone who
wants their own."""

WORST_LATE_FLAGS = 20
"""Spec §3.1's table size."""

UNAVAILABLE_FLAG_STATUS = ("i", "s", "u", "n")
"""Statuses that assert the player will not feature. ``d`` (doubtful) is
deliberately not one: it is the layer *hedging*, and grading a hedge as a
prediction of absence would score the honest answer as a miss."""


def _bucket(days: float) -> str:
    for lo, hi, label in LEAD_BUCKETS:
        if lo <= days < hi:
            return label
    return LEAD_BUCKETS[-1][2]


def _outcomes(actuals: pd.DataFrame) -> dict[tuple[int, int], bool]:
    """``{(gw, code): started}`` over the graded gameweeks.

    ``start_truth`` rather than a bare ``minutes > 0``: the question §3.1 asks
    is whether he *started*, and the ``starts`` column postdates part of the
    archive, so the shipped inference is the one that must be used here too.
    Summed per (gw, code) first, because a double gameweek is two rows and
    "did he start" over a double is "did he start either".
    """
    from gaffer.evaluation import start_truth

    if actuals is None or actuals.empty:
        return {}
    frame = actuals.copy()
    frame["_started"] = start_truth(frame)
    grouped = frame.groupby(["gw", "code"], as_index=False).agg(
        _started=("_started", "max"))
    return {(int(r.gw), int(r.code)): bool(r._started > 0.0)
            for r in grouped.itertuples()}


def score_flag_latency(log: pd.DataFrame, actuals: pd.DataFrame,
                       events: pd.DataFrame, *, season: str) -> dict:
    """Spec §3.1, over the banked snapshot log. Never raises.

    One row per (gw, code) whose ``status`` changed at least once inside the
    pre-deadline window of a graded gameweek. ``lead_days`` is measured from
    the **first** change, which is the first moment a manager could have
    acted; the final status is the last one recorded before the deadline.

    The payload carries its own gate. ``available`` is false until the log
    holds :data:`MIN_SNAP_DATES` distinct days **and** at least one covered
    gameweek is graded, and the note names both numbers — because "nothing to
    show" and "nothing happened" are different sentences and only one of them
    is true in August.
    """
    empty = _empty("flag_latency",
                   "No availability snapshots have been banked yet.",
                   snap_dates=0, min_snap_dates=MIN_SNAP_DATES,
                   covered_gws=[], checked_covered_gws=[], histogram=[],
                   late_flags=[], changes=[])
    if log is None or log.empty or "status" not in log.columns:
        return empty
    frame = log.copy()
    if "season" in frame.columns:
        frame = frame[frame["season"].astype(str) == str(season)]
    if frame.empty:
        return empty

    snap_dates = int(frame["snap_date"].astype(str).nunique())
    window = pre_deadline(frame, deadlines(events))
    covered = sorted({int(g) for g in window["gw"].unique()}) \
        if not window.empty else []
    graded = sorted(set(covered) & checked_gws(actuals))
    gate = dict(snap_dates=snap_dates, min_snap_dates=MIN_SNAP_DATES,
                covered_gws=covered, checked_covered_gws=graded)
    if snap_dates < MIN_SNAP_DATES or not graded:
        return {**_empty(
            "flag_latency",
            f"{snap_dates} of {MIN_SNAP_DATES} snapshot days banked, and "
            f"{len(graded)} covered gameweek(s) graded. The report fills as "
            f"`gaffer snapshot` runs and gameweeks are marked data_checked.",
            **gate), "histogram": [], "late_flags": [], "changes": []}

    started = _outcomes(actuals)
    window = window[window["gw"].isin(graded)]
    window = window.sort_values(["gw", "code", "snap_date"])
    changes = []
    for (gw, code), part in window.groupby(["gw", "code"], sort=True):
        statuses = part["status"].astype("string").tolist()
        first = statuses[0]
        moved = [i for i, s in enumerate(statuses) if s != first]
        if not moved:
            continue
        outcome = started.get((int(gw), int(code)))
        if outcome is None:
            continue
        row = part.iloc[moved[0]]
        final = statuses[-1]
        changes.append({
            "gw": int(gw), "code": int(code),
            "first_change": str(row["snap_date"]),
            "lead_days": float(row["lead_days"]),
            "from_status": str(first), "final_status": str(final),
            "chance_of_playing": (
                None if pd.isna(part.iloc[-1].get("chance_of_playing"))
                else float(part.iloc[-1]["chance_of_playing"])),
            "started": bool(outcome),
        })

    histogram = []
    for _lo, _hi, label in LEAD_BUCKETS:
        rows = [c for c in changes if _bucket(c["lead_days"]) == label]
        if not rows:
            continue
        histogram.append({
            "bucket": label,
            "started": sum(1 for c in rows if c["started"]),
            "missed": sum(1 for c in rows if not c["started"]),
        })

    # The disagreement, both ways round. "The log said unavailable and he
    # started" is as much a late flag as its opposite: in each case the last
    # thing the manager was told before the deadline was wrong.
    late = [c for c in changes
            if (c["final_status"] in UNAVAILABLE_FLAG_STATUS) == c["started"]]
    late.sort(key=lambda c: (c["lead_days"], c["gw"], c["code"]))

    return {"run_at": run_at(), "git_sha": git_sha(), "kind": "flag_latency",
            "available": True, "rows": len(changes), "note": None,
            "histogram": histogram,
            "late_flags": late[:WORST_LATE_FLAGS],
            "changes": changes, **gate}
```

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_flag_latency.py
.venv/bin/pytest -q
```

- [ ] **Commit.**

```bash
git add src/gaffer/availability_eval.py tests/test_v12_flag_latency.py \
  && git commit -m "$(cat <<'EOF'
feat: flag latency — how much warning a status change actually gave

Spec §3.1 over the snapshot log v7c has been banking since August and nothing
has ever read. One row per (gw, code) whose status moved inside the
pre-deadline window of a graded gameweek, measured from the first change
because that is the first moment a manager could have acted.

A late flag is a disagreement in either direction: the log said unavailable
and he started, or it said available and he did not. Both are the manager
being told the wrong thing last, and grading only one direction would score
the layer's optimism and forgive its pessimism.

The gate is on the payload rather than in the page: fourteen snapshot days and
one graded covered gameweek, with the note naming both numbers, because
"nothing to show" and "nothing happened" are different sentences.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 3 — the presser-verdict scorer

**Files:**
- Modify `src/gaffer/availability_eval.py`
- Create `tests/test_v12_presser_grades.py`

**Read A3 before starting.** The population is `llm_verdict.notna()` and not
`source == "llm"`, and the classes are read off the data rather than declared.

- [ ] **Write the failing test.** Create `tests/test_v12_presser_grades.py`:

```python
"""Spec §3.2: the classifier's four verdicts against what happened.

The event being predicted is **absence** — "he did not start" — because that
is what every one of the four classes claims to some degree: ruled_out claims
it outright, knock and assess and rotation_risk claim it with less confidence.
Precision is then "of the players it called X, how many indeed did not start",
and the readout worth having is whether precision falls in the order the
classes are named in.

Recall is reported over the *verdict-carrying population* and labelled that
way on the payload. Recall over every absent player in the gameweek would be a
different and much harsher number — it would count every player the classifier
was never shown — and reporting it under the same word would be dishonest
about what was measured.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer import availability_eval as ae

EVENTS = pd.DataFrame({
    "gw": [2, 3],
    "deadline_time": ["2026-08-28T17:30:00Z", "2026-09-04T17:30:00Z"],
})


def _log(rows):
    """``(gw, snap_date, code, verdict, source)`` -> a snapshot-log frame."""
    return pd.DataFrame(
        [{"season": "2026-27", "gw": g, "snap_date": d, "code": c,
          "status": "d", "llm_verdict": v, "llm_confidence": 0.8,
          "source": s}
         for g, d, c, v, s in rows])


def _actuals(rows):
    return pd.DataFrame([{"gw": g, "code": c, "minutes": m, "starts": st}
                         for g, c, m, st in rows])


def test_the_population_is_the_verdict_column_and_not_the_source_column():
    """A3. 160 of the live log's 169 verdict rows say source=premierinjuries
    and 9 say llm. Filtering on source would grade 5% of the evidence."""
    log = _log([(3, "2026-09-01", 1, "ruled_out", "premierinjuries"),
                (3, "2026-09-01", 2, "ruled_out", "llm"),
                (3, "2026-09-01", 3, None, "lineups")])
    out = ae.score_presser_grades(
        log, _actuals([(3, 1, 0, 0), (3, 2, 0, 0), (3, 3, 90, 1)]), EVENTS,
        season="2026-27")
    assert out["rows"] == 2


def test_the_source_travels_as_a_breakdown_rather_than_a_filter():
    log = _log([(3, "2026-09-01", 1, "ruled_out", "premierinjuries"),
                (3, "2026-09-01", 2, "ruled_out", "llm")])
    out = ae.score_presser_grades(
        log, _actuals([(3, 1, 0, 0), (3, 2, 0, 0)]), EVENTS,
        season="2026-27")
    assert out["by_source"] == [{"source": "llm", "rows": 1},
                                {"source": "premierinjuries", "rows": 1}]


def test_the_confusion_matrix_counts_starts_against_each_class():
    log = _log([(3, "2026-09-01", 1, "ruled_out", "premierinjuries"),
                (3, "2026-09-01", 2, "ruled_out", "premierinjuries"),
                (3, "2026-09-01", 3, "assess", "premierinjuries")])
    out = ae.score_presser_grades(
        log, _actuals([(3, 1, 0, 0), (3, 2, 90, 1), (3, 3, 0, 0)]), EVENTS,
        season="2026-27")
    matrix = {r["verdict"]: r for r in out["confusion"]}
    assert matrix["ruled_out"] == {"verdict": "ruled_out", "started": 1,
                                   "not_started": 1, "n": 2}
    assert matrix["assess"]["not_started"] == 1


def test_precision_is_absence_given_the_verdict():
    log = _log([(3, "2026-09-01", i, "ruled_out", "premierinjuries")
                for i in range(4)])
    out = ae.score_presser_grades(
        log, _actuals([(3, 0, 0, 0), (3, 1, 0, 0), (3, 2, 0, 0),
                       (3, 3, 90, 1)]), EVENTS, season="2026-27")
    row = next(r for r in out["per_class"] if r["verdict"] == "ruled_out")
    assert row["precision"] == 0.75
    assert row["n"] == 4


def test_recall_is_over_the_verdict_carrying_population_and_says_so():
    """Three absent players carried a verdict; two of them were ruled_out."""
    log = _log([(3, "2026-09-01", 1, "ruled_out", "premierinjuries"),
                (3, "2026-09-01", 2, "ruled_out", "premierinjuries"),
                (3, "2026-09-01", 3, "knock", "premierinjuries")])
    out = ae.score_presser_grades(
        log, _actuals([(3, 1, 0, 0), (3, 2, 0, 0), (3, 3, 0, 0)]), EVENTS,
        season="2026-27")
    row = next(r for r in out["per_class"] if r["verdict"] == "ruled_out")
    assert row["recall"] == pytest.approx(2 / 3)
    assert out["recall_population"] == "verdict-carrying rows"


def test_a_class_nobody_got_right_reports_zero_and_not_null():
    log = _log([(3, "2026-09-01", 1, "rotation_risk", "premierinjuries")])
    out = ae.score_presser_grades(log, _actuals([(3, 1, 90, 1)]), EVENTS,
                                  season="2026-27")
    row = next(r for r in out["per_class"] if r["verdict"] == "rotation_risk")
    assert row["precision"] == 0.0
    assert row["n"] == 1


def test_the_classes_are_read_off_the_data_and_not_hard_coded():
    """A fifth class from a prompt change must show up as a row, not vanish."""
    log = _log([(3, "2026-09-01", 1, "suspended_appeal", "premierinjuries")])
    out = ae.score_presser_grades(log, _actuals([(3, 1, 0, 0)]), EVENTS,
                                  season="2026-27")
    assert [r["verdict"] for r in out["per_class"]] == ["suspended_appeal"]


def test_the_last_pre_deadline_verdict_is_the_one_graded():
    """Same rule ``score_news_shadow`` applies with ``.last()``: the verdict
    that stood when the deadline came is the one the manager acted on."""
    log = _log([(3, "2026-09-01", 1, "ruled_out", "premierinjuries"),
                (3, "2026-09-03", 1, "assess", "premierinjuries")])
    out = ae.score_presser_grades(log, _actuals([(3, 1, 90, 1)]), EVENTS,
                                  season="2026-27")
    assert out["rows"] == 1
    assert [r["verdict"] for r in out["per_class"]] == ["assess"]


def test_post_deadline_verdicts_are_not_graded_and_the_note_says_so():
    """A3, and the state of the live log today: every banked verdict was
    recorded after its gameweek's deadline, so the report is empty even though
    GW2 is data_checked."""
    log = _log([(2, "2026-08-30", 1, "ruled_out", "premierinjuries"),
                (2, "2026-08-31", 2, "assess", "premierinjuries")])
    out = ae.score_presser_grades(
        log, _actuals([(2, 1, 0, 0), (2, 2, 90, 1)]), EVENTS,
        season="2026-27")
    assert out["available"] is False
    assert out["rows"] == 0
    assert out["verdicts_banked"] == 2
    assert "before a deadline" in out["note"]


def test_an_ungraded_gameweek_waits_rather_than_scoring():
    log = _log([(3, "2026-09-01", 1, "ruled_out", "premierinjuries")])
    out = ae.score_presser_grades(log, _actuals([(2, 1, 0, 0)]), EVENTS,
                                  season="2026-27")
    assert out["available"] is False
    assert "data_checked" in out["note"]


def test_the_season_guard_drops_another_seasons_verdicts():
    log = pd.concat([
        _log([(3, "2026-09-01", 1, "ruled_out", "premierinjuries")]),
        _log([(3, "2025-09-01", 1, "assess", "premierinjuries")])
        .assign(season="2025-26")])
    out = ae.score_presser_grades(log, _actuals([(3, 1, 0, 0)]), EVENTS,
                                  season="2026-27")
    assert out["rows"] == 1


def test_a_log_with_no_verdict_column_at_all_is_a_refusal():
    """A log banked before the classifier existed. Not a crash."""
    log = _log([(3, "2026-09-01", 1, None, "lineups")]).drop(
        columns=["llm_verdict"])
    out = ae.score_presser_grades(log, _actuals([(3, 1, 0, 0)]), EVENTS,
                                  season="2026-27")
    assert out["available"] is False
    assert out["rows"] == 0
```

Run it: `.venv/bin/pytest -q tests/test_v12_presser_grades.py` — fails,
`AttributeError: … has no attribute 'score_presser_grades'`.

- [ ] **Implement.** Append to `src/gaffer/availability_eval.py`:

```python
def score_presser_grades(log: pd.DataFrame, actuals: pd.DataFrame,
                         events: pd.DataFrame, *, season: str) -> dict:
    """Spec §3.2, over the banked snapshot log. Never raises.

    **The population is ``llm_verdict.notna()``**, not ``source == "llm"``.
    The spec says both and they are different sets: measured on the live log,
    160 of 169 verdict rows carry ``source = premierinjuries`` and 9 carry
    ``llm``, because ``source`` names *which news source produced the row* and
    the classifier's verdict rides along on whatever row it was asked about.
    ``source`` travels into the payload as a breakdown instead.

    The event scored is **absence**. Every class claims it to some degree, so
    precision — absence given the verdict — is comparable across them, and the
    readout worth having is whether it falls in the order the classes are
    named in. Recall is over the verdict-carrying rows only and the payload
    says so: recall against every absent player in the gameweek would count
    everyone the classifier was never shown.

    The verdict graded is the **last one recorded before the deadline**, which
    is ``score_news_shadow``'s ``.last()`` rule for the same reason — it is the
    one that stood when the manager acted.
    """
    empty = _empty("presser_grades",
                   "No presser verdicts have been banked yet.",
                   verdicts_banked=0, confusion=[], per_class=[],
                   by_source=[], recall_population="verdict-carrying rows")
    if log is None or log.empty or "llm_verdict" not in log.columns:
        return empty
    frame = log.copy()
    if "season" in frame.columns:
        frame = frame[frame["season"].astype(str) == str(season)]
    frame = frame[frame["llm_verdict"].notna()]
    if frame.empty:
        return empty
    banked = int(len(frame))

    window = pre_deadline(frame, deadlines(events))
    if window.empty:
        return {**empty, "verdicts_banked": banked, "note": (
            f"{banked} verdict(s) banked, none of them recorded before a "
            f"deadline. The snapshot job began after GW2's deadline; the "
            f"first gradeable verdicts are the ones banked in a gameweek's "
            f"own week.")}
    graded = sorted({int(g) for g in window["gw"].unique()}
                    & checked_gws(actuals))
    if not graded:
        return {**empty, "verdicts_banked": banked, "note": (
            f"{banked} verdict(s) banked and {len(set(window['gw']))} "
            f"gameweek(s) covered before their deadline, none of them yet "
            f"marked data_checked. The grades land with the results.")}

    window = window[window["gw"].isin(graded)]
    last = (window.sort_values(["gw", "code", "snap_date"])
            .groupby(["gw", "code"], as_index=False).last())
    started = _outcomes(actuals)
    rows = []
    for r in last.itertuples():
        outcome = started.get((int(r.gw), int(r.code)))
        if outcome is None:
            continue
        rows.append({"verdict": str(r.llm_verdict),
                     "source": ("" if pd.isna(getattr(r, "source", None))
                                else str(r.source)),
                     "started": bool(outcome)})
    if not rows:
        return {**empty, "verdicts_banked": banked, "note": (
            "Every pre-deadline verdict belongs to a player with no result "
            "row in the graded gameweeks.")}

    absent_total = sum(1 for row in rows if not row["started"])
    confusion, per_class = [], []
    for verdict in sorted({row["verdict"] for row in rows}):
        part = [row for row in rows if row["verdict"] == verdict]
        missed = sum(1 for row in part if not row["started"])
        confusion.append({"verdict": verdict, "n": len(part),
                          "started": len(part) - missed,
                          "not_started": missed})
        per_class.append({
            "verdict": verdict, "n": len(part),
            "precision": round(missed / len(part), 3),
            # Zero rather than null when nobody was absent at all: the class
            # then found none of nothing, which is 0/0 only if you ask the
            # question the wrong way round. ``absent_total`` is on the payload
            # so a reader can see the denominator.
            "recall": (round(missed / absent_total, 3) if absent_total
                       else 0.0),
        })
    by_source = [{"source": s,
                  "rows": sum(1 for row in rows if row["source"] == s)}
                 for s in sorted({row["source"] for row in rows})]

    return {"run_at": run_at(), "git_sha": git_sha(),
            "kind": "presser_grades", "available": True, "rows": len(rows),
            "note": None, "verdicts_banked": banked,
            "graded_gws": graded, "absent_rows": absent_total,
            "confusion": confusion, "per_class": per_class,
            "by_source": by_source,
            "recall_population": "verdict-carrying rows"}
```

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_presser_grades.py
.venv/bin/pytest -q
```

- [ ] **Commit.**

```bash
git add src/gaffer/availability_eval.py tests/test_v12_presser_grades.py \
  && git commit -m "$(cat <<'EOF'
feat: grade the presser verdicts against who actually started

Spec §3.2, with one correction the log forced. The spec says the population is
"source is llm"; measured, 160 of the 169 verdict-carrying rows say
premierinjuries and 9 say llm, because source names which news source produced
the row and the classifier's verdict rides along on whatever it was asked
about. The population is llm_verdict.notna(); source travels as a breakdown.

The event scored is absence, which is what all four classes claim to differing
degrees, so precision is comparable across them. Recall is over the
verdict-carrying rows and the payload says so in a field — recall against every
absent player in the gameweek is a different number and would count everyone
the classifier was never shown.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 4 — the two evaluators, two CLI flags, two terminal tables

**Files:**
- Modify `src/gaffer/availability_eval.py`
- Modify `src/gaffer/evaluation.py` (`format_report`, `:1237-1250`)
- Modify `src/gaffer/cli.py` (`:528-568`)
- Create `tests/test_v12_availability_cli.py`

**Read A1.** Both payloads go into `reports/evaluation.json` under their own
key, through `save_evaluation`, and no new file is written.

- [ ] **Write the failing test.** Create `tests/test_v12_availability_cli.py`:

```python
"""The two reports end to end: log on disk -> artifact key -> terminal table.

The artifact is ``reports/evaluation.json``, not a file of their own. Spec
§3.1 names ``reports/evaluate/flag_latency.json``; that directory does not
exist, nothing would read it, and ``save_evaluation`` already merges
independent keys into one artifact through a temp file with allow_nan=False —
which is the discipline that stops a NaN becoming a 500 from /api/quality
three weeks later. The deviation is deliberate and recorded in the README.
"""

from __future__ import annotations

import json

import pandas as pd
from typer.testing import CliRunner

from gaffer import availability_eval as ae
from gaffer.cli import app

runner = CliRunner()


def _wire(monkeypatch, tmp_path, log, actuals, events):
    """Point every reader at frames, and the artifact at a temp directory."""
    from gaffer import evaluation
    from gaffer.config import Config

    monkeypatch.setattr(evaluation, "REPORTS", tmp_path)
    monkeypatch.setattr(evaluation, "EVALUATION_PATH",
                        tmp_path / "evaluation.json")
    monkeypatch.setattr(ae, "load_snapshot_log", lambda: log)
    monkeypatch.setattr(ae, "news_actuals", lambda: actuals)
    monkeypatch.setattr(ae, "load_events", lambda: events)
    monkeypatch.setattr(ae, "load_config",
                        lambda: Config(entry_id=1, league_id=2,
                                       current_season="2026-27"))
    return tmp_path / "evaluation.json"


def _log(gw, dates, verdict=None):
    rows = []
    for i, day in enumerate(dates):
        rows.append({"season": "2026-27", "gw": gw, "snap_date": day,
                     "code": 1, "status": "a" if i == 0 else "i",
                     "chance_of_playing": 100.0 if i == 0 else 0.0,
                     "llm_verdict": verdict, "llm_confidence": 0.9,
                     "source": "premierinjuries"})
    return pd.DataFrame(rows)


EVENTS = pd.DataFrame({"gw": [3],
                       "deadline_time": ["2026-09-04T17:30:00Z"]})
ACTUALS = pd.DataFrame({"gw": [3], "code": [1], "minutes": [0],
                        "starts": [0]})


def test_flag_latency_writes_its_key_into_the_one_artifact(monkeypatch,
                                                           tmp_path):
    dates = [f"2026-08-{d:02d}" for d in range(18, 32)] + ["2026-09-01"]
    path = _wire(monkeypatch, tmp_path, _log(3, dates), ACTUALS, EVENTS)
    result = runner.invoke(app, ["evaluate", "--flag-latency"])
    assert result.exit_code == 0
    stored = json.loads(path.read_text())
    assert stored["flag_latency"]["available"] is True
    assert stored["flag_latency"]["rows"] == 1


def test_presser_grades_writes_its_own_key_and_leaves_the_other_alone(
        monkeypatch, tmp_path):
    path = _wire(monkeypatch, tmp_path,
                 _log(3, ["2026-09-01"], verdict="ruled_out"), ACTUALS,
                 EVENTS)
    path.write_text(json.dumps({"flag_latency": {"kind": "flag_latency"}}))
    result = runner.invoke(app, ["evaluate", "--presser-grades"])
    assert result.exit_code == 0
    stored = json.loads(path.read_text())
    assert stored["presser_grades"]["rows"] == 1
    assert stored["flag_latency"] == {"kind": "flag_latency"}


def test_the_refusal_is_still_written_and_still_exit_zero(monkeypatch,
                                                          tmp_path):
    """An empty report is a measurement, not a failure. It is banked so the
    page can print what it is waiting for."""
    path = _wire(monkeypatch, tmp_path, _log(3, ["2026-09-01"]), ACTUALS,
                 EVENTS)
    result = runner.invoke(app, ["evaluate", "--flag-latency"])
    assert result.exit_code == 0
    stored = json.loads(path.read_text())
    assert stored["flag_latency"]["available"] is False
    assert "of 14" in stored["flag_latency"]["note"]


def test_the_terminal_table_prints_the_buckets_and_the_worst_flags():
    payload = {"kind": "flag_latency", "available": True, "rows": 2,
               "snap_dates": 15, "min_snap_dates": 14,
               "histogram": [{"bucket": "1-2d", "started": 1, "missed": 1}],
               "late_flags": [{"gw": 3, "code": 7, "lead_days": 1.5,
                               "final_status": "i", "started": True,
                               "first_change": "2026-09-03",
                               "from_status": "a",
                               "chance_of_playing": 0.0}],
               "run_at": "now", "git_sha": "abc1234"}
    from gaffer.evaluation import format_report

    text = format_report("flag_latency", payload)
    assert "1-2d" in text
    assert "code 7" in text


def test_the_terminal_table_says_what_it_is_waiting_for_when_empty():
    from gaffer.evaluation import format_report

    text = format_report("flag_latency",
                         {"kind": "flag_latency", "available": False,
                          "rows": 0, "note": "3 of 14 snapshot days banked.",
                          "run_at": "now", "git_sha": "abc1234"})
    assert "3 of 14" in text


def test_the_presser_table_prints_precision_per_class():
    from gaffer.evaluation import format_report

    text = format_report("presser_grades", {
        "kind": "presser_grades", "available": True, "rows": 4,
        "absent_rows": 3, "recall_population": "verdict-carrying rows",
        "per_class": [{"verdict": "ruled_out", "n": 4, "precision": 0.75,
                       "recall": 1.0}],
        "confusion": [{"verdict": "ruled_out", "n": 4, "started": 1,
                       "not_started": 3}],
        "by_source": [{"source": "premierinjuries", "rows": 4}],
        "run_at": "now", "git_sha": "abc1234"})
    assert "ruled_out" in text
    assert "0.75" in text
```

Run it: `.venv/bin/pytest -q tests/test_v12_availability_cli.py` — fails,
`AttributeError: … has no attribute 'load_snapshot_log'`.

- [ ] **Implement the evaluators.** Append to
`src/gaffer/availability_eval.py`, and add the three imports the tests
monkeypatch **at module level** so a test can replace them:

```python
from gaffer.config import load_config          # top of file, beside the rest
from gaffer.snapshot import load_snapshot_log  # ditto
```

```python
def load_events() -> pd.DataFrame:
    """The banked events snapshot, or an empty frame with the two columns.

    A module-level function rather than an inline ``store.load`` so a test can
    replace it, and so the two evaluators below cannot end up reading the
    deadline from two different places.
    """
    from gaffer.data import store

    if not store.exists("live/events.parquet"):
        return pd.DataFrame(columns=["gw", "deadline_time"])
    return store.load("live/events.parquet")


def _season() -> str:
    """``cfg.current_season``, or ``""``.

    Its own try, for ``news_shadow._current_season``'s reason: a report is
    better than no report, and a clone with no ``config.toml`` still has a log
    worth reading. An empty season matches the log's own empty-string season
    and therefore scores the pre-season rows and nothing else, which is the
    honest degradation rather than a silent whole-log score.
    """
    try:
        return str(load_config().current_season or "")
    except Exception as exc:  # noqa: BLE001 — a report never blocks on config
        print(f"availability report: no configured season ({exc})")
        return ""


def evaluate_flag_latency() -> dict:
    """:func:`score_flag_latency` over the banked log and the live results."""
    return score_flag_latency(load_snapshot_log(), news_actuals(),
                              load_events(), season=_season())


def evaluate_presser_grades() -> dict:
    """:func:`score_presser_grades` over the banked log and the results."""
    return score_presser_grades(load_snapshot_log(), news_actuals(),
                                load_events(), season=_season())
```

- [ ] **Implement the terminal tables.** In `src/gaffer/evaluation.py`, beside
`_format_news_shadow` (`:1178`):

```python
def _format_flag_latency(payload: dict) -> str:
    """Spec §3.1's table: lead time by outcome, then the worst late flags."""
    if not payload.get("available"):
        return f"flag latency: {payload.get('note') or 'nothing to score.'}"
    lines = [f"flag latency ({payload['rows']} status changes over "
             f"{payload['snap_dates']} snapshot days)",
             "  lead        started  missed"]
    for row in payload["histogram"]:
        lines.append(f"  {row['bucket']:<10} {row['started']:>7}  "
                     f"{row['missed']:>6}")
    if payload["late_flags"]:
        lines.append("  worst late flags (final status disagreed with the "
                     "start)")
        for row in payload["late_flags"]:
            lines.append(
                f"    GW{row['gw']:<3} code {row['code']:<7} "
                f"{row['lead_days']:5.2f}d  {row['from_status']}->"
                f"{row['final_status']}  "
                f"{'started' if row['started'] else 'did not start'}")
    return "\n".join(lines)


def _format_presser_grades(payload: dict) -> str:
    """Spec §3.2's table: precision of absence per verdict class."""
    if not payload.get("available"):
        return f"presser grades: {payload.get('note') or 'nothing to score.'}"
    lines = [f"presser grades ({payload['rows']} graded verdicts, "
             f"{payload['absent_rows']} absences)",
             "  verdict           n   started  absent  precision  recall"]
    conf = {row["verdict"]: row for row in payload["confusion"]}
    for row in payload["per_class"]:
        c = conf.get(row["verdict"], {})
        lines.append(
            f"  {row['verdict']:<16} {row['n']:>3}   {c.get('started', 0):>7}"
            f"  {c.get('not_started', 0):>6}  {row['precision']:>9.2f}"
            f"  {row['recall']:>6.2f}")
    lines.append(f"  recall is over {payload['recall_population']}")
    lines.append("  " + ", ".join(f"{s['source'] or 'unknown'} {s['rows']}"
                                  for s in payload["by_source"]))
    return "\n".join(lines)
```

and two lines in `format_report` (`:1247-1250`), beside the two that are there:

```python
    if key == "flag_latency":
        return _format_flag_latency(payload)
    if key == "presser_grades":
        return _format_presser_grades(payload)
```

- [ ] **Implement the CLI.** In `src/gaffer/cli.py`'s `evaluate` (`:528-568`),
two options beside `--news-shadow`:

```python
             flag_latency: bool = typer.Option(
                 False, "--flag-latency",
                 help="How much warning a status change gave before the "
                      "deadline, and whether the player then started "
                      "(v12 §3.1). Reads the banked snapshot log, refits "
                      "nothing, takes seconds."),
             presser_grades: bool = typer.Option(
                 False, "--presser-grades",
                 help="The presser classifier's verdicts against who actually "
                      "started (v12 §3.2)."),
```

and two branches at the head of the chain, before `calibration` — order does
not matter behaviourally, but both belong beside the other disk-only reports:

```python
    if flag_latency:
        from gaffer.availability_eval import evaluate_flag_latency

        key, payload = "flag_latency", evaluate_flag_latency()
    elif presser_grades:
        from gaffer.availability_eval import evaluate_presser_grades

        key, payload = "presser_grades", evaluate_presser_grades()
    elif calibration:
        key, payload = "calibration", evaluate_calibration(season=season)
```

— that `elif calibration:` line is the existing `:552-553`, unchanged; every
branch below it is unchanged too. The two new branches go **above** it.

The imports are local to the branch, for the module docstring's reason
(`evaluation.py:11-14`): `cli.py --help` must not pay for pandas.

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_availability_cli.py tests/test_cli.py
.venv/bin/pytest -q
```

- [ ] **Commit.**

```bash
git add src/gaffer/availability_eval.py src/gaffer/evaluation.py \
  src/gaffer/cli.py tests/test_v12_availability_cli.py \
  && git commit -m "$(cat <<'EOF'
feat: gaffer evaluate --flag-latency and --presser-grades

Both reports land in reports/evaluation.json under their own key rather than in
files of their own. Spec §3.1 names reports/evaluate/flag_latency.json; that
directory does not exist, nothing would read it, and save_evaluation already
merges independent keys through a temp file with allow_nan=False — the
discipline that stops a NaN becoming a 500 from /api/quality weeks later.

A refusal is written and exits zero: an empty report is a measurement, and the
page needs the banked sentence to print what it is waiting for.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 5 — `/api/quality` serves both reports

**Files:**
- Modify `src/gaffer/web/schemas.py` (`:952-960`)
- Create `tests/test_v12_quality_availability.py`

**Read A1 and A9.** No route, no router change: `quality()` already does
`Quality(**stored)` over the whole artifact, so declaring the fields is the
whole of the server work.

- [ ] **Write the failing test.** Create
`tests/test_v12_quality_availability.py`:

```python
"""Both availability reports on the wire, off the artifact already served.

``routers/quality.py:32-48`` does ``Quality(**stored)`` over
``reports/evaluation.json``. Undeclared keys are dropped by pydantic, silently
— which is exactly how ``news_shadow`` was written for a whole cycle and never
reached the page (``schemas.py:958-960`` records it). So the assertion that
matters here is not that the field exists; it is that a payload written by the
scorer survives the trip.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from gaffer.web.app import create_app

FLAG_LATENCY = {
    "run_at": "2026-09-05T10:00:00+00:00", "git_sha": "abc1234",
    "kind": "flag_latency", "available": True, "rows": 2, "note": None,
    "snap_dates": 15, "min_snap_dates": 14, "covered_gws": [3],
    "checked_covered_gws": [3],
    "histogram": [{"bucket": "1-2d", "started": 1, "missed": 1}],
    "late_flags": [{"gw": 3, "code": 7, "first_change": "2026-09-03",
                    "lead_days": 1.73, "from_status": "a",
                    "final_status": "i", "chance_of_playing": 0.0,
                    "started": True}],
    "changes": [{"gw": 3, "code": 7, "first_change": "2026-09-03",
                 "lead_days": 1.73, "from_status": "a", "final_status": "i",
                 "chance_of_playing": 0.0, "started": True}],
}

PRESSER = {
    "run_at": "2026-09-05T10:00:00+00:00", "git_sha": "abc1234",
    "kind": "presser_grades", "available": True, "rows": 4, "note": None,
    "verdicts_banked": 9, "graded_gws": [3], "absent_rows": 3,
    "confusion": [{"verdict": "ruled_out", "n": 4, "started": 1,
                   "not_started": 3}],
    "per_class": [{"verdict": "ruled_out", "n": 4, "precision": 0.75,
                   "recall": 1.0}],
    "by_source": [{"source": "premierinjuries", "rows": 4}],
    "recall_population": "verdict-carrying rows",
}


@pytest.fixture()
def served(tmp_path, monkeypatch):
    def install(payload: dict):
        from gaffer import evaluation

        path = tmp_path / "evaluation.json"
        path.write_text(json.dumps(payload))
        monkeypatch.setattr(evaluation, "EVALUATION_PATH", path)
        return TestClient(create_app())
    return install


def test_both_reports_reach_the_page(served):
    body = served({"flag_latency": FLAG_LATENCY,
                   "presser_grades": PRESSER}).get("/api/quality").json()
    assert body["flag_latency"]["late_flags"][0]["code"] == 7
    assert body["presser_grades"]["per_class"][0]["precision"] == 0.75


def test_a_refusal_reaches_the_page_with_its_sentence(served):
    """The empty state is served, not withheld: spec §1 wants the page to say
    what it is waiting for, and the sentence is written by the scorer."""
    refusal = {**FLAG_LATENCY, "available": False, "rows": 0,
               "note": "3 of 14 snapshot days banked, and 0 covered "
                       "gameweek(s) graded.", "histogram": [],
               "late_flags": [], "changes": []}
    body = served({"flag_latency": refusal}).get("/api/quality").json()
    assert body["flag_latency"]["available"] is False
    assert "3 of 14" in body["flag_latency"]["note"]


def test_an_artifact_without_the_keys_is_unchanged(served):
    """Every already-banked artifact predates this cycle. Absent, not empty."""
    body = served({"current": None}).get("/api/quality").json()
    assert body["flag_latency"] is None
    assert body["presser_grades"] is None


def test_the_route_total_is_unchanged(served):
    """No route: both reports ride the endpoint that already reads this file.
    The absolute count lives in tests/test_v11_degradation.py and stays there;
    this is the by-name claim (v11 route-pin restructure)."""
    client = served({})
    paths = set(client.app.openapi()["paths"])
    assert "/api/quality" in paths
    assert not [p for p in paths if "latency" in p or "presser" in p]
```

Run it: `.venv/bin/pytest -q tests/test_v12_quality_availability.py` — fails,
`KeyError: 'flag_latency'` (pydantic dropped the undeclared keys).

- [ ] **Implement.** In `src/gaffer/web/schemas.py`, above `class Quality`
(`:952`):

```python
class LeadBucket(BaseModel):
    """One band of the lead-time histogram, split by what happened."""

    bucket: str
    started: int
    missed: int


class FlagChange(BaseModel):
    """One (gameweek, player) whose status moved before the deadline."""

    gw: int
    code: int
    first_change: str
    """The snapshot day the status first differed from what it had been —
    the first day a manager could have acted, not the last."""
    lead_days: float
    from_status: str
    final_status: str
    """The last status recorded **before** the deadline. A snapshot taken
    afterwards told nobody anything and is not in this window."""
    chance_of_playing: float | None = None
    started: bool


class FlagLatency(BaseModel):
    """v12 §3.1's readout, or its refusal.

    ``available`` is what the card branches on, and ``note`` is the sentence
    it prints when the answer is no. Both are on the payload rather than in
    the page because the CLI prints the same sentence, and two copies of an
    empty state drift.
    """

    run_at: str
    git_sha: str
    available: bool = False
    rows: int = 0
    note: str | None = None
    snap_dates: int = 0
    min_snap_dates: int = 14
    covered_gws: list[int] = []
    checked_covered_gws: list[int] = []
    histogram: list[LeadBucket] = []
    late_flags: list[FlagChange] = []
    changes: list[FlagChange] = []


class VerdictRow(BaseModel):
    verdict: str
    n: int
    started: int
    not_started: int


class VerdictScore(BaseModel):
    verdict: str
    n: int
    precision: float
    """P(did not start | this verdict). Absence is the event every class
    claims, which is what makes the four numbers comparable."""
    recall: float


class SourceRows(BaseModel):
    source: str
    rows: int


class PresserGrades(BaseModel):
    """v12 §3.2's readout, or its refusal.

    ``recall_population`` is a field rather than a footnote: recall here is
    over the rows that carried a verdict, and the same word over every absent
    player in the gameweek would be a much harsher number about a much larger
    population.
    """

    run_at: str
    git_sha: str
    available: bool = False
    rows: int = 0
    note: str | None = None
    verdicts_banked: int = 0
    graded_gws: list[int] = []
    absent_rows: int = 0
    confusion: list[VerdictRow] = []
    per_class: list[VerdictScore] = []
    by_source: list[SourceRows] = []
    recall_population: str = "verdict-carrying rows"
```

and two fields on `Quality` (`:952-960`), beside `news_shadow`:

```python
    # v12 W2 §3.1/§3.2 (specs/2026-09-01-gaffer-v12-program-design.md). Same
    # trap news_shadow fell into for a cycle: the CLI writes the key, and an
    # undeclared field is dropped here without a word.
    flag_latency: FlagLatency | None = None
    presser_grades: PresserGrades | None = None
```

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_quality_availability.py tests/test_web_quality.py
.venv/bin/pytest -q
```

If `tests/test_web_quality.py` does not exist under that name, run the
quality-router tests the repo does have:
`.venv/bin/pytest -q -k quality`.

- [ ] **Commit.**

```bash
git add src/gaffer/web/schemas.py tests/test_v12_quality_availability.py \
  && git commit -m "$(cat <<'EOF'
feat: /api/quality serves the two availability reports

No route and no router change: quality() already does Quality(**stored) over
reports/evaluation.json, so declaring the models is the whole of it. The test
that matters asserts the trip rather than the field — news_shadow was written
by the CLI for a whole cycle and dropped here silently because nothing
declared it.

The refusal is served too, with its sentence, because spec §1 wants the page to
say what it is waiting for and the scorer is where that sentence is written.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 6 — the "Availability signal" section on Model → Quality

**Files:**
- Modify `frontend/src/types.ts` (`:559` `QualityData`, and beside
  `NewsShadowData` at `:720`)
- Modify `frontend/src/hubs/model/QualityTab.tsx` (`:845-856`)
- Modify `frontend/src/hubs/model/QualityTab.test.tsx`

**Read A9.** The card renders whenever the key is present, including when the
report is empty — which is deliberately *not* the `rows > 0` rule the
news-shadow section uses.

- [ ] **Write the failing test.** Append to
`frontend/src/hubs/model/QualityTab.test.tsx` (inside the existing top-level
`describe`, following the file's existing `apiGet` mock shape):

```tsx
  const FLAG_LATENCY = {
    run_at: 'now', git_sha: 'abc1234', available: true, rows: 2, note: null,
    snap_dates: 15, min_snap_dates: 14, covered_gws: [3],
    checked_covered_gws: [3],
    histogram: [{ bucket: '1-2d', started: 1, missed: 1 },
                { bucket: '3-5d', started: 3, missed: 0 }],
    late_flags: [{ gw: 3, code: 7, first_change: '2026-09-03',
                   lead_days: 1.73, from_status: 'a', final_status: 'i',
                   chance_of_playing: 0, started: true }],
    changes: [],
  }

  const PRESSER = {
    run_at: 'now', git_sha: 'abc1234', available: true, rows: 4, note: null,
    verdicts_banked: 9, graded_gws: [3], absent_rows: 3,
    confusion: [{ verdict: 'ruled_out', n: 4, started: 1, not_started: 3 }],
    per_class: [{ verdict: 'ruled_out', n: 4, precision: 0.75, recall: 1 }],
    by_source: [{ source: 'premierinjuries', rows: 4 }],
    recall_population: 'verdict-carrying rows',
  }

  it('draws the lead-time histogram and the worst late flags', async () => {
    apiGet.mockImplementation((path: string) => (
      path === '/api/quality'
        ? Promise.resolve({ flag_latency: FLAG_LATENCY })
        : Promise.reject(new FakeApiError(422, 'nothing'))))
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    expect(await screen.findByText('Availability signal')).toBeInTheDocument()
    expect(screen.getByTestId('lead-bucket-1-2d')).toHaveTextContent('1')
    expect(screen.getByTestId('late-flag-3-7'))
      .toHaveTextContent('did not start')
  })

  it('says what it is waiting for instead of drawing zeros', async () => {
    // Spec §1. The bar chart of an empty histogram is a row of zeroes that
    // reads as "nothing ever changed", which is a measurement nobody made.
    apiGet.mockImplementation((path: string) => (
      path === '/api/quality'
        ? Promise.resolve({
          flag_latency: {
            ...FLAG_LATENCY, available: false, rows: 0, snap_dates: 3,
            checked_covered_gws: [], histogram: [], late_flags: [],
            note: '3 of 14 snapshot days banked, and 0 covered gameweek(s) '
              + 'graded.',
          },
        })
        : Promise.reject(new FakeApiError(422, 'nothing'))))
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    expect(await screen.findByTestId('flag-latency-empty'))
      .toHaveTextContent('3 of 14 snapshot days')
    expect(screen.queryByTestId('lead-bucket-1-2d')).toBeNull()
  })

  it('prints precision per verdict class with its denominator', async () => {
    apiGet.mockImplementation((path: string) => (
      path === '/api/quality'
        ? Promise.resolve({ presser_grades: PRESSER })
        : Promise.reject(new FakeApiError(422, 'nothing'))))
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    const row = await screen.findByTestId('verdict-ruled_out')
    expect(row).toHaveTextContent('0.75')
    expect(row).toHaveTextContent('4')
    expect(screen.getByTestId('presser-recall-note'))
      .toHaveTextContent('verdict-carrying rows')
  })

  it('draws no availability card at all on an artifact without the keys',
     async () => {
       apiGet.mockImplementation((path: string) => (
         path === '/api/quality'
           ? Promise.resolve({ current: null })
           : Promise.reject(new FakeApiError(422, 'nothing'))))
       render(<MemoryRouter><QualityTab /></MemoryRouter>)
       await screen.findByText(/Quality|evaluat/i)
       expect(screen.queryByText('Availability signal')).toBeNull()
     })
```

Run it: `cd frontend && npx vitest run src/hubs/model/QualityTab.test.tsx` —
fails on the missing heading.

- [ ] **Implement the types.** In `frontend/src/types.ts`, beside
`NewsShadowData` (`:720`):

```ts
export interface LeadBucket {
  bucket: string
  started: number
  missed: number
}

export interface FlagChange {
  gw: number
  code: number
  /** The snapshot day the status first differed — the first day a manager
   *  could have acted, not the last. */
  first_change: string
  lead_days: number
  from_status: string
  final_status: string
  chance_of_playing: number | null
  started: boolean
}

export interface FlagLatencyData {
  run_at: string
  git_sha: string
  /** False until fourteen snapshot days and one graded covered gameweek. The
   *  card still renders — it prints `note`. */
  available: boolean
  rows: number
  note: string | null
  snap_dates: number
  min_snap_dates: number
  covered_gws: number[]
  checked_covered_gws: number[]
  histogram: LeadBucket[]
  late_flags: FlagChange[]
  changes: FlagChange[]
}

export interface VerdictRow {
  verdict: string
  n: number
  started: number
  not_started: number
}

export interface VerdictScore {
  verdict: string
  n: number
  /** P(did not start | this verdict). */
  precision: number
  recall: number
}

export interface PresserGradesData {
  run_at: string
  git_sha: string
  available: boolean
  rows: number
  note: string | null
  verdicts_banked: number
  graded_gws: number[]
  absent_rows: number
  confusion: VerdictRow[]
  per_class: VerdictScore[]
  by_source: Array<{ source: string; rows: number }>
  /** Which population `recall` is over. Printed, not assumed. */
  recall_population: string
}
```

and two fields on `QualityData` (`:559`):

```ts
  flag_latency: FlagLatencyData | null
  presser_grades: PresserGradesData | null
```

- [ ] **Implement the section.** In
`frontend/src/hubs/model/QualityTab.tsx`, add `FlagLatencyData` and
`PresserGradesData` to the type import block (`:11-16`) and add, beside
`NewsShadowSection`:

```tsx
// The bar is scaled to the largest bucket in *this* histogram, the way
// PairedBar scales to its own row: lead times are counts and a shared axis
// across a fortnight of snapshots would draw every early bucket as nothing.
function LeadBar({ started, missed, top }:
                 { started: number; missed: number; top: number }) {
  return (
    <span className="inline-flex w-32 flex-col gap-0.5 align-middle">
      <span className="h-1.5 rounded-full bg-base">
        <span className="block h-1.5 rounded-full"
              style={{ width: `${(started / top) * 100}%`,
                       background: 'var(--color-sage)' }}
              aria-label={`started ${started}`} />
      </span>
      <span className="h-1.5 rounded-full bg-base">
        <span className="block h-1.5 rounded-full"
              style={{ width: `${(missed / top) * 100}%`,
                       background: 'var(--color-rust)' }}
              aria-label={`did not start ${missed}`} />
      </span>
    </span>
  )
}

function FlagLatencySection({ data }: { data: FlagLatencyData }) {
  if (!data.available) {
    // Spec §1: an empty state names what it is waiting for. The sentence is
    // the server's, so the CLI and the page cannot drift apart on it.
    return (
      <p data-testid="flag-latency-empty" className="text-text-muted">
        {data.note ?? 'Nothing to score yet.'}
      </p>
    )
  }
  const top = Math.max(
    1, ...data.histogram.map((b) => Math.max(b.started, b.missed)))
  return (
    <>
      <p className="mb-2 text-text-secondary">
        {data.rows}
        {' status changes over '}
        {data.snap_dates}
        {' snapshot days, in gameweeks '}
        {data.checked_covered_gws.join(', ')}
        {'.'}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="label pb-1 text-left">Warning</th>
              <th className="label pb-1 text-right">Started</th>
              <th className="label pb-1 text-right">Did not</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.histogram.map((b) => (
              <tr key={b.bucket} data-testid={`lead-bucket-${b.bucket}`}
                  className="border-t border-divider">
                <td className="num py-1.5 text-text">{b.bucket}</td>
                <td className="num py-1.5 text-right text-sage">
                  {b.started}
                </td>
                <td className="num py-1.5 text-right text-rust">
                  {b.missed}
                </td>
                <td className="px-2 py-1.5">
                  <LeadBar started={b.started} missed={b.missed} top={top} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.late_flags.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <p className="label mb-1">
            Latest flags whose final status disagreed with the start
          </p>
          <table className="w-full">
            <tbody>
              {data.late_flags.map((f) => (
                <tr key={`${f.gw}-${f.code}`}
                    data-testid={`late-flag-${f.gw}-${f.code}`}
                    className="border-t border-divider">
                  <td className="num py-1.5 text-text">{`GW${f.gw}`}</td>
                  <td className="num py-1.5 text-text-secondary">
                    {`code ${f.code}`}
                  </td>
                  <td className="num py-1.5 text-right">
                    {`${fmtNum(f.lead_days, 2)}d`}
                  </td>
                  <td className="py-1.5 text-text-muted">
                    {`${f.from_status} → ${f.final_status}`}
                  </td>
                  <td className="py-1.5 text-right">
                    {f.started ? 'started' : 'did not start'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

function PresserGradesSection({ data }: { data: PresserGradesData }) {
  if (!data.available) {
    return (
      <p data-testid="presser-grades-empty" className="mt-3 text-text-muted">
        {data.note ?? 'Nothing to score yet.'}
      </p>
    )
  }
  const conf = new Map(data.confusion.map((c) => [c.verdict, c]))
  return (
    <div className="mt-4">
      <p className="label mb-1">Presser verdicts</p>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="label pb-1 text-left">Verdict</th>
              <th className="label pb-1 text-right">Graded</th>
              <th className="label pb-1 text-right">Started</th>
              <th className="label pb-1 text-right">Absent</th>
              <th className="label pb-1 text-right">Precision</th>
              <th className="label pb-1 text-right">Recall</th>
            </tr>
          </thead>
          <tbody>
            {data.per_class.map((row) => (
              <tr key={row.verdict} data-testid={`verdict-${row.verdict}`}
                  className="border-t border-divider">
                <td className="py-1.5 text-text">{row.verdict}</td>
                <td className="num py-1.5 text-right">{row.n}</td>
                <td className="num py-1.5 text-right text-text-muted">
                  {conf.get(row.verdict)?.started ?? 0}
                </td>
                <td className="num py-1.5 text-right text-text-muted">
                  {conf.get(row.verdict)?.not_started ?? 0}
                </td>
                <td className="num py-1.5 text-right text-sage">
                  {fmtNum(row.precision, 2)}
                </td>
                <td className="num py-1.5 text-right text-text-secondary">
                  {fmtNum(row.recall, 2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p data-testid="presser-recall-note"
         className="mt-1 text-xs text-text-faint">
        {'Precision is P(did not start | verdict). Recall is over '}
        {data.recall_population}
        {` — ${data.absent_rows} absences among ${data.rows} graded `}
        {'verdicts, not every absence in the gameweek.'}
      </p>
    </div>
  )
}

function AvailabilitySection({ flag, presser }:
                             { flag: FlagLatencyData | null
                               presser: PresserGradesData | null }) {
  return (
    <Card title="Availability signal" className="mt-4">
      {flag && <FlagLatencySection data={flag} />}
      {presser && <PresserGradesSection data={presser} />}
    </Card>
  )
}
```

and one line in the render list (`:851-856`), after the news-shadow line:

```tsx
      {(data.flag_latency || data.presser_grades)
        && <AvailabilitySection flag={data.flag_latency ?? null}
                                presser={data.presser_grades ?? null} />}
```

- [ ] **Verify.**

```bash
cd frontend && npx vitest run src/hubs/model/QualityTab.test.tsx
cd frontend && npx tsc --noEmit
cd frontend && npx vitest run
```

The 390px rail (`frontend/src/hubs/responsive.test.tsx`) asserts no bare
tables: both tables above are inside `overflow-x-auto`, which is what keeps it
green. If it fails, the wrapper was dropped — **fix the wrapper, not the
rail**.

- [ ] **Commit.**

```bash
git add frontend/src/types.ts frontend/src/hubs/model/QualityTab.tsx \
  frontend/src/hubs/model/QualityTab.test.tsx \
  && git commit -m "$(cat <<'EOF'
feat: the Availability signal card on Model -> Quality

Two reports in one card: lead time by outcome with the worst late flags, and
precision per presser verdict with the denominator printed rather than assumed.

It renders whenever the key is present, including when the report is empty —
deliberately not the rows > 0 rule the news-shadow section uses. An empty
histogram drawn as bars is a row of zeroes that reads as "nothing ever
changed", which is a measurement nobody made; the card prints the server's own
sentence instead, so the CLI and the page cannot drift apart on it.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 7 — degradation tests for the two new readers

**Files:**
- Create `tests/test_v12_w2_degradation.py`

**Named `_w2_` on purpose.** CONVENTIONS' pattern is
`tests/test_<name>_degradation.py`, and the v12 program has five workstreams
that would otherwise collide on one `test_v12_degradation.py`. W1 owns that
name; this is W2's.

**It makes absence claims, not count claims.** The v11 route-pin restructure
put the absolute route total in `tests/test_v11_degradation.py` **alone**, and
re-asserting it here would rebuild exactly what that cycle dismantled.

- [ ] **Write the test.** Create `tests/test_v12_w2_degradation.py`:

```python
"""v12 W2's degradation contract: four ways for each reader to have nothing.

Missing file, malformed file, empty result, partial result — each a named
behaviour and none of them a crash (spec §1). Plus the three claims W2 makes
about the shape of the tree, stated as absence rather than as counts: the
route-pin restructure (v11 §0) put the absolute totals in one file and this is
not that file.
"""

from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from gaffer import availability_eval as ae
from gaffer.config import Config


def _events():
    return pd.DataFrame({"gw": [3],
                         "deadline_time": ["2026-09-04T17:30:00Z"]})


# --- missing -------------------------------------------------------------

def test_no_availability_log_at_all_is_a_refusal(monkeypatch):
    monkeypatch.setattr(ae, "load_snapshot_log", lambda: pd.DataFrame())
    monkeypatch.setattr(ae, "news_actuals", lambda: pd.DataFrame())
    monkeypatch.setattr(ae, "load_events", _events)
    monkeypatch.setattr(ae, "load_config",
                        lambda: Config(entry_id=1, league_id=2))
    for payload in (ae.evaluate_flag_latency(), ae.evaluate_presser_grades()):
        assert payload["available"] is False
        assert payload["rows"] == 0
        assert payload["note"]


def test_no_events_snapshot_means_no_deadlines_and_no_report():
    """Without a deadline there is no such thing as a lead time, and the
    report says so rather than measuring from an assumed Friday."""
    log = pd.DataFrame({"season": ["2026-27"], "gw": [3],
                        "snap_date": ["2026-09-01"], "code": [1],
                        "status": ["a"], "llm_verdict": ["ruled_out"],
                        "source": ["premierinjuries"]})
    actuals = pd.DataFrame({"gw": [3], "code": [1], "minutes": [0],
                            "starts": [0]})
    empty = pd.DataFrame(columns=["gw", "deadline_time"])
    assert ae.score_flag_latency(log, actuals, empty,
                                 season="2026-27")["rows"] == 0
    assert ae.score_presser_grades(log, actuals, empty,
                                   season="2026-27")["rows"] == 0


# --- malformed -----------------------------------------------------------

def test_a_log_missing_the_status_column_is_a_refusal():
    log = pd.DataFrame({"season": ["2026-27"], "gw": [3],
                        "snap_date": ["2026-09-01"], "code": [1]})
    out = ae.score_flag_latency(log, pd.DataFrame(), _events(),
                                season="2026-27")
    assert out["available"] is False


def test_unparseable_gameweeks_and_dates_are_dropped_not_defaulted():
    log = pd.DataFrame({
        "season": ["2026-27"] * 2, "gw": ["three", 3],
        "snap_date": ["not-a-date", "2026-09-01"], "code": [1, 1],
        "status": ["a", "a"]})
    kept = ae.pre_deadline(log, ae.deadlines(_events()))
    assert len(kept) == 1


def test_a_deadline_that_will_not_parse_takes_its_gameweek_with_it():
    events = pd.DataFrame({"gw": [3], "deadline_time": ["never"]})
    assert ae.deadlines(events) == {}


# --- empty ---------------------------------------------------------------

def test_a_log_with_verdicts_but_no_results_waits(monkeypatch):
    log = pd.DataFrame({"season": ["2026-27"], "gw": [3],
                        "snap_date": ["2026-09-01"], "code": [1],
                        "status": ["d"], "llm_verdict": ["assess"],
                        "source": ["premierinjuries"]})
    out = ae.score_presser_grades(log, pd.DataFrame(columns=["gw", "code",
                                                             "minutes"]),
                                  _events(), season="2026-27")
    assert out["available"] is False
    assert out["verdicts_banked"] == 1


def test_a_season_with_no_rows_scores_nothing_rather_than_everything():
    """The season guard has no fallback: "whatever is newest" is the failure
    it exists to prevent (field.py:233-234's rule, applied here)."""
    log = pd.DataFrame({"season": ["2025-26"], "gw": [3],
                        "snap_date": ["2026-09-01"], "code": [1],
                        "status": ["a"], "llm_verdict": ["assess"],
                        "source": ["premierinjuries"]})
    actuals = pd.DataFrame({"gw": [3], "code": [1], "minutes": [0],
                            "starts": [0]})
    assert ae.score_flag_latency(log, actuals, _events(),
                                 season="2026-27")["rows"] == 0
    assert ae.score_presser_grades(log, actuals, _events(),
                                   season="2026-27")["rows"] == 0


# --- partial -------------------------------------------------------------

def test_a_player_with_no_result_row_is_skipped_and_the_rest_score():
    dates = [f"2026-08-{d:02d}" for d in range(18, 32)] + ["2026-09-01"]
    rows = []
    for code in (1, 2):
        for i, day in enumerate(dates):
            rows.append({"season": "2026-27", "gw": 3, "snap_date": day,
                         "code": code, "status": "a" if i == 0 else "i",
                         "chance_of_playing": None, "llm_verdict": None,
                         "source": None})
    actuals = pd.DataFrame({"gw": [3], "code": [1], "minutes": [0],
                            "starts": [0]})
    out = ae.score_flag_latency(pd.DataFrame(rows), actuals, _events(),
                                season="2026-27")
    assert out["rows"] == 1
    assert [c["code"] for c in out["changes"]] == [1]


def test_a_missing_config_scores_the_empty_season_rather_than_raising(
        monkeypatch):
    def boom():
        raise RuntimeError("no config.toml on this machine")

    monkeypatch.setattr(ae, "load_config", boom)
    monkeypatch.setattr(ae, "load_snapshot_log", lambda: pd.DataFrame())
    monkeypatch.setattr(ae, "news_actuals", lambda: pd.DataFrame())
    monkeypatch.setattr(ae, "load_events", _events)
    assert ae.evaluate_flag_latency()["available"] is False


# --- the shape claims ----------------------------------------------------

def test_w2_adds_no_config_field():
    """Both W2 keys are module-level readers (config.py:221's precedent):
    another field moves a count four protected degradation files pin, and W1
    §2.6 has already spent that once on ``top_n``.

    ``top_n`` is asserted *present* on purpose. It is W1's field, it is
    splatted out of the same ``[optimizer]`` section W2's flag hides in, and
    the pop list is one careless line away from swallowing it."""
    names = {f.name for f in dataclasses.fields(Config)}
    assert "price_timing" not in names
    assert "xg_per_shot" not in names
    assert "top_n" in names


def test_w2_adds_no_job_kind():
    """JOB_KINDS maps a kind to a zero-argument callable, so a report that is
    a CLI flag cannot be a job (evaluation.py:562-566's story)."""
    from gaffer.web.job_kinds import JOB_KINDS

    assert not [k for k in JOB_KINDS
                if "latency" in k or "presser" in k or "trend" in k]


def test_w2_adds_no_route():
    import os
    import tempfile

    os.chdir(tempfile.mkdtemp())
    from gaffer.web.app import create_app

    paths = set(create_app().openapi()["paths"])
    assert "/api/quality" in paths
    assert not [p for p in paths
                if "latency" in p or "presser" in p or "trend" in p]
```

Note the `os.chdir` in the last test: it is the idiom `test_v11_degradation.py`
uses to build the app on a tree with no `config.toml`. If that test's ordering
disturbs another test's working directory, move it to its own file rather than
weakening it — **stop and report** if it does.

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_w2_degradation.py
.venv/bin/pytest -q
```

- [ ] **Commit.**

```bash
git add tests/test_v12_w2_degradation.py && git commit -m "$(cat <<'EOF'
test: v12 W2 degradation — four ways for each reader to have nothing

Missing file, malformed file, empty result, partial result, each a named
behaviour. Plus the three shape claims, stated as absence rather than as
counts: no config field, no job kind, no route. The v11 route-pin restructure
put the absolute totals in one file and this is not that file.

The season guard's test is the one worth reading: it has no fallback, because
"score whatever is newest" is the failure the guard exists to prevent.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 8 — `field_eo_trend`, at the grain the data actually has

**Files:**
- Modify `src/gaffer/data/field.py` (append, after `latest_field_eo` at
  `:202-253`)
- Create `tests/test_v12_field_eo_trend.py`

**Read A4 in full before writing a line of this.** The spec's day-grained
trend cannot exist: the collector never banks two samples of one gameweek
(`field.py:384-400`), post-deadline picks are frozen so the difference would be
sampling noise, the units are percent and the ceiling is not 1.0, and the
field's ownership of the *upcoming* gameweek is not observable at all before
its deadline. The grain that has data in it is the gameweek.

**If the orchestrator has answered Question 1 by choosing the day grain
anyway, only `_pair_samples` changes** — the payload, the callers, the tests'
shape and the UI are grain-agnostic by construction.

- [ ] **Write the failing test.** Create `tests/test_v12_field_eo_trend.py`:

```python
"""Spec §3.3, at the grain the log has: gameweek to gameweek.

Three measured facts decide this and each is in the plan's A4:

* ``run_field_scrape`` exits on ``_already_banked`` before it builds a client,
  so the Sunday plist never writes a second sample for one gameweek — the live
  log holds 123 rows, one gameweek, one snap_date;
* picks are frozen after the deadline (the scrape is deliberately
  post-deadline, ``field.py:280-291``), so two same-gameweek samples would
  differ only by which ~300 entries were drawn;
* ``eo_from_picks`` returns **percent** with captaincy counted double, so the
  live log's maximum is 214.7 and the spec's clamp to [0, 1] would floor the
  entire instrument.

So the trend is between the latest sample of the requested gameweek and the
latest sample of the newest earlier gameweek, and ``deadline_eo`` extrapolates
**one gameweek forward** — the only interval over which field ownership moves
at all, since nobody's picks for the next gameweek are public before its
deadline.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.data import field


def _log(rows):
    """``(season, gw, snap_date, element, eo)`` -> a field-EO log frame."""
    return pd.DataFrame(
        [{"season": s, "gw": g, "snap_date": d, "element": e, "eo": v,
          "se": 2.0, "n": 300} for s, g, d, e, v in rows])


@pytest.fixture()
def logged(monkeypatch):
    def install(rows):
        monkeypatch.setattr(field, "load_field_eo", lambda: _log(rows))
    return install


def test_one_gameweek_of_samples_has_no_trend(logged):
    """Today's state, and it must read as "no trend" rather than as zero
    drift. A delta of 0.0 is a measurement; this is the absence of one."""
    logged([("2026-27", 2, "2026-08-31", 100, 40.0)])
    out = field.field_eo_trend("2026-27", 2)
    assert out[100]["trend_available"] is False
    assert out[100]["delta"] is None
    assert out[100]["deadline_eo"] == 40.0
    assert out[100]["eo_last"] == 40.0


def test_two_gameweeks_extrapolate_one_gameweek_forward(logged):
    logged([("2026-27", 2, "2026-08-31", 100, 40.0),
            ("2026-27", 3, "2026-09-07", 100, 46.0)])
    out = field.field_eo_trend("2026-27", 3)
    assert out[100]["trend_available"] is True
    assert out[100]["eo_first"] == 40.0
    assert out[100]["eo_last"] == 46.0
    assert out[100]["delta"] == 6.0
    assert out[100]["gws_between"] == 1
    assert out[100]["deadline_eo"] == 52.0


def test_a_gap_in_the_log_divides_the_delta_by_the_gap(logged):
    """GW2 and GW5 with nothing between: six points over three gameweeks is
    two a week, not six."""
    logged([("2026-27", 2, "2026-08-31", 100, 40.0),
            ("2026-27", 5, "2026-09-21", 100, 46.0)])
    out = field.field_eo_trend("2026-27", 5)
    assert out[100]["gws_between"] == 3
    assert out[100]["deadline_eo"] == 48.0


def test_the_latest_snapshot_of_each_gameweek_is_the_one_used(logged):
    logged([("2026-27", 2, "2026-08-30", 100, 30.0),
            ("2026-27", 2, "2026-08-31", 100, 40.0),
            ("2026-27", 3, "2026-09-06", 100, 44.0),
            ("2026-27", 3, "2026-09-07", 100, 46.0)])
    out = field.field_eo_trend("2026-27", 3)
    assert (out[100]["eo_first"], out[100]["eo_last"]) == (40.0, 46.0)


def test_the_extrapolation_is_clamped_to_what_the_sampler_can_produce(logged):
    """EO is a percentage that captaincy doubles, so the ceiling is 200 and
    not 1.0 — the live log's own maximum today is 214.7, which is a *triple*
    captain's contribution and the reason the clamp is generous rather than
    tight. The floor is 0: a negative ownership is not a thing."""
    logged([("2026-27", 2, "2026-08-31", 100, 150.0),
            ("2026-27", 3, "2026-09-07", 100, 190.0),
            ("2026-27", 2, "2026-08-31", 200, 20.0),
            ("2026-27", 3, "2026-09-07", 200, 4.0)])
    out = field.field_eo_trend("2026-27", 3)
    assert out[100]["deadline_eo"] == 200.0
    assert out[200]["deadline_eo"] == 0.0


def test_a_player_the_earlier_gameweek_never_sampled_has_no_trend(logged):
    """``eo_from_picks`` omits an element nobody started, so absence from the
    earlier table is "nobody had him", not "we did not look" — but a
    zero-based delta off a sparse table would read a promoted bench player as
    a 40-point riser. He gets no trend."""
    logged([("2026-27", 2, "2026-08-31", 100, 40.0),
            ("2026-27", 3, "2026-09-07", 100, 46.0),
            ("2026-27", 3, "2026-09-07", 200, 40.0)])
    out = field.field_eo_trend("2026-27", 3)
    assert out[200]["trend_available"] is False
    assert out[200]["deadline_eo"] == 40.0


def test_the_season_is_required_and_filters(logged):
    """Element ids are re-issued every August: the same integer is a different
    footballer on the other side of a rollover."""
    logged([("2025-26", 3, "2025-09-07", 100, 90.0),
            ("2026-27", 2, "2026-08-31", 100, 40.0),
            ("2026-27", 3, "2026-09-07", 100, 46.0)])
    assert field.field_eo_trend("2026-27", 3)[100]["eo_first"] == 40.0
    assert field.field_eo_trend("2025-26", 3)[100]["trend_available"] is False
    with pytest.raises(TypeError):
        field.field_eo_trend(3)          # season is positional and required


def test_gw_none_reads_the_newest_gameweek_in_the_season(logged):
    logged([("2026-27", 2, "2026-08-31", 100, 40.0),
            ("2026-27", 3, "2026-09-07", 100, 46.0)])
    assert field.field_eo_trend("2026-27", None)[100]["deadline_eo"] == 52.0


def test_an_unreadable_log_is_an_empty_map_and_never_an_exception(
        monkeypatch):
    """``latest_field_eo``'s contract, kept: F4 is display and a missing
    display column is the documented degradation."""
    def boom():
        raise OSError("parquet is a directory today")

    monkeypatch.setattr(field, "load_field_eo", boom)
    assert field.field_eo_trend("2026-27", 3) == {}


def test_a_log_with_no_season_column_is_an_empty_map(monkeypatch):
    """A log banked before v8c's season column. Empty rather than scored:
    without the column there is no way to know which season's element 100 the
    rows describe, and the guard has no fallback by design."""
    frame = _log([("2026-27", 3, "2026-09-07", 100, 46.0)]).drop(
        columns=["season"])
    monkeypatch.setattr(field, "load_field_eo", lambda: frame)
    assert field.field_eo_trend("2026-27", 3) == {}
```

Run it: `.venv/bin/pytest -q tests/test_v12_field_eo_trend.py` — fails,
`AttributeError: module 'gaffer.data.field' has no attribute
'field_eo_trend'`.

- [ ] **Implement.** Append to `src/gaffer/data/field.py`, after
`latest_field_eo`:

```python
EO_CEILING = 200.0
"""The most an EO extrapolation may claim, in the log's own percent units.

``eo_from_picks`` counts a captain twice (``tier_eo.py:154-179``), so a player
every sampled entry starts and captains reads 200. Triple captain can push a
single sample past it — the live log's maximum is 214.7 — but a *projection*
that assumed a chip week would be inventing one, so the clamp sits at the
ceiling the ordinary week can produce. v12 §3.3's "clamped to [0, 1]" is a
fraction-unit clamp on a percent quantity and would floor the whole instrument
at 1.0 (plan A4).
"""


def _samples_by_gw(frame: pd.DataFrame) -> dict[int, dict[int, float]]:
    """``{gw: {element: eo}}`` from each gameweek's latest snapshot day.

    The latest day per gameweek, for :func:`latest_field_eo`'s reason: a
    Saturday number beside a Sunday one is a pair nobody can reason about.
    """
    out: dict[int, dict[int, float]] = {}
    for gw, part in frame.groupby("gw"):
        day = max(str(d) for d in part["snap_date"])
        rows = part[part["snap_date"].astype(str) == day]
        out[int(gw)] = {int(r.element): float(r.eo) for r in rows.itertuples()}
    return out


def _pair_samples(by_gw: dict[int, dict[int, float]], want: int | None
                  ) -> tuple[int, int | None]:
    """``(gw, earlier_gw)`` — the two gameweeks whose samples are compared.

    **The grain decision, isolated to one function** (plan A4). The spec asks
    for two snapshot days of one gameweek; the log cannot hold them and the
    difference would not mean drift if it did, because picks are frozen after
    the deadline. Gameweek to gameweek is the only interval over which field
    ownership moves — and the only one anybody can observe, since next week's
    picks are not public until next week's deadline has passed.

    ``None`` for the earlier gameweek when there is no earlier sample, which
    is the whole of the "no trend" path.
    """
    if not by_gw:
        raise KeyError("no samples")
    gw = int(want) if want is not None else max(by_gw)
    if gw not in by_gw:
        raise KeyError(gw)
    earlier = [g for g in by_gw if g < gw]
    return gw, (max(earlier) if earlier else None)


def field_eo_trend(season: str, gw: int | None = None) -> dict[int, dict]:
    """``element -> {"eo_first", "eo_last", "delta", "gws_between",
    "deadline_eo", "trend_available"}`` for one season.

    v12 §3.3, at the gameweek grain the log actually has (plan A4).
    ``deadline_eo`` is ``eo_last`` plus one gameweek of the observed drift,
    clamped to ``[0, EO_CEILING]``. With no earlier sample there is no drift
    to project: ``trend_available`` is ``False``, ``delta`` is ``None`` — not
    ``0.0``, which is the different and stronger claim that the field did not
    move — and ``deadline_eo`` is ``eo_last`` unchanged.

    An element the earlier gameweek never sampled also gets no trend.
    ``eo_from_picks`` omits anyone no sampled entry started, so his absence
    means "nobody had him", and differencing against an implied zero would
    read every promoted bench player as a forty-point riser.

    ``season`` is required and positional: element ids are re-issued every
    August, and the same integer is a different footballer on the other side
    of a rollover. Empty dict on any failure at all, which is
    :func:`latest_field_eo`'s contract and for its reason — this is display.
    """
    try:
        log = load_field_eo()
    except Exception:  # noqa: BLE001 — a display read never blocks a page
        return {}
    if log is None or log.empty or "season" not in log.columns:
        return {}
    frame = log[log["season"].astype(str) == str(season)].copy()
    if frame.empty:
        return {}
    frame["gw"] = pd.to_numeric(frame["gw"], errors="coerce")
    frame = frame.dropna(subset=["gw"])
    if frame.empty:
        return {}
    by_gw = _samples_by_gw(frame)
    try:
        want, earlier = _pair_samples(by_gw, gw)
    except KeyError:
        return {}

    latest = by_gw[want]
    before = by_gw.get(earlier) if earlier is not None else None
    span = (want - earlier) if earlier is not None else 0
    out: dict[int, dict] = {}
    for element, eo_last in latest.items():
        eo_first = before.get(element) if before else None
        if eo_first is None or span <= 0:
            out[element] = {"eo_first": None, "eo_last": eo_last,
                            "delta": None, "gws_between": None,
                            "deadline_eo": eo_last, "trend_available": False}
            continue
        delta = round(eo_last - eo_first, 1)
        projected = round(min(EO_CEILING, max(0.0, eo_last + delta / span)), 1)
        out[element] = {"eo_first": eo_first, "eo_last": eo_last,
                        "delta": delta, "gws_between": int(span),
                        "deadline_eo": projected, "trend_available": True}
    return out
```

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_field_eo_trend.py tests/test_v8c_degradation.py
.venv/bin/pytest -q
```

`test_v8c_degradation.py` is **protected** and pins `latest_field_eo`'s
behaviour over fixtures with no `season` column. This task adds a function and
touches none of that; if it goes red, the append was not additive — **stop and
report**.

- [ ] **Commit.**

```bash
git add src/gaffer/data/field.py tests/test_v12_field_eo_trend.py \
  && git commit -m "$(cat <<'EOF'
feat: field EO trend, at the grain the log actually has

Spec §3.3 asks for a within-gameweek trend across two snapshot days and the
data cannot supply one. Three measured reasons: run_field_scrape exits on
_already_banked before it builds a client, so the Sunday plist never banks a
second sample (the live log is 123 rows, one gameweek, one day); picks are
frozen after the deadline, so two same-gameweek samples would differ only by
which ~300 entries were drawn; and EO is percent with captaincy doubled, so the
spec's clamp to [0, 1] would floor the whole instrument at 1.0.

There is a fourth fact that decides the grain: nobody's picks for the upcoming
gameweek are public before its deadline, so a "deadline EO" can only ever be an
extrapolation from one gameweek to the next. That is what this computes, and
the grain lives in one function so the day-grained version is a one-function
change if the data ever supports it.

No trend is None and never 0.0 — a zero delta is the field holding steady,
which is a measurement, and this is the absence of one.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 9 — `deadline_eo` on the two serve-time seams and on the page

**Files:**
- Modify `src/gaffer/web/routers/players.py` (`:149`, `:161-176`)
- Modify `src/gaffer/web/schemas.py` (`PlayerRow`, `:405-414`)
- Modify `src/gaffer/web/field_frame.py` (`:236-284`)
- Modify `frontend/src/types.ts` (`PlayerRow`)
- Modify `frontend/src/hubs/Players.tsx` (`:159-167`)
- Modify `frontend/src/hubs/Players.test.tsx`
- Create `tests/test_v12_deadline_eo_api.py`

**Read A5.** Both readers of the EO log are unprotected serve-time seams, and
the advice artifact's bytes do not change.

- [ ] **Write the failing test.** Create `tests/test_v12_deadline_eo_api.py`:

```python
"""``deadline_eo`` beside ``field_eo``, on both seams that read the EO log.

The rule both inherit from ``field_eo`` (schemas.py:405-414): **None means
unknown and never 0.0**. A projected ownership of zero is a real and different
statement — nobody in the top 10k starts him — and a page that printed it for
"we have one gameweek of samples" would be making a claim the log cannot back.
"""

from __future__ import annotations

import pytest

from gaffer.web import field_frame
from gaffer.web.routers import players as players_router

TREND = {
    100: {"eo_first": 40.0, "eo_last": 46.0, "delta": 6.0, "gws_between": 1,
          "deadline_eo": 52.0, "trend_available": True},
    200: {"eo_first": None, "eo_last": 12.0, "delta": None,
          "gws_between": None, "deadline_eo": 12.0,
          "trend_available": False},
}


def test_the_row_carries_the_projection_and_the_delta(monkeypatch):
    monkeypatch.setattr(players_router, "field_eo_trend", lambda s, g: TREND)
    row = players_router._trend_fields(TREND, 100)
    assert row == {"field_eo_deadline": 52.0, "field_eo_delta": 6.0}


def test_no_trend_is_null_on_both_fields_and_never_zero(monkeypatch):
    assert players_router._trend_fields(TREND, 200) == {
        "field_eo_deadline": None, "field_eo_delta": None}


def test_an_element_the_trend_never_saw_is_null_too():
    assert players_router._trend_fields(TREND, 999) == {
        "field_eo_deadline": None, "field_eo_delta": None}


def test_an_unreadable_trend_costs_the_columns_and_not_the_page(monkeypatch):
    def boom(season, gw):
        raise OSError("log is a directory today")

    monkeypatch.setattr(players_router, "field_eo_trend", boom)
    assert players_router._trend_table(3, "2026-27") == {}


def test_the_captain_frame_carries_the_projection(monkeypatch):
    monkeypatch.setattr(field_frame, "_field_table",
                        lambda gw: {100: {"eo": 46.0, "se": 2.0, "n": 300,
                                          "gw": 3}})
    monkeypatch.setattr(field_frame, "_trend_table", lambda gw: TREND)
    monkeypatch.setattr(field_frame, "_elements_by_code", lambda: {55: 100})
    monkeypatch.setattr(field_frame, "_modal_captain", lambda gw: None)
    out = field_frame.with_field_frame(
        {"captain": {"code": 55, "name": "Salah"}}, 3)
    assert out["captain_field"]["deadline_eo"] == 52.0
    assert out["captain_field"]["eo_delta"] == 6.0


def test_the_captain_frame_is_absent_when_there_is_nothing_to_say(
        monkeypatch):
    """Task 2 of v10b's rule, kept: the key is absent, not null."""
    monkeypatch.setattr(field_frame, "_field_table", lambda gw: {})
    monkeypatch.setattr(field_frame, "_trend_table", lambda gw: {})
    monkeypatch.setattr(field_frame, "_elements_by_code", lambda: {55: 100})
    monkeypatch.setattr(field_frame, "_modal_captain", lambda gw: None)
    payload = {"captain": {"code": 55, "name": "Salah"}}
    assert field_frame.with_field_frame(payload, 3) == payload
```

Run it: `.venv/bin/pytest -q tests/test_v12_deadline_eo_api.py` — fails,
`AttributeError: … has no attribute '_trend_fields'`.

- [ ] **Implement the schema.** In `src/gaffer/web/schemas.py`'s `PlayerRow`,
beside `field_se`/`field_n`:

```python
    # v12 W2 §3.3 (specs/2026-09-01-gaffer-v12-program-design.md, plan A4/A5).
    field_eo_deadline: float | None = None
    """Field EO projected forward one gameweek, in percent.

    ``None`` means *no trend*, which is what one gameweek of samples buys —
    and never 0.0, which is the different and stronger claim that nobody in
    the top 10k starts him. Same contract as ``field_eo`` above.
    """
    field_eo_delta: float | None = None
    """The observed move between the last two sampled gameweeks, in points of
    EO. ``None`` when there is no earlier sample; ``0.0`` is a measurement —
    the field held steady."""
```

- [ ] **Implement the players router.** In
`src/gaffer/web/routers/players.py`, add the import beside
`latest_field_eo` (`:17`) and two helpers above the route body:

```python
from gaffer.data.field import field_eo_trend, latest_field_eo


def _trend_table(gw: int | None, season: str) -> dict[int, dict]:
    """v12 §3.3's trend, or an empty map. Display, so it never raises."""
    try:
        return field_eo_trend(season, gw)
    except Exception as exc:  # noqa: BLE001 — a column is not worth a 500
        print(f"players: field EO trend unreadable ({exc})")
        return {}


def _trend_fields(trend: dict[int, dict], element: int) -> dict:
    """The two additive fields for one element.

    ``None`` on both whenever there is no trend, rather than falling back to
    ``eo_last``: the row already carries ``field_eo``, and repeating it under
    a name that says "deadline" would make a projection out of a measurement.
    """
    cell = trend.get(int(element)) or {}
    if not cell.get("trend_available"):
        return {"field_eo_deadline": None, "field_eo_delta": None}
    return {"field_eo_deadline": cell["deadline_eo"],
            "field_eo_delta": cell["delta"]}
```

In the route body, beside the existing `latest_field_eo` call (`:149`, which
W1 §2.3 has already given `season=current_season`), add:

```python
    trend = _trend_table(first_gw, season)
```

and in the `PlayerRow(...)` construction (`:173-176`), after `field_n`:

```python
            **_trend_fields(trend, int(r.element)),
```

Use the same `season` local W1's edit introduced at `:149`; if that call still
reads the season inline, hoist it to a local first so the two reads cannot
disagree.

- [ ] **Implement the captain frame.** In `src/gaffer/web/field_frame.py`, a
`_trend_table` beside `_field_table` (`:174-199`), sharing its season guard:

```python
def _trend_table(gw: int) -> dict[int, dict]:
    """v12 §3.3's trend for this season, or an empty map.

    Guard 3 again, and the same failure it always was: element ids are
    re-issued every August, so an unseasoned read frames the captain against
    a footballer who has since left the game.
    """
    try:
        from gaffer.config import load_config

        season = load_config().current_season
    except Exception as exc:  # noqa: BLE001 — a clone with no config.toml
        print(f"field_frame: no configured season, no EO trend ({exc})")
        return {}
    try:
        from gaffer.data.field import field_eo_trend

        return field_eo_trend(season, gw)
    except Exception as exc:  # noqa: BLE001
        print(f"field_frame: EO trend unreadable ({exc})")
        return {}
```

and in `with_field_frame`, inside the `else` branch that builds `frame`
(`:266-275`), after `field_class` is computed:

```python
            # v12 W2 §3.3 (specs/2026-09-01-gaffer-v12-program-design.md).
            # Absent-not-null does not apply *inside* the key: the key already
            # exists because there is an EO to report, and a null projection
            # beside a real EO is the honest reading of one gameweek of
            # samples.
            cell = _trend_table(gw).get(element) or {}
            frame["deadline_eo"] = (cell.get("deadline_eo")
                                    if cell.get("trend_available") else None)
            frame["eo_delta"] = (cell.get("delta")
                                 if cell.get("trend_available") else None)
```

- [ ] **Implement the page.** In `frontend/src/types.ts`, on `PlayerRow`:

```ts
  /** Field EO projected one gameweek forward, in percent. Null means no
   *  trend — one gameweek of samples — and never 0. */
  field_eo_deadline: number | null
  field_eo_delta: number | null
```

and on the `captain_field` interface, `deadline_eo: number | null` and
`eo_delta: number | null`.

In `frontend/src/hubs/Players.tsx`, the `field_eo` column (`:159-167`) gains
the arrow, and **only when there is a trend**:

```tsx
    { key: 'field_eo', header: 'Field%', numeric: true,
      value: (r) => r.field_eo,
      render: (r) => (r.field_eo === null ? '—' : (
        <span>
          {fmtNum(r.field_eo, 1)}
          {r.field_eo_delta !== null && (
            // The arrow is the sign and the title is the number. A delta drawn
            // as a second figure in the cell would read as a second ownership.
            <span className="ml-1 text-text-muted"
                  title={`${r.field_eo_delta > 0 ? '+' : ''}`
                    + `${fmtNum(r.field_eo_delta, 1)} since the last sampled `
                    + `gameweek; projected ${fmtNum(r.field_eo_deadline, 1)}%`}
                  data-testid={`eo-trend-${r.code}`}>
              {r.field_eo_delta > 0 ? '↑'
                : (r.field_eo_delta < 0 ? '↓' : '→')}
            </span>
          )}
          {r.field_class && (
            <span className="ml-1 text-text-muted">{r.field_class}</span>
          )}
        </span>
      )) },
```

- [ ] **Write the frontend test.** In `frontend/src/hubs/Players.test.tsx`,
beside the existing field-EO assertions:

```tsx
  it('draws an EO arrow only where a trend exists', async () => {
    // One gameweek of samples is the ordinary state for most of a season's
    // first month, and an arrow there would be drawn from nothing.
    renderPlayers([
      { ...ROW, code: 1, field_eo: 46, field_eo_delta: 6,
        field_eo_deadline: 52 },
      { ...ROW, code: 2, field_eo: 12, field_eo_delta: null,
        field_eo_deadline: null },
    ])
    expect(await screen.findByTestId('eo-trend-1')).toHaveTextContent('↑')
    expect(screen.queryByTestId('eo-trend-2')).toBeNull()
  })
```

Match `renderPlayers`/`ROW` to whatever the file's existing fixture helpers
are called; if it has none, follow the shape of the nearest existing test in
that file rather than inventing a second harness.

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_deadline_eo_api.py tests/test_web_players.py \
  tests/test_v10b_degradation.py
.venv/bin/pytest -q
cd frontend && npx vitest run && npx tsc --noEmit
```

`tests/test_v10b_degradation.py` is **protected** and pins `field_frame`'s
absent-not-null contract. This task adds keys *inside* a frame that already
exists and adds none when the frame is absent; if it goes red, **stop and
report**.

- [ ] **Commit.**

```bash
git add src/gaffer/web/routers/players.py src/gaffer/web/schemas.py \
  src/gaffer/web/field_frame.py frontend/src/types.ts \
  frontend/src/hubs/Players.tsx frontend/src/hubs/Players.test.tsx \
  tests/test_v12_deadline_eo_api.py && git commit -m "$(cat <<'EOF'
feat: the projected deadline EO beside the sampled one

Both readers of the EO log are unprotected serve-time seams — the explorer's
row and the captain framing that exists precisely because advise.py is not one
— so the projection reaches the page without a re-solve and the banked advice
artifacts keep their bytes.

Null means no trend and never 0.0, which is field_eo's own standing contract: a
projected ownership of zero says nobody in the top 10k starts him, and one
gameweek of samples cannot say that. The arrow is drawn only where a trend
exists, which for most of a season's first month is nowhere.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 10 — **STOP** — the price-timing term (`optimize/milp.py`, spec §3.4)

> **STOP. Do not begin this task until the orchestrator has read the
> enumeration below and authorized it.** `src/gaffer/optimize/milp.py` is a
> protected file. Spec §3.4 authorizes "one term"; this is that term, in three
> line-groups, with every other line of the file untouched.

**Files:**
- Create `src/gaffer/price_timing.py` (unprotected)
- Modify `src/gaffer/config.py` (one module-level reader)
- Modify `config.example.toml`
- **Modify `src/gaffer/optimize/milp.py` — PROTECTED, three line-groups**
- Create `tests/test_v12_price_timing.py`

**Read A6 and A8 before authorizing.** The term is worth 0.008 points at the
shipped `itb_value = 0.08` and HiGHS's default relative gap on a real horizon
is around 0.02. It is a tie-breaker. Shipping it is still right — it is the
correct sign on a real cost and it decides exact ties, which is where EP-equal
sell timings actually live — but nobody should expect the replay to move, and
**the flag therefore defaults off** (ruling, 2026-09-02).

**Two consequences of that ruling for this task.** The default-off flag means
`owned_price_falls` returns `{}` on every stock configuration, so Group 3's
term is arithmetically absent unless a user opts in — which makes the
`price_fall=None`/`{}` byte-identity test below the *shipped* path rather than
an edge case. And the knob lives in **`[optimizer]`**, which `load_config`
splats wholesale, so this task also pops it before the splat or the next
`gaffer advise` dies of `TypeError` (A8).

### The enumeration

**Group 1 — `solve_plan`, `milp.py:412-416`.** The lookup is built here, once,
rather than on `SolveInput`, because `SolveInput` is constructed in
`advise.py`, `backtest.py`, `chips.py`, `policy.py`, `scenarios.py`,
`calibrate_decisions.py` and `routers/whatif.py` — two of which are protected.
Reading it at the seam is `serving_config`'s pattern (`config.py:251-273`).

*Before:*

```python
    kw = dict(decay=decay, bench_weight=bench_weight,
              vice_weight=vice_weight, ft_value=ft_value,
              itb_value=itb_value, hit_cost=hit_cost,
              fixed_moves=fixed_moves, ft_lambda=ft_lambda,
              ft_use_penalty=ft_use_penalty, bench_curve=bench_curve)
```

*After:*

```python
    # v12 W2 §3.4 (specs/2026-09-01-gaffer-v12-program-design.md). Read here
    # rather than carried on SolveInput: seven call sites construct one and
    # two of them are protected files. Empty dict when the switch is off, the
    # log is missing, or nothing is near a threshold — and an empty dict makes
    # every expression below arithmetically today's.
    from gaffer.price_timing import owned_price_falls

    kw = dict(decay=decay, bench_weight=bench_weight,
              vice_weight=vice_weight, ft_value=ft_value,
              itb_value=itb_value, hit_cost=hit_cost,
              fixed_moves=fixed_moves, ft_lambda=ft_lambda,
              ft_use_penalty=ft_use_penalty, bench_curve=bench_curve,
              price_fall=owned_price_falls(state.owned_codes))
```

**Group 2 — `_solve_once`'s signature, `milp.py:441`.** One defaulted keyword,
after `p_play` and before the `_decision_scales` block, so pass two's call
(`:422-423`) reaches it through `**kw` unchanged.

*Before:*

```python
                p_play: dict[int, dict[int, float]] | None = None,
```

*After:*

```python
                p_play: dict[int, dict[int, float]] | None = None,
                price_fall: dict[int, float] | None = None,
```

**Group 3 — the objective, `milp.py:631`.** Inserted immediately after the hit
term, inside the existing `for t in T:` loop.

*Before:*

```python
        obj.append(-hit_cost * d * hits[t])
```

*After:*

```python
        obj.append(-hit_cost * d * hits[t])
        # v12 W2 §3.4 (specs/2026-09-01-gaffer-v12-program-design.md). Selling
        # a falling player next week instead of this week loses 0.1m of his
        # sale, which the objective already prices at itb_value per million
        # (see the bank term below). So a deferred sale is charged exactly
        # that, weighted by tonight's fall probability. No term for a rise:
        # spec §8 and the ROADMAP both name price chasing as rejected.
        #
        # Undecayed, deliberately, like the bank term it is denominated
        # against: the money is lost at the moment of the sale and the
        # horizon's decay is about the value of *points* later, not of pounds.
        #
        # It is a tie-breaker and not a driver, and the magnitude says so:
        # 0.008 points at the shipped itb_value of 0.08, against a solver
        # whose default relative gap on a real horizon is around 0.02. It
        # decides exactly-equal sell timings, which is where the question
        # actually arises, and it will not move a plan that has any real EP
        # difference in it (plan A6).
        if price_fall and t != T[0]:
            for c in codes:
                p = price_fall.get(c)
                if p:
                    obj.append(-p * 0.1 * itb_value * tout[c][t])
```

**Nothing else in `milp.py` changes.** In particular `_solve` (`:714-725`) is
not touched: tightening the solver's gap to make one epsilon decidable would
change every solve in the tree.

### The rest of the task

- [ ] **Write the failing test.** Create `tests/test_v12_price_timing.py`:

```python
"""Spec §3.4: a deferred sale of a falling player is charged the fall.

Two levels, because the term is smaller than the solver's own tolerance on a
real problem (plan A6). The coefficient test is exact and gap-free; the
behavioural test sets itb_value high enough in its own fixture that the charge
is half a point, and says so, because a test that depended on HiGHS resolving
0.008 would be testing the solver's mood.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer import price_timing
from gaffer.optimize import milp


def test_a_falling_owned_player_gets_his_predictor_reading_as_a_probability():
    log = pd.DataFrame({
        "snap_date": ["2026-09-01"] * 3,
        "code": [1, 2, 3],
        "now_cost": [80, 75, 60],
        "price_change_percent": [-95.0, -40.0, 88.0],
        "direction": ["drop", "drop", "rise"],
        "calibrating": [False, False, False]})
    out = price_timing.price_falls(log, [1, 2, 3])
    assert out[1] == 0.95
    assert out[2] == 0.4
    assert 3 not in out          # a rise is never charged (spec §8)


def test_a_calibrating_reading_is_not_a_probability():
    """``calibrating`` exists to say the log is not yet trustworthy, and a
    charge levied off an untrustworthy reading is worse than none —
    ``routers/prices.py``'s own rule for the movers panel."""
    log = pd.DataFrame({"snap_date": ["2026-09-01"], "code": [1],
                        "now_cost": [80], "price_change_percent": [-95.0],
                        "direction": ["drop"], "calibrating": [True]})
    assert price_timing.price_falls(log, [1]) == {}


def test_only_the_newest_day_is_read():
    log = pd.DataFrame({
        "snap_date": ["2026-08-31", "2026-09-01"],
        "code": [1, 1], "now_cost": [80, 80],
        "price_change_percent": [-95.0, -10.0],
        "direction": ["drop", "drop"], "calibrating": [False, False]})
    assert price_timing.price_falls(log, [1]) == {1: 0.1}


def test_a_reading_past_the_threshold_is_clamped_to_one():
    log = pd.DataFrame({"snap_date": ["2026-09-01"], "code": [1],
                        "now_cost": [80], "price_change_percent": [-129.9],
                        "direction": ["drop"], "calibrating": [False]})
    assert price_timing.price_falls(log, [1]) == {1: 1.0}


def test_an_unowned_player_is_not_in_the_table():
    log = pd.DataFrame({"snap_date": ["2026-09-01"], "code": [9],
                        "now_cost": [80], "price_change_percent": [-95.0],
                        "direction": ["drop"], "calibrating": [False]})
    assert price_timing.price_falls(log, [1, 2]) == {}


def test_the_switch_is_off_by_default_and_lives_under_optimizer(tmp_path):
    """Off, against spec §3.4's `true`: CONVENTIONS §6, and the flip rule is
    in the gate. Under [optimizer] and not [solver]: program ruling."""
    from gaffer.config import price_timing as read_flag

    on = tmp_path / "on.toml"
    on.write_text("[optimizer]\nprice_timing = true\n")
    off = tmp_path / "off.toml"
    off.write_text("[optimizer]\nhorizon = 3\n")
    assert read_flag(on) is True
    assert read_flag(off) is False
    assert read_flag(tmp_path / "nothing.toml") is False
    stale = tmp_path / "stale.toml"
    stale.write_text("[solver]\nprice_timing = true\n")
    # A key in a section this project does not have is not a switch.
    assert read_flag(stale) is False


def test_the_flag_does_not_reach_the_config_constructor(tmp_path):
    """The grenade the [optimizer] ruling armed: that section is splatted
    wholesale, so an unpopped knob is a TypeError out of Config.__init__ on
    the next advise run — for anyone who copies config.example.toml."""
    from gaffer.config import load_config

    path = tmp_path / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n\n"
                    "[optimizer]\nhorizon = 3\nprice_timing = true\n")
    cfg = load_config(path)
    assert cfg.horizon == 3
    assert not hasattr(cfg, "price_timing")


def test_w1s_top_n_still_travels_through_the_splat(tmp_path):
    """The other half of the pop list, and the expensive mistake it prevents.

    W1 §2.6 ships ``top_n`` as a real Config field read through
    ``optimizer_top_n()``. Popping it beside ``price_timing`` would strip a
    configured pool size out of the constructor and hand every user the
    dataclass default — silently, because a smaller pool is a valid solve.
    A key belongs in NON_FIELD_OPTIMIZER_KEYS only when Config has no field
    of that name.
    """
    import dataclasses

    from gaffer.config import NON_FIELD_OPTIMIZER_KEYS, Config, load_config

    names = {f.name for f in dataclasses.fields(Config)}
    assert not (set(NON_FIELD_OPTIMIZER_KEYS) & names)

    path = tmp_path / "config.toml"
    path.write_text(
        "[fpl]\nentry_id = 1\nleague_id = 2\n\n[optimizer]\n"
        "top_n = {GKP = 4, DEF = 5, MID = 6, FWD = 7}\nprice_timing = true\n")
    cfg = load_config(path)
    assert cfg.top_n["MID"] == 6


def test_a_typo_under_optimizer_still_raises_loudly(tmp_path):
    """Why the pop is a named list and not a fields(Config) filter: a silently
    ignored `horizen = 6` is a season of quietly wrong advice."""
    from gaffer.config import load_config

    path = tmp_path / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n\n"
                    "[optimizer]\nhorizen = 6\n")
    with pytest.raises(TypeError):
        load_config(path)


def test_the_switch_off_is_an_empty_table(monkeypatch):
    monkeypatch.setattr(price_timing, "price_timing_enabled", lambda: False)
    monkeypatch.setattr(price_timing, "load_price_log",
                        lambda: pd.DataFrame({
                            "snap_date": ["2026-09-01"], "code": [1],
                            "now_cost": [80], "price_change_percent": [-95.0],
                            "direction": ["drop"], "calibrating": [False]}))
    assert price_timing.owned_price_falls([1]) == {}


def test_a_missing_price_log_costs_the_term_and_not_the_solve(monkeypatch):
    def boom():
        raise OSError("no price log on this machine")

    monkeypatch.setattr(price_timing, "price_timing_enabled", lambda: True)
    monkeypatch.setattr(price_timing, "load_price_log", boom)
    assert price_timing.owned_price_falls([1]) == {}


# --- the objective ------------------------------------------------------

def _pool():
    """Fifteen buildable players plus one alternative, all EP-equal."""
    rows = []
    positions = ["GKP"] * 2 + ["DEF"] * 5 + ["MID"] * 5 + ["FWD"] * 4
    for i, pos in enumerate(positions):
        rows.append({"code": i + 1, "position": pos, "team_code": i % 6,
                     "cost": 40.0, "sell": 40.0,
                     "ep": {5: 1.0, 6: 1.0}})
    return pd.DataFrame(rows)


def _state(pool):
    return milp.SolveInput(owned_codes=list(pool["code"])[:15], bank=100,
                           free_transfers=2, gws=[5, 6])


def test_the_charge_lands_on_the_objective_with_the_specified_coefficient(
        monkeypatch):
    """The exact assertion. The built problem carries one term per (owned,
    later gameweek) at p x 0.1 x itb_value, and none in the first week."""
    captured = {}

    def spy(prob):
        captured["obj"] = str(prob.objective)
        raise RuntimeError("stop here — the built problem is the assertion")

    pool = _pool()
    monkeypatch.setattr(milp, "_solve", spy)
    with pytest.raises(RuntimeError):
        milp._solve_once(pool, _state(pool), decay=1.0, bench_weight=0.1,
                         vice_weight=0.1, ft_value=1.5, itb_value=0.08,
                         hit_cost=4, price_fall={1: 1.0})
    # 1.0 x 0.1 x 0.08 = 0.008, on out_1_6 and on nothing in week 5.
    assert "0.008*out_1_6" in captured["obj"].replace(" ", "")
    assert "out_1_5" not in captured["obj"].replace(" ", "").replace(
        "0.008*out_1_6", "")


def test_with_the_charge_large_enough_to_beat_the_gap_the_sale_moves_forward(
        monkeypatch):
    """Spec §3.4's own test, at a knob setting where the solver must respect
    it: itb_value = 5.0 makes the charge 0.5 points. At the shipped 0.08 the
    charge is 0.008 and HiGHS's default relative gap on a real horizon is
    larger than that — which is a fact about the term's size, recorded in the
    plan (A6), not a fact this test can paper over."""
    pool = _pool()
    state = _state(pool)
    plan = milp.solve_plan(pool, state, decay=1.0, bench_weight=0.1,
                           vice_weight=0.1, ft_value=0.0, itb_value=5.0,
                           hit_cost=4, price_fall={1: 1.0})
    assert 1 not in plan.gw_plans[1].squad or 1 in plan.gw_plans[0].sells


def test_no_price_fall_leaves_the_problem_byte_identical(monkeypatch):
    """The degradation direction: an empty table must reproduce today's
    objective exactly, so a machine with no price log solves what it always
    did."""
    captured = []

    def spy(prob):
        captured.append(str(prob.objective))
        raise RuntimeError("stop")

    pool = _pool()
    monkeypatch.setattr(milp, "_solve", spy)
    for fall in (None, {}):
        with pytest.raises(RuntimeError):
            milp._solve_once(pool, _state(pool), decay=1.0, bench_weight=0.1,
                             vice_weight=0.1, ft_value=1.5, itb_value=0.08,
                             hit_cost=4, price_fall=fall)
    assert captured[0] == captured[1]
```

If `solve_plan`'s two-pass path makes the behavioural test slow or
non-deterministic, call `milp._solve_once` directly there — the term lives in
`_solve_once` and pass two inherits it through `**kw`. **Do not** relax the
assertion to "the objective is lower".

`test_w1s_top_n_still_travels_through_the_splat` writes `top_n` in the shape
W1 §2.6 specifies (`{GKP, DEF, MID, FWD}`). **Read W1's shipped field before
running it** and match the TOML to whatever W1 actually banked; the assertion
that must survive any shape change is the first one — that no name in
`NON_FIELD_OPTIMIZER_KEYS` is also a `Config` field.

- [ ] **Implement the config reader.** Append to `src/gaffer/config.py`,
following `lineup_providers` (`:221-248`) in shape:

```python
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
    """``[optimizer] price_timing`` (v12 §3.4). Default **off**.

    Off, against spec §3.4's ``true``, by the coordinator's 2026-09-02 ruling:
    CONVENTIONS §6 says an arm that cannot demonstrate an effect ships behind
    its flag, and this term is 0.008 points against a solver gap of about 0.02
    (plan A6). The flip rule is pre-registered in the W2 gate rather than left
    to taste.

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
        return False
    return bool(raw.get("optimizer", {}).get("price_timing", False))
```

and the splat guard in `load_config` (`config.py:143-147`):

*Before:*

```python
    return Config(
        entry_id=raw["fpl"]["entry_id"],
        league_id=raw["fpl"]["league_id"],
        **raw.get("optimizer", {}),
```

*After:*

```python
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
```

**Check W1's shipped `load_config` first.** W1 §2.6 makes `top_n` a real field
splatted from this same section, so it needs no filter and is expected to have
added none. If it nonetheless left one, **add `price_timing` to that filter
and change nothing else** — two comprehensions over one dict is how the second
ends up in front of the first — and **never add `top_n` to either**: popping a
key that *is* a field strips a configured pool size out of the constructor and
hands every user the dataclass default in silence.

- [ ] **Implement the seam.** Create `src/gaffer/price_timing.py`:

```python
"""Tonight's price fall, per owned player, for the objective's timing term.

``price_log.py`` has been banking every player's predictor reading nightly
since v10b and its own docstring says why: *"the log is being accrued now so
that a future cycle has a season of it to justify a price-timing term with;
today it is banked and read by nobody, which is the correct order to do that
in."* This is that cycle, and this is the reader.

**What the number is.** ``price_change_percent`` is FPL's own progress toward
the nightly 00:00 change; it reaches ±100 at the change itself and the live
log holds values past it (min -129.9). Read as a probability of falling
tonight it is ``min(1, |pct| / 100)`` on a ``drop``, and nothing at all
otherwise — a rise is never charged, because spec §8 and the ROADMAP both name
price chasing as rejected, and a ``flat`` or null reading is the predictor
declining to say.

``calibrating`` rows are dropped whole. The field exists to say the log is not
yet trustworthy, and ``routers/prices.py`` already suppresses its warnings on
it; a charge levied off an untrustworthy reading is worse than no charge,
because the solver cannot see the caveat.

Nothing here raises. It is read on the solve path and a missing log, a corrupt
log or a machine that has never run ``gaffer prices`` must cost the term and
nothing else.
"""

from __future__ import annotations

import pandas as pd

from gaffer.config import price_timing as price_timing_enabled
from gaffer.price_log import load_price_log


def price_falls(log: pd.DataFrame,
                owned: list[int] | None) -> dict[int, float]:
    """``{code: P(falls tonight)}`` over the newest banked day.

    The newest day only: a reading from Tuesday is not evidence about
    Thursday night, and the log keeps every day precisely so that "the newest"
    is a choice somebody made rather than the only row there is.
    """
    if log is None or log.empty or not owned:
        return {}
    frame = log.copy()
    day = max(str(d) for d in frame["snap_date"])
    frame = frame[frame["snap_date"].astype(str) == day]
    frame = frame[frame["code"].isin([int(c) for c in owned])]
    if "calibrating" in frame.columns:
        frame = frame[~frame["calibrating"].fillna(False).astype(bool)]
    if frame.empty:
        return {}
    pct = pd.to_numeric(frame["price_change_percent"], errors="coerce")
    falling = frame[pct.notna() & (pct < 0)]
    out = {}
    for code, value in zip(falling["code"],
                           pd.to_numeric(falling["price_change_percent"],
                                         errors="coerce")):
        out[int(code)] = round(min(1.0, abs(float(value)) / 100.0), 3)
    return out


def owned_price_falls(owned: list[int] | None) -> dict[int, float]:
    """:func:`price_falls` over the banked log, behind the switch.

    Empty dict on the switch being off, on no log, on a corrupt log and on a
    log with nothing near a threshold — and an empty dict makes the objective
    term arithmetically absent, which is what keeps a machine with no price
    log solving exactly what it always did.
    """
    try:
        if not price_timing_enabled():
            return {}
        return price_falls(load_price_log(), owned)
    except Exception as exc:  # noqa: BLE001 — never blocks a solve
        print(f"price timing: no charge applied ({exc})")
        return {}
```

- [ ] **Implement the config example.** In `config.example.toml`, inside the
**existing `[optimizer]` section** (`:5-14`), under `itb_value` so the two
numbers that multiply each other are read together. There is no `[solver]`
section and none is to be created — program ruling, 2026-09-02:

```toml
# Charge a deferred sale the price it is expected to lose overnight (v12 §3.4).
# Worth p(fall) x 0.1m x itb_value, so about 0.008 points at the itb_value
# above — below the solver's own optimality gap on a full horizon. It breaks
# exactly-equal sell timings and moves nothing else, which is why it ships off
# (CONVENTIONS §6) with a pre-registered flip rule in the W2 gate. No term for
# rises: price chasing is rejected (ROADMAP).
price_timing = false
```

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_price_timing.py
.venv/bin/pytest -q -k config          # the [optimizer] splat guard
.venv/bin/pytest -q tests/test_optimize.py tests/test_advise.py \
  tests/test_web_whatif.py
.venv/bin/pytest -q
git diff --stat src/gaffer/optimize/milp.py    # expect exactly the 3 groups
```

Any pre-existing optimizer test that changes verdict means the term is not
inert with an empty table: **stop and report**.

- [ ] **Commit.**

```bash
git add src/gaffer/optimize/milp.py src/gaffer/price_timing.py \
  src/gaffer/config.py config.example.toml tests/test_v12_price_timing.py \
  && git commit -m "$(cat <<'EOF'
feat: charge a deferred sale the price it is expected to lose (spec §3.4)

Three authorized line-groups in milp.py, each carrying its provenance comment:
the lookup built at solve_plan, one defaulted keyword on _solve_once, and the
term itself beside the hit cost. Everything else in the file is untouched, and
an empty lookup reproduces today's objective exactly.

The lookup is read at the seam rather than carried on SolveInput because seven
call sites construct one and two of them are protected files — serving_config's
pattern, for serving_config's reason.

The size is stated in the code rather than left to be discovered: 0.008 points
at the shipped itb_value, against a solver whose default relative gap on a real
horizon is around 0.02. It is a tie-breaker for exactly-equal sell timings, and
the replay is expected to show no diff at all — so the flag ships off, with the
flip rule pre-registered in the gate rather than decided after the numbers.

The knob is [optimizer] price_timing and not a section of its own, which is the
program ruling and also a trap: load_config splats [optimizer] wholesale, so an
unpopped knob is a TypeError out of Config.__init__ for anyone who copies the
example file. Popped by name, so a typo under [optimizer] still raises.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 11 — the xG-per-shot columns, built always, fed only behind the flag

**Files:**
- Modify `src/gaffer/features/engineer.py` (beside
  `understat_feature_columns`, `:876-922`)
- Modify `src/gaffer/models/train.py` (`attach_understat` `:232`, `train_all`
  `:491`)
- Modify `src/gaffer/config.py` (one module-level reader)
- Modify `config.example.toml`
- Create `tests/test_v12_xg_per_shot.py`

**Read A7.** It is eight columns, not one, and the flag gates what the
attacking model is *told*, not what is built — the withdrawn v8a arms' rule
(`train.py:100-103`: "the columns cost a fit nothing").

- [ ] **Write the failing test.** Create `tests/test_v12_xg_per_shot.py`:

```python
"""Spec §3.5's feature: non-penalty xG per shot, per Understat window.

The spec writes it as ``us_npxg90 / us_shots90``. Neither column exists:
``add_understat_rolling`` produces ``us_npxg90_r{w}`` and ``us_shots90_r{w}``
for w in [3, 5, 10, 38] (engineer.py:857-879). Both are per-90 rates over the
*same* window, so their ratio is genuinely xG per shot at that window, and
there are four of them.

Zero with a missing indicator, per the spec, and the indicator is what makes
the zero readable: a player with no shots in the window has an undefined rate,
not a bad one, and LightGBM cannot tell a real 0.00 from a filled one without
being told.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from gaffer.features.engineer import (US_WINDOWS, XG_PER_SHOT_FEATURES,
                                      add_xg_per_shot, feature_columns)


def _frame(npxg, shots):
    cols = {}
    for w in US_WINDOWS:
        cols[f"us_npxg90_r{w}"] = npxg
        cols[f"us_shots90_r{w}"] = shots
    return pd.DataFrame(cols)


def test_the_ratio_is_built_for_every_understat_window():
    out = add_xg_per_shot(_frame([0.6], [4.0]))
    for w in US_WINDOWS:
        assert out[f"us_npxg_per_shot_r{w}"].iloc[0] == 0.15
        assert out[f"us_npxg_per_shot_missing_r{w}"].iloc[0] == 0.0


def test_no_shots_is_zero_with_the_indicator_raised():
    out = add_xg_per_shot(_frame([0.0], [0.0]))
    assert out["us_npxg_per_shot_r5"].iloc[0] == 0.0
    assert out["us_npxg_per_shot_missing_r5"].iloc[0] == 1.0


def test_a_null_window_is_missing_and_not_a_division_by_nothing():
    """A window with no minutes at all yields NaN from the rolling rate
    (engineer.py:912-913), which is 'we have no shot data', not 'no shots'."""
    out = add_xg_per_shot(_frame([np.nan], [np.nan]))
    assert out["us_npxg_per_shot_r5"].iloc[0] == 0.0
    assert out["us_npxg_per_shot_missing_r5"].iloc[0] == 1.0


def test_a_frame_with_no_understat_columns_still_gets_every_column():
    """The model's feature schema must not depend on whether the scrape ran —
    add_understat_rolling's own contract, inherited."""
    out = add_xg_per_shot(pd.DataFrame({"code": [1, 2]}))
    for col in XG_PER_SHOT_FEATURES:
        assert col in out.columns
        assert out[col].notna().all()


def test_the_columns_are_in_feature_columns_so_a_re_derive_strips_them():
    """``advise.py:548`` strips ``feature_columns()`` off the training frame
    before re-deriving; a column left behind would be a stale one."""
    cols = set(feature_columns())
    assert set(XG_PER_SHOT_FEATURES) <= cols


def test_the_attacking_model_is_told_only_when_the_flag_is_on(monkeypatch,
                                                              tmp_path):
    from gaffer.config import xg_per_shot
    from gaffer.models import train as tr

    off = tmp_path / "off.toml"
    off.write_text("[model]\nxg_per_shot = false\n")
    on = tmp_path / "on.toml"
    on.write_text("[model]\nxg_per_shot = true\n")
    assert xg_per_shot(off) is False
    assert xg_per_shot(on) is True

    monkeypatch.setattr(tr, "xg_per_shot", lambda: False)
    assert set(tr.attacking_features()) & set(XG_PER_SHOT_FEATURES) == set()
    monkeypatch.setattr(tr, "xg_per_shot", lambda: True)
    assert set(XG_PER_SHOT_FEATURES) <= set(tr.attacking_features())


def test_the_flag_defaults_off_and_survives_a_missing_file(tmp_path):
    from gaffer.config import xg_per_shot

    assert xg_per_shot(tmp_path / "nothing.toml") is False
    broken = tmp_path / "broken.toml"
    broken.write_text("[model\nxg_per_shot = true")
    assert xg_per_shot(broken) is False
```

Run it: `.venv/bin/pytest -q tests/test_v12_xg_per_shot.py` — fails on the
import of `XG_PER_SHOT_FEATURES`.

- [ ] **Implement the features.** In `src/gaffer/features/engineer.py`, after
`understat_feature_columns` (`:876-879`):

```python
XG_PER_SHOT_FEATURES = (
    [f"us_npxg_per_shot_r{w}" for w in US_WINDOWS]
    + [f"us_npxg_per_shot_missing_r{w}" for w in US_WINDOWS])
"""v12 §3.5's arm: shot *quality*, beside the shot volume already fed in.

Eight columns and not one. The spec writes the feature as ``us_npxg90 /
us_shots90``; both are windowed, and a ratio of two per-90 rates over the same
window is xG per shot at that window, so there is one per window — with a
missing indicator each, because a player with no shots has an undefined rate
rather than a bad one."""


def add_xg_per_shot(df: pd.DataFrame) -> pd.DataFrame:
    """Non-penalty xG per shot per Understat window, with missing indicators.

    ``0.0`` where the ratio is undefined — no shots, or a window with no
    minutes in it — with the indicator raised, which is the pairing that makes
    the zero readable: LightGBM splits on the indicator and never has to guess
    whether a 0.00 was measured or filled.

    Every column is created even on a frame with no Understat columns at all,
    so the model's feature schema does not depend on whether the scrape ran —
    :func:`add_understat_rolling`'s contract, inherited.
    """
    feats: dict[str, pd.Series] = {}
    for w in US_WINDOWS:
        npxg = pd.to_numeric(df.get(f"us_npxg90_r{w}"), errors="coerce") \
            if f"us_npxg90_r{w}" in df.columns \
            else pd.Series(float("nan"), index=df.index, dtype="float64")
        shots = pd.to_numeric(df.get(f"us_shots90_r{w}"), errors="coerce") \
            if f"us_shots90_r{w}" in df.columns \
            else pd.Series(float("nan"), index=df.index, dtype="float64")
        ratio = npxg / shots.where(shots > 0.0)
        missing = (~np.isfinite(ratio)).astype("float64")
        feats[f"us_npxg_per_shot_r{w}"] = ratio.where(
            np.isfinite(ratio), 0.0).astype("float64")
        feats[f"us_npxg_per_shot_missing_r{w}"] = missing
    return pd.concat([df, pd.DataFrame(feats, index=df.index)], axis=1)
```

`engineer.py` already imports numpy as `np`; confirm with
`grep -n "^import numpy" src/gaffer/features/engineer.py` and add the import
if it does not.

Add the block to `feature_columns` (`:848-854`), at the end of the existing
concatenation:

```python
            + SHRUNK_CARD_FEATURES + XG_PER_SHOT_FEATURES)
```

- [ ] **Implement the config reader.** Append to `src/gaffer/config.py`,
beside `price_timing`:

```python
def xg_per_shot(path: Path | str = "config.toml") -> bool:
    """``[model] xg_per_shot`` (v12 §3.5). Default **off**, until the arm
    clears its pre-registered bar.

    A module-level reader for :func:`price_timing`'s reason. Never raises: a
    training run must not die of a config file, and the default is the
    shipped behaviour.
    """
    try:
        raw = tomllib.loads(Path(path).read_text())
    except Exception:  # noqa: BLE001 — a training reader never raises
        return False
    return bool(raw.get("model", {}).get("xg_per_shot", False))
```

- [ ] **Implement the training seam.** In `src/gaffer/models/train.py`, the
import block gains `add_xg_per_shot` and `XG_PER_SHOT_FEATURES` from
`gaffer.features.engineer` and `xg_per_shot` from `gaffer.config`; then one
line in `attach_understat` (`:232-234`):

```python
    df = add_understat_rolling(df)
    # v12 W2 §3.5 (specs/2026-09-01-gaffer-v12-program-design.md). Built
    # unconditionally, like the withdrawn v8a arms' builders: the columns cost
    # a fit nothing and the next cycle re-measures rather than rebuilds. Only
    # whether the attacking model is *told* about them is gated.
    df = add_xg_per_shot(df)
    df = merge_understat_team(df, understat_team_rolled())
```

and a composer beside `train_all`:

```python
def attacking_features() -> list[str]:
    """The attacking model's feature list for this run.

    A function rather than a module constant, because the v12 §3.5 arm is a
    config flag and a constant evaluated at import time would bind whatever
    ``config.toml`` said when the process started — which is v9c's
    disconnected-lever lesson from the other direction.
    """
    return list(ATTACK_FEATURES) + (list(XG_PER_SHOT_FEATURES)
                                    if xg_per_shot() else [])
```

with `train_all` (`:491`) reading it:

```python
    attacking = AttackingModel(attacking_features()).fit(df)
```

- [ ] **Implement the config example.** In `config.example.toml`:

```toml
[model]
# Non-penalty xG per shot, per Understat window, on the attacking model
# (v12 §3.5). Off until scripts/v12_xgps_arm.py clears its pre-registered bar:
# haulers RMSE improves and no other bucket worsens by more than its own
# seed-spread, over three seed bases.
xg_per_shot = false
```

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_xg_per_shot.py tests/test_features.py \
  tests/test_train.py tests/test_v9c_cards.py
.venv/bin/pytest -q
```

- [ ] **Commit.**

```bash
git add src/gaffer/features/engineer.py src/gaffer/models/train.py \
  src/gaffer/config.py config.example.toml tests/test_v12_xg_per_shot.py \
  && git commit -m "$(cat <<'EOF'
feat: xG per shot as a gated arm on the attacking model

Spec §3.5 writes the feature as us_npxg90 / us_shots90; neither column exists.
Both are windowed, so the feature is four ratios — one per Understat window —
each with a missing indicator, because a player with no shots has an undefined
rate rather than a bad one and LightGBM cannot tell a measured 0.00 from a
filled one without being told.

Built unconditionally in attach_understat, which is the one seam both the
training frame and the prediction frame pass through, so advise.py did not need
to move. Only whether the attacking model is told about the columns is gated,
which is the withdrawn v8a arms' rule: the columns cost a fit nothing.

The list is composed by a function rather than bound at import, because a
constant would freeze whatever config.toml said when the process started —
v9c's disconnected lever, from the other direction.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 12 — the arm driver (built, not run)

**Files:**
- Create `scripts/v12_xgps_arm.py`

**CONVENTIONS §7: the implementer builds this and does not launch it.** The
orchestrator runs it at G1.

**It is a three-seed matrix, not one fit** (A7), because the bar the spec
pre-registers names a *seed-spread* and CONVENTIONS §1 says a spread is
measured over K ≥ 3 bases whose runs differ in nothing but the seed.

- [ ] **Write the driver.** Create `scripts/v12_xgps_arm.py`, modelled on
`scripts/v10_shrunk_arm.py` line for line where the shape is the same:

```python
"""Gate G1, v12 §3.5: the xG-per-shot arm on the 2024-25 benchmark.

``us_npxg_per_shot_r{w}`` is shot *quality* beside the shot volume the
attacking model already reads. The claim is narrow and worth stating before
the numbers arrive: two players with the same npxG per 90 are different
players if one takes eight shots for it and the other takes two, and every
Understat column fed today is a volume or a total.

**The pre-registered bar (spec §3.5), against the control arm of this same
run and never against a banked number:**

    KEEP iff  mean haulers RMSE improves
              AND no other bucket's mean worsens by more than that bucket's
                  own seed-spread on the control arm.

Three seed bases, six fits. CONVENTIONS §1: the bar names a seed-spread, and a
spread measured on one draw is not a spread. ``AttackingModel`` takes a
``seed`` (attacking.py:42-52) and it is the only thing that differs between
the three runs of an arm — ``seed_stats.py``'s rule, applied by construction
rather than checked afterwards.

**The lever guards (v10's A12, v9c's lesson).** Three, all before any arm is
scored, because this repo has produced a clean meaningless negative twice. The
driver raises rather than printing a decorated zero.

Run it, watch it, read the verdict::

    mkdir -p logs && caffeinate -i nohup .venv/bin/python \\
        scripts/v12_xgps_arm.py > logs/v12_xgps_arm.log 2>&1 &
    grep -e V12_ARM_DONE -e V12_VERDICT -e V12_ARM_LEVER logs/v12_xgps_arm.log

For scale: v8a's baseline on this benchmark was zeros 1.066 / haulers 5.179 /
all 1.968. That is a sanity range for the control arm, not a comparison for
the arm — CONVENTIONS §1.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import gaffer.evaluation as ev
from gaffer.features.engineer import XG_PER_SHOT_FEATURES
from gaffer.models import train as tr

SEED_BASES = (20260901, 20260902, 20260903)
"""Three, per CONVENTIONS §1. Consecutive rather than scattered: they are
LightGBM ``random_state`` values and any three distinct integers are as good
as any other three, so the readable ones are chosen."""

ARMS: dict[str, list[str]] = {
    "baseline": [],
    "xg_per_shot": list(XG_PER_SHOT_FEATURES),
}
"""The eight columns go in as a block: they are one claim measured at four
windows, and a withdrawal here withdraws the claim rather than a column."""

BUCKETS = ("zeros", "blanks", "tickers", "haulers", "all")
"""``evaluation.RETURN_CATEGORIES``, restated so the verdict's loop reads in
the order the bar is written in."""

_cached = None
_real_load = tr.load_training_frame


def _memoised():
    """One ``load_training_frame`` for the whole run, handed out as copies.

    The frame is the expensive half and cannot differ between arms by
    construction; copies mean an arm that mutates its frame cannot poison the
    next one. ``scripts/v10_shrunk_arm.py:88-99``, verbatim in intent.
    """
    global _cached
    if _cached is None:
        _cached = _real_load()
    df, tg, elo = _cached
    return df.copy(), tg.copy(), elo


def arm_features(name: str) -> list[str]:
    from gaffer.models.attacking import ATTACK_FEATURES

    return list(ATTACK_FEATURES) + list(ARMS[name])


def check_lever(df: pd.DataFrame) -> None:
    """Three guards, all before any arm is scored."""
    from gaffer.models.attacking import ATTACK_FEATURES

    base = set(ATTACK_FEATURES)
    for name, cols in ARMS.items():
        if name == "baseline":
            continue
        if set(arm_features(name)) == base:
            raise SystemExit(
                f"the lever is disconnected: arm {name!r} builds the same "
                f"feature list as the control, so both sides would fit the "
                f"same model and every number below would be a zero with a "
                f"name on it.")
        for col in cols:
            if col not in df.columns:
                raise SystemExit(
                    f"{col} is not on the training frame — feature_columns() "
                    f"lists it but load_training_frame did not produce it, so "
                    f"the arm would fail at fit time or silently drop it.")
            series = pd.to_numeric(df[col], errors="coerce")
            if not series.notna().any():
                raise SystemExit(f"{col} is entirely null on this window.")
            if series.nunique(dropna=True) <= 1:
                raise SystemExit(
                    f"{col} is constant on this window — LightGBM will never "
                    f"split on it and the arm is the control by another name.")
    # Guard 4, this cycle's own: the indicator must not be all-1. An Understat
    # parquet that never landed would make every ratio missing, every value
    # 0.0, and the arm a rename of the control that guard 3 cannot see —
    # because a column of all-zeros with a column of all-ones beside it is two
    # constants, and only the pair is suspicious.
    for w_col in [c for c in XG_PER_SHOT_FEATURES if "missing" in c]:
        if float(pd.to_numeric(df[w_col], errors="coerce").mean()) > 0.95:
            raise SystemExit(
                f"{w_col} is raised on more than 95% of rows — the Understat "
                f"shot columns are effectively absent on this window and the "
                f"arm would be the control with eight constants attached.")
    print("V12_ARM_LEVER ok", flush=True)


def run_arm(name: str, seed: int) -> dict:
    """One fit at one seed, then the benchmark's own walk.

    Deliberately a re-walk of ``evaluate_benchmark``'s loop rather than a call
    to it: the bar reads every bucket off the *same* fitted model, and the arm
    is a seed as well as a feature list. Every number is computed by shipped
    code; only the loop is re-written.
    """
    from gaffer.assets import load_bootstrap_sample
    from gaffer.data.bootstrap import scoring_table
    from gaffer.models.assemble import apply_calibration, assemble_ep, ep_matrix
    from gaffer.models.attacking import AttackingModel
    from gaffer.models.train import predict_components_simple, train_all

    df, tg, _ = _memoised()
    train_df, test_df = ev.benchmark_split(df, ev.BENCHMARK_TRAIN_MAX_IDX,
                                           ev.BENCHMARK_TEST_IDX)
    train_tg, _ = ev.benchmark_split(tg, ev.BENCHMARK_TRAIN_MAX_IDX,
                                     ev.BENCHMARK_TEST_IDX)
    models = train_all(train_df, train_tg.dropna(subset=["elo_diff"]),
                       save=False)
    # The intervention, applied where it is measurable: the attacking head is
    # refitted on this arm's columns at this seed, and everything else in
    # ``models`` is the shared fit. train_all's own attacking model is
    # discarded, which is one wasted fit per arm and is the price of not
    # threading a seed through a function six other callers share.
    models["attacking"] = AttackingModel(arm_features(name),
                                         seed=seed).fit(train_df)

    # Guard 3: the fit actually read the arm's columns.
    fitted = set(getattr(models["attacking"], "feature_cols", []))
    for col in ARMS[name]:
        if col not in fitted:
            raise SystemExit(
                f"arm {name!r} was built with {col} but the fitted model's "
                f"feature_cols does not contain it — the intervention is not "
                f"what it says it is (v9c's lesson).")

    scoring = ev.benchmark_scoring(scoring_table(load_bootstrap_sample()))
    parts = []
    for gw in sorted(int(g) for g in test_df["gw"].dropna().unique()):
        rows = test_df[test_df["gw"] == gw].reset_index(drop=True)
        if rows.empty:
            continue
        comp = predict_components_simple(models, rows)
        ep = ep_matrix(apply_calibration(assemble_ep(comp, scoring),
                                         models.get("calibration")))
        truth = rows.groupby(["code", "gw"], as_index=False).agg(
            total_points=("total_points", "sum"), minutes=("minutes", "sum"))
        parts.append(ep.merge(truth, on=["code", "gw"], how="inner"))
        print(f"{name} seed{seed} gw{gw}: {len(parts[-1])} rows", flush=True)

    scored = pd.concat(parts, ignore_index=True)
    table = ev.stratified_metrics(scored["ep"], scored["total_points"])
    return {b: table[b]["rmse"] for b in BUCKETS} | {
        "rows": int(len(scored)),
        "haulers_n": table["haulers"]["n"],
        "zeros_n": table["zeros"]["n"]}


def verdict(base: list[dict], arm: list[dict]) -> dict:
    """The pre-registered rule, applied to the means and the control spread.

    The spread is the control arm's own max-minus-min across the three seeds,
    per bucket. v7b measured a seed spread of 116 points on a replay — larger
    than every arm gap this project has ever gated on — and the whole point of
    naming the spread in the bar is that an arm has to clear the noise it was
    measured in rather than a number somebody liked.
    """
    def mean(rows, key):
        return sum(r[key] for r in rows) / len(rows)

    spread = {b: max(r[b] for r in base) - min(r[b] for r in base)
              for b in BUCKETS}
    deltas = {b: round(mean(arm, b) - mean(base, b), 5) for b in BUCKETS}
    regressions = {b: deltas[b] for b in BUCKETS
                   if b != "haulers" and deltas[b] > spread[b]}
    keep = deltas["haulers"] < 0 and not regressions
    return {"seed_bases": list(SEED_BASES),
            "base_mean": {b: round(mean(base, b), 5) for b in BUCKETS},
            "arm_mean": {b: round(mean(arm, b), 5) for b in BUCKETS},
            "control_spread": {b: round(spread[b], 5) for b in BUCKETS},
            "delta": deltas, "regressions": regressions,
            "decision": "keep" if keep else "withdraw"}


def main() -> None:
    tr.load_training_frame = _memoised
    df, _tg, _elo = _memoised()
    check_lever(df)
    results: dict[str, list[dict]] = {"baseline": [], "xg_per_shot": []}
    try:
        for seed in SEED_BASES:
            for name in ARMS:
                row = run_arm(name, seed)
                results[name].append(row)
                print("V12_ARM_DONE", name, seed, json.dumps(row), flush=True)
    finally:
        tr.load_training_frame = _real_load

    v = verdict(results["baseline"], results["xg_per_shot"])
    print("V12_VERDICT xg_per_shot", json.dumps(v), flush=True)
    Path("reports").mkdir(exist_ok=True)
    Path("reports/v12_xgps_arm.json").write_text(
        json.dumps({"arms": results, "verdict": v}, indent=1))


if __name__ == "__main__":
    main()
```

**Do not run it.** If a name in it does not resolve — `benchmark_scoring`,
`BENCHMARK_TRAIN_MAX_IDX`, `predict_components_simple` — check it against
`scripts/v10_shrunk_arm.py`, which uses every one of them, and fix the
*driver*, not the module.

- [ ] **Verify it imports and its verdict rule is right**, which is the only
part an implementer may run:

```bash
.venv/bin/python -c "
import runpy, sys
sys.argv = ['v12_xgps_arm']
mod = runpy.run_path('scripts/v12_xgps_arm.py', run_name='not_main')
base = [{'zeros': 1.06, 'blanks': 1.0, 'tickers': 1.0, 'haulers': 5.18,
         'all': 1.97}] * 3
arm = [{'zeros': 1.06, 'blanks': 1.0, 'tickers': 1.0, 'haulers': 5.10,
        'all': 1.97}] * 3
print(mod['verdict'](base, arm)['decision'])"
# withdraw  — a zero control spread means any regression at all fails, and
#             the haulers gain alone does not carry it. Change arm's zeros to
#             1.05 and it prints keep.
```

- [ ] **Commit.**

```bash
git add scripts/v12_xgps_arm.py && git commit -m "$(cat <<'EOF'
test: the xG-per-shot arm driver (three seeds, pre-registered bar)

Six fits, not one. Spec §3.5's bar names a seed-spread and CONVENTIONS §1 says
a spread is measured over K >= 3 bases whose runs differ in nothing but the
seed — so the control arm supplies its own spread, per bucket, and the arm has
to clear the noise it was measured in.

Four lever guards rather than three. The fourth is this cycle's own: an
Understat parquet that never landed makes every ratio missing, every value 0.0
and every indicator 1.0, which is two constants that guard 3 waves through
individually and only the pair betrays.

Not run: CONVENTIONS §7, the orchestrator runs the gates.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 13 — the README lines, the ROADMAP checkboxes, the spec's corrections

**Files:**
- Modify `README.md`
- Modify `docs/superpowers/ROADMAP.md`
- Modify
  `docs/superpowers/specs/2026-09-01-gaffer-v12-program-design.md` (§3 only)

- [ ] **README.** In the commands section, beside `gaffer evaluate
--news-shadow`:

```markdown
- `gaffer evaluate --flag-latency` — how much warning a status change gave
  before the deadline, and whether the player then started. Reads the banked
  availability snapshots; fills once fourteen snapshot days exist and a
  covered gameweek is `data_checked`.
- `gaffer evaluate --presser-grades` — the presser classifier's verdicts
  against who actually started: precision of absence per class, over the
  verdicts recorded *before* their gameweek's deadline.
```

Both write into `reports/evaluation.json` and appear on Model → Quality.

And in the residuals section:

```markdown
- v12 §3.1 names `reports/evaluate/flag_latency.json`; both reports go into
  `reports/evaluation.json` instead, because that is the artifact
  `/api/quality` reads and `save_evaluation` is where the atomic-write and
  `allow_nan=False` discipline already lives.
- The EO trend is measured **gameweek to gameweek**, not day to day: the field
  scrape's already-banked exit means one sample per gameweek, and picks are
  frozen after the deadline anyway, so a same-gameweek delta would be sampling
  noise. Field EO is in **percent** and captaincy doubles it, so the ceiling is
  200 rather than the spec's 1.0.
- The price-timing term is worth 0.008 points at the shipped `itb_value` and
  the solver's default relative gap on a real horizon is larger. It breaks
  exactly-equal sell timings and is not expected to move a replay, so
  `[optimizer] price_timing` ships **false** (CONVENTIONS §6) with the
  flip rule in the W2 gate.
- There is no `[solver]` section: solver knobs live in `[optimizer]`, which
  `load_config` splats into `Config`. A knob there is therefore either a real
  `Config` field (`top_n`) or listed in `config.NON_FIELD_OPTIMIZER_KEYS` and
  popped before the splat (`price_timing`) — never both, and never neither. A
  typo under `[optimizer]` still raises, which is why that tuple is named
  rather than derived from the field list.
```

- [ ] **ROADMAP.** Under `## In progress`, a v12 W2 block, with the
data-gated checkboxes spec §3.2 asks for — and the presser one saying **GW3**,
because GW2 is already `data_checked` and every verdict banked in it postdates
its deadline:

```markdown
### v12 W2 — mine what we have (in progress)
Spec: `specs/2026-09-01-gaffer-v12-program-design.md` §3 · Plan: `plans/2026-09-01-gaffer-v12-w2-mine.md`
- [x] §3.1 flag latency + §3.2 presser grading: `gaffer evaluate
  --flag-latency` / `--presser-grades`, both into `reports/evaluation.json`,
  both on Model → Quality with the empty state naming both numbers. Both
  filter to snapshots taken **before** their gameweek's deadline — the log
  stamps a snapshot with `next_unfinished_gw`, so a Saturday row carries a
  gameweek whose deadline is already gone
- [x] §3.3 EO trend at the gameweek grain, with `deadline_eo` on the explorer
  row and the captain frame; the day grain is not available and the plan's A4
  says why in three measured parts
- [x] §3.4 price-timing term (three authorized line-groups in `milp.py`), and
  §3.5's xG-per-shot arm built with its three-seed driver
- [x] **N2's first news verdict, after four cycles of "pending GW2
  `data_checked`"** (`gaffer evaluate --news-shadow`, run by the orchestrator
  2026-09-02): GW2, n=620 — Brier news **0.1276** vs flags **0.1191**, minutes
  MAE **13.29** vs **13.02**. **Flags are ahead on both.** One gameweek and one
  draw, so by CONVENTIONS §5 this is a residual and not a verdict on the news
  layer; it is banked here so the second gameweek has something to be compared
  against, and the direction is the one worth watching — the layer is not yet
  earning its place. The stale "pending GW2" lines at `:139` and `:148` are
  flipped to point here.
- [ ] **Data-gated:** flag latency — needs 14 snapshot days (3 banked on
  2026-09-01) and one graded covered gameweek
- [ ] **Data-gated:** presser grading — needs a `data_checked` gameweek with
  verdicts banked **before** its deadline. GW2 is checked and has none; GW3 is
  the first candidate
- [ ] **Data-gated:** EO trend — needs a second gameweek in
  `field_eo_log.parquet` (one gameweek, one snapshot day on 2026-09-01)
```

- [ ] **Spec corrections.** Five edits, so the spec stops saying something the
code disproved or a ruling superseded:

1. §3.1: add "Snapshots taken after the gameweek's deadline are excluded — the
   log stamps a snapshot with `next_unfinished_gw`, so a Saturday row carries
   a gameweek whose deadline has passed. The payload lands in
   `reports/evaluation.json` under `flag_latency` rather than in a file of its
   own."
2. §3.2: replace "(`source` is `llm`…)" with "(`source` names the news source,
   not the classifier — 160 of the live log's 169 verdict rows say
   `premierinjuries`)" and change the empty-state gate from "GW2 is
   `data_checked`" to "a `data_checked` gameweek carries a verdict banked
   before its deadline; GW2 is checked and carries none".
3. §3.3: replace the day-grained description with the gameweek-grained one and
   the `[0, 1]` clamp with `[0, 200]` percent, citing the plan's A4.
4. §3.4: add "The term is worth `p × 0.1 × itb_value` — 0.008 points at the
   shipped `itb_value` — which is below the solver's default relative gap on a
   full horizon. It is a tie-breaker for equal sell timings and the replay is
   expected to show no diff." Change `Config [solver] price_timing = true` to
   **`[optimizer] price_timing = false`**: the section by the program ruling of
   2026-09-02 (no `[solver]`; solver knobs live in `[optimizer]`), the default
   by CONVENTIONS §6, with the flip rule in the W2 gate.
5. §2.6 and the W2 gate's config references: `[solver]` → `[optimizer]`
   throughout, key names unchanged. Add the program-wide consequence of the
   ruling, which is not a W2 detail: `[optimizer]` is splatted into `Config`,
   so a knob in that section is either **a real field** — which is what W1
   made `top_n` — or **listed in `config.NON_FIELD_OPTIMIZER_KEYS` and popped
   before the splat**, which is what `price_timing` is. The two are mutually
   exclusive and the invariant is asserted in Task 10: no name in that tuple
   is also a field. Do **not** describe `top_n` as a popped key; W1 ships it as
   a field and W2 does not edit W1's shipped config surface.

- [ ] **Verify.**

```bash
.venv/bin/pytest -q
cd frontend && npx vitest run
git status --short          # only the three docs files
```

- [ ] **Commit.**

```bash
git add README.md docs/superpowers/ROADMAP.md \
  docs/superpowers/specs/2026-09-01-gaffer-v12-program-design.md \
  && git commit -m "$(cat <<'EOF'
docs: W2's data gates, N2's first row, and the five spec corrections

The presser checkbox says GW3 and not GW2, which is the correction worth
reading: GW2 is data_checked today and the report is still empty, because every
verdict banked in it postdates its deadline. The gate was never "a checked
gameweek" — it is "a checked gameweek with a verdict recorded in time".

N2 finally has a row after four cycles of "pending GW2 data_checked": GW2,
n=620, Brier news 0.1276 vs flags 0.1191, MAE 13.29 vs 13.02 — flags ahead on
both. One gameweek, one draw, so it is banked as a residual and not read as a
verdict on the news layer (CONVENTIONS §5). It is recorded because the
direction is the one worth watching.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 14 — the gate checklist (results unfilled)

**Files:**
- Modify `tests/test_v12_w2_degradation.py` (the audit test)
- Modify
  `docs/superpowers/specs/2026-09-01-gaffer-v12-program-design.md` (W2 gate)

**CONVENTIONS §7: the implementer writes the checklist and does not run it.**

- [ ] **Add the protected-diff audit** to
`tests/test_v12_w2_degradation.py`:

```python
def test_the_only_protected_file_w2_touched_is_milp():
    """The audit, as a test rather than as a step somebody remembers.

    Spec §3.4 authorizes one term in optimize/milp.py and nothing else in W2
    touches a protected path. Run against the workstream's base commit.
    """
    import subprocess

    base = subprocess.run(
        ["git", "merge-base", "HEAD", "main"], capture_output=True,
        text=True, check=False).stdout.strip()
    if not base:
        import pytest as _pytest
        _pytest.skip("no merge base — running outside a git checkout")
    changed = subprocess.run(
        ["git", "diff", "--name-only", base, "HEAD"], capture_output=True,
        text=True, check=False).stdout.split()
    protected = [
        p for p in changed
        if p in {"src/gaffer/advise.py", "src/gaffer/set_pieces.py",
                 "src/gaffer/web/jobs.py",
                 "src/gaffer/web/routers/whatif.py",
                 "tests/test_advise.py", "tests/test_odds.py",
                 "tests/test_web_jobs.py", "scripts/s2_replay.py"}
        or p.startswith("src/gaffer/optimize/")
        or (p.startswith("tests/test_") and p.endswith("_degradation.py")
            and p != "tests/test_v12_w2_degradation.py")]
    assert protected == ["src/gaffer/optimize/milp.py"]
```

- [ ] **Write the checklist** into the spec's W2 gate section, results
**unfilled**:

```markdown
**W2 gate — results (filled by the orchestrator).**

| # | Gate | Command | Result |
| --- | --- | --- | --- |
| G1a | Suite green | `.venv/bin/pytest -q` | |
| G1b | Frontend green + types | `cd frontend && npx vitest run && npx tsc --noEmit` | |
| G1c | Zero unauthorized protected diffs | `.venv/bin/pytest -q tests/test_v12_w2_degradation.py -k protected` and `git diff --stat <base> HEAD -- src/gaffer/optimize/` | |
| G1d | §3.4 replay, tolerance 5 vs `main` at the base commit, K=3 seed bases (CONVENTIONS §1), run with `price_timing = true` in the local `config.toml` — the shipped default is off and a replay of the off arm would be a replay of `main` | `scripts/v7b_replay.py --seed-bases 20260901,20260902,20260903` on each side, then `scripts/seed_stats.py` | |
| G1e | Empty states verified against an empty log | `.venv/bin/pytest -q tests/test_v12_w2_degradation.py` | |
| G1f | Pins unmoved | the three-line measurement in the plan header | |
| G2a | §3.5 outcome recorded either way (CONVENTIONS §6: a failing arm ships OFF with its numbers) | `caffeinate -i .venv/bin/python scripts/v12_xgps_arm.py`, then transcribe every `V12_ARM_DONE` and the `V12_VERDICT` line into spec §3.5 verbatim (CONVENTIONS §4) | |
| G2b | Adversarial review → fix round → re-verify | | |
| G3 | Post-merge ritual | `git show main:config.toml` fails; `git log -S<odds key> --all` is empty | |

**G1d is expected to show no diff at all**, and that is the pre-registered
prediction rather than a pass by luck: the price-timing charge is 0.008 points
at the shipped `itb_value` and the solver's default relative gap on a full
horizon is larger (plan A6). A replay that *does* move by more than the seed
spread is the surprising outcome and should be investigated before it is
accepted.

**The §3.4 flip rule, pre-registered here before the arm runs (CONVENTIONS
§2), per the coordinator's 2026-09-02 ruling.** `price_timing` ships `false`;
the default is changed to `true` in `config.example.toml` **iff** the
`price_timing = true` replay clears both halves:

> **FLIP iff** the on-arm's mean total is within the control's seed spread of
> the off-arm's mean (no regression: the term must not cost points), **and**
> hits are not up by more than 3 over the three bases.
>
> A *gain* is not required and must not be read as one. The term is 0.008
> points; any total difference in either direction is seed noise by
> construction, and the flip is a judgement that a correctly-signed cost with
> no measurable downside belongs on, not a claim that it won anything.

If the on-arm regresses beyond the spread, the flag stays `false` **and the
numbers are transcribed into spec §3.4 anyway** — CONVENTIONS §6: deleting a
failed arm loses the measurement that cost the hours.
```

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_w2_degradation.py
.venv/bin/pytest -q
```

- [ ] **Commit.**

```bash
git add tests/test_v12_w2_degradation.py \
  docs/superpowers/specs/2026-09-01-gaffer-v12-program-design.md \
  && git commit -m "$(cat <<'EOF'
test: W2's gate checklist and the protected-diff audit

The audit is a test rather than a step somebody remembers, and it asserts
equality with the single authorized path rather than emptiness — a widened diff
that happens to touch another protected file fails loudly instead of being
counted as compliance.

G1d's expected result is written down before it runs: no diff at all, because
the price-timing term is smaller than the solver's own gap. A replay that moves
is the surprise.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Rulings — settled by the coordinator, 2026-09-02

All five open questions are answered and the plan above is written to the
answers. Recorded rather than deleted, because the next reader's question is
"why is this not what the spec says".

1. **§3.3's grain — ACCEPTED.** The EO trend is gameweek-to-gameweek, not
   day-to-day (A4). Tasks 8 and 9 as written.
2. **§3.4's default — OFF.** `price_timing = false`, against spec §3.4's
   `true`: CONVENTIONS §6 wins for a term that cannot demonstrate an effect.
   The flip-to-on rule is pre-registered in Task 14's G1d — no regression
   beyond the control's seed spread, hits not up by more than 3 — and a *gain*
   is explicitly not required and not claimable. A6, A8, Task 10 and Task 13
   are written to this.
3. **§3.5's cost — SIX FITS ACCEPTED.** Three seed bases, the honest
   measurement (CONVENTIONS §1). Task 12 as written.
4. **W1 first.** W2 executes after W1 merges; the three pins are re-measured
   at that commit and written into the header table before Task 1.
5. **N2 is live and its first row is banked here.** The orchestrator ran
   `gaffer evaluate --news-shadow` on 2026-09-02: GW2, n=620, Brier news
   0.1276 vs flags 0.1191, minutes MAE 13.29 vs 13.02 — **flags ahead on
   both**. One gameweek and one draw, so it is a residual and not a verdict
   (CONVENTIONS §5). Task 13 records it and retires the stale "pending GW2
   `data_checked`" lines.

**Program ruling, same date, applied throughout: there is no `[solver]`
section.** Every solver knob lives in the existing `[optimizer]`, key names
unchanged. This is not cosmetic here — `load_config` splats `[optimizer]`
straight into `Config`, so `price_timing` under it is a `TypeError` on the
next advise run unless it is popped first. A8 has the reasoning and Task 10
has the edit and its three tests.

## What to read in W1's shipped code before Task 1

Settled by the coordinator on 2026-09-02, after W1's plan was amended: **W1
ships `top_n` as a real `Config` field** — `default_factory`, splatted out of
`[optimizer]`, read through `optimizer_top_n()`. So there is no `[solver]
top_n` case to stop on, and `NON_FIELD_OPTIMIZER_KEYS` contains
**`price_timing` alone**. Popping a key that is a field would strip a
configured pool size out of the constructor and hand every user the dataclass
default in silence, which is the one failure in this area that no test would
notice: a smaller pool still solves, and still returns a plan.

Two things to read off W1's merged code rather than assume, both cheap:

```bash
grep -n "top_n" src/gaffer/config.py            # a field, and its shape
grep -n "raw.get(\"optimizer\"" src/gaffer/config.py   # any filter already there
```

- **`top_n`'s shape** — Task 10's `test_w1s_top_n_still_travels_through_the_splat`
  writes it as `{GKP, DEF, MID, FWD}` per spec §2.6; match the TOML to what W1
  actually banked. The assertion that survives any shape change is the first
  one in that test: no name in `NON_FIELD_OPTIMIZER_KEYS` is also a field.
- **Whether W1 already filters the splat** — it should not need to, since its
  key is a field. If it does, add `price_timing` to the existing comprehension
  rather than writing a second one, and add nothing else.

