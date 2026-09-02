"""The ``gaffer`` command line.

Every command body imports its dependencies lazily. Loading the whole
pipeline (lightgbm, pulp, jinja) to print ``--help`` would be slow, so each
command pulls in only what it needs when it actually runs.
"""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(help="FPL ML advisor", no_args_is_help=True)


@app.command()
def advise(fast: bool = typer.Option(
        False, "--fast",
        help="Skip the scenario sweep (~5 min); serves the raw optimum.")):
    """Full weekly run: refresh -> predict -> optimize -> report."""
    import dataclasses

    from gaffer.advise import run_advise
    from gaffer.config import load_config
    from gaffer.errors import GafferError
    from gaffer.report.render import render_report

    cfg = load_config()
    # n = 0 is the byte-pinned pre-v4c rail: solve once, deterministically.
    # Every consumer of a scenario field already degrades on its absence
    # (the `_pct` helper below is the CLI's own half of that), so the flag
    # needs no second switch anywhere downstream.
    if fast:
        cfg = dataclasses.replace(cfg, scenarios_n=0)
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
    from gaffer.data.bootstrap import build_events, season_from_events
    from gaffer.data.live import refresh_live

    cfg = load_config()
    client = FPLClient()
    # v12 W1 §2.4. Every downstream failure of a rollover is silent:
    # `current_season` is stamped onto every row banked here and every model
    # trained afterwards, so a stale value does not raise — it labels this
    # season's rows as last season's and trains on the mixture. The first
    # symptom is a model that has quietly got worse.
    #
    # `None` is "cannot tell" and never blocks: a bootstrap FPL has not opened
    # for the new season is a normal July state.
    bootstrap = client.get_bootstrap()
    ingested = season_from_events(build_events(bootstrap))
    if ingested is not None and ingested != cfg.current_season:
        typer.echo(
            f"Refusing to refresh: the API is serving {ingested} and "
            f"config.toml says {cfg.current_season}.\n"
            f"A rollover needs two keys changed together in [data]: set "
            f"current_season = \"{ingested}\" and append "
            f"\"{cfg.current_season}\" to train_seasons.")
        raise typer.Exit(1)
    # The same payload, handed on: the guard above already paid for it, and a
    # second fetch would be a second `data/raw/bootstrap-*.json` snapshot of
    # the same file seconds later.
    df = refresh_live(client, cfg.current_season, len(cfg.train_seasons),
                      bootstrap=bootstrap)
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


@app.command("core-insights")
def core_insights_cmd():
    """Ingest FPL-Core-Insights per-match, fixture and Elo tables.

    The launchd job's body, and held to ``snapshot``'s contract: it prints its
    own line and never fails. A twice-daily job that exits non-zero the
    morning GitHub is slow is a job that gets uninstalled.
    """
    try:
        from gaffer.config import load_config
        from gaffer.data.core_insights import download_core_insights

        cfg = load_config()
        # The current season as well as the training ones. The fixture table
        # is a prediction-time input (density_pub_7d reads next week's
        # published ties), so the season being played is the one that matters
        # most, and the training seasons are what makes an arm measurable.
        seasons = list(cfg.train_seasons) + [cfg.current_season]
        written = download_core_insights(
            seasons, {s: i for i, s in enumerate(seasons)})
        total = sum(sum(v.values()) for v in written.values())
        typer.echo(f"Core insights: {total} rows across {len(seasons)} "
                   "seasons -> data/core_insights/.")
    except Exception as exc:  # noqa: BLE001 — a scheduled job never blocks
        typer.echo(f"core insights not collected: {exc}")


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
    """Tonight's likely price changes, and the day's reading, banked.

    The printed list is unchanged and pinned (spec D1c). The banking runs
    *after* it and in its own try, so a read-only disk costs the night's row
    and never the answer the user actually asked for.

    Held to ``snapshot``'s contract on top of that: the launchd job runs this
    at 23:15 every night and a scheduled command that exits non-zero on a bad
    evening is a command that gets uninstalled.
    """
    from gaffer.api.client import FPLClient
    from gaffer.data.bootstrap import build_players
    from gaffer.price_log import bank_prices
    from gaffer.prices import price_alerts

    try:
        players = build_players(FPLClient().get_bootstrap())
    except Exception as exc:  # noqa: BLE001 — a scheduled job never blocks
        typer.echo(f"price check failed: {exc}")
        return
    watch = players.nlargest(200, "selected_by_percent")["code"].tolist()
    alerts = price_alerts(players, watch)
    if alerts.empty:
        typer.echo("No imminent price changes among watched players.")
    for r in alerts.itertuples():
        cal = " [calibrating]" if r.calibrating else ""
        typer.echo(f"{r.name}: {r.direction} ({r.price_change_percent}%){cal}")
    # Instrumentation, and it prints its own line either way. Every player is
    # banked rather than only the alerts above: the row worth having in
    # February is the one that was not an alert in August.
    bank_prices(players)


