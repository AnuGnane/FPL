# The gaffer guide

*A tour of everything this project does, how it got here, and how to use it.
Last updated 2026-09-04, after the free-transfer rule hotfix (`main` `3c39048`). The
README covers setup and reference; this document is for understanding. If you
only read one section, read §12: it is the current to-do list.*

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
- **The free-transfer rule, as FPL plays it** (hotfix 2026-09-04): one free
  transfer a week, banked to five, and a wildcard or free hit week *carries
  the count over unchanged* — the chip consumes nothing and the week accrues
  nothing, so one FT into the chip is one FT out of it. Gaffer had banked
  the +1, and read a GW2 wildcard as two FTs for GW3. The live count, the
  MILP's wildcard week, the backtest and the plan trace now all say the same
  thing, and a wildcard that fixes nothing is priced at exactly the one
  accrual it forgoes.
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
  (Enter saves it) and an unstar button. This is the only surface that writes
  a note: the explorer's ☆ sends the code and nothing else, and a request
  that says nothing about the note leaves the note and the star date alone.
  The date says "noted" and not "watching since", because saving a note —
  including clearing it — stamps the row with the time you did it.

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
  features, the v7 estimation-σ gating, the v10 shrunk-modes arm, v12's
  xG-per-shot head and its `density` minutes arm all died this way, and the
  ROADMAP says so. Twice in v12 a feature that improved its own head's metric
  *lost* season points on the replay, which is why the rule now demands both
  halves up front (CONVENTIONS §9).
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
reviewed. Every cycle ran the same way, and knowing the shape tells you where
to look for the evidence behind any feature:

1. **Research** (`docs/superpowers/research/`) — a survey of what is wrong,
   unmined or missing, ranked. Two so far: 2026-08-25 (which produced v4–v11)
   and 2026-09-01 (which produced v12).
2. **Spec** (`docs/superpowers/specs/`) — the design, with the gate and its
   pass/fail rule written *before* anything runs. The spec is also where the
   results land afterwards: every spec ends in a §Gates or §Outcome section
   with the measured numbers, what was withdrawn, and what was left open.
3. **Plan** (`docs/superpowers/plans/`) — the task list an implementer
   follows, file by file.
4. **Implement, review, gate, merge** — subagents implement; each chunk gets a
   spec-compliance review and a code-quality review; the whole branch gets an
   adversarial fix-first review and a re-verification; the orchestrator runs
   the gate (never the implementer) and merges fast-forward only.
5. **Record** — the ROADMAP block for the cycle, with pins (route, job and
   config-field counts), the suite size, residuals and data-gated items.

Your part in it has been the decisions: which research items to take, the
rulings a plan asks for when it meets a protected file, the arm to flip when
a gate's verdict is close, and the live spot-checks on the running UI that no
test can do. Those rulings are recorded in the spec and ROADMAP blocks by
date.

What each era added:

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

**v12 — five workstreams in one program (Sep 2–3; closed at `9274f33`).**
One spec, five sequential workstreams, each gated and merged on its own.
W1, hygiene: the "as of" freshness strip, `gaffer backup` and `gaffer tidy`,
a write token for `--lan`, one atomic-write helper to replace what turned out
to be twenty copies of the idiom, `top_n` in config, a season-rollover
refusal, and `gaffer mcp`. W2, the logs we already had: flag-latency and
presser-grading reports off the availability and presser logs, the EO trend,
the nightly price log turned into a price-timing charge on a deferred sale
(ships **on** — the replay was byte-identical with the term live), and the
xG-per-shot arm — measured, and **withdrawn** on the season replay (−28 points)
after the bucket metric liked it. W3, what the solver is allowed to say: Plan
B and Plan C by no-good cuts, the *must-sell* constraint the `ban` switch had
been standing in for, θ as the only chip decision, the availability draw in
the scenario sweep (ships on; captain support 60 → 52.5 on the live board), a
real free-hit re-solve and a wildcard+bench-boost pair. W4, the field: the
FPL-Core-Insights collector, `P(green arrow)` against 300 synthetic managers
drawn from the banked top-10k sample, set-piece overrides in TOML, and two
minutes arms — **`role` shipped, `density` withdrawn** on a pre-registered
two-half rule. W5, the interface: the open tab in the URL, the Settings tab
and the `config.local.toml` overlay it owns, the watchlist's notes, frozen
projection snapshots behind every graded row, "why this move" on the board,
and half of `types.ts` generated from `schemas.py`.

Also in v12: the first news-shadow verdict, four cycles after it was
instrumented — on GW2 the plain FPL flag beat the news layer (Brier 0.1191
vs 0.1276), one gameweek and therefore a residual, but the direction to watch.

The suite grew from nothing to **4,042 Python + 795 frontend tests** along
the way, with a set of degradation rails that pin every honesty rule above
so a future change cannot quietly break one.

## 12. What is pending and what was left open

