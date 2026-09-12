# The gaffer guide

*A tour of everything this project does, how it got here, and how to use it.
Last updated 2026-09-05, after v14 (the dark ledger) merged. The
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
11. [The version history, v1 to v17h](#11-the-version-history-v1-to-v17h)
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
  points are always the raw model numbers. Since v15 exactly one league —
  the **focus** league, `fpl.league_id` unless `[league] focus` in the
  overlay says otherwise — feeds the tilt, and a manual **stance**
  (`[league] stance`: auto, chase, defend, neutral) can override the dial at
  full tilt: chase and defend pin λ to ±`lambda_cap`, neutral pins it to 0,
  which is plain points-max. Both are set from the League page.
- **Minutes-weighted bench, bench order and vice** (v10): the bench slots,
  the reserve keeper and the vice-captain hedge are priced by each player's
  actual chance of appearing rather than population averages, in a two-pass
  solve that pins the XI and captain between passes. Measured worth:
  **+0.38 points per week across the 21 weeks of 2024-25 in which an
  autosub actually fired**, with the reshaping confined to the bench — the
  intended shape.
- **Transfer appetite and the ladder** (v13): two `[optimizer]` keys, `max_hits`
  (default 2) and `max_transfers` (default 15 = no cap), cap what the solver
  may do in any one non-wildcard week, and the Thursday advice, its scenario
  sweep, its alternative plans, its chip table and the season replay all
  solve under them. The **transfer ladder** then prices every rung of
  appetite off the saved board — bank, then 0, 1, 2 and 3 hits — and scores
  each fixed plan on one shared matrix of 2,000 outcome-noise draws, so
  P(a rung beats banking) and P(it is the best) compare only the players
  that differ. Its points are raw XI + captain over the horizon, undecayed
  and untilted, so they can rank the rungs differently from the objective:
  on the GW3 board the extra hits bought points but fewer than four each,
  and the zero-hit rung was the best on raw points at 33% against 20% for
  three hits.
- **Restraint** (v16): the ladder now *decides* how many changes the
  advice commits to. Inside the ladder build a walk starts at the lowest
  rung and steps up one distinct rung at a time only when the higher rung
  beats the lower in at least `[optimizer] hit_bar` of the shared draws
  (default 0.60, three draws in five, bounded 0.5–0.95); it stops at the
  first refusal, and the rung it stops on is the plan the advice serves —
  its moves, XI, bench and expected points, with the rung's own captain
  unless a league-mode note explains the sweep's. Each step carries a
  reason in a fixed precedence — a flagged player, a price fall, a fixture
  grade, a planned chip, else expected points alone — descriptive, never a
  second gate. The objective's own week one rides beside the served plan
  as `objective`, and the CLI, the moves card and the Planning board all
  say what it wanted when the two differ. Measured on the 2024-25 replay
  (`scripts/v7b_replay.py --arm restraint`, three seeds against one raw
  run): raw 1844 points with 15 hits and 65 transfers; restraint 1819 / 1867 / 1819 across seeds 20260901–3 (mean 1835, spread 48) with 5 hits and 45–54 transfers each — nine points behind raw, well inside the seed spread, for a third of the hits.

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

### The dark ledger (v14)

The whole UI is drawn in one design language, chosen on 2026-09-04: hairline
rules instead of card boxes, one sans face with tabular figures everywhere a
number appears, and colour spent only where it means something. It is dark by
default; the light theme is the same token set re-declared, so no component
picks a colour twice and nothing is styled for one theme alone. The tokens —
four surfaces, four text weights, the semantic colours with their tints, the
position hues, the turf, two radii — live in
`frontend/src/styles/theme.css`.

Eight rules govern colour, and the rest of the UI follows from them:

1. **Green and rust are directions** relative to something you care about:
   price up or down, better or worse than the plan, an easy or hard fixture,
   in or out, ahead or behind. Never chrome, never emphasis.
2. **Amber is doubt**: availability under 100%, a data warning, a stale feed.
3. **Blue is interaction**: the primary button, the active tab's underline,
   the active nav item, links, a focused input, the selected row. Blue never
   carries data.
4. **Grey is information**: labels, units, context lines, neutral values, a
   fixture of middling difficulty.
5. **The position hues are identity**: the position badge, a tile's stripe,
   the compare panel's header. Never a verdict.
6. **A tint** — a 14% fill behind one cell — may repeat a direction or a
   doubt, never behind a whole row and never on a heading.
7. **A bar** appears only where a magnitude against a known ceiling matters
   *and* several are compared in one view: the ladder's probabilities,
   ownership and EO in the Players table, scenario support in the moves and
   sensitivity tables, the chip threshold meter, the league race gap. Flat
   fill, 6px, no gradient, the number printed beside it.
8. **The turf** is the one patch of colour on any page that means nothing at
   all.

Every page is assembled from the same handful of pieces: a **Section** (a
small uppercase label over a hairline, no border box) holds the content; a
**Stat** is one label, one 22px value with its unit, one context line and an
optional meter; **Button** has three weights and one height and **Segmented**
is the toggle group built from it; a **Chip** is the tinted 2px tag used for
IN/OUT, fixture difficulty, attack/cover and availability; a **Bar** is rule
7; a **Callout** is the note, warning or error strip; **DataTable** is the
one table style every table in the app renders through or matches
class-for-class; and the pitch is muted turf with hairline markings and dark
92px player tiles.

If you change the UI, `frontend/src/kit/tokens.test.ts` is the rule-book your
change is held to: no `rounded-full`, no shadows, no gradients, no raw hex
outside `theme.css` and the shirt/turf tokens, monospace only in the job log
and the plan trace, and none of the retired colour names. The visual gate is
a screenshot pass — build the frontend, serve it with
`uv run gaffer ui --no-open-browser --port 8927`, then
`frontend/scripts/shots.sh <stage>` writes the six hubs in both themes to
`.superpowers/shots/<stage>/` (the shell is playwright's
`chromium-headless-shell`; if its cache under `~/Library/Caches/ms-playwright`
has been cleaned, `cd frontend && npx -y playwright@latest install
chromium-headless-shell` restores it and `CHROME_HEADLESS_SHELL=<path>`
points the script at the new version directory; the headless shell needs
`--blink-settings=preferredColorScheme=0` for dark; `--force-dark-mode` does
nothing).

### The six hubs

**This Week** — the answer. The advised XI on a pitch in formation rows,
shirts, C/V armbands, difficulty-tinted next-opponent chips; the bench in
substitution order; the transfer list with attack/cover tags; the captain
sentence telling you where your pick stands against the top-10k field
(cover or attack, with its error bar) and, when the league tilt moved the
armband, the run's own half-sentence saying why (v12 W5); the chip planner's
best week per
chip; the Friday/Tuesday digest cards; a re-run button (full or `--fast`).
An **EO lens** toggle tints the pitch by how owned each player is; a
**Table** toggle returns the dense squad table. Under the moves card sits
the **transfer ladder** (v13): one row per rung of hits with the moves, the
cost now and over the horizon, this week's and the horizon's expected
points, and the probabilities; your cap's row is highlighted and the rows
beyond it stay visible but muted; expand a row for that rung's squad and
exactly what the last hit bought; three selects set your max hits, max
transfers and hit bar (saved to `config.local.toml`; since v17e the
options they offer come from the settings rows, so a hand-edited value is
offered too) and rebuild the ladder in a couple of seconds. The moves card's heading names the live count and cap. Since
v16 the moves card also says which rung the walk chose and the one step it
refused, with its share and reason, and — when they differ — what the
objective wanted; the ladder card gains a **Hit bar** select, a *chosen*
chip on the served rung, the walk's steps in words, and a note when a
rebuild at another bar would choose differently. Below the moves sits
**What I did and why** (v16): closed until the deadline, then one of eight
reasons (injury, fixtures, eye test, price, chip, rival, gut, other) and a
line of text for the week you did something other than the advice, closed
again once the review has graded it. The digest cards are replaced by
**The week** (v16): a brief written by the classifier's `claude -p` command
from a facts document off the advice, the ladder, the trace, the ledger and
your note, checked mechanically so every number and every name in it is in
the facts, with a *Write the brief* button; when no brief passed, the card
falls back to the digest with the reason.

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
- *What-If*: lock, ban, force in or **must-sell** players, cap the hits and
  (v13) the transfers, and re-solve the real MILP; the baseline it diffs
  against is solved under your saved caps, so "original" is the plan the
  report served. The transfer ladder is on this tab too, above the
  sensitivity card. Must sell (v12 W3) is the constraint `ban` was
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

**League** — every league you are in, and one of them drives the plan.
The *Leagues* tab (v15) lists your private mini-leagues with rank, size,
last week's move, the gap to first or over second and what the dial *would*
do there, marks the **focus** league — the one whose standings set λ — and
lets you make any other the focus or set the **stance** (Auto · the live
word, Chase, Defend, Neutral) for it; both write through the same settings
overlay the Model tab uses. Public leagues (Overall, country, club) are a
rank line beneath. Click a private league for its *Race*: standings with
win probabilities, the trajectory, what the λ tilt is doing and why — and,
when it is not the focus, a note saying which league sets the plan and what
this one would want, its λ computed from its own standings and tilting
nothing; *Rivals* (each rival's squad, overlap, differentials against you);
*What if* (pin a haul or a blank and re-simulate the league — pricing a
week, not proposing transfers). The win-probability
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
  Since v16 your deviation note sits under the transfers lane ("You said:
  Gut — …") and a **Deviations by reason** table above the rows counts the
  graded gameweeks per reason code with the mean transfers-lane result, so
  the season can say which of your reasons cost and which paid.
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
| Thu 18:00 | `com.gaffer.advise` | `prices`, then `train` then `advise`; logs to `logs/prices.log` and `logs/advise.log`. The price bank comes first so the optimizer's timing term has a same-day log; a failed fetch does not stop the advice. Since v17d `advise` chains the brief, so the Thursday log ends with the brief's line (or its note) and Friday's digest headline comes from the brief. |
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

- `gaffer advise` (and `--fast` to skip the five-minute scenario sweep) —
  since v17d one call to `pipeline.weekly_run` (advise, render, brief; the
  train step is off here because the plist and the user run `gaffer train`
  first), the same body the web advise job runs with the train step on
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
- `gaffer brief` (v16) — write this week's brief from the banked advice:
  the same body the web button and the web advise job run; never fails,
  a dead command or a brief that did not pass its check is one printed
  line and the card falls back to the digest
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
- `cd frontend && npm run types` (v12 W5, one command since v17a) — not a
  `gaffer` subcommand: a developer command. It writes `frontend/src/schemas.json`
  from the live pydantic models and `frontend/src/types.generated.ts` from
  that. **Run it after any change to `src/gaffer/web/schemas.py`** and commit
  both files; `npm run types -- --check` exits 1 naming any file that
  drifted, and the two suites (`tests/test_v12_w5_gen_types.py`,
  `frontend/src/types.generated.test.ts`) fail on the same drift.
  `frontend/src/types.ts` is hand-written and is never overwritten by it

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

- **A golden board gates every refactor** (v17c). `tests/test_golden_board.py`
  replays one recorded gameweek through the whole weekly solve in a frozen
  working directory and compares the advice and solve state byte for byte
  with committed expected files, on a board chosen to carry a restraint
  step taken and refused, a hit, a chip row and a league tilt, so a "no
  diff" is evidence of something (CONVENTIONS §10). It skips, naming the
  file, when the models or the archive on disk are not the ones it was
  recorded under. Since v17g the board also carries a recorded `Inputs` —
  everything the solve was handed for that gameweek, as parquet — so the
  pure half of the pipeline, `build_advice`, is replayed and compared on
  **any** machine, with no `models/` directory at all; only the full
  `run_advise` replay still needs the recorded models. `python -m
  tests.golden_client --write` re-records the board after a retrain, and
  `--inputs` re-records the seam without restamping it.

Where the numbers live: `docs/superpowers/ROADMAP.md` (per-cycle results),
each cycle's spec in `docs/superpowers/specs/` (§Gates/§Outcome sections),
`reports/evaluation.json`, and the Model hub.

## 11. The version history, v1 to v18a

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

**v13 — the transfer ladder** (2026-09-04, one day after v12 closed). The
morning's free-transfer hotfix (§4) regenerated a GW3 board that still
wanted four moves at three hits, and one solve per hit cap showed the
objective and the raw points pointing different ways. The cycle put the
manager's appetite into the tool: `max_hits` / `max_transfers` obeyed by
the advice, the sweep, the alternatives, the chip table, the What-If
baseline and the season replay, and the ladder card that prices every rung
with probabilities from shared draws. Two reviews reshaped it before merge:
the cost column now shows the horizon's hits (a one-hit-per-week plan
spends 12, not 4), the draws are no longer clipped at zero (the clip had
inflated every rung by ~6 points and shrunk the gaps), and the caps the
ladder highlights come from the live config so the selects move the row at
once. Pins after: routes 48, job kinds 12, `Config` fields 57.

**v14 — the dark ledger** (2026-09-05). A design cycle, not a feature one:
no route, no number and no backend line changed. The user's verdict on the
built UI was that it lacked a unified design language, and the four choices
he made from mockups — a dark ledger rather than cards, ink plus tint plus
bars, one sans face with tabular figures and one blue accent, a muted-turf
pitch — became §4's eight colour rules. The branch moved in four stages so
every page moved at once: the token set, then five new kit primitives
(Button, Segmented, Chip, Bar, Callout) with the rest of the kit restyled,
then five reworks by hand (the nav, This Week's tiles, the pitch, the moves
and ladder tables, the button set), then a sweep of every hub and a
`tokens.test.ts` that pins the rules a reader cannot be asked to police.
`Card` kept its name over the new Section rendering, so 100 call sites did
not churn. The gate was the user's approval of headless screenshots of six
hubs in both themes, taken after each of the last three stages; there was no
replay to run. Frontend suite 814 → **866**; pins unchanged.

**v15 — leagues** (2026-09-06). The entry endpoint already listed every
classic league the manager is in; nothing read it. Now the League hub opens
on all of them: the private mini-leagues (the FPL `league_type` flag, no
size rule) in one table with rank, move, gap and the "would chase / would
defend" word, the public ones as a rank line. One squad can only be tilted
one way, so exactly one league — the **focus** — reaches the solver, as
before; the others get the full race, rivals and what-if for display, each
computing its own Strategy from its own standings. The user's three
decisions: mini-leagues only, a focus league rather than a blend or an
auto-pick, and a manual stance at full tilt. The stance is one pure
function (`apply_stance`) and one added call in `advise.py`; the focus is
`[league] focus` in the settings overlay resolved into `Config.league_id`,
so no reader of `league_id` changed. Two things the build corrected: the
protected v12 W5 pin that the settings whitelist never names `league_id`
made the focus row a reader named `focus`; and the standings fetch now pages
to your own row instead of stopping at 50 (the user was 80th of 138 the
week before). Routes 48 → **49** (`/api/league/leagues`), `Config` fields
57 → **58** (`stance`); Python 4110 → **4170**, frontend 866 → **893**.
Deferred to a model cycle: a blended stance across leagues.

**v16 — restraint and the brief** (2026-09-07). The user's ask, after a
week of the advice buying and selling more than felt right: let the ladder
decide how much to commit, write down why you deviated, and read the week
as prose. Three pieces. *Restraint*: the walk described in §4, inside
`build_ladder`, reading `hit_bar` through the live config; `advise.py`
(protected, one orchestrator diff shown to the user first) now saves the
components and the solve state, builds the ladder, and serves the chosen
rung's plan through a pure `serve_rung`, keeping the objective's own week
one beside it. *The note*: `reports/decisions.json`, `GET/POST
/api/decisions/{gw}` with the settings endpoint's refusal shape (unknown
reason, text over 280 characters, a future gameweek, before the deadline,
already graded), joined into the Review payload with a by-reason tally.
*The brief*: `brief.py` builds a rounded facts document, runs the presser
classifier's no-tools `claude -p` command, checks every number and every
capitalised name in the reply against the facts (sentence starts, `GW\d`,
the chips' names and a short allow-list exempt), banks the prose keyed by
the advice run's stamp and the prompt version, and is chained after the
web advise job and offered as `gaffer brief`; the Friday digest's headline
becomes the brief's first sentence. Things the build corrected: the
job-kinds pin lives in sixteen protected files, so the brief runs as an
anonymous job like the ladder rebuild (job kinds stay 12); a protected pin
on the objective's expected-points literal made the objective a keyword
dict; the served rung's *own* captain is served unless a note explains the
sweep's, because the objective never saw the rung's buy on its captain
table (Groß over Palmer on the GW4 board); the truth check reads every
string of the facts so a refused step's reason is sayable; and the first
brief called this week's XI points a horizon total, which prompt version 2
now forbids. Routes 49 → **51** (`/api/decisions/{gw}`, `/api/brief`),
`Config` fields 58 → **59** (`hit_bar`); Python 4170 → **4266**, frontend
893 → **910**. R1: raw 1844 points with 15 hits and 65 transfers; restraint 1819 / 1867 / 1819 across seeds 20260901–3 (mean 1835, spread 48) with 5 hits and 45–54 transfers each — nine points behind raw, well inside the seed spread, for a third of the hits.

**v17a — the wire types, one command** (2026-09-07). The first sub-cycle
of the deepening programme that the 2026-09-07 architecture review produced
(`docs/superpowers/plans/2026-09-07-v17-deepening-programme.md`): a tooling
cycle that changes no number. `cd frontend && npm run types` now writes
`schemas.json` and `types.generated.ts` from one module,
`frontend/scripts/gen_types.ts`, which holds the only copy of the compile
options, runs the Python half `scripts/gen_types.py` and compiles the result;
`npm run types -- --check` writes nothing and exits 1 naming every file that
drifted. Node runs the script as written. The vitest drift test imports the
writer's own `render`, CLAUDE.md's twelve-line node one-liner is one command,
and the eleven hand narrowings in `types.ts` stay where they are with their
written reasons. Gated by exercising the lever: a hand edit to each generated
file made the check fail naming that file and the writer cleared it. Pins
unchanged; Python 4266 → **4271**.

**v17b — restraint narrated once, on the server** (2026-09-08). The rung's
name and the step's sentence were written in four places and already
disagreed ("free transfers only" on the CLI, "No hits" in the ladder card).
Now `ladder.py` writes them once: every rung carries `label`, every step
`line`, the served `restraint` block `label`, `hit_cost` and `line`, the
`objective` block `line`; the CLI, the brief's facts, the moves card and
the ladder card render those strings and compose nothing, and a rail proves
the four surfaces carry the same string for every rung key. A v16 advice or
ladder on disk is backfilled on read (`load_ladder`, `ladder.narrated`).
Gated by a paired `gaffer advise --fast` on `main` and the branch that
differed only in the live-input noise a same-code pair also shows, with
every served decision identical. Pins unchanged; Python 4271 → **4288**,
frontend 910 → **923**.

**v17c — the golden board harness** (2026-09-08). The programme's remaining
refactors promise to change no served number, and v17b showed two live
runs minutes apart differ anyway. `tests/golden_client.py` adds the second
adapter behind `run_advise(cfg, client)`: a client that replays recorded
FPL responses, run in a scratch directory whose `config.toml`, Core
Insights, models and archive are the recorded ones (the last two pinned by
SHA-256, so a retrain skips the test with the file named). GW4 recorded
2026-09-08; the board carries two restraint steps taken and one refused, an
objective at two hits, twelve chip rows, a league tilt and a six-week plan.
Gate passed first run: byte-identical twice, every lever floor met, fixture
960 KB, no odds table anywhere. Nothing under `src/` changed. Pins
unchanged; Python 4288 → **4317**, frontend 923.

**v17d — one weekly pipeline module** (2026-09-08). The weekly run was
defined inside an HTTP router, imported from there by the job registry,
and re-assembled by hand in the CLI without the brief, which is why the
Thursday launchd run had no brief. `src/gaffer/pipeline.py` now holds it
once: `weekly_run(cfg, *, client=None, train=True, log=print)` runs train
→ advise → render → brief and returns a `RunResult` whose `record()` is
the job runner's stored dict. The `advise` job kind is defined in
`job_kinds.py` over it (train on), `gaffer advise` calls it with the train
step off (the plist runs `gaffer train` first), and the router keeps
request handling only. The brief gets the config in force rather than a
second read, and its own line now prints before the CLI's banner. Gated
on the golden board plus a parity test that runs the CLI entry and the
job kind over the recorded board with the LLM command stubbed to fixed
prose; passed first run. During the build the plan's "watch it fail" step
retrained the real models, so the golden was re-recorded on `main`'s code
before the gate (spec §10). Pins unchanged; Python 4317 → **4329**,
frontend 923.

**v17e — the config in force, one interface** (2026-09-08). Which value
of a knob was in force depended on which of seven readers a module
called: the loud parser, a cached serving view, and four private readers
that opened `config.toml` themselves, with three caches cleared from two
places. `config.py` is now the only module that opens either TOML file
(an AST rail says so): `config_in_force()` is the one cached,
never-raising read, `invalidate()` the one clearing, `load_config(path)`
the parser the CLI calls loudly. The four readers became fields
(`price_timing`, `xg_per_shot`, `news_lineup_providers`, and
`solver_top_n()` over `top_n`), so the `Config` pin moved 59 → **62**.
Bounds and the refusal sentence are stated once and the settings
registry reads them; the three ladder rows carry offered options, and
the ladder card renders its selects from the settings rows rather than
its own constants. The settings router stopped reading files. Gated on
the golden board (unmoved), a rail, two greps and screenshots; passed
first full run. Python 4329 → **4360**, frontend 923 → **925**.

**v17f — the served plan, owned once** (2026-09-08). "What does the user
see for GW7?" was answered across four modules and the shape of a served
week was written four times: an anonymous dict into `serve_rung`, a
thirteen-key dict out of it, nine fields splatted into `Advice`, and the
plan route re-parsing the file with its own coercers, pricing every move
a second time and running the bank forward because the artifact carried
no money. Now one frozen value, `ServedPlan` (`src/gaffer/served.py`),
owns the moves, the weeks with their prices, hit charge, chip, bank and
trace, the restraint walk, the objective's own week and the
alternatives. Its field names are the artifact's keys, so the write is
one `model_dump` and the read one `model_validate`. `advise` completes
it off the solve state it just saved — so the trace and the
price-timing charge are the ones the solve saw, not tonight's —
and `artifacts.served_plan(gw)` reads it back, filling those fields for
a file written before the cycle from that file's own solve state. The
plan route became a shape adapter: no coercers, no arithmetic, the wire
unchanged, which a recorded `GET /api/plan/4` over the golden board
proved byte for byte. The advice filename is now spelled once, in
`artifacts.py`. Python 4360 → **4369**, frontend 925 → **926**.

**v17g — `build_advice` as a pure module** (2026-09-09). `run_advise` did
two jobs in one 700-line body: fetch the world, then decide. Nothing could
run the deciding half without a network, six trained models and this
machine's own `reports/` directory, so the tests that guarded it asserted
on its *source text* — thirty-five of them read the function with
`inspect.getsource` and matched strings. It is now two functions with a
value between them: `gather_inputs` does the fetching and the disk, and
`build_advice(inputs, cfg)` does the deciding and touches nothing but its
argument. A rail proves that at run time by sealing both spellings of
`open` and rebuilding the board anyway. The thirty-five source pins became
fifty-three tests that assert what the run actually *did*, and the golden
board gained a recorded `Inputs`, so the decision half is now checked on a
machine with no models on it. Asking for purity surfaced seven quiet file
reads on that path — the ladder reloading a parquet and last week's advice,
three chip pricers reading the price log, the ticker reading the fixture
difficulty — each one a chance for a replay to be scored against tonight's
files instead of the recorded gameweek's. All seven now take the value the
run already holds. Nothing changed on screen, and no configuration field
was added. Python 4369 → **4386**, frontend 926 unchanged.

**v17h — This Week's data fetched once; one job hook** (2026-09-09). Every
card on This Week owned its own request, so one render asked the server
seventeen questions — four of them the identical "is a run in flight?", and
two of them the same EP decomposition under two spellings, one of which
fetched every player in the game to read the fifteen in your squad. The
awkward part was that per-card fetching is *right*: it is what lets a card
fail without blanking the page, reload after its own job, and not fetch at
all until its tab is opened. So what changed is the wire underneath, not the
cards: `usePageData` holds one in-flight request and one body per URL, shared
by every card and kept across hub navigations, and each card still calls for
itself and still keeps its own error. Seventeen GETs became fourteen, the
advice is read once across four hubs instead of once per navigation, the
squad-row assembly came out of the hub as a tested pure function, and the two
job hooks became one that streams or polls on its argument alone. The cycle's
own trap is worth knowing if you touch this: the cache holds a body until
something clears it, which is right for an artifact and wrong for a liveness
check — routing "is a run in flight?" through it made a cached 204 permanent,
so the button offered a solve the server could only refuse. That probe now
shares its request without caching its answer.

This closes the v17 deepening programme: eight sub-cycles, none of which
changed a number the advice serves.

**v18a — the gate, back on** (2026-09-12). The first sub-cycle of the v18
polish programme, which the 2026-09-12 final review
(`docs/superpowers/research/2026-09-12-final-review.md`) set up: eight
gated sub-cycles that change no served number. The golden board — the
thing every refactor since v17c is gated on — had been silently skipping
since the Thursday retrain moved the model files. It was re-recorded (the
board itself had not moved), the recorder was fixed so its two modes record
the same Inputs, one loud skip helper replaced three wordings, the pipeline
test runs alone again, and `CLAUDE.md` stopped saying three things that had
been false since v17. Python 4425 → **4427**, frontend 986 unchanged.

The suite grew from nothing to **4,425 Python + 986 frontend tests** along
the way, with a set of degradation rails that pin every honesty rule above
so a future change cannot quietly break one.

## 12. What is pending and what was left open

As of 2026-09-03. Nothing is in flight: every v12 workstream is merged and the
program is closed. What remains falls into six groups, in the order you
would act on them.

### 12.0 First: install the two new launchd jobs

`launchctl list | grep com.gaffer` shows all **nine** jobs loaded on this
machine (checked 2026-09-08; until then `com.gaffer.backup` and
`com.gaffer.core-insights` were never installed, which is how v17d's
retrain incident found no backup). One command:

```bash
./scripts/install_automation.sh
```

Then `launchctl list | grep com.gaffer` should show nine. This is the
single most useful thing on the list: everything in §9 that cannot be
rebuilt is unprotected until the backup job runs.

### 12.1 Things only you can check — the live spot-checks

**v13, the ladder (2026-09-04):** on This Week, the ladder card shows five
rows with the 2-hit row highlighted and the 3-hit row muted; change *Max
hits* to 1 and the highlight moves within a few seconds without a re-run;
expand the 1-hit row and the "what the last hit bought" line names one
extra move and its horizon cost; the moves card heading reads "1 free
transfer · cap 2 hits"; the Settings tab lists the two new rows with source
*local* after the change; the What-If tab's *Max transfers* select at
"bank" re-solves to no moves.

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
- **The light theme's turf reads more saturated than the mockup** (v14). The
  final screenshots flagged it; the value shipped is the spec's, so changing
  it is a decision rather than a fix.
- **The empty state's shell command borrows the browser's monospace face**
  (v14) — it is a bare `<code>`, with no `font-mono` class, which is also why
  `tokens.test.ts` cannot see it.
- **The overview's "would" word is gap-sign only** (v15): rank 1 says
  defend, anything else says chase, with no dead-band, because the row costs
  one standings page and the dial's real answer (which honours the band)
  appears when the league is opened. The column is labelled "would".
- **A non-focus league's sim shares the focus league's one-entry cache
  slot** (v15): switching leagues on the What-if tab re-runs the Monte
  Carlo rather than remembering both.
- **The chip step reason needs a `chip_plan` on the solve state** (v16):
  `advise.py` writes it from the chip table's `play_now` rows, so a ladder
  rebuilt off a state written before v16 gives no chip reason and falls
  through to the next one.
- **Sentence-initial names escape the truth check** (v16): English
  capitalises sentence starts, so the first word of a sentence is never
  checked; the prompt forbids opening a sentence with a player's name,
  and the check catches the same name anywhere else.
- **The walk can step past the objective's own hit count** (v16): the
  policy is symmetric by design — on the GW4 board it served one hit where
  the objective wanted none, on a 60.25% share — and the replay in §4 is
  the evidence it is net positive over a season. A rule that the walk
  never goes above the objective's hits is a one-line candidate if a
  season says otherwise.

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
