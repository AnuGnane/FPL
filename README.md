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
| `gaffer build-history` | Download the `train_seasons` archives into `data/history/`. Run once, before the first `train`. |
| `gaffer refresh` | Pull the latest FPL data into `data/live/`. |
| `gaffer train` | (Re)train all models on history + live data; writes to `models/`. |
| `gaffer prices` | Likely price changes tonight among the 200 most-owned players. |
| `gaffer league` | Mini-league standings and rival ownership for `fpl.league_id`. |
| `gaffer live` | In-gameweek tracker: your live points and the projected league table while matches are on. |
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

[data]
train_seasons = ["2022-23", "2023-24", "2024-25", "2025-26"]
current_season = "2026-27"
```

`entry_id` is the number in your FPL team URL. `league_id` likewise from the
mini-league URL.

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

## Live gameweek

```
uv run gaffer live
```

Read-only, for while the matches are on. Prints your live points and a
projected league table, with two caveats it states itself: bonus points are
provisional, reconstructed 3/2/1 from the current BPS table until FPL settles
each match, and no autosubs are applied — the XI is scored as picked, so bench
points never count. Between gameweeks it prints "no gameweek in progress" and
exits clean.

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
MILP against the saved pool — the plan diff shows what changed), **League
Race** (standings, trajectory, win probability and what λ is doing, with
rival intel a click away: each rival's squad, overlap and differentials
against yours), **Live** (in-gameweek points, auto-refreshing), **Players**
(the candidate pool, with the "why 6.8?" breakdown behind every name),
**History** (past runs, expected versus actual, price charts) and **Runs &
Health** (data freshness, model metrics, the launchd log, re-run buttons).
A fixture ticker sits alongside them and is embedded read-only in the
What-If Lab.

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
- `models/` — trained model files (gitignored)
- `reports/` — `gw{N}-report.html` and `gw{N}-advice.json` (gitignored)
- `logs/` — output from the launchd jobs (gitignored)
- `frontend/` — React/Vite source for the web UI; built output lands in
  `src/gaffer/web/static/` (gitignored, shipped in the wheel)

## Price changes

FPL applies price changes at roughly 00:00 UK time. The nightly `prices` job
runs at 23:15 **local** time to catch them before they land, so if your machine
is not on UK time, adjust the `Hour`/`Minute` in
`scripts/com.gaffer.prices.plist` and reinstall.

## Automation

```
./scripts/install_automation.sh
```

Substitutes the project path into the three plists in `scripts/`, copies them to
`~/Library/LaunchAgents/`, and loads them: `com.gaffer.advise` (Thursday 18:00),
`com.gaffer.prices` (nightly 23:15) and `com.gaffer.snapshot` (daily 17:00, banks
the availability log the news corrector will train on). Re-run it after moving
the project.

Check they are loaded with `launchctl list | grep com.gaffer`. Remove with
`launchctl unload ~/Library/LaunchAgents/com.gaffer.{advise,prices}.plist`.

## Tests

```
uv run pytest -q
```

## Docs

- Design spec: `docs/superpowers/specs/2026-08-23-fpl-ml-advisor-design.md`
- Implementation plan: `docs/superpowers/plans/2026-08-23-fpl-ml-advisor.md`
- v3 design spec: `docs/superpowers/specs/2026-08-24-gaffer-v3-ui-design.md`
- v3 implementation plan: `docs/superpowers/plans/2026-08-24-gaffer-v3-ui.md`
