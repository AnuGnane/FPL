"""The ``gaffer`` command line.

Every command body imports its dependencies lazily. Loading the whole
pipeline (lightgbm, pulp, jinja) to print ``--help`` would be slow, so each
command pulls in only what it needs when it actually runs.
"""

from __future__ import annotations

import typer

app = typer.Typer(help="FPL ML advisor", no_args_is_help=True)


@app.command()
def advise():
    """Full weekly run: refresh -> predict -> optimize -> report."""
    from gaffer.advise import run_advise
    from gaffer.config import load_config
    from gaffer.errors import GafferError
    from gaffer.report.render import render_report

    cfg = load_config()
    if not cfg.entry_id:
        typer.echo("Set fpl.entry_id in config.toml first.")
        raise typer.Exit(1)
    try:
        advice = run_advise(cfg)
    except SystemExit as e:  # missing models, raised before any network call
        typer.echo(str(e))
        raise typer.Exit(1)
    except GafferError as e:  # season boundary: no next GW at all
                              # (GW1 is handled inside run_advise)
        typer.echo(str(e))
        raise typer.Exit(1)
    from gaffer.tracking import latest_health

    health = latest_health()
    path = render_report(advice, model_health=health)
    typer.echo(f"\n=== GW{advice.gw} — deadline {advice.deadline} ===")
    if advice.data_warning:
        # Loud, and above the picks: the advice below was built without last
        # gameweek's results, and that changes how much to trust it.
        typer.echo(f"\n!!! WARNING: {advice.data_warning} !!!\n")
    def _pct(move: dict) -> str:
        """' [85% of sims]' when the scenario sweep ran, '' otherwise.

        Conditional because the n = 0 output is a pinned regression rail:
        tests/test_v4c_degradation.py compares it character for character.
        """
        f = move.get("frequency")
        return "" if f is None else f" [{round(f * 100)}% of sims]"

    for b in advice.buys:
        typer.echo(f"BUY  {b['name']} ({b['ep']} xPts){_pct(b)}")
    for s in advice.sells:
        typer.echo(f"SELL {s['name']} ({s['ep']} xPts){_pct(s)}")
    if not advice.buys:
        typer.echo("No transfers — bank the FT.")
    if advice.hits:
        typer.echo(f"Hits: -{advice.hits * 4}")
    cap_pct = ""
    if advice.scenarios and advice.scenarios.get("captain_frequency"):
        cap_pct = (f" [{round(advice.scenarios['captain_frequency'] * 100)}"
                   "% of sims]")
    # Both conditional: with no league tilt this is byte-for-byte the v4c
    # line, which tests/test_v4c_degradation.py compares character by
    # character.
    note = f" ({advice.captain_note})" if advice.captain_note else ""
    typer.echo(f"Captain: {advice.captain['name']}{note} | "
               f"Vice: {advice.vice['name']}{cap_pct}")
    if advice.demoted_captain:
        typer.echo(f"Raw-EP captain: {advice.demoted_captain['name']} "
                   f"({advice.demoted_captain['ep']} xPts)")
    if advice.scenarios:
        s = advice.scenarios
        typer.echo(f"Scenarios: {s['completed']}/{s['n']} solved, "
                   f"seed {s['seed']}")
        agreed = "agreed" if advice.raw_optimum_agrees else "differed"
        typer.echo(f"The single-solve optimum {agreed}.")
        for miss in s.get("near_misses", [])[:3]:
            typer.echo(f"Nearest miss: {miss['label']} {miss['code']} at "
                       f"{round(miss['frequency'] * 100)}%")
    typer.echo(f"Expected XI points: {advice.expected_pts}")
    typer.echo(f"Report: {path}")


@app.command()
def refresh():
    """Pull latest FPL data into data/live/."""
    from gaffer.api.client import FPLClient
    from gaffer.config import load_config
    from gaffer.data.live import refresh_live

    cfg = load_config()
    df = refresh_live(FPLClient(), cfg.current_season, len(cfg.train_seasons))
    typer.echo(f"Refreshed {len(df)} player-GW rows.")


@app.command("build-history")
def build_history_cmd():
    """Download the historical seasons into data/history/ (run once)."""
    from gaffer.config import load_config
    from gaffer.data.history import (build_history, build_history_fixtures,
                                     season_name_codes)
    from gaffer.data.match_odds import build_match_odds

    cfg = load_config()
    df = build_history(cfg.train_seasons)
    fx = build_history_fixtures(cfg.train_seasons)
    # Closing odds are part of the corpus now: without them the odds blend
    # weight can only be guessed and Dixon-Coles can never be scored against
    # the market. They join onto the fixtures frame just built.
    odds = build_match_odds(
        cfg.train_seasons, fx, season_name_codes(cfg.train_seasons),
        season_indexes={s: i for i, s in enumerate(cfg.train_seasons)})
    typer.echo(f"History: {len(df)} player-GW rows, {len(fx)} fixtures "
               f"across {len(cfg.train_seasons)} seasons -> data/history/.")
    typer.echo(f"Match odds: {len(odds)} priced fixtures.")


