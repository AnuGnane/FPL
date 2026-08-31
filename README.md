# gaffer

An advisor-only Fantasy Premier League tool. It predicts player points with
per-component LightGBM models, plans transfers over a multi-gameweek horizon
with a MILP (PuLP modelling, HiGHS solver with a CBC fallback), and writes an
HTML report. `gaffer ui` serves the same advice as a local web app.

It never logs into FPL and never makes transfers. It reads public FPL endpoints
only; you apply its advice yourself in the official app.

## First-time setup

A fresh clone has no data and no models. Set `fpl.entry_id` in `config.toml`,
then:

```
uv run gaffer build-history   # downloads data/history/*.parquet (slow, once)
uv run gaffer train           # trains the component models into models/
uv run gaffer advise          # the weekly run
```

`build-history` caches the downloads under `data/raw/vaastav/`, so re-running
it is cheap. `train` refuses nothing but `advise` refuses to run without the
model files.

## Weekly ritual

Before the Friday deadline:

```
uv run gaffer advise
```

That refreshes live data, predicts, optimizes, prints the action list, and
writes `reports/gw{N}-report.html` (plus `reports/gw{N}-advice.json`). Open the
HTML report for the detail behind the terminal summary.

Before GW1 there is no squad to transfer from, so the run builds an opening
fifteen out of the full 100.0m budget instead of erroring — the "buys" are the
whole squad and there are no chips to consider yet.

Or let the installed Thursday 18:00 launchd job do it and read the report at
your leisure — that run does `gaffer train` first, then `gaffer advise`, logging
to `logs/advise.log`.

## Commands

| Command | What it does |
|---|---|
| `gaffer advise` | Full weekly run: refresh, predict, optimize, report. Requires trained models and `fpl.entry_id` in config. |
| `gaffer advise --fast` | Skips the ~5-minute scenario sweep and serves the raw optimum, without the risk spread around it. |
| `gaffer build-history` | Download the `train_seasons` archives into `data/history/`. Run once, before the first `train`. |
| `gaffer refresh` | Pull the latest FPL data into `data/live/`. |
| `gaffer train` | (Re)train all models on history + live data; writes to `models/`. |
| `gaffer prices` | Likely price changes tonight among the 200 most-owned players; banks every player's reading to `data/live/price_log.parquet`. |
| `gaffer digest --kind friday\|tuesday` | The Friday briefing or the Tuesday debrief: written to `reports/`, shown as a macOS notification. |
| `gaffer league` | Mini-league standings and rival ownership for `fpl.league_id`. |
| `gaffer live` | In-gameweek tracker: your live points and the projected league table while matches are on. |
| `gaffer field-scrape [--gw N] [--force]` | Bank a gameweek's top-10k sample: the squads (anonymised) and their effective ownership. |
| `gaffer league-sim [--seeds a,b,c]` | Monte Carlo of your mini-league: P(win), P(top 3), expected finish and the margin fan. |
| `gaffer backtest [--season 2025-26] [--start-gw 5] [--horizon N] [--chips]` | Replay a past season following the tool's own advice. |
| `gaffer ui [--port N] [--no-open-browser]` | Serve the local web UI on 127.0.0.1:8927. |

## Configuration

`config.toml`:

```toml
[fpl]
entry_id = 2210493   # your FPL team ID
league_id = 1794743  # mini-league ID for rival tracking

[optimizer]
horizon = 6          # gameweeks planned ahead
decay = 0.85         # per-GW discount on future expected points
vice_weight = 0.1    # weight on the vice-captain's expected points
bench_weight = 0.10  # weight on bench points
ft_value = 1.5       # points value of holding a free transfer
itb_value = 0.05     # points per 1.0m in the bank at horizon end
hit_cost = 4         # points charged per extra transfer

[odds]
# api_key = "..."    # optional, from the-odds-api.com

[news]
enabled = true             # live injury / line-up sources
lineup_absence = true      # damp a regular the predicted XI left out
lineup_start_floor = 0.0   # off: never raise a p_play toward a predicted start
llm_classifier = false     # off: the presser classifier logs, never serves
llm_shadow = true          # log what it would have done
llm_command = 'claude -p --output-format json --disallowedTools "Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,Task,NotebookEdit"'
llm_timeout_s = 300        # per batch of 40 texts

[data]
train_seasons = ["2022-23", "2023-24", "2024-25", "2025-26"]
current_season = "2026-27"
```

