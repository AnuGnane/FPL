# gaffer

An advisor-only Fantasy Premier League tool. It predicts player points with
per-component LightGBM models, plans transfers over a multi-gameweek horizon
with a MILP (PuLP modelling, HiGHS solver with a CBC fallback), and writes an
HTML report. `gaffer ui` serves the same advice as a local web app.

It never logs into FPL and never makes transfers. It reads public FPL endpoints
only; you apply its advice yourself in the official app.

New to the project, or coming back to it? **[docs/GUIDE.md](docs/GUIDE.md)**
is the orientation manual: how everything works end to end, every feature and
how to use it, the version history, and how the project measures itself. This
README is the setup and reference document.

**Contents:** [First-time setup](#first-time-setup) ·
[Weekly ritual](#weekly-ritual) · [Commands](#commands) ·
[Configuration](#configuration) · [Bookmaker odds](#bookmaker-odds-optional) ·
[League strategy](#league-strategy) · [Live gameweek](#live-gameweek) ·
[Local web UI](#local-web-ui) · [Backtesting](#backtesting) ·
[Retraining](#retraining) · [Where things live](#where-things-live) ·
[Price changes](#price-changes) · [Digests](#digests) ·
[Automation](#automation) · [Tests](#tests) · [Docs](#docs)

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
| `gaffer evaluate --calibration` | Per-gameweek reliability for the probabilities the weekly run actually served. Reads banked components, refits nothing, takes seconds. |
| `gaffer ui [--port N] [--no-open-browser] [--lan]` | Serve the local web UI on 127.0.0.1:8927. Always a single process — see below. |
| `gaffer snapshot` | Bank today's availability state into the daily log (idempotent per UTC day). |
| `gaffer review` | Grade every gameweek FPL has finalised since the last run into the decision ledger. |
| `gaffer track-pens` | Predicted penalty EP against the penalties actually taken. |
| `gaffer understat` / `gaffer cups` | Auxiliary history ingestion (Understat player-match data; cup and European match dates). Long first runs, resumable, rarely needed again. |
| `gaffer evaluate [--news-shadow] [--calibration]` | The model scorecard; the news layer's would-be effect; served-probability reliability. |
| `gaffer evaluate --flag-latency` | How much warning a status change gave before the deadline, and whether the player then started. Reads the banked availability snapshots; fills once fourteen snapshot days exist and a covered gameweek is `data_checked`. |
| `gaffer evaluate --presser-grades` | The presser classifier's verdicts against who actually started: precision of absence per class, over the verdicts recorded *before* their gameweek's deadline. |
| `gaffer diagnose-zeros` | Decompose the error on players who blanked, into `reports/zeros_diagnostic.json`. |
| `gaffer calibrate-decisions` / `calibrate-injuries` / `calibrate-noise` | Rebuild the committed calibration assets from replays and scrapes. Occasional, not weekly. |
| `gaffer backup [--to DIR] [--rsync TARGET]` | Tar the data no command can rebuild into `~/gaffer-backups` (or `[backup] dir`), keep the last fourteen. |
| `gaffer tidy [--apply] [--older-than DAYS]` | List — and only with `--apply`, delete — replay logs nothing references and stale run logs. |
| `gaffer mcp` | Serve this tree to an MCP client over stdio. Six read tools, no writes. |

### `gaffer backup`

Writes `~/gaffer-backups/gaffer-<YYYYmmdd-HHMMSS>.tar.gz` — about 16 MB — and
prunes to the newest fourteen. `[backup] dir`, `[backup] keep` and
`[backup] rsync_target` set the defaults; `--to` and `--rsync` override them
for one run.

In the archive: `data/live/`, `data/raw/field/`, `data/raw/tier_eo/`,
`reports/` and `models/`. **`data/raw/field/` is in it and the spec did not put
it there.** The field EO *log* lives under `data/live/`; the sampled top-10k
*squads* do not — `gaffer field-scrape` writes them to
`data/raw/field/<season>/gw<N>.json`, and a past gameweek's picks cannot be
fetched again from anywhere. With `data/raw/tier_eo/`, they are the only bytes
in this tree no command can rebuild.

Deliberately out, and what rebuilds each: `data/history/` (`gaffer
build-history`), `data/raw/understat/` (`gaffer understat`, slowly),
`data/raw/vaastav/` (a download), `data/raw/news/` (a scrape cache — 67 MB,
four times the rest of the archive combined; the *derived* corpus that matters,
`data/live/availability_log.parquet` and `live/presser_log.parquet`, is inside
the set), and the timestamped API snapshots under `data/raw/`, which are a
record of calls made rather than anything the tool reads.

`--rsync TARGET` copies the finished archive with `rsync -a`. **The remote copy
is never pruned** — a retention rule reaching across it would be this tool
deleting files on a machine it does not own, over a protocol with no undo. A
failed copy is not fatal: the local archive exists, and saying nothing was
backed up would be false. The archive is written through the tree's atomic-write
helper — a temp sibling, renamed into place — so a full disk or a Ctrl-C leaves
no truncated file for the next run's prune to count as a backup.

### `gaffer tidy`

Dry run by default; `--apply` deletes. It targets two sets: replay logs
`data/live/backtest_log_v7b_*.parquet` whose companion `reports/v7b_<tag>.json`
never appeared, and `logs/*.log` past `--older-than` (30 days).

**How little it reclaims: 54 KB on this tree today**, five orphaned replay logs
out of thirty-three. It is a correctness tool, not a disk-space one — see the
residuals below for where the megabytes actually are.

Four things it will never touch, each with a named reader: the shared
`data/live/backtest_log.parquet` that `/api/history` reads (the glob does not
match it, which is luck rather than design, so a rail asserts it);
`backtest_log_s2_*.parquet`, whose S2 arm evidence lives only in `logs/` and
which pairs with no report by design; the availability, field EO, price and
presser logs, which are the corpus rather than output; and `logs/advise.log`,
which is `/api/health`'s launchd line and which the 30-day cutoff would have
swallowed within a week. It refuses a negative `--older-than`, and refuses to
run at all when `logs/` is absent — that is the check, not a project-root
detection, and it stands in for one because the usual way to have no `logs/`
is to be in the wrong directory, where "nothing to tidy" is indistinguishable
from a clean tree.

### `gaffer mcp`

A stdio MCP server, so Claude Code can read this tree without a browser:

```
claude mcp add gaffer -- gaffer mcp
```

Six tools, all reads: `projections`, `explain`, `whatif`, `ledger`,
`freshness` and `health`. Each is the router function that already serves the
same payload to the web UI, so nothing here is a second implementation that
could drift from the page showing it. `whatif` is the exception and the reason
is worth knowing: `POST /api/whatif` returns a job id, so the tool wraps the
synchronous solve instead — it **re-solves locally and starts no job**, and a
transfer out reaches the solver as "don't own him", which also rules out buying
him back. There are no write tools.

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
price_timing = true  # charge a deferred sale its expected overnight price
                     # drop. On since the v12 W2 gate; `false` drops the term.
alt_plan_max_gap = 2.0
                     # v12: how far behind the recommended plan an alternative
                     # may sit and still be offered as Plan B or Plan C, in the
                     # solver's own objective points. 0 turns the search off;
                     # each alternative costs one more MILP solve.
# top_n = {GKP = 8, DEF = 22, MID = 26, FWD = 14}
#                    # how many players per position reach the solver at all.
#                    # Merged over these defaults, so tuning one position does
#                    # not mean restating the other three; anything
#                    # unreadable — a typo'd position, a zero, a corrupt file —
#                    # falls back to the shipped value for that position, and
#                    # Model → Health prints what is actually in force.

[model]
xg_per_shot = false  # non-penalty xG per shot, per Understat window, on the
                     # attacking model. Off: the v12 §3.5 arm said keep on the
                     # RMSE buckets, the season replay said no. `true` fits
                     # the head anyway.

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
alone.

**One process, and that is a contract (v9d).** Every job-runner invariant is
per-instance: the single lane, the run records, the log lines an SSE response
tails. A second worker gets a second runner, and a browser that started a job
on worker A then polls worker B, which has never heard of it — no crash, just
a job that never finishes on screen. `cli.ui` passes uvicorn the app
*instance* rather than an import string, which is what makes `workers=`
impossible rather than merely unset, so please do not add `--workers` to be
helpful. `tests/test_v9d_degradation.py` asserts the shape of that call. By default it
binds the loopback interface only — that is the whole security model, so do not
put it behind a public proxy.

**`--lan`, and what it does and does not protect (v12).** `gaffer ui --lan`
binds every interface so a phone on the sofa can reach it, and prints the LAN
URL with a QR code. **Reads are open; writes need a token.** Every non-GET
route — pinned p_play overrides, watchlist stars, saved drafts, queued jobs —
needs an `X-Gaffer-Token` header or answers 403 (not 401: a 401 invites the
browser's own credential prompt for a scheme this app does not implement, and
leaves the user a dialog with nowhere to type). `OPTIONS` and `HEAD` pass with
`GET`, because a preflight that failed closed would make every write look like
a network error rather than a refusal.

The token is `[web] token` from your config, or — with no key there — one
generated at startup and printed **once**, in the LAN banner. It is not written
into `config.toml`: a tool that edits the file holding your API key is a
surprise nobody asked for. The QR code carries `?token=…`, so a phone that
scans it is authorised on its first load and stores the token under
`gaffer-token`; the printed URL stays bare, for the device you type into. That
query parameter reaches uvicorn's access log once, in the terminal that just
printed the token anyway.

None of this applies on loopback: with no token, no middleware is installed at
all and the app is byte for byte the one that has always shipped.

Six hubs: **This Week** (the recommendation, with a pitch view, the captain
field-EO sentence, the chip planner's best week for each unused chip, the
digest cards and a re-run button), **Planning** (the What-If lab — lock, ban
or force in players, cap the hits, and re-solve the real MILP against the
saved pool, with the plan diff, the twenty-solve sensitivity card and your
editable pins beside it; a **Drafts** tab where you name a set of what-if
constraints, keep up to twelve and compare any six against today's board;
the plan **Timeline**; the **Chips** workbench with its season Outlook; the
v11 **Board** laying the solved horizon out week by week with the bank
trajectory; and the fixture **Ticker**), **Players** (the candidate pool,
with the "why 6.8?" breakdown behind every name, a **Pin** button on each
row for the weeks you know something the model does not, a ☆ that stars a
player onto your watchlist — a bookmark, not a pin: it widens the movers
card's price-alert watch set and adds him to the Friday digest's flagged
section, and claims nothing the model has to obey; plus **Compare** and the
Dixon-Coles fixture **Matrix**), **League** (standings, trajectory, win
probability and what λ is doing, with rival intel a click away: each rival's
squad, overlap and differentials against yours, and a league what-if),
**Live** (in-gameweek points, auto-refreshing: the auto-subs FPL would apply
if the afternoon ended now, a race chart of where your score is heading —
points banked plus the expectation still owed by every unfinished match,
against the pre-gameweek plan — and what you need to take or hold the league
places either side of you) and **Model** (quality and calibration, the
graded decision **Review**, the v11 **Season** dashboard, data freshness and
re-run buttons under **Health**, the decision **Journal**, and past runs
under **History**). A three-state theme toggle in the sidebar footer follows
your system by default, or holds dark or light if you pick one.

This Week opens on a pitch. The advised XI sits in four formation rows with
the bench drawn as a bench below it in substitution order, each player wearing
his club's shirt, and the captain and vice-captain carrying C and V armbands.
Under every name is a chip naming his next opponent, the side he plays on and
the kickoff in your own timezone, tinted by the fixture ticker's odds-implied
difficulty rather than FPL's cruder FDR — so the number on the chip and the
number in the ticker are the same number. A player whose team has no fixture
that gameweek reads **Blank**, honestly, rather than showing an empty chip.
The **Table** toggle beside the captain line returns the data-dense squad
table, unchanged.

A player's name is a card wherever the page has room for one: Live's rows, a
rival's squad list and the review's flagged-and-skipped list each draw the
shirt beside the name, and clicking it opens the same expected-points
breakdown those names always opened — now with the player's face, served from
the local asset cache rather than fetched from anyone else. Live and a rival's
squad show the plain shirt and no club: neither payload carries a team, and
nothing here guesses one.

A panel a solve is filling shows the shape of the answer while it solves,
instead of sitting blank until the job lands — the what-if diff, the chip
re-solve, the draft comparison and the sensitivity sweep. Saving a pin, an
override or a draft now says so in a line at the top of the page, as does
deleting one; a star whose write the server refused reverts instead of sitting
there filled, claiming a player is on a list he is not on. A successful star
stays silent: the filled star is the acknowledgement.

### Where your captain stands, and the season ahead (v10b)

The squad now shows what share of the **top 10k** owns each player beside what
share of your own league does — `Field%` next to `EO%`, the same two numbers
the Players explorer has carried since v8c, joined onto the rows you already
have rather than computed a second time. A player the field scrape has never
seen reads as an em dash, never as a zero: nobody owning him and nobody having
counted are different facts.

Above the pitch, a sentence says where your captain stands against that field
and whether the pick is cover or attack — heavily owned and he cannot cost you
rank, rare and every point he scores is a gain. It carries the standard error,
because it has to: the figure comes from a 300-entry sample of the top 10k, so
it is good to a couple of percentage points and the page says so rather than
implying a precision the sample does not have. Between the two thresholds the
sentence gives the number and makes no claim at all — a third of the game is
neither template nor punt, and labelling it anyway is how a classification
stops meaning anything. In the weeks the tier scrape cannot cover, the line
falls back to FPL's own most-captained player *for that gameweek*, named as
such, with no percentage attached.

The **EO lens** on the pitch tints each card by the same classification. It is
off by default and it is presentation only — nothing about it reaches the
solve.

On Planning, the Chips tab gains a **Season outlook** segment: each unused
chip's best week and the bar (θ) it is measured against, week by week, plus
the GW19 expiry for a first-half chip; and below it the doubles and blanks in
the fixture list as published. It is planning rather than advice, and says so
above the numbers — what to play *this* week is This Week's answer. On today's
list it has nothing to report: ten fixtures in every one of thirty-eight
gameweeks, no team doubled, no team blank. That is the honest empty state and
it is what you will see until the cup rounds start moving games.

Two things this cycle left open, deliberately. (A third — the Players
explorer reading the field log without filtering by season — was closed in v12
W1: the keyword is now required, so the omission is a stack trace rather than
last season's ownership for a re-issued element id.) `advise.py` still writes a
`captain_note` about the
league-tilt armband override that no page renders. And there are now two
code→element maps in the tree, one private to the league simulator and one
memoised in `web/field_frame.py`; merging them would mean opening a router this
cycle otherwise never touches.

### The board, the working, and the season so far (v11)

**Planning** gains a **Board**: the horizon the last advice run solved, laid
out week by week — the buys and sells with their prices, the hits and what they
cost, the chip if the solver placed one inside the horizon, and what is left in
the bank after each week. A shorter horizon is a shorter board; nothing is
padded to six columns. Names whose price is moving carry a warning read off the
price log — the direction and how far through the threshold they are, never a
predicted price, because the log does not hold one — and a log still calibrating
draws no warning at all rather than an untrustworthy one. **The board never
re-solves.** It draws the plan the advice run wrote.

"Try these changes" hands the week to the What-If lab prefilled, and stops
there: you press Re-solve yourself. Two limits are printed under the button
rather than hidden in a tooltip, because a limit you discover by hovering is a
limit you discover after the solve. A planned sell reaches the lab as *don't
own him*, which also rules out buying him back — the constraint vocabulary has
no "sell exactly this". And the bank is not a constraint the lab accepts at
all.

The bank itself goes blank from the first move the pool cannot price, and stays
blank for every week after it. Skipping such a move would report a number wrong
by exactly that player's price, confidently, with nothing on the page to say
so, and there is no later week at which the running total comes right again. A
blank is not a zero: zero is *fully invested*, which is a real thing to be.

**Players → Compare** now shows the model's own working. Where each player's
expected points come from, term by term and signed, with the rows adding up to
the number printed above them so the claim is checkable rather than asserted;
his chance of playing, his chance of sixty minutes and his expected minutes for
the gameweek, both fixtures on a double because an average of two probabilities
is a probability of nothing; his set-piece order, said loudly at one and barely
at three, and not said at all where the bootstrap does not say — which is not
the same as "not a taker". The next six carry the same difficulty tint the rest
of the app uses, still read off the clean-sheet axis for a goalkeeper or
defender and the attacking axis for everyone else.

All three ownership figures sit together, and the top-10k one now carries its
error bar. It has to: the figure is measured from a sample of a few hundred
entries, so it is good to a couple of percentage points, and a page that
printed it bare would imply a precision the sample does not have. An older
scrape that recorded no error shows the figure and an em dash — never a zero,
which would be a claim of perfect precision.

**Model** gains a **Season** tab beside Review: the decision record per lane —
what each cost or gained and how often it went your way — cumulative points
left on the bench, the accuracy and overall-rank trajectories, and the
calibration trend. A lane's record is counted over the weeks it was *graded*,
and a week where your decision made no difference is neither a win nor a loss:
counting agreement as judgment is how a lane that never disagreed comes to look
like a lane that was never wrong. A lane nothing has measured says **never
graded**, not 0%. The rank axis runs downward, because a line that rises when
the season goes badly is a chart lying with its shape, and a missing rank is a
gap in the line rather than a point at zero — zero is the best rank in the
game.

It is built empty on purpose and it is empty today. The first grades land when
FPL marks GW2 `data_checked`; the Tuesday review job banks them by itself.

Two things this cycle left open, deliberately, on top of the three v10b left.
The bank trajectory is arithmetic the solver already did internally, re-done at
`web/routers/plan.py`, because the alternative is widening the advice
artifact's `plan_by_gw` — which means editing `advise.py`, and this cycle did
not. And `overall_rank` populates only for gameweeks graded *after* v11: grades
are banked and never re-derived, so every row already in the ledger has no rank
and will never acquire one. The trajectory starts where this cycle did.

**Freeing a wedged job (v9c).** The server runs one background job at a time,
so a job that hangs used to hold the lane and answer every later job with a
409 until you restarted the process — and the 409 named a run you had no way
to clear. Two things changed. `JobRunner.start` now reaps a holder older than
`ADVISE_TIMEOUT_S` (30 minutes) before it refuses, and `DELETE
/api/jobs/current` frees the lane on demand, returning the abandoned run, or
404 when nothing is running.

**Per-kind deadlines, and a cancel that says cancelled (v9d).** One number for
all twelve kinds was chosen for the most expensive of them, so a wedged
four-second snapshot blocked every later job for half an hour. The fast four —
`advise-fast`, `snapshot`, `track-pens`, `sensitivity` — are reaped after 120
seconds instead (`ABANDON_TIMEOUT_S` in `web/job_kinds.py`); everything else
keeps the 30 minutes, which is also the default for a kind nobody listed. And
the cancel path no longer reports "timed out after 0s" about a button you just
pressed: it says `cancelled`. Both wordings keep the half that is true either
way — *abandoned as a daemon, its thread still running*.

What neither of them does is **stop the work**. The worker is a daemon thread
and Python has no safe way to kill one, so abandonment releases the lane and
discards the result while the thread runs on to completion. That is only safe
because every job kind writes its artifacts idempotently or writes nothing —
a constraint from v8f that a future job kind must keep. The abandoned run is
marked `failed` with the reason in `error`, and it cannot take the lane back
from the job that replaced it.

Two things the Live page will not pretend to know. The race trajectory lives
in the server process and nowhere else — restart `gaffer ui` mid-afternoon and
it starts again from that moment, which is the price of a page that writes
nothing. And the safety numbers are league places only: an overall-rank
cushion would need every one of ten million entries' live scores, and no
public endpoint gives them.

### Hygiene: freshness, refusals and a backup (v12 W1)

Every hub draws an **"as of" strip** at the top: how old the refresh, the odds,
the field EO log, the last advice run and the last backup are. Green under a
day, amber under three, red beyond, grey for never — and "never" is spelled
out, never rendered as `0h`, because a zero age means "just now", which is the
exact opposite. It is mounted once, in the app shell, so it survives every
navigation and covers the rival-detail route that has no hub of its own; a
failed fetch renders five grey rows rather than disappearing, because a strip
that vanishes teaches you its absence means nothing is stale.

Model → **Health** gains three lines: the season check described under
Retraining, the solver's per-position pool sizes (`[optimizer] top_n`, and it
re-reads the file so an edit shows on the next reload), and the last backup with
its size, or `never — run gaffer backup`.

Two more refusals besides `refresh`'s. `gaffer track-pens` will not overwrite a
good `reports/pen_tracker.json` with a degraded run — neither one where every
gameweek block failed to read, nor an empty one caused by a missing
`data/live/player_gw.parquet` — and says which case it is. It writes freely when
there is nothing banked to protect, or the file would never come into existence
on a cold clone. The web job lane obeys the same guard, because it lives in the
writer rather than in the CLI. And the LAN write token above is the third.

Underneath, the temp-then-rename idiom that twenty modules had each written for
themselves is one helper, `gaffer/io.py`. Two latent bugs went with it:
`presser_log.py` shared a single `.tmp` between the nightly snapshot job and a
hand `gaffer snapshot` — two writers, each unlinking the other's file — and
`understat.py` and `chip_scenarios.py` had no `finally`, so a write that raised
left the temp behind for ever in a cache directory that is permanent by design.

**Five things this cycle left open, deliberately.**

1. `journal.py` keeps its own copy of the atomic-write idiom: it is import-only
   for this cycle. A census rail names the surviving copies — `io.py` and
   `journal.py` — as an equality rather than a `<=`, so a twenty-first copy
   cannot appear quietly.
2. The spec asked for a `[solver]` section; there is none. `top_n` lives in the
   existing `[optimizer]` beside every other solver knob, by ruling — which
   means the price-timing and settings-whitelist work in later workstreams
   reads `[optimizer]` too, and the spec's `[solver]` wording is stale wherever
   it appears.
3. `gaffer tidy` reclaims 54 KB. The real accumulation is **~34 MB of
   timestamped API snapshots** under `data/raw/` (`bootstrap-*.json` at 1.7 MB
   apiece, plus `fixtures-*`, `odds-*`, `ags-*`, `entry-*`) that nothing prunes,
   and 67 MB of `data/raw/news/`. Both are outside the spec's scope and stayed
   there: silently widening a delete command past what was asked for is the
   most expensive kind of helpfulness available.
4. The rollover guard's served half reads the **banked** events snapshot rather
   than the API, because `/api/health` is disk-only by contract. So it answers
   "is the data on disk the data the config describes", which is the state that
   matters, and says nothing about a season FPL has published and this machine
   has not yet fetched.
5. The MCP server exposes no write tools and no resources or prompts. `whatif`
   is the one tool that computes, and it computes locally and banks nothing.

### Mining the logs we already had (v12 W2)

`gaffer evaluate --flag-latency` and `--presser-grades` both write into
`reports/evaluation.json` and appear on Model → Quality, in one
**Availability signal** card that renders even when it is empty — an empty
state that says what it is waiting for is the whole point of the instrument
this early. The captain frame and the Players explorer both gained a projected
deadline EO beside the sampled one.

The two are keyed differently on purpose, and it shows. The Players explorer
asks the trend for **the newest gameweek the log actually holds**, while the
captain card asks it for **the gameweek being served** — so on the upcoming
gameweek, whose picks are not public yet and therefore not in the log, the
captain card falls back to its most-captained note while the explorer's rows
still carry their arrows. Keying the explorer to the served gameweek instead
would blank a whole column on precisely the days the page is read most.

**`[model] xg_per_shot` ships off.** The column exists — non-penalty xG per
shot at each Understat window, shot quality beside the shot volume the
attacking model already had — but the head is not told about it. The
2026-09-02 §3.5 arm returned `keep` on its pre-registered bar (no bucket
regressed beyond its own seed spread; haulers 5.207 → 5.203, inside the 0.019
spread), and then the season replay with the head on scored [1874, 1834, 1799]
against main's [1854, 1875, 1862] — 28 points off the mean, past the control
spread, with the seed spread tripled to 75 from 21. **The RMSE-bucket rule
lacked a replay half**: it could say the fit did not get worse and could not
say the season got better, and a fit measure that never meets an outcome
measure cannot be the last word on what ships. The outcome measure wins, so
the §3.5 keep is withdrawn. It takes effect on the next `gaffer train`; a
model fitted while the flag was on keeps predicting exactly as it did, because
its own `cols_` name the columns it was given. Set `xg_per_shot = true` to fit
the head anyway.

A flag's **lead time is whole days between the snapshot date and the deadline
date**, and a snapshot dated the deadline day is not counted at all. The
snapshot log stamps a date with no clock on it, so a row dated deadline day
could have been taken in the morning or in the evening; dropping it can only
throw away real warning, while keeping it would credit every deadline-day flag
with up to a day of warning it may never have given.

**Four places this cycle does not match its own spec, recorded rather than
quietly fixed.**

1. v12 §3.1 names `reports/evaluate/flag_latency.json`; both reports go into
   `reports/evaluation.json` instead, because that is the artifact
   `/api/quality` reads and `save_evaluation` is where the atomic-write and
   `allow_nan=False` discipline already lives.
2. The EO trend is measured **gameweek to gameweek**, not day to day: the
   field scrape's already-banked exit means one sample per gameweek, and picks
   are frozen after the deadline anyway, so a same-gameweek delta would be
   sampling noise. Field EO is in **percent** and captaincy doubles it, so the
   ceiling is 200 rather than the spec's 1.0.
3. The price-timing term is worth 0.008 points at the shipped `itb_value` and
   the solver's default relative gap on a real horizon is larger, so it breaks
   exactly-equal sell timings and was not expected to move a replay. It did
   not: over three seed bases the 40-scenario replay with the term live scored
   [1854, 1875, 1862] against main's identical [1854, 1875, 1862], hits
   unchanged at [18, 12, 18], with 34 of the transferred players carrying a
   non-zero `p_fall` — which is the pre-registered §3.4 flip rule met, so
   `[optimizer] price_timing` ships **true** rather than the `false` W2 first
   shipped it behind. It has a **live window**, found at that gate: a
   reading banked on UTC day D predicts the night D→D+1 and is stale from the
   next UTC midnight, so a solve only sees the term if the day's prices have
   already been banked. The Thursday `advise` job therefore now runs `gaffer
   prices` before it trains — with `;`, not `&&`, so a failed price fetch
   never costs the week its advice — because at 18:00 local it had been
   reading the previous day's log every week and solving with the term at
   zero. The web UI's **advise** button still does not bank first, so a solve
   started from the browser during the day gets an untimed sale: the pre-v12
   behaviour, recorded rather than fixed, because fetching prices as a side
   effect of asking for advice is a new job kind and W2 adds none.
4. There is no `[solver]` section: solver knobs live in `[optimizer]`, which
   `load_config` splats into `Config`. A knob there is therefore either a real
   `Config` field (`top_n`) or listed in `config.NON_FIELD_OPTIMIZER_KEYS` and
   popped before the splat (`price_timing`) — never both, and never neither. A
   typo under `[optimizer]` still raises, which is why that tuple is named
   rather than derived from the field list.

### What the solver is allowed to say (v12 W3)

**Must sell.** The What-If lab has a fourth constraint beside lock, ban and
force in: *sell this player*, honoured in the first week of the horizon, with
the sale credited to the bank. That is the whole difference from `ban`, which
takes a player out of every week and never pays you for him — and until this
cycle `ban` was what the Board's "Try these changes" button handed over for a
planned sale, so a sell also forbade buying him back three weeks later and
priced the replacement out of money you did not have. The board now hands over
a **Must sell**. It is a picker rather than a free-text field, and the names in
it are validated as *owned* at solve time (`force_out_not_owned`), so an
unowned name is refused at the input instead of quietly doing nothing. Four
more combinations are refused the same way: locking and selling the same
player, banning and selling him, buying and selling him, and a must-sell on a
free hit — which conjures a squad from nothing and so has nobody to sell.

**Plan A / B / C.** The Board's strip carries the two next-best *distinct*
plans, found by re-solving with a no-good cut over the recommended plan's move
set. Each one's card names its gap from Plan A **in the solver's own objective
points** — decayed by week, carrying the bench curve and the vice hedge,
pricing banked transfers and the bank itself — and not in raw expected points,
because re-scoring in xPts would compare two plans on a quantity neither of
them was chosen by. **The gap is signed and a negative one means the
alternative is ahead**: the recommended plan carries the scenario sweep's
moves as a constraint and an alternative does not, so the coherence constraint
has a price and this is the first surface that shows it. Each alternative
costs one more MILP solve on the weekly advise run; `[optimizer]
alt_plan_max_gap = 0` turns the search off entirely, and the shipped 2.0 also
stops it early when nothing else is close.

**The availability draw.** The scenario sweep can now draw *whether each
player turned out at all* — a Bernoulli on the minutes model's `p_play`, per
scenario, from its own generator — before the EP noise is applied to whoever
survived. "Did he play" is the largest single source of forecast error, and a
sweep that only widened the EP band was asking a softer question than the one
the week actually asks. It ships **on**, behind `[scenarios]
draw_availability`; set that key to `false` and you sweep on expected minutes
alone, which is the pre-v12 sweep to the byte, because the normal is drawn for
every cell either way and the two arms differ in the zeroing alone.

It merged off, and the gate turned it on. The pre-registered rule (CONVENTIONS
§6) was that the draw could not cost more than 10 points of *captain support*
— the sweep's agreement on who to captain, which is what a hedging draw would
be likeliest to shred. On the GW3 board (2026-09-02, seed 20260828, n = 40,
219 of 219 players priced and covered) support fell from **60.0 off to 52.5
on: a drop of 7.5**, with all 40 scenarios completing in both arms. Two
honesties about that number. It is **one board, one gameweek, one seed**, not
a season. And the **season replay cannot see this lever at all** — the replay
harness never passes `p_play`, so the draw is inert there and the live weekly
board is the only place its effect shows. What the gate establishes is that
the draw does not shred the captain call, not that it scores more points.

**Residual — `raw_optimum_agrees` will read `False` more often** now that the
draw is on. The line on the report compares the raw optimum against the
sweep's plurality, and with the draw on the sweep models a risk the raw solve
does not, so the two will part company more often than they used to. That
disagreement is *information* rather than instability: it is the sweep doing
the job the flag was added for. Read a `False` there as "the raw optimum
ignores availability and the sweep does not", not as "the plan is fragile".

**Residual — the chip pair is data-gated.** `wildcard+bboost` is priced as one
decision, a wildcard in one week and a bench boost in a double gameweek later
in the horizon, and **no machine can show it today**: the row needs a `[dgw]`
entry in `data/chip_scenarios.toml`, the writer refuses to create that file
while every gameweek of the published fixture list has ten fixtures, and every
one of the 2026-27 gameweeks does. An empty chip table with five columns and no
pair row is the correct state, not a bug. It unblocks at the first real
rearrangement. Two consequences of the pair being a decision about two named
weeks, so neither reads as an omission: the Outlook's season fold
(`web/routers/meta.py::chips_plan`) deliberately does **not** pass `dgw_gws`,
because it emits one row per chip across the whole season and there is no pair
arm in that shape; and the pair's row has **no "Try it" arm** in the What-If
lab, because a What-If job solves one chip and a pair is two — pick the single
wildcard or the single bench boost above it to re-solve either half.

Two smaller things worth knowing before you go looking for them. Every chip row
and the wildcard verdict now carry a `threshold_source` saying *why* the bar is
what it is — `theta`, or one of three different flat fallbacks — but no surface
prints the sentence in full: it is rendered as a one-character `θ`/`flat`
marker with the sentence as its title text. The source is evaluated at the
**first gameweek of the horizon**, so a row for a later week reports the source
of the bar that week's lookup gave, not of a bar computed for the week you are
reading about. And of those fallbacks, `flat: gameweek outside the calibrated
window` is effectively unreachable: `stopping_thresholds` fills every week of
both halves of the season, so a gap in the calibration is missing information
rather than a missing key, and the window fallback fires only on a gameweek the
season does not have — GW39 — which is what an off-by-one in a caller's horizon
looks like. It is not dead code; it is a rail on somebody else's arithmetic.

### The field, and who really takes them (v12 W4)

**A second archive.** `gaffer core-insights` collects
`github.com/olbauday/FPL-Core-Insights` into `data/core_insights/`: per-player
per-match detail (crosses, box touches, tackles, the minute a man came on and
the minute he went off), the whole **published** fixture list including cup and
European ties nobody has played yet, and the club Elo the archive carries. It
is not built from a path template. The archive publishes **two layouts** —
2025-2026 and 2026-2027 under `By Gameweek/GW<n>/`, 2024-2025 under
`<table>/GW<n>/` with its `teams.csv` a folder deeper — so every path is
enumerated from the one recursive git-tree call `data/cups.py` already makes,
keyed on basename and season folder, which survives the next reorganisation
without an edit. `By Gameweek` already carries every tournament in one file per
week, so `By Tournament` is never walked and no cup tie is counted twice.

Two honesties about it. There is **no ClubElo file**: Elo is a column on
`teams.csv` and a pair of columns on each fixture row, `elo.parquet` is derived
from both, and for 2026-27 the publisher has not filled it in — so that table
is legitimately empty today. Model → Health carries a **Core insights** card
naming the season and each table's rows and latest date, where a zero reads
"the archive publishes none yet" and a clone that has never collected says
what it is waiting for, because three zeros would look like a measurement of
an archive that had nothing in it. And the cache under
`data/raw/core_insights/` is not "cached forever": a gameweek whose every
fixture is finished is fetched once, while a gameweek with an unfinished
fixture — or with no cached fixture list to judge by — is **re-fetched on every
run**, which is what makes the 06:30/18:30 pair worth having against an archive
that pushes at 07:30 and 17:30 UTC. `gaffer core-insights --refresh N` forces
the last N gameweeks of each season whatever the cache says; that is for the
file the publisher corrects *after* it went final, not for the week being
played, which refreshes itself. A failed re-fetch leaves the previous copy in
place, because freshness is worth a request and never a deletion.

**Two minutes arms, built on both seams; one of them now ships.**
`role_wb_share` reads the share of a defender's last five starts whose
per-match profile is a wing-back's rather than a centre-back's — a stated
convention (a start with at least one accurate cross or three touches in the
opposition box), not a fitted classifier, and built from the two positional
columns that exist in **every** season the archive covers, because a rule using
`defensive_contributions` would be a season indicator wearing a role's name.
`density_pub_7d` counts the club's published fixtures on the seven calendar
days (UTC) before this fixture's own kickoff date. Both are appended to the
training frame *and* to the serving frame by the same functions, so the two
seams cannot disagree; both degrade to all-missing with their own `_missing`
indicator on a machine that has never collected, and a season the archive does
not cover is **missing rather than zero** — a zero there is a claim the club
played nothing, and it read as 100% coverage to the arm driver until a review
caught it.

The arm rule was pre-registered before either driver ran: an arm is kept only
if `scripts/v12_w4_arms.py` shows the starters-slice `p_start` log-loss improve
by at least 1% relative against *that run's own control* with zeros RMSE no
worse by more than 0.005, **and** `scripts/v12_w4_autosub_cf.py` shows the mean
points delta over the weeks an autosub actually fired not regress. Either half
failing is a withdrawal — W2's lesson, where a bucket rule with no outcome half
kept a head that a replay overturned the same day. Both run on a **shifted
window** (train 2022-23…2024-25, test 2025-26) because the archive's earliest
season is the shipped benchmark's *test* season, so on the shipped window both
columns are null through the whole of training and the only thing a fit could
learn is "populated implies test season" — the exact confound that withdrew
v5's congestion features. If training coverage comes back zero the drivers
**exit**: "not measurable on any window the archive covers" and "no effect" are
different findings, and only one of them would be true.

**Both drivers ran on 2026-09-03** and the rule decided them opposite ways.
Half (a): baseline starters-slice log-loss 0.43723 with zeros RMSE 0.917;
`role_wb_share` 0.42889 — a **1.907%** relative gain — for **+0.002** of zeros
RMSE, clearing both guards; `density_pub_7d` 0.43584, a **0.318%** gain for
**+0.006** of zeros, failing both. Half (b), over the 15 weeks of 38 in which
an autosub actually fired: role **+0.133** mean points, density **+0.333** —
both pass. So **`role_wb_share` and `role_wb_missing` are now in
`MINUTES_FEATURES`** and take effect on the next `gaffer train`; a minutes
model pickled before the flip pins its own column list at fit time and keeps
predicting untouched. **`density_pub_7d` is withdrawn** — half (b) passing
does not rescue an arm that failed half (a) — and stays built on both seams
and fed to no head, so a later cycle re-measures it rather than rebuilding it.

One number stated because burying it would be the dishonest thing: over **all
38 weeks**, not only the autosub ones, the mean points delta is **−0.211** for
role and **−0.895** for density. That is outside the pre-registered rule,
which asked about the weeks the intervention is *about*, and the rule is read
as written rather than rewritten after the fact. It is recorded here anyway,
and the next cycle to touch these arms should read it first. The W4
no-regression replay was run with **both arms off**, exactly as pre-registered
— the arm's evidence is the counterfactual, not the replay.

One qualification stated rather than glossed: the fixture table is *today's*
published schedule, not a snapshot of what was published at the time — the
archive keeps no vintages. A tie rearranged in November sits on a historical
row at its February date. That hindsight is real, one-directional
(rearrangement moves a fixture later, so a training row's count is if anything
understated) and **identical on both seams**, so it cannot produce a train/serve
skew; it would matter for a claim about what a manager knew in November, and
does not for a feature both sides compute the same way.

**The Field panel** on the League hub answers one question with a number and
two with their reasons. `P(green arrow)` is your week against a synthetic
field: 300 managers drawn from the banked EO table, everybody scored off the
**same** matrix of drawn player weeks — so the correlation between you and the
field is the shared-ownership correlation and is not a parameter — and a green
arrow defined as beating the population's own median week, which is what makes
"a squad exchangeable with the field is a coin flip" exactly true rather than
approximately. The field is an **ownership portfolio, not a legal squad**: no
budget, no position limits, no three-per-club, which is what the EO table
actually describes, and the panel's caption says so rather than letting a
reader over-read it.

Four things about that number worth knowing before you go looking for them.
The EO comes from **the previous gameweek's sample** (`eo_gw = plan gw − 1`,
and the panel names it), because entry picks 404 before a deadline so the
scrape can only ever have banked the last scored week — reading the plan
gameweek's own sample would be reading the field's frozen picks and would make
the answer depend on what time of week you opened the page. An **EO above 100%
is an armband, not a clamp**: the draw is two Bernoullis, `min(eo, 1)` and
`eo − 1`, so a manager holds the crowd's captain twice, once, or not at all, and
clamping (which this did) threw away 1.15 of the live GW2 log's 13.48 ownership
units and handed every one of them to you for free. The element axis is the
**union of the EO table and your own squad**, because field EO only counts
players a sampled entry started and a genuine differential is routinely absent
from it — filtering deleted him from your week while the field kept its whole
one, which pointed against exactly the squad the panel exists to reward. An
unsampled pick enters owned by nobody, which is what his absence means, and the
panel says how many of your players the sample cannot speak to. And the
population is drawn **eight times and averaged**, because *which* three hundred
managers were drawn was the larger noise term: one population put the
exchangeability check at 0.427–0.585 over sixty seeds, eight put it at
0.471–0.538.

The other two rows are empty states with their conditions named. `P(top-10k)`
needs a top-10k weekly score threshold and **no such series exists** anywhere
this project reads — `build-history` writes player and fixture tables,
`data/live/events.parquet` carries no score at all, and the archive's
`gameweek_summaries.csv` has an average and a highest and no tier threshold —
so it is not computed rather than guessed. The overall-rank response is an
ordinary least-squares slope through the ledger's `(my_points, overall_rank)`
pairs and needs five graded gameweeks. Two are graded today, and one of them
carries both today — GW1 banked a score with no overall rank — so the panel
reads `1 of 5 graded gameweeks`, not 2. When it does fill,
read it as an association: `my_points` is one week and `overall_rank` is a
**cumulative** standing that drifts with the season on its own, so the slope
charges some of the season's passage to the points. Differencing rank week to
week is the obvious next version and needs consecutive graded weeks this
project does not yet have. The sign carries the meaning — rank counts down, so
a negative slope is points buying places — and the panel renders it that way
rather than as a bare magnitude.

**Set-piece overrides.** `data/set_pieces.toml` is the one place you can tell
the tool that the manager said something FPL's feed has not caught up with.
Copy the template out of `src/gaffer/assets/set_pieces.example.toml` (a package
asset, because `data/` is never staged), one table per club, takers listed in
order by **code**:

```toml
["Arsenal"]
penalties = [232413]        # Eze takes them now; Saka does not
```

Codes, not element ids, because element ids are remapped every summer and codes
are not — and a player's code is printed in the header of his explain panel
(`code 223340`, beside his club and xPts), which is the only place in the app
it is shown and the reason that line exists. **Quote any club header with a
space or an apostrophe** (`["Man City"]`, `["Nott'm Forest"]`): bare TOML keys
allow neither and one bad header discards the *whole* file, every club in it,
so the loader prints the line and column when that happens. The header itself
is decorative — nothing matches it against a club name, each man's club is read
off the frame being priced, so a code filed under the club he left last summer
still applies and two clubs' codes under one header are two queues.

**Listing a club's queue demotes the teammates it leaves out.** For the club a
listed code plays for, the file's list *is* the queue: a man it does not name
is not a taker, whatever FPL published. Without that rule the one line a user
actually types — the new man takes them now — would leave the incumbent at
FPL's order 1 and price both of them for every penalty the club wins. **An
empty list demotes nobody**: it names no code, so it identifies no club, so
there is nothing for it to be the queue of — it records that you checked and
found nobody.

The file reaches exactly two read paths and **only penalties reach expected
points**. `set_pieces.pen_table` applies the penalty queue to the EP term (the
one protected edit this workstream took, with the module's "nothing here does
I/O" docstring amended in the same edit rather than left saying something the
code had stopped obeying); `web/routers/players.py` serves the corrected
`penalties_order` / `free_kicks_order` / `corners_order` on `/api/players` and
on the explain panel, with a **manual** badge beside them — including on the
demoted, because a blank with no badge reads as "FPL has nothing to say", which
is the opposite of what happened. Corners and free kicks move the served order
and nothing else: there is no free-kick or corner term in the model to move.
Two things the file deliberately does **not** override: `gaffer track-pens`
(`pen_tracker.save_tracker_guarded`), which records what FPL published and must
keep doing so, and the `pen_taker` training column in `features/engineer.py`,
which is built from history and not from your opinion of it. A missing file, a
malformed file, a half-edited one at 11pm on a Friday are all "no override",
byte-identical to pre-v12.

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

The Planning hub's **Timeline** tags each week card with the opponents its
named players face that week — the captain, the vice and any buys and sells,
one chip per club — shaded by the same odds-implied difficulty and the same
colour ramp the fixture ticker uses, so a chip and the ticker's square for the
same fixture are the same colour by construction. The player-to-club half of
the join is free — it rides on the advice payload the hub already fetches —
and the fixtures themselves are one request to the same ticker endpoint the
Ticker tab reads. Any link it cannot make is left out rather than guessed: a
player the last advice run never named, or a gameweek past the ticker's
window, simply has no chip.

### Two sources for the predicted XI, and the minutes model in the weights (v10)

Predicted line-ups now come from **two** sources — Fantasy Football Scout and
RotoWire — and they are merged by pessimism: where they disagree, the more
conservative hint wins, and a player some source names a starter carries no
absence damp from the other. A source that goes silent, parses into nonsense
or falls below the name-matching coverage floor leaves the other exactly where
it was, which is the single-source behaviour by construction.

`[news] lineup_providers = ["ffs"]` in `config.toml` switches one off. That is
a different switch from `[news] lineups = false`, which turns the whole layer
off: the coarse one covers a source going *silent*, and a silent source needs
no switch. The fine one covers a source going *wrong* — parsing cleanly,
resolving above the floor, and being false — which the pessimistic merge turns
into benched starters. An empty list behaves exactly like `lineups = false`.
RotoWire supplies hints only and is deliberately not allowed to drive the
notable-absence rule: it carries no FPL codes, so its XI resolves by name, and
one wrong match would both fabricate a starter and dock the one he displaced.

The presser classifier's would-be effect is now **banked** every week beside
what the news layer actually did, and scored as a third side by
`gaffer evaluate --news-shadow` once verdicts accrue. The classifier itself
stays off; this is the evidence that would let it be turned on.

And the bench, the bench *order* and the vice hedge are now weighted by each
player's chance of appearing rather than by three population averages. The
bench curve is modulated by how fragile this week's XI actually is — an XI as
fragile as the league's average reproduces the calibrated curve exactly — the
first substitute is the one most likely to come on *and* score rather than
simply the highest-EP body, and the vice is priced by how likely the captain
is to leave the armband unused. When minutes probabilities are unavailable, or
are the same number for everybody in a week, all three degrade to exactly the
previous behaviour: the solve that runs is the pre-v10 solve, constraint for
constraint, and it says on the console which of the two reasons it was.

The weighting prices the plan you are actually shown, and not the scenario
sweep that gates it — the sweep's job is to measure how stable a *move* is
under noise, and it is priced exactly as it was before v10 so that the raw
optimum it is compared against stays the same problem. So in a normal week
the transfers themselves are still chosen without this, and only the squad
built around them is weighted by it. In the weeks with no sweep to keep
honest — `[scenarios] n = 0`, and the opening-squad week, where there is no
incumbent to gate against — the one solve that runs is the plan you are
shown, and it carries the weights outright.

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

**Two things called a "haul", and which is which (v9c).** `P(points >= 10)`
in the tail of a player's whole forecast is the *band* quantity, and it keeps
the name `p_haul` on `/api/players` and `/api/components`; This Week's chip
labels it `10+ pts`. `P(2 or more attacking returns)` under a Poisson on
expected goals plus assists is a different number on a different scale, and it
is what the advice payload's `alternatives` and `captain_options` carry — it
is served as `p_attacking_haul`, and the HTML report's columns say
`P(2+ returns)`. The artifact on disk keeps the internal name, so every advice
file already banked stays readable.

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

**Calibration by gameweek (v9d).** `gaffer evaluate --calibration` grades the
probabilities the weekly run *actually served*, week by week, and writes them
to `reports/evaluation.json` under `calibration`; `GET /api/model/calibration`
serves them and the Model hub's Quality tab draws them in a card titled
**Calibration by gameweek** (the card titled **Calibration** beside it is the
holdout, which is a different protocol on different rows).

The predictions come off `reports/components_gw{N}.parquet`, written before
the gameweek was played, so this is the model that served rather than a model
refitted afterwards — nothing is retrained and the whole report takes seconds.
Four heads are graded: `p_play`, `p60`, `p_cs` and the attacking `p_haul`,
recomputed through the same function the solver called. Both sides are read at
player-fixture grain — a double gameweek is two forecasts, and grading either
against the pair's totals invents outcomes that happened in no fixture.

`p_cs` is graded per club-fixture (a clean sheet is one event, not eleven) and
therefore only in the cumulative row: about twenty club-fixtures a gameweek is
under the 30-row floor, so a per-gameweek column of it could never read
anything but "not enough data". The club's result is goals conceded among its
60-minute rows, not FPL's per-player `clean_sheets`, which is an award — 0 for
anyone under 60 minutes however the club played.

Its refusals matter as much as its numbers, and the card prints all of them:

- **`p_start` is omitted**, and the payload says why — the minutes trichotomy
  is never banked, so there is nothing to grade. An omission without its
  reason would read as a head that is fine.
- **A gameweek whose components file post-dates its own first kickoff is not
  graded**, and appears in `excluded` with the reason. Re-running `gaffer
  advise` on a finished gameweek silently overwrites an as-of prediction with
  a hindsight one, and mtime against kickoff is the only signal there is. The
  boundary is the *first* kickoff because the file is written whole: a Sunday
  morning re-run banks Saturday's played fixtures beside Sunday's unplayed
  ones. The guard fails closed: no kickoff information is also an exclusion.
- **A banked file that joins no graded rows is excluded too**, with its own
  reason. `missing` means one thing only: nobody banked a file for that week.
- **A head under 30 rows says "not enough data"** rather than drawing a curve
  through sampling noise.

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

Since v12, `gaffer refresh` **refuses** rather than ingesting a season the
config does not name: it compares the API bootstrap's own deadlines with
`current_season` and stops, naming both values and both keys. The remedy is the
config edit above — there is no `--force`, deliberately. The failure this
prevents is silent (August data written under last season's index, and a model
trained on it), and a flag to skip the check would be reached for on exactly
the morning it matters. Model → Health says the same thing from disk: "the last
refresh ingested X, your config says Y". It reads the banked events snapshot
rather than the API, because that page is disk-only by contract, so it can say
nothing about a season FPL has published and this machine has not yet fetched.

**`club_code`, the club a row's player actually played for (v9c).** The store
rebuilds player history from scratch every run and stamps each player's
*current* `team_code` onto every row of it, so a January transfer silently
rewrote his August training rows under his new club — and three features key
on club: the position-by-club prior, manager-spell scoping, and the own side
of the team-Elo merge. `club_code` is derived at training time, in
`load_training_frame`, by joining the archived fixture list on `(season_idx,
gw, kickoff_time)`: `opp_code` is written per row from the fixture and
survives a transfer, so the player's club is the *other* side of the match he
played in, cross-checked against `was_home`. Rows that match no fixture — and
whole seasons with no archived fixture list — fall back to the stamped
`team_code`, never to a null. Measured on the current store, 0.94% of history
rows were keyed on the wrong club before this.

`team_code` is unchanged and is still the serve-time identity: the pitch, the
shirt images and the bootstrap joins all read it, and for a fixture that has
not been played the current club *is* the as-of club.

## Where things live

- `data/raw/`, `data/history/`, `data/live/` — downloaded and derived datasets (gitignored)
- `data/manager_tenures.toml` — EPL head-coach spells; the one file under
  `data/` that is committed, because it is curated knowledge rather than
  fetched data (absent, the rotation features fall back to club-season windows)
- `data/raw/field/{season}/gw{N}.json` — the top-10k squads sampled for that
  gameweek. Permanent, and anonymous: entries are keyed by their index in the
  sample, never by entry id.
- `data/live/assets/` — cached shirt and player images, fetched once from the
  official Premier League CDN by `/api/assets/` and served from disk
  afterwards. Untracked like the rest of `data/`, never redistributed, and
  entirely disposable: delete the directory and the next page load refills
  it. With no network the endpoint serves a bundled plain shirt and
  silhouette instead, so the pitch renders identically offline. Player and kit
  imagery is Premier League property; this is a single-user local copy for
  personal display, it is never staged, and nothing here redistributes it.
- `data/live/price_log.parquet` — one row per player per UTC day: FPL's own
  price predictor reading, banked by the nightly `prices` job. Every player,
  not only the ones near a threshold — the row worth having in February is
  the one that was not an alert in August. Read by nobody yet; a season of it
  is what a price-timing term would need.
- `data/chip_scenarios.toml` — one entry per **scheduled** double gameweek, at
  probability 1.0, derived from the published fixture list by the
  `refresh-data` job. Absent until there is one, which on today's list means
  absent everywhere; never committed, and safe to delete — the next refresh
  rewrites it, and the chip layer reads an absent file and an empty one
  identically. It does not project unannounced rearrangements and never has.
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

Substitutes the project path into the nine plists in `scripts/`, copies them to
`~/Library/LaunchAgents/`, and loads them: `com.gaffer.advise` (Thursday 18:00,
which banks a price reading of its own first so the optimizer's timing term
has a same-day log to read), `com.gaffer.prices` (nightly 23:15 — the reading
the price predictor is really about, and the one that replaces the Thursday
afternoon one), `com.gaffer.snapshot` (daily 17:00, banks
the availability log the news corrector will train on), `com.gaffer.field`,
`com.gaffer.review`, `com.gaffer.digest-friday` (Friday 17:00),
`com.gaffer.digest-tuesday` (Tuesday 09:30), `com.gaffer.backup`
(nightly 23:45) and `com.gaffer.core-insights` (06:30 and 18:30 daily).
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
- **Nightly 23:45** — `gaffer backup`, half an hour after the price check, so
  the archive contains the night's reading rather than racing it. Tars
  `data/live/`, `data/raw/field/`, `data/raw/tier_eo/`, `reports/` and
  `models/` — about 16 MB — into `~/gaffer-backups` and keeps the last
  fourteen. `data/history/`, `data/raw/understat/`, `data/raw/vaastav/` and
  `data/raw/news/` are left out because a command rebuilds each of them; the
  sampled top-10k squads under `data/raw/field/` are in, because nothing
  can.
- **06:30 and 18:30 daily** — `gaffer core-insights`, pulling
  FPL-Core-Insights' per-match player detail, its published cup and European
  fixtures and its club Elo into `data/core_insights/`. The archive pushes at
  07:30 and 17:30 UTC, so the two slots sit either side of the later one.
  Fetched CSVs are cached under `data/raw/core_insights/`: a gameweek whose
  every fixture is finished is downloaded once and never again, while the
  gameweek being played — and any future one the archive has already listed —
  is re-fetched on every run, which is what makes the second slot of the day
  worth having. `gaffer core-insights --refresh N` re-fetches the last N
  gameweeks even if they have gone final, for the file the publisher corrects
  after the fact. The command prints its line rather than exiting non-zero
  when GitHub is slow.

Nothing else is scheduled. The rest of the work the UI can start — including
`sensitivity`, twenty noised re-solves of this week's board in about five
seconds — runs only when you press its button.

Check they are loaded with `launchctl list | grep com.gaffer`. Remove with
`launchctl unload ~/Library/LaunchAgents/com.gaffer.{advise,prices,snapshot,field,review,digest-friday,digest-tuesday,backup,core-insights}.plist`.

## Tests

```
uv run pytest -q
```

## Docs

- **`docs/GUIDE.md`** — the orientation manual: how everything works, every
  feature and how to use it, the version history v1–v11, what is pending.
- `docs/superpowers/ROADMAP.md` — every development cycle with its measured
  results, what was withdrawn and why, and what was explicitly rejected.
- `docs/superpowers/specs/` — one design spec per cycle, each ending in the
  gate numbers and outcomes that justified (or refused) the merge.
- `docs/superpowers/plans/` — the implementation plans behind the specs.
- `docs/superpowers/CONVENTIONS.md` — the measurement rules every cycle
  follows (multi-seed replays, spread quoting, gate discipline).