@app.command()
def snapshot():
    """Bank today's availability state into the daily log (v7c F1).

    The launchd job's body. It prints its own line and never fails: a
    scheduled command that exits non-zero on a bad afternoon is a command
    that gets uninstalled.
    """
    try:
        from gaffer.snapshot import run_snapshot

        run_snapshot()
    except Exception as exc:  # noqa: BLE001 — a scheduled job never blocks
        # run_snapshot swallows its own failures; the import cannot, and an
        # ImportError here would be the one traceback the launchd job still
        # emits every afternoon.
        typer.echo(f"availability snapshot not written: {exc}")


@app.command()
def field_scrape(
        gw: int = typer.Option(0, help="Gameweek to scrape (default: the "
                                       "last one whose deadline has passed)."),
        force: bool = typer.Option(False, "--force",
                                   help="Re-scrape a gameweek already "
                                        "banked.")):
    """Bank the top-10k field sample and its EO for a gameweek (v8c F1).

    The launchd job's body, and held to ``snapshot``'s contract: it prints its
    own line and never fails. A scheduled command that exits non-zero on a bad
    Saturday is a command that gets uninstalled.
    """
    try:
        from gaffer.data.field import run_field_scrape

        run_field_scrape(gw=gw or None, force=force)
    except Exception as exc:  # noqa: BLE001 — a scheduled job never blocks
        # run_field_scrape swallows its own failures; the import cannot, and
        # an ImportError here would be the one traceback the launchd job
        # still emits every weekend.
        typer.echo(f"field scrape not written: {exc}")


@app.command()
def review(gw: int = typer.Option(0, help="Gameweek to review (default: "
                                          "every finished one not yet in "
                                          "the ledger).")):
    """Grade last week's decisions against the model's (v8b F2).

    The launchd job's body, and held to ``snapshot``'s contract: it prints one
    line per gameweek and never fails. A Tuesday with no network is a Tuesday
    with no new grade, not a Tuesday with a traceback.
    """
    try:
        from gaffer.review import run_review

        run_review(gw=gw or None)
    except Exception as exc:  # noqa: BLE001 — a scheduled job never blocks
        # run_review swallows its own failures; the import cannot, and an
        # ImportError here would be the one traceback the launchd job still
        # emits every Tuesday morning.
        typer.echo(f"review not written: {exc}")


@app.command()
def digest(kind: str = typer.Option(
        "friday", "--kind",
        help="friday (pre-deadline briefing) or tuesday (post-review "
             "debrief).")):
    """Write the day's digest, and show it as a notification (v8f D3).

    The launchd job's body, held to ``snapshot``'s and ``review``'s contract:
    it prints one line and never fails. A Friday evening with no network is a
    Friday with no briefing, not a Friday with a traceback in
    ``logs/digest-friday.log``.

    ``run_digest`` takes the notification switch as an argument and has no
    opinion about it; the opinion is ``[digest] notify``, read here.
    """
    try:
        from gaffer.config import serving_config
        from gaffer.digest import run_digest

        run_digest(kind, notify=bool(serving_config().digest_notify))
    except Exception as exc:  # noqa: BLE001 — a scheduled job never blocks
        # run_digest swallows its own failures and raises only on an unknown
        # kind; the imports cannot, and an ImportError here would be the one
        # traceback the launchd job still emits every Friday evening.
        typer.echo(f"digest not written: {exc}")