@app.command()
def cups():
    """Ingest cup, European and EFL match dates into data/history/."""
    from gaffer.config import load_config
    from gaffer.data.cups import download_cup_matches
    from gaffer.data.history import season_name_codes

    cfg = load_config()
    # The current season as well as the training ones: congestion is a
    # prediction-time feature, and this week's midweek tie is the whole point.
    seasons = list(cfg.train_seasons) + [cfg.current_season]
    names = {name: code
             for table in season_name_codes(cfg.train_seasons).values()
             for name, code in table.items()}
    out = download_cup_matches(
        seasons, {s: i for i, s in enumerate(seasons)}, names=names)
    typer.echo(f"Cups: {len(out)} club-match dates across {len(seasons)} "
               "seasons -> data/history/cup_matches.parquet.")


@app.command()
def understat():
    """Scrape Understat into data/history/ (long first run; resumable)."""
    from gaffer.api.client import FPLClient
    from gaffer.config import load_config
    from gaffer.data.bootstrap import build_teams
    from gaffer.data.history import season_name_codes
    from gaffer.data.understat import (build_understat_player,
                                       build_understat_team,
                                       history_player_index)

    cfg = load_config()
    if not cfg.understat_enabled:
        typer.echo("Understat disabled in config.toml ([understat] enabled).")
        return
    seasons = list(cfg.train_seasons) + [cfg.current_season]
    indexes = {s: i for i, s in enumerate(seasons)}
    names = season_name_codes(cfg.train_seasons)
    # One name->code table across seasons: codes are stable, and a club that
    # appears in several seasons resolves the same way in all of them.
    flat = {name: code for table in names.values()
            for name, code in table.items()}
    # The scrape covers the current season too, and its promoted clubs are in
    # no historical bootstrap: without the live table their team rows have no
    # code and drop, leaving that season three clubs short.
    live = build_teams(FPLClient().get_bootstrap())
    flat.update({r.name: int(r.code) for r in live.itertuples()})
    players = build_understat_player(seasons, indexes,
                                     history_player_index(cfg.train_seasons))
    teams = build_understat_team(seasons, indexes, flat)
    typer.echo(f"Understat: {len(players)} player-match rows, "
               f"{len(teams)} team-match rows -> data/history/.")


@app.command()
def train():
    """(Re)train all models on history + live data."""
    from gaffer.models.train import load_training_frame, train_all

    df, tg, _ = load_training_frame()
    train_all(df, tg, save=True)
    typer.echo(f"Trained on {len(df)} player-GW rows. Models saved to models/.")


@app.command()
def prices():
    """Tonight's likely price changes among relevant players."""
    from gaffer.api.client import FPLClient
    from gaffer.data.bootstrap import build_players
    from gaffer.prices import price_alerts

    players = build_players(FPLClient().get_bootstrap())
    watch = players.nlargest(200, "selected_by_percent")["code"].tolist()
    alerts = price_alerts(players, watch)
    if alerts.empty:
        typer.echo("No imminent price changes among watched players.")
    for r in alerts.itertuples():
        cal = " [calibrating]" if r.calibrating else ""
        typer.echo(f"{r.name}: {r.direction} ({r.price_change_percent}%){cal}")


@app.command()
def league():
    """Mini-league standings and rival ownership."""
    from gaffer.api.client import FPLClient
    from gaffer.config import load_config
    from gaffer.data.league import fetch_rival_entries

    cfg = load_config()
    if not cfg.league_id:
        typer.echo("Set fpl.league_id in config.toml first.")
        raise typer.Exit(1)
    rivals = fetch_rival_entries(FPLClient(), cfg.league_id, cfg.entry_id)
    if rivals.empty:
        typer.echo(f"No rivals in league {cfg.league_id} yet.")
        return
    typer.echo(rivals.to_string(index=False))


@app.command()
def live():
    """Live points for you and your rivals while the gameweek is on."""
    from gaffer.api.client import FPLClient
    from gaffer.config import load_config
    from gaffer.errors import GafferError
    from gaffer.live_gw import run_live

    cfg = load_config()
    if not cfg.entry_id:
        typer.echo("Set fpl.entry_id in config.toml first.")
        raise typer.Exit(1)
    try:
        run_live(cfg, FPLClient())
    except GafferError as e:
        # Between gameweeks there is simply nothing to show. That is a quiet
        # no-op, not a failure: print the message and exit clean.
        typer.echo(str(e))
        raise typer.Exit(0)