`entry_id` is the number in your FPL team URL. `league_id` likewise from the
mini-league URL.

The `[news]` block is optional — every key above is its default. `llm_*` drive
the presser classifier, which runs on your own Claude subscription through
whatever `llm_command` names and, with `llm_classifier = false`, only ever
writes `data/live/presser_log.parquet`.

The default `llm_command` hands the model no tools. The texts it classifies
are scraped from the web, so they are untrusted by construction, and a job
whose whole output is one word from a six-word vocabulary has no use for a
shell or a file. If you point `llm_command` at a different CLI, keep the
no-tools posture.

### `[league]`

Also optional, and also all-defaults. League mode itself is gated by
`fpl.league_id`, not by a switch here.

| Key | Default | What it does |
| --- | --- | --- |
| `z_scale` | 1.5 | Points of gap per unit of z before the tilt moves. |
| `lambda_cap` | 0.5 | The most the tilt may bend the candidate board. |
| `sigma_floor` / `sigma_cap` | 8 / 30 | Bounds on the weekly-points sigma the gap is measured in. |
| `sigma_min_weeks` | 6 | Gameweeks of history before sigma is estimated rather than assumed. |
| `z_deadband` | 0.25 | `\|z\|` under this is noise: no tilt at all. |
| `tier_eo` | true | The live tracker's top-10k EO column. |
| `tier_sample` | 300 | Entries sampled from the top 10k. |
| `field_scrape` | true | v8c: the scheduled version of the same sample, which also keeps the squads. |
| `field_sample` | = `tier_sample` | Sample size for the scheduled scrape. |
| `sim_n` | 2000 | Simulations per mini-league Monte Carlo run. |
| `rival_drift` | 0.5 | How far a rival's squad drifts toward the field template over the rest of the season. 0 freezes every squad. |

## Bookmaker odds (optional)

