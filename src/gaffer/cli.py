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
    except GafferError as e:  # season boundary: GW1, or no next GW at all
        typer.echo(str(e))
        raise typer.Exit(1)
    from gaffer.tracking import latest_health

    health = latest_health()
    path = render_report(advice, model_health=health)
    typer.echo(f"\n=== GW{advice.gw} — deadline {advice.deadline} ===")
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
def backtest(season: str = "2025-26", start_gw: int = 5):
    """Replay a past season following the tool's advice."""
    from gaffer.backtest import run_backtest

    result = run_backtest(season, start_gw)
    typer.echo(result)


def main():
    app()