@app.command()
def league_sim(
        seeds: str = typer.Option("", help="Comma-separated seed bases; "
                                           "default is the shipped seed."),
        n: int = typer.Option(0, help="Simulations per seed (default: "
                                      "league.sim_n)."),
        drift: float = typer.Option(-1.0, help="Rival drift 0-1 (default: "
                                              "league.rival_drift).")):
    """Simulate the mini-league to the end of the season (v8c F2).

    With several seeds it prints mean +/- spread, which is the only form a
    recorded claim about this number may take (CONVENTIONS.md §1).
    """
    from gaffer.api.client import FPLClient
    from gaffer.config import load_config
    from gaffer.league_sim import (SIM_SEED, build_inputs, format_multi_seed,
                                   multi_seed)

    cfg = load_config()
    bases = [int(s) for s in seeds.split(",") if s.strip()] or [SIM_SEED]
    report = multi_seed(
        build_inputs(cfg, FPLClient()), seeds=bases,
        n=int(n or cfg.sim_n),
        rival_drift=(cfg.rival_drift if drift < 0 else float(drift)))
    typer.echo(format_multi_seed(report, cfg.league_id))


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
               f"{payload['spells']} spells across {payload['players']} "
               f"players at {payload['clubs']} clubs "
               f"({payload['players_failed']} players and "
               f"{payload['clubs_failed']} clubs skipped) -> {dest}")


@app.command("diagnose-zeros")
def diagnose_zeros(holdout_slots: int = typer.Option(
        10, help="Gameweek slots to hold out — the evaluation default.")):
    """Decompose the zeros-stratum error and write reports/zeros_diagnostic.json.

    Slow: one full component refit on everything before the holdout, the same
    fit `gaffer evaluate` pays for. A report, not a gate — spec §2.1.
    """
    from gaffer.zeros_diagnostic import DIAGNOSTIC_PATH, run_diagnostic

    run_diagnostic(holdout_slots)
    typer.echo(f"-> {DIAGNOSTIC_PATH}")


@app.command("calibrate-noise")
def calibrate_noise(
    estimation: bool = typer.Option(
        False, "--estimation",
        help="Fit the estimation-only sigma (K=5 seed-bagged ensemble "
             "spread) instead of the residual sigma — v7-model spec §3."),
    out: Path = typer.Option(
        None, "--out",
        help="Where to write the asset. Defaults to the shipped path; point "
             "it at reports/ to fit a candidate without replacing the asset."),
    force: bool = typer.Option(
        False, "--force",
        help="Overwrite a shipped estimation asset with a residual fit. "
             "Refused without this, because the serving flag is on and the "
             "residual sigma is the arm gate S1 failed."),
):
    """Fit src/gaffer/assets/scenario_noise.json.

    Two modes, one asset shape. Without ``--estimation`` this is the v6
    residual σ, fitted on benchmark residuals: slow, refreshed once a season.
    With ``--estimation`` it is the v7 spread of a five-seed LightGBM
    ensemble over the 2025-26 walk-forward — how unsure the *model* is rather
    than how random football is, which is the follow-up gate S1's failure
    pre-registered.

    Either asset ships in git; without one the scenario sweep falls back to
    the (92 - xmins) / 134 heuristic, which is the pre-v6 behaviour.

    A residual fit aimed at the shipped path while an *estimation* asset sits
    there is refused before the fit starts. The two sources are different
    quantities at different scales, the serving flag is on, and the residual
    arm is the one gate S1 failed — so replacing one with the other has to be
    a decision somebody typed (``--force``), not the default of a bare
    command. ``--out`` says the same thing by aiming somewhere else.
    """
    import json

    from gaffer.calibrate_noise import (ASSET_PATH, run_calibration,
                                        run_estimation_calibration,
                                        write_noise)

    dest = out or ASSET_PATH
    if not estimation and out is None and not force:
        try:
            existing = json.loads(Path(dest).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — no asset, or an unreadable one
            existing = {}
        if existing.get("source") == "estimation":
            typer.echo(
                f"Refusing to overwrite {dest}: it holds the estimation "
                f"sigma, which is what the serving flag ships, and this is a "
                f"residual fit — the arm gate S1 failed. Pass --out to write "
                f"a candidate elsewhere, or --force if you mean it.")
            raise typer.Exit(1)

    payload = (run_estimation_calibration() if estimation
               else run_calibration())
    dest = write_noise(payload, dest)
    typer.echo(f"Fitted {len(payload['sigma'])} cells and "
               f"{len(payload['ep_marginal'])} EP marginals from "
               f"{payload['rows']} rows on {payload['season']} "
               f"(source {payload['source']}, "
               f"global sigma {payload['global']}) -> {dest}")


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
             flag_latency: bool = typer.Option(
                 False, "--flag-latency",
                 help="How much warning a status change gave before the "
                      "deadline, and whether the player then started "
                      "(v12 §3.1). Reads the banked snapshot log, refits "
                      "nothing, takes seconds."),
             presser_grades: bool = typer.Option(
                 False, "--presser-grades",
                 help="The presser classifier's verdicts against who actually "
                      "started (v12 §3.2)."),
             calibration: bool = typer.Option(
                 False, "--calibration",
                 help="Per-gameweek reliability for the probabilities the "
                      "weekly run actually served (v9d §4). Reads banked "
                      "components, refits nothing, takes seconds."),
             season: str = "2025-26", start_gw: int = 5):
    """Score the model and write reports/evaluation.json."""
    from gaffer.evaluation import (evaluate_benchmark, evaluate_calibration,
                                   evaluate_current, evaluate_news_shadow,
                                   format_report, run_decomposition,
                                   save_evaluation)

    if flag_latency:
        from gaffer.availability_eval import evaluate_flag_latency

        key, payload = "flag_latency", evaluate_flag_latency()
    elif presser_grades:
        from gaffer.availability_eval import evaluate_presser_grades

        key, payload = "presser_grades", evaluate_presser_grades()
    elif calibration:
        key, payload = "calibration", evaluate_calibration(season=season)
    elif news_shadow:
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