As of 2026-09-03. Nothing is in flight: every v12 workstream is merged and the
program is closed. What remains falls into six groups, in the order you
would act on them.

### 12.0 First: install the two new launchd jobs

`launchctl list | grep com.gaffer` shows **seven** jobs loaded on this
machine (checked 2026-09-03). v12 added two — `com.gaffer.backup` (23:45
nightly) and `com.gaffer.core-insights` (06:30 and 18:30) — and the plists
exist but were never installed, so no backup has run and the Core-Insights
archive is only as fresh as the last manual `gaffer core-insights`. One
command:

```bash
./scripts/install_automation.sh
```

Then `launchctl list | grep com.gaffer` should show nine. This is the
single most useful thing on the list: everything in §9 that cannot be
rebuilt is unprotected until the backup job runs.

### 12.1 Things only you can check — the live spot-checks

Every cycle's spec ends with a list of checks on the running UI that no test
can do, and v12's were deferred rather than passed (the W5 gate says so in
writing). Run `uv run gaffer ui`, then walk these. The full row-by-row lists
are in `docs/superpowers/ROADMAP.md` under **Open**, and in the spec's
"live spot-checks" sections (`specs/2026-09-01-gaffer-v12-program-design.md`
lines for W1, W3 and W5).

- **The six-hub pass (W5).** Open each hub with a `?tab=` link
  (`/planning?tab=board`, `/players?tab=watchlist`, `/league?tab=rivals`,
  `/model?tab=settings`); each lands on that tab, and Back leaves the hub
  rather than walking the strip.
- **A Settings save round-trip (W5).** `md5 config.toml` before; change one
  value in Model → Settings; `md5 config.toml` after is identical and
  `config.local.toml` now exists with that one key.
- **The watchlist note survives a star (W5).** Write a note in Players →
  Watchlist, then star/unstar the same player in the Explorer: the note and
  its "noted" stamp are untouched.
- **The board (W3).** Plan A / B / C switch when alternatives were banked and
  no strip appears when none were; "Try these changes" lands on What-If with
  sells under *Must sell*; every chip bar reads θ or `flat` and the "Wildcard
  now" verdict names the same bar; the chip table has **no** WC+BB row on
  today's fixture list (correct, not a bug).
- **The field (W4).** League → Field names the EO gameweek as the *previous*
  one and shows `P(green arrow)` with its caveats, and two named empty states
  below it; Model → Health shows a row per Core-Insights table; a
  `data/set_pieces.toml` entry produces the "manual" badge on the player row.
- **Hygiene (W1).** Every hub draws the "as of" strip once; `gaffer ui --lan`
  prints a token and a phone from the bare URL gets a 403 sentence on a
  write; `gaffer tidy` names its files and `gaffer backup` writes ~16 MB;
  `claude mcp add gaffer -- gaffer mcp` answers "top five midfielders".

### 12.2 Waiting on data, not code

Each of these is built, tested and rendered as a named empty state today.
Nine rows, with the condition that fills each and the rough date:

| Surface | Needs | Expected |
|---|---|---|
| Model → Quality: **flag latency** (W2) | 14 daily availability snapshots plus one graded gameweek they cover | ~2026-09-13 (four days banked, 08-30 → 09-02, one a day at 17:00) |
| Model → Quality: **presser grading** (W2) | a `data_checked` gameweek with classifier verdicts banked *before* its deadline; GW2 had none | GW3, once graded |
| Players / captain frame: **EO trend** (W2) | a second gameweek in `field_eo_log.parquet` | the GW3 weekend scrape |
| Planning → Chips: **WC + BB pair row** (W3) | a `[dgw]` entry in `data/chip_scenarios.toml`, which the writer only creates from a real double in the published list | the first rearrangement FPL announces |
| League → Field: **`P(top-10k)`** (W4) | a top-10k weekly score-threshold series; no source gaffer reads has one | needs a new scrape — a candidate for the next spec |
| League → Field: **expected overall-rank change** (W4) | 5 graded gameweeks carrying both `my_points` and `overall_rank`; GW1's rank is null, so 1 of 5 today | ~GW6 |
| Model → Health: **Elo for 2026-27** (W4) | the archive publisher to fill the `elo` column for this season | out of our hands |
| Planning → Board: **the price-timing line shows a number** (W5) | `[optimizer] price_timing` on (it is, by default) *and* a nightly price log long enough to return a row per owned player | a couple of weeks of the 23:15 job |
| Model → Review: **a row names its projection snapshot** (W5) | the first gameweek graded after the W5 merge; earlier rows keep `null` for ever | GW3's Tuesday review |

Two verdicts also accrue by gameweek rather than by code: `gaffer evaluate
--news-shadow` gets its second reading when GW3 is `data_checked` (GW2's
said the plain flag was ahead), and the presser classifier's serving
decision waits on the presser-grading row above.

### 12.3 One experiment queued

