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
    for b in advice.buys:
        typer.echo(f"BUY  {b['name']} ({b['ep']} xPts)")
    for s in advice.sells:
        typer.echo(f"SELL {s['name']} ({s['ep']} xPts)")
    if not advice.buys:
        typer.echo("No transfers — bank the FT.")
    if advice.hits:
        typer.echo(f"Hits: -{advice.hits * 4}")
    typer.echo(f"Captain: {advice.captain['name']} | Vice: {advice.vice['name']}")
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


@app.command()
def evaluate(mode: str = typer.Option(
                 "current", help="current (last-10-slot holdout) or "
                                 "benchmark (train <=2023-24, test 2024-25)."),
             decompose: bool = typer.Option(
                 False, "--decompose",
                 help="Run the {model,oracle} x {h1,h3} replay 2x2 instead. "
                      "Hours: launch it under `caffeinate -i`."),
             season: str = "2025-26", start_gw: int = 5):
    """Score the model and write reports/evaluation.json."""
    from gaffer.evaluation import (evaluate_benchmark, evaluate_current,
                                   format_report, run_decomposition,
                                   save_evaluation)

    if decompose:
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
