# gaffer

An advisor-only Fantasy Premier League tool. It predicts player points with
per-component LightGBM models, plans transfers over a receding multi-gameweek
horizon with a MILP (PuLP modelling, HiGHS solver, CBC fallback), and writes an
HTML report. `gaffer ui` serves the same advice as a local web app.

**It never logs into FPL and it never makes a transfer.** It reads public FPL
endpoints only; you apply its advice yourself in the official app.

This README is the front door: setup, commands, configuration, reference.
**[docs/GUIDE.md](docs/GUIDE.md)** is the orientation manual behind it — how
everything works end to end, every feature and how to use it, the version
history, and in its §12 what is still open.

**Contents:** [First-time setup](#first-time-setup) ·
[The weekly ritual](#the-weekly-ritual) · [Commands](#commands) ·
[Configuration](#configuration) · [The web UI](#the-web-ui) ·
[Automation](#automation) · [Backtesting](#backtesting) ·
[Retraining and season rollover](#retraining-and-season-rollover) ·
[Where things live](#where-things-live) · [Tests](#tests) · [Docs](#docs)

## First-time setup

You need Python 3.12 or newer, [uv](https://docs.astral.sh/uv/), and — only if
you intend to work on the web UI — Node. The shipped wheel carries a pre-built
frontend, so end users never need Node.

```
git clone <this repo> && cd FPL
uv sync                        # the Python environment, into .venv/
cp config.example.toml config.toml
```

Then edit `config.toml`: set `fpl.entry_id` to the number in your FPL team URL,
and `fpl.league_id` to the mini-league you care about. Everything else in the
example is at its shipped default, with a comment saying what it does.

For the bookmaker blend, put a free key from
[the-odds-api.com](https://the-odds-api.com) in the `[odds]` table under
`api_key`. **That value is a secret**: `config.toml` is gitignored, the web UI
is forbidden from reading or writing the file, and nothing here should ever
print it. With no key the odds step is skipped silently.

A fresh clone has no data and no models:

```
uv run gaffer build-history    # downloads data/history/*.parquet (slow, once)
uv run gaffer train            # trains the component models into models/
uv run gaffer advise           # the weekly run
```

`build-history` caches its downloads under `data/raw/vaastav/`, so re-running it
is cheap. `advise` refuses to run without the model files or without
`fpl.entry_id`.

To work on the web UI as well:

```
cd frontend && npm install
npm run dev        # http://localhost:5173, proxies /api to 127.0.0.1:8927
npm run build      # emits src/gaffer/web/static/, which the wheel ships
```

The build output is untracked, so a fresh clone serves a "frontend not built"
message until `npm run build` has run once.

## The weekly ritual

Before the deadline: `uv run gaffer advise`.

That refreshes the live data, predicts, optimizes, writes the brief, prints the
action list, and leaves `reports/gw{N}-report.html` and
`reports/gw{N}-advice.json` behind. Since v17d it is one call to
`pipeline.weekly_run` — the same body the web app's advise job runs — so the
terminal, the report, the JSON and the UI can never disagree about what was
advised. `--fast` skips the ~5-minute scenario sweep and serves the raw optimum
without the risk spread around it. Before GW1 there is no squad to transfer
from, so the run builds an opening fifteen out of the full 100.0m budget
instead of erroring.

Or let the Thursday 18:00 launchd job do it and read the report at your leisure
— that run banks a price reading, then `gaffer train`, then `gaffer advise`,
logging to `logs/advise.log`.

## Commands

The weekly core:

| Command | What it does |
|---|---|
| `gaffer advise [--fast]` | The full weekly run: refresh, predict, optimize, report, brief. Needs trained models and `fpl.entry_id`. |
| `gaffer refresh` | Pull the latest FPL data into `data/live/`. |
| `gaffer train` | (Re)train every component model on history plus live data, into `models/`. |
| `gaffer brief` | Rewrite this week's LLM brief from the banked advice, without re-solving. Never fails a run: a dead command or a brief that failed its truth check is one printed line. |
| `gaffer ui [--port N] [--no-open-browser] [--lan]` | Serve the local web app on 127.0.0.1:8927. |

Standing intelligence — the jobs the automation schedules, each runnable by
hand:

| Command | What it does |
|---|---|
| `gaffer prices` | Tonight's likely price changes, and every player's reading banked to `data/live/price_log.parquet`. |
| `gaffer snapshot` | Bank today's availability state into the daily log (idempotent per UTC day). |
| `gaffer field-scrape [--gw N] [--force]` | Bank a gameweek's top-10k sample: the squads, anonymised, and their effective ownership with standard errors. |
| `gaffer core-insights [--refresh N]` | Ingest FPL-Core-Insights per-match stats, published cup and European fixtures, and club Elo into `data/core_insights/`. `--refresh N` re-fetches the last N gameweeks past the cache. |
| `gaffer review [--gw N]` | Grade every gameweek FPL has finalised since the last run into the decision ledger. |
| `gaffer digest --kind friday\|tuesday` | The Friday briefing or the Tuesday debrief: written to `reports/`, shown as a macOS notification. |
| `gaffer backup [--to DIR] [--rsync TARGET]` | Tar the ~16 MB no command can rebuild into `~/gaffer-backups`; keep the newest fourteen. |

League and matchday:

| Command | What it does |
|---|---|
| `gaffer league` | Mini-league standings and rival ownership. |
| `gaffer live` | In-gameweek tracker: your live points and the projected table while matches are on. Bonus is provisional and no autosubs are applied — the web UI's Live page projects both. |
| `gaffer league-sim [--seeds a,b,c]` | Monte Carlo of your mini-league: P(win), P(top 3), expected finish, the margin fan. Several seeds print the spread, which is the only form a recorded claim about this number may take. |

Evaluation and research:

| Command | What it does |
|---|---|
| `gaffer evaluate [--mode current\|benchmark]` | The model scorecard, into `reports/evaluation.json`. |
| `gaffer evaluate --calibration` | Per-gameweek reliability for the probabilities the weekly run actually served. Refits nothing; seconds. |
| `gaffer evaluate --news-shadow` | Score the banked news-shadow log against completed gameweeks. |
| `gaffer evaluate --flag-latency` | How much warning a status change gave before the deadline, and whether the player then started. |
| `gaffer evaluate --presser-grades` | The presser classifier's verdicts against who actually started, over verdicts recorded *before* their deadline. |
| `gaffer backtest [--season S] [--start-gw N] [--horizon N] [--chips]` | Replay a past season following the tool's own advice. |
| `gaffer track-pens` | Predicted penalty EP against the penalties actually taken. |
| `gaffer diagnose-zeros` | Decompose the error on players who blanked, into `reports/zeros_diagnostic.json`. |

Housekeeping and one-time setup:

| Command | What it does |
|---|---|
| `gaffer tidy [--apply] [--older-than DAYS]` | List — and only with `--apply`, delete — replay logs nothing references and stale run logs. It reclaims tens of kilobytes: a correctness tool, not a disk-space one. |
| `gaffer mcp` | Serve this tree to an MCP client over stdio: `claude mcp add gaffer -- gaffer mcp`. Six tools (`projections`, `explain`, `whatif`, `ledger`, `freshness`, `health`), all reads. Each wraps the router function that already serves the same payload to the web app, except `whatif`, which re-solves synchronously because the HTTP route returns a job id. |
| `gaffer build-history` | Download the `train_seasons` archives into `data/history/`. Once, before the first `train`. |
| `gaffer understat` / `gaffer cups` | Auxiliary history ingestion. Long first runs, resumable, rarely needed again. |
| `gaffer calibrate-decisions` / `calibrate-injuries` / `calibrate-noise` | Rebuild the committed calibration assets from replays and scrapes. Occasional, not weekly. |

`cd frontend && npm run types` is not a `gaffer` subcommand but belongs in the
same list: it writes `frontend/src/schemas.json` and
`types.generated.ts` from the live pydantic models. **Run it after any change
to `src/gaffer/web/schemas.py`** and commit both; `npm run types -- --check`
exits 1 naming any file that drifted. `frontend/src/types.ts` is hand-written
and is never overwritten.

## Configuration

`config.example.toml` is a working file with every key at its shipped value and
a comment explaining each; copy it and edit. What follows is the shape, with
the defaults **as `src/gaffer/config.py` declares them** — the example
deliberately differs on a few knobs this tree has tuned.

```toml
[fpl]
entry_id = 0         # your FPL team ID, from the team URL
league_id = 0        # mini-league ID for rival tracking and the λ tilt

[optimizer]
horizon = 3          # gameweeks planned ahead, bounded 1-8. Three is the
                     # default and what this tree runs: the 2025/26 sweep took
                     # the fewest hits at three, and six chased noise.
decay = 0.85         # per-GW discount on future expected points
vice_weight = 0.1    # weight on the vice-captain's expected points
bench_weight = 0.10  # weight on bench points
ft_value = 1.5       # points value of holding a free transfer
itb_value = 0.05     # points per 1.0m in the bank at horizon end
hit_cost = 4         # points charged per extra transfer
price_timing = true  # charge a deferred sale its expected overnight drop
alt_plan_max_gap = 2.0   # how far behind the recommendation an alternative may
                     # sit and still be offered as Plan B or C, in objective
                     # points. 0 turns the search off; each one costs a solve.
max_hits = 2         # most hits in any one gameweek; 15 means no cap
max_transfers = 15   # most transfers in any one gameweek; 0 means bank
hit_bar = 0.60       # the share of the transfer ladder's shared draws a rung
                     # must win against the one below before the advice steps
                     # up to it. Bounded 0.5-0.95.
top_n = { GKP = 8, DEF = 22, MID = 26, FWD = 14 }
                     # candidate pool per position, merged over these defaults

[model]
xg_per_shot = false  # off: the head metric liked it, the replay lost 28 points

[scenarios]
n = 0                # scenario-sweep re-solves; the example file sets 40
draw_availability = true
decision_priors = true

[odds]
# api_key = "..."    # optional, free from the-odds-api.com; a secret

[data]
train_seasons = ["2022-23", "2023-24", "2024-25", "2025-26"]
current_season = "2026-27"
```

`[news]`, `[league]`, `[digest]`, `[backup]` and `[web]` are optional and all
default to what `config.example.toml` shows. `[news]` drives the injury and
predicted-line-up layer, every source of which degrades to the official FPL
flag on its own; `llm_classifier = false` with `llm_shadow = true` is the
shipped posture, so the presser classifier logs what it would have done and
changes no advice, and its default `llm_command` hands the model no tools
because every text it reads is scraped from the web. `[league]` holds the λ
tilt's dials, plus `focus` and `stance`, which are normally set from the League
page. `[web]` is consulted only by `gaffer ui --lan`.

### `config.local.toml`

An **overlay**, merged over `config.toml` after it is read — same tables, same
keys, and it may introduce a section `config.toml` never declared. It is the
file **Model → Settings owns and writes**; the web app never touches
`config.toml`, which carries the odds key. Gitignored too. Hand-edit it freely;
the Settings tab reads back whatever is in it and says, per row, which of the
two files the value in force came from. The merge is per table and per key, and
one level further in wherever both sides are themselves tables — so an overlay
saying `top_n = { GKP = 3 }` keeps the other three pool sizes.

Since v17e, `config.py` is the **only** module in the tree that opens either
TOML file, and a rail asserts it: `config_in_force()` is the one cached,
never-raising read every serving path uses, `load_config(path)` the loud parser
the CLI calls, `invalidate()` the one way to clear the cache. A key in
`[optimizer]` or `[data]` that is not a config field is ignored with a printed
line naming it, and so is an overlay that will not parse at all — one bad write
from the Settings tab must not stop every job on the machine.

### Bookmaker odds

With a key in `[odds] api_key`, market prices for the upcoming fixtures are
inverted into an expected goals-against per team and blended into the team
model's clean-sheet and goals-conceded predictions at a **fitted** market
weight, refitted on every `gaffer train` and stored in
`models/blend.params.json` (0.7 when there is nothing fitted yet). Fixtures the
feed misses, a dead key or a club name that fails to match all fall back to the
pure model output. The free tier allows 500 requests a month and `advise`
spends one pull a week.

## The web UI

`uv run gaffer ui` serves the whole tool on <http://127.0.0.1:8927> and opens
your browser. `--port N` moves it, `--no-open-browser` leaves the browser
alone. Everything it draws comes from the artifacts the CLI writes, so most of
it works offline; long jobs run through a single-lane job runner with streamed
logs.

**One process, and that is a contract.** Every job-runner invariant is
per-instance, so a second worker gives you a job that never finishes on screen;
`cli.ui` passes uvicorn the app *instance* rather than an import string, which
makes `workers=` impossible rather than merely unset. It binds loopback only by
default — that is the whole security model, so do not put it behind a public
proxy.

**`--lan`** binds every interface so a phone on the sofa can reach it, and
prints the LAN URL with a QR code. Reads are open; every non-GET route needs an
`X-Gaffer-Token` header or answers 403. The token is `[web] token`, or one
generated at startup and printed once in the banner; the QR carries it, so a
scanned code is authorised on first load and a typed URL needs `?token=…` once.
None of this middleware is installed on loopback.

Six hubs, and `docs/GUIDE.md` §5 has the detail on each:

- **This Week** — the answer: the advised XI on a pitch, the transfers, the
  captain sentence against the top-10k field, the transfer ladder with the
  rung the walk chose and the step it refused, your deviation note, and the
  week written as prose by the brief.
- **Planning** — the future, in six tabs: the solved Board with Plan A/B/C
  and "why this move", the What-If lab (which re-solves the real MILP under
  your locks, bans, forced buys and must-sells), Drafts, Timeline, the Chips
  workbench, and the odds-implied fixture Ticker.
- **Players** — the evidence: the candidate pool with the "why 6.8?"
  breakdown behind every name, Compare for four players side by side, the
  Dixon-Coles fixture Matrix, and your Watchlist.
- **League** — every league you are in, one of which drives the plan: the
  race with real Monte Carlo win probabilities, rival squads and
  differentials, a league what-if, and the Field panel.
- **Live** — matchday: live points with autosubs projected, provisional bonus
  from BPS, and a race chart against the pre-gameweek plan.
- **Model** — the mirror: holdout quality and calibration, the graded
  decision Review, the Season dashboard, Health, the Journal, History, and
  the Settings tab that writes `config.local.toml`.

The whole app is drawn in one design language (v14): hairline rules rather than
cards, tabular figures, colour spent only where it means something.
`frontend/src/styles/theme.css` holds the tokens, `kit/tokens.test.ts` the
rules. Pages render in dark and light.

## Automation

`./scripts/install_automation.sh` substitutes the project path into the nine
plists in `scripts/`, copies them to `~/Library/LaunchAgents/` and loads them.
Re-run it after moving the project — the plists embed the path.

| When | Job | What it does |
|---|---|---|
| Thu 18:00 | `com.gaffer.advise` | `prices`, then `train`, then `advise` (which chains the brief). Logs to `logs/prices.log` and `logs/advise.log`. |
| Nightly 23:15 | `com.gaffer.prices` | Banks every player's price-predictor reading. Local time, for a UK-midnight event: adjust `scripts/com.gaffer.prices.plist` if you are not on UK time. |
| Daily 17:00 | `com.gaffer.snapshot` | Banks the day's availability state. |
| Sat & Sun 12:30 | `com.gaffer.field` | Samples ~300 top-10k squads an hour after the deadline; banks their EO. |
| Tue 09:00 | `com.gaffer.review` | Grades every gameweek FPL has finalised into the decision ledger. |
| Fri 17:00 | `com.gaffer.digest-friday` | The briefing, after the pressers and before the deadline. |
| Tue 09:30 | `com.gaffer.digest-tuesday` | The debrief, half an hour after the review has banked. |
| Nightly 23:45 | `com.gaffer.backup` | Tars `data/live/`, `data/raw/field/`, `data/raw/tier_eo/`, `reports/` and `models/` — about 16 MB — into `~/gaffer-backups`; keeps fourteen. A `--rsync` copy is never pruned. |
| 06:30 & 18:30 | `com.gaffer.core-insights` | The FPL-Core-Insights pull. Twice a day because the gameweek being played is re-fetched every run. |

Check what is loaded with `launchctl list | grep com.gaffer`; **on this machine
today only two of the nine are** (see `docs/GUIDE.md` §12.0). Remove them with
`launchctl unload ~/Library/LaunchAgents/com.gaffer.<name>.plist`. Nothing else
is scheduled: every other job — a sensitivity sweep, a re-solve, a retrain —
runs when you press its button in the UI.

## Backtesting

```
uv run gaffer backtest --season 2025-26 --start-gw 5 --horizon 6 --chips
```

Replays a past season following the tool's own advice, retraining as the season
goes. Two things are truncated at each week's deadline, not one: the training
data the models are refit on, and the feature rows for the later gameweeks of
the horizon, rebuilt each week from history up to that deadline plus the
fixture list — so a GW+1 row never carries a result that had not been played.
`--horizon N` plans N weeks ahead and executes only the first, then re-plans;
`--horizon 1` (the default here) is the myopic single-week replay. `--chips`
lets the replay play the four chips when one clears its threshold, tracking the
two half-season sets separately.

For season-scale claims, `scripts/v7b_replay.py --arm <arm> --tag <tag>
--seed-bases a,b,c` is the harness: three or more seed bases in one process,
with the spread quoted. `docs/superpowers/CONVENTIONS.md` is the house rule
book for what a measurement has to do before it counts.

## Retraining and season rollover

`uv run gaffer train` trains the six component models — minutes, team,
attacking, defcon, saves, bonus — plus the calibration model that corrects the
level bias in the assembled expected points, saving each as a `.joblib` plus a
`.meta.json` in `models/`. `advise` refuses to run if any is missing; the
Thursday job retrains weekly.

At a rollover, edit **both** `[data]` keys together: append the finished season
to `train_seasons` *and* set `current_season` to the new one, then run
`gaffer build-history` and `gaffer train`. `season_idx` is derived from
`len(train_seasons)`, so adding a season without moving `current_season` on
makes the live season collide with the one you just archived.

`gaffer refresh` **refuses** rather than ingesting a season the config does not
name: it compares the bootstrap's own deadlines with `current_season` and stops,
naming both values and both keys. There is no `--force`, deliberately — the
failure it prevents (August rows written under last season's index, then trained
on) is silent, and a flag to skip the check would be reached for on exactly the
morning it matters.

## Where things live

- `src/gaffer/` — the Python package. `advise.py` (`gather_inputs` then the
  pure `build_advice`), `inputs.py` (the frozen seam between them), `served.py`
  (the `ServedPlan` the advice JSON *is*), `pipeline.py` (the one weekly run),
  `config.py` (the one config reader), `ladder.py`, `brief.py`, `optimize/`,
  `models/`, `features/`, `web/`.
- `frontend/` — React and Vite source; the build lands in
  `src/gaffer/web/static/` (untracked, shipped in the wheel).
- `data/` — downloaded and derived datasets, gitignored but for
  `data/manager_tenures.toml`, curated EPL head-coach spells. `data/live/`
  holds the standing logs — price, availability, field EO, presser — the
  corpus several future features need a *season* of, which is why the
  collectors run whether or not anything reads them yet.
  `data/raw/field/{season}/gw{N}.json` is the sampled top-10k squads,
  anonymised by index; with `data/raw/tier_eo/`, the only bytes here no
  command can rebuild, which is what `gaffer backup` exists for.
- `models/`, `reports/`, `logs/` — trained models; the reports, advice JSON,
  decision ledger, pins, stars, drafts and digests; launchd output. All
  gitignored, as are `config.toml` and `config.local.toml`.

## Tests

```
.venv/bin/pytest -q                                   # 4509 Python tests
.venv/bin/pytest -q -m "not slow and not golden"      # the inner loop, ~70 s
.venv/bin/pytest -q -rs tests/test_golden_board.py tests/test_pipeline.py
                                                      # the golden gate, ~18 min
cd frontend && npm run check                          # 1098 tests, types, drift, lint
```

The golden gate replays one recorded gameweek through the whole weekly solve in
a frozen directory and compares the advice, the solve state and the ladder byte
for byte with committed files. Run it with `-rs`: a stale board *skips*, and the
skip line names the file. **0 skipped is the pass.** Read vitest's
`Errors  N error` line as a failure — an unhandled rejection does not change
its exit code.

A large share of the Python suite is *degradation rails*: tests that pin the
honesty rules and the counts a later change must not move silently — API routes
(51), job kinds (12), `Config` fields (62), the files a cycle was not authorised
to edit, and the staging rules that keep `config.toml` out of git. A rail
failing after an edit is telling you which rule the edit crossed, and its
message names the file that owns it. Do not edit a rail to make it pass.

## Docs

- **`docs/GUIDE.md`** — the orientation manual: how everything works, every
  feature and how to use it, how a development cycle runs, the version history
  v1–v18h, and — in §12 — what is pending and what was deliberately left open.
- `docs/superpowers/ROADMAP.md` — the tracker: what is open, candidates for the
  next spec, then every cycle in order with its measured results, what was
  withdrawn and why, and what was explicitly rejected.
- `docs/superpowers/CONVENTIONS.md` — the measurement rules every cycle follows:
  multi-seed replays, spread quoting, pre-registered gates. Alongside it,
  `research/`, `specs/` and `plans/` hold the ranked surveys each programme was
  picked from, one design spec per cycle ending in its gate numbers, and the
  implementation plans behind them.
- `CLAUDE.md` — the working rules for this repo: the commands, the pins, the
  protected files, the secrets ritual, the git conventions.
