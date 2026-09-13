"""What the live models say, and the availability they say it under.

Moved out of ``advise.py`` whole (v18d §2). ``inputs.LiveModels`` is the
seam the weekly run loads models through, and ``snapshot`` banks the
availability frame every day; both reached back into ``advise`` from inside a
function body to dodge the cycle ``advise → inputs``. The two functions and
the model list are the model side of gather, so they live with the models
and both callers import them at the top.

The one join in here is the one the ``advise`` docstring warns about:
component predictions are stitched **positionally**, not merged. Every
model's ``predict`` returns one row per input row in input order, and
``(code, season_idx, gw)`` is *not* unique in a double gameweek — merging on
it fans a player's two fixtures out into four rows and doubles their
expected points. The team model genuinely is many-to-one, so that one *is*
a merge — on ``(team_code, season_idx, gw, opp_code)``, with ``opp_code`` in
the key so a double gameweek's two fixtures stay distinct.
"""

from __future__ import annotations

import pandas as pd

from gaffer.config import Config
from gaffer.data.news.lineups import fetch_lineups
from gaffer.data.news.normalize import availability_frame
from gaffer.data.news.premierinjuries import fetch_injuries
from gaffer.models.components import card_penalty
from gaffer.models.minutes import apply_availability
from gaffer.models.persistence import load_model
from gaffer.models.team import (ODDS_AGAINST_COL, blend_team_odds,
                                odds_blend_weight)
from gaffer.models.train import DEFAULT_E_GC, DEFAULT_P_CS
from gaffer.set_pieces import add_pen_ep, attack_multipliers, pen_notices

MODEL_NAMES = ["minutes", "team", "attacking", "defcon", "saves", "bonus"]


def news_availability(cfg: Config, players: pd.DataFrame,
                      teams: pd.DataFrame, events: pd.DataFrame,
                      gw: int) -> pd.DataFrame:
    """The availability frame for this run: official flags, sharpened by news.

    Every failure mode lands in the same place. ``[news] enabled = false``
    skips the fetchers entirely; a dead host, a rewritten page or a match rate
    below the floor returns an empty frame from the fetcher itself; and
    :func:`availability_frame` with empty news inputs reproduces the official
    frame exactly. Advice never blocks on news, and each degraded source
    prints one line — the same shape the league and tier-EO paths use.

    "Degraded" includes *returning nothing*, not only raising: a rewritten
    page and a match rate under the floor both come back as an empty frame,
    and an unremarked empty frame reads as "nobody in the league is injured".
    Every enabled source that answered with nothing is named.
    """
    official = players[["code", "status", "chance_of_playing"]]
    if not cfg.news_enabled:
        return official
    injuries = lineups = None
    spoke_up: set[str] = set()
    if cfg.news_injuries:
        try:
            injuries = fetch_injuries(players, teams,
                                      cache_hours=cfg.news_cache_hours,
                                      min_coverage=cfg.news_min_coverage)
        except Exception as e:  # noqa: BLE001 — news must never block advice
            spoke_up.add("premierinjuries")
            print(f"news: premierinjuries unavailable — official flags "
                  f"only ({e})")
    if cfg.news_lineups:
        try:
            lineups = fetch_lineups(players, teams,
                                    cache_hours=cfg.news_cache_hours,
                                    min_coverage=cfg.news_min_coverage)
        except Exception as e:  # noqa: BLE001 — news must never block advice
            spoke_up.add("line-ups")
            print(f"news: predicted line-ups unavailable — official flags "
                  f"only ({e})")
    for enabled, frame, name in ((cfg.news_injuries, injuries,
                                  "premierinjuries"),
                                 (cfg.news_lineups, lineups, "line-ups")):
        if enabled and name not in spoke_up and (frame is None
                                                 or frame.empty):
            print(f"news: {name} returned nothing — official flags only")
    if (injuries is None or injuries.empty) and (lineups is None
                                                 or lineups.empty):
        return official
    print(f"news: {0 if injuries is None else len(injuries)} injuries, "
          f"{0 if lineups is None else len(lineups)} line-up hints")
    return availability_frame(official, injuries, lineups, gw, events)


