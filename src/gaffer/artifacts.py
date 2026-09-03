"""On-disk artifacts the local web UI reads.

``advise`` already computes everything in here; these functions only persist
it. Two files per run land under ``reports/``:

* ``components_gw{N}.parquet`` — one row per (player, fixture) with every
  expected-points component, so "why 6.8?" can be answered offline.
* ``solve_state_gw{N}.parquet`` + ``solve_state_gw{N}.json`` — the candidate
  pool with **raw** (untilted) expected points, prices and squad state, plus
  the league tilt recorded separately. A what-if re-solve rebuilds the exact
  MILP from these without retraining or refetching anything.

The tilt is deliberately *not* baked into the stored expected points. Chips
and every displayed points number use raw values (see ``advise.run_advise``),
and ``league_mode.tilt_ep`` reproduces the tilted pool on demand from ``lam``
and the saved ``cover`` fractions — so one file serves both, and neither can
drift from the other. ``league_eo`` is a *percent* kept for display; it is not
what the tilt reads (a state written before ``cover`` existed falls back to
``cover_from_eo(league_eo)``, which converts it).
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from gaffer.errors import GafferError

REPORTS = Path("reports")

COMPONENT_COLS = [
    "code", "element", "name", "position", "team_code", "team_name",
    "gw", "opp_code", "opp_name", "was_home", "kickoff_time",
    "p_play", "p60", "e_goals", "e_assists", "p_defcon", "e_saves",
    "e_bonus", "e_cards", "p_cs", "e_gc", "p_cs_model", "e_gc_model",
    "odds_e_goals_against", "odds_weight", "pen_taker", "setpiece_taker",
    "ep_minutes", "ep_goals", "ep_assists", "ep_cs", "ep_gc", "ep_saves",
    "ep_defcon", "ep_bonus", "ep_cards", "ep_pensave",
    # v6: the penalty-taker increment, already folded into ep_goals above.
    # Recorded separately because "why is he suddenly worth 0.4 more?" has no
    # other answer once the term is inside e_goals — and because gate P1's
    # audit reads it back off the file.
    "ep_pen_taker",
    "ep_uncalibrated", "cal_delta", "ep",
]

POOL_COLS = ["code", "name", "position", "team_code", "cost", "sell",
             "owned", "gw", "ep_raw"]

SNAPSHOT_PLAYER_COLS = [
    "code", "element", "name", "position", "team_id", "team_code",
    "now_cost", "status", "news", "chance_of_playing",
    "selected_by_percent", "form", "points_per_game", "ep_next",
    "price_change_percent", "price_change_calibrating",
    "penalties_order", "direct_freekicks_order",
    "corners_and_indirect_freekicks_order",
]

NUMERIC_SNAPSHOT_COLS = ["chance_of_playing", "penalties_order",
                         "direct_freekicks_order",
                         "corners_and_indirect_freekicks_order"]


def components_path(gw: int) -> Path:
    return REPORTS / f"components_gw{gw}.parquet"


def solve_state_paths(gw: int) -> tuple[Path, Path]:
    return (REPORTS / f"solve_state_gw{gw}.parquet",
            REPORTS / f"solve_state_gw{gw}.json")


def components_frame(comp: pd.DataFrame, scoring: dict, cal,
                     players: pd.DataFrame,
                     teams: pd.DataFrame) -> pd.DataFrame:
    """Per-fixture component breakdown, named and ready to persist.

    ``cal`` is the calibration model or ``None``; the difference it makes is
    stored as its own column rather than folded silently into ``ep``.
    """
    from gaffer.models.assemble import (apply_calibration, assemble_ep,
                                        ep_breakdown)

    assembled = assemble_ep(comp, scoring)
    out = ep_breakdown(assembled, scoring)
    out["ep_uncalibrated"] = out["ep"]
    out["ep"] = apply_calibration(assembled, cal)["ep"].values
    out["cal_delta"] = out["ep"] - out["ep_uncalibrated"]
    name_of = dict(zip(players["code"], players["name"]))
    element_of = dict(zip(players["code"], players["element"]))
    team_name = dict(zip(teams["code"], teams["name"]))
    out["name"] = out["code"].map(name_of)
    out["element"] = out["code"].map(element_of)
    out["team_name"] = out["team_code"].map(team_name)
    out["opp_name"] = out["opp_code"].map(team_name)
    for col in COMPONENT_COLS:
        if col not in out.columns:
            out[col] = float("nan")
    return out[COMPONENT_COLS].reset_index(drop=True)


def prev_components_path(gw: int) -> Path:
    """The single retained predecessor of ``gw``'s component breakdown.

    One slot, never rotated. The question it answers is "what did tonight's
    retrain change", and a third file answers no question anybody asked while
    costing a directory that grows all season.
    """
    return REPORTS / f"components_gw{gw}_prev.parquet"


def save_components(frame: pd.DataFrame, gw: int) -> Path:
    """Bank the component breakdown, keeping the previous one beside it.

    The copy is instrumentation and is treated as such: it is taken before the
    overwrite, it is wrapped, and its failure is a printed line rather than an
    exception. Banking the *current* components is this function's actual job
    — an advise run that died because a diff could not be preserved would be
    a far worse trade than a Thursday with no diff.
    """
    REPORTS.mkdir(exist_ok=True)
    path = components_path(gw)
    if path.exists():
        try:
            shutil.copyfile(path, prev_components_path(gw))
        except Exception as exc:  # noqa: BLE001 — a diff is never worth a run
            print(f"components: no predecessor kept for GW{gw} ({exc})")
    frame.to_parquet(path, index=False)
    return path


def load_components(gw: int) -> pd.DataFrame:
    path = components_path(gw)
    if not path.exists():
        raise GafferError(
            f"no component breakdown for GW{gw} — run `gaffer advise` first")
    return pd.read_parquet(path)


@dataclass
class SolveState:
    """Everything the MILP needs to be re-run without models or network."""

    gw: int
    gws: list[int]
    deadline: str
    generated_at: str
    mode: str                        # "weekly" | "initial_squad"
    bank: int                        # 0.1m units
    free_transfers: int
    owned_codes: list[int]
    lam: float                       # league tilt strength, 0.0 when neutral
    league_eo: dict[int, float]      # code -> rival EO percent
    avail_by_gw: dict[int, list[str]]
    opt: dict                        # decay/bench_weight/.../horizon
    pool: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=POOL_COLS))
    # The threat-weighted cover *fraction* advise actually tilted on, in [0,1]
    # per code. ``None`` means the state predates the field: a re-solve then
    # falls back to ``cover_from_eo(league_eo)``, which is the same table under
    # equal weights and no armbands. Appended last and defaulted so every
    # existing keyword construction still works.
    cover: dict[int, float] | None = None


def pool_rows(pool: pd.DataFrame, players: pd.DataFrame,
              owned_codes: list[int], ep_by: dict,
              gws: list[int]) -> pd.DataFrame:
    """MILP pool -> one row per (candidate, gameweek) with **raw** EP."""
    name_of = dict(zip(players["code"], players["name"]))
    owned = {int(c) for c in owned_codes}
    rows = []
    for r in pool.itertuples():
        code = int(r.code)
        for g in gws:
            rows.append({"code": code,
                         "name": name_of.get(code, str(code)),
                         "position": str(r.position),
                         "team_code": int(r.team_code),
                         "cost": int(r.cost), "sell": int(r.sell),
                         "owned": code in owned, "gw": int(g),
                         "ep_raw": float(ep_by.get((code, int(g)), 0.0))})
    return pd.DataFrame(rows, columns=POOL_COLS)


def save_solve_state(state: SolveState) -> tuple[Path, Path]:
    """Pool to parquet, everything scalar to JSON beside it.

    JSON object keys are strings by definition, so ``league_eo`` and
    ``avail_by_gw`` are written stringly and converted back on load — a
    caller looking up ``league_eo[code]`` with an int must never silently
    miss.
    """
    REPORTS.mkdir(exist_ok=True)
    parquet, meta = solve_state_paths(state.gw)
    state.pool.to_parquet(parquet, index=False)
    meta.write_text(json.dumps({
        "gw": state.gw, "gws": [int(g) for g in state.gws],
        "deadline": state.deadline, "generated_at": state.generated_at,
        "mode": state.mode, "bank": int(state.bank),
        "free_transfers": int(state.free_transfers),
        "owned_codes": [int(c) for c in state.owned_codes],
        "lam": float(state.lam),
        "league_eo": {str(k): float(v) for k, v in state.league_eo.items()},
        "cover": (None if state.cover is None
                  else {str(k): float(v) for k, v in state.cover.items()}),
        "avail_by_gw": {str(g): list(c)
                        for g, c in state.avail_by_gw.items()},
        "opt": dict(state.opt),
    }, indent=1))
    # v12 W5 §6.4. The same pool, frozen and dated, so Review can read the EP
    # table that stood at the deadline rather than the one the last re-run
    # left behind. Wrapped and swallowed: banking the solve state is this
    # function's job, and a run that died because a snapshot could not be
    # written would be a far worse trade (``save_components``' reasoning).
    #
    # The import is local, not top-of-module: ``artifacts`` is imported early
    # by ``config``'s own callers and a module-level import here is a cycle
    # waiting for a refactor. ``_availability_frame`` sets the precedent.
    from gaffer.config import serving_config
    try:
        save_projection_snapshot(
            state.pool, state.gw, state.generated_at,
            str(getattr(serving_config(), "current_season", "") or ""))
    except Exception as exc:  # noqa: BLE001 — a snapshot is never worth a run
        print(f"projections: no snapshot kept for GW{state.gw} ({exc})")
    return parquet, meta


def load_solve_state(gw: int) -> SolveState:
    parquet, meta = solve_state_paths(gw)
    if not meta.exists() or not parquet.exists():
        raise GafferError(
            f"no saved solve state for GW{gw} — run `gaffer advise` first")
    raw = json.loads(meta.read_text())
    return SolveState(
        gw=int(raw["gw"]), gws=[int(g) for g in raw["gws"]],
        deadline=str(raw["deadline"]),
        generated_at=str(raw["generated_at"]), mode=str(raw["mode"]),
        bank=int(raw["bank"]), free_transfers=int(raw["free_transfers"]),
        owned_codes=[int(c) for c in raw["owned_codes"]],
        lam=float(raw["lam"]),
        league_eo={int(k): float(v) for k, v in raw["league_eo"].items()},
        avail_by_gw={int(g): list(c)
                     for g, c in raw["avail_by_gw"].items()},
        opt=dict(raw["opt"]), pool=pd.read_parquet(parquet),
        cover=(None if raw.get("cover") is None
               else {int(k): float(v) for k, v in raw["cover"].items()}))


def latest_gw() -> int | None:
    """Newest gameweek with a saved solve state, or ``None`` if never run."""
    gws = []
    for path in REPORTS.glob("solve_state_gw*.json"):
        stem = path.stem.removeprefix("solve_state_gw")
        if stem.isdigit():
            gws.append(int(stem))
    return max(gws) if gws else None


def raw_ep_by(state: SolveState) -> dict[tuple[int, int], float]:
    """``{(code, gw): raw expected points}`` — the untilted numbers."""
    return {(int(r.code), int(r.gw)): float(r.ep_raw)
            for r in state.pool.itertuples()}


def milp_pool(state: SolveState, ep_by: dict[tuple[int, int], float],
              gws: list[int]) -> pd.DataFrame:
    """The frame ``optimize.milp.solve_plan`` expects, ep as ``{gw: pts}``."""
    one = state.pool.drop_duplicates("code")
    return pd.DataFrame({
        "code": [int(c) for c in one["code"]],
        "position": [str(p) for p in one["position"]],
        "team_code": [int(t) for t in one["team_code"]],
        "cost": [int(c) for c in one["cost"]],
        "sell": [int(s) for s in one["sell"]],
        "ep": [{int(g): float(ep_by.get((int(c), int(g)), 0.0)) for g in gws}
               for c in one["code"]],
    })


OPT_REQUIRED_KEYS = ("decay", "bench_weight", "vice_weight", "ft_value",
                     "itb_value", "hit_cost")
"""``SolveState.opt`` keys every saved state has ever carried.