@app.command("track-pens")
def track_pens_cmd(season: str = typer.Option(
        "", help="Season to track (default: fpl.current_season).")):
    """Predicted penalty EP against the penalties actually taken (v7c F3)."""
    from gaffer.pen_tracker import (format_tracker, save_tracker_guarded,
                                    track_pens)

    report = track_pens(season or None)
    # v12 W1 §2.5 (specs/2026-09-01-gaffer-v12-program-design.md). The guard
    # itself lives in pen_tracker so that the web job lane obeys it too; here
    # a refusal is a non-zero exit, mirroring calibrate_noise's above.
    path, refusal = save_tracker_guarded(report)
    if refusal is not None:
        typer.echo(refusal)
        raise typer.Exit(1)
    typer.echo(format_tracker(report))
    typer.echo(f"Wrote {path}")


@app.command()
def backup(to: Path = typer.Option(
               None, "--to",
               help="Where to write the archive. Defaults to [backup] dir, "
                    "then ~/gaffer-backups."),
           rsync: str = typer.Option(
               None, "--rsync",
               help="Also copy the archive here with `rsync -a`. Defaults to "
                    "[backup] rsync_target. Never pruned.")):
    """Tar the data no command can rebuild, and keep the last few."""
    from gaffer.backup import backup_dir, run_backup
    from gaffer.config import load_config

    try:
        cfg = load_config()
        configured, target, keep = (cfg.backup_dir, cfg.backup_rsync_target,
                                    cfg.backup_keep)
    except Exception:  # noqa: BLE001 — a clone with no config can still back up
        configured, target, keep = "", "", 14
    dest = Path(to) if to is not None else backup_dir(configured)
    path = run_backup(to=dest, rsync=rsync or target or None, keep=keep)
    if path is None:
        raise typer.Exit(1)
    typer.echo(f"Wrote {path} ({path.stat().st_size / 1e6:.1f} MB)")


@app.command()
def tidy(apply: bool = typer.Option(
             False, "--apply",
             help="Actually delete. Without it this only prints."),
         older_than: int = typer.Option(
             30, "--older-than",
             help="Age in days for logs/. Backtest logs are judged by whether "
                  "their report exists, not by age.")):
    """List (or delete) replay logs nothing references and stale run logs."""
    from gaffer.tidy import run_tidy

    # A refusal, not a warning: both of these end with the command printing
    # "nothing to tidy", which is indistinguishable from a clean tree. One is
    # a cutoff in the future, the other is the wrong working directory.
    try:
        run_tidy(apply=apply, older_than=older_than)
    except (ValueError, FileNotFoundError) as exc:
        typer.echo(f"tidy: {exc}")
        raise typer.Exit(1) from exc


@app.command()
def mcp():
    """Serve this tree to an MCP client (Claude Code) over stdio.

    Add it with:  claude mcp add gaffer -- gaffer mcp
    """
    # No typer.echo anywhere in this command: stdout *is* the protocol
    # channel, and a banner is a parse error at the other end.
    from gaffer.mcp_server import run

    run()