**A K ≥ 5 role-on-vs-off replay** (ten seeds if time allows). W4 shipped the
`role_wb_share` minutes feature on its pre-registered rule, but a post-hoc
three-seed replay with the feature on scored −27 on the mean (`[1813, 1847,
1846]` vs `[1798, 1917, 1872]`), inside the spread. The read it was
pre-registered under lets the flip stand; the honest next step is a replay
with enough seeds to say whether −27 is real. Negative beyond its own spread
withdraws the arm. It is the second time in the program a head-metric gain
did not show up as season points (xG-per-shot was the first), which is why
CONVENTIONS §9 now requires both halves up front.

How to run it: `scripts/replay_pair.sh <tag>` from a branch worktree runs
both sides through `scripts/v7b_replay.py --seed-bases …`; the "off" side is
a branch with `ROLE_FEATURES` removed from `MINUTES_FEATURES`
(`src/gaffer/models/train.py:53`), the "on" side is `main`. Both sides need
`config.toml` byte-identical and `data/core_insights/` present, with its
seasons and collection date named in the write-up (CONVENTIONS §1). The W4
runs took about an hour per three seeds a side on this machine, so K=10 is an
overnight job — `caffeinate -i` it, as `replay_pair.sh`'s header shows.

### 12.4 Deliberately open — recorded, not fixed

These are known, bounded, and each has a reason it was left. None blocks
weekly use.

- **The presser classifier only logs.** Serving stays off until the grading
  report (12.2) has a few gameweeks in it.
- **The trace's price line is present tense.** "Why this move" reads
  tonight's price log and today's `price_timing` switch, not the ones the
  solve used, because freezing them into the solve state means editing
  `advise.py` (protected) for a decoration. The caption says so.
- **The trace does not attribute the squad-side terms**, so its lines do not
  sum to the week's xPts; the caption says that too.
- **Plans B and C are not re-scored under Plan A's own coefficients**, so a
  small gap of either sign can be two coefficient sets rather than two plans.
- **The free hit re-solve excludes horizon effects** (pricing them needs a
  two-branch horizon solve).
- **`overall_rank` and `projection_snapshot` fill forward only** — grades are
  banked and never rewritten, so rows from before v11/W5 keep `null`.
- **The decision ledger has no season key**; nothing reads across a rollover
  today, and the fix is a ledger migration.
- **The watchlist has no "starred at"** — `set_at` is the note's stamp, hence
  the column reads "noted".
- **`reports/projections/` is never pruned** (~6–12 MB a season); a future
  `gaffer tidy` target. So are ~34 MB of timestamped API snapshots under
  `data/raw/`, outside `tidy`'s scope.
- **The web "re-run" button does not bank a same-day price reading** the way
  the Thursday plist does, so a run from the button can solve with the
  price-timing term seeing an empty table. Run `gaffer prices` first, or use
  the plist.
- **`threshold_source` is served but rendered nowhere**, and the chip pair's
  "Try it" card has no What-If arm.
- **The generated `types.ts` half lost the client's field comments.** 119 of
  891 sentences were recovered from `schemas.py` docstrings; the rest belong
  in `schemas.py` field docstrings, where the generator can carry them.
- **`density_pub_7d` is built on both seams and fed to no head**, kept for a
  later re-measure with a replay half of its own.

### 12.5 Not planned — what the research proposed and v12 did not take

Nothing below is spec'd or committed. It is the candidate list a next
brainstorm would start from, in the order the 2026-09-01 research ranked it
(`docs/superpowers/research/2026-09-01-polish-and-improvement-research.md`):

1. **News-layer ablation against the plain FPL flag (C1).** The research
   called this the most important experiment in the document, and the GW2
   news-shadow reading points the same way. It could retire the v5/v6 news
   subsystem or justify it; either answer is worth having. Gate on the
   blanks and zeros buckets *and* a K ≥ 5 replay.
2. **The K ≥ 5 role replay** (12.3) — small, and it should go first because
   it changes what the minutes model ships with.
3. **A top-10k score-threshold scrape**, which is the only thing between the
   Field panel and `P(top-10k)`.
4. **`p_play` top-bin recalibration (C2)** — 0.936 predicted vs 0.912
   observed on n=1519; an isotonic step, tiny and measurable.
5. **Home/away rolling splits (C3)** — cheap, never in any arm.
6. **A "days since status last changed" `p_play` feature** off the
   availability log (B1's second half), once the flag-latency report has
   shown the log carries the signal.
7. **Housekeeping follow-ups** from 12.4: `tidy` for projections and API
   snapshots, the ledger season key, `starred_at`, the `schemas.py`
   docstrings, rendering `threshold_source`, the chip pair's What-If arm, the
   web button banking prices.
8. **FotMob as an xG fallback (B8)** — only if Understat goes down.

Still rejected, and the research confirmed it: referee and weather, price
chasing, per-player finishing multipliers, a longer horizon, transformer news
sentiment, the withdrawn minutes arms as they were, write tools on the MCP
server, a UI that edits `config.toml`.

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