A state written by an older build is missing everything else, so the rest are
read with defaults; these six are read directly and raise ``KeyError``, which
is the routers' signal to say "re-run `gaffer advise`" rather than 500.
"""


def solve_kw_from_state(state: SolveState) -> dict:
    """The ``solve_plan`` keyword bundle a saved state re-solves under.

    ``opt`` is JSON on disk, so the free-transfer lambda lookup cannot live in
    it — but the boolean saying whether it was on can, and rebuilding the
    lookup from the shipped asset here is what stops a What-If baseline being
    priced differently from the advice it is supposed to be a baseline for.
    """
    kw = {k: state.opt[k] for k in OPT_REQUIRED_KEYS}
    if "ft_use_penalty" in state.opt:
        kw["ft_use_penalty"] = float(state.opt["ft_use_penalty"])
    if state.opt.get("bench_curve") is not None:
        kw["bench_curve"] = [float(w) for w in state.opt["bench_curve"]]
    if state.opt.get("decision_priors"):
        from gaffer.assets import load_decision_priors
        from gaffer.optimize.ft_value import lambda_from_priors
        kw["ft_lambda"] = lambda_from_priors(load_decision_priors())
    return kw


def load_snapshot(rel: str) -> pd.DataFrame:
    """A bootstrap snapshot written by :func:`save_snapshots`."""
    from gaffer.data import store

    if not store.exists(rel):
        raise GafferError(
            f"data/{rel} has not been written yet — run `gaffer advise` first")
    return store.load(rel)


def upcoming_gw(now: pd.Timestamp | None = None) -> int | None:
    """The gameweek whose deadline has not passed, from the events snapshot.

    Read from disk rather than the API so a stale-advice banner still renders
    with no network. ``None`` means every deadline in the snapshot is behind
    us — an end-of-season or a very old snapshot.
    """
    events = load_snapshot("live/events.parquet")
    ts = pd.Timestamp.now(tz="UTC") if now is None else now
    deadlines = pd.to_datetime(events["deadline_time"], utc=True,
                               format="mixed")
    future = events[deadlines > ts]
    return int(future["gw"].min()) if not future.empty else None


def ingested_through(season_idx: int | None = None) -> int | None:
    """Newest gameweek present in ``data/live/player_gw.parquet``.

    The one place anything asks "how much of this season has the model
    actually seen?". ``refresh_live`` drops every gameweek FPL has not marked
    ``data_checked``, so running ``gaffer advise`` on the evening of GW1
    leaves this at ``None`` — the model is predicting GW2 off last season
    alone, and every surface that shows advice needs to say so.

    ``season_idx`` restricts the answer to one season; the default takes the
    newest season in the file, which is the current one (``refresh_live``
    rewrites the whole table from today's bootstrap).
    """
    from gaffer.data import store

    if not store.exists("live/player_gw.parquet"):
        return None
    df = store.load("live/player_gw.parquet")
    if df.empty:
        return None
    if "season_idx" in df.columns:
        want = df["season_idx"].max() if season_idx is None else season_idx
        df = df[df["season_idx"] == want]
    gws = pd.to_numeric(df["gw"], errors="coerce").dropna()
    return int(gws.max()) if not gws.empty else None


DATA_WARNING_TAIL = ("FPL usually finalizes it the morning after the last "
                     "match; re-run gaffer advise after that")


def data_warning(upcoming: int | None, through: int | None) -> str | None:
    """The one warning string, shared by the CLI, the report and the API.

    ``None`` when the model has results for every gameweek before ``upcoming``
    — including the start of the season, when there is nothing to be missing.
    """
    if upcoming is None or upcoming <= 1:
        return None
    last_played = upcoming - 1
    if through is not None and through >= last_played:
        return None
    start = (through or 0) + 1
    span = f"GW{start}" if start >= last_played \
        else f"GW{start}-GW{last_played}"
    return f"model has no data for {span} — {DATA_WARNING_TAIL}"


def load_advice(gw: int) -> dict:
    """The advice payload ``run_advise`` wrote for ``gw``."""
    path = REPORTS / f"gw{gw}-advice.json"
    if not path.exists():
        raise GafferError(
            f"no advice for GW{gw} — run `gaffer advise` first")
    return json.loads(path.read_text())


def save_snapshots(players: pd.DataFrame, teams: pd.DataFrame,
                   events: pd.DataFrame, fixtures: pd.DataFrame) -> None:
    """Bootstrap tables the web layer reads when the FPL API is unreachable.

    ``data/live/fixtures.parquet`` holds only *finished* matches (it feeds Elo
    and the team model), so the fixture ticker needs its own copy of the whole
    list — hence ``fixtures_all``.
    """
    from gaffer.data import store

    snap = players[SNAPSHOT_PLAYER_COLS].copy()
    for col in NUMERIC_SNAPSHOT_COLS:
        snap[col] = pd.to_numeric(snap[col], errors="coerce")
    store.save(snap, "live/players.parquet")
    store.save(teams, "live/teams.parquet")
    store.save(events, "live/events.parquet")
    store.save(fixtures, "live/fixtures_all.parquet")


AVAILABILITY_COLS = ["code", "status", "chance_of_playing", "injury_type",
                     "expected_return_gw", "p_start_hint", "absence_damp",
                     "llm_verdict", "llm_confidence", "source", "fetched_at",
                     "override", "override_p_play", "override_e_min",
                     "override_note"]
"""The availability frame's columns, in the order
:func:`gaffer.data.news.normalize.availability_frame` produces them.

A flags-only run (news disabled, every source down) produces the first three
and nothing else, so the missing five are filled with nulls on the way to
disk: the news endpoint reads one shape whatever the week did.

v8a adds three. ``absence_damp`` is the notable-absence factor a predicted
line-up implies for a player it silently left out; ``llm_verdict`` and
``llm_confidence`` are the presser classifier's reading of the free text.
All three are nullable and all three are logged whether or not they are
served, because the point of banking them is that a future season can train
on what the news said (spec §4).

v8e adds four. ``override`` marks a player the *user* pinned, and the three
beside it carry what he pinned and why. They are restated here rather than
imported from :mod:`gaffer.overrides`, which imports this module;
``tests/test_v8e_degradation.py`` pins the two lists against each other so the
duplication cannot drift.
"""

OVERRIDE_COLS = ["override", "override_p_play", "override_e_min",
                 "override_note"]
"""The v8e tail of :data:`AVAILABILITY_COLS`, named so callers can ask for
just that block without slicing a list by index."""


def availability_path(gw: int) -> Path:
    return REPORTS / f"availability_gw{gw}.parquet"


def save_availability(avail, gw: int) -> Path | None:
    """Snapshot the availability frame this run predicted on.

    The only record of *why* the news layer moved a player: the shadow log
    banks what changed, and this banks the evidence that changed it. Nothing
    else reads the frame after ``predict_components`` consumes it.

    Never raises and returns ``None`` when there is nothing worth keeping —
    it is instrumentation for a UI panel, and an advise run that died of its
    own snapshot would be a much worse trade than a hidden panel.
    """
    try:
        if avail is None or len(avail) == 0:
            return None
        if "code" not in avail.columns:
            return None
        out = avail.copy()
        # v8e: the pins this run predicted under, banked with the evidence.
        # Gated on the same key the availability pass reads, so "no read, no
        # marker" holds for the artifact too. Idempotent, so a frame that
        # already carries them is not re-read.
        from gaffer.config import serving_config
        from gaffer.overrides import attach_overrides
        if serving_config().news_overrides:
            out = attach_overrides(out)
        for col in AVAILABILITY_COLS:
            if col not in out.columns:
                out[col] = None
        out = out[AVAILABILITY_COLS].copy()
        # Parquet wants a settled dtype per column and an all-None object
        # column has none. Strings become nullable strings and the three
        # numeric columns become floats, so a flags-only week and a
        # news-heavy one write the same schema.
        for col in ("status", "injury_type", "llm_verdict", "source",
                    "fetched_at", "override_note"):
            out[col] = out[col].astype("object").where(
                out[col].notna(), None).astype("string")
        for col in ("chance_of_playing", "expected_return_gw", "p_start_hint",
                    "absence_damp", "llm_confidence", "override_p_play",
                    "override_e_min"):
            out[col] = pd.to_numeric(out[col], errors="coerce")
        out["override"] = out["override"].astype("object").where(
            out["override"].notna(), False).astype(bool)
        out["code"] = pd.to_numeric(out["code"], errors="coerce").astype(
            "int64")
        REPORTS.mkdir(exist_ok=True)
        path = availability_path(gw)
        out.to_parquet(path, index=False)
        return path
    except Exception as exc:  # noqa: BLE001 — instrumentation never blocks
        print(f"availability snapshot not written: {exc}")
        return None


def load_availability(gw: int) -> pd.DataFrame | None:
    """The snapshot for ``gw``, or ``None``.

    ``None`` rather than a domain error, unlike :func:`load_components`: an
    absent snapshot means the panel hides, and there is nothing for the user
    to go and run.
    """
    path = availability_path(gw)
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        print(f"availability snapshot unreadable: {exc}")
        return None


ADVICE_HISTORY = REPORTS / "advice_history"

ADVICE_HISTORY_KEEP = 20
"""Runs kept on disk.

Enough to see a week's worth of re-runs and the two or three weeks before it,
few enough that the directory never becomes an archive nobody prunes. The diff
only ever reads the newest two of one gameweek.
"""


def _history_stamp(path: Path) -> str:
    """The ISO timestamp out of ``gw{N}-{stamp}.json``.

    Sorting on this rather than on mtime: two runs a second apart can share an
    mtime on a coarse filesystem, and a copied ``reports/`` directory has
    mtimes that say nothing at all. The stamp is written by the writer and
    sorts lexicographically because ISO-8601 does.
    """
    _, _, stamp = path.stem.partition("-")
    return stamp


def advice_history_files(gw: int | None = None) -> list[Path]:
    """Every banked run, oldest first; ``gw`` filters to one gameweek."""
    if not ADVICE_HISTORY.is_dir():
        return []
    files = [p for p in ADVICE_HISTORY.glob("gw*-*.json") if p.is_file()]
    if gw is not None:
        files = [p for p in files if p.name.startswith(f"gw{int(gw)}-")]
    return sorted(files, key=_history_stamp)


def prune_advice_history(keep: int = ADVICE_HISTORY_KEEP) -> int:
    """Drop everything but the newest ``keep`` runs. Returns how many went."""
    files = advice_history_files()
    doomed = files[:-keep] if len(files) > keep else []
    for path in doomed:
        path.unlink(missing_ok=True)
    return len(doomed)


def append_advice_history(payload: dict, gw: int,
                          now: datetime | None = None) -> Path | None:
    """Bank this run's advice payload and prune the log.

    One file per *run*, not per gameweek: re-running on Friday morning after
    the Thursday press conferences is the case the "since last run" strip
    exists for, and overwriting would destroy exactly the comparison the user
    wants. Pruned on write so nothing has to remember to.

    Never raises, for the same reason :func:`save_availability` does not.
    """
    try:
        ADVICE_HISTORY.mkdir(parents=True, exist_ok=True)
        stamp = (now or datetime.now(timezone.utc)).isoformat(
            timespec="seconds")
        path = ADVICE_HISTORY / f"gw{int(gw)}-{stamp}.json"
        path.write_text(json.dumps(payload, indent=1, default=str))
        prune_advice_history()
        return path
    except Exception as exc:  # noqa: BLE001 — instrumentation never blocks
        print(f"advice history not written: {exc}")
        return None


def _players_by_code(payload: dict, key: str) -> dict[int, dict]:
    rows = payload.get(key) or []
    return {int(r["code"]): {"code": int(r["code"]),
                             "name": str(r.get("name", r["code"]))}
            for r in rows if isinstance(r, dict) and "code" in r}


def _recommended_chip(payload: dict) -> str | None:
    """The chip this run said to play now, or ``None``.

    Reads ``play_now`` — the flag ``run_advise`` sets by comparing each row's
    gain against its own θ threshold — rather than re-deriving it, so the diff
    cannot disagree with the report about what was recommended.
    """
    for row in payload.get("chip_table") or []:
        if isinstance(row, dict) and row.get("play_now"):
            return str(row.get("chip"))
    return None


def diff_advice(previous: dict, current: dict) -> dict:
    """What changed between two runs of the same gameweek.

    Structural, not textual: the UI renders "Wirtz in place of Isak", and a
    string diff of two JSON files could never say that. Everything is
    tolerant of a missing key, because the log outlives the shape of the
    payload it stores.
    """
    out: dict = {}
    for key in ("buys", "sells"):
        before = _players_by_code(previous, key)
        after = _players_by_code(current, key)
        out[f"{key}_added"] = [after[c] for c in sorted(set(after) - set(before))]
        out[f"{key}_dropped"] = [before[c]
                                 for c in sorted(set(before) - set(after))]
    prev_cap = previous.get("captain") or {}
    curr_cap = current.get("captain") or {}
    changed_cap = (prev_cap.get("code") != curr_cap.get("code")
                   and (prev_cap or curr_cap))
    out["captain_from"] = dict(prev_cap) if changed_cap and prev_cap else None
    out["captain_to"] = dict(curr_cap) if changed_cap and curr_cap else None
    prev_chip = _recommended_chip(previous)
    curr_chip = _recommended_chip(current)
    out["chip_from"] = prev_chip if prev_chip != curr_chip else None
    out["chip_to"] = curr_chip if prev_chip != curr_chip else None
    out["expected_pts_delta"] = round(
        float(current.get("expected_pts") or 0.0)
        - float(previous.get("expected_pts") or 0.0), 2)
    out["changed"] = bool(out["buys_added"] or out["buys_dropped"]
                          or out["sells_added"] or out["sells_dropped"]
                          or out["captain_to"] or out["chip_to"]
                          or out["chip_from"]
                          or out["expected_pts_delta"] != 0.0)
    return out


EP_MOVER_THRESHOLD = 0.5
"""Points of expected-points change worth naming.

Half a point is roughly the gap between a rotation risk and a nailed-on
starter in one gameweek, and it is well above the noise a retrain on one extra
gameweek of data produces for a settled player. A tenth would list the whole
pool, which is a diff nobody reads.
"""

EP_MOVERS_KEEP = 20
"""How many movers the payload carries. The card names three; the rest are
there so a future panel can list them without a second endpoint."""


def _first_gw_ep(frame: pd.DataFrame) -> dict[int, float] | None:
    """``{code: EP}`` for a frame's own earliest gameweek, or ``None``.

    Its *own* earliest, not a shared one (plan A9): the two frames being
    compared may have been written either side of a horizon roll, and the week
    being decided is the comparable thing in both. EP is summed across that
    week's fixtures, so a double gameweek is one number — the forecast was for
    the week.
    """
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    if not {"code", "gw", "ep"}.issubset(frame.columns):
        return None
    gws = pd.to_numeric(frame["gw"], errors="coerce")
    if gws.dropna().empty:
        return None
    rows = frame[gws == gws.min()]
    totals = (pd.DataFrame({
        "code": pd.to_numeric(rows["code"], errors="coerce").astype("int64"),
        "ep": pd.to_numeric(rows["ep"], errors="coerce").fillna(0.0)})
        .groupby("code", as_index=False)["ep"].sum())
    return {int(r.code): float(r.ep) for r in totals.itertuples()}


def ep_movers(gw: int, threshold: float = EP_MOVER_THRESHOLD) -> list | None:
    """Players whose expected points moved between the two newest breakdowns.

    ``None`` — never ``[]`` — when there is no predecessor, or when either
    file is unreadable. The distinction is the whole point: "we have not
    retrained since you last looked" and "the retrain changed nothing" are
    different sentences, and a payload that could not tell them apart would
    make the first run after this cycle merges claim a quiet retrain it has no
    evidence for.

    A player present in only one frame is **not** a mover. He did not move, he
    appeared (or left the pool), and reporting a new entrant as "+8.0 EP"
    would be the diff's most eye-catching and least true row.
    """
    prev_path = prev_components_path(int(gw))
    if not prev_path.exists():
        return None
    try:
        before = _first_gw_ep(pd.read_parquet(prev_path))
        after = _first_gw_ep(load_components(int(gw)))
    except Exception as exc:  # noqa: BLE001 — a strip is never worth a 500
        print(f"ep movers: unreadable breakdown for GW{gw} ({exc})")
        return None
    if not before or not after:
        return None

    names: dict[int, str] = {}
    try:
        comp = load_components(int(gw))
        names = {int(r.code): str(r.name) for r in comp.itertuples()
                 if getattr(r, "name", None) is not None}
    except Exception:  # noqa: BLE001 — a code is a usable label
        pass

    rows = []
    for code in sorted(set(before) & set(after)):
        delta = after[code] - before[code]
        if abs(delta) < float(threshold):
            continue
        rows.append({"code": code, "name": names.get(code, str(code)),
                     "ep_prev": round(before[code], 2),
                     "ep_now": round(after[code], 2),
                     "delta": round(delta, 2)})
    rows.sort(key=lambda r: abs(r["delta"]), reverse=True)
    return rows[:EP_MOVERS_KEEP]


PROJECTIONS = REPORTS / "projections"
"""Frozen copies of the EP table each advise run solved over (v12 W5 §6.4).

``solve_state_gw{N}.parquet`` is one slot per gameweek and advise runs several
times a week, so the file that survives to Tuesday is the *last* run — which
may be the one written after kickoff. The advice payload has not had that
problem since v9c (``ADVICE_HISTORY`` keeps 20 and
``journal.latest_run_per_gw`` picks the newest run written before the
deadline); this directory gives the EP table the same treatment under the same
rule.

Kept for the season and never pruned here. A snapshot is the pool — roughly
700 codes times the horizon times nine columns, 40-80 KB — so four runs a week
across a season is about 6-12 MB in a gitignored directory. Deciding which one
Review will want, before Review has ever wanted one, is not this cycle's call.
"""


@dataclass(frozen=True)
class ProjectionSnapshot:
    path: Path
    season: str
    gw: int
    stamp: str
    """The writer's own UTC stamp, ``%Y%m%dT%H%M%SZ``. Sorts
    lexicographically, which is why it is the sort key rather than mtime: two
    runs a second apart can share an mtime, and a copied ``reports/`` has
    mtimes that say nothing at all (``_history_stamp``'s reasoning)."""
    post_deadline: bool = False
    """Set only by :func:`latest_projection_before`, and only when *every*
    snapshot for the gameweek was written after the deadline."""


def _stamp_utc(when) -> str | None:
    """An ISO instant as a filename stamp, or ``None`` if it is not one."""
    try:
        at = pd.Timestamp(when)
    except (TypeError, ValueError):
        return None
    if at is pd.NaT or at != at:
        return None
    at = at.tz_localize("UTC") if at.tzinfo is None else at.tz_convert("UTC")
    return at.strftime("%Y%m%dT%H%M%SZ")


def projection_path(season: str, gw: int, stamp: str) -> Path:
    return PROJECTIONS / f"{season}-gw{int(gw)}-{stamp}.parquet"


def save_projection_snapshot(pool: "pd.DataFrame", gw: int, generated_at,
                             season: str) -> Path | None:
    """Freeze ``pool`` under ``season`` and ``gw``. Never raises.

    ``None`` — and a printed line — rather than an exception on every failure
    mode, including an empty season. A snapshot filed under the wrong season
    is worse than no snapshot: the reader selects by glob, and a season-less
    name would be read back next August as this August's projections.
    """
    if not str(season or "").strip():
        print("projections: no current_season — no snapshot written for "
              f"GW{int(gw)}")
        return None
    # Two chances at a stamp and then give up: the run's own instant, then
    # now. ``or`` on the pair is not enough on its own — if both came back
    # ``None`` the f-string below would file the snapshot under the literal
    # name "None" and every later run would overwrite it.
    stamp = _stamp_utc(generated_at) or _stamp_utc(datetime.now(timezone.utc))
    if not stamp:
        print(f"projections: no usable timestamp — no snapshot written for "
              f"GW{int(gw)}")
        return None
    try:
        path = projection_path(str(season), int(gw), str(stamp))
        # ``io.atomic_path`` rather than a bare ``to_parquet``: a reader
        # globbing this directory must never meet a half-written file, and
        # two advise runs a second apart are two writers (``io``'s pid temp).
        # Not ``atomic_save``, which names a path relative to the data store
        # and this one is under ``reports/``.
        from gaffer.io import atomic_path

        with atomic_path(path) as tmp:
            pool.to_parquet(tmp, index=False)
        return path
    except Exception as exc:  # noqa: BLE001 — instrumentation never gates a run
        print(f"projections: no snapshot kept for GW{int(gw)} ({exc})")
        return None


def projection_snapshots(season: str, gw: int) -> list[ProjectionSnapshot]:
    """Every frozen EP table for one ``(season, gw)``, oldest first.

    ``season`` is a required argument and is matched exactly. Codes, not
    element ids, are what the pool is keyed on — but a directory selected by a
    glob is exactly the shape of the cross-season read that element-id remaps
    make dangerous, so the season is in the name and in the filter.
    """
    if not PROJECTIONS.is_dir():
        return []
    prefix = f"{season}-gw{int(gw)}-"
    out = []
    for path in PROJECTIONS.glob(f"{prefix}*.parquet"):
        if not path.is_file():
            continue
        out.append(ProjectionSnapshot(path=path, season=str(season),
                                      gw=int(gw),
                                      stamp=path.stem.rsplit("-", 1)[1]))
    return sorted(out, key=lambda s: s.stamp)


def latest_projection_before(season: str, gw: int,
                             deadline) -> ProjectionSnapshot | None:
    """The newest snapshot written before ``deadline``, or the newest at all.

    ``journal.latest_run_per_gw``'s rule applied to the EP table: a run banked
    after kickoff has seen the team news, and scoring a decision against
    projections that saw it flatters the model with information nobody had. So
    the newest *in-time* snapshot wins, and when every one of them is late the
    newest is returned with ``post_deadline`` set — a flagged comparison is
    worth more than a missing row as long as it cannot pass itself off as
    foresight.

    An unparseable deadline takes the same late branch rather than guessing.
    """
    snaps = projection_snapshots(season, gw)
    if not snaps:
        return None
    cutoff = _stamp_utc(deadline)
    if cutoff is not None:
        in_time = [s for s in snaps if s.stamp < cutoff]
        if in_time:
            return in_time[-1]
    return ProjectionSnapshot(path=snaps[-1].path, season=snaps[-1].season,
                              gw=snaps[-1].gw, stamp=snaps[-1].stamp,
                              post_deadline=True)
