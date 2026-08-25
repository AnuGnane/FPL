import random

import pandas as pd
from gaffer.models.train import (CALIBRATION_HOLDOUT_GWS,
                                 CALIBRATION_MIN_SLOTS, bonus_season_floor,
                                 evaluate_predictions, fit_calibration,
                                 train_all)
from gaffer.assets import load_bootstrap_sample
from gaffer.data.bootstrap import scoring_table
from gaffer.features.engineer import ROTATION_FEATURES
from gaffer.models.attacking import ATTACK_FEATURES
from gaffer.models.components import (BONUS_FEATURES, DEFCON_FEATURES,
                                      SAVES_FEATURES)
from gaffer.models.team import TEAM_FEATURES
from gaffer.models.train import MINUTES_FEATURES


def _frame(rows_by_season: dict[int, int], minutes: int = 90) -> pd.DataFrame:
    """Appearance rows per season_idx."""
    return pd.DataFrame([{"season_idx": s, "minutes": minutes}
                         for s, n in rows_by_season.items() for _ in range(n)])


def test_bonus_floor_reaches_back_a_season_when_the_newest_is_thin():
    # A brand-new season with one gameweek played cannot train a bonus model
    # on its own; the floor drops to include the season before it.
    df = _frame({3: 5000, 4: 100})
    assert bonus_season_floor(df) == 3


def test_bonus_floor_stays_on_the_newest_season_once_it_is_deep_enough():
    df = _frame({3: 5000, 4: 3000})
    assert bonus_season_floor(df) == 4


def test_bonus_floor_falls_back_to_the_oldest_season_on_a_tiny_frame():
    # Nothing clears the threshold — use everything rather than crash.
    df = _frame({1: 50, 2: 50})
    assert bonus_season_floor(df) == 1


def test_bonus_floor_counts_only_appearances():
    # 5000 rows in the newest season, but nobody played: they teach the bonus
    # model nothing, so the floor must still reach back.
    df = pd.concat([_frame({3: 5000}), _frame({4: 5000}, minutes=0)])
    assert bonus_season_floor(df) == 3


def test_minutes_features_include_the_rotation_signals():
    """Gated in on a last-10-slot holdout: p_play log-loss 0.27703 ->
    0.27322, p60 0.26025 -> 0.25627, with mae_starters and the 60-minute
    bias both improving downstream. The rolling ``starts_r*`` means alone
    read a benching in the opener as a rounding error."""
    for col in ROTATION_FEATURES:
        assert col in MINUTES_FEATURES


def test_evaluate_beats_worse_baseline():
    truth = pd.DataFrame({
        "code": [1, 2, 3, 4], "gw": [10] * 4,
        "total_points": [2.0, 6.0, 12.0, 0.0],
        "minutes": [90, 90, 90, 0],
    })
    good = pd.DataFrame({"code": [1, 2, 3, 4], "gw": [10] * 4,
                         "ep": [2.5, 5.0, 10.0, 0.5]})
    bad = pd.DataFrame({"code": [1, 2, 3, 4], "gw": [10] * 4,
                        "ep": [8.0, 1.0, 2.0, 6.0]})
    m_good = evaluate_predictions(good, truth)
    m_bad = evaluate_predictions(bad, truth)
    assert m_good["mae_starters"] < m_bad["mae_starters"]
    assert m_good["captain_pts"] >= m_bad["captain_pts"]


POSITIONS = ["GKP", "DEF", "MID", "FWD"]

_PLAYER_FEATURES = sorted(set(MINUTES_FEATURES) | set(ATTACK_FEATURES)
                          | set(DEFCON_FEATURES) | set(SAVES_FEATURES)
                          | set(BONUS_FEATURES))


def _player_frame(seasons=(0, 1), gws=8, players=24) -> pd.DataFrame:
    """Synthetic player-gameweek frame with every column train_all touches.

    Values are deterministic-random: the models only have to *fit*, not be
    any good, but each classifier needs both classes present.
    """
    rng = random.Random(11)
    rows = []
    for season in seasons:
        for gw in range(1, gws + 1):
            for p in range(players):
                pos = POSITIONS[p % 4]
                played = (p + gw) % 5 != 0
                minutes = rng.choice([60, 75, 90]) if played else 0
                row = {
                    "code": 1000 + p,
                    "element": 1000 + p,
                    "season_idx": season,
                    "gw": gw,
                    "position": pos,
                    "team_code": p % 6,
                    "minutes": minutes,
                    "goals": rng.choice([0, 0, 0, 1]) if played else 0,
                    "assists": rng.choice([0, 0, 0, 1]) if played else 0,
                    "saves": rng.randint(0, 5) if played and pos == "GKP" else 0,
                    "bonus": rng.choice([0, 0, 1, 3]) if played else 0,
                    "tackles": float(rng.randint(0, 8)),
                    "cbi": float(rng.randint(0, 9)),
                    "recoveries": float(rng.randint(0, 10)),
                    "yc_r38": 0.1,
                    "rc_r38": 0.01,
                    "total_points": rng.randint(0, 12) if played else 0,
                }
                for col in _PLAYER_FEATURES:
                    row.setdefault(col, rng.random() * 3)
                row["home"] = (p + gw) % 2
                row["minutes"] = minutes
                rows.append(row)
    return pd.DataFrame(rows)