@app.command()
def ui(port: int = typer.Option(8927, help="Port to serve on (default 8927)."),
       open_browser: bool = typer.Option(
           True, "--open-browser/--no-open-browser",
           help="Open the UI in your default browser on start."),
       lan: bool = typer.Option(
           False, "--lan",
           help="Serve to your whole network so a phone can reach it. "
                "Reads are open; writes need the printed token.")):
    """Serve the local web UI until Ctrl-C (loopback unless --lan)."""
    import webbrowser

    import uvicorn

    from gaffer.config import load_config
    from gaffer.web import lan as lan_mod
    from gaffer.web.app import create_app, generate_token

    host = "0.0.0.0" if lan else "127.0.0.1"
    url = f"http://127.0.0.1:{port}"
    typer.echo(f"gaffer UI on {url} — Ctrl-C to stop")
    # v12 W1 §2.8. None on loopback, which is the default and the
    # overwhelmingly common case: no token, no middleware, and the app is the
    # app that has always shipped.
    token = None
    if lan:
        try:
            token = load_config().web_token or None
        except Exception:  # noqa: BLE001 — a clone with no config still serves
            token = None
        generated = token is None
        token = token or generate_token()
        address = lan_mod.lan_ip()
        if address is None:
            typer.echo("Could not work out this machine's LAN address — "
                       "the loopback URL above still works.")
        else:
            lan_url = f"http://{address}:{port}"
            typer.echo(f"On your network: {lan_url}")
            # The QR carries the token; the printed line does not. Scanning
            # the code is the whole point of it being there, and a phone that
            # lands on a tokenless page gets a UI where every star and every
            # pin fails with a 403 it cannot fix without retyping a
            # 22-character string by hand. The bare URL stays printed for the
            # second device, the one typing it in.
            for line in lan_mod.qr_lines(f"{lan_url}/?token={token}"
                                         if token else lan_url):
                typer.echo(line)
        if generated:
            typer.echo(f"Write token (this run only): {token}")
            typer.echo(f"Open on your phone with ?token={token} — the page "
                       f"stores it. Set [web] token in config.toml to keep "
                       f"one across restarts.")
        else:
            typer.echo("Writes need the [web] token from config.toml; open "
                       "with ?token=<it> once per device.")
        typer.echo("Serving to the whole network. Reads are open; writes need "
                   "the token above.")
    if open_browser:
        webbrowser.open(url)
    # v9d §2 (specs/2026-09-01-gaffer-v9d-design.md): this serves a single
    # process, and that is a contract rather than a default.
    #
    # ``create_app()`` builds a ``JobRunner`` onto ``app.state`` (web/app.py:51)
    # and every job invariant is per-instance: one lane at a time, the run
    # records in a dict, the streamed log lines in per-run buffers an SSE
    # response tails. A second worker gets a second runner, and then a browser
    # that started a job on worker A polls worker B, which has never heard of
    # it — no crash, no error, just a job that never finishes on screen.
    #
    # Passing the app *instance* rather than an import string is what makes
    # ``workers=`` impossible: uvicorn can only fork from something it can
    # re-import. So the shape of this call is load-bearing, and
    # tests/test_v9d_degradation.py asserts it rather than trusting a comment.
    # Making the runner multi-process is a real piece of work (shared state,
    # a broker for the streams) and deliberately out of scope here.
    # A single process is the contract this line keeps.
    #
    # v12 W1 §2.8 (specs/2026-09-01-gaffer-v12-program-design.md) added the
    # token. `token` is None on loopback, and `create_app` installs no
    # middleware at all in that case — so this one call is still, byte for
    # byte, the app that has always shipped by default.
    uvicorn.run(create_app(token=token), host=host, port=port,
                log_level="info")


def main():
    """The console-script entry point.

    GafferError is the "you, not the code" exception: no config.toml, no
    trained models, a season with no next gameweek. Individual commands catch
    it where they can say something more useful, but the ones that do not were
    letting it reach typer's handler, which prints forty lines of traceback and
    then the sentence that was the whole message. A stack trace of our own
    code is noise when the fix is to copy config.example.toml.

    Only GafferError. Anything else is a bug and keeps its traceback, or the
    next one gets debugged blind.
    """
    from gaffer.errors import GafferError

    try:
        app()
    except GafferError as exc:
        # stderr, like every other failure: a caller redirecting stdout to a
        # file should still see why the run stopped, and should not find the
        # message pasted into the output it was collecting.
        typer.echo(str(exc), err=True)
        raise SystemExit(1) from None