@app.command()
def backtest(season: str = "2025-26", start_gw: int = 5, horizon: int = 1,
             chips: bool = False):
    """Replay a past season following the tool's advice."""
    from gaffer.backtest import run_backtest

    result = run_backtest(season, start_gw, horizon=horizon, chips=chips)
    typer.echo(result)


@app.command("calibrate-decisions")
def calibrate_decisions(start_gw: int = 5):
    """Replay past seasons to rebuild src/gaffer/assets/decision_priors.json.

    Slow (one backtest per season) and refreshed rarely — once a season, or
    when the model shifts materially. The asset it writes ships in git.
    """
    from gaffer.calibrate_decisions import (ASSET_PATH,  # noqa: F401
                                            run_calibration, write_priors)
    from gaffer.config import load_config

    cfg = load_config()
    payload = run_calibration(cfg.train_seasons, start_gw=start_gw)
    dest = write_priors(payload, "src/gaffer/assets/decision_priors.json")
    n = sum(len(v) for v in payload["transfer_surplus"].values())
    typer.echo(f"Calibrated {n} transfer-surplus samples across "
               f"{len(payload['seasons'])} seasons -> {dest}")


@app.command("calibrate-injuries")
def calibrate_injuries(clubs: str = typer.Option(
        "clubs.json", help="JSON file of {transfermarkt slug: club id}.")):
    """Scrape injury spells to rebuild src/gaffer/assets/injury_return_curves.json.

    Slow, network-heavy and refreshed rarely — once a season, or when the
    club list changes. The asset it writes ships in git; without it the
    horizon decay falls back to the flat RECOVERY constant, which is the
    pre-v5 behaviour.
    """
    import json
    from pathlib import Path

    from gaffer.calibrate_injuries import (ASSET_PATH, run_calibration,
                                           write_curves)

    path = Path(clubs)
    if not path.exists():
        typer.echo(f"No club table at {path}. Write a JSON file of "
                   '{"arsenal-fc": 11, ...} — Transfermarkt slug to club id.')
        raise typer.Exit(1)
    payload = run_calibration(json.loads(path.read_text()))
    dest = write_curves(payload, ASSET_PATH)
    typer.echo(f"Fitted {len(payload['curves'])} typed curves from "
               f"{payload['spells']} spells -> {dest}")


@app.command()
def evaluate(mode: str = typer.Option(
                 "current", help="current (last-10-slot holdout) or "
                                 "benchmark (train <=2023-24, test 2024-25)."),
             decompose: bool = typer.Option(
                 False, "--decompose",
                 help="Run the {model,oracle} x {h1,h3} replay 2x2 instead. "
                      "Hours: launch it under `caffeinate -i`."),
             news_shadow: bool = typer.Option(
                 False, "--news-shadow",
                 help="Score the banked news shadow log against completed "
                      "gameweeks instead (gate N2)."),
             season: str = "2025-26", start_gw: int = 5):
    """Score the model and write reports/evaluation.json."""
    from gaffer.evaluation import (evaluate_benchmark, evaluate_current,
                                   evaluate_news_shadow, format_report,
                                   run_decomposition, save_evaluation)

    if news_shadow:
        key, payload = "news_shadow", evaluate_news_shadow()
    elif decompose:
        key, payload = "decomposition", run_decomposition(season=season,
                                                          start_gw=start_gw)
    elif mode == "benchmark":
        key, payload = "benchmark", evaluate_benchmark()
    elif mode == "current":
        key, payload = "current", evaluate_current()
    else:
        typer.echo(f"unknown mode: {mode} (expected current or benchmark)")
        raise typer.Exit(1)
    path = save_evaluation(key, payload)
    typer.echo(format_report(key, payload))
    typer.echo(f"Wrote {path}")


@app.command()
def ui(port: int = typer.Option(8927, help="Port to serve on (default 8927)."),
       open_browser: bool = typer.Option(
           True, "--open-browser/--no-open-browser",
           help="Open the UI in your default browser on start.")):
    """Serve the local web UI on 127.0.0.1 until Ctrl-C."""
    import webbrowser

    import uvicorn

    from gaffer.web.app import create_app

    url = f"http://127.0.0.1:{port}"
    typer.echo(f"gaffer UI on {url} — Ctrl-C to stop")
    if open_browser:
        webbrowser.open(url)
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="info")


def main():
    app()