def _team_frame(seasons=(0, 1), gws=8, teams=6) -> pd.DataFrame:
    rng = random.Random(23)
    rows = []
    for season in seasons:
        for gw in range(1, gws + 1):
            for t in range(teams):
                row = {"season_idx": season, "gw": gw, "code": t,
                       "opp_code": (t + 1) % teams,
                       "cs": (t + gw) % 2, "ga": rng.randint(0, 3)}
                for col in TEAM_FEATURES:
                    row.setdefault(col, rng.random() * 2)
                row["home"] = (t + gw) % 2
                rows.append(row)
    return pd.DataFrame(rows)


def test_train_all_fits_calibration_out_of_sample():
    models = train_all(_player_frame(), _team_frame(), save=False)
    assert "calibration" in models
    # A tiny synthetic holdout is below CalibrationModel.MIN_ROWS, so the
    # model is very likely unfitted (identity); the contract under test is
    # that it is present and that apply() works.
    frame = pd.DataFrame({"ep": [2.0, 4.0], "position": ["MID", "FWD"],
                          "p60": [1.0, 0.8]})
    out = models["calibration"].apply(frame)
    assert list(out.index) == [0, 1]
    assert out["ep"].notna().all()


def test_fit_calibration_measures_the_delta_on_60_minute_rows_only():
    """The delta is the *conditional* bias E[actual - ep | 60+ minutes].

    ``apply`` already multiplies by ``p60``, so mixing cameo rows into the
    fit would estimate the unconditional bias and double-count the gate.
    Here every 60+ row scores 10 while every cameo scores -100: a fit that
    let cameos in could not come out positive.
    """
    df = _player_frame(seasons=(0, 1), players=160)
    played = df["minutes"] > 0
    cameo = played & (df.index % 7 == 0)
    df.loc[played, "total_points"] = 10
    df.loc[cameo, ["minutes", "total_points"]] = [30, -100]
    cal = fit_calibration(df, _team_frame(seasons=(0, 1)),
                          scoring_table(load_bootstrap_sample()))
    assert cal.by_pos, "expected enough 60+ rows per group to fit"
    for group, delta in cal.by_pos.items():
        assert delta > 0, (group, delta)


def test_fit_calibration_on_too_few_gameweek_slots_is_unfitted():
    # 8 distinct (season_idx, gw) slots, at or under CALIBRATION_MIN_SLOTS:
    # holding 10 out would leave nothing to fit the inner model on.
    df = _player_frame(seasons=(0,))
    tg = _team_frame(seasons=(0,))
    assert len(df[["season_idx", "gw"]].drop_duplicates()) <= CALIBRATION_MIN_SLOTS
    cal = fit_calibration(df, tg, scoring_table(load_bootstrap_sample()))
    assert cal.by_pos == {}


def test_fit_calibration_splits_on_gameweek_slots_not_seasons():
    # The boundary is the 10th slot from the end, so the inner training set
    # reaches into the newest season rather than stopping at its start.
    df = _player_frame(seasons=(0, 1))
    slots = (df[["season_idx", "gw"]].drop_duplicates()
             .sort_values(["season_idx", "gw"]))
    assert len(slots) > CALIBRATION_MIN_SLOTS
    bs, bg = slots.iloc[-CALIBRATION_HOLDOUT_GWS][["season_idx", "gw"]]
    held = slots[(slots.season_idx > bs)
                 | ((slots.season_idx == bs) & (slots.gw >= bg))]
    assert len(held) == CALIBRATION_HOLDOUT_GWS
    # Holdout straddles the season boundary: it is not "the newest season".
    assert held.season_idx.nunique() == 2


