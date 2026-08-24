# gaffer

An advisor-only Fantasy Premier League tool. It predicts player points with
per-component LightGBM models, plans transfers over a multi-gameweek horizon
with a MILP (PuLP modelling, HiGHS solver with a CBC fallback), and writes an
HTML report.

It never logs into FPL and never makes transfers. It reads public FPL endpoints
only; you apply its advice yourself in the official app.

## Weekly ritual

Before the Friday deadline:

```
uv run gaffer advise
```

That refreshes live data, predicts, optimizes, prints the action list, and
writes `reports/gw{N}-report.html` (plus `reports/gw{N}-advice.json`). Open the
HTML report for the detail behind the terminal summary.

Or let the installed Thursday 18:00 launchd job do it and read the report at
your leisure — that run does `gaffer train` first, then `gaffer advise`, logging
to `logs/advise.log`.

## Commands

| Command | What it does |
|---|---|
| `gaffer advise` | Full weekly run: refresh, predict, optimize, report. Requires trained models and `fpl.entry_id` in config. |
| `gaffer refresh` | Pull the latest FPL data into `data/live/`. |
| `gaffer train` | (Re)train all models on history + live data; writes to `models/`. |
| `gaffer prices` | Likely price changes tonight among the 200 most-owned players. |
| `gaffer league` | Mini-league standings and rival ownership for `fpl.league_id`. |
| `gaffer backtest [--season 2025-26] [--start-gw 5]` | Replay a past season following the tool's own advice. |

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

[data]
train_seasons = ["2022-23", "2023-24", "2024-25", "2025-26"]
current_season = "2026-27"
```

`entry_id` is the number in your FPL team URL. `league_id` likewise from the
mini-league URL.

## Retraining

```
uv run gaffer train
```

Trains the component models (minutes, attacking, defcon, saves, bonus, team)
and saves each as a `.joblib` plus a `.meta.json` in `models/`. `advise` refuses
to run if any model file is missing. Retrain after adding a season to
`train_seasons`, or periodically as the current season accumulates data — the
Thursday automation retrains every week.

## Where things live

- `data/raw/`, `data/history/`, `data/live/` — downloaded and derived datasets (gitignored)
- `models/` — trained model files (gitignored)
- `reports/` — `gw{N}-report.html` and `gw{N}-advice.json` (gitignored)
- `logs/` — output from the launchd jobs (gitignored)

## Price changes

FPL applies price changes at roughly 00:00 UK time. The nightly `prices` job
runs at 23:15 **local** time to catch them before they land, so if your machine
is not on UK time, adjust the `Hour`/`Minute` in
`scripts/com.gaffer.prices.plist` and reinstall.

## Automation

```
./scripts/install_automation.sh
```

Substitutes the project path into the two plists in `scripts/`, copies them to
`~/Library/LaunchAgents/`, and loads them: `com.gaffer.advise` (Thursday 18:00)
and `com.gaffer.prices` (nightly 23:15). Re-run it after moving the project.

Check they are loaded with `launchctl list | grep com.gaffer`. Remove with
`launchctl unload ~/Library/LaunchAgents/com.gaffer.{advise,prices}.plist`.

## Tests

```
uv run pytest -q
```

## Docs

- Design spec: `docs/superpowers/specs/2026-08-23-fpl-ml-advisor-design.md`
- Implementation plan: `docs/superpowers/plans/2026-08-23-fpl-ml-advisor.md`