def predict_components(pred_frame: pd.DataFrame, tg_future: pd.DataFrame,
                       players: pd.DataFrame,
                       avail: pd.DataFrame | None = None,
                       pens=None, *, cfg: Config) -> pd.DataFrame:
    """Every component prediction on one row per player-fixture.

    Assembled positionally (see the module docstring): each ``predict``
    returns one row per input row in input order, so ``.values`` lines up
    exactly while a merge on ``(code, season_idx, gw)`` would fan a double
    gameweek out.

    ``pens`` is the :class:`~gaffer.set_pieces.PenPriors` bundle, or ``None``
    for the pre-v6 behaviour: without it the penalty term is identically zero
    and this function returns exactly the frame it always did, plus a zero
    column.
    """
    pf = pred_frame.copy().reset_index(drop=True)
    pf["e_cards"] = pf.apply(card_penalty, axis=1)

    minutes = load_model("minutes")
    mp = minutes.predict(pf)
    # Two availability passes over one model run. The news pass is what the
    # advice is built on; the flags-only pass is gate N2's control, and
    # running the model twice to get it would be both slower and wrong — the
    # two sides have to differ by the availability layer alone.
    flags = players[["code", "status", "chance_of_playing"]]
    # v18b ruling 4: told, not read — the four switches the pass used to
    # take off the process-wide view come from the cfg this run was given.
    switches = dict(overrides=cfg.news_overrides,
                    start_floor=cfg.news_lineup_start_floor,
                    llm_serving=cfg.news_llm_classifier,
                    current_season=cfg.current_season)
    mp_flags = apply_availability(mp, flags, **switches)
    mp = apply_availability(mp, avail if avail is not None else flags,
                            **switches)

    keys = ["code", "season_idx", "gw", "opp_code"]
    carried = ["position", "team_code", "e_cards", "was_home",
               "kickoff_time", "pen_taker", "setpiece_taker"]
    comp = pf[keys + [c for c in carried if c in pf.columns]] \
        .reset_index(drop=True)
    for col in ["p_play", "p60"]:
        comp[col] = mp[col].values
    # Carried for the shadow log and dropped by components_frame's column
    # selection, so nothing downstream sees them.
    comp["e_min"] = mp["e_min"].values
    comp["p_play_flags"] = mp_flags["p_play"].values
    comp["e_min_flags"] = mp_flags["e_min"].values
    for name, cols in (("attacking", ["e_goals", "e_assists"]),
                       ("defcon", ["p_defcon"]),
                       ("saves", ["e_saves"]),
                       ("bonus", ["e_bonus"])):
        out = load_model(name).predict(pf)
        for col in cols:
            comp[col] = out[col].values

    # The fitted model itself, not only its predictions: the penalty term
    # reads Dixon-Coles' attack strengths off it at the bottom of this
    # function, and loading it twice would be two deserialisations of the
    # same file.
    team_model = load_model("team")
    tp = team_model.predict(tg_future)
    tp["opp_code"] = tg_future["opp_code"].values
    # Keep the model's own numbers before the market touches them: the
    # explainability page shows both sides of the blend and the weight that
    # was actually applied, and after blending there is no way back.
    tp["p_cs_model"] = tp["p_cs"].values
    tp["e_gc_model"] = tp["e_gc"].values
    # Blend the market in while tp is still one row per team-fixture: the
    # merge below is many-to-one, so blending after it would apply the same
    # correction once per player in the squad.
    if ODDS_AGAINST_COL in tg_future.columns:
        tp[ODDS_AGAINST_COL] = tg_future[ODDS_AGAINST_COL].values
    tp = blend_team_odds(tp, weight=odds_blend_weight())
    if ODDS_AGAINST_COL not in tp.columns:
        tp[ODDS_AGAINST_COL] = float("nan")
    tp["odds_weight"] = (tp[ODDS_AGAINST_COL].notna().astype(float)
                         * odds_blend_weight())
    tp = tp.rename(columns={"code": "team_code"})
    comp = comp.merge(tp, on=["team_code", "season_idx", "gw", "opp_code"],
                      how="left")
    comp["p_cs"] = comp["p_cs"].fillna(DEFAULT_P_CS)
    comp["e_gc"] = comp["e_gc"].fillna(DEFAULT_E_GC)
    # Set pieces last, and deliberately so. The term multiplies by p_play, so
    # it has to see the availability passes above; it reads the club's attack
    # strength, so it has to see the team model; and it folds into e_goals
    # rather than into ep, so it has to land before assemble_ep ever runs.
    # With no priors it is identically zero and this is a no-op.
    for line in pen_notices(comp, players, pens,
                            attack_multipliers(team_model)):
        print(line)
    return add_pen_ep(comp, players, pens, attack_multipliers(team_model))
