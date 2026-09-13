"""The body of the ``refresh-data`` job kind.

It lives in the core because a job body is not a route: nothing here
answers a request, and its one caller is ``gaffer.web.job_kinds``, which
reaches down into the core for every other body it registers. Keeping it
under ``web/routers/`` made the router a dependency of the job table and
gave the core no way to run a refresh at all (v18d §2).

The imports below are top-level because none of them is a cycle dodge:
nothing in the core imports this module, so ``advise`` and the data
builders can be named here the ordinary way.
"""

from __future__ import annotations

from gaffer.advise import fixture_frame, save_live_fixtures
from gaffer.api.client import FPLClient
from gaffer.artifacts import save_snapshots
from gaffer.config import load_config
from gaffer.data.bootstrap import build_events, build_players, build_teams
from gaffer.data.chip_scenarios import write_chip_scenarios
from gaffer.data.live import refresh_live


def run_data_refresh() -> dict:
    """Pull the live season and re-write the bootstrap snapshots.

    The body of the ``refresh-data`` job kind, started through
    ``POST /api/jobs/refresh-data``. The ``POST /api/data/refresh`` route that
    used to queue this on the legacy ``JobRegistry`` is gone: it was a second
    lane past the single-flight runner, and two concurrent refreshes rewrite
    the same parquet files underneath each other.
    """
    cfg = load_config()
    season_idx = len(cfg.train_seasons)
    client = FPLClient()
    frame = refresh_live(client, cfg.current_season, season_idx)
    raw = client.get_bootstrap()
    teams = build_teams(raw)
    fixtures = fixture_frame(client.get_fixtures())
    # The finished-only copy too, exactly as `advise` writes it: it is what
    # the ticker's Elo reads and what /api/health grades as "fixtures", so a
    # refresh that skipped it would leave both stale for ever.
    save_live_fixtures(fixtures, teams, season_idx)
    save_snapshots(build_players(raw), teams, build_events(raw), fixtures)
    # v10b §F2b: the DGW hook v4c shipped has been waiting for data since
    # August. Derived here rather than in a new job kind because the fixture
    # list was just fetched and is in hand — a second kind would re-fetch it
    # to learn the same thing. Never raises; see the writer's docstring.
    write_chip_scenarios(fixtures,
                         dict(zip(teams["team_id"], teams["code"])))
    return {"rows": int(len(frame))}