def test_train_all_survives_defcon_stats_only_in_the_newest_season():
    # Mirrors the real frame: tackles/cbi arrived in 2025/26, so the inner
    # calibration split can land on rows that have none. A season-wise
    # holdout crashed LightGBM here with an empty design matrix.
    df = _player_frame(seasons=(0, 1))
    old = df["season_idx"] == 0
    df.loc[old, ["tackles", "cbi", "recoveries"]] = float("nan")
    models = train_all(df, _team_frame(seasons=(0, 1)), save=False)
    assert "calibration" in models
    out = models["calibration"].apply(
        pd.DataFrame({"ep": [3.0], "position": ["MID"], "p60": [1.0]}))
    assert out["ep"].notna().all()


# --- re-derived BPS reaches the feature builder ---------------------------

def _bps_history(year=2022, season_idx=0):
    """One season of a single two-team fixture per gameweek."""
    rows = []
    for gw in range(1, 4):
        for i in range(4):
            rows.append({
                "season": f"{year}-{year - 1999}",
                "season_idx": season_idx, "gw": gw, "code": 100 + i,
                "element": 1 + i, "name": f"P{i}",
                "position": ["GKP", "DEF", "MID", "FWD"][i],
                "team_code": 1 if i < 2 else 2,
                "opp_code": 2 if i < 2 else 1,
                "was_home": i < 2, "minutes": 90,
                "kickoff_time": f"{year}-08-{10 + gw:02d}T14:00:00Z",
                "bps": [30.0, 25.0, 20.0, 10.0][i],
                "bonus": [3.0, 2.0, 1.0, 0.0][i],
                "cbi": 6.0 if i == 0 else 0.0,
                "total_points": 5, "starts": 1, "value": 50,
            })
    return pd.DataFrame(rows)


def _bps_fixtures(year=2022, season_idx=0):
    rows = []
    for gw in range(1, 4):
        rows.append({
            "season_idx": season_idx, "gw": gw,
            "kickoff_time": f"{year}-08-{10 + gw:02d}T14:00:00Z",
            "home_code": 1, "away_code": 2,
            "home_goals": 1, "away_goals": 0})
    return pd.DataFrame(rows)


def _stub_store(monkeypatch, train_mod, history, fixtures,
                live=None, live_fixtures=None):
    frames = {"history/player_gw.parquet": history,
              "history/fixtures.parquet": fixtures,
              "live/player_gw.parquet": live,
              "live/fixtures.parquet": live_fixtures}
    monkeypatch.setattr(train_mod.store, "exists",
                        lambda rel: frames.get(rel) is not None)
    monkeypatch.setattr(train_mod.store, "load",
                        lambda rel: frames[rel].copy())


def test_load_training_frame_re_derives_bonus_under_the_new_bps_rules(
        monkeypatch):
    """The bonus target and every bps_r* / bonus_r* feature have to mean the
    same thing on both sides of the 2026/27 rule change, so every *stored*
    season is restated before feature engineering. Only the live season is
    already scored under the new rules and passes through untouched."""
    from gaffer.models import train as train_mod

    live = _bps_history(year=2023).drop(columns=["season_idx"])
    _stub_store(monkeypatch, train_mod,
                history=_bps_history(year=2022, season_idx=0),
                fixtures=_bps_fixtures(year=2022, season_idx=0),
                live=live,
                live_fixtures=_bps_fixtures(year=2023, season_idx=1))

    df, _tg, _elo = train_mod.load_training_frame()
    assert "bps_old" in df.columns and "bonus_old" in df.columns
    old = df[df["season_idx"] == 0]
    new = df[df["season_idx"] == 1]
    # The stored season is restated; the live season is not.
    assert set(old.loc[old["code"] == 100, "bps"]) == {29.0}
    assert set(new.loc[new["code"] == 100, "bps"]) == {30.0}
    # And the rolling features were built from the adjusted column.
    gw3 = old[(old["code"] == 100) & (old["gw"] == 3)]
    assert float(gw3["bps_r38"].iloc[0]) == 29.0


def test_load_training_frame_restates_every_stored_season_when_no_live(
        monkeypatch):
    """Before the first data_checked gameweek of a new season there is no
    live frame yet, and the newest *stored* season is still old-rules — it
    must not be mistaken for the current one and skipped."""
    from gaffer.models import train as train_mod

    _stub_store(monkeypatch, train_mod,
                history=_bps_history(year=2022, season_idx=0),
                fixtures=_bps_fixtures(year=2022, season_idx=0))

    df, _tg, _elo = train_mod.load_training_frame()
    assert set(df.loc[df["code"] == 100, "bps"]) == {29.0}