`[odds].api_key` takes a free key from [the-odds-api.com](https://the-odds-api.com)
— the free tier allows 500 requests a month and `advise` spends one pull a
week, so a weekly run never comes close to the cap.

With a key, market prices for the upcoming fixtures are inverted into an
expected goals-against per team and blended into the team model's clean-sheet
and goals-conceded predictions (70% market, 30% model) for the fixtures the
feed covers. Everything else — fixtures the feed misses, a dead key, a club
name that fails to match — falls back to the pure model output.

With no key at all the whole step is skipped silently; odds never block or
change the shape of the advice, they only sharpen the defensive predictions.

## League strategy

When `league_id` is set, `advise` reads your mini-league and picks a stance
against the leader (or, if you lead, the closest rival):

- **chase** — you are behind by more than noise, so the optimizer favours
  players your rivals do *not* own. Catching up needs differentials.
- **defend** — you are ahead by more than noise, so it mirrors rival ownership
  and protects the lead.
- **neutral** — the gap is inside the noise, so it is exactly the v1
  points-max solve, no tilt at all.

The stance is automatic; there is no flag. It comes from λ, a tilt strength
derived from the points gap, the weeks left in the season, and a per-gameweek
score sigma. λ is positive when chasing, negative when defending, zero when
neutral, and capped at ±0.5. It only tilts the pool the MILP chooses from —
reported expected points are always the raw model numbers.

Alongside it the report carries:

- **attack / cover tags** on each buy: `attack` for a player under 30% rival
  effective ownership (a punt on the field), `cover` at 70% or above (matching
  a player the league already has), blank in between. Untagged when there is no
  league to be different from.
- **a win-probability column** in the league table: P(you finish above that
  rival), a normal approximation from the current gap and the weeks remaining.
  Treat it as a rough steer, not a forecast — it assumes independent scores and
  a fixed sigma.

### The simulated league (v8c)

The League hub's win-probability card is a Monte Carlo, not a formula: 2,000
seeded seasons of your actual mini-league, every rival on the squad he last
played, per-player noise from the same sigma table the scenario sweep uses,
and rivals drifting toward the top-10k template at `rival_drift`. It reports
P(win), P(top 3), expected finish, per-rival P(beat) and a fan of final
margins — with its `n` and its seed printed underneath, because a probability
nobody can reproduce is a decoration.

The managers are **not** simulated as independent. Every week carries one
shared factor and each entry is exposed to it in proportion to how much of the
top-10k template its squad owns, measured off the banked field sample. Two
managers' weekly scores correlate at 0.59 in a real fifty-team mini-league
and 0.68 in the top-10k sample, and simulating them apart made every margin
1.6-1.8x too wide — a fan that pushes every probability toward 0.5 in both
directions. On league 1794743 turning it on moved P(win) from 0.19 to 0.36
and expected finish from 8.7 to 5.6. Each entry's own spread is
unchanged; only the comparisons between them move. With no field sample
banked the card falls back to independence and says so.

```
uv run gaffer league-sim --seeds 1,2,3
```

prints the same headline under three seed bases with the spread, which is the
only form a *recorded* claim about this number may take
(`docs/superpowers/CONVENTIONS.md` §1).

The **What if** tab prices a week: pin a haul, a blank or a different armband
and the league is re-simulated with that event fixed. It is not the squad
What-If Lab — no MILP is re-solved and no transfer is proposed. The question
is "what would that week do to my title odds".

None of this feeds the optimizer. The λ tilt remains the only thing that
shapes advice; the simulation is measurement and display.

## Live gameweek

```
uv run gaffer live
```

Read-only, for while the matches are on. Prints your live points and a
projected league table, with two caveats it states itself: bonus points are
provisional, reconstructed 3/2/1 from the current BPS table until FPL settles
each match, and no autosubs are applied — the XI is scored as picked, so bench
points never count. The web UI's Live page projects the autosubs as well; the
CLI stays the plain read. Between gameweeks it prints "no gameweek in
progress" and exits clean.

## Local web UI

```
uv run gaffer ui
```

Serves the whole tool as a local web app on <http://127.0.0.1:8927> and opens
your browser. `--port N` moves it; `--no-open-browser` leaves the browser
alone. It binds the loopback interface only and has no login — that is the
whole security model, so do not put it behind a public proxy.

Seven pages: **This Week** (the recommendation, with a pitch view, the chip
planner's best week for each unused chip, and a re-run button), **What-If
Lab** (lock, ban or force in players, cap the hits, and re-solve the real
MILP against the saved pool — the plan diff shows what changed; a
sensitivity card re-solves the same board twenty times with every expected-
points cell knocked by its own plausible error, so a move that survives
seventeen of twenty solves can be told apart from one that survives twelve;
and your own pins are listed and editable beside it, with a **Drafts** tab
alongside where you name a set of what-if constraints, keep up to twelve of
them, and compare any six side by side against today's board with the
unconstrained optimum as the reference row), **League
Race** (standings, trajectory, win probability and what λ is doing, with
rival intel a click away: each rival's squad, overlap and differentials
against yours), **Live** (in-gameweek points, auto-refreshing: the auto-subs
FPL would apply if the afternoon ended now, a race chart of where your score
is heading — points banked plus the expectation still owed by every unfinished
match, against the pre-gameweek plan — and what you need to take or hold the
league places either side of you), **Players**
(the candidate pool, with the "why 6.8?" breakdown behind every name, and a
**Pin** button on each row for the weeks you know something the model does
not, and a ☆ that stars a player onto your watchlist — a bookmark, not a pin:
it widens the movers card's price-alert watch set and adds him to the Friday
digest's flagged section, and claims nothing the model has to obey),
**History** (past runs, expected versus actual, price charts) and **Runs &
Health** (data freshness, model metrics, the launchd log, re-run buttons).
A fixture ticker sits alongside them and is embedded read-only in the
What-If Lab. A three-state theme toggle in the sidebar footer follows your
system by default, or holds dark or light if you pick one.

Two things the Live page will not pretend to know. The race trajectory lives
in the server process and nowhere else — restart `gaffer ui` mid-afternoon and
it starts again from that moment, which is the price of a page that writes
nothing. And the safety numbers are league places only: an overall-rank
cushion would need every one of ten million entries' live scores, and no
public endpoint gives them.

### Pinning a player (v8e)

`Pin` on any row in the Players page sets your own probability of playing, or
your own expected minutes, for the coming gameweek. It is applied **last** —
over the official flag, the injury feed, the predicted line-up, the notable-
absence damp and the presser classifier — because those are all sources of
evidence and you are the one who watched the press conference. A pin on
`p_play` carries `p60` and expected minutes with it so the three stay
coherent; a pin on a player the model has zeroed is taken literally, as "he
starts and he lasts".

Three things it deliberately will not do. It applies to the imminent gameweek
only, like every other team-news adjustment, because a claim about Saturday
says nothing about the gameweek after — though it does cover both fixtures of
a double gameweek, since "he is fit" is a claim about the player and not
about one team sheet. It cannot override expected *points* —
only minutes — so a bad afternoon cannot rewrite the model's whole opinion of
a player. And it is recorded rather than hidden: the availability artifact and
the daily snapshot both carry an `override` marker, This Week's why-panel
names every active pin beside what the model had when you set it, and
`[news] overrides = false` in `config.toml` switches the whole thing off
without deleting anything.

The pins live in `reports/overrides.json`. Because the two availability passes
inside an advise run are indistinguishable from the inside, a pin lands on
both the news arm and the news-shadow control arm — which means a pinned
player shows no *news* effect in the shadow log at all, rather than the news
layer being credited with a move you made.

### Sensitivity and drafts (v8e)

**Run sensitivity** on the What-If tab re-solves the saved board twenty times
under seeded noise drawn from the same minutes-driven error scale the advice
sweep uses, and writes `reports/sensitivity_gw{N}.json`: how often each buy,
sell and captain survives, the modal plan, and what the best *differing* plan
would have cost priced on the true board. That last number is signed — the
plan the sweep reaches most often is not always the one the true board prices
highest, and when they disagree the card says which way round it is. Chips
are not swept: the solver's plan object carries no chip, so there is nothing
to count.

The seed is the configured `[scenarios] seed` plus a million plus the
gameweek, which keeps the sweep's draws independent of the advice path's own
per-gameweek seeds rather than a replay of the draws it already gated its
moves on. It takes about five seconds, it never runs inside `gaffer advise`,
and it never changes a served number — it is a report about the plan, not a
revision of it. With the same seed it is the same report.

A **draft** is a named set of what-if constraints in `reports/drafts.json`,
not a frozen squad, so it still means something after Thursday's price changes
and Friday's injury: comparing re-solves each draft against today's board and
stamps each row with when it was solved.

### Uncertainty and calibration (v8g)

Every expected-points number in the tool now carries a range, and the tool is
explicit about which of two different uncertainties each range is.

**Bands.** The squad table and the player explorer print a `Range` column
beside `xPts`: the p25 and p75 of *what he might score*. Two variances added,
because they are variances of independent things — football's own (whether the
goal goes in, whether the clean sheet holds, who takes the bonus, measured at
3.2 points of variance per point of expected points over three seasons of
`player_gw`) and the model's estimation error out of the scenario sweep's
calibrated σ table. The first is an order of magnitude larger.

**These bands are wide, and that is the finding.** Haaland at 5.93 expected
points comes back with σ 4.4 and a p25–p75 of about 2.8 to 8.7. Anyone
selling you a tighter range on a single footballer's single gameweek is
selling you an estimation error and calling it a forecast.

It is quartiles, not a plus-or-minus. The variance is absolute, so the draw
clips at zero and the centre is shifted down to keep the range averaging the
forecast — the band is not symmetric about the headline.

**xMins reaches the band through the EP, not around it.** The calibrated σ
table is close to flat across xMins bins at a fixed EP, so at *equal* expected
points a rotation risk and a nailed-on starter get nearly the same absolute
band. What separates them is that the rotation risk's expected points are
lower to begin with, which narrows the absolute band and widens the relative
one.

A player with no minutes model shows an em dash, not a range of zero width.
"We have no minutes prediction for him" is a different claim from "his minutes
are certain", and the second is the one that loses money.

**Haul and blank.** A player with a real chance of ten-plus points, or a real
chance of two or fewer, gets a chip on his row. Both are tails of the band
above — the same distribution, read at 10 points and at 2 — so both price what
he might score rather than how precisely he was estimated. They are still a
normal approximation to a lumpy, discrete thing, and the tool says so in the
tooltip rather than in a disclaimer nobody reads. What it will not do is
answer 0% or 100%: no player and no gameweek gets a certainty.

**Captain confidence.** Under the pitch, one sentence about what the graded
record actually says: *"the model's captain outscored yours in 4 of 5
comparable gameweeks (2 you agreed on)"*. A gameweek where you picked the
model's own captain is quoted beside that record and is in no denominator of
it — agreeing with the tool is not evidence for or against the tool. Below
four *disagreements* it declines to have an opinion and says how many
gameweeks it has looked at. There is no percentage anywhere in it, because
there is nothing to compute one from.

**Sensitivity margin.** The sensitivity card's noise line is the one place
that quotes **estimation** σ, and it says which one it means: "how wrong the
forecast for the players that separate the two plans might be". Football's own
variance is deliberately absent, because both plans are solved off the same
board — an outcome shock hits them equally and cannot reorder them. When the
gap between the two plans is inside that number, the card appends the caveat
to the margin rather than in place of it: which plan is ahead and how solid
the ordering is are two separate facts.

**Model → Quality** gains four things: a reliability curve for `P(starts)`
(the model has emitted it since v8a and nothing rendered it), a y = x
reference on every calibration curve with the observation count under it, a
scatter of your points against the model's for every graded gameweek, and a
table of last week's biggest misses with the sign kept — a positive miss is a
player the model under-rated, a negative one is a transfer it may have talked
you into.

Both axes of that scatter come off the decision ledger, where `review` hand-
scores your squad and the model-composite squad against the same results
frame, so the diagonal is a real reference and the vertical distance is in
points. The misses table waits for FPL to mark the gameweek `data_checked`,
which is usually the morning after the last fixture rather than the final
whistle — a card that appeared at full time would be naming players off
provisional bonus.

Every one of those cards is **absent** rather than empty when its artifact is
missing. Nothing here needs a new command, a new job or a config key: it all
reads what `gaffer advise`, `gaffer evaluate` and `gaffer review` have already
banked.

**Compare radar.** Ticking two to four players in Explorer now draws an
overlaid radar over attacking share, minutes security, set-piece duty,
three-week fixtures and form, each axis scaled 0–100 against the players
currently listed. Comparing a goalkeeper with a forward is allowed and
captioned: the axes measure different jobs, and the chart is the quickest way
to see that.

The pages read the artifacts `gaffer advise` writes, so the UI works offline
apart from League Race, Live and the rival pages, which need the FPL API and
say so when it is unreachable. Nothing here logs into FPL or submits anything;
you still apply the advice yourself.

### Developing the UI

The shipped wheel contains a pre-built frontend, so **end users never need
node**. To work on it:

```
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to 127.0.0.1:8927
npm run test       # Vitest + React Testing Library
npm run build      # emits into src/gaffer/web/static/, which the wheel ships
```

Run `uv run gaffer ui` in another terminal while `npm run dev` is up: the Vite
dev server proxies `/api` to it, so the React app hot-reloads against the real
backend. The build output is untracked, so a fresh clone serves a "frontend
not built" message until you run `npm run build` once.

## Backtesting

```
uv run gaffer backtest --season 2025-26 --start-gw 5 --horizon 6 --chips
```

Replays a past season following the tool's own advice, retraining as the
season goes. Two things are truncated at each week's deadline, not one: the
training data the models are refit on, and the feature rows for the later
gameweeks of the horizon — those are rebuilt each week from history up to
that deadline plus the fixture list, so a GW+1 row never carries a result
that had not been played yet.

- `--horizon N` plans N gameweeks ahead but executes only the first, then
  re-plans next week — the same receding horizon the weekly run uses.
  `--horizon 1` (the default) is the myopic single-week replay.
- `--chips` lets the replay play wildcard, bench boost, triple captain and
  free hit when a chip clears its gain threshold, tracking the two half-season
  chip sets separately (the first set expires after GW19).

## Retraining

```
uv run gaffer train
```

Trains the component models (minutes, attacking, defcon, saves, bonus, team)
plus a calibration model that corrects the known level bias in the assembled
expected points (one additive per-position delta, scaled by each player's
chance of a 60-minute appearance), and saves each as a `.joblib` plus a
`.meta.json` in `models/`. `advise` refuses
to run if any model file is missing. Retrain periodically as the current season
accumulates data — the Thursday automation retrains every week.

At a season rollover, edit both `[data]` keys together: append the finished
season to `train_seasons` **and** set `current_season` to the new one, then run
`gaffer build-history` and `gaffer train`. `season_idx` is derived from
`len(train_seasons)`, so adding a season without moving `current_season` on
makes the live season collide with the one you just archived.

## Where things live

- `data/raw/`, `data/history/`, `data/live/` — downloaded and derived datasets (gitignored)
- `data/manager_tenures.toml` — EPL head-coach spells; the one file under
  `data/` that is committed, because it is curated knowledge rather than
  fetched data (absent, the rotation features fall back to club-season windows)
- `data/raw/field/{season}/gw{N}.json` — the top-10k squads sampled for that
  gameweek. Permanent, and anonymous: entries are keyed by their index in the
  sample, never by entry id.
- `data/live/price_log.parquet` — one row per player per UTC day: FPL's own
  price predictor reading, banked by the nightly `prices` job. Every player,
  not only the ones near a threshold — the row worth having in February is
  the one that was not an alert in August. Read by nobody yet; a season of it
  is what a price-timing term would need.
- `data/live/field_eo_log.parquet` — one row per (gameweek, scrape day,
  element): effective ownership in the top 10k with its standard error and
  its sample size.
- `data/raw/league/{season}/{entry}-{gw}.json` — one entry's squad for one
  finished gameweek. Your own entry is banked here too, in the same layout as
  every rival's, so the review can grade a September decision in December
  without asking the API again.
- `data/raw/league/{season}/{entry}-history.json` and `-transfers.json` — your
  per-gameweek points, rank, bench points and transfer cost, and every
  transfer you have made. Replaced on write, because both are cumulative.
- `models/` — trained model files (gitignored)
- `reports/` — `gw{N}-report.html` and `gw{N}-advice.json` (gitignored)
- `reports/league_sim_history.json` — one banked headline per gameweek, which
  is what the league card's sparkline draws.
- `reports/decision_ledger.json` — one banked grade per reviewed gameweek: the
  four decision lanes in points and in title odds, the reconciliation against
  FPL's own score, and the best eleven you could have fielded. Written once,
  when the gameweek's results are final, and never re-derived — the model's
  pre-deadline advice is pruned after twenty runs, so the grade has to outlive
  it.
- `reports/overrides.json` — your own pins on a player's probability of
  playing or expected minutes, with what the model had for him when you set
  each one. Read at serve time only; never a training feature.
- `reports/watchlist.json` — starred players, up to a hundred, each with an
  optional note. Widens the movers card's watch set and adds a section to the
  Friday digest, and is read by nothing that solves or trains.
- `reports/digest_friday.json` / `reports/digest_tuesday.json` — the newest
  briefing and debrief, replace-on-write. A section whose input is missing is
  absent rather than empty.
- `reports/components_gw{N}_prev.parquet` — the previous run's component
  breakdown, one slot, kept so "since last run" can name the players the
  retrain moved rather than only saying the plan changed.
- `reports/drafts.json` — named what-if constraint sets, up to twelve.
- `reports/sensitivity_gw{N}.json` — one banked robustness sweep per
  gameweek: move frequencies over twenty noised re-solves, the modal plan and
  the margin to the best differing one.
- `src/gaffer/uncertainty.py` — EP bands and haul/blank tails: outcome
  variance plus the scenario sweep's estimation σ, in quadrature
- `src/gaffer/confidence.py` — ledger-derived confidence tiers: counts, never
  percentages
- `src/gaffer/misses.py` — the last scored week's biggest forecast errors
- `logs/` — output from the launchd jobs (gitignored)
- `frontend/` — React/Vite source for the web UI; built output lands in
  `src/gaffer/web/static/` (gitignored, shipped in the wheel)

## Price changes

FPL applies price changes at roughly 00:00 UK time. The nightly `prices` job
runs at 23:15 **local** time to catch them before they land, so if your machine
is not on UK time, adjust the `Hour`/`Minute` in
`scripts/com.gaffer.prices.plist` and reinstall.

## Digests

Two scheduled summaries, each written to `reports/` and shown as a macOS
notification.

- **Friday 17:00** — `gaffer digest --kind friday`. The deadline countdown,
  the advised move and captain, watched players the news layer or a press
  conference is unhappy about, tonight's likely price changes, one
  differential from the alternatives table, and the data-staleness warning if
  there is one.
- **Tuesday 09:30** — `gaffer digest --kind tuesday`, half an hour after the
  review job. Last week's score against the model's, the worst lane and its
  label, the hindsight-XI gap, the league win probability and which way it
  moved, and the largest forecast miss.

Both appear on This Week as the **Digest** card, newest first, and both have a
button there. A section with nothing to say does not appear at all: "no data"
is a sentence about the tool, and its absence is a sentence about the season.

The notification is best-effort — it runs `osascript`, swallows every failure,
and is macOS-only. Turn it off with:

    [digest]
    notify = false

## Automation

```
./scripts/install_automation.sh
```

Substitutes the project path into the seven plists in `scripts/`, copies them to
`~/Library/LaunchAgents/`, and loads them: `com.gaffer.advise` (Thursday 18:00),
`com.gaffer.prices` (nightly 23:15), `com.gaffer.snapshot` (daily 17:00, banks
the availability log the news corrector will train on), `com.gaffer.field`,
`com.gaffer.review`, `com.gaffer.digest-friday` (Friday 17:00) and
`com.gaffer.digest-tuesday` (Tuesday 09:30).
Re-run it after moving the project.

- **Saturday and Sunday 12:30** — `gaffer field-scrape`, an hour after the
  11:30 deadline: samples ~300 top-10k entries, banks their squads and logs
  their EO. A gameweek already banked is a no-op in milliseconds, and a run
  that finds the live tracker has just done the same fetch reuses it rather
  than asking the API twice in an hour.
- **Tuesday 09:00** — `gaffer review`, grading every gameweek FPL has
  finalised since the last run. Tuesday rather than Monday because FPL
  finalises a weekend gameweek's bonus and its `data_checked` flag on the
  Monday, sometimes late; a midweek gameweek is picked up the following
  Tuesday or by the Model hub's **Review last week** button. Already-reviewed
  weeks are a no-op that prints one line.
- **Friday 17:00** — `gaffer digest --kind friday`, the briefing. After the
  pressers are in and before the deadline.
- **Tuesday 09:30** — `gaffer digest --kind tuesday`, the debrief. Half an
  hour after the review job, so it reads a ledger that has already been
  written rather than one still being graded.

Nothing else is scheduled. The rest of the work the UI can start — including
`sensitivity`, twenty noised re-solves of this week's board in about five
seconds — runs only when you press its button.

Check they are loaded with `launchctl list | grep com.gaffer`. Remove with
`launchctl unload ~/Library/LaunchAgents/com.gaffer.{advise,prices,snapshot,field,review,digest-friday,digest-tuesday}.plist`.

## Tests

```
uv run pytest -q
```

## Docs

- Design spec: `docs/superpowers/specs/2026-08-23-fpl-ml-advisor-design.md`
- Implementation plan: `docs/superpowers/plans/2026-08-23-fpl-ml-advisor.md`
- v3 design spec: `docs/superpowers/specs/2026-08-24-gaffer-v3-ui-design.md`
- v3 implementation plan: `docs/superpowers/plans/2026-08-24-gaffer-v3-ui.md`
