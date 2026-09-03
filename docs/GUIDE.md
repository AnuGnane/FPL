# The gaffer guide

*A tour of everything this project does, how it got here, and how to use it.
Last updated 2026-09-01 (after the v11 merge). The README covers setup and
reference; this document is for understanding.*

---

## Contents

1. [What gaffer is](#1-what-gaffer-is)
2. [How it works, end to end](#2-how-it-works-end-to-end)
3. [The models](#3-the-models)
4. [The optimizer](#4-the-optimizer)
5. [The web UI, hub by hub](#5-the-web-ui-hub-by-hub)
6. [Your week with the tool](#6-your-week-with-the-tool)
7. [The automation](#7-the-automation)
8. [Everything the CLI can do](#8-everything-the-cli-can-do)
9. [The data it collects and why](#9-the-data-it-collects-and-why)
10. [How the project measures itself](#10-how-the-project-measures-itself)
11. [The version history, v1 to v12](#11-the-version-history-v1-to-v12)
12. [What is pending and what was left open](#12-what-is-pending-and-what-was-left-open)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. What gaffer is

Gaffer is an **advisor-only** Fantasy Premier League tool. Every week it
downloads the public FPL data, predicts every player's points with a set of
machine-learned models, plans your transfers several gameweeks ahead with a
mathematical optimizer, and tells you what to do — in the terminal, in an
HTML report, and in a local web app. You apply the advice yourself in the
official FPL app; gaffer never logs in and never touches your team.

Three design principles run through everything:

- **Honesty over polish.** A number the tool cannot back up is not shown.
  Missing data reads as an em dash, never as zero; empty states say *why*
  they are empty; every probability carries its sample size or its error bar
  where one exists.
- **Advice is separate from measurement.** The optimizer produces the plan;
  a large evaluation layer (backtests, replays, calibration reports, the
  decision ledger) grades the plan after the fact and never feeds forward
  silently.
- **Everything degrades gracefully.** No odds key, no news source, no field
  sample, no models trained yet — each layer falls back to the one below it
  and says so, rather than blocking or guessing.

## 2. How it works, end to end

A weekly `gaffer advise` run walks this pipeline:

```
FPL API + banked history ──► feature engineering ──► component models
     (data/)                    (engineer.py)          (LightGBM ×6)
                                                            │
  bookmaker odds ──────────► team model blend               ▼
  injury/news layer ───────► availability pass ──► expected points per
  predicted line-ups (×2)                          player per gameweek
  your own pins                                          │
                                                         ▼
                              MILP optimizer (PuLP → HiGHS/CBC)
                              6-GW receding horizon, chips, hits,
                              league tilt, scenario-sweep gating
                                                         │
                                                         ▼
                       reports/gwN-report.html + gwN-advice.json
                       (the web UI reads these same artifacts)
```

Step by step:

1. **Refresh** — pulls the FPL bootstrap, fixtures, your entry, and your
   mini-league into `data/live/`.
2. **Features** — builds per-player-per-fixture rows from three seasons of
   history plus the live season: rolling form, minutes patterns, team
   strength (Elo and Dixon-Coles), fixture difficulty, set-piece duty,
   congestion from cup schedules, manager tenure, Understat xG.
3. **Predict** — six component models produce per-player probabilities and
   rates (see §3), which are assembled into expected points using FPL's own
   scoring table, then corrected by a calibration layer.
4. **News pass** — injury tables, two predicted-line-up sources, the
   official flag and your own pins adjust each player's chance of playing.
   Applied last of all is *your* pin, because you watched the press
   conference and the model did not.
5. **Optimize** — a mixed-integer program picks transfers, captain, bench
   order and chip timing over a six-gameweek horizon (see §4). A scenario
   sweep re-solves the board 40 times under calibrated noise and gates out
   moves that only win on a knife-edge.
6. **Report** — terminal summary, HTML report, JSON artifact. The web UI
   serves the same artifacts, so the two never disagree.

## 3. The models

All trained by `gaffer train` into `models/` (LightGBM, one `.joblib` +
`.meta.json` each):

| Model | Predicts |
|---|---|
| **Minutes** | A three-mode outcome per player: did not play / came off the bench / started — giving `p_play`, `p60`, expected minutes. |
| **Attacking** | Goals and assists rates, blended with Understat xG history. |
| **Team** | A Dixon-Coles goals model per fixture: clean-sheet and goals-conceded probabilities, blended 70/30 with bookmaker odds when a key is configured. |
| **Saves** | Goalkeeper save points. |
| **Bonus** | Bonus points via the BPS system (restated for the 2026/27 rule changes). |
| **Calibration** | A final per-position additive correction to the assembled expected points, scaled by each player's chance of a 60-minute appearance. |

On top of the point estimates, every number carries **uncertainty** (v8g):
the `Range` column is the p25–p75 of what a player might actually score —
football's own variance (much the larger part) plus the model's estimation
error, added in quadrature. The bands are wide (Haaland at 5.9 xPts spans
roughly 2.8–8.7) and that width is the finding, not a bug. Haul (`10+ pts`)
and blank chips are tails of the same distribution.

**Penalties and set pieces** are priced explicitly: an event-based history of
who actually took each penalty, a league conversion rate, and the delivery
share for the non-taker — audited weekly by `gaffer track-pens`.

## 4. The optimizer

A multi-period MILP (PuLP modelling, HiGHS solver, CBC fallback) that plans
the whole squad — transfers, captain, vice, bench order, chip — over a
**receding six-gameweek horizon**: it plans six weeks ahead, you execute only
the first, and next week it re-plans. Key machinery, in the order it was
earned:

- **Shadow prices for transfers** (v4c): a dynamic program values holding a
  free transfer and charges hits properly across the horizon, so "take a −4
  now" competes fairly with "bank the transfer".
- **Chip timing by optimal stopping** (v4c): each unused chip has a
  week-by-week threshold θ — the chip plays when this week's gain clears the
  bar of what waiting could still buy. This was the single biggest measured
  win in the project's history (+73 points over a replayed season). The
  first-half chip set expiring at GW19 is modelled.
- **Scenario-sweep gating** (v4c): the board is re-solved 40 times under
  calibrated noise; a transfer that appears in only a handful of the solves
  is dropped as noise-chasing. The UI shows each move's "% of sims".
- **League tilt λ** (v4d): with a `league_id` configured, the optimizer
  leans toward differentials when you are chasing and toward covering rival
  ownership when you are defending, with a dead-band where the gap is just
  noise. It only tilts which players are *considered* — reported expected
  points are always the raw model numbers.
- **Minutes-weighted bench, bench order and vice** (v10): the bench slots,
  the reserve keeper and the vice-captain hedge are priced by each player's
  actual chance of appearing rather than population averages, in a two-pass
  solve that pins the XI and captain between passes. Measured worth:
  **+0.38 points per week across the 21 weeks of 2024-25 in which an
  autosub actually fired**, with the reshaping confined to the bench — the
  intended shape.

## 5. The web UI, hub by hub

`uv run gaffer ui` → <http://127.0.0.1:8927>. One process, six hubs, a
fixture ticker alongside, three-state light/dark theme. Everything reads the
artifacts the CLI writes, so most of it works offline. Long jobs (a re-solve,
a retrain) run through a single-lane job runner with live streamed logs.

Every tabbed hub's open tab is in the URL as `?tab=` (v12 W5), so a tab can be
bookmarked or linked to — `/players?tab=watchlist`. Switching tabs replaces the
history entry rather than adding one, so Back leaves the hub instead of walking
backwards through the strip, and a `?tab=` naming a tab the hub does not have
opens the hub's default rather than a blank panel.

**This Week** — the answer. The advised XI on a pitch in formation rows,
shirts, C/V armbands, difficulty-tinted next-opponent chips; the bench in
substitution order; the transfer list with attack/cover tags; the captain
sentence telling you where your pick stands against the top-10k field
(cover or attack, with its error bar) and, when the league tilt moved the
armband, the run's own half-sentence saying why (v12 W5); the chip planner's
best week per
chip; the Friday/Tuesday digest cards; a re-run button (full or `--fast`).
An **EO lens** toggle tints the pitch by how owned each player is; a
**Table** toggle returns the dense squad table.

**Planning** — the future. Six tabs:
- *Board* (v11): the solved horizon laid out week by week — buys, sells,
  prices, hits, chip, and the bank after each week. Price-change warnings
  ride each name. "Try these changes" hands a week to the What-If lab
  prefilled; the board itself never re-solves. A **Plan A / B / C** strip
  (v12 W3) switches between the recommended plan and the two next-best
  *distinct* ones when the run banked any, each labelled with its gap from
  Plan A in the solver's own objective points — signed, so an alternative
  that is ahead of the recommendation says so. **"Why this move"** (v12 W5)
  opens the objective's own terms for that week's transfers — the decayed
  points difference of each swap, the hit charge, the per-transfer friction,
  what a free transfer is worth at the end of the horizon, the terminal
  bank, θ where a chip is played, and the price-timing charge. It is
  accounting over the plan the solver returned, not a comparison against a
  plan it did not make, and it names the terms it does not attribute (the
  captain, vice and bench weightings), so the lines are not meant to add up
  to the week's xPts. Plan A only: B and C came out of different solves.
- *What-If*: lock, ban, force in or **must-sell** players, cap the hits, and
  re-solve the real MILP. Must sell (v12 W3) is the constraint `ban` was
  standing in for: the player goes in the first week of the horizon and the
  bank receives the sale. It is refused inline, before the solve, on someone
  you do not own (use ban), on someone you also locked, banned or forced in,
  and on a free hit, which conjures a squad and so has nobody to sell. The
  diff shows what changed; a sensitivity card re-solves the board twenty
  times under noise so you can tell a robust move from a coin-flip.
- *Drafts*: name a set of what-if constraints, keep up to twelve, compare
  six side by side against today's board.
- *Timeline*: the plan's weeks with difficulty-tinted opponent chips for
  every named player.
- *Chips*: chip thresholds and workbench, plus the **Season outlook**
  (v10b): each chip's best week against its θ bar, the GW19 expiry, and
  any double/blank gameweeks in the published fixture list.
- *Ticker*: the odds-implied fixture difficulty grid.

**Players** — the evidence. Four tabs:
- *Explorer*: the full candidate pool with the "why 6.8?" breakdown behind
  every name, uncertainty ranges, haul/blank chips, a **Pin** button (set
  your own p_play/minutes for the week — applied over every other source),
  and a ☆ watchlist star.
- *Compare* (deepened in v11): up to four players side by side — the signed
  expected-points breakdown that visibly sums to the headline, p_play/p60/
  expected minutes, set-piece order, next-six difficulty strip, all three
  ownership numbers (global / your league / top-10k with ±SE), and a radar.
- *Matrix*: the Dixon-Coles fixture matrix.
- *Watchlist* (v12 W5): the starred players, each with a note you can edit
  (Enter saves it) and an unstar button. This is the only surface a note can
  be written or read from — the explorer's ☆ posts an empty one on every
  click. The date says "noted" and not "watching since", because re-starring
  from the explorer replaces the note *and* the timestamp; the caveat under
  the rows says so.

**League** — the race. Standings with win probabilities, the trajectory,
what the λ tilt is doing and why; *Rivals* (each rival's squad, overlap,
differentials against you); *What if* (pin a haul or a blank and re-simulate
the league — pricing a week, not proposing transfers). The win-probability
card is a real Monte Carlo: 2,000 seeded seasons with rivals correlated
through a shared weekly factor, because simulating managers independently
provably overstates every margin. The **Field** panel (v12) prices your week
against 300 synthetic managers drawn from the banked top-10k EO — a green
arrow is beating the field's median week — and states its limits beside the
number: the field is an ownership portfolio rather than a set of legal squads,
and the EO comes from the *previous* gameweek's sample, which is the only one
a scrape can have banked before a deadline. Its other two rows are empty
states with their conditions named: `P(top-10k)` needs a weekly score
threshold that exists in no source this project reads, and the overall-rank
response needs five graded gameweeks.

**Live** — matchday. Your live points with FPL's autosub rules projected,
provisional bonus reconstructed from BPS, a race chart of where your score
is heading against the pre-gameweek plan, and the league places above and
below you with what they need.

**Model** — the mirror. Seven tabs:
- *Quality*: holdout metrics, reliability curves (including calibration by
  gameweek — how good the probabilities the tool *actually served* were),
  your points vs the model's per gameweek, last week's biggest misses.
- *Review*: the graded decision ledger — every finished gameweek scored
  across four lanes (transfers, captaincy, bench, chip) against what the
  model would have done, in points and in title odds. Each row also names
  the frozen projection table it was graded against (v12 W5), tagged
  `(late)` when that table cannot be trusted to predate the deadline.
- *Season* (v11): the season dashboard — per-lane records and win rates,
  cumulative points left on the bench, accuracy and overall-rank
  trajectories, the calibration trend. Built to fill as the season grades;
  a lane never measured says "never graded", not 0%.
- *Health*: data freshness, model ages, the launchd log, re-run buttons —
  plus (v12) a red banner when the season on disk is not the season your
  config names, the solver's per-position pool sizes, and the last backup
  with its size (or `never — run gaffer backup`).
- *Journal*: the decision journal with its deadline guard.
- *History*: past runs, expected versus actual, price charts.
- *Settings* (v12 W5): the nine settings the UI may edit — horizon, decay,
  the bank's value, the bench weights, the λ tilt cap, the θ/λ priors
  switch, the pool size per position, the price-timing charge and the
  availability draw. It writes `config.local.toml` and **never**
  `config.toml`, which carries the odds API key; one save per field, bounds
  and refusals from the server, and a setting this build does not have is
  named rather than dropped. The note under the form is the server's own
  sentence about what a save reaches.

## 6. Your week with the tool

Assuming the automation is installed (§7), a normal week is mostly reading:

- **Thursday 18:00** — the scheduled run retrains and re-advises. Open the
  UI (or `reports/gwN-report.html`) in the evening and read the plan.
- **Friday 17:00** — the briefing digest arrives as a notification: the
  advised move and captain, players the news layer is unhappy about,
  tonight's likely price changes, one differential.
- **Before the deadline** — if a press conference changes something, **pin**
  the player in the Players explorer (your judgment, applied last) and hit
  re-run; or take the plan to the **What-If lab** and price your own idea
  against the model's. Apply the transfers yourself in the FPL app.
- **Saturday/Sunday** — the *Live* hub while matches are on. The field
  scrape banks the top-10k sample an hour after each deadline day.
- **Tuesday 09:00/09:30** — the review job grades last week's decisions
  into the ledger; the debrief digest summarises it: your score against the
  model's, the worst lane, the hindsight-XI gap, how your title odds moved.
- **Any evening** — the nightly price job banks every player's
  price-predictor reading at 23:15 and the movers card watches your
  watchlist.

Things worth doing occasionally: `gaffer evaluate --calibration` after a few
gameweeks (are the probabilities honest?); the Season tab once grades
accrue; `gaffer league-sim --seeds 1,2,3` when you want the title odds with
error bars; a backtest when you change something and want season-scale
evidence.

### Correcting a set-piece taker (v12)

A **pin** is your judgment about minutes. `data/set_pieces.toml` is your
judgment about who takes the set pieces, for the weeks FPL's feed is behind
the press conference. Copy the template and edit it:

```bash
cp src/gaffer/assets/set_pieces.example.toml data/set_pieces.toml
```

One table per club; takers listed **in order**, by **code**:

```toml
["Arsenal"]
penalties = [232413]        # Eze takes them now; Saka does not
corners   = [232413, 204480]
```

Six things to know, and the template repeats all of them:

- **Codes, not element ids.** Element ids are remapped every summer; codes are
  not. A player's code is printed in the header of his **explain panel**
  (`code 223340`, beside his club and xPts) — click any player row, anywhere
  in the app. That is the only place a code is shown.
- **Quote a header with a space or an apostrophe** — `["Man City"]`,
  `["Nott'm Forest"]`. Bare TOML keys allow neither, and one bad header
  discards the *whole* file, every club in it. The loader prints the line and
  column when that happens, and quoting every header is the safe habit.
- **The header is decorative.** Nothing matches it against a club name; each
  man's club is read off the frame being priced. A code filed under the club
  he left last summer still applies, and two clubs' codes under one header are
  two queues.
- **Listing a club's queue demotes the teammates it leaves out.** For the club
  a listed code plays for, your list *is* the queue — a man you do not name is
  not a taker, whatever FPL published. That is what makes the one line you
  actually want to type mean what you meant by it. An **empty list demotes
  nobody**: it names no code, so it identifies no club, so there is nothing
  for it to be the queue of — it records that you checked and found nobody.
- **Only `penalties` reaches expected points.** `direct_free_kicks` and
  `corners` change the order the player page and the explain panel *serve*,
  and nothing else: there is no free-kick or corner term in the model to move.
- **The "manual" badge is how you check the correction took** — on the player
  row and in the explain panel, beside the three orders, including on a man
  the file demoted (a blank with no badge would read as "FPL has nothing to
  say", which is the opposite of what happened).

Two things the file deliberately does **not** touch. `gaffer track-pens`
records what FPL published and keeps doing so, because a tracker of the feed
that quietly agreed with you would stop being evidence. And the `pen_taker`
training column is built from match history, not from this file — your opinion
prices the coming week, it does not rewrite the past the model learned from.

A missing file, an unparsable one, or one half-edited at 11pm on a Friday are
all "no override": the penalty term is byte-identical to what it was before
the file existed, and the loader says why on stdout rather than failing a run.

## 7. The automation

`./scripts/install_automation.sh` installs nine launchd jobs (re-run it if
the project folder moves — the plists embed the path):

| When | Job | What it does |
|---|---|---|
| Thu 18:00 | `com.gaffer.advise` | `prices`, then `train` then `advise`; logs to `logs/prices.log` and `logs/advise.log`. The price bank comes first so the optimizer's timing term has a same-day log; a failed fetch does not stop the advice. |
| Nightly 23:15 | `com.gaffer.prices` | Banks every player's price reading; flags likely changes. |
| Daily 17:00 | `com.gaffer.snapshot` | Banks the day's availability state (the corpus a future news model trains on). |
| Sat & Sun 12:30 | `com.gaffer.field` | Samples ~300 top-10k squads; banks their EO with standard errors. |
| Tue 09:00 | `com.gaffer.review` | Grades every gameweek FPL has finalised into the decision ledger. |
| Fri 17:00 | `com.gaffer.digest-friday` | The briefing. |
| Tue 09:30 | `com.gaffer.digest-tuesday` | The debrief (after the review has banked). |
| Nightly 23:45 | `com.gaffer.backup` | Tars the ~16 MB no command can rebuild into `~/gaffer-backups`; keeps fourteen. |
| 06:30 & 18:30 | `com.gaffer.core-insights` | `gaffer core-insights` — FPL-Core-Insights per-match stats, published cup/European fixtures and club Elo into `data/core_insights/`. |

Fetched CSVs are cached under `data/raw/core_insights/`. A finished gameweek
is downloaded once; the gameweek being played is re-fetched every run, which
is why this one is scheduled twice a day. To pull a week the publisher
corrected after it went final, run `gaffer core-insights --refresh 3` — the
last three gameweeks of each season, cache ignored.

Check with `launchctl list | grep com.gaffer`. Everything else — sensitivity
sweeps, news-shadow evaluation, snapshots on demand — runs from UI buttons.

## 8. Everything the CLI can do

The weekly core:

- `gaffer advise` (and `--fast` to skip the five-minute scenario sweep)
- `gaffer refresh` — pull latest FPL data
- `gaffer train` — retrain all models
- `gaffer ui` — `--lan` serves to your whole network and prints a QR code
  for your phone. Reads are open; **writes need a token** (v12), from
  `[web] token` in your config or generated and printed once per run. The QR
  carries it, so a phone that scans the code can write; a device you type the
  bare URL into needs `?token=<it>` once. On loopback there is no token and
  nothing changes.

Standing intelligence:

- `gaffer prices` — tonight's likely price changes, banked
- `gaffer snapshot` — bank today's availability state
- `gaffer field-scrape [--gw N]` — bank the top-10k sample
- `gaffer review` — grade finished gameweeks into the ledger
- `gaffer digest --kind friday|tuesday` — write and notify the digest
- `gaffer league` / `gaffer live` / `gaffer league-sim [--seeds a,b,c]`

Evaluation and research:

- `gaffer evaluate` — the full model scorecard
  (`--calibration` for served-probability reliability, `--news-shadow` for
  the news layer's would-be effect)
- `gaffer backtest --season 2025-26 --horizon 6 --chips` — replay a season
  following the tool's own advice
- `gaffer track-pens` — predicted penalty EP against penalties actually taken
- `gaffer diagnose-zeros` — decompose the error on players who blanked

Housekeeping (v12):

- `gaffer backup [--to DIR] [--rsync TARGET]` — one tar of `data/live/`,
  `data/raw/field/`, `data/raw/tier_eo/`, `reports/` and `models/`; keeps the
  newest fourteen locally and never prunes across `--rsync`
- `gaffer tidy [--apply] [--older-than DAYS]` — dry run by default; lists
  replay logs whose report never appeared and stale `logs/*.log`. It reclaims
  54 KB on this tree, and it never touches the shared backtest log, the S2 arm
  logs, the corpus logs or `logs/advise.log`
- `gaffer mcp` — a stdio MCP server for Claude Code:
  `claude mcp add gaffer -- gaffer mcp`. Six read tools, no writes
- `.venv/bin/python scripts/gen_types.py` (v12 W5) — not a `gaffer`
  subcommand: a developer script. It writes `frontend/src/schemas.json` from
  the live pydantic models, which a vitest test compiles into
  `frontend/src/types.generated.ts`. **Run it after any change to
  `src/gaffer/web/schemas.py`**, and commit both files, or the two diff tests
  (`tests/test_v12_w5_gen_types.py` and `frontend/src/types.generated.test.ts`)
  fail. `frontend/src/types.ts` is hand-written and is never overwritten by it

One-time / rollover setup:

- `gaffer build-history` — download the training seasons
- `gaffer understat` / `gaffer cups` — auxiliary history ingestion
- `gaffer calibrate-decisions` / `calibrate-injuries` / `calibrate-noise` —
  rebuild the committed calibration assets from replays and scrapes

## 9. The data it collects and why

All under `data/` (gitignored except one curated file). The point of the
standing collectors is that several future features need a *season* of data
that cannot be backfilled — the tool started banking early:

- `data/history/` — three-plus seasons of per-player-per-GW rows, fixtures,
  Understat, cup dates, closing odds.
- `data/live/price_log.parquet` — every player's price-predictor reading,
  daily. Read by the movers card and the board's warnings; a full season of
  it is what a price-*timing* model would need.
- `data/live/availability_log.parquet` — daily availability snapshots; the
  training corpus for a future news-aware minutes model.
- `data/live/field_eo_log.parquet` + `data/raw/field/` — the top-10k
  effective-ownership log and the anonymised squads behind it. Feeds the EO
  columns, the captain sentence, and the correlated league simulation.
- `data/raw/league/` — every rival's squad per finished gameweek (and your
  own), so December can grade September without re-asking the API.
- `reports/decision_ledger.json` — the graded decision record; written
  once per gameweek when results are final, never re-derived.
- `reports/overrides.json`, `watchlist.json`, `drafts.json` — your pins,
  stars and saved what-if scenarios.
- `data/manager_tenures.toml` — the one committed data file: curated EPL
  head-coach spells for the rotation features.

## 10. How the project measures itself

This is the part that separates the project from a heuristics spreadsheet,
and it is worth knowing because you can read the evidence yourself:

- **Every feature faced a gate before shipping.** A pre-registered bar,
  measured on held-out data or a season replay. Features that failed were
  **withdrawn and recorded**, not shipped hopefully — the v5 congestion
  features, the v7 estimation-σ gating, the v10 shrunk-modes arm all died
  this way, and the ROADMAP says so.
- **Season replays with seed spreads.** Claims about season-scale points
  are made under three seed bases with the spread quoted
  (`docs/superpowers/CONVENTIONS.md`), because a single replay's ±120
  points is draw luck.
- **Adversarial review every cycle.** Each merge got an independent
  fix-first review and a re-verification pass; across v9d–v11 alone this
  caught thirteen real defects before they shipped, including several in
  the fixes themselves.
- **The decision ledger grades the tool, not just the model.** Four lanes —
  transfers, captaincy, bench, chip — scored against what the model
  advised, in points and in title-odds terms, with the honesty rules built
  in: a week where you agreed with the model is evidence of nothing, and a
  lane never measured is never "never wrong".
- **Calibration by gameweek** grades the probabilities that were *actually
  served* (from artifacts written before kickoff — a re-run after the
  matches is detected and excluded), not a model refitted in hindsight.

Where the numbers live: `docs/superpowers/ROADMAP.md` (per-cycle results),
each cycle's spec in `docs/superpowers/specs/` (§Gates/§Outcome sections),
`reports/evaluation.json`, and the Model hub.

## 11. The version history, v1 to v12

Twenty-odd merge cycles, each spec'd, planned, implemented, gated and
reviewed. What each era added:

**v1–v3 — the core (Aug 23–24).** Component models, the MILP with a
receding horizon, `advise`/`backtest`, probability calibration, the odds
blend, league mode v1, the live tracker, and the first web UI.

**v4 — measure, model, decide, compete (Aug 25–26).** The evaluation
harness and benchmark against public models (within ~2% of OpenFPL on
haulers, with half the training data); Understat + Dixon-Coles + devigged
closing odds; then the decision layer — scenario gating, transfer shadow
prices, chip optimal-stopping (+73 pts/season) — and league mode v2 with
the z-derived tilt and EO-aware captaincy.

**v5–v6 — news and the cockpit (Aug 26–27).** The injury/news package
(premierinjuries, FFS predicted line-ups, per-injury-type return curves
from 3,381 scraped spells), the three-mode minutes model, the shadow-first
LLM presser classifier (runs through your Claude subscription with no
tools, logs what it *would* do, serving stays off until the evidence says
otherwise), penalty EP, and the decision-cockpit UI.

**v7 — the command centre and honest noise (Aug 29–30).** The full UI
redesign to six hubs, the streaming job runner, responsiveness, `--lan`,
light theme, fast advise. On the model side, a measurement cycle that
attributed a sign reversal, established the multi-seed standard, and chose
the honest answer (keep the heuristic) over the flattering one.

**v8 — the seven-cycle queue (Aug 30–31).** One sitting: minutes
intelligence (notable-absence damp, presser classifier), field intelligence
(the top-10k scrape and the correlated league Monte Carlo), the decision
loop (four graded lanes, the ledger, the Tuesday job), live matchday
(autosub projection, the race chart), solver trust (pins, sensitivity,
drafts), honest uncertainty (the bands, the calibration cards), and the
daily companion (price log, watchlist, digests).

**v9 — pitch, polish, debt (Aug 31–Sep 1).** The pitch view with shirts
and armbands, identity chips everywhere, toasts and skeletons, the 390px
pass; then the model-debt cycle (red cards priced, the club retro-stamp
leak measured and closed, job cancel/timeout) and v9d (leak fully closed
with the match rate *up*, calibration-by-gameweek monitoring, per-kind job
deadlines).

**v10/v10b — minutes into the solve, EO and chips (Sep 1–2).** The minutes
model finally reaches the optimizer's own weights (+0.38 pts/autosub-week,
measured); RotoWire as a second line-up source merged by pessimism; then
the EO framing (Field% beside EO%, the captain sentence with its ±SE, the
EO lens) and the season chip Outlook fed by a real double/blank-gameweek
detector.

**v11 — the UI trio (Sep 2).** The planner board, the comparison view that
shows the model's working, and the season review dashboard — built empty on
purpose, filling as the season grades.

**v12 — five workstreams in one program (Sep 2–3).** W1, hygiene: the "as of"
freshness strip, `gaffer backup` and `gaffer tidy`, a write token for `--lan`,
one atomic-write helper to replace six copies of the idiom, and `top_n` in
config. W2, the logs we already had: the nightly price log turned into a
price-timing charge on a deferred sale, and the xG-per-shot arm — measured,
and withdrawn on the season replay after the bucket metric liked it. W3, what
the solver is allowed to say: Plan B and Plan C, the *must-sell* constraint the
`ban` switch had been standing in for, and the availability draw in the
scenario sweep. W4, the field: the FPL-Core-Insights collector, `P(green
arrow)` against 300 synthetic managers drawn from the banked top-10k sample,
set-piece overrides in TOML, and two minutes arms of which one shipped and one
was withdrawn. W5, the interface: the open tab in the URL, the Settings tab and
the overlay file it owns, the watchlist's notes, frozen projection snapshots
behind every graded row, "why this move" on the board, and half of `types.ts`
generated from `schemas.py`.

The suite grew from nothing to **4,029 Python + 792 frontend tests** along
the way, with a set of degradation rails that pin every honesty rule above
so a future change cannot quietly break one.

## 12. What is pending and what was left open

Waiting on data, not code (as of 2026-09-01):

- **GW2 `data_checked`** (expected imminently): the first fully-graded
  Review row, the first Season-tab content, and the first news-shadow
  verdict (`gaffer evaluate --news-shadow`).
- **The weekend's GW3 field scrape**: lights up the captain field sentence
  and Field% column live checks.

Deliberately open (recorded per cycle in the ROADMAP/specs, the notable
ones):

- The presser classifier still only *logs*; turning it on awaits its
  accrued verdict.
- The scenario sweep cannot yet see per-player `p_play`, so the minutes
  weighting prices the squad around the transfers rather than the transfer
  choice itself.
- `overall_rank` in the ledger populates only from v11 onward — banked
  grades are never rewritten.
- A season of price-log data must accrue before a price-timing term is
  worth building.
- **Closed rather than pending, and left here because the previous entry
  said otherwise:** the two v12 minutes arms built on FPL-Core-Insights were
  measured on 2026-09-03 and the pre-registered two-half rule split them.
  **`role_wb_share` ships on**: starters-slice `p_start` log-loss 0.43723 →
  0.42889 (−1.907% relative) for +0.002 of zeros RMSE, and +0.133 mean points
  over the 15 weeks of 38 an autosub fired. It is in `MINUTES_FEATURES` and
  takes effect on the next `gaffer train`; a model pickled before the flip
  pins its columns at fit time and keeps predicting.
- **`density_pub_7d` is withdrawn**: 0.43584 (−0.318%, under the 1% bar) for
  +0.006 of zeros RMSE (over the 0.005 guard), so half (a) fails and its
  half (b) pass (+0.333) does not rescue it. It stays built on both seams and
  fed to no head, for a later cycle to re-measure.
- Recorded outside the rule, because it is worth knowing: over **all** 38
  weeks the mean points delta is −0.211 for role and −0.895 for density.
  Half (b) was pre-registered on the autosub weeks and read as written; the
  W4 no-regression replay was run with both arms off, as pre-registered, so
  the flip's decision-path evidence is the counterfactual and not the replay.
- The Field panel's `P(top-10k)` has no source: no top-10k weekly score
  threshold series exists in anything gaffer reads, so it is a named empty
  state rather than a guess.

Left open by v12 W5, each recorded rather than fixed:

- **The trace's price-timing charge is read from tonight's price log, not
  from the solve.** `owned_price_falls` is the same reader the objective
  uses, but a board drawn on Saturday against a Thursday plan multiplies a
  probability the solve never saw. Freezing it would mean writing it into the
  solve state from `advise.py`, which is protected, for a decoration.
- **The trace does not attribute the squad-side terms.** The XI, captain and
  vice weightings and the three bench seats price the whole fifteen and a
  per-week autosub scale, not a swap, so a share of them assigned to one
  transfer would be invented. The week's lines therefore do not sum to its
  xPts, and the caption says so rather than leaving it to be discovered.
- **`projection_snapshot` fills forward only.** Grades are banked and never
  re-derived, so every ledger row banked before W5 keeps `null` for ever.
- **`reports/projections/` is never pruned.** ~6–12 MB a season, gitignored.
  A future `gaffer tidy` target, deliberately not invented here.
- **The watchlist's `set_at` is reset by every save**, because
  `watchlist.watch` replaces the note and the timestamp together. The column
  is labelled "noted" rather than "watching since" for that reason; fixing it
  means a second store field.
- **The decision ledger has no season key.** After a rollover, a GW-N row
  could name last season's GW-N snapshot: the snapshot *reader* is
  season-guarded, the ledger is not. Nothing reads across a rollover today,
  and the fix is a ledger migration rather than a W5 line.
- **The generated half carried away the client's field comments.** The split
  deleted 113 hand-written interfaces; 119 of the 891 field sentences were
  recovered by reading `schemas.py`'s attribute docstrings, and the rest of
  the client-side commentary on those interfaces is gone. The follow-up is to
  move the sentences worth keeping into `schemas.py` field docstrings, where
  the generator can carry them, rather than back into a file it overwrites.

## 13. Troubleshooting

- **Fresh clone shows "frontend not built"** — `cd frontend && npm install
  && npm run build` once; end users of the wheel never need node.
- **`advise` refuses to run** — models missing (`gaffer train`) or
  `fpl.entry_id` unset in `config.toml`.
- **A job seems stuck in the UI** — the runner reaps a wedged holder
  automatically (120 s for fast kinds, 30 min for slow ones), or free the
  lane yourself: `DELETE /api/jobs/current`. Never run the UI with
  multiple workers — the job system is single-process by contract.
- **League/Live pages error offline** — they are the only pages that need
  the live FPL API; everything else reads local artifacts.
- **Season rollover** — append the finished season to `train_seasons`
  *and* bump `current_season` together, then `gaffer build-history` and
  `gaffer train`. The README's Retraining section explains why both. Since
  v12, `gaffer refresh` **refuses** to ingest a season `current_season` does
  not name, printing both values and both keys. Editing `current_season` in
  the `[data]` block of `config.toml` is the remedy, and it is the only
  one: there is no escape flag, deliberately, because the failure it prevents
  (August rows written under last season's index, then trained on) is silent,
  and a `--force` would be reached for on exactly the morning it matters.
- **Writes fail from your phone on `--lan`** — the page needs the write
  token. Scan the QR code rather than typing the URL, or open it once with
  `?token=<the token in the banner>`; the page stores it. A refusal is a 403
  with a sentence naming the header, not a silent failure.
- **Moved the project folder** — re-run `scripts/install_automation.sh`
  (plists embed the path).
- **Price job fires at the wrong time** — it is scheduled in *local* time
  for a UK-midnight event; adjust `scripts/com.gaffer.prices.plist` if you
  are not on UK time.

---

*Deeper reading: `README.md` (setup and reference),
`docs/superpowers/ROADMAP.md` (every cycle with its measured results),
`docs/superpowers/specs/` (per-cycle designs with gate numbers),
`docs/superpowers/CONVENTIONS.md` (the measurement rules).*
