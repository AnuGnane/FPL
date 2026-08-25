# Gaffer v4b Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the forecast gap v4a measured — replace the GBM clean-sheet head with a time-decayed Dixon-Coles fixture model fed by Shin-devigged historical closing odds, fit the odds/model blend weight instead of guessing it, add Understat's marginal xG signal and shrunken per-90 rates to the attacking heads, and layer anytime-goalscorer market prices onto `e_goals` at prediction time.

**Architecture:** Five layered prior-generating sources, one at a time, each behind a graceful-degradation rail. `src/gaffer/data/match_odds.py` ingests football-data.co.uk closing prices into `data/history/match_odds.parquet`; `shin_devig` in `src/gaffer/data/odds.py` becomes the devigger for every match-odds call site. `src/gaffer/models/dixon_coles.py` fits attack/defence/home/rho by weighted MLE and exposes `TeamModel`'s exact `fit`/`predict` contract, so the training path switches on a single constructor site and the protected `blend_team_odds(` → `comp.merge(tp` seam never moves. The blend weight is fitted walk-forward and stored as a JSON params artifact next to the pickles. `src/gaffer/data/understat.py` scrapes and caches per-match player JSON, maps Understat ids to FPL codes, and writes two parquets that `features/engineer.py` turns into leakage-safe per-90 rolling and empirical-Bayes shrunken-rate features on the existing GBM heads. Anytime-goalscorer odds are normalized against the devigged match mu and blended into `e_goals` by `blend_attacking_odds` in the advise path, before `assemble_ep`'s inputs are built.

**Tech Stack:** Python 3.12, pandas, numpy, scipy (`optimize.minimize` L-BFGS-B), LightGBM, httpx, joblib, Typer, pytest (`uv run pytest`).

---

## File Structure

**Created:**

| Path | Responsibility |
| --- | --- |
| `src/gaffer/data/names.py` | `normalize_name` — one accent/punctuation-stripping normalizer shared by the Understat id mapping and the AGS name match. No I/O. |
| `src/gaffer/data/match_odds.py` | football-data.co.uk season CSVs: download + cache, column-triple selection, `FOOTBALL_DATA_ALIASES`, Shin devig, join to fixtures, `data/history/match_odds.parquet`. |
| `src/gaffer/models/dixon_coles.py` | `DixonColesModel` (weighted MLE, decay, rho, promoted-team fallback), the scoreline pmf, and the walk-forward CS frame the blend weight is fitted on. |
| `src/gaffer/data/understat.py` | Embedded-JSON scraping, per-match cache, league/team/match parsers, id mapping, parquet builders. |
| `src/gaffer/assets/understat_overrides.json` | Manual `understat_id -> FPL code` overrides for players the automatic matcher cannot resolve. |
| `tests/test_match_odds.py` | Alias resolution, column-triple fallback chain, parsing, fixture join, unmatched counting. |
| `tests/test_dixon_coles.py` | Synthetic parameter recovery, decay behaviour, pmf properties, predict contract parity, promoted fallback, blend-weight fit. |
| `tests/test_understat.py` | Embedded-JSON parsing, cache/politeness, id mapping paths, parquet shape, degradation. |

**Modified:**

| Path | Change |
| --- | --- |
| `src/gaffer/data/odds.py` | `shin_devig`; match-odds call sites switch to it; AGS market fetch, normalization, `ags_frame`, `blend_attacking_odds`, `next_gw_event_ids`. |
| `src/gaffer/models/team.py` | `blend_team_odds(weight=...)`, `odds_blend_weight()`, `fit_blend_weight`. |
| `src/gaffer/models/persistence.py` | `save_params` / `load_params` / `params_exist` — small JSON artifacts beside the pickles. |
| `src/gaffer/models/train.py` | `build_team_model()` single constructor site; Understat join + new feature blocks in `load_training_frame`; blend-weight fit in `train_all`. |
| `src/gaffer/models/attacking.py` | `ATTACK_FEATURES` gains the Understat and shrunken-rate columns. |
| `src/gaffer/models/components.py` | `SAVES_FEATURES` gains the opponent team-level Understat columns. |
| `src/gaffer/features/engineer.py` | `add_understat_rolling`, `add_understat_team_rolling`, `merge_understat_team`, `add_shrunken_rates`. |
| `src/gaffer/config.py` | `[odds] player_props`, `[odds] ags_blend_weight`, `[understat] enabled`. |
| `src/gaffer/advise.py` | Resolve the fitted blend weight; AGS fetch + `blend_attacking_odds` between `predict_components` and `assemble_ep`. |
| `src/gaffer/cli.py` | `build-history` also builds match odds; new `understat` command. |
| `src/gaffer/evaluation.py` | Report the fitted blend weight in the current-mode payload and formatter. |
| `tests/test_odds.py` | Shin devig properties, AGS fetch/normalization/blend, degradation regression. |
| `tests/test_team_model.py` | Blend weight argument, fitted-weight resolution, existing blend tests pass the weight explicitly. |
| `tests/test_train.py` | `build_team_model` switch, Understat-absent degradation rail. |
| `tests/test_features.py` | Understat rolling leakage, shrunken rates. |
| `tests/test_config.py` | New config keys and their defaults. |
| `tests/test_cli.py` | `understat` added to the command list. |

---

## Task 1: Shin devigging

Proportional devig divides every implied probability by the booksum, which
leaves the favourite–longshot bias in place: bookmakers pad longshots more
than favourites, so the flat division under-prices exactly the big favourites
FPL managers load up on. Shin's model backs out the insider proportion `z`
and removes the pad in proportion to the risk it was protecting against.

**Files:**
- Modify: `src/gaffer/data/odds.py:83-87` (after `devig`)
- Test: `tests/test_odds.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_odds.py`:

```python
# --- Shin devigging --------------------------------------------------------

def test_shin_devig_outputs_sum_to_one():
    from gaffer.data.odds import shin_devig

    for prices in ([1.30, 3.50], [2.4, 3.4, 2.9], [1.2, 7.0, 15.0]):
        assert abs(sum(shin_devig(prices)) - 1.0) < 1e-12


def test_shin_devig_preserves_the_order_of_the_prices():
    from gaffer.data.odds import shin_devig

    out = shin_devig([1.2, 7.0, 15.0])
    assert out[0] > out[1] > out[2]


def test_shin_devig_shrinks_the_longshot_more_than_proportional_devig():
    """The whole point of the change: the pad on a longshot is bigger than
    the pad on a favourite, so removing it proportionally leaves the
    favourite under-priced."""
    from gaffer.data.odds import devig, shin_devig

    prices = [1.30, 3.50]
    shin, prop = shin_devig(prices), devig(prices)
    assert shin[0] > prop[0]        # favourite gains
    assert shin[1] < prop[1]        # longshot shrinks


def test_shin_devig_pins_a_hand_checked_two_way_market():
    from gaffer.data.odds import shin_devig

    out = shin_devig([1.30, 3.50])
    assert round(out[0], 4) == 0.7418
    assert round(out[1], 4) == 0.2582


def test_shin_devig_on_equal_prices_is_uniform():
    from gaffer.data.odds import shin_devig

    assert shin_devig([2.0, 2.0]) == [0.5, 0.5]
    for p in shin_devig([3.0, 3.0, 3.0]):
        assert abs(p - 1 / 3) < 1e-12


def test_shin_devig_on_a_vig_free_book_is_the_implied_probabilities():
    """Booksum <= 1 has no pad to remove; inventing one would push
    probabilities the wrong way."""
    from gaffer.data.odds import shin_devig

    out = shin_devig([2.0, 4.0, 4.0])
    assert abs(out[0] - 0.5) < 1e-12


def test_shin_devig_does_not_diverge_on_an_extreme_favourite():
    from gaffer.data.odds import shin_devig

    out = shin_devig([1.01, 40.0])
    assert abs(sum(out) - 1.0) < 1e-12
    assert 0.0 < out[1] < 0.05


def test_shin_devig_on_a_single_outcome_returns_one():
    from gaffer.data.odds import shin_devig

    assert shin_devig([1.5]) == [1.0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_odds.py -k shin -v`
Expected: FAIL — `ImportError: cannot import name 'shin_devig' from 'gaffer.data.odds'`

- [ ] **Step 3: Write minimal implementation**

Insert into `src/gaffer/data/odds.py`, directly after `devig`:

```python
SHIN_MAX_Z = 0.4
"""Upper bracket for the insider proportion.

Real books sit well under 0.1; the bracket only has to contain the root, and
z -> 1 is where the closed form is singular.
"""

SHIN_TOL = 1e-13
SHIN_MAX_ITER = 300


def _shin_probs(implied: list[float], booksum: float, z: float) -> list[float]:
    """Shin's implied true probabilities for a given insider proportion."""
    return [(math.sqrt(z * z + 4.0 * (1.0 - z) * pi * pi / booksum) - z)
            / (2.0 * (1.0 - z)) for pi in implied]


def shin_devig(prices: list[float]) -> list[float]:
    """Strip the vig under Shin's insider-trading model, for n outcomes.

    Bookmakers pad longshots more heavily than favourites, because the loss
    they are insuring against is bigger there. :func:`devig` divides that pad
    away uniformly and so systematically under-prices big favourites — which
    in FPL are exactly the clean-sheet and goalscorer bets the model cares
    about (Strumbelj 2014). Shin instead assumes a proportion ``z`` of the
    money is informed and solves for the ``z`` that makes the implied
    probabilities sum to one.

    ``sum(p(z))`` is ``sqrt(booksum)`` at ``z = 0`` and decreases in ``z``, so
    a plain bisection on the bracket finds the root without a derivative. A
    book with no overround (``booksum <= 1``) has no pad to remove and comes
    back as the normalized implied probabilities, and a one-outcome market is
    a certainty.
    """
    implied = [1.0 / p for p in prices]
    booksum = sum(implied)
    if len(implied) < 2 or booksum <= 1.0:
        return [pi / booksum for pi in implied]
    lo, hi = 0.0, SHIN_MAX_Z
    for _ in range(SHIN_MAX_ITER):
        mid = 0.5 * (lo + hi)
        if sum(_shin_probs(implied, booksum, mid)) > 1.0:
            lo = mid
        else:
            hi = mid
        if hi - lo < SHIN_TOL:
            break
    out = _shin_probs(implied, booksum, 0.5 * (lo + hi))
    # The bisection lands within tolerance, not exactly; renormalize so the
    # caller can rely on the sum without carrying the solver's slack.
    total = sum(out)
    return [x / total for x in out]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_odds.py -v`
Expected: PASS (every test in the file, including the 8 new ones)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/data/odds.py tests/test_odds.py
git commit -m "feat: Shin devigging for n-outcome markets

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 2: Live match odds devig through Shin

`devig` stays exactly where it is as the documented fallback and keeps
serving the over/under pair inside `_p_over25` (a two-way total is not a
favourite–longshot market in the same way, and changing it would move a
number no measurement in this cycle covers). Only the 1X2 triple in
`odds_frame` switches.

**Files:**
- Modify: `src/gaffer/data/odds.py:290` (inside `odds_frame`)
- Test: `tests/test_odds.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_odds.py`:

```python
def test_odds_frame_devigs_the_match_triple_with_shin():
    """The 1X2 triple is where favourite-longshot bias bites; the totals
    pair keeps proportional devig on purpose."""
    import inspect

    from gaffer.data.odds import _p_over25, odds_frame

    src = inspect.getsource(odds_frame)
    assert "shin_devig(triple)" in src
    assert "devig(triple)" not in src
    assert "devig(" in inspect.getsource(_p_over25)


def test_odds_frame_favourite_gets_the_shin_boost():
    """Same fixture, hand-computed: the home mu recovered from Shin-devigged
    probabilities is at least as big as the proportional one."""
    from gaffer.data.odds import devig, invert_odds, shin_devig

    triple = [2.4, 3.4, 2.9]
    ph_s, pd_s, pa_s = shin_devig(triple)
    ph_p, pd_p, pa_p = devig(triple)
    assert ph_s > ph_p
    mu_shin = invert_odds(ph_s, pd_s, pa_s, 0.5)
    mu_prop = invert_odds(ph_p, pd_p, pa_p, 0.5)
    assert mu_shin[0] >= mu_prop[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_odds.py -k shin_boost -v`
Expected: FAIL — `AssertionError: assert 'shin_devig(triple)' in src`

- [ ] **Step 3: Write minimal implementation**

In `src/gaffer/data/odds.py`, inside `odds_frame`, replace the devig line:

```python
        p_home, p_draw, p_away = shin_devig(triple)
```

And extend `odds_frame`'s docstring paragraph about devigging to read:

```python
    h2h outcomes are matched by *name* (home team / away team / ``Draw``),
    never by list position, and de-vigged with :func:`shin_devig` before
    inversion; the Over/Under pair keeps proportional :func:`devig` (a
    two-way total carries no favourite-longshot bias worth modelling, and
    ``invert_odds`` validates nothing).
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_odds.py -v`
Expected: PASS (whole file)

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/data/odds.py tests/test_odds.py
git commit -m "feat: devig the live 1X2 triple with Shin

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 3: football-data.co.uk parsing and aliases

**Files:**
- Create: `src/gaffer/data/match_odds.py`
- Test: `tests/test_match_odds.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_match_odds.py`:

```python
import pandas as pd
import pytest

from gaffer.data.match_odds import (FOOTBALL_DATA_ALIASES, PRICE_TRIPLES,
                                    TOTALS_PAIRS, parse_football_data,
                                    resolve_fd_team)
from gaffer.errors import GafferError


def _csv_rows(extra: dict | None = None) -> pd.DataFrame:
    """Two matches in football-data's own column vocabulary."""
    base = {
        "Date": ["16/08/2024", "17/08/2024"],
        "HomeTeam": ["Man United", "Nott'm Forest"],
        "AwayTeam": ["Wolves", "Bournemouth"],
        "AvgCH": [1.80, 2.30], "AvgCD": [3.80, 3.30], "AvgCA": [4.50, 3.20],
        "AvgC>2.5": [1.90, 2.05], "AvgC<2.5": [1.95, 1.80],
    }
    base.update(extra or {})
    return pd.DataFrame(base)


def test_resolve_fd_team_maps_football_data_short_names():
    assert resolve_fd_team("Man United") == "Man Utd"
    assert resolve_fd_team("Nott'm Forest") == "Nott'm Forest"
    assert resolve_fd_team("Wolves") == "Wolves"
    assert resolve_fd_team("Spurs") == "Spurs"


def test_resolve_fd_team_raises_on_an_unknown_name():
    """A silently mismatched club attaches one team's odds to another, which
    is far worse than losing the odds for a season."""
    with pytest.raises(GafferError) as exc:
        resolve_fd_team("Barnsley Athletic")
    assert "FOOTBALL_DATA_ALIASES" in str(exc.value)


def test_every_alias_target_is_an_fpl_bootstrap_name():
    from gaffer.data.odds import TEAM_ALIASES

    fpl_names = set(TEAM_ALIASES.values())
    unknown = sorted(set(FOOTBALL_DATA_ALIASES.values()) - fpl_names)
    assert unknown == []


def test_parse_football_data_devigs_the_closing_triple_with_shin():
    from gaffer.data.odds import shin_devig

    out = parse_football_data(_csv_rows(), season="2024-25", season_idx=2)
    want = shin_devig([1.80, 3.80, 4.50])
    assert abs(out.loc[0, "p_home"] - want[0]) < 1e-12
    assert abs(out.loc[0, "p_draw"] - want[1]) < 1e-12
    assert abs(out.loc[0, "p_away"] - want[2]) < 1e-12
    assert abs(out.loc[0, "p_home"] + out.loc[0, "p_draw"]
               + out.loc[0, "p_away"] - 1.0) < 1e-12


def test_parse_football_data_devigs_the_totals_pair():
    from gaffer.data.odds import devig

    out = parse_football_data(_csv_rows(), season="2024-25", season_idx=2)
    assert abs(out.loc[0, "p_over25"] - devig([1.90, 1.95])[0]) < 1e-12


def test_parse_football_data_maps_names_and_dates():
    out = parse_football_data(_csv_rows(), season="2024-25", season_idx=2)
    assert list(out["home_name"]) == ["Man Utd", "Nott'm Forest"]
    assert list(out["away_name"]) == ["Wolves", "Bournemouth"]
    assert list(out["date"]) == [pd.Timestamp("2024-08-16").date(),
                                 pd.Timestamp("2024-08-17").date()]
    assert set(out["season"]) == {"2024-25"} and set(out["season_idx"]) == {2}


def test_parse_football_data_accepts_four_digit_years_too():
    """Older seasons use dd/mm/yy, newer ones dd/mm/yyyy; both appear in the
    same archive."""
    rows = _csv_rows({"Date": ["16/08/24", "17/08/24"]})
    out = parse_football_data(rows, season="2024-25", season_idx=2)
    assert out.loc[0, "date"] == pd.Timestamp("2024-08-16").date()


def test_parse_football_data_falls_back_down_the_price_chain():
    """Closing averages are the first choice; a season that predates them
    still has to parse."""
    rows = _csv_rows().drop(columns=["AvgCH", "AvgCD", "AvgCA"])
    rows["B365H"], rows["B365D"], rows["B365A"] = [1.80, 2.30], [3.80, 3.30], [4.50, 3.20]
    out = parse_football_data(rows, season="2020-21", season_idx=0)
    assert len(out) == 2
    assert out["p_home"].notna().all()


def test_parse_football_data_takes_the_first_fully_present_triple():
    """A partially-populated preferred triple must not win over a complete
    later one — half a market is not a market."""
    rows = _csv_rows()
    rows.loc[0, "AvgCH"] = float("nan")
    rows["AvgH"], rows["AvgD"], rows["AvgA"] = [1.70, 2.20], [3.90, 3.40], [4.60, 3.30]
    out = parse_football_data(rows, season="2024-25", season_idx=2)
    from gaffer.data.odds import shin_devig
    assert abs(out.loc[0, "p_home"] - shin_devig([1.70, 3.90, 4.60])[0]) < 1e-12


def test_parse_football_data_without_any_price_triple_returns_empty():
    rows = _csv_rows().drop(columns=["AvgCH", "AvgCD", "AvgCA"])
    out = parse_football_data(rows, season="2024-25", season_idx=2)
    assert out.empty
    assert list(out.columns) == ["season", "season_idx", "date", "home_name",
                                 "away_name", "p_home", "p_draw", "p_away",
                                 "p_over25"]


def test_parse_football_data_without_a_totals_pair_uses_the_neutral_prior():
    from gaffer.data.odds import NEUTRAL_P_OVER25

    rows = _csv_rows().drop(columns=["AvgC>2.5", "AvgC<2.5"])
    out = parse_football_data(rows, season="2024-25", season_idx=2)
    assert (out["p_over25"] == NEUTRAL_P_OVER25).all()


def test_parse_football_data_drops_blank_trailing_rows():
    """football-data ships trailing all-empty rows in most season files."""
    rows = _csv_rows()
    blank = pd.DataFrame([{c: float("nan") for c in rows.columns}])
    blank["HomeTeam"] = None
    out = parse_football_data(pd.concat([rows, blank], ignore_index=True),
                              season="2024-25", season_idx=2)
    assert len(out) == 2


def test_price_and_totals_preference_chains_are_ordered_closing_first():
    assert PRICE_TRIPLES[0] == ("AvgCH", "AvgCD", "AvgCA")
    assert TOTALS_PAIRS[0] == ("AvgC>2.5", "AvgC<2.5")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_match_odds.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gaffer.data.match_odds'`

- [ ] **Step 3: Write minimal implementation**

Create `src/gaffer/data/match_odds.py`:

```python
"""Historical closing match odds from football-data.co.uk.

The-odds-api prices only *upcoming* fixtures, so nothing in the live feed can
ever be backfilled: there is no historical row anywhere in this codebase that
carries what the market thought before a match that has already been played.
Without one, the odds blend weight can only be guessed, and a Dixon-Coles fit
can never be scored against the market it is supposed to complement.
football-data.co.uk publishes exactly that record — one CSV per season, closing
averages across books — free, stable, and going back further than our history.

Finished seasons never change, so their files are cached permanently; the
current season's file grows weekly and is re-downloaded on every refresh.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pandas as pd

from gaffer.data import store
from gaffer.data.odds import NEUTRAL_P_OVER25, devig, shin_devig
from gaffer.errors import GafferError

BASE = "https://www.football-data.co.uk/mmz4281"
MATCH_ODDS_PATH = "history/match_odds.parquet"
CACHE_DIR = Path("data/raw/football-data")

PRICE_TRIPLES = [
    ("AvgCH", "AvgCD", "AvgCA"),    # closing average across books
    ("AvgH", "AvgD", "AvgA"),       # opening/period average
    ("B365CH", "B365CD", "B365CA"),  # single-book closing
    ("B365H", "B365D", "B365A"),    # single-book
]
"""1X2 column triples in preference order, closing averages first.

Closing prices are the sharpest number the market ever produces, and an
average across books strips one book's idiosyncratic lean. The chain exists
because coverage varies by season: the ``C`` (closing) columns only start in
2019-20, and a handful of early files carry Bet365 alone.
"""

TOTALS_PAIRS = [
    ("AvgC>2.5", "AvgC<2.5"),
    ("Avg>2.5", "Avg<2.5"),
    ("B365C>2.5", "B365C<2.5"),
    ("B365>2.5", "B365<2.5"),
]
"""Over/Under 2.5 pairs, same preference order and same reason."""

OUT_COLS = ["season", "season_idx", "date", "home_name", "away_name",
            "p_home", "p_draw", "p_away", "p_over25"]

# football-data uses its own short club names, which are neither The Odds
# API's official names nor FPL's bootstrap names. Values are FPL bootstrap
# names, so this table and TEAM_ALIASES land in the same vocabulary.
FOOTBALL_DATA_ALIASES = {
    "Arsenal": "Arsenal",
    "Aston Villa": "Aston Villa",
    "Bournemouth": "Bournemouth",
    "Brentford": "Brentford",
    "Brighton": "Brighton",
    "Burnley": "Burnley",
    "Cardiff": "Cardiff City",
    "Chelsea": "Chelsea",
    "Coventry": "Coventry City",
    "Crystal Palace": "Crystal Palace",
    "Everton": "Everton",
    "Fulham": "Fulham",
    "Huddersfield": "Huddersfield",
    "Hull": "Hull City",
    "Ipswich": "Ipswich Town",
    "Leeds": "Leeds",
    "Leicester": "Leicester",
    "Liverpool": "Liverpool",
    "Luton": "Luton",
    "Man City": "Man City",
    "Man United": "Man Utd",
    "Middlesbrough": "Middlesbrough",
    "Newcastle": "Newcastle",
    "Norwich": "Norwich",
    "Nott'm Forest": "Nott'm Forest",
    "Sheffield United": "Sheffield Utd",
    "Southampton": "Southampton",
    "Stoke": "Stoke City",
    "Sunderland": "Sunderland",
    "Swansea": "Swansea",
    "Tottenham": "Spurs",
    "Watford": "Watford",
    "West Brom": "West Brom",
    "West Ham": "West Ham",
    "Wolves": "Wolves",
}

_FPL_NAMES = set(FOOTBALL_DATA_ALIASES.values())


def resolve_fd_team(name: str) -> str:
    """football-data club name -> FPL bootstrap name.

    Same raise-on-unknown discipline as
    :func:`gaffer.data.odds.resolve_team`: guessing would attach one club's
    closing odds to another, and a silently wrong prior is worse than none.
    """
    if name in FOOTBALL_DATA_ALIASES:
        return FOOTBALL_DATA_ALIASES[name]
    if name in _FPL_NAMES:
        return name
    raise GafferError(
        f"unknown team name in the football-data file: {name!r} — add it to "
        "FOOTBALL_DATA_ALIASES in gaffer/data/match_odds.py")


def _first_complete(df: pd.DataFrame,
                    groups: list[tuple[str, ...]]) -> tuple[str, ...] | None:
    """First column group present *and* fully populated on every kept row.

    A half-filled preferred triple is not a market: taking it would devig two
    real prices against a NaN and produce a probability that looks fine and
    means nothing.
    """
    for group in groups:
        if not all(c in df.columns for c in group):
            continue
        block = df[list(group)].apply(pd.to_numeric, errors="coerce")
        if block.notna().all().all() and (block > 1.0).all().all():
            return group
    return None


def parse_football_data(raw: pd.DataFrame, season: str,
                        season_idx: int) -> pd.DataFrame:
    """One season's football-data CSV -> devigged match probabilities.

    Output ``[season, season_idx, date, home_name, away_name, p_home, p_draw,
    p_away, p_over25]``, one row per match, team names already in FPL's
    vocabulary and probabilities already devigged — the 1X2 triple by
    :func:`~gaffer.data.odds.shin_devig`, the totals pair by proportional
    :func:`~gaffer.data.odds.devig`.

    A file with no usable 1X2 triple yields an empty frame with the right
    columns rather than an exception: some early seasons in the archive are
    genuinely price-free, and one bad season must not fail a backfill.
    """
    df = raw[raw["HomeTeam"].notna() & raw["AwayTeam"].notna()].copy()
    df = df.reset_index(drop=True)
    empty = pd.DataFrame(columns=OUT_COLS)
    if df.empty:
        return empty
    triple = _first_complete(df, PRICE_TRIPLES)
    if triple is None:
        return empty

    prices = df[list(triple)].apply(pd.to_numeric, errors="coerce")
    devigged = [shin_devig([float(h), float(d), float(a)])
                for h, d, a in zip(prices[triple[0]], prices[triple[1]],
                                   prices[triple[2]])]
    pair = _first_complete(df, TOTALS_PAIRS)
    if pair is None:
        p_over = [NEUTRAL_P_OVER25] * len(df)
    else:
        totals = df[list(pair)].apply(pd.to_numeric, errors="coerce")
        p_over = [devig([float(o), float(u)])[0]
                  for o, u in zip(totals[pair[0]], totals[pair[1]])]

    # dayfirst covers both dd/mm/yy and dd/mm/yyyy, which the archive mixes
    # across seasons; a date is all we join on, so the time of day is noise.
    dates = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    out = pd.DataFrame({
        "season": season,
        "season_idx": int(season_idx),
        "date": dates.dt.date,
        "home_name": [resolve_fd_team(n) for n in df["HomeTeam"]],
        "away_name": [resolve_fd_team(n) for n in df["AwayTeam"]],
        "p_home": [p[0] for p in devigged],
        "p_draw": [p[1] for p in devigged],
        "p_away": [p[2] for p in devigged],
        "p_over25": p_over,
    })
    return out[out["date"].notna()].reset_index(drop=True)[OUT_COLS]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_match_odds.py -v`
Expected: PASS (13 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/data/match_odds.py tests/test_match_odds.py
git commit -m "feat: parse football-data.co.uk closing odds with Shin devig

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 4: Download, join and store `data/history/match_odds.parquet`

**Files:**
- Modify: `src/gaffer/data/match_odds.py` (append after `parse_football_data`)
- Modify: `src/gaffer/cli.py:70-81` (`build-history`)
- Test: `tests/test_match_odds.py` (append)
- Test: `tests/test_cli.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_match_odds.py`:

```python
import httpx

from gaffer.data.match_odds import (MATCH_ODDS_PATH, build_match_odds,
                                    download_season, join_to_fixtures,
                                    season_slug)

_CSV = ("Date,HomeTeam,AwayTeam,AvgCH,AvgCD,AvgCA,AvgC>2.5,AvgC<2.5\n"
        "16/08/2024,Man United,Wolves,1.80,3.80,4.50,1.90,1.95\n"
        "17/08/2024,Nott'm Forest,Bournemouth,2.30,3.30,3.20,2.05,1.80\n")


def _fixtures() -> pd.DataFrame:
    return pd.DataFrame([
        {"season_idx": 2, "gw": 1, "kickoff_time": "2024-08-16T19:00:00Z",
         "home_code": 1, "away_code": 39, "home_goals": 1, "away_goals": 0},
        {"season_idx": 2, "gw": 1, "kickoff_time": "2024-08-17T14:00:00Z",
         "home_code": 17, "away_code": 91, "home_goals": 1, "away_goals": 1},
        {"season_idx": 2, "gw": 2, "kickoff_time": "2024-08-24T14:00:00Z",
         "home_code": 39, "away_code": 17, "home_goals": 2, "away_goals": 2},
    ])


_NAME_TO_CODE = {"Man Utd": 1, "Wolves": 39, "Nott'm Forest": 17,
                 "Bournemouth": 91}


def test_season_slug_is_the_two_year_pair():
    assert season_slug("2024-25") == "2425"
    assert season_slug("2020-21") == "2021"


def test_download_season_caches_and_does_not_refetch_a_finished_season(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        assert str(request.url) == (
            "https://www.football-data.co.uk/mmz4281/2425/E0.csv")
        return httpx.Response(200, text=_CSV)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    first = download_season("2024-25", cache_dir=tmp_path, client=client)
    second = download_season("2024-25", cache_dir=tmp_path, client=client)
    assert calls["n"] == 1
    assert len(first) == len(second) == 2
    assert (tmp_path / "2024-25" / "E0.csv").exists()


def test_download_season_refetches_the_current_season(tmp_path):
    """The running season's file grows every week; a cached copy is stale by
    definition."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, text=_CSV)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    download_season("2024-25", cache_dir=tmp_path, client=client, refresh=True)
    download_season("2024-25", cache_dir=tmp_path, client=client, refresh=True)
    assert calls["n"] == 2


def test_download_season_on_a_missing_file_returns_none(tmp_path):
    """A season the archive has not published yet must not fail a backfill."""
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    assert download_season("2030-31", cache_dir=tmp_path, client=client) is None


def test_join_to_fixtures_matches_on_date_and_both_team_codes():
    parsed = parse_football_data(_csv_rows(), season="2024-25", season_idx=2)
    out, report = join_to_fixtures(parsed, _fixtures(), _NAME_TO_CODE)
    assert list(out.columns) == ["season_idx", "gw", "kickoff_time",
                                 "home_code", "away_code", "p_home", "p_draw",
                                 "p_away", "p_over25"]
    assert list(out["home_code"]) == [1, 17]
    assert list(out["gw"]) == [1, 1]
    assert report == {"rows": 2, "matched": 2, "unmatched": 0}


def test_join_to_fixtures_counts_unmatched_rows_without_raising():
    """A cup game, a postponement, or a club we cannot code must cost that
    row and nothing else."""
    parsed = parse_football_data(_csv_rows(), season="2024-25", season_idx=2)
    out, report = join_to_fixtures(parsed, _fixtures(),
                                   {"Man Utd": 1, "Wolves": 39})
    assert len(out) == 1
    assert report == {"rows": 2, "matched": 1, "unmatched": 1}


def test_join_to_fixtures_uses_uk_local_dates():
    """A 20:00 UK kickoff in summer is 19:00 UTC on the same day, but a
    23:00 one would roll over — football-data stamps UK dates, so the
    comparison has to be made in UK time."""
    parsed = parse_football_data(
        _csv_rows({"Date": ["16/08/2024", "17/08/2024"]}),
        season="2024-25", season_idx=2)
    fx = _fixtures()
    fx.loc[0, "kickoff_time"] = "2024-08-16T23:30:00Z"   # 00:30 UK, 17 Aug
    out, report = join_to_fixtures(parsed, fx, _NAME_TO_CODE)
    assert report["unmatched"] == 1


def test_join_to_fixtures_keeps_a_double_gameweek_apart():
    """Date + both team codes is unique even when a team plays twice in one
    gameweek."""
    rows = _csv_rows({"Date": ["16/08/2024", "24/08/2024"],
                      "HomeTeam": ["Man United", "Wolves"],
                      "AwayTeam": ["Wolves", "Nott'm Forest"]})
    parsed = parse_football_data(rows, season="2024-25", season_idx=2)
    out, _ = join_to_fixtures(parsed, _fixtures(), _NAME_TO_CODE)
    assert list(out["gw"]) == [1, 2]


def test_build_match_odds_writes_the_parquet(tmp_path, monkeypatch):
    import gaffer.data.store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=_CSV)))
    out = build_match_odds(["2024-25"], _fixtures(), {"2024-25": _NAME_TO_CODE},
                           cache_dir=tmp_path / "raw", client=client,
                           season_indexes={"2024-25": 2})
    assert len(out) == 2
    assert (tmp_path / MATCH_ODDS_PATH).exists()


def test_build_match_odds_survives_a_season_the_archive_lacks(tmp_path,
                                                              monkeypatch):
    import gaffer.data.store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)

    def handler(request):
        if "/2425/" in str(request.url):
            return httpx.Response(200, text=_CSV)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = build_match_odds(["2023-24", "2024-25"], _fixtures(),
                           {"2024-25": _NAME_TO_CODE}, cache_dir=tmp_path / "raw",
                           client=client,
                           season_indexes={"2023-24": 1, "2024-25": 2})
    assert len(out) == 2
```

Append to `tests/test_cli.py`:

```python
def test_build_history_also_builds_the_match_odds_parquet():
    """Closing odds are part of the training corpus now, so the one-shot
    corpus command has to produce them."""
    import inspect

    from gaffer.cli import build_history_cmd

    src = inspect.getsource(build_history_cmd)
    assert "build_match_odds(" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_match_odds.py -k season_slug -v`
Expected: FAIL — `ImportError: cannot import name 'MATCH_ODDS_PATH' from 'gaffer.data.match_odds'` (the whole appended import block fails to resolve)

- [ ] **Step 3: Write minimal implementation**

Append to `src/gaffer/data/match_odds.py`:

```python
def season_slug(season: str) -> str:
    """``"2024-25"`` -> ``"2425"``, football-data's directory name."""
    return f"{season[2:4]}{season[5:7]}"


def download_season(season: str, cache_dir: Path = CACHE_DIR,
                    client: httpx.Client | None = None,
                    refresh: bool = False) -> pd.DataFrame | None:
    """One season's ``E0.csv``, cached under ``cache_dir/<season>/E0.csv``.

    A finished season's file never changes, so it is fetched once and read
    from disk forever after. ``refresh=True`` is for the running season, whose
    file grows every week. A season the archive does not carry (a 404, or a
    future season) returns ``None`` — a backfill spanning five seasons must
    not die on the one that is missing.
    """
    dest = Path(cache_dir) / season / "E0.csv"
    if refresh or not dest.exists():
        http = client if client is not None else httpx.Client(
            timeout=60, follow_redirects=True)
        try:
            resp = http.get(f"{BASE}/{season_slug(season)}/E0.csv")
            resp.raise_for_status()
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            print(f"football-data: no file for {season} ({exc})")
            return None
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
    try:
        return pd.read_csv(dest)
    except UnicodeDecodeError:      # a few seasons are latin-1
        return pd.read_csv(dest, encoding="latin-1")


JOIN_COLS = ["season_idx", "gw", "kickoff_time", "home_code", "away_code",
             "p_home", "p_draw", "p_away", "p_over25"]


def join_to_fixtures(parsed: pd.DataFrame, fixtures: pd.DataFrame,
                     name_to_code: dict[str, int]
                     ) -> tuple[pd.DataFrame, dict[str, int]]:
    """Attach ``(season_idx, gw, kickoff_time)`` to each priced match.

    Keyed on ``(home_code, away_code, UK kickoff date)``. Date plus both
    codes is unique even in a double gameweek — the same pair does not meet
    twice in a week — where ``(gw, home_code)`` alone would not be. The date
    is compared in *UK local time* because that is the clock football-data
    stamps its files with; a 23:30 UTC kickoff is the next day in neither
    system's opinion but the previous day in ours if the conversion is
    skipped.

    Returns the joined frame and a count report. Unmatched rows are dropped
    and reported, never fatal: cup fixtures, postponements and clubs missing
    from a season's bootstrap all land here legitimately.
    """
    fx = fixtures.copy()
    kt = pd.to_datetime(fx["kickoff_time"], utc=True, format="mixed")
    fx["_date"] = kt.dt.tz_convert("Europe/London").dt.date
    left = parsed.copy()
    left["home_code"] = left["home_name"].map(name_to_code)
    left["away_code"] = left["away_name"].map(name_to_code)
    left["_date"] = left["date"]
    merged = left.merge(
        fx[["season_idx", "gw", "kickoff_time", "home_code", "away_code",
            "_date"]],
        on=["home_code", "away_code", "_date"], how="left",
        suffixes=("", "_fx"))
    ok = merged["gw"].notna()
    report = {"rows": int(len(left)), "matched": int(ok.sum()),
              "unmatched": int((~ok).sum())}
    out = merged[ok].copy()
    out["season_idx"] = out["season_idx"].astype(int)
    out["gw"] = out["gw"].astype(int)
    out["home_code"] = out["home_code"].astype(int)
    out["away_code"] = out["away_code"].astype(int)
    return out[JOIN_COLS].reset_index(drop=True), report


def build_match_odds(seasons: list[str], fixtures: pd.DataFrame,
                     names_by_season: dict[str, dict[str, int]],
                     cache_dir: Path = CACHE_DIR,
                     client: httpx.Client | None = None,
                     season_indexes: dict[str, int] | None = None,
                     current_season: str | None = None) -> pd.DataFrame:
    """Every season's closing odds -> ``data/history/match_odds.parquet``.

    ``names_by_season`` maps a season to its ``{bootstrap name: code}`` table,
    because a code is only meaningful next to the season whose bootstrap
    produced it. ``current_season``, if given and present in ``seasons``, is
    the only file re-downloaded.

    A season with no archive file, no usable prices or no name table is
    skipped with a printed line; the parquet is still written from what did
    resolve, and an entirely empty result writes an empty frame with the right
    columns so downstream ``store.load`` never sees a missing schema.
    """
    indexes = season_indexes or {s: i for i, s in enumerate(seasons)}
    frames, reports = [], {}
    for season in seasons:
        raw = download_season(season, cache_dir=cache_dir, client=client,
                              refresh=season == current_season)
        if raw is None:
            continue
        parsed = parse_football_data(raw, season, indexes[season])
        if parsed.empty:
            print(f"football-data: no usable price columns for {season}")
            continue
        names = names_by_season.get(season)
        if not names:
            print(f"football-data: no team name table for {season}")
            continue
        joined, report = join_to_fixtures(parsed, fixtures, names)
        reports[season] = report
        frames.append(joined)
    out = (pd.concat(frames, ignore_index=True) if frames
           else pd.DataFrame(columns=JOIN_COLS))
    for season, rep in reports.items():
        print(f"football-data {season}: {rep['matched']}/{rep['rows']} "
              f"matched, {rep['unmatched']} unmatched")
    store.save(out, MATCH_ODDS_PATH)
    return out
```

In `src/gaffer/cli.py`, replace the body of `build_history_cmd`:

```python
@app.command("build-history")
def build_history_cmd():
    """Download the historical seasons into data/history/ (run once)."""
    from gaffer.config import load_config
    from gaffer.data.history import build_history, build_history_fixtures
    from gaffer.data.history import season_name_codes
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
```

And append the name-table helper to `src/gaffer/data/history.py`:

```python
def season_name_codes(
    seasons: list[str],
    cache_dir: Path = Path("data/raw/vaastav"),
) -> dict[str, dict[str, int]]:
    """``{season: {bootstrap team name: code}}`` from the cached teams.csv.

    A team code is only meaningful next to the season whose bootstrap
    produced it, so the tables are kept per season rather than merged. The
    files are already on disk from :func:`build_history`, so this costs
    nothing after the first run.
    """
    out: dict[str, dict[str, int]] = {}
    for season in seasons:
        teams = _download_csv(
            f"{VAASTAV}/{season}/teams.csv", cache_dir / season / "teams.csv"
        )
        out[season] = dict(zip(teams["name"], teams["code"].astype(int)))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_match_odds.py tests/test_cli.py -v`
Expected: PASS (23 in `test_match_odds.py`, whole `test_cli.py` green)

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/data/match_odds.py src/gaffer/data/history.py src/gaffer/cli.py tests/test_match_odds.py tests/test_cli.py
git commit -m "feat: build data/history/match_odds.parquet from football-data

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 5: The Dixon-Coles scoreline pmf

**Files:**
- Create: `src/gaffer/models/dixon_coles.py`
- Test: `tests/test_dixon_coles.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_dixon_coles.py`:

```python
import math

import numpy as np
import pandas as pd

from gaffer.models.dixon_coles import (GOAL_CAP, fixture_outcomes,
                                       scoreline_pmf, tau_correction)


def test_tau_correction_is_one_away_from_the_low_score_corner():
    assert tau_correction(2, 3, 1.4, 1.1, -0.1) == 1.0
    assert tau_correction(0, 2, 1.4, 1.1, -0.1) == 1.0


def test_tau_correction_matches_the_published_four_cases():
    lam, mu, rho = 1.4, 1.1, -0.12
    assert abs(tau_correction(0, 0, lam, mu, rho) - (1 - lam * mu * rho)) < 1e-12
    assert abs(tau_correction(0, 1, lam, mu, rho) - (1 + lam * rho)) < 1e-12
    assert abs(tau_correction(1, 0, lam, mu, rho) - (1 + mu * rho)) < 1e-12
    assert abs(tau_correction(1, 1, lam, mu, rho) - (1 - rho)) < 1e-12


def test_scoreline_pmf_sums_to_one():
    pmf = scoreline_pmf(1.6, 1.1, -0.12)
    assert abs(pmf.sum() - 1.0) < 1e-12
    assert pmf.shape == (GOAL_CAP + 1, GOAL_CAP + 1)


def test_scoreline_pmf_with_zero_rho_is_independent_poisson():
    pmf = scoreline_pmf(1.6, 1.1, 0.0)
    for x in (0, 1, 3):
        for y in (0, 2):
            want = (math.exp(-1.6) * 1.6 ** x / math.factorial(x)
                    * math.exp(-1.1) * 1.1 ** y / math.factorial(y))
            assert abs(pmf[x, y] - want) < 1e-6


def test_scoreline_pmf_negative_rho_lifts_the_nil_nil():
    """The correction exists because low-scoring scorelines are more common
    than independence implies; a negative rho is what buys that."""
    assert scoreline_pmf(1.4, 1.1, -0.12)[0, 0] > scoreline_pmf(1.4, 1.1, 0.0)[0, 0]


def test_scoreline_pmf_is_never_negative():
    for rho in (-0.4, -0.1, 0.0, 0.1, 0.4):
        assert (scoreline_pmf(0.4, 3.5, rho) >= 0.0).all()


def test_fixture_outcomes_clean_sheet_is_the_opponents_zero_column():
    out = fixture_outcomes(1.6, 1.1, -0.12)
    pmf = scoreline_pmf(1.6, 1.1, -0.12)
    assert abs(out["p_cs_home"] - pmf[:, 0].sum()) < 1e-12
    assert abs(out["p_cs_away"] - pmf[0, :].sum()) < 1e-12


def test_fixture_outcomes_expected_goals_conceded_matches_the_mean():
    out = fixture_outcomes(1.6, 1.1, 0.0)
    # With rho = 0 the marginals are exactly Poisson, so E[GC] is the mu.
    assert abs(out["e_gc_home"] - 1.1) < 1e-6
    assert abs(out["e_gc_away"] - 1.6) < 1e-6


def test_fixture_outcomes_result_probabilities_sum_to_one():
    out = fixture_outcomes(1.6, 1.1, -0.12)
    total = out["p_home_win"] + out["p_draw"] + out["p_away_win"]
    assert abs(total - 1.0) < 1e-12


def test_fixture_outcomes_reports_the_two_goal_concession_band():
    """The -0.5/goal deduction only starts biting at two conceded, so the
    band is worth carrying out of the one coherent distribution."""
    out = fixture_outcomes(1.6, 1.1, -0.12)
    pmf = scoreline_pmf(1.6, 1.1, -0.12)
    assert abs(out["p_gc2_home"] - pmf[:, 2:].sum()) < 1e-12


def test_fixture_outcomes_stronger_side_has_the_better_clean_sheet():
    strong = fixture_outcomes(2.2, 0.6, -0.12)
    weak = fixture_outcomes(0.6, 2.2, -0.12)
    assert strong["p_cs_home"] > weak["p_cs_home"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dixon_coles.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gaffer.models.dixon_coles'`

- [ ] **Step 3: Write minimal implementation**

Create `src/gaffer/models/dixon_coles.py`:

```python
"""Dixon-Coles: one coherent scoreline distribution per fixture.

The GBM team head predicts P(clean sheet) and E[goals conceded] as two
unrelated numbers from rolling form and an Elo gap, and v4a measured what
that costs: CS log loss 0.6190, the worst-calibrated head in the model. The
trouble is structural rather than a tuning problem. A clean sheet is a
*scoreline* event, the -0.5/goal deduction is the same distribution's mean,
and the saves context is its shape; a classifier and a regressor fitted
side by side can and do disagree about all three.

Dixon & Coles (1997) model the two goal counts directly: every team carries
an attack strength and a defence strength, the home side gets a fixed
advantage, and a low-score correction ``rho`` fixes independent Poisson's
well-known under-prediction of 0-0 and 1-1. Fitting is weighted maximum
likelihood with an exponential decay on match age, so last month counts for
more than two seasons ago without anyone hand-picking a window.

The class deliberately mirrors :class:`gaffer.models.team.TeamModel`'s
``fit``/``predict`` contract exactly, so the switch is one constructor site
and the protected ``blend_team_odds(`` -> ``comp.merge(tp`` seam in
``advise.predict_components`` never moves.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

GOAL_CAP = 10
"""Highest scoreline modelled. P(11+ goals for one side) is ~1e-8 at EPL
rates, and the pmf is renormalized anyway, so the truncation costs nothing
measurable and bounds every sum in here."""

DEFAULT_XI = 0.0065
"""Decay rate per day, ~1-year half-life — the published starting point.
Task 10 measures the grid {0.003, 0.0065, 0.01} and pins the winner here."""

RHO_BOUNDS = (-0.4, 0.4)
"""Bracket for the low-score correction. Real fits land near -0.1; the bound
is what stops the optimizer wandering into the region where the corrected
pmf can go negative."""


def tau_correction(x: int, y: int, lam: float, mu: float,
                   rho: float) -> float:
    """Dixon-Coles' low-score dependence factor for one scoreline.

    Independent Poisson under-predicts 0-0 and 1-1 and over-predicts 1-0 and
    0-1; ``tau`` reweights exactly those four cells and leaves every other
    scoreline alone.
    """
    if x == 0 and y == 0:
        return 1.0 - lam * mu * rho
    if x == 0 and y == 1:
        return 1.0 + lam * rho
    if x == 1 and y == 0:
        return 1.0 + mu * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def _poisson_pmf(mu: float, cap: int = GOAL_CAP) -> np.ndarray:
    mu = max(float(mu), 1e-9)
    return np.array([math.exp(-mu) * mu ** k / math.factorial(k)
                     for k in range(cap + 1)])


def scoreline_pmf(lam: float, mu: float, rho: float,
                  cap: int = GOAL_CAP) -> np.ndarray:
    """``P[x, y]`` for home ``x`` goals and away ``y`` goals.

    Clipped at zero and renormalized: an extreme ``rho`` against an extreme
    ``lam*mu`` can push the 0-0 cell negative, and a negative probability
    downstream is a crash waiting for a quiet fixture. Renormalization also
    absorbs the truncation at ``cap``.
    """
    ph, pa = _poisson_pmf(lam, cap), _poisson_pmf(mu, cap)
    out = np.outer(ph, pa)
    out[0, 0] *= tau_correction(0, 0, lam, mu, rho)
    out[0, 1] *= tau_correction(0, 1, lam, mu, rho)
    out[1, 0] *= tau_correction(1, 0, lam, mu, rho)
    out[1, 1] *= tau_correction(1, 1, lam, mu, rho)
    out = np.clip(out, 0.0, None)
    total = out.sum()
    return out / total if total > 0 else np.full(out.shape,
                                                 1.0 / out.size)


def fixture_outcomes(lam: float, mu: float, rho: float,
                     cap: int = GOAL_CAP) -> dict[str, float]:
    """Everything downstream needs, read off one scoreline distribution.

    Clean sheets, the goals-conceded mean behind the -0.5/goal deduction,
    result probabilities for the fixture ticker and the 2+ conceded band all
    come from the same joint pmf, so they cannot contradict each other the
    way a separate classifier and regressor could.
    """
    pmf = scoreline_pmf(lam, mu, rho, cap)
    goals = np.arange(cap + 1, dtype="float64")
    home_marg, away_marg = pmf.sum(axis=1), pmf.sum(axis=0)
    idx_h, idx_a = np.indices(pmf.shape)
    return {
        "p_cs_home": float(pmf[:, 0].sum()),
        "p_cs_away": float(pmf[0, :].sum()),
        "e_gc_home": float((away_marg * goals).sum()),
        "e_gc_away": float((home_marg * goals).sum()),
        "p_home_win": float(pmf[idx_h > idx_a].sum()),
        "p_draw": float(pmf[idx_h == idx_a].sum()),
        "p_away_win": float(pmf[idx_h < idx_a].sum()),
        "p_gc2_home": float(pmf[:, 2:].sum()),
        "p_gc2_away": float(pmf[2:, :].sum()),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_dixon_coles.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/models/dixon_coles.py tests/test_dixon_coles.py
git commit -m "feat: Dixon-Coles scoreline pmf with the low-score correction

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 6: `DixonColesModel.fit` — weighted MLE

**Files:**
- Modify: `src/gaffer/models/dixon_coles.py` (append after `fixture_outcomes`)
- Test: `tests/test_dixon_coles.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_dixon_coles.py`:

```python
from gaffer.models.dixon_coles import DEFAULT_XI, DixonColesModel
from gaffer.models.team import build_team_gw


def _synthetic_fixtures(attack, defence, gamma=0.28, repeats=8, seed=7,
                        season_idx=0, start_day=0):
    """Double round-robins sampled from known Dixon-Coles parameters."""
    rng = np.random.default_rng(seed)
    n = len(attack)
    rows, day = [], start_day
    for _ in range(repeats):
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                lam = math.exp(attack[i] + defence[j] + gamma)
                mu = math.exp(attack[j] + defence[i])
                rows.append({
                    "season_idx": season_idx, "gw": 1 + day // 20,
                    "kickoff_time": (pd.Timestamp("2020-01-01", tz="UTC")
                                     + pd.Timedelta(days=day)).isoformat(),
                    "home_code": i, "away_code": j,
                    "home_goals": int(rng.poisson(lam)),
                    "away_goals": int(rng.poisson(mu))})
                day += 1
    return pd.DataFrame(rows)


_TRUE_ATTACK = np.linspace(0.5, -0.5, 12) - np.linspace(0.5, -0.5, 12).mean()
_TRUE_DEFENCE = np.linspace(-0.4, 0.4, 12)


def _fitted(xi=0.0):
    fx = _synthetic_fixtures(_TRUE_ATTACK, _TRUE_DEFENCE)
    return DixonColesModel(xi=xi).fit(build_team_gw(fx)), fx


def test_matches_from_team_gw_rebuilds_one_row_per_match():
    fx = _synthetic_fixtures(_TRUE_ATTACK, _TRUE_DEFENCE, repeats=1)
    tg = build_team_gw(fx)
    matches = DixonColesModel.matches_from_team_gw(tg)
    assert len(matches) == len(fx)
    assert set(matches.columns) >= {"season_idx", "gw", "kickoff_time",
                                    "home_code", "away_code", "home_goals",
                                    "away_goals"}
    assert matches["home_goals"].sum() == fx["home_goals"].sum()


def test_fit_recovers_the_attack_parameters():
    model, _ = _fitted()
    fitted = np.array([model.attack_[c] for c in range(12)])
    assert np.abs(fitted - _TRUE_ATTACK).max() < 0.25
    assert np.corrcoef(fitted, _TRUE_ATTACK)[0, 1] > 0.9


def test_fit_recovers_the_defence_parameters_up_to_the_shared_level():
    """Only differences are identified: the attack constraint fixes the
    overall scale, and a constant added to every defence is absorbed by the
    attacks."""
    model, _ = _fitted()
    fitted = np.array([model.defence_[c] for c in range(12)])
    centred = fitted - fitted.mean()
    assert np.abs(centred - (_TRUE_DEFENCE - _TRUE_DEFENCE.mean())).max() < 0.25


def test_fit_recovers_the_home_advantage():
    model, _ = _fitted()
    assert abs(model.gamma_ - 0.28) < 0.1


def test_fit_holds_mean_log_attack_at_zero():
    """Identifiability: without it every attack could rise by a constant and
    every defence fall by the same one with no change in likelihood."""
    model, _ = _fitted()
    assert abs(float(np.mean(list(model.attack_.values())))) < 1e-9


def test_fit_keeps_rho_inside_its_bracket():
    model, _ = _fitted()
    assert RHO_BOUNDS[0] <= model.rho_ <= RHO_BOUNDS[1]


def _two_era_fixtures(seed=5):
    """A team that was poor for six round-robins and good for six."""
    n, rows, day = 6, [], 0
    rng = np.random.default_rng(seed)
    for boost in (-0.6, 0.8):
        for _ in range(6):
            for i in range(n):
                for j in range(n):
                    if i == j:
                        continue
                    a = [0.0] * n
                    a[0] = boost
                    lam = math.exp(a[i] + 0.25)
                    mu = math.exp(a[j])
                    rows.append({
                        "season_idx": 0, "gw": 1 + day // 20,
                        "kickoff_time": (pd.Timestamp("2020-01-01", tz="UTC")
                                         + pd.Timedelta(days=day)).isoformat(),
                        "home_code": i, "away_code": j,
                        "home_goals": int(rng.poisson(lam)),
                        "away_goals": int(rng.poisson(mu))})
                    day += 1
    return pd.DataFrame(rows)


def test_decay_pulls_the_fit_toward_recent_form():
    """The reason the decay exists: a team that improved halfway through has
    to read as good now, not as the average of its two selves."""
    tg = build_team_gw(_two_era_fixtures())
    flat = DixonColesModel(xi=0.0).fit(tg).attack_[0]
    decayed = DixonColesModel(xi=0.02).fit(tg).attack_[0]
    assert decayed > flat + 0.2


def test_default_xi_is_the_pinned_constant():
    assert DixonColesModel().xi == DEFAULT_XI


def test_fit_stores_a_promoted_team_fallback_from_the_bottom_three():
    """A newly-promoted club has no Premier League history at all; the
    bottom three of the latest season are the closest thing to a prior."""
    model, _ = _fitted()
    bottom = model.bottom_codes_
    assert len(bottom) == 3
    assert abs(model.fallback_attack_
               - float(np.mean([model.attack_[c] for c in bottom]))) < 1e-12
    assert abs(model.fallback_defence_
               - float(np.mean([model.defence_[c] for c in bottom]))) < 1e-12


def test_the_bottom_three_are_the_weakest_teams_in_the_latest_season():
    model, _ = _fitted()
    # Attack was built descending, so the weakest codes are the last three.
    assert set(model.bottom_codes_) <= {9, 10, 11}


def test_fit_on_a_single_round_robin_still_converges():
    fx = _synthetic_fixtures(_TRUE_ATTACK, _TRUE_DEFENCE, repeats=1)
    model = DixonColesModel().fit(build_team_gw(fx))
    assert len(model.attack_) == 12
    assert np.isfinite(model.gamma_)
```

Add `RHO_BOUNDS` to the file's existing import from `gaffer.models.dixon_coles`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dixon_coles.py -k recovers -v`
Expected: FAIL — `ImportError: cannot import name 'DixonColesModel' from 'gaffer.models.dixon_coles'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/gaffer/models/dixon_coles.py`:

```python
PARAM_BOUNDS = (-3.0, 3.0)
"""Bracket on log attack/defence. exp(3) = 20 goals expected — no real team
is anywhere near it, and the bound keeps L-BFGS-B out of the flat regions a
club with three matches of history can otherwise wander into."""

GAMMA_BOUNDS = (-1.0, 1.0)
MAX_ITER = 500
PROMOTED_FALLBACK_TEAMS = 3
"""How many bottom finishers the promoted-team prior averages. Three is the
number that go down, so it is exactly the group the promoted clubs replace."""


def _unpack(theta: np.ndarray, n: int):
    """Free parameter vector -> (attack, defence, gamma, rho).

    Attack carries only ``n - 1`` free values; the last is minus their sum,
    which *is* the mean(log attack) = 0 constraint. Reparameterizing rather
    than adding an equality constraint keeps the problem inside L-BFGS-B,
    which is bound-constrained only and much faster than the alternatives.
    """
    free = theta[:n - 1]
    attack = np.empty(n)
    attack[:n - 1] = free
    attack[n - 1] = -free.sum()
    defence = theta[n - 1:2 * n - 1]
    return attack, defence, float(theta[2 * n - 1]), float(theta[2 * n])


def _tau_vec(x: np.ndarray, y: np.ndarray, lam: np.ndarray, mu: np.ndarray,
             rho: float) -> np.ndarray:
    """:func:`tau_correction` over whole arrays of matches."""
    out = np.ones_like(lam)
    out = np.where((x == 0) & (y == 0), 1.0 - lam * mu * rho, out)
    out = np.where((x == 0) & (y == 1), 1.0 + lam * rho, out)
    out = np.where((x == 1) & (y == 0), 1.0 + mu * rho, out)
    out = np.where((x == 1) & (y == 1), 1.0 - rho, out)
    return out


def _nll(theta, hi, ai, hg, ag, lgh, lga, w, n) -> float:
    """Negative time-weighted log likelihood of every match at once."""
    attack, defence, gamma, rho = _unpack(theta, n)
    log_lam = attack[hi] + defence[ai] + gamma
    log_mu = attack[ai] + defence[hi]
    lam, mu = np.exp(log_lam), np.exp(log_mu)
    # A tau driven negative by an extreme rho would make the log undefined;
    # clipping turns that into a very bad likelihood instead of a crash, and
    # the optimizer walks back out on its own.
    tau = np.clip(_tau_vec(hg, ag, lam, mu, rho), 1e-10, None)
    ll = np.log(tau) + hg * log_lam - lam - lgh + ag * log_mu - mu - lga
    return -float(np.dot(w, ll))


class DixonColesModel:
    """P(clean sheet) and E[goals conceded] from a fitted scoreline model.

    Interface-compatible with :class:`gaffer.models.team.TeamModel`: same
    ``fit(team_gw)`` input frame, same ``predict(team_gw)`` output columns
    ``[code, season_idx, gw, p_cs, e_gc]``. That parity is the whole point —
    it makes the swap a single constructor site in
    :func:`gaffer.models.train.train_all` and leaves the protected
    ``blend_team_odds(`` -> ``comp.merge(tp`` seam untouched.

    ``fit`` takes the *team-gw* frame rather than a fixture frame, even
    though the model is fundamentally about matches, because that is what the
    training path already has in hand; the home rows are folded back into
    matches internally.
    """

    def __init__(self, xi: float = DEFAULT_XI, cap: int = GOAL_CAP):
        self.xi = float(xi)
        self.cap = int(cap)

    @staticmethod
    def matches_from_team_gw(tg: pd.DataFrame) -> pd.DataFrame:
        """Fold the two rows per match back into one.

        ``build_team_gw`` doubles every fixture so each team owns a row; the
        home rows alone carry the whole match, opponent and both scorelines
        included.
        """
        home = tg[tg["home"] == 1.0]
        return pd.DataFrame({
            "season_idx": home["season_idx"].to_numpy(),
            "gw": home["gw"].to_numpy(),
            "kickoff_time": home["kickoff_time"].to_numpy(),
            "home_code": home["code"].to_numpy(),
            "away_code": home["opp_code"].to_numpy(),
            "home_goals": pd.to_numeric(home["gf"], errors="coerce").to_numpy(),
            "away_goals": pd.to_numeric(home["ga"], errors="coerce").to_numpy(),
        }).dropna(subset=["home_goals", "away_goals"]).reset_index(drop=True)

    def _fallback(self, matches: pd.DataFrame, codes: list,
                  attack: np.ndarray, defence: np.ndarray) -> None:
        """Prior for a club with no top-flight history: the mean of the
        bottom three finishers' parameters.

        A promoted side is, on the evidence, about as good as the sides it
        replaced, and that is a far better opening prior than either the
        league mean (too generous) or the worst team (too harsh).
        """
        index = {c: i for i, c in enumerate(codes)}
        latest = matches[matches["season_idx"] == matches["season_idx"].max()]
        points: dict = {c: 0.0 for c in codes}
        for m in latest.itertuples():
            if m.home_goals > m.away_goals:
                points[m.home_code] += 3.0
            elif m.home_goals < m.away_goals:
                points[m.away_code] += 3.0
            else:
                points[m.home_code] += 1.0
                points[m.away_code] += 1.0
        order = sorted(points, key=lambda c: (points[c], c))
        bottom = order[:PROMOTED_FALLBACK_TEAMS]
        self.bottom_codes_ = bottom
        self.fallback_attack_ = float(np.mean([attack[index[c]] for c in bottom]))
        self.fallback_defence_ = float(
            np.mean([defence[index[c]] for c in bottom]))

    def fit(self, tg: pd.DataFrame) -> "DixonColesModel":
        """Weighted MLE over every completed match in the frame.

        Each match is weighted ``exp(-xi * days)`` back from the newest
        kickoff present, so the fit is always anchored on the data's own end
        rather than on wall-clock now — which is what makes a backtest at an
        earlier cut behave like a live run at that date.
        """
        from scipy.optimize import minimize
        from scipy.special import gammaln

        matches = self.matches_from_team_gw(tg)
        codes = sorted(set(matches["home_code"]) | set(matches["away_code"]))
        index = {c: i for i, c in enumerate(codes)}
        n = len(codes)
        hi = matches["home_code"].map(index).to_numpy()
        ai = matches["away_code"].map(index).to_numpy()
        hg = matches["home_goals"].to_numpy(dtype="float64")
        ag = matches["away_goals"].to_numpy(dtype="float64")
        lgh, lga = gammaln(hg + 1.0), gammaln(ag + 1.0)
        kt = pd.to_datetime(matches["kickoff_time"], utc=True, format="mixed")
        days = (kt.max() - kt).dt.total_seconds().to_numpy() / 86400.0
        weights = np.exp(-self.xi * days)

        x0 = np.concatenate([np.zeros(2 * n - 1), [0.25], [0.0]])
        bounds = ([PARAM_BOUNDS] * (2 * n - 1) + [GAMMA_BOUNDS] + [RHO_BOUNDS])
        res = minimize(_nll, x0,
                       args=(hi, ai, hg, ag, lgh, lga, weights, n),
                       method="L-BFGS-B", bounds=bounds,
                       options={"maxiter": MAX_ITER})
        attack, defence, gamma, rho = _unpack(res.x, n)
        self.codes_ = codes
        self.attack_ = {c: float(attack[index[c]]) for c in codes}
        self.defence_ = {c: float(defence[index[c]]) for c in codes}
        self.gamma_, self.rho_ = gamma, rho
        self.converged_ = bool(res.success)
        self._fallback(matches, codes, attack, defence)
        return self
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_dixon_coles.py -v`
Expected: PASS (22 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/models/dixon_coles.py tests/test_dixon_coles.py
git commit -m "feat: time-decayed weighted MLE fit for Dixon-Coles

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 7: `DixonColesModel.predict` — the TeamModel contract

**Files:**
- Modify: `src/gaffer/models/dixon_coles.py` (append inside `DixonColesModel`)
- Test: `tests/test_dixon_coles.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_dixon_coles.py`:

```python
def _future_rows(codes=(0, 1), opp=(1, 0), home=(1.0, 0.0)):
    return pd.DataFrame([
        {"code": c, "opp_code": o, "home": h, "season_idx": 1, "gw": 5,
         "kickoff_time": "2021-01-01T15:00:00Z"}
        for c, o, h in zip(codes, opp, home)])


def test_predict_returns_the_team_model_contract_columns():
    """Parity with TeamModel is the whole reason the swap is one line."""
    from gaffer.models.team import TeamModel

    model, _ = _fitted()
    out = model.predict(_future_rows())
    assert list(out.columns) == ["code", "season_idx", "gw", "p_cs", "e_gc"]
    assert len(out) == 2

    gbm = TeamModel(feature_cols=["home"])
    tg = build_team_gw(_synthetic_fixtures(_TRUE_ATTACK, _TRUE_DEFENCE,
                                           repeats=1))
    gbm.fit(tg)
    assert list(gbm.predict(tg.head(2)).columns) == list(out.columns)


def test_predict_is_row_for_row_with_its_input():
    """Every caller stitches component outputs positionally, so a dropped or
    reordered row silently misattributes a clean sheet."""
    model, _ = _fitted()
    rows = _future_rows(codes=(3, 7, 3), opp=(7, 3, 7),
                        home=(1.0, 0.0, 0.0))
    out = model.predict(rows)
    assert list(out["code"]) == [3, 7, 3]


def test_predict_probabilities_are_in_range():
    model, _ = _fitted()
    out = model.predict(_future_rows(codes=tuple(range(12)),
                                     opp=tuple(reversed(range(12))),
                                     home=tuple([1.0] * 12)))
    assert (out["p_cs"] >= 0.0).all() and (out["p_cs"] <= 1.0).all()
    assert (out["e_gc"] >= 0.0).all()


def test_predict_gives_the_stronger_team_the_better_clean_sheet():
    model, _ = _fitted()
    out = model.predict(_future_rows(codes=(0, 11), opp=(11, 0),
                                     home=(1.0, 0.0)))
    assert out.loc[0, "p_cs"] > out.loc[1, "p_cs"]
    assert out.loc[1, "e_gc"] > out.loc[0, "e_gc"]


def test_predict_home_advantage_helps_the_same_pairing():
    model, _ = _fitted()
    at_home = model.predict(_future_rows(codes=(4,), opp=(5,), home=(1.0,)))
    away = model.predict(_future_rows(codes=(4,), opp=(5,), home=(0.0,)))
    assert at_home.loc[0, "e_gc"] < away.loc[0, "e_gc"]


def test_predict_uses_the_promoted_fallback_for_an_unseen_club():
    """A promoted club appears in the fixture list with no history at all;
    predicting NaN for it would knock out every player in its squad."""
    model, _ = _fitted()
    out = model.predict(_future_rows(codes=(999,), opp=(0,), home=(1.0,)))
    assert out["p_cs"].notna().all()
    assert 0.0 < float(out.loc[0, "p_cs"]) < 1.0


def test_predict_treats_two_unseen_clubs_as_equals():
    model, _ = _fitted()
    out = model.predict(_future_rows(codes=(999, 998), opp=(998, 999),
                                     home=(1.0, 0.0)))
    # Same parameters both sides: only the home advantage separates them.
    assert out.loc[0, "p_cs"] > out.loc[1, "p_cs"]


def test_predict_handles_a_double_gameweek_row_pair():
    """The team-future frame is already one row per fixture, so a DGW needs
    nothing special — but it must not be collapsed."""
    model, _ = _fitted()
    rows = _future_rows(codes=(2, 2), opp=(6, 8), home=(1.0, 0.0))
    out = model.predict(rows)
    assert len(out) == 2
    assert out["p_cs"].nunique() == 2


def test_predict_without_a_home_column_treats_every_row_as_neutral():
    """Frames from the simple component path carry no ``home``; a KeyError
    there would take the whole backtest down."""
    model, _ = _fitted()
    rows = _future_rows().drop(columns=["home"])
    out = model.predict(rows)
    assert out["p_cs"].notna().all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dixon_coles.py -k predict -v`
Expected: FAIL — `AttributeError: 'DixonColesModel' object has no attribute 'predict'`

- [ ] **Step 3: Write minimal implementation**

Append inside `DixonColesModel` in `src/gaffer/models/dixon_coles.py`:

```python
    def _params(self, code) -> tuple[float, float]:
        """Attack/defence for one club, promoted fallback where unseen."""
        return (self.attack_.get(code, self.fallback_attack_),
                self.defence_.get(code, self.fallback_defence_))

    def predict(self, tg: pd.DataFrame) -> pd.DataFrame:
        """One row per input row: code, season_idx, gw, p_cs, e_gc.

        Byte-for-byte the same contract as :meth:`TeamModel.predict`, and
        positional like every other component: a double gameweek's two
        fixtures stay two rows, because the caller stitches on position and
        would otherwise attach one fixture's clean sheet to both.

        A row whose ``home`` is missing is treated as neutral (no home
        advantage either way) rather than raising — the simple component path
        hands over frames without it.
        """
        out = tg[["code", "season_idx", "gw"]].copy().reset_index(drop=True)
        rows = tg.reset_index(drop=True)
        home = (pd.to_numeric(rows["home"], errors="coerce").fillna(0.5)
                if "home" in rows.columns
                else pd.Series(0.5, index=rows.index, dtype="float64"))
        p_cs, e_gc = [], []
        for code, opp, is_home in zip(rows["code"], rows["opp_code"], home):
            att, dfn = self._params(code)
            opp_att, opp_dfn = self._params(opp)
            # gamma is the *home* team's edge; a neutral 0.5 splits it, which
            # is what a frame with no home flag deserves.
            lam = math.exp(att + opp_dfn + self.gamma_ * float(is_home))
            mu = math.exp(opp_att + dfn
                          + self.gamma_ * (1.0 - float(is_home)))
            stats = fixture_outcomes(lam, mu, self.rho_, self.cap)
            p_cs.append(stats["p_cs_home"])
            e_gc.append(stats["e_gc_home"])
        out["p_cs"] = p_cs
        out["e_gc"] = e_gc
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_dixon_coles.py -v`
Expected: PASS (31 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/models/dixon_coles.py tests/test_dixon_coles.py
git commit -m "feat: DixonColesModel.predict matching the TeamModel contract

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 8: Switch the training path to Dixon-Coles

`TeamModel` stays in the codebase for one cycle as the fallback if gate G1
fails — spec §9 — so this task adds a switch, not a deletion.

**Files:**
- Modify: `src/gaffer/models/train.py:30-31` (imports), `:277-305` (`train_all`)
- Test: `tests/test_train.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_train.py`:

```python
# --- the team head is Dixon-Coles now -------------------------------------

def test_build_team_model_returns_the_dixon_coles_model():
    from gaffer.models.dixon_coles import DixonColesModel
    from gaffer.models.train import build_team_model

    assert isinstance(build_team_model(), DixonColesModel)


def test_build_team_model_can_still_produce_the_gbm_fallback(monkeypatch):
    """G1 may fail. TeamModel stays for one cycle, reachable by flipping one
    constant rather than by reverting a commit."""
    from gaffer.models import train as train_mod
    from gaffer.models.team import TeamModel

    monkeypatch.setattr(train_mod, "TEAM_MODEL", "gbm")
    assert isinstance(train_mod.build_team_model(), TeamModel)


def test_train_all_fits_the_team_head_through_the_single_constructor_site():
    """One site is what keeps the protected blend seam untouched: nothing
    downstream of train_all knows which class it got."""
    import inspect

    from gaffer.models.train import train_all

    src = inspect.getsource(train_all)
    assert "build_team_model()" in src
    assert "TeamModel(" not in src
    assert "DixonColesModel(" not in src


def test_train_all_team_head_predicts_the_contract_frame():
    models = train_all(_player_frame(seasons=(0, 1)),
                       _team_frame(seasons=(0, 1)), save=False)
    tg = _team_frame(seasons=(0, 1))
    out = models["team"].predict(tg.dropna(subset=["elo_diff"]))
    assert list(out.columns) == ["code", "season_idx", "gw", "p_cs", "e_gc"]
    assert len(out) == len(tg.dropna(subset=["elo_diff"]))
```

`_team_frame` must supply what `build_team_gw`-shaped frames carry. Check the
existing helper in `tests/test_train.py`: if it does not already emit
`kickoff_time`, `home`, `opp_code`, `gf` and `ga`, extend it to do so — those
are the columns `DixonColesModel.matches_from_team_gw` folds back into
matches, and `add_team_rolling` already assumes most of them.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_train.py -k build_team_model -v`
Expected: FAIL — `ImportError: cannot import name 'build_team_model' from 'gaffer.models.train'`

- [ ] **Step 3: Write minimal implementation**

In `src/gaffer/models/train.py`, add the import beside the existing team import:

```python
from gaffer.models.dixon_coles import DixonColesModel
from gaffer.models.team import (TEAM_FEATURES, TeamModel, add_team_rolling,
                                build_team_gw)
```

Add the switch above `train_all`:

```python
TEAM_MODEL = "dixon_coles"
"""Which class predicts team clean sheets and goals conceded.

``"dixon_coles"`` is the shipped head: one fitted scoreline distribution per
fixture, which the v4b measurement showed beats the GBM pair on CS log loss.
``"gbm"`` restores :class:`gaffer.models.team.TeamModel`, kept for one cycle
so a regression is a one-constant revert rather than an archaeology exercise.
"""


def build_team_model():
    """The team head, constructed in exactly one place.

    Both classes expose the same ``fit(team_gw)`` / ``predict(team_gw) ->
    [code, season_idx, gw, p_cs, e_gc]`` contract, so nothing downstream —
    ``advise.predict_components`` and its protected ``blend_team_odds(``
    before ``comp.merge(tp`` seam included — can tell which one it is holding.
    """
    if TEAM_MODEL == "dixon_coles":
        return DixonColesModel()
    return TeamModel(TEAM_FEATURES)
```

And in `train_all`, replace the team line:

```python
    team = build_team_model().fit(tg.dropna(subset=["elo_diff"]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_train.py -v`
Expected: PASS (whole file)

Run: `uv run pytest`
Expected: PASS — in particular `tests/test_odds.py`, `tests/test_assemble.py`
and `tests/test_advise.py`'s source-text tests, which must not have moved

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/models/train.py tests/test_train.py
git commit -m "feat: train the team head as Dixon-Coles behind one constructor site

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 9: Walk-forward CS frame and the fitted blend weight

`ODDS_BLEND_WEIGHT = 0.7` was a guess, and a guess with a train/serve skew
baked in: nothing ever checked how much of the truth is in the market versus
the model. With `match_odds.parquet` in hand it becomes a one-parameter fit.

**Files:**
- Modify: `src/gaffer/models/dixon_coles.py` (append `walk_forward_cs`)
- Modify: `src/gaffer/models/team.py` (append `fit_blend_weight`)
- Modify: `src/gaffer/models/persistence.py` (append params helpers)
- Test: `tests/test_dixon_coles.py` (append)
- Test: `tests/test_artifacts.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_dixon_coles.py`:

```python
from gaffer.models.dixon_coles import walk_forward_cs
from gaffer.models.team import fit_blend_weight


def test_fit_blend_weight_recovers_a_pure_odds_mixture():
    """If the odds column is the truth and the model column is noise, the
    fit has to land on w = 1."""
    rng = np.random.default_rng(0)
    p = rng.uniform(0.05, 0.95, 4000)
    cs = (rng.random(4000) < p).astype(float)
    frame = pd.DataFrame({"p_cs_odds": p, "p_cs_model": rng.random(4000),
                          "cs": cs})
    assert fit_blend_weight(frame) >= 0.95


def test_fit_blend_weight_recovers_a_pure_model_mixture():
    rng = np.random.default_rng(1)
    p = rng.uniform(0.05, 0.95, 4000)
    cs = (rng.random(4000) < p).astype(float)
    frame = pd.DataFrame({"p_cs_odds": rng.random(4000), "p_cs_model": p,
                          "cs": cs})
    assert fit_blend_weight(frame) <= 0.05


def test_fit_blend_weight_lands_between_two_noisy_signals():
    """Both sides carry the signal plus independent noise, so neither alone
    is optimal and the fit has to compromise."""
    rng = np.random.default_rng(2)
    truth = rng.uniform(0.1, 0.9, 8000)
    cs = (rng.random(8000) < truth).astype(float)
    jitter = lambda: np.clip(truth + rng.normal(0, 0.12, 8000), 0.01, 0.99)
    frame = pd.DataFrame({"p_cs_odds": jitter(), "p_cs_model": jitter(),
                          "cs": cs})
    w = fit_blend_weight(frame)
    assert 0.2 < w < 0.8


def test_fit_blend_weight_is_quantized_to_two_decimals():
    rng = np.random.default_rng(3)
    frame = pd.DataFrame({"p_cs_odds": rng.random(500),
                          "p_cs_model": rng.random(500),
                          "cs": rng.integers(0, 2, 500).astype(float)})
    w = fit_blend_weight(frame)
    assert w == round(w, 2)
    assert 0.0 <= w <= 1.0


def test_fit_blend_weight_on_an_empty_frame_returns_the_constant():
    from gaffer.models.team import ODDS_BLEND_WEIGHT

    empty = pd.DataFrame(columns=["p_cs_odds", "p_cs_model", "cs"])
    assert fit_blend_weight(empty) == ODDS_BLEND_WEIGHT


def test_fit_blend_weight_ignores_rows_missing_either_side():
    frame = pd.DataFrame({"p_cs_odds": [0.9, float("nan"), 0.8],
                          "p_cs_model": [0.9, 0.5, float("nan")],
                          "cs": [1.0, 0.0, 1.0]})
    assert fit_blend_weight(frame) == round(fit_blend_weight(frame.head(1)), 2)


def _odds_for(fx: pd.DataFrame) -> pd.DataFrame:
    """Closing-odds rows for every fixture, priced off the true scoreline."""
    rows = []
    for m in fx.itertuples():
        total = m.home_goals + m.away_goals
        rows.append({"season_idx": m.season_idx, "gw": m.gw,
                     "kickoff_time": m.kickoff_time,
                     "home_code": m.home_code, "away_code": m.away_code,
                     "p_home": 0.45, "p_draw": 0.27, "p_away": 0.28,
                     "p_over25": 0.6 if total >= 3 else 0.4})
    return pd.DataFrame(rows)


def test_walk_forward_cs_predicts_each_half_from_earlier_data_only():
    fx = pd.concat([
        _synthetic_fixtures(_TRUE_ATTACK, _TRUE_DEFENCE, repeats=3,
                            season_idx=0, seed=4),
        _synthetic_fixtures(_TRUE_ATTACK, _TRUE_DEFENCE, repeats=3,
                            season_idx=1, seed=5, start_day=800),
    ], ignore_index=True)
    tg = build_team_gw(fx)
    out = walk_forward_cs(tg, _odds_for(fx), xi=DEFAULT_XI)
    assert set(out.columns) == {"season_idx", "gw", "code", "opp_code",
                                "p_cs_odds", "p_cs_model", "cs"}
    # The first half has nothing before it and is not scored.
    assert out["season_idx"].min() >= 0
    assert len(out) > 0
    assert out["p_cs_model"].between(0.0, 1.0).all()
    assert out["p_cs_odds"].between(0.0, 1.0).all()
    assert set(out["cs"].unique()) <= {0.0, 1.0}


def test_walk_forward_cs_without_odds_returns_an_empty_frame():
    """No football-data file means no fittable weight — and the caller has to
    fall back to the constant rather than fit on nothing."""
    fx = _synthetic_fixtures(_TRUE_ATTACK, _TRUE_DEFENCE, repeats=2)
    out = walk_forward_cs(build_team_gw(fx),
                          pd.DataFrame(columns=["season_idx", "gw",
                                                "home_code", "away_code",
                                                "p_home", "p_draw", "p_away",
                                                "p_over25"]),
                          xi=DEFAULT_XI)
    assert out.empty
```

Append to `tests/test_artifacts.py`:

```python
def test_save_and_load_params_round_trip(tmp_path, monkeypatch):
    import gaffer.models.persistence as persistence

    monkeypatch.setattr(persistence, "MODELS_DIR", tmp_path)
    persistence.save_params("blend", {"odds_blend_weight": 0.62})
    assert persistence.params_exist("blend")
    assert persistence.load_params("blend")["odds_blend_weight"] == 0.62


def test_params_exist_is_false_before_anything_is_saved(tmp_path, monkeypatch):
    import gaffer.models.persistence as persistence

    monkeypatch.setattr(persistence, "MODELS_DIR", tmp_path)
    assert persistence.params_exist("blend") is False


def test_load_params_on_a_missing_file_returns_an_empty_dict(tmp_path,
                                                             monkeypatch):
    """A fresh clone has no artifacts; every reader falls back to its own
    default rather than crashing on the way to a first train."""
    import gaffer.models.persistence as persistence

    monkeypatch.setattr(persistence, "MODELS_DIR", tmp_path)
    assert persistence.load_params("blend") == {}


def test_save_params_stamps_the_save_time(tmp_path, monkeypatch):
    import gaffer.models.persistence as persistence

    monkeypatch.setattr(persistence, "MODELS_DIR", tmp_path)
    persistence.save_params("blend", {"odds_blend_weight": 0.5})
    assert "saved_at" in persistence.load_params("blend")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_artifacts.py -k params -v`
Expected: FAIL — `AttributeError: module 'gaffer.models.persistence' has no attribute 'save_params'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/gaffer/models/persistence.py`:

```python
def save_params(name: str, params: dict) -> Path:
    """Write a small JSON artifact to ``models/<name>.params.json``.

    Not everything the training run learns is a pickle. The fitted odds blend
    weight is one float, read at prediction time by code that has no business
    unpickling a model to get it, and worth being able to read with ``cat``
    when a number in a report looks wrong. Same ``saved_at`` stamp as
    :func:`save_model`, for the same reason.
    """
    MODELS_DIR.mkdir(exist_ok=True)
    path = MODELS_DIR / f"{name}.params.json"
    payload = dict(params)
    payload["saved_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(payload, indent=1))
    return path


def params_exist(name: str) -> bool:
    return (MODELS_DIR / f"{name}.params.json").exists()


def load_params(name: str) -> dict:
    """A previously saved params artifact, or ``{}`` when there is none.

    Empty rather than an exception: a fresh clone has no artifacts, and every
    reader here has a documented default to fall back to.
    """
    path = MODELS_DIR / f"{name}.params.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())
```

Append to `src/gaffer/models/dixon_coles.py`:

```python
BLEND_FOLDS_PER_SEASON = 2
"""Walk-forward granularity for the blend-weight frame.

Refitting Dixon-Coles before every fixture would be honest and unusable; per
half-season it is 10 fits over five seasons, each on strictly earlier data.
The weight being estimated is one scalar, and it does not move at the
resolution the extra fidelity would buy.
"""


def walk_forward_cs(tg: pd.DataFrame, match_odds: pd.DataFrame,
                    xi: float = DEFAULT_XI) -> pd.DataFrame:
    """Out-of-sample model and odds clean-sheet probabilities, side by side.

    For each half-season fold after the first, Dixon-Coles is fitted on every
    match strictly before the fold and used to predict the fold's fixtures;
    the closing odds for the same fixtures are inverted to independent-Poisson
    mus and turned into ``p_cs_odds = exp(-mu_against)``, the identical
    assumption :func:`gaffer.models.team.blend_team_odds` makes at serve time.
    Realized ``cs`` comes along as the target.

    Returns ``[season_idx, gw, code, opp_code, p_cs_odds, p_cs_model, cs]``,
    two rows per priced fixture. An empty frame means there is nothing to fit
    a weight on — no odds file, or no fold with data on both sides.
    """
    from gaffer.data.odds import invert_odds

    if match_odds is None or match_odds.empty:
        return pd.DataFrame(columns=["season_idx", "gw", "code", "opp_code",
                                     "p_cs_odds", "p_cs_model", "cs"])
    # Odds -> per-team expected goals against, once for the whole history.
    mus = [invert_odds(float(m.p_home), float(m.p_draw), float(m.p_away),
                       float(m.p_over25)) for m in match_odds.itertuples()]
    odds_rows = []
    for (mu_h, mu_a), m in zip(mus, match_odds.itertuples()):
        odds_rows.append({"season_idx": m.season_idx, "gw": m.gw,
                          "code": m.home_code, "opp_code": m.away_code,
                          "p_cs_odds": math.exp(-mu_a)})
        odds_rows.append({"season_idx": m.season_idx, "gw": m.gw,
                          "code": m.away_code, "opp_code": m.home_code,
                          "p_cs_odds": math.exp(-mu_h)})
    odds_cs = pd.DataFrame(odds_rows)

    played = tg.dropna(subset=["ga"]).copy()
    played["_fold"] = (played["season_idx"].astype(int) * BLEND_FOLDS_PER_SEASON
                       + (played["gw"].astype(int) > 19).astype(int))
    folds = sorted(played["_fold"].unique())
    out = []
    for fold in folds[1:]:
        before = played[played["_fold"] < fold]
        current = played[played["_fold"] == fold]
        if before.empty or current.empty:
            continue
        model = DixonColesModel(xi=xi).fit(before)
        pred = model.predict(current)
        block = current[["season_idx", "gw", "code", "opp_code", "cs"]].copy()
        block = block.reset_index(drop=True)
        block["p_cs_model"] = pred["p_cs"].to_numpy()
        out.append(block)
    if not out:
        return pd.DataFrame(columns=["season_idx", "gw", "code", "opp_code",
                                     "p_cs_odds", "p_cs_model", "cs"])
    frame = pd.concat(out, ignore_index=True).merge(
        odds_cs, on=["season_idx", "gw", "code", "opp_code"], how="inner")
    frame["cs"] = pd.to_numeric(frame["cs"], errors="coerce").astype(float)
    return frame[["season_idx", "gw", "code", "opp_code", "p_cs_odds",
                  "p_cs_model", "cs"]]
```

Append to `src/gaffer/models/team.py` (imports first: `from gaffer.models.persistence import load_params, params_exist`):

```python
BLEND_PARAMS_NAME = "blend"
BLEND_GRID_STEP = 0.01


def fit_blend_weight(frame: pd.DataFrame,
                     step: float = BLEND_GRID_STEP) -> float:
    """The convex weight on the market, fitted by log loss.

    ``frame`` is :func:`gaffer.models.dixon_coles.walk_forward_cs`'s output:
    out-of-sample ``p_cs_model``, market ``p_cs_odds`` and the realized
    ``cs``. One scalar over ``[0, 1]``, so a grid at 0.01 is both exhaustive
    and instant — no optimizer, no local minimum to worry about.

    Log loss rather than Brier or accuracy because calibration is the thing
    the number is for: the MILP multiplies this probability by points, so
    being right on average and wrong in every bin is the failure mode that
    matters. An empty or unusable frame falls back to
    :data:`ODDS_BLEND_WEIGHT`, which is exactly what it was there for.
    """
    cols = ["p_cs_odds", "p_cs_model", "cs"]
    if frame is None or frame.empty or any(c not in frame for c in cols):
        return ODDS_BLEND_WEIGHT
    sub = frame[cols].apply(pd.to_numeric, errors="coerce").dropna()
    if sub.empty:
        return ODDS_BLEND_WEIGHT
    odds = sub["p_cs_odds"].to_numpy(dtype="float64")
    model = sub["p_cs_model"].to_numpy(dtype="float64")
    y = sub["cs"].to_numpy(dtype="float64")
    best_w, best_loss = ODDS_BLEND_WEIGHT, float("inf")
    for i in range(int(round(1.0 / step)) + 1):
        w = round(i * step, 2)
        p = np.clip(w * odds + (1.0 - w) * model, 1e-12, 1.0 - 1e-12)
        loss = float(-(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)).mean())
        if loss < best_loss:
            best_loss, best_w = loss, w
    return best_w


def odds_blend_weight() -> float:
    """The fitted weight from the artifact bundle, else the constant.

    Read at prediction time rather than baked into the pickle so a refit of
    the weight alone is possible, and so the number is greppable on disk when
    a blended clean sheet looks wrong.
    """
    if not params_exist(BLEND_PARAMS_NAME):
        return ODDS_BLEND_WEIGHT
    stored = load_params(BLEND_PARAMS_NAME).get("odds_blend_weight")
    return ODDS_BLEND_WEIGHT if stored is None else float(stored)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_artifacts.py tests/test_dixon_coles.py -v`
Expected: PASS (4 new in `test_artifacts.py`, 40 in `test_dixon_coles.py`)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/models/persistence.py src/gaffer/models/dixon_coles.py src/gaffer/models/team.py tests/test_artifacts.py tests/test_dixon_coles.py
git commit -m "feat: fit the odds blend weight walk-forward on closing odds

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 10: Apply the fitted weight at prediction time

**Files:**
- Modify: `src/gaffer/models/team.py:91-115` (`blend_team_odds`)
- Modify: `src/gaffer/models/train.py` (`train_all` fits and stores the weight)
- Modify: `src/gaffer/advise.py:331-335` (`predict_components`)
- Modify: `src/gaffer/evaluation.py:282-341` (`evaluate_current`), `:518-527` (`format_report`)
- Test: `tests/test_team_model.py` (modify + append)
- Test: `tests/test_odds.py` (append)

- [ ] **Step 1: Write the failing test**

In `tests/test_team_model.py`, the two existing hand-computed blend tests now
have to say which weight they mean, because the default resolves through the
artifact and a developer with a trained `models/` directory would otherwise
see a different number. Replace them:

```python
def test_blend_team_odds_matches_hand_computed_blend():
    """Explicit weight: the default now resolves through the artifact, and a
    fitted weight on disk must not be able to change what this test means."""
    preds = pd.DataFrame({"code": [1], "season_idx": [0], "gw": [1],
                          "p_cs": [0.20], "e_gc": [1.60],
                          "odds_e_goals_against": [1.00]})
    out = blend_team_odds(preds, weight=ODDS_BLEND_WEIGHT)
    w = ODDS_BLEND_WEIGHT
    assert abs(out.loc[0, "p_cs"] - (w * np.exp(-1.0) + (1 - w) * 0.20)) < 1e-12
    assert abs(out.loc[0, "e_gc"] - (w * 1.0 + (1 - w) * 1.60)) < 1e-12


def test_blend_team_odds_leaves_rows_without_odds_untouched():
    preds = pd.DataFrame({"code": [1, 2], "season_idx": [0, 0], "gw": [1, 1],
                          "p_cs": [0.20, 0.30], "e_gc": [1.60, 1.20],
                          "odds_e_goals_against": [1.00, float("nan")]})
    out = blend_team_odds(preds, weight=ODDS_BLEND_WEIGHT)
    assert out.loc[1, "p_cs"] == 0.30
    assert out.loc[1, "e_gc"] == 1.20
```

Then append:

```python
def test_blend_team_odds_honours_an_explicit_weight():
    preds = pd.DataFrame({"code": [1], "season_idx": [0], "gw": [1],
                          "p_cs": [0.20], "e_gc": [1.60],
                          "odds_e_goals_against": [1.00]})
    out = blend_team_odds(preds, weight=0.0)
    assert out.loc[0, "p_cs"] == 0.20
    assert out.loc[0, "e_gc"] == 1.60


def test_blend_team_odds_defaults_to_the_fitted_artifact_weight(tmp_path,
                                                                monkeypatch):
    import gaffer.models.persistence as persistence

    monkeypatch.setattr(persistence, "MODELS_DIR", tmp_path)
    persistence.save_params("blend", {"odds_blend_weight": 1.0})
    preds = pd.DataFrame({"code": [1], "season_idx": [0], "gw": [1],
                          "p_cs": [0.20], "e_gc": [1.60],
                          "odds_e_goals_against": [1.00]})
    out = blend_team_odds(preds)
    assert abs(out.loc[0, "e_gc"] - 1.00) < 1e-12


def test_odds_blend_weight_falls_back_to_the_module_constant(tmp_path,
                                                             monkeypatch):
    """No artifact — a fresh clone, or a train that never saw closing odds —
    must behave exactly as the codebase did before the fit existed."""
    import gaffer.models.persistence as persistence
    from gaffer.models.team import odds_blend_weight

    monkeypatch.setattr(persistence, "MODELS_DIR", tmp_path)
    assert odds_blend_weight() == ODDS_BLEND_WEIGHT


def test_odds_blend_weight_reads_the_stored_value(tmp_path, monkeypatch):
    import gaffer.models.persistence as persistence
    from gaffer.models.team import odds_blend_weight

    monkeypatch.setattr(persistence, "MODELS_DIR", tmp_path)
    persistence.save_params("blend", {"odds_blend_weight": 0.42})
    assert odds_blend_weight() == 0.42
```

Add `odds_blend_weight` to the file's `from gaffer.models.team import ...`
line.

Append to `tests/test_odds.py`:

```python
def test_predict_components_still_blends_before_merging_onto_players():
    """Re-pin after the weight argument landed: the protected ordering is
    what the fitted weight must not disturb."""
    import inspect

    from gaffer.advise import predict_components

    src = inspect.getsource(predict_components)
    assert src.index("blend_team_odds(") < src.index("comp.merge(tp")
    assert "odds_blend_weight()" in src
```

Append to `tests/test_train.py`:

```python
def test_train_all_stores_the_fitted_blend_weight(tmp_path, monkeypatch):
    """The weight is a training output like any other component, and the
    weekly refit is where it gets refreshed."""
    import gaffer.models.persistence as persistence
    from gaffer.models.train import train_all

    monkeypatch.setattr(persistence, "MODELS_DIR", tmp_path)
    train_all(_player_frame(seasons=(0, 1)), _team_frame(seasons=(0, 1)),
              save=True)
    assert "odds_blend_weight" in persistence.load_params("blend")


def test_train_all_without_match_odds_stores_the_constant(tmp_path,
                                                          monkeypatch):
    """No football-data file is the default state of a fresh clone; the
    stored weight then has to be the documented fallback, not a fit on
    nothing."""
    import gaffer.models.persistence as persistence
    from gaffer.models import train as train_mod
    from gaffer.models.team import ODDS_BLEND_WEIGHT

    monkeypatch.setattr(persistence, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(train_mod.store, "exists", lambda rel: False)
    train_mod.train_all(_player_frame(seasons=(0, 1)),
                        _team_frame(seasons=(0, 1)), save=True)
    stored = persistence.load_params("blend")["odds_blend_weight"]
    assert stored == ODDS_BLEND_WEIGHT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_team_model.py -k weight -v`
Expected: FAIL — `TypeError: blend_team_odds() got an unexpected keyword argument 'weight'`

- [ ] **Step 3: Write minimal implementation**

In `src/gaffer/models/team.py`, replace `blend_team_odds`:

```python
def blend_team_odds(team_preds: pd.DataFrame,
                    weight: float | None = None) -> pd.DataFrame:
    """Blend market odds into team predictions where odds exist.

    ``p_cs``: independent-Poisson P(concede 0) = ``exp(-mu_against)``, the
    same independence assumption ``invert_odds`` used to recover the mus, so
    the two ends of the odds path agree.

    ``weight`` defaults to :func:`odds_blend_weight` — the value fitted at
    train time on historical closing odds and stored in the artifact bundle,
    falling back to :data:`ODDS_BLEND_WEIGHT` when no artifact exists. Pass it
    explicitly to pin a number, which is what the tests and the explainability
    path do.

    Rows without odds keep the pure model output — a fixture the feed did not
    cover, or a week with no API key at all, must degrade to the model rather
    than to a blend against NaN. A frame with no odds column whatsoever comes
    back untouched, so any caller that never joins odds on is safe to route
    through here.

    One row per team-fixture is assumed: apply this *before* the many-to-one
    merge onto player rows, or the blend lands once per player.
    """
    if ODDS_AGAINST_COL not in team_preds.columns:
        return team_preds
    out = team_preds.copy()
    has = out[ODDS_AGAINST_COL].notna()
    mu = out.loc[has, ODDS_AGAINST_COL].astype(float)
    w = odds_blend_weight() if weight is None else float(weight)
    out.loc[has, "p_cs"] = w * np.exp(-mu) + (1 - w) * out.loc[has, "p_cs"]
    out.loc[has, "e_gc"] = w * mu + (1 - w) * out.loc[has, "e_gc"]
    return out
```

Extend the `ODDS_BLEND_WEIGHT` docstring's last paragraph:

```python
ODDS_BLEND_WEIGHT = 0.7
"""How much of the blended team output comes from the market.

Odds cannot enter as a *feature*: bookmakers only price upcoming fixtures, so
every historical training row is NaN on the odds columns and LightGBM never
learns a split on them — a populated prediction-time value would change
nothing. They enter at prediction time instead, as a weighted blend against
the model's own output.

0.7 was a guess. It is now only the *fallback*: with historical closing odds
on disk, :func:`fit_blend_weight` estimates the weight by log loss on
walk-forward predictions and :func:`odds_blend_weight` serves the fitted value
instead. The constant still applies wherever there is no artifact — a fresh
clone, or a train that never saw a football-data file.
"""
```

In `src/gaffer/models/train.py`, fit and store the weight inside `train_all`,
directly before the `save` block:

```python
    models = {"minutes": minutes, "team": team, "attacking": attacking,
              "defcon": defcon, "saves": saves, "bonus": bonus}
    if _fit_cal:
        models["calibration"] = fit_calibration(
            df, tg, scoring_table(load_bootstrap_sample()))
    if save:
        # The odds blend weight is a training output like any other: fitted on
        # the closing-odds record, stored beside the pickles, read back by
        # blend_team_odds at prediction time. No football-data file on disk
        # means walk_forward_cs returns nothing and fit_blend_weight hands
        # back the module constant, which is the pre-v4b behaviour exactly.
        match_odds = (store.load(MATCH_ODDS_PATH)
                      if store.exists(MATCH_ODDS_PATH)
                      else pd.DataFrame())
        weight = fit_blend_weight(walk_forward_cs(tg, match_odds))
        save_params(BLEND_PARAMS_NAME, {"odds_blend_weight": weight,
                                        "rows": len(match_odds)})
        for name, m in models.items():
            save_model(m, name, meta={"rows": len(df)})
    return models
```

with the matching imports at the top of `train.py`:

```python
from gaffer.data.match_odds import MATCH_ODDS_PATH
from gaffer.models.dixon_coles import DixonColesModel, walk_forward_cs
from gaffer.models.persistence import save_model, save_params
from gaffer.models.team import (BLEND_PARAMS_NAME, TEAM_FEATURES, TeamModel,
                                add_team_rolling, build_team_gw,
                                fit_blend_weight)
```

In `src/gaffer/advise.py`, `predict_components`, replace the blend block:

```python
    tp = blend_team_odds(tp, weight=odds_blend_weight())
    if ODDS_AGAINST_COL not in tp.columns:
        tp[ODDS_AGAINST_COL] = float("nan")
    tp["odds_weight"] = (tp[ODDS_AGAINST_COL].notna().astype(float)
                         * odds_blend_weight())
```

and extend its import line:

```python
from gaffer.models.team import (ODDS_AGAINST_COL, ODDS_BLEND_WEIGHT,
                                add_team_rolling, blend_team_odds,
                                odds_blend_weight)
```

In `src/gaffer/evaluation.py`, add the weight to `evaluate_current`'s payload,
directly after `"holdout_slots"`:

```python
        "holdout_slots": int(holdout_slots),
        # The weight actually in force for this run — a blended clean sheet
        # is only interpretable next to it.
        "odds_blend_weight": odds_blend_weight(),
```

with `from gaffer.models.team import odds_blend_weight` added to
`evaluate_current`'s local import block, and in `format_report`, directly
after the header line:

```python
    if payload.get("odds_blend_weight") is not None:
        lines.append(f"odds blend weight w = {payload['odds_blend_weight']:.2f}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_team_model.py tests/test_odds.py tests/test_train.py -v`
Expected: PASS (all three files)

Run: `uv run pytest`
Expected: PASS — the three protected source-text tests included

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/models/team.py src/gaffer/models/train.py src/gaffer/advise.py src/gaffer/evaluation.py tests/test_team_model.py tests/test_odds.py tests/test_train.py
git commit -m "feat: serve the fitted odds blend weight from the artifact bundle

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 11: Measure — the ξ grid and gate G1

Run-and-record. Nothing is implemented here; the outputs decide what gets
pinned in Task 5's `DEFAULT_XI` and whether the Task 8 switch stays on
`"dixon_coles"`.

**Files:**
- Modify: `src/gaffer/models/dixon_coles.py:DEFAULT_XI` (pin the winner)
- Modify: `docs/superpowers/specs/2026-08-25-gaffer-v4b-model-design.md` §13 Outcome

- [ ] **Step 1: Capture the before-photo**

The v4a numbers are already in `reports/evaluation.json` under `current`.
Copy it aside so a later run cannot overwrite the baseline:

Run: `cp reports/evaluation.json reports/evaluation-v4a-baseline.json`
Expected: the file exists; `current.heads.cs.log_loss` in it reads `0.6190`
(v4a's measured value). If it does not, run
`caffeinate -i uv run gaffer evaluate` **on the branch point** first and keep
that artifact — without it there is nothing to compare against.

- [ ] **Step 2: Build the closing-odds corpus**

Run: `caffeinate -i uv run gaffer build-history`
Expected: the existing history lines plus `Match odds: N priced fixtures.`
with N in the low thousands (~380 per season × the number of seasons that
carry price columns). Record the per-season `matched/rows` lines it prints —
a season below ~90% matched means an alias is missing from
`FOOTBALL_DATA_ALIASES` and must be added before continuing.

- [ ] **Step 3: Score the ξ grid**

For each ξ in {0.003, 0.0065, 0.01}, set `DEFAULT_XI` in
`src/gaffer/models/dixon_coles.py` to that value and run:

Run: `caffeinate -i uv run gaffer evaluate --mode current`
Expected: a `current` block whose `-- head cs: log loss ...` line is the
number to record, alongside the printed `odds blend weight w = ...`.

Record all three in a table:

| ξ | CS log loss | fitted w |
| --- | --- | --- |
| 0.003 | | |
| 0.0065 | | |
| 0.01 | | |

- [ ] **Step 4: Pin the winner**

Set `DEFAULT_XI` to the ξ with the lowest CS log loss and update its
docstring to state the measured value rather than "Task 10 measures":

```python
DEFAULT_XI = 0.0065
"""Decay rate per day. Chosen by CS log loss on the current-mode holdout over
the grid {0.003, 0.0065, 0.01} — see the v4b spec's Outcome table."""
```

(substituting the actual winner).

Run: `uv run pytest tests/test_dixon_coles.py -v`
Expected: PASS

- [ ] **Step 5: Evaluate gate G1**

Run: `caffeinate -i uv run gaffer evaluate --mode current`
Expected: a printed report. Extract and record in the spec's §13 Outcome:

- `heads.cs.log_loss` — **G1 passes when it is below 0.6190.**
- `heads.cs.reliability` — the pred/obs pairs; G1 also wants them visibly
  closer to the diagonal than the v4a baseline's.
- `odds_blend_weight` — the fitted w.
- `stratified.all` and `stratified.starters` for all five categories —
  **no cell may regress by more than 2%** against the v4a baseline.

If CS log loss did not improve after the ξ grid, set `TEAM_MODEL = "gbm"` in
`src/gaffer/models/train.py`, re-run `gaffer evaluate --mode current` to
confirm the fitted blend alone still helps on the old head, record the
negative result in the spec, and carry on to Task 12 — spec §9's stated
fallback.

- [ ] **Step 6: Commit**

```bash
git add src/gaffer/models/dixon_coles.py docs/superpowers/specs/2026-08-25-gaffer-v4b-model-design.md reports/evaluation.json
git commit -m "measure: pin xi and record gate G1 for the Dixon-Coles head

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 12: Name normalization and Understat's embedded JSON

**Files:**
- Create: `src/gaffer/data/names.py`
- Create: `src/gaffer/data/understat.py`
- Test: `tests/test_understat.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_understat.py`:

```python
import json

import pandas as pd
import pytest

from gaffer.data.names import normalize_name
from gaffer.data.understat import (match_player_rows, parse_embedded_json,
                                   league_matches, team_match_rows)
from gaffer.errors import GafferError


def _embed(var: str, payload) -> str:
    """An understat page fragment: hex-escaped JSON inside JSON.parse('...')."""
    raw = json.dumps(payload)
    escaped = "".join(f"\\x{ord(c):02x}" if c in '"\'\\<>&' else c
                      for c in raw)
    return f"<script>var {var} = JSON.parse('{escaped}');</script>"


def test_normalize_name_strips_case_accents_and_punctuation():
    assert normalize_name("Ødegaard") == "odegaard"
    assert normalize_name("N'Golo Kanté") == "ngolo kante"
    assert normalize_name("  Heung-Min  Son ") == "heung min son"
    assert normalize_name("João Pedro") == "joao pedro"


def test_normalize_name_of_the_same_player_two_ways_agrees():
    assert normalize_name("Gabriel Martinelli") == normalize_name(
        "gabriel  martinelli")


def test_normalize_name_of_none_is_empty():
    assert normalize_name(None) == ""
    assert normalize_name(float("nan")) == ""


def test_parse_embedded_json_decodes_the_hex_escaped_blob():
    html = _embed("playersData", [{"id": "1", "player": "Kanté"}])
    assert parse_embedded_json(html, "playersData") == [
        {"id": "1", "player": "Kanté"}]


def test_parse_embedded_json_finds_the_right_variable_among_several():
    html = (_embed("teamsData", {"1": {"title": "Arsenal"}})
            + _embed("datesData", [{"id": "9"}]))
    assert parse_embedded_json(html, "datesData") == [{"id": "9"}]


def test_parse_embedded_json_raises_on_a_missing_variable():
    """A silent empty result would look exactly like a season with no data
    and would poison the cache with nothing."""
    with pytest.raises(GafferError) as exc:
        parse_embedded_json("<html></html>", "playersData")
    assert "playersData" in str(exc.value)


_DATES = [
    {"id": "18001", "isResult": True, "datetime": "2024-08-16 20:00:00",
     "h": {"id": "89", "title": "Manchester United"},
     "a": {"id": "76", "title": "Wolverhampton Wanderers"},
     "goals": {"h": "1", "a": "0"}},
    {"id": "18002", "isResult": False, "datetime": "2025-05-25 16:00:00",
     "h": {"id": "83", "title": "Arsenal"},
     "a": {"id": "89", "title": "Manchester United"},
     "goals": {"h": None, "a": None}},
]


def test_league_matches_lists_ids_dates_and_played_flags():
    out = league_matches(_embed("datesData", _DATES))
    assert list(out["match_id"]) == ["18001", "18002"]
    assert list(out["is_result"]) == [True, False]
    assert out.loc[0, "date"] == pd.Timestamp("2024-08-16").date()
    assert out.loc[0, "home_team"] == "Manchester United"


def test_league_matches_on_an_empty_season_is_an_empty_frame():
    out = league_matches(_embed("datesData", []))
    assert out.empty
    assert list(out.columns) == ["match_id", "date", "home_team", "away_team",
                                 "is_result"]


_TEAMS = {
    "83": {"id": "83", "title": "Arsenal", "history": [
        {"date": "2024-08-17 14:00:00", "xG": 1.8, "xGA": 0.6,
         "ppda": {"att": 240, "def": 22}, "deep": 9, "deep_allowed": 2},
        {"date": "2024-08-24 14:00:00", "xG": 2.1, "xGA": 1.4,
         "ppda": {"att": 200, "def": 25}, "deep": 11, "deep_allowed": 5},
    ]},
}


def test_team_match_rows_flattens_history_with_ppda():
    out = team_match_rows(_embed("teamsData", _TEAMS), season="2024-25",
                          season_idx=2)
    assert list(out.columns) == ["season", "season_idx", "team", "date",
                                 "us_xg", "us_xga", "ppda", "deep",
                                 "deep_allowed"]
    assert len(out) == 2
    assert out.loc[0, "team"] == "Arsenal"
    # PPDA is passes allowed per defensive action: att / def.
    assert abs(out.loc[0, "ppda"] - 240 / 22) < 1e-9
    assert out.loc[1, "us_xga"] == 1.4


def test_team_match_rows_with_a_zero_defensive_action_count_is_nan():
    """A division by zero here would ship an inf into a LightGBM split."""
    teams = {"83": {"id": "83", "title": "Arsenal", "history": [
        {"date": "2024-08-17 14:00:00", "xG": 1.0, "xGA": 1.0,
         "ppda": {"att": 100, "def": 0}, "deep": 1, "deep_allowed": 1}]}}
    out = team_match_rows(_embed("teamsData", teams), season="2024-25",
                          season_idx=2)
    assert pd.isna(out.loc[0, "ppda"])


_ROSTER = {
    "h": {"501": {"player_id": "1250", "player": "Bruno Fernandes",
                  "h_a": "h", "time": "90", "goals": "1", "assists": "0",
                  "shots": "4", "key_passes": "3", "xG": "0.85", "xA": "0.31",
                  "xGChain": "1.2", "xGBuildup": "0.4"}},
    "a": {"502": {"player_id": "3110", "player": "Matheus Cunha",
                  "h_a": "a", "time": "63", "goals": "0", "assists": "0",
                  "shots": "2", "key_passes": "1", "xG": "0.20", "xA": "0.05",
                  "xGChain": "0.5", "xGBuildup": "0.1"}},
}

_SHOTS = {
    "h": [{"player_id": "1250", "xG": "0.76", "situation": "Penalty"},
          {"player_id": "1250", "xG": "0.09", "situation": "OpenPlay"}],
    "a": [{"player_id": "3110", "xG": "0.20", "situation": "OpenPlay"}],
}


def _match_html() -> str:
    return _embed("rostersData", _ROSTER) + _embed("shotsData", _SHOTS)


def test_match_player_rows_carries_the_marginal_understat_stats():
    out = match_player_rows(_match_html(), match_id="18001",
                            date=pd.Timestamp("2024-08-16").date(),
                            home_team="Manchester United",
                            away_team="Wolverhampton Wanderers")
    assert list(out["understat_id"]) == ["1250", "3110"]
    assert list(out["team"]) == ["Manchester United",
                                 "Wolverhampton Wanderers"]
    assert list(out["minutes"]) == [90.0, 63.0]
    assert out.loc[0, "us_shots"] == 4.0
    assert out.loc[0, "us_key_passes"] == 3.0
    assert out.loc[0, "us_xgchain"] == 1.2
    assert out.loc[0, "us_xgbuildup"] == 0.4
    assert set(out["match_id"]) == {"18001"}
    assert set(out["date"]) == {pd.Timestamp("2024-08-16").date()}


def test_match_player_rows_derives_npxg_by_dropping_penalty_shots():
    """The roster blob has no npxG field; the shot list does, and a penalty
    is exactly the shot a per-90 shooting rate must not be credited with."""
    out = match_player_rows(_match_html(), match_id="18001",
                            date=pd.Timestamp("2024-08-16").date(),
                            home_team="Manchester United",
                            away_team="Wolverhampton Wanderers")
    assert abs(out.loc[0, "us_npxg"] - 0.09) < 1e-9
    assert abs(out.loc[1, "us_npxg"] - 0.20) < 1e-9


def test_match_player_rows_gives_a_player_with_no_shots_zero_npxg():
    roster = {"h": {"501": {"player_id": "77", "player": "Casemiro",
                            "h_a": "h", "time": "90", "goals": "0",
                            "assists": "0", "shots": "0", "key_passes": "2",
                            "xG": "0", "xA": "0.1", "xGChain": "0.3",
                            "xGBuildup": "0.3"}}, "a": {}}
    html = _embed("rostersData", roster) + _embed("shotsData", {"h": [], "a": []})
    out = match_player_rows(html, match_id="18001",
                            date=pd.Timestamp("2024-08-16").date(),
                            home_team="Manchester United",
                            away_team="Wolves")
    assert out.loc[0, "us_npxg"] == 0.0


def test_match_player_rows_on_an_empty_roster_is_an_empty_frame():
    html = _embed("rostersData", {"h": {}, "a": {}}) + _embed(
        "shotsData", {"h": [], "a": []})
    out = match_player_rows(html, match_id="18001",
                            date=pd.Timestamp("2024-08-16").date(),
                            home_team="A", away_team="B")
    assert out.empty
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_understat.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gaffer.data.names'`

- [ ] **Step 3: Write minimal implementation**

Create `src/gaffer/data/names.py`:

```python
"""One normalizer for player names, shared by every source that has to match
on them.

Understat writes "Ødegaard", the odds feed writes "Martin Odegaard", the FPL
bootstrap writes "M.Ødegaard" depending on the season. Every one of those has
to collapse to the same key, and the collapse has to be identical in the
Understat id mapping and the AGS name match — two normalizers that disagree
by a hyphen would match different sets of players and nobody would notice.
"""

from __future__ import annotations

import re
import unicodedata

_PUNCT = re.compile(r"[^a-z0-9 ]+")
_SPACES = re.compile(r"\s+")


def normalize_name(name) -> str:
    """Casefolded, accent-stripped, punctuation-free, single-spaced.

    Punctuation becomes a space rather than nothing, so "Heung-Min" and
    "Heung Min" agree; a missing or non-string name is the empty string,
    which matches nothing rather than raising in the middle of a join.
    """
    if name is None or not isinstance(name, str):
        return ""
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed
                       if not unicodedata.combining(c))
    lowered = stripped.casefold()
    # Ø and ß survive NFKD as themselves; map the few that matter by hand.
    lowered = lowered.replace("ø", "o").replace("ß", "ss").replace("đ", "d")
    return _SPACES.sub(" ", _PUNCT.sub(" ", lowered)).strip()
```

Create `src/gaffer/data/understat.py`:

```python
"""Understat ingestion: the marginal xG signal FPL's own feed does not carry.

FPL publishes expected goals and expected assists, and ``ATTACK_FEATURES``
already uses them, so Understat is *not* worth scraping for xG. What it has
that nothing else does is the shape underneath: shot counts, key passes,
non-penalty xG, xGChain and xGBuildup per player-match, and per-team xGA,
PPDA and deep completions. Those separate a striker on two big chances from
one on six half-chances — the same xG, very different next week.

There is no API. Every page ships its data as hex-escaped JSON inside a
``JSON.parse('...')`` call, which is what :func:`parse_embedded_json` picks
apart. Match pages never change once played, so they are cached forever by id
and only a running season ever re-fetches.
"""

from __future__ import annotations

import json
import re

import pandas as pd

from gaffer.errors import GafferError

UNDERSTAT_BASE = "https://understat.com"

TEAM_COLS = ["season", "season_idx", "team", "date", "us_xg", "us_xga",
             "ppda", "deep", "deep_allowed"]
PLAYER_COLS = ["match_id", "date", "understat_id", "player_name", "team",
               "minutes", "us_shots", "us_key_passes", "us_npxg",
               "us_xgchain", "us_xgbuildup"]
MATCH_COLS = ["match_id", "date", "home_team", "away_team", "is_result"]


def parse_embedded_json(html: str, var_name: str):
    """The payload of ``var <var_name> = JSON.parse('...')``.

    The blob is hex-escaped ASCII, so ``unicode_escape`` undoes the escaping;
    that decoder works byte-wise, though, so any real UTF-8 in the page comes
    back mojibake and has to be re-encoded through latin-1 to recover. A page
    without the variable raises rather than returning empty: "the season has
    no data" and "understat changed its markup" must not look the same.
    """
    match = re.search(var_name + r"\s*=\s*JSON\.parse\('(.*?)'\)", html,
                      re.DOTALL)
    if match is None:
        raise GafferError(
            f"understat page carries no {var_name} blob — the markup changed, "
            "or the URL was wrong")
    decoded = match.group(1).encode("utf-8").decode("unicode_escape")
    try:
        decoded = decoded.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass        # already clean ASCII
    return json.loads(decoded)


def _num(value) -> float:
    """Understat ships every number as a string, and ``None`` for absent."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def league_matches(html: str) -> pd.DataFrame:
    """``datesData`` -> ``[match_id, date, home_team, away_team, is_result]``.

    ``is_result`` is what makes an incremental refresh cheap: a fixture that
    has not been played has nothing to cache and must be re-checked next week.
    """
    rows = []
    for m in parse_embedded_json(html, "datesData") or []:
        rows.append({
            "match_id": str(m["id"]),
            "date": pd.to_datetime(m["datetime"], errors="coerce").date()
            if m.get("datetime") else None,
            "home_team": m["h"]["title"],
            "away_team": m["a"]["title"],
            "is_result": bool(m.get("isResult")),
        })
    return pd.DataFrame(rows, columns=MATCH_COLS)


def team_match_rows(html: str, season: str, season_idx: int) -> pd.DataFrame:
    """``teamsData`` -> one row per team per match.

    PPDA is passes allowed per defensive action, which understat reports as
    the two counts rather than the ratio. A zero denominator (never seen in
    practice, cheap to guard) yields NaN, because an infinity in a feature
    column is a crash somewhere downstream rather than a signal.
    """
    rows = []
    for team in (parse_embedded_json(html, "teamsData") or {}).values():
        for h in team.get("history", []):
            ppda = h.get("ppda") or {}
            att, dfn = _num(ppda.get("att")), _num(ppda.get("def"))
            rows.append({
                "season": season, "season_idx": int(season_idx),
                "team": team["title"],
                "date": pd.to_datetime(h["date"], errors="coerce").date()
                if h.get("date") else None,
                "us_xg": _num(h.get("xG")), "us_xga": _num(h.get("xGA")),
                "ppda": att / dfn if dfn else float("nan"),
                "deep": _num(h.get("deep")),
                "deep_allowed": _num(h.get("deep_allowed")),
            })
    return pd.DataFrame(rows, columns=TEAM_COLS)


def match_player_rows(html: str, match_id: str, date, home_team: str,
                      away_team: str) -> pd.DataFrame:
    """One match page -> one row per player who appeared.

    ``rostersData`` carries minutes, shots, key passes, xGChain and xGBuildup
    but *not* non-penalty xG, so npxG is summed off ``shotsData`` with the
    penalties dropped. A penalty is worth ~0.76 xG and says nothing about how
    a player creates chances from open play, which is the whole reason the
    non-penalty split is the one worth rolling.
    """
    rosters = parse_embedded_json(html, "rostersData") or {}
    shots = parse_embedded_json(html, "shotsData") or {}
    npxg: dict[str, float] = {}
    for side in ("h", "a"):
        for shot in shots.get(side, []) or []:
            if str(shot.get("situation")) == "Penalty":
                continue
            pid = str(shot.get("player_id"))
            npxg[pid] = npxg.get(pid, 0.0) + _num(shot.get("xG"))
    rows = []
    for side, team in (("h", home_team), ("a", away_team)):
        for entry in (rosters.get(side) or {}).values():
            pid = str(entry["player_id"])
            rows.append({
                "match_id": str(match_id), "date": date,
                "understat_id": pid, "player_name": entry.get("player"),
                "team": team,
                "minutes": _num(entry.get("time")),
                "us_shots": _num(entry.get("shots")),
                "us_key_passes": _num(entry.get("key_passes")),
                "us_npxg": npxg.get(pid, 0.0),
                "us_xgchain": _num(entry.get("xGChain")),
                "us_xgbuildup": _num(entry.get("xGBuildup")),
            })
    return pd.DataFrame(rows, columns=PLAYER_COLS)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_understat.py -v`
Expected: PASS (16 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/data/names.py src/gaffer/data/understat.py tests/test_understat.py
git commit -m "feat: parse understat embedded JSON into player and team frames

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 13: `UnderstatClient` — fetch, cache, politeness

**Files:**
- Modify: `src/gaffer/data/understat.py` (append after `match_player_rows`)
- Test: `tests/test_understat.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_understat.py`:

```python
import httpx

from gaffer.data.understat import UnderstatClient


def _http(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_league_page_requests_the_season_url(tmp_path):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, text=_embed("datesData", _DATES))

    client = UnderstatClient(client=_http(handler), cache_dir=tmp_path,
                             sleep=0.0)
    out = client.league_matches("2024-25")
    assert seen["url"] == "https://understat.com/league/EPL/2024"
    assert list(out["match_id"]) == ["18001", "18002"]


def test_match_page_is_cached_by_id_and_never_refetched(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, text=_match_html())

    client = UnderstatClient(client=_http(handler), cache_dir=tmp_path,
                             sleep=0.0)
    first = client.match_players("18001", pd.Timestamp("2024-08-16").date(),
                                 "Manchester United",
                                 "Wolverhampton Wanderers")
    second = client.match_players("18001", pd.Timestamp("2024-08-16").date(),
                                  "Manchester United",
                                  "Wolverhampton Wanderers")
    assert calls["n"] == 1
    assert len(first) == len(second) == 2
    assert (tmp_path / "match" / "18001.json").exists()


def test_cached_match_survives_a_process_restart(tmp_path):
    """The 1900-page backfill has to be resumable: a fresh client must read
    the same cache."""
    def handler(request):
        return httpx.Response(200, text=_match_html())

    UnderstatClient(client=_http(handler), cache_dir=tmp_path,
                    sleep=0.0).match_players(
        "18001", pd.Timestamp("2024-08-16").date(), "A", "B")

    def refuse(request):
        raise AssertionError("cached match must not be refetched")

    out = UnderstatClient(client=_http(refuse), cache_dir=tmp_path,
                          sleep=0.0).match_players(
        "18001", pd.Timestamp("2024-08-16").date(), "A", "B")
    assert len(out) == 2


def test_uncached_fetches_sleep_between_requests(tmp_path, monkeypatch):
    """Politeness is not optional on somebody else's free website."""
    slept = []
    monkeypatch.setattr("gaffer.data.understat.time.sleep", slept.append)

    def handler(request):
        return httpx.Response(200, text=_match_html())

    client = UnderstatClient(client=_http(handler), cache_dir=tmp_path,
                             sleep=1.0)
    client.match_players("18001", pd.Timestamp("2024-08-16").date(), "A", "B")
    client.match_players("18002", pd.Timestamp("2024-08-17").date(), "A", "B")
    assert slept == [1.0, 1.0]


def test_a_cache_hit_does_not_sleep(tmp_path, monkeypatch):
    slept = []
    monkeypatch.setattr("gaffer.data.understat.time.sleep", slept.append)
    client = UnderstatClient(
        client=_http(lambda r: httpx.Response(200, text=_match_html())),
        cache_dir=tmp_path, sleep=1.0)
    client.match_players("18001", pd.Timestamp("2024-08-16").date(), "A", "B")
    slept.clear()
    client.match_players("18001", pd.Timestamp("2024-08-16").date(), "A", "B")
    assert slept == []


def test_a_failed_match_fetch_returns_empty_and_caches_nothing(tmp_path):
    """One dead page must cost one match, not the backfill — and must not
    poison the cache with an empty result that never retries."""
    client = UnderstatClient(
        client=_http(lambda r: httpx.Response(503)), cache_dir=tmp_path,
        sleep=0.0, retries=1)
    out = client.match_players("18001", pd.Timestamp("2024-08-16").date(),
                               "A", "B")
    assert out.empty
    assert not (tmp_path / "match" / "18001.json").exists()


def test_team_history_reads_the_league_page_once_per_season(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, text=_embed("teamsData", _TEAMS))

    client = UnderstatClient(client=_http(handler), cache_dir=tmp_path,
                             sleep=0.0)
    out = client.team_history("2024-25", season_idx=2)
    assert len(out) == 2
    assert calls["n"] == 1


def test_season_year_is_the_starting_year():
    from gaffer.data.understat import season_year

    assert season_year("2024-25") == "2024"
    assert season_year("2020-21") == "2020"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_understat.py -k UnderstatClient -v`
Expected: FAIL — `ImportError: cannot import name 'UnderstatClient' from 'gaffer.data.understat'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/gaffer/data/understat.py` (adding `import time` and
`from pathlib import Path` and `import httpx` to the header):

```python
CACHE_DIR = Path("data/raw/understat")
SLEEP_SECONDS = 1.0
"""Minimum gap between uncached requests.

Understat is a free site with no API and no rate-limit documentation. One
second is what a person browsing looks like, and a five-season backfill is
~1900 pages — half an hour, once, and cached forever after.
"""


def season_year(season: str) -> str:
    """``"2024-25"`` -> ``"2024"``, understat's season key."""
    return season[:4]


class UnderstatClient:
    """Fetches understat pages, caches every match forever.

    A played match's page can never change, so it is written to
    ``data/raw/understat/match/<id>.json`` on first read and served from disk
    afterwards. That is what makes the backfill resumable: a run killed
    halfway costs only the pages it had not reached. Failures are per page —
    a 503 costs that one match and returns an empty frame — and nothing
    failed is ever cached, so the next run retries it.
    """

    def __init__(self, client: httpx.Client | None = None,
                 cache_dir: Path | str | None = None,
                 sleep: float = SLEEP_SECONDS, retries: int = 3):
        self._http = client if client is not None else httpx.Client(
            timeout=30, follow_redirects=True,
            headers={"User-Agent": "gaffer/1.0 (personal FPL research)"})
        self.cache_dir = Path(cache_dir) if cache_dir is not None else CACHE_DIR
        self.sleep = float(sleep)
        self.retries = int(retries)

    def _get(self, url: str) -> str | None:
        """Page text, or ``None`` after exhausting the retries."""
        for attempt in range(self.retries):
            if self.sleep:
                time.sleep(self.sleep)
            try:
                resp = self._http.get(url)
                resp.raise_for_status()
                return resp.text
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                if attempt == self.retries - 1:
                    print(f"understat: giving up on {url} ({exc})")
        return None

    def league_matches(self, season: str) -> pd.DataFrame:
        """Every fixture id understat knows for a season."""
        html = self._get(f"{UNDERSTAT_BASE}/league/EPL/{season_year(season)}")
        if html is None:
            return pd.DataFrame(columns=MATCH_COLS)
        return league_matches(html)

    def team_history(self, season: str, season_idx: int) -> pd.DataFrame:
        """Per-team per-match xG/xGA/PPDA/deep from the league page."""
        html = self._get(f"{UNDERSTAT_BASE}/league/EPL/{season_year(season)}")
        if html is None:
            return pd.DataFrame(columns=TEAM_COLS)
        return team_match_rows(html, season, season_idx)

    def match_players(self, match_id: str, date, home_team: str,
                      away_team: str) -> pd.DataFrame:
        """One match's player rows, from cache where possible."""
        path = self.cache_dir / "match" / f"{match_id}.json"
        if path.exists():
            cached = json.loads(path.read_text())
            frame = pd.DataFrame(cached, columns=PLAYER_COLS)
            frame["date"] = date
            return frame
        html = self._get(f"{UNDERSTAT_BASE}/match/{match_id}")
        if html is None:
            return pd.DataFrame(columns=PLAYER_COLS)
        try:
            rows = match_player_rows(html, match_id, date, home_team,
                                     away_team)
        except GafferError as exc:
            print(f"understat: unparseable match {match_id} ({exc})")
            return pd.DataFrame(columns=PLAYER_COLS)
        path.parent.mkdir(parents=True, exist_ok=True)
        # The date is re-applied on read rather than stored: it is a date
        # object, JSON has no such type, and the caller always knows it.
        path.write_text(rows.drop(columns=["date"]).to_json(orient="records"))
        return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_understat.py -v`
Expected: PASS (24 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/data/understat.py tests/test_understat.py
git commit -m "feat: UnderstatClient with a permanent per-match cache

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 14: Understat -> FPL id mapping

**Files:**
- Create: `src/gaffer/assets/understat_overrides.json`
- Modify: `src/gaffer/data/understat.py` (append after `UnderstatClient`)
- Modify: `src/gaffer/assets/__init__.py`
- Test: `tests/test_understat.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_understat.py`:

```python
from gaffer.data.understat import load_overrides, map_understat_players


def _us(rows):
    """[(understat_id, player_name, team)]"""
    return pd.DataFrame([{"understat_id": i, "player_name": n, "team": t}
                         for i, n, t in rows])


def _fpl(rows):
    """[(code, name, team_name)]"""
    return pd.DataFrame([{"code": c, "name": n, "team_name": t}
                         for c, n, t in rows])


def test_map_understat_players_matches_on_name_and_club():
    us = _us([("1250", "Bruno Fernandes", "Manchester United")])
    fpl = _fpl([(1, "Bruno Fernandes", "Man Utd"),
                (2, "Bruno Guimarães", "Newcastle")])
    out, report = map_understat_players(us, fpl,
                                        team_aliases={"Manchester United":
                                                      "Man Utd"})
    assert out.to_dict("records") == [{"understat_id": "1250", "code": 1}]
    assert report["exact"] == 1 and report["unmatched"] == 0


def test_map_understat_players_ignores_accents_and_punctuation():
    us = _us([("9", "N'Golo Kanté", "Chelsea")])
    fpl = _fpl([(5, "Ngolo Kante", "Chelsea")])
    out, _ = map_understat_players(us, fpl, team_aliases={"Chelsea": "Chelsea"})
    assert list(out["code"]) == [5]


def test_map_understat_players_falls_back_to_a_unique_cross_club_name():
    """A January transfer puts the player at one club in one source and
    another in the other; a unique full-name match is safe."""
    us = _us([("11", "Kai Havertz", "Arsenal")])
    fpl = _fpl([(7, "Kai Havertz", "Chelsea")])
    out, report = map_understat_players(us, fpl,
                                        team_aliases={"Arsenal": "Arsenal"})
    assert list(out["code"]) == [7]
    assert report["cross_club"] == 1


def test_map_understat_players_refuses_an_ambiguous_cross_club_name():
    """Two players share a normalized name and neither club agrees — a coin
    flip here attaches one player's shots to another."""
    us = _us([("12", "Danny Ward", "Leicester")])
    fpl = _fpl([(8, "Danny Ward", "Huddersfield"),
                (9, "Danny Ward", "Cardiff City")])
    out, report = map_understat_players(us, fpl, team_aliases={})
    assert out.empty
    assert report["unmatched"] == 1


def test_map_understat_players_applies_the_override_file():
    us = _us([("13", "Emile Smith Rowe", "Fulham")])
    fpl = _fpl([(10, "Emile Smith-Rowe", "Fulham")])
    out, report = map_understat_players(us, fpl, team_aliases={},
                                        overrides={"13": 10})
    assert list(out["code"]) == [10]
    assert report["override"] == 1


def test_map_understat_players_reports_unmatched_names(capsys):
    us = _us([("14", "Nobody At All", "Nowhere")])
    fpl = _fpl([(11, "Someone Else", "Arsenal")])
    out, report = map_understat_players(us, fpl, team_aliases={})
    assert out.empty
    assert report["rows"] == 1 and report["unmatched"] == 1
    assert report["exact"] == report["cross_club"] == report["override"] == 0
    assert "Nobody At All" in report["unmatched_names"][0]


def test_map_understat_players_is_one_row_per_understat_id():
    """A player appears in 38 match frames; the mapping is a lookup table,
    not a row-for-row join."""
    us = _us([("15", "Cole Palmer", "Chelsea")] * 38)
    fpl = _fpl([(12, "Cole Palmer", "Chelsea")])
    out, _ = map_understat_players(us, fpl, team_aliases={"Chelsea": "Chelsea"})
    assert len(out) == 1


def test_load_overrides_returns_a_dict_and_skips_doc_keys():
    overrides = load_overrides()
    assert isinstance(overrides, dict)
    assert not any(k.startswith("_") for k in overrides)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_understat.py -k map_understat -v`
Expected: FAIL — `ImportError: cannot import name 'map_understat_players' from 'gaffer.data.understat'`

- [ ] **Step 3: Write minimal implementation**

Create `src/gaffer/assets/understat_overrides.json`:

```json
{
  "_note": "understat player id -> FPL player code. Add an entry when the refresh prints an unmatched name that is really a player we carry. Keys starting with _ are documentation and are ignored.",
  "_example": "\"1250\": 141746"
}
```

Append to `src/gaffer/assets/__init__.py`:

```python
UNDERSTAT_OVERRIDES = "understat_overrides.json"


def load_understat_overrides() -> dict:
    """The bundled ``understat_id -> FPL code`` override table.

    Shipped in the package rather than under ``data/`` because it is curated
    knowledge, not fetched data: it belongs in git and in the wheel, and it
    survives a wiped data directory.
    """
    return json.loads(
        files(__package__).joinpath(UNDERSTAT_OVERRIDES).read_text(
            encoding="utf-8")
    )
```

Append to `src/gaffer/data/understat.py` (adding
`from gaffer.data.names import normalize_name` to the header):

```python
def load_overrides() -> dict[str, int]:
    """Manual id mappings, documentation keys stripped."""
    from gaffer.assets import load_understat_overrides

    return {k: int(v) for k, v in load_understat_overrides().items()
            if not k.startswith("_")}


def map_understat_players(us_players: pd.DataFrame, fpl_players: pd.DataFrame,
                          team_aliases: dict[str, str],
                          overrides: dict[str, int] | None = None
                          ) -> tuple[pd.DataFrame, dict]:
    """``understat_id -> code`` lookup, plus a report of how each id resolved.

    Three passes, most conservative first. A normalized full-name match at the
    *same club* is unambiguous. A normalized full-name match that is unique
    across the whole league is next — that is the transfer case, where the two
    sources disagree about the club but only one player can be meant. Anything
    left goes to the manual override file, and whatever survives that is
    logged by name and dropped: an unmapped player contributes NaN features,
    which LightGBM handles natively, where a wrong mapping would attach one
    player's shot volume to another.

    ``team_aliases`` maps understat club names to FPL bootstrap names; a club
    missing from it simply never matches on the same-club pass and falls
    through to the cross-club one.
    """
    overrides = load_overrides() if overrides is None else overrides
    us = us_players[["understat_id", "player_name", "team"]].drop_duplicates(
        subset=["understat_id"]).copy()
    # Not ``_name``: DataFrame.itertuples renames any column starting with an
    # underscore to a positional ``_1``, and the attribute access below would
    # silently read the wrong field.
    us["norm_name"] = us["player_name"].map(normalize_name)
    us["norm_club"] = us["team"].map(lambda t: team_aliases.get(t, t))

    fpl = fpl_players[["code", "name", "team_name"]].copy()
    fpl["norm_name"] = fpl["name"].map(normalize_name)
    by_name_club = {(r.norm_name, r.team_name): int(r.code)
                    for r in fpl.itertuples()}
    counts = fpl["norm_name"].value_counts()
    unique_names = {r.norm_name: int(r.code) for r in fpl.itertuples()
                    if counts.get(r.norm_name, 0) == 1}

    rows, report = [], {"rows": int(len(us)), "exact": 0, "cross_club": 0,
                        "override": 0, "unmatched": 0}
    unmatched_names = []
    for r in us.itertuples():
        code = by_name_club.get((r.norm_name, r.norm_club))
        bucket = "exact"
        if code is None:
            code = unique_names.get(r.norm_name)
            bucket = "cross_club"
        if code is None:
            code = overrides.get(str(r.understat_id))
            bucket = "override"
        if code is None:
            report["unmatched"] += 1
            unmatched_names.append(f"{r.player_name} ({r.team}, "
                                   f"id {r.understat_id})")
            continue
        report[bucket] += 1
        rows.append({"understat_id": str(r.understat_id), "code": int(code)})
    report["unmatched_names"] = unmatched_names
    print(f"understat id mapping: {report['exact']} exact, "
          f"{report['cross_club']} cross-club, {report['override']} override, "
          f"{report['unmatched']} unmatched")
    for name in unmatched_names[:20]:
        print(f"  unmatched: {name}")
    return pd.DataFrame(rows, columns=["understat_id", "code"]), report
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_understat.py -v`
Expected: PASS (32 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/assets/understat_overrides.json src/gaffer/assets/__init__.py src/gaffer/data/understat.py tests/test_understat.py
git commit -m "feat: map understat player ids onto FPL codes with an override file

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 15: Understat parquets and the backfill command

**Files:**
- Modify: `src/gaffer/data/understat.py` (append after `map_understat_players`)
- Modify: `src/gaffer/config.py`
- Modify: `src/gaffer/cli.py` (new `understat` command)
- Test: `tests/test_understat.py` (append)
- Test: `tests/test_config.py` (append)
- Test: `tests/test_cli.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_understat.py`:

```python
from gaffer.data.understat import (UNDERSTAT_TEAM_ALIASES,
                                   UNDERSTAT_PLAYER_PATH,
                                   UNDERSTAT_TEAM_PATH, build_understat_player,
                                   build_understat_team)


def _league_and_match_handler(request):
    if "/league/" in str(request.url):
        return httpx.Response(200, text=(_embed("datesData", _DATES)
                                         + _embed("teamsData", _TEAMS)))
    return httpx.Response(200, text=_match_html())


def test_every_understat_alias_target_is_an_fpl_name():
    from gaffer.data.odds import TEAM_ALIASES

    unknown = sorted(set(UNDERSTAT_TEAM_ALIASES.values())
                     - set(TEAM_ALIASES.values()))
    assert unknown == []


def test_build_understat_player_writes_the_parquet(tmp_path, monkeypatch):
    import gaffer.data.store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    client = UnderstatClient(client=_http(_league_and_match_handler),
                             cache_dir=tmp_path / "raw", sleep=0.0)
    fpl = _fpl([(1, "Bruno Fernandes", "Man Utd"),
                (2, "Matheus Cunha", "Wolves")])
    out = build_understat_player(["2024-25"], {"2024-25": 2}, fpl,
                                 client=client)
    assert (tmp_path / UNDERSTAT_PLAYER_PATH).exists()
    assert set(out.columns) == {"season", "season_idx", "understat_id", "code",
                                "player_name", "team", "date", "minutes",
                                "us_shots", "us_key_passes", "us_npxg",
                                "us_xgchain", "us_xgbuildup"}
    assert set(out["code"]) == {1, 2}


def test_build_understat_player_only_fetches_played_matches(tmp_path):
    """The unplayed fixture in datesData has no page worth caching."""
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return _league_and_match_handler(request)

    client = UnderstatClient(client=_http(handler),
                             cache_dir=tmp_path / "raw", sleep=0.0)
    build_understat_player(["2024-25"], {"2024-25": 2},
                           _fpl([(1, "Bruno Fernandes", "Man Utd")]),
                           client=client, store_result=False)
    assert any("/match/18001" in u for u in seen)
    assert not any("/match/18002" in u for u in seen)


def test_build_understat_player_drops_unmapped_players(tmp_path):
    """An unmatched player contributes nothing rather than something wrong."""
    client = UnderstatClient(client=_http(_league_and_match_handler),
                             cache_dir=tmp_path / "raw", sleep=0.0)
    out = build_understat_player(["2024-25"], {"2024-25": 2},
                                 _fpl([(1, "Bruno Fernandes", "Man Utd")]),
                                 client=client, store_result=False)
    assert set(out["code"]) == {1}


def test_build_understat_team_writes_the_parquet(tmp_path, monkeypatch):
    import gaffer.data.store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    client = UnderstatClient(client=_http(_league_and_match_handler),
                             cache_dir=tmp_path / "raw", sleep=0.0)
    out = build_understat_team(["2024-25"], {"2024-25": 2},
                               {"Arsenal": 3}, client=client)
    assert (tmp_path / UNDERSTAT_TEAM_PATH).exists()
    assert list(out["team_code"]) == [3, 3]
    assert "ppda" in out.columns


def test_build_understat_team_drops_a_club_with_no_code(tmp_path):
    client = UnderstatClient(client=_http(_league_and_match_handler),
                             cache_dir=tmp_path / "raw", sleep=0.0)
    out = build_understat_team(["2024-25"], {"2024-25": 2}, {},
                               client=client, store_result=False)
    assert out.empty
```

Append to `tests/test_config.py`:

```python
def test_config_defaults_the_new_v4b_switches_on(tmp_path):
    """Both new sources default to enabled and degrade on their own when the
    data is not there — no config edit needed to get the old behaviour."""
    path = tmp_path / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n")
    cfg = load_config(path)
    assert cfg.player_props is True
    assert cfg.understat_enabled is True
    assert cfg.ags_blend_weight == 0.5


def test_config_reads_the_new_v4b_switches(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n"
                    "[odds]\nplayer_props = false\nags_blend_weight = 0.3\n"
                    "[understat]\nenabled = false\n")
    cfg = load_config(path)
    assert cfg.player_props is False
    assert cfg.ags_blend_weight == 0.3
    assert cfg.understat_enabled is False
```

Append to `tests/test_cli.py`:

```python
def test_understat_is_a_command():
    from typer.testing import CliRunner

    from gaffer.cli import app

    result = CliRunner().invoke(app, ["--help"])
    assert "understat" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_understat.py -k build_understat -v`
Expected: FAIL — `ImportError: cannot import name 'build_understat_player' from 'gaffer.data.understat'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/gaffer/data/understat.py`:

```python
UNDERSTAT_PLAYER_PATH = "history/understat_player.parquet"
UNDERSTAT_TEAM_PATH = "history/understat_team.parquet"

PLAYER_PARQUET_COLS = ["season", "season_idx", "understat_id", "code",
                       "player_name", "team", "date", "minutes", "us_shots",
                       "us_key_passes", "us_npxg", "us_xgchain",
                       "us_xgbuildup"]
TEAM_PARQUET_COLS = ["season", "season_idx", "team", "team_code", "date",
                     "us_xg", "us_xga", "ppda", "deep", "deep_allowed"]

# Understat's own club titles -> FPL bootstrap names. Season-agnostic, same
# discipline as TEAM_ALIASES: relegated clubs stay so a promotion needs no
# code change.
UNDERSTAT_TEAM_ALIASES = {
    "Arsenal": "Arsenal",
    "Aston Villa": "Aston Villa",
    "Bournemouth": "Bournemouth",
    "Brentford": "Brentford",
    "Brighton": "Brighton",
    "Burnley": "Burnley",
    "Cardiff": "Cardiff City",
    "Chelsea": "Chelsea",
    "Crystal Palace": "Crystal Palace",
    "Everton": "Everton",
    "Fulham": "Fulham",
    "Huddersfield": "Huddersfield",
    "Hull": "Hull City",
    "Ipswich": "Ipswich Town",
    "Leeds": "Leeds",
    "Leicester": "Leicester",
    "Liverpool": "Liverpool",
    "Luton": "Luton",
    "Manchester City": "Man City",
    "Manchester United": "Man Utd",
    "Middlesbrough": "Middlesbrough",
    "Newcastle United": "Newcastle",
    "Norwich": "Norwich",
    "Nottingham Forest": "Nott'm Forest",
    "Sheffield United": "Sheffield Utd",
    "Southampton": "Southampton",
    "Stoke": "Stoke City",
    "Sunderland": "Sunderland",
    "Swansea": "Swansea",
    "Tottenham": "Spurs",
    "Watford": "Watford",
    "West Bromwich Albion": "West Brom",
    "West Ham": "West Ham",
    "Wolverhampton Wanderers": "Wolves",
}


def build_understat_player(seasons: list[str],
                           season_indexes: dict[str, int],
                           fpl_players: pd.DataFrame,
                           client: UnderstatClient | None = None,
                           store_result: bool = True) -> pd.DataFrame:
    """Scrape every played match of every season -> the player parquet.

    ``fpl_players`` is ``[code, name, team_name]`` — the FPL side of the id
    mapping. Rows for players the mapping could not resolve are dropped, so
    the parquet only ever carries stats that belong to a code we can join on;
    the ``code`` column is why this frame is usable at all and is why it is
    stored alongside the ``understat_id`` the spec lists.

    Cached matches cost nothing, so re-running after a killed backfill is
    cheap and only the running season ever adds pages.
    """
    from gaffer.data import store

    client = client or UnderstatClient()
    frames = []
    for season in seasons:
        idx = season_indexes[season]
        fixtures = client.league_matches(season)
        played = fixtures[fixtures["is_result"]]
        print(f"understat {season}: {len(played)} played matches")
        for m in played.itertuples():
            rows = client.match_players(m.match_id, m.date, m.home_team,
                                        m.away_team)
            if rows.empty:
                continue
            rows = rows.copy()
            rows["season"] = season
            rows["season_idx"] = int(idx)
            frames.append(rows)
    if not frames:
        out = pd.DataFrame(columns=PLAYER_PARQUET_COLS)
        if store_result:
            store.save(out, UNDERSTAT_PLAYER_PATH)
        return out
    us = pd.concat(frames, ignore_index=True)
    mapping, _report = map_understat_players(us, fpl_players,
                                            UNDERSTAT_TEAM_ALIASES)
    out = us.merge(mapping, on="understat_id", how="inner")
    out = out[PLAYER_PARQUET_COLS]
    if store_result:
        store.save(out, UNDERSTAT_PLAYER_PATH)
    return out


def build_understat_team(seasons: list[str], season_indexes: dict[str, int],
                         name_to_code: dict[str, int],
                         client: UnderstatClient | None = None,
                         store_result: bool = True) -> pd.DataFrame:
    """Per-team per-match xG/xGA/PPDA/deep -> the team parquet.

    ``name_to_code`` maps FPL bootstrap names to team codes. A club with no
    code — a season the bootstrap tables do not cover — is dropped rather than
    carried with a NaN key that would silently never join.
    """
    from gaffer.data import store

    client = client or UnderstatClient()
    frames = []
    for season in seasons:
        rows = client.team_history(season, season_indexes[season])
        if rows.empty:
            continue
        rows = rows.copy()
        rows["team_code"] = rows["team"].map(
            lambda t: name_to_code.get(UNDERSTAT_TEAM_ALIASES.get(t, t)))
        frames.append(rows[rows["team_code"].notna()])
    if not frames:
        out = pd.DataFrame(columns=TEAM_PARQUET_COLS)
    else:
        out = pd.concat(frames, ignore_index=True)
        out["team_code"] = out["team_code"].astype(int)
        out = out[TEAM_PARQUET_COLS]
    if store_result:
        store.save(out, UNDERSTAT_TEAM_PATH)
    return out


def history_player_index(seasons: list[str]) -> pd.DataFrame:
    """``[code, name, team_name]`` for every player in stored history.

    The FPL side of the id mapping, built offline from what is already on
    disk: a scrape must not need a live bootstrap call, and history covers
    seasons the current bootstrap has forgotten. The newest row per code wins,
    because that is the club the player is at now and the one a same-club
    match is most likely to hit.
    """
    from gaffer.data import store
    from gaffer.data.history import season_name_codes

    player_gw = store.load("history/player_gw.parquet")
    code_to_name: dict[int, str] = {}
    for _season, table in season_name_codes(seasons).items():
        for name, code in table.items():
            code_to_name[int(code)] = name
    latest = (player_gw.sort_values(["season_idx", "gw"])
              .groupby("code", as_index=False).tail(1))
    return pd.DataFrame({
        "code": latest["code"].astype(int),
        "name": latest["name"],
        "team_name": latest["team_code"].map(
            lambda c: code_to_name.get(int(c)) if pd.notna(c) else None),
    })
```

In `src/gaffer/config.py`, extend the dataclass and loader:

```python
@dataclass
class Config:
    entry_id: int
    league_id: int
    horizon: int = 3
    decay: float = 0.85
    vice_weight: float = 0.1
    bench_weight: float = 0.10
    ft_value: float = 1.5
    itb_value: float = 0.05
    hit_cost: int = 4
    train_seasons: list[str] = field(default_factory=list)
    current_season: str = "2026-27"
    odds_api_key: str = ""
    player_props: bool = True
    ags_blend_weight: float = 0.5
    understat_enabled: bool = True


def load_config(path: Path | str = "config.toml") -> Config:
    raw = tomllib.loads(Path(path).read_text())
    odds = raw.get("odds", {})
    return Config(
        entry_id=raw["fpl"]["entry_id"],
        league_id=raw["fpl"]["league_id"],
        **raw.get("optimizer", {}),
        **raw.get("data", {}),
        # Read explicitly rather than splatted: [odds] is optional and its
        # TOML keys do not all match the dataclass field names. Both new
        # switches default on and degrade by themselves when the data or the
        # key is missing, so nobody has to edit config.toml to keep the old
        # behaviour.
        odds_api_key=odds.get("api_key", ""),
        player_props=bool(odds.get("player_props", True)),
        ags_blend_weight=float(odds.get("ags_blend_weight", 0.5)),
        understat_enabled=bool(
            raw.get("understat", {}).get("enabled", True)),
    )
```

In `src/gaffer/cli.py`, add the command after `build-history`:

```python
@app.command()
def understat():
    """Scrape Understat into data/history/ (long first run; resumable)."""
    from gaffer.config import load_config
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
    players = build_understat_player(seasons, indexes,
                                     history_player_index(cfg.train_seasons))
    teams = build_understat_team(seasons, indexes, flat)
    typer.echo(f"Understat: {len(players)} player-match rows, "
               f"{len(teams)} team-match rows -> data/history/.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_understat.py tests/test_config.py tests/test_cli.py -v`
Expected: PASS (38 in `test_understat.py`, the other two files green)

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 5: Run the backfill**

Run: `caffeinate -i uv run gaffer understat`
Expected: a per-season "N played matches" line, an id-mapping report, and a
final count. ~1900 pages at one second each — roughly 35 minutes on the first
run, seconds on every run after. Record the mapping report's
matched/override/unmatched counts. Any unmatched name that is really a player
we carry goes into `src/gaffer/assets/understat_overrides.json`; re-run (the
cache makes it instant) until the unmatched list is only players FPL never
listed.

- [ ] **Step 6: Commit**

```bash
git add src/gaffer/data/understat.py src/gaffer/config.py src/gaffer/cli.py src/gaffer/assets/understat_overrides.json tests/test_understat.py tests/test_config.py tests/test_cli.py
git commit -m "feat: gaffer understat backfills the player and team parquets

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 16: Understat rolling features

**Files:**
- Modify: `src/gaffer/features/engineer.py` (append after `add_player_rolling`)
- Test: `tests/test_features.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_features.py`:

```python
# --- Understat rolling features -------------------------------------------

from gaffer.features.engineer import (TEAM_US_FEATURES, US_WINDOWS,
                                      add_understat_rolling,
                                      add_understat_team_rolling,
                                      merge_understat_team,
                                      understat_feature_columns)


def _us_rows(spec, code=1):
    """spec: list of (gw, us_minutes, us_shots)."""
    return pd.DataFrame([
        {"code": code, "season_idx": 0, "gw": gw,
         "kickoff_time": f"2024-08-{10 + gw:02d}T14:00:00Z",
         "us_minutes": m, "us_shots": s, "us_key_passes": 1.0,
         "us_npxg": 0.1, "us_xgchain": 0.2, "us_xgbuildup": 0.1}
        for gw, m, s in spec])


def test_add_understat_rolling_is_leakage_safe():
    """A match's own shots must never reach its own features."""
    out = add_understat_rolling(_us_rows([(1, 90, 4), (2, 90, 2)])
                                ).set_index("gw")
    assert pd.isna(out.loc[1, "us_shots90_r3"])
    assert out.loc[2, "us_shots90_r3"] == 4.0


def test_add_understat_rolling_is_a_per_ninety_not_a_per_match_mean():
    """Two matches, 90 and 45 minutes, five shots between them: the rate is
    5 / 135 * 90, not the mean of 4 and 1."""
    out = add_understat_rolling(_us_rows([(1, 90, 4), (2, 45, 1), (3, 90, 0)])
                                ).set_index("gw")
    assert abs(out.loc[3, "us_shots90_r3"] - 5.0 / 135.0 * 90.0) < 1e-9


def test_add_understat_rolling_window_only_reaches_back_w_matches():
    out = add_understat_rolling(
        _us_rows([(1, 90, 9), (2, 90, 0), (3, 90, 0), (4, 90, 0),
                  (5, 90, 0)])).set_index("gw")
    assert out.loc[5, "us_shots90_r3"] == 0.0
    assert abs(out.loc[5, "us_shots90_r38"] - 9.0 / 360.0 * 90.0) < 1e-9


def test_add_understat_rolling_zero_minutes_window_is_nan_not_inf():
    """An unused substitute run of matches would divide by zero, and an
    infinity in a feature column is a crash downstream, not a signal."""
    out = add_understat_rolling(_us_rows([(1, 0, 0), (2, 90, 1)])
                                ).set_index("gw")
    assert pd.isna(out.loc[2, "us_shots90_r3"])


def test_add_understat_rolling_keeps_players_separate():
    frame = pd.concat([_us_rows([(1, 90, 6), (2, 90, 0)], code=1),
                       _us_rows([(1, 90, 0), (2, 90, 0)], code=2)],
                      ignore_index=True)
    out = add_understat_rolling(frame).set_index(["code", "gw"])
    assert out.loc[(1, 2), "us_shots90_r3"] == 6.0
    assert out.loc[(2, 2), "us_shots90_r3"] == 0.0


def test_add_understat_rolling_without_any_understat_columns_is_all_nan():
    """The degradation rail: no Understat parquet means the columns exist and
    are empty, so LightGBM's schema is identical either way."""
    frame = pd.DataFrame([{"code": 1, "season_idx": 0, "gw": 1,
                           "kickoff_time": "2024-08-11T14:00:00Z"}])
    out = add_understat_rolling(frame)
    for col in understat_feature_columns():
        assert col in out.columns
        assert out[col].isna().all()


def test_understat_feature_columns_covers_every_stat_and_window():
    cols = understat_feature_columns()
    assert len(cols) == 5 * len(US_WINDOWS)
    assert "us_kp90_r5" in cols and "us_xgbuildup90_r38" in cols


def _ut_rows(team_code, dates, xga, ppda):
    return pd.DataFrame([
        {"team_code": team_code, "season_idx": 0, "date": d,
         "us_xga": g, "ppda": p}
        for d, g, p in zip(dates, xga, ppda)])


def test_add_understat_team_rolling_is_leakage_safe():
    ut = _ut_rows(3, ["2024-08-17", "2024-08-24", "2024-08-31"],
                  [0.5, 2.5, 1.0], [9.0, 11.0, 10.0])
    out = add_understat_team_rolling(ut).set_index("date")
    assert pd.isna(out.loc["2024-08-17", "team_us_xga_r5"])
    assert out.loc["2024-08-24", "team_us_xga_r5"] == 0.5
    assert out.loc["2024-08-31", "team_us_xga_r5"] == 1.5


def test_merge_understat_team_attaches_own_and_opponent_columns():
    ut = pd.concat([
        _ut_rows(3, ["2024-08-17", "2024-08-24"], [0.5, 2.5], [9.0, 11.0]),
        _ut_rows(4, ["2024-08-17", "2024-08-24"], [3.0, 1.0], [14.0, 13.0]),
    ], ignore_index=True)
    rolled = add_understat_team_rolling(ut)
    df = pd.DataFrame([{"code": 1, "season_idx": 0, "gw": 2, "team_code": 3,
                        "opp_code": 4,
                        "kickoff_time": "2024-08-24T14:00:00Z"}])
    out = merge_understat_team(df, rolled)
    assert out.loc[0, "team_us_xga_r5"] == 0.5
    assert out.loc[0, "opp_us_xga_r5"] == 3.0
    assert out.loc[0, "opp_ppda_r5"] == 14.0
    assert set(TEAM_US_FEATURES) <= set(out.columns)


def test_merge_understat_team_without_data_still_creates_the_columns():
    df = pd.DataFrame([{"code": 1, "season_idx": 0, "gw": 2, "team_code": 3,
                        "opp_code": 4,
                        "kickoff_time": "2024-08-24T14:00:00Z"}])
    out = merge_understat_team(df, None)
    for col in TEAM_US_FEATURES:
        assert col in out.columns and out[col].isna().all()


def test_merge_understat_team_does_not_add_rows():
    """A many-to-one join that fans out would double a player's gameweek."""
    ut = _ut_rows(3, ["2024-08-24", "2024-08-24"], [2.5, 2.5], [11.0, 11.0])
    rolled = add_understat_team_rolling(ut)
    df = pd.DataFrame([{"code": 1, "season_idx": 0, "gw": 2, "team_code": 3,
                        "opp_code": 4,
                        "kickoff_time": "2024-08-24T14:00:00Z"}])
    assert len(merge_understat_team(df, rolled)) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_features.py -k understat -v`
Expected: FAIL — `ImportError: cannot import name 'add_understat_rolling' from 'gaffer.features.engineer'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/gaffer/features/engineer.py`:

```python
US_STATS = ["us_shots", "us_key_passes", "us_npxg", "us_xgchain",
            "us_xgbuildup"]
US_FEATURE_NAMES = {"us_shots": "us_shots90", "us_key_passes": "us_kp90",
                    "us_npxg": "us_npxg90", "us_xgchain": "us_xgchain90",
                    "us_xgbuildup": "us_xgbuildup90"}
US_WINDOWS = [3, 5, 10, 38]

TEAM_US_STATS = ["us_xga", "ppda"]
TEAM_US_WINDOWS = [5, 38]
TEAM_US_FEATURES = [f"{side}_{stat}_r{w}"
                    for side in ("team", "opp")
                    for stat in TEAM_US_STATS
                    for w in TEAM_US_WINDOWS]
"""Own and opponent defensive shape. The opponent's is the attacking signal:
a forward's chances come from how leaky and how passive the defence in front
of him is, which ``opp_us_xga`` and ``opp_ppda`` measure directly and Elo
only summarizes."""


def understat_feature_columns(windows: list[int] = US_WINDOWS) -> list[str]:
    """Every player-level Understat feature name, in a stable order."""
    return [f"{name}_r{w}" for name in US_FEATURE_NAMES.values()
            for w in windows]


def add_understat_rolling(df: pd.DataFrame,
                          windows: list[int] = US_WINDOWS) -> pd.DataFrame:
    """Rolling per-90 Understat rates from past matches only.

    Per-90 rather than per-match: a substitute's four shots in 20 minutes and
    a starter's four in 90 are different players, and a per-match mean calls
    them the same. The rate is ``sum(stat) / sum(minutes) * 90`` over the
    window, both sums taken from the ``shift(1)``-ed series — the identical
    leakage discipline :func:`add_player_rolling` uses, for the identical
    reason.

    A window with no minutes at all yields NaN rather than an infinity;
    LightGBM splits on missing natively and an ``inf`` would propagate into
    a crash. Frames with no Understat columns at all (no parquet on disk, or
    the source disabled) come back with every feature present and empty, so
    the model's feature schema never depends on whether the scrape ran.
    """
    sort_cols = ["code", "season_idx", "gw"]
    if "kickoff_time" in df.columns:
        sort_cols.append("kickoff_time")
    df = df.sort_values(sort_cols).reset_index(drop=True)
    missing = [c for c in US_STATS + ["us_minutes"] if c not in df.columns]
    if missing:
        df = df.assign(**{c: float("nan") for c in missing})
    code = df["code"]
    mins = pd.to_numeric(df["us_minutes"], errors="coerce")
    shifted_mins = mins.groupby(code).shift(1)
    denom = {}
    for w in windows:
        rolled = (shifted_mins.groupby(code).rolling(w, min_periods=1).sum()
                  .reset_index(level=0, drop=True))
        denom[w] = rolled.where(rolled > 0.0)
    feats: dict[str, pd.Series] = {}
    for stat in US_STATS:
        shifted = (pd.to_numeric(df[stat], errors="coerce")
                   .groupby(code).shift(1))
        for w in windows:
            num = (shifted.groupby(code).rolling(w, min_periods=1).sum()
                   .reset_index(level=0, drop=True))
            feats[f"{US_FEATURE_NAMES[stat]}_r{w}"] = num / denom[w] * 90.0
    return pd.concat([df, pd.DataFrame(feats, index=df.index)], axis=1)


def add_understat_team_rolling(
        ut: pd.DataFrame,
        windows: list[int] = TEAM_US_WINDOWS) -> pd.DataFrame:
    """Rolling team xGA and PPDA from a team's past matches only.

    Input is the Understat team parquet: one row per team per match, keyed by
    ``(team_code, date)``. Output adds ``team_<stat>_r<w>`` columns; the
    opponent's copies are attached by :func:`merge_understat_team`, which is
    where the same numbers get read from the other side of the fixture.
    """
    ut = ut.sort_values(["team_code", "date"]).reset_index(drop=True)
    code = ut["team_code"]
    feats: dict[str, pd.Series] = {}
    for stat in TEAM_US_STATS:
        shifted = (pd.to_numeric(ut[stat], errors="coerce")
                   .groupby(code).shift(1))
        for w in windows:
            feats[f"team_{stat}_r{w}"] = (
                shifted.groupby(code).rolling(w, min_periods=1).mean()
                .reset_index(level=0, drop=True))
    return pd.concat([ut, pd.DataFrame(feats, index=ut.index)], axis=1)


def merge_understat_team(df: pd.DataFrame,
                         rolled: pd.DataFrame | None) -> pd.DataFrame:
    """Attach own and opponent team Understat features to player rows.

    Joined on ``(team_code, match date)``, the only key both frames share —
    Understat carries no gameweek number. ``rolled`` of ``None`` (no parquet,
    or the source disabled) still produces every column as all-NaN, which is
    what keeps the model's feature schema stable across that switch.
    """
    out = df.copy()
    own_cols = [f"team_{s}_r{w}" for s in TEAM_US_STATS
                for w in TEAM_US_WINDOWS]
    if rolled is None or rolled.empty:
        for col in TEAM_US_FEATURES:
            out[col] = float("nan")
        return out
    out["_date"] = pd.to_datetime(out["kickoff_time"], errors="coerce",
                                  utc=True).dt.tz_convert(
                                      "Europe/London").dt.date
    keyed = rolled[["team_code", "date"] + own_cols].copy()
    # Both sides have to be plain ``date`` objects: the player frame's key is
    # derived from a timestamp and the parquet's may come back as a string,
    # and a string-vs-date merge matches nothing while looking fine.
    keyed["date"] = pd.to_datetime(keyed["date"], errors="coerce").dt.date
    keyed = keyed.drop_duplicates(subset=["team_code", "date"])
    own = keyed.rename(columns={"date": "_date"})
    out = out.merge(own, on=["team_code", "_date"], how="left",
                    validate="many_to_one")
    opp = keyed.rename(columns={"date": "_date", "team_code": "opp_code",
                                **{c: c.replace("team_", "opp_", 1)
                                   for c in own_cols}})
    out = out.merge(opp, on=["opp_code", "_date"], how="left",
                    validate="many_to_one")
    return out.drop(columns=["_date"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_features.py -v`
Expected: PASS (whole file, including the 12 new tests)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/features/engineer.py tests/test_features.py
git commit -m "feat: leakage-safe Understat per-90 and team rolling features

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 17: Shrunken per-90 rates

Rolling means are hopeless in August. Three matches into a season a striker
who has scored twice reads as a 0.67 goals-per-match player and the model
believes it. Empirical Bayes pulls a thin sample toward what players of his
position at his club normally do, and lets go of the prior as evidence
accumulates — which is exactly the early-season regime v4a's stratified
tables showed the model losing points in.

**Files:**
- Modify: `src/gaffer/features/engineer.py` (append after `merge_understat_team`)
- Test: `tests/test_features.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_features.py`:

```python
from gaffer.features.engineer import (SHRINK_K, SHRINK_K_GRID,
                                      SHRUNK_FEATURES, add_shrunken_rates,
                                      best_shrinkage_k)


def _goal_rows(spec, code=1, position="FWD", team_code=3):
    """spec: list of (gw, minutes, goals, assists)."""
    return pd.DataFrame([
        {"code": code, "season_idx": 0, "gw": gw, "position": position,
         "team_code": team_code,
         "kickoff_time": f"2024-08-{10 + gw:02d}T14:00:00Z",
         "minutes": m, "goals": g, "assists": a}
        for gw, m, g, a in spec])


def test_add_shrunken_rates_adds_both_columns():
    out = add_shrunken_rates(_goal_rows([(1, 90, 1, 0), (2, 90, 0, 1)]))
    for col in SHRUNK_FEATURES:
        assert col in out.columns


def test_add_shrunken_rates_is_leakage_safe():
    """A match's own goal must not raise its own shrunken rate."""
    a = add_shrunken_rates(_goal_rows([(1, 90, 0, 0), (2, 90, 5, 0)]))
    b = add_shrunken_rates(_goal_rows([(1, 90, 0, 0), (2, 90, 0, 0)]))
    assert a.loc[1, "shrunk_goals90"] == b.loc[1, "shrunk_goals90"]


def test_add_shrunken_rates_pulls_a_thin_sample_toward_the_prior():
    """One match with a goal is not a one-goal-per-90 player."""
    frame = pd.concat([
        _goal_rows([(1, 90, 1, 0), (2, 90, 0, 0)], code=1),
        _goal_rows([(1, 90, 0, 0), (2, 90, 0, 0)], code=2),
        _goal_rows([(1, 90, 0, 0), (2, 90, 0, 0)], code=3),
    ], ignore_index=True)
    out = add_shrunken_rates(frame, k=10.0).set_index(["code", "gw"])
    assert 0.0 < out.loc[(1, 2), "shrunk_goals90"] < 0.5


def test_add_shrunken_rates_lets_go_of_the_prior_with_evidence():
    """Thirty matches of a goal each has to read close to one per 90.

    The scoreless teammate keeps the prior at 0.5 rather than 1.0 — with only
    one player in the (position, club) group the prior *is* his own rate and
    the shrunken value would sit at 1.0 from the first match, proving nothing.
    """
    frame = pd.concat([
        _goal_rows([(gw, 90, 1, 0) for gw in range(1, 32)], code=1),
        _goal_rows([(gw, 90, 0, 0) for gw in range(1, 32)], code=2),
    ], ignore_index=True)
    out = add_shrunken_rates(frame, k=10.0).set_index(["code", "gw"])
    assert out.loc[(1, 31), "shrunk_goals90"] > out.loc[(1, 5),
                                                        "shrunk_goals90"]
    assert out.loc[(1, 31), "shrunk_goals90"] > 0.6


def test_add_shrunken_rates_prior_excludes_the_same_gameweek():
    """A teammate's goals in the very same fixture must not enter the prior —
    the row would be predicting a match partly from that match's own result.
    Likewise nothing later: the frame is sorted by player, not by time, so a
    naive per-row cumsum over the (position, club) group would see both."""
    loud = pd.concat([
        _goal_rows([(1, 90, 0, 0), (2, 90, 0, 0)], code=1),
        _goal_rows([(1, 90, 0, 0), (2, 90, 5, 0)], code=2),
    ], ignore_index=True)
    quiet = pd.concat([
        _goal_rows([(1, 90, 0, 0), (2, 90, 0, 0)], code=1),
        _goal_rows([(1, 90, 0, 0), (2, 90, 0, 0)], code=2),
    ], ignore_index=True)
    a = add_shrunken_rates(loud, k=10.0).set_index(["code", "gw"])
    b = add_shrunken_rates(quiet, k=10.0).set_index(["code", "gw"])
    assert a.loc[(1, 2), "shrunk_goals90"] == b.loc[(1, 2), "shrunk_goals90"]


def test_add_shrunken_rates_with_no_history_at_all_is_the_prior():
    """The first row of a (position, club) group has neither a player sample
    nor a prior, and NaN is the honest answer."""
    out = add_shrunken_rates(_goal_rows([(1, 90, 0, 0)]))
    assert pd.isna(out.loc[0, "shrunk_goals90"])


def test_add_shrunken_rates_separates_positions_within_a_club():
    """A defender's prior is other defenders, not the club's strikers."""
    frame = pd.concat([
        _goal_rows([(gw, 90, 1, 0) for gw in range(1, 11)], code=1,
                   position="FWD"),
        _goal_rows([(gw, 90, 0, 0) for gw in range(1, 11)], code=2,
                   position="DEF"),
        _goal_rows([(gw, 90, 0, 0) for gw in range(1, 11)], code=3,
                   position="DEF"),
    ], ignore_index=True)
    out = add_shrunken_rates(frame, k=20.0).set_index(["code", "gw"])
    assert out.loc[(2, 10), "shrunk_goals90"] < out.loc[(1, 10),
                                                        "shrunk_goals90"]


def test_add_shrunken_rates_ignores_zero_minute_rows_in_the_denominator():
    out = add_shrunken_rates(_goal_rows([(1, 0, 0, 0), (2, 90, 1, 0),
                                         (3, 90, 0, 0)])).set_index("gw")
    assert out.loc[3, "shrunk_goals90"] > 0.0


def test_best_shrinkage_k_picks_from_the_grid():
    frame = pd.concat([
        _goal_rows([(gw, 90, gw % 2, 0) for gw in range(1, 26)], code=1),
        _goal_rows([(gw, 90, 0, 0) for gw in range(1, 26)], code=2),
    ], ignore_index=True)
    k = best_shrinkage_k(frame, holdout_slots=5)
    assert k in SHRINK_K_GRID


def test_best_shrinkage_k_on_a_frame_with_no_holdout_returns_the_default():
    k = best_shrinkage_k(_goal_rows([(1, 90, 0, 0)]), holdout_slots=5)
    assert k == SHRINK_K
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_features.py -k shrunk -v`
Expected: FAIL — `ImportError: cannot import name 'SHRINK_K' from 'gaffer.features.engineer'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/gaffer/features/engineer.py`:

```python
SHRINK_K = 10.0
"""Prior weight, in nineties, for the empirical-Bayes rates.

``k`` is literally "how many matches of league-average evidence the prior is
worth". Ten means a player needs about ten full appearances before his own
record outweighs what his position at his club normally does — which is
roughly where a goals rate stops being noise.
"""

SHRINK_K_GRID = [2.0, 5.0, 10.0, 20.0]
SHRUNK_FEATURES = ["shrunk_goals90", "shrunk_assists90"]


def _shrunk_rate(df: pd.DataFrame, stat: str, k: float) -> pd.Series:
    """``(sum stat + k * prior) / (sum nineties + k)``, all sums leakage-free.

    The player's own record is ``shift(1)`` then ``cumsum`` within his own
    rows, whose order is chronological inside each code group. The
    position-by-club prior CANNOT be built the same way: the frame is sorted
    by *player*, not by time, so a per-row cumsum over the (position, club)
    group would fold in other players' future matches — and teammates share
    fixtures, so even a time-sorted row cumsum would leak the current match's
    own result through the teammate's row. The prior is therefore accumulated
    at gameweek-slot granularity: per-(position, club, slot) totals, cumsummed
    over slots with the current slot subtracted out, so a row's prior contains
    strictly-earlier gameweeks only.
    """
    code = df["code"]
    val = pd.to_numeric(df[stat], errors="coerce").fillna(0.0)
    nineties = (pd.to_numeric(df["minutes"], errors="coerce").fillna(0.0)
                / 90.0)

    own_val = val.groupby(code).shift(1).fillna(0.0).groupby(code).cumsum()
    own_90 = nineties.groupby(code).shift(1).fillna(0.0).groupby(code).cumsum()

    slots = pd.DataFrame({
        "pos": df["position"].to_numpy(),
        "team": df["team_code"].to_numpy(),
        # gw <= 38, so *100 keeps (season, gw) ordered in one integer key.
        "slot": (pd.to_numeric(df["season_idx"]).astype(int) * 100
                 + pd.to_numeric(df["gw"]).astype(int)).to_numpy(),
        "val": val.to_numpy(), "n90": nineties.to_numpy()})
    agg = (slots.groupby(["pos", "team", "slot"], as_index=False)
           [["val", "n90"]].sum().sort_values(["pos", "team", "slot"]))
    g = agg.groupby(["pos", "team"])
    # cumsum minus the current slot's own total == everything strictly before.
    before_val = g["val"].cumsum() - agg["val"]
    before_90 = g["n90"].cumsum() - agg["n90"]
    prior_rate = before_val / before_90.where(before_90 > 0.0)
    lookup = dict(zip(zip(agg["pos"], agg["team"], agg["slot"]), prior_rate))
    prior = pd.Series(
        [lookup[key] for key in zip(slots["pos"], slots["team"],
                                    slots["slot"])],
        index=df.index, dtype="float64")
    return (own_val + k * prior) / (own_90 + k)


def add_shrunken_rates(df: pd.DataFrame,
                       k: float = SHRINK_K) -> pd.DataFrame:
    """``shrunk_goals90`` and ``shrunk_assists90``.

    A rolling mean over five matches is a terrible estimate of a rate when
    only three matches exist, and August is full of those. Shrinking toward
    the position-by-club prior gives a sensible number from the first
    gameweek and converges on the player's own record as he plays — the
    standard empirical-Bayes trade, applied to the two rates the attacking
    heads care about most.

    Rows before the prior has any evidence at all come back NaN, which
    LightGBM splits on natively.
    """
    sort_cols = [c for c in ("code", "season_idx", "gw", "kickoff_time")
                 if c in df.columns]
    out = df.sort_values(sort_cols).reset_index(drop=True)
    for stat, col in (("goals", "shrunk_goals90"),
                      ("assists", "shrunk_assists90")):
        if stat in out.columns:
            out[col] = _shrunk_rate(out, stat, k)
        else:
            out[col] = float("nan")
    return out


def best_shrinkage_k(df: pd.DataFrame, k_grid: list[float] = SHRINK_K_GRID,
                     holdout_slots: int = 10) -> float:
    """The ``k`` whose shrunken goals rate best predicts held-out goals.

    Scored by correlation against the *actual* goals-per-90 on the last
    ``holdout_slots`` gameweek slots, with the rates themselves built from
    earlier rows only — so this is a genuine out-of-sample choice and not a
    fit of the fit. A frame too short to hold anything out returns
    :data:`SHRINK_K` rather than pretending to have measured something.
    """
    slots = (df[["season_idx", "gw"]].drop_duplicates()
             .sort_values(["season_idx", "gw"]))
    if len(slots) <= holdout_slots:
        return SHRINK_K
    bs, bg = slots.iloc[-holdout_slots][["season_idx", "gw"]]
    best_k, best_score = SHRINK_K, -2.0
    for k in k_grid:
        rated = add_shrunken_rates(df, k=k)
        hold = rated[(rated["season_idx"] > bs)
                     | ((rated["season_idx"] == bs) & (rated["gw"] >= bg))]
        hold = hold[pd.to_numeric(hold["minutes"], errors="coerce") > 0]
        actual = (pd.to_numeric(hold["goals"], errors="coerce")
                  / (pd.to_numeric(hold["minutes"], errors="coerce") / 90.0))
        pair = pd.DataFrame({"pred": hold["shrunk_goals90"],
                             "actual": actual}).dropna()
        if len(pair) < 2 or pair["pred"].nunique() < 2:
            continue
        score = float(pair["pred"].corr(pair["actual"]))
        if score > best_score:
            best_score, best_k = score, float(k)
    return best_k
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_features.py -v`
Expected: PASS (whole file, including the 10 new tests)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/features/engineer.py tests/test_features.py
git commit -m "feat: empirical-Bayes shrunken goals and assists per 90

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 18: Broadcast the new features onto future rows

Training rows get their Understat and shrunken features from
`add_*_rolling`; future rows cannot, because a fixture that has not been
played has no Understat page and no minutes. Every other feature block in
this codebase solves that the same way — compute the as-of-today vector once
and broadcast it onto every future row (`latest_player_rolling`,
`latest_rotation`) — and these have to follow, or the model trains on
columns that are NaN at serve time.

**Files:**
- Modify: `src/gaffer/features/engineer.py` (`merge_understat_team`, `feature_columns`, `build_prediction_frame`, plus three new helpers)
- Test: `tests/test_features.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_features.py`:

```python
from gaffer.features.engineer import (build_prediction_frame,
                                      latest_shrunken_rates,
                                      latest_understat_rolling,
                                      latest_understat_team)


def test_latest_understat_rolling_is_the_next_rows_form_vector():
    """The value a hypothetical next match would see: the same window,
    evaluated one row past the end of history."""
    hist = _us_rows([(1, 90, 4), (2, 90, 2)])
    latest = latest_understat_rolling(hist)
    assert abs(latest.loc[1, "us_shots90_r3"] - 6.0 / 180.0 * 90.0) < 1e-9


def test_latest_understat_rolling_is_one_row_per_player():
    hist = pd.concat([_us_rows([(1, 90, 4), (2, 90, 2)], code=1),
                      _us_rows([(1, 90, 0)], code=2)], ignore_index=True)
    latest = latest_understat_rolling(hist)
    assert sorted(latest.index) == [1, 2]


def test_latest_shrunken_rates_is_one_row_per_player():
    hist = pd.concat([_goal_rows([(gw, 90, 1, 0) for gw in range(1, 11)],
                                 code=1),
                      _goal_rows([(gw, 90, 0, 0) for gw in range(1, 11)],
                                 code=2)], ignore_index=True)
    latest = latest_shrunken_rates(hist)
    assert sorted(latest.index) == [1, 2]
    assert latest.loc[1, "shrunk_goals90"] > latest.loc[2, "shrunk_goals90"]


def test_latest_understat_team_is_the_last_value_per_club():
    ut = pd.concat([
        _ut_rows(3, ["2024-08-17", "2024-08-24"], [0.5, 2.5], [9.0, 11.0]),
        _ut_rows(4, ["2024-08-17", "2024-08-24"], [3.0, 1.0], [14.0, 13.0]),
    ], ignore_index=True)
    latest = latest_understat_team(add_understat_team_rolling(ut))
    assert sorted(latest.index) == [3, 4]
    assert latest.loc[3, "team_us_xga_r5"] == 0.5


def test_merge_understat_team_falls_back_to_the_latest_for_future_rows():
    """A fixture in three weeks has no Understat row of its own; without the
    broadcast the column is NaN at serve time and NaN-free in training, which
    is exactly the train/serve skew this codebase keeps avoiding."""
    ut = pd.concat([
        _ut_rows(3, ["2024-08-17", "2024-08-24"], [0.5, 2.5], [9.0, 11.0]),
        _ut_rows(4, ["2024-08-17", "2024-08-24"], [3.0, 1.0], [14.0, 13.0]),
    ], ignore_index=True)
    rolled = add_understat_team_rolling(ut)
    future = pd.DataFrame([{"code": 1, "season_idx": 0, "gw": 9,
                            "team_code": 3, "opp_code": 4,
                            "kickoff_time": "2024-10-19T14:00:00Z"}])
    out = merge_understat_team(future, rolled,
                               latest=latest_understat_team(rolled))
    assert out.loc[0, "team_us_xga_r5"] == 1.5
    assert out.loc[0, "opp_us_xga_r5"] == 3.0


def test_feature_columns_covers_every_new_block():
    from gaffer.features.engineer import feature_columns

    cols = set(feature_columns())
    assert set(understat_feature_columns()) <= cols
    assert set(TEAM_US_FEATURES) <= cols
    assert set(SHRUNK_FEATURES) <= cols


def _pred_hist():
    rows = _us_rows([(1, 90, 4), (2, 90, 2)])
    rows["position"] = "FWD"
    rows["team_code"] = 3
    rows["opp_code"] = 4
    rows["was_home"] = True
    rows["minutes"] = 90
    rows["goals"] = 1
    rows["assists"] = 0
    rows["starts"] = 1
    return rows


def test_build_prediction_frame_broadcasts_the_new_features():
    hist = _pred_hist()
    future = pd.DataFrame([{"code": 1, "season_idx": 0, "gw": 3,
                            "position": "FWD", "team_code": 3, "opp_code": 4,
                            "was_home": True,
                            "kickoff_time": "2024-08-24T14:00:00Z"}])
    out = build_prediction_frame(hist, future)
    assert out["us_shots90_r3"].notna().all()
    assert out["shrunk_goals90"].notna().all()
    assert len(out) == 1


def test_build_prediction_frame_takes_the_team_understat_frame():
    hist = _pred_hist()
    future = pd.DataFrame([{"code": 1, "season_idx": 0, "gw": 3,
                            "position": "FWD", "team_code": 3, "opp_code": 4,
                            "was_home": True,
                            "kickoff_time": "2024-08-24T14:00:00Z"}])
    ut = pd.concat([
        _ut_rows(3, ["2024-08-11", "2024-08-18"], [0.5, 2.5], [9.0, 11.0]),
        _ut_rows(4, ["2024-08-11", "2024-08-18"], [3.0, 1.0], [14.0, 13.0]),
    ], ignore_index=True)
    out = build_prediction_frame(hist, future,
                                 understat_team=add_understat_team_rolling(ut))
    assert out.loc[0, "opp_us_xga_r5"] == 3.0


def test_build_prediction_frame_without_understat_still_makes_the_columns():
    hist = _pred_hist().drop(columns=["us_minutes", "us_shots",
                                      "us_key_passes", "us_npxg",
                                      "us_xgchain", "us_xgbuildup"])
    future = pd.DataFrame([{"code": 1, "season_idx": 0, "gw": 3,
                            "position": "FWD", "team_code": 3, "opp_code": 4,
                            "was_home": True,
                            "kickoff_time": "2024-08-24T14:00:00Z"}])
    out = build_prediction_frame(hist, future)
    for col in understat_feature_columns() + TEAM_US_FEATURES:
        assert col in out.columns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_features.py -k latest_understat -v`
Expected: FAIL — `ImportError: cannot import name 'latest_understat_rolling' from 'gaffer.features.engineer'`

- [ ] **Step 3: Write minimal implementation**

In `src/gaffer/features/engineer.py`, add the three helpers after
`add_shrunken_rates`:

```python
def latest_understat_rolling(hist: pd.DataFrame,
                             windows: list[int] = US_WINDOWS) -> pd.DataFrame:
    """Each player's as-of-today Understat per-90 vector, indexed by ``code``.

    The counterpart of :func:`latest_player_rolling`: an unshifted roll
    ending at the last played match is the same window a next-fixture row's
    ``shift(1)``-then-roll would produce, without needing a placeholder row.
    """
    sort_cols = [c for c in ("code", "season_idx", "gw", "kickoff_time")
                 if c in hist.columns]
    h = hist.sort_values(sort_cols)
    for col in US_STATS + ["us_minutes"]:
        if col not in h.columns:
            h = h.assign(**{col: float("nan")})
    codes = h["code"]
    mins = pd.to_numeric(h["us_minutes"], errors="coerce")
    denom = {}
    for w in windows:
        rolled = (mins.groupby(codes).rolling(w, min_periods=1).sum()
                  .reset_index(level=0, drop=True))
        denom[w] = rolled.where(rolled > 0.0)
    feats: dict[str, pd.Series] = {}
    for stat in US_STATS:
        s = pd.to_numeric(h[stat], errors="coerce")
        for w in windows:
            num = (s.groupby(codes).rolling(w, min_periods=1).sum()
                   .reset_index(level=0, drop=True))
            feats[f"{US_FEATURE_NAMES[stat]}_r{w}"] = num / denom[w] * 90.0
    frame = pd.DataFrame(feats, index=h.index)
    frame.insert(0, "code", codes)
    return frame.groupby("code", sort=False).tail(1).set_index("code")


def latest_shrunken_rates(hist: pd.DataFrame,
                          k: float = SHRINK_K) -> pd.DataFrame:
    """Each player's as-of-today shrunken rates, indexed by ``code``.

    ``add_shrunken_rates`` already excludes the current row, so the last
    played match's value *is* the next fixture's value plus that match — near
    enough at any realistic sample size, and identical in spirit to how
    :func:`latest_rotation` reads the last played match's state. Taking the
    last row keeps every future row of a player identical, which is the point
    of the broadcast.
    """
    rated = add_shrunken_rates(hist, k=k)
    return (rated[["code"] + SHRUNK_FEATURES]
            .groupby("code", sort=False).tail(1).set_index("code"))


def latest_understat_team(rolled: pd.DataFrame) -> pd.DataFrame:
    """Each club's newest team-level Understat vector, indexed by team code.

    The Elo pattern: a future fixture has no row of its own, so it inherits
    the club's latest state.
    """
    own_cols = [f"team_{s}_r{w}" for s in TEAM_US_STATS
                for w in TEAM_US_WINDOWS]
    frame = rolled.sort_values(["team_code", "date"])
    return (frame[["team_code"] + own_cols]
            .groupby("team_code", sort=False).tail(1).set_index("team_code"))
```

Replace `merge_understat_team`'s signature and add the fallback fill at the
end (everything above the fill is unchanged):

```python
def merge_understat_team(df: pd.DataFrame, rolled: pd.DataFrame | None,
                         latest: pd.DataFrame | None = None) -> pd.DataFrame:
    """Attach own and opponent team Understat features to player rows.

    Joined on ``(team_code, match date)``, the only key both frames share —
    Understat carries no gameweek number. ``rolled`` of ``None`` (no parquet,
    or the source disabled) still produces every column as all-NaN, which is
    what keeps the model's feature schema stable across that switch.

    ``latest`` (from :func:`latest_understat_team`) fills rows the date join
    could not match — every *future* fixture, which by definition has no
    Understat row. Without it these columns would be populated in training
    and empty at serve time, which is the train/serve skew this codebase
    goes out of its way to avoid.
    """
```

and, immediately before the final `return`:

```python
    if latest is not None and not latest.empty:
        for col in [f"team_{s}_r{w}" for s in TEAM_US_STATS
                    for w in TEAM_US_WINDOWS]:
            opp_col = col.replace("team_", "opp_", 1)
            out[col] = out[col].fillna(out["team_code"].map(latest[col]))
            out[opp_col] = out[opp_col].fillna(out["opp_code"].map(latest[col]))
    return out.drop(columns=["_date"])
```

Extend `feature_columns`:

```python
def feature_columns(stats: list[str] = ROLL_STATS,
                    windows: list[int] = WINDOWS) -> list[str]:
    """Canonical model input columns for the given stats/windows.

    Everything a caller has to strip off a history frame before re-deriving
    features over it — which is why the Understat, team-Understat and
    shrunken-rate blocks belong here too, not only the rolling means.
    """
    cols = [f"{s}_r{w}" for s in stats for w in windows]
    return (cols + ["team_elo", "opp_elo", "elo_diff", "home", "days_rest",
                    "pen_taker", "setpiece_taker"] + ROTATION_FEATURES
            + understat_feature_columns() + TEAM_US_FEATURES
            + SHRUNK_FEATURES)
```

And extend `build_prediction_frame` — signature, plus the three broadcasts
appended to the concat:

```python
def build_prediction_frame(hist: pd.DataFrame, future: pd.DataFrame,
                           stats: list[str] = ROLL_STATS,
                           windows: list[int] = WINDOWS,
                           elo: pd.DataFrame | None = None,
                           elo_final: dict | None = None,
                           understat_team: pd.DataFrame | None = None
                           ) -> pd.DataFrame:
```

with the body's tail replaced by:

```python
    latest = latest_player_rolling(hist, stats, windows)
    rot = latest_rotation(hist).reindex(out["code"]).reset_index(drop=True)
    # A state carried over from an earlier season is not this season's start
    # share — before a player's first match of the new season it is undefined.
    stale = rot["_rot_season_idx"] != out["season_idx"]
    rot.loc[stale, "season_start_share"] = float("nan")
    us = latest_understat_rolling(hist, US_WINDOWS)
    shrunk = latest_shrunken_rates(hist)
    frame = pd.concat(
        [out.drop(columns=list(latest.columns) + ROTATION_FEATURES
                  + list(us.columns) + SHRUNK_FEATURES, errors="ignore"),
         latest.reindex(out["code"]).reset_index(drop=True),
         rot.drop(columns=["_rot_season_idx"]),
         us.reindex(out["code"]).reset_index(drop=True),
         shrunk.reindex(out["code"]).reset_index(drop=True)], axis=1)
    return merge_understat_team(
        frame.drop(columns=TEAM_US_FEATURES, errors="ignore"),
        understat_team,
        latest_understat_team(understat_team)
        if understat_team is not None and not understat_team.empty else None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_features.py -v`
Expected: PASS (whole file, including the 10 new tests)

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/features/engineer.py tests/test_features.py
git commit -m "feat: broadcast Understat and shrunken features onto future rows

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 19: Feed the new features to the GBM heads

**Files:**
- Modify: `src/gaffer/models/attacking.py:19-27` (`ATTACK_FEATURES`)
- Modify: `src/gaffer/models/components.py:80-81` (`SAVES_FEATURES`)
- Modify: `src/gaffer/models/train.py` (`load_training_frame`)
- Modify: `src/gaffer/advise.py:426-433` (prediction frame construction)
- Test: `tests/test_attacking.py` (append)
- Test: `tests/test_train.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_attacking.py`:

```python
def test_attack_features_carry_the_understat_and_shrunken_blocks():
    from gaffer.features.engineer import (SHRUNK_FEATURES, TEAM_US_FEATURES,
                                          understat_feature_columns)
    from gaffer.models.attacking import ATTACK_FEATURES

    cols = set(ATTACK_FEATURES)
    assert set(understat_feature_columns()) <= cols
    assert set(SHRUNK_FEATURES) <= cols
    assert {"opp_us_xga_r5", "opp_ppda_r5"} <= cols
    # FPL's own xg/xa stay: Understat is the marginal signal, not a
    # replacement for the expected-stats the feed already gives us.
    assert "xg_r5" in cols and "xa_r5" in cols


def test_saves_features_carry_the_opponent_team_understat_block():
    from gaffer.models.components import SAVES_FEATURES

    assert {"opp_us_xga_r5", "opp_us_xga_r38"} <= set(SAVES_FEATURES)


def test_attacking_model_fits_with_the_new_columns_all_nan():
    """The degradation rail at the model level: no Understat data means the
    columns are present and empty, and LightGBM must simply ignore them."""
    import numpy as np
    import pandas as pd

    from gaffer.models.attacking import ATTACK_FEATURES, AttackingModel

    rng = np.random.default_rng(0)
    rows = []
    for i in range(200):
        rows.append({"code": 100 + i % 10, "season_idx": 0, "gw": 1 + i % 20,
                     "position": "MID", "minutes": 90,
                     "goals": int(rng.random() < 0.2),
                     "assists": int(rng.random() < 0.2),
                     "xg_r5": rng.random(), "xa_r5": rng.random()})
    df = pd.DataFrame(rows)
    for col in ATTACK_FEATURES:
        if col not in df.columns:
            df[col] = float("nan")
    model = AttackingModel().fit(df)
    out = model.predict(df)
    assert out["e_goals"].notna().all()
```

Append to `tests/test_train.py`:

```python
def test_load_training_frame_attaches_the_understat_features(monkeypatch,
                                                             tmp_path):
    """The join is by (code, UK match date) — Understat has no gameweek
    number, and the date is the only key both sources agree on."""
    from gaffer.features.engineer import understat_feature_columns
    from gaffer.models import train as train_mod

    hist = _bps_history(year=2022, season_idx=0)
    fx = _bps_fixtures(year=2022, season_idx=0)
    us = pd.DataFrame([
        {"season": "2022-23", "season_idx": 0, "understat_id": "1",
         "code": 100, "player_name": "P0", "team": "Arsenal",
         "date": pd.Timestamp("2022-08-11").date(), "minutes": 90.0,
         "us_shots": 4.0, "us_key_passes": 2.0, "us_npxg": 0.5,
         "us_xgchain": 0.9, "us_xgbuildup": 0.3},
        {"season": "2022-23", "season_idx": 0, "understat_id": "1",
         "code": 100, "player_name": "P0", "team": "Arsenal",
         "date": pd.Timestamp("2022-08-12").date(), "minutes": 90.0,
         "us_shots": 2.0, "us_key_passes": 1.0, "us_npxg": 0.2,
         "us_xgchain": 0.4, "us_xgbuildup": 0.1},
    ])
    frames = {"history/player_gw.parquet": hist,
              "history/fixtures.parquet": fx,
              "history/understat_player.parquet": us}
    monkeypatch.setattr(train_mod.store, "exists", lambda rel: rel in frames)
    monkeypatch.setattr(train_mod.store, "load", lambda rel: frames[rel].copy())

    df, _tg, _elo = train_mod.load_training_frame()
    for col in understat_feature_columns():
        assert col in df.columns
    row = df[(df["code"] == 100) & (df["gw"] == 3)]
    assert float(row["us_shots90_r38"].iloc[0]) == 3.0


def test_load_training_frame_without_understat_still_has_the_columns(
        monkeypatch):
    """No parquet on disk is the default state; every new column has to
    exist and be empty so the feature schema never depends on the scrape."""
    from gaffer.features.engineer import (SHRUNK_FEATURES, TEAM_US_FEATURES,
                                          understat_feature_columns)
    from gaffer.models import train as train_mod

    _stub_store(monkeypatch, train_mod,
                history=_bps_history(year=2022, season_idx=0),
                fixtures=_bps_fixtures(year=2022, season_idx=0))
    df, _tg, _elo = train_mod.load_training_frame()
    for col in understat_feature_columns() + TEAM_US_FEATURES:
        assert col in df.columns and df[col].isna().all()
    for col in SHRUNK_FEATURES:
        assert col in df.columns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_attacking.py -k understat -v`
Expected: FAIL — `AssertionError` (the Understat columns are not in
`ATTACK_FEATURES`)

- [ ] **Step 3: Write minimal implementation**

In `src/gaffer/models/attacking.py`:

```python
from gaffer.features.engineer import (SHRUNK_FEATURES,
                                      understat_feature_columns)
from gaffer.models.minutes import LGB_KW

ATTACK_FEATURES = [
    "xg_r1", "xg_r3", "xg_r5", "xg_r10", "xg_r38",
    "xa_r1", "xa_r3", "xa_r5", "xa_r10", "xa_r38",
    "xgi_r5", "xgi_r10", "goals_r5", "goals_r38", "assists_r5", "assists_r38",
    "bps_r5", "minutes_r5", "starts_r5",
    "team_elo", "opp_elo", "elo_diff", "home", "days_rest",
    # Defenders take corners, so every position group gets these.
    "pen_taker", "setpiece_taker",
] + understat_feature_columns() + SHRUNK_FEATURES + [
    # The opponent's defensive shape is the attacking signal: how leaky and
    # how passive the defence in front of the player is. FPL's own xg/xa stay
    # exactly where they are — Understat contributes the *marginal* signal
    # (shot volume, chance creation, non-penalty split), not a replacement.
    "opp_us_xga_r5", "opp_us_xga_r38", "opp_ppda_r5", "opp_ppda_r38",
]
```

In `src/gaffer/models/components.py`:

```python
SAVES_FEATURES = ["saves_r3", "saves_r5", "saves_r38", "opp_elo", "elo_diff",
                  "home",
                  # Shots faced is what a keeper's save count is made of, and
                  # the opponent's expected goals against us is the closest
                  # measurable proxy for shot volume coming our way.
                  "opp_us_xga_r5", "opp_us_xga_r38"]
```

In `src/gaffer/models/train.py`, add the attach helper before
`load_training_frame`:

```python
def attach_understat(df: pd.DataFrame) -> pd.DataFrame:
    """Join the Understat parquets onto player rows and build their features.

    The join key is ``(code, UK match date)``: Understat carries no gameweek
    number, and a date plus a player is unique even in a double gameweek. A
    player-match with no Understat row keeps NaN stats, which LightGBM splits
    on natively — no imputation, deliberately, because "we have no shot data
    for him" is genuinely different from "he had no shots".

    With no parquet on disk at all the feature columns are still created,
    empty, so the model's schema is identical whether or not the scrape ever
    ran.
    """
    if store.exists(UNDERSTAT_PLAYER_PATH):
        us = store.load(UNDERSTAT_PLAYER_PATH)
    else:
        us = pd.DataFrame()
    if not us.empty:
        keyed = us.rename(columns={"minutes": "us_minutes"})
        keyed = keyed[["code", "date", "us_minutes"] + US_STATS]
        keyed["date"] = pd.to_datetime(keyed["date"], errors="coerce").dt.date
        keyed = keyed.drop_duplicates(subset=["code", "date"])
        df = df.copy()
        df["_date"] = pd.to_datetime(df["kickoff_time"], errors="coerce",
                                     utc=True).dt.tz_convert(
                                         "Europe/London").dt.date
        df = df.merge(keyed.rename(columns={"date": "_date"}),
                      on=["code", "_date"], how="left", validate="many_to_one")
        df = df.drop(columns=["_date"])
    df = add_understat_rolling(df)
    df = merge_understat_team(df, understat_team_rolled())
    return add_shrunken_rates(df)


def understat_team_rolled() -> pd.DataFrame | None:
    """The rolled Understat team frame, or ``None`` when there is no parquet.

    Shared by training and by ``advise``'s prediction frame, so both sides see
    the same team-level numbers.
    """
    if not store.exists(UNDERSTAT_TEAM_PATH):
        return None
    ut = store.load(UNDERSTAT_TEAM_PATH)
    return add_understat_team_rolling(ut) if not ut.empty else None
```

with the imports:

```python
from gaffer.data.understat import (UNDERSTAT_PLAYER_PATH, UNDERSTAT_TEAM_PATH)
from gaffer.features.engineer import (ROTATION_FEATURES, US_STATS, add_context,
                                      add_player_rolling, add_rotation,
                                      add_setpiece, add_shrunken_rates,
                                      add_understat_rolling,
                                      add_understat_team_rolling,
                                      merge_understat_team)
```

and the call inside `load_training_frame`, after `add_context`:

```python
    df = add_player_rolling(player_gw)
    df = add_rotation(df)
    df = add_setpiece(df)
    df = add_context(df, elo, elo_final)
    df = attach_understat(df)
```

In `src/gaffer/advise.py`, pass the same team frame into the prediction
frame:

```python
    pred_frame = build_prediction_frame(hist_raw, future, elo=None,
                                        elo_final=elo_final,
                                        understat_team=understat_team_rolled())
```

with `understat_team_rolled` added to the existing
`from gaffer.models.train import ...` line.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_attacking.py tests/test_train.py -v`
Expected: PASS (both files)

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/models/attacking.py src/gaffer/models/components.py src/gaffer/models/train.py src/gaffer/advise.py tests/test_attacking.py tests/test_train.py
git commit -m "feat: feed Understat and shrunken-rate features to the GBM heads

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 20: The degradation rail, as a regression test

Spec §11 asks for this explicitly: with every new source absent, behaviour
must be identical to v4a. Three switches (no football-data file, no Understat
parquet, no odds key) and each one has to be a no-op on its own and together.

**Files:**
- Create: `tests/test_degradation.py`
- Test: `tests/test_degradation.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_degradation.py`:

```python
"""Every v4b source has to be optional.

A fresh clone has no football-data CSV, no Understat parquet and no odds
API key, and it must behave exactly as the tool did before this cycle — the
same columns, the same fallbacks, the same numbers. These are the tests that
say so, gathered in one file so the rail is visible as a rail rather than
scattered across six suites.
"""

import numpy as np
import pandas as pd

from gaffer.features.engineer import (SHRUNK_FEATURES, TEAM_US_FEATURES,
                                      add_shrunken_rates,
                                      add_understat_rolling,
                                      merge_understat_team,
                                      understat_feature_columns)


def _plain_history(n_players=6, n_gws=12):
    """History with no Understat columns whatsoever."""
    rows = []
    for gw in range(1, n_gws + 1):
        for i in range(n_players):
            rows.append({
                "code": 100 + i, "season_idx": 0, "gw": gw,
                "position": ["GKP", "DEF", "MID", "FWD"][i % 4],
                "team_code": 1 + i % 2, "opp_code": 2 - i % 2,
                "was_home": i % 2 == 0, "minutes": 90,
                "kickoff_time": f"2024-08-{10 + gw:02d}T14:00:00Z",
                "goals": i % 3 == 0, "assists": 0, "starts": 1,
                "total_points": 2, "bps": 20, "bonus": 0})
    return pd.DataFrame(rows)


def test_understat_rolling_without_data_produces_only_nan_columns():
    out = add_understat_rolling(_plain_history())
    for col in understat_feature_columns():
        assert col in out.columns and out[col].isna().all()


def test_team_understat_without_data_produces_only_nan_columns():
    out = merge_understat_team(_plain_history(), None)
    for col in TEAM_US_FEATURES:
        assert col in out.columns and out[col].isna().all()


def test_shrunken_rates_survive_a_frame_with_no_goals_column():
    out = add_shrunken_rates(_plain_history().drop(columns=["goals"]))
    assert out["shrunk_goals90"].isna().all()
    assert "shrunk_assists90" in out.columns


def test_blend_weight_without_match_odds_is_the_module_constant():
    from gaffer.models.dixon_coles import walk_forward_cs
    from gaffer.models.team import ODDS_BLEND_WEIGHT, fit_blend_weight

    empty = pd.DataFrame(columns=["season_idx", "gw", "home_code",
                                  "away_code", "p_home", "p_draw", "p_away",
                                  "p_over25"])
    tg = pd.DataFrame([{"code": 1, "opp_code": 2, "home": 1.0,
                        "season_idx": 0, "gw": 1, "cs": 1, "gf": 1, "ga": 0,
                        "kickoff_time": "2024-08-11T14:00:00Z"}])
    assert fit_blend_weight(walk_forward_cs(tg, empty)) == ODDS_BLEND_WEIGHT


def test_blend_team_odds_without_an_odds_column_is_the_identity():
    from gaffer.models.team import blend_team_odds

    preds = pd.DataFrame({"code": [1], "season_idx": [0], "gw": [1],
                          "p_cs": [0.25], "e_gc": [1.4]})
    out = blend_team_odds(preds)
    assert out.equals(preds)


def test_odds_client_without_a_key_makes_no_request_for_player_props():
    from gaffer.data.odds import OddsClient

    def refuse(request):
        raise AssertionError("no key means no request")

    import httpx

    client = OddsClient("", client=httpx.Client(
        transport=httpx.MockTransport(refuse)))
    assert client.get_player_goalscorer_odds(["abc"]) is None


def test_blend_attacking_odds_with_no_odds_is_byte_identical():
    """Gate G3's no-key half: the AGS layer must be provably invisible when
    the market is not there."""
    from gaffer.data.odds import blend_attacking_odds

    comp = pd.DataFrame({"code": [1, 2], "gw": [1, 1], "opp_code": [9, 9],
                         "p_play": [0.9, 0.8], "e_goals": [0.4, 0.1],
                         "e_assists": [0.2, 0.1]})
    for absent in (None, pd.DataFrame()):
        out = blend_attacking_odds(comp, absent, weight=0.5)
        pd.testing.assert_frame_equal(out, comp)


def test_understat_client_with_a_dead_site_returns_empty_frames(tmp_path):
    import httpx

    from gaffer.data.understat import UnderstatClient

    client = UnderstatClient(
        client=httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(500))),
        cache_dir=tmp_path, sleep=0.0, retries=1)
    assert client.league_matches("2024-25").empty
    assert client.team_history("2024-25", 0).empty


def test_dixon_coles_predicts_every_row_of_an_all_promoted_fixture_list():
    """Worst case for the fallback: nobody in the fixture list was fitted."""
    from gaffer.models.dixon_coles import DixonColesModel
    from gaffer.models.team import build_team_gw

    rng = np.random.default_rng(0)
    fx = pd.DataFrame([
        {"season_idx": 0, "gw": 1 + i // 5,
         "kickoff_time": f"2024-08-{10 + i:02d}T14:00:00Z",
         "home_code": 1 + i % 4, "away_code": 1 + (i + 1) % 4,
         "home_goals": int(rng.poisson(1.4)),
         "away_goals": int(rng.poisson(1.1))}
        for i in range(40)])
    model = DixonColesModel().fit(build_team_gw(fx))
    future = pd.DataFrame([{"code": 900, "opp_code": 901, "home": 1.0,
                            "season_idx": 1, "gw": 1}])
    out = model.predict(future)
    assert out["p_cs"].notna().all() and out["e_gc"].notna().all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_degradation.py -v`
Expected: 2 FAILED, 7 passed — `ImportError: cannot import name
'blend_attacking_odds' from 'gaffer.data.odds'` and
`AttributeError: 'OddsClient' object has no attribute
'get_player_goalscorer_odds'`. Both halves land in Tasks 22-23; every other
test in this file should already pass.

- [ ] **Step 3: Make the already-implemented half green**

No implementation is written here — this task is a rail, not a feature. Run
the file excluding the two AGS tests, which Tasks 21 and 22 implement:

Run: `uv run pytest tests/test_degradation.py -v -k "not player_props and not blend_attacking"`
Expected: PASS (7 passed)

If any of those seven fails, that is a real degradation bug in a previous
task and must be fixed there before continuing.

- [ ] **Step 4: Mark the two AGS tests as pending**

Add `import pytest` to the file's import block, and put this decorator
directly above **both** `test_odds_client_without_a_key_makes_no_request_for_player_props`
and `test_blend_attacking_odds_with_no_odds_is_byte_identical`:

```python
@pytest.mark.xfail(reason="AGS layer lands in Tasks 22-23", strict=False)
```

**Task 23's Step 4 removes both decorators** — they are scaffolding with an
expiry date, not a permanent allowance.

Run: `uv run pytest tests/test_degradation.py -v`
Expected: PASS (7 passed, 2 xfailed)

- [ ] **Step 5: Commit**

```bash
git add tests/test_degradation.py
git commit -m "test: pin the graceful-degradation rail for every v4b source

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 21: Measure — shrinkage k and gate G2

Run-and-record.

**Files:**
- Modify: `src/gaffer/features/engineer.py:SHRINK_K` (pin the winner)
- Modify: `docs/superpowers/specs/2026-08-25-gaffer-v4b-model-design.md` §13 Outcome

- [ ] **Step 1: Fit the shrinkage k**

Run:

```bash
caffeinate -i uv run python -c "
from gaffer.features.engineer import best_shrinkage_k
from gaffer.models.train import load_training_frame
df, _tg, _elo = load_training_frame()
print('best k =', best_shrinkage_k(df))
"
```

Expected: a single line `best k = <one of 2.0, 5.0, 10.0, 20.0>`.

- [ ] **Step 2: Pin it**

Set `SHRINK_K` in `src/gaffer/features/engineer.py` to the winner and replace
the docstring's last sentence with the measured basis:

```python
SHRINK_K = 10.0
"""Prior weight, in nineties, for the empirical-Bayes rates.

``k`` is literally "how many matches of league-average evidence the prior is
worth". Chosen by out-of-sample correlation on the last ten gameweek slots
over the grid {2, 5, 10, 20} — see the v4b spec's Outcome table.
"""
```

(substituting the actual winner).

Run: `uv run pytest tests/test_features.py -v`
Expected: PASS

- [ ] **Step 3: Retrain on the full corpus**

Run: `caffeinate -i uv run gaffer train`
Expected: `Trained on N player-GW rows. Models saved to models/.` — N should
match the pre-change run; a large drop means the Understat join fanned out or
dropped rows and must be investigated before measuring anything.

- [ ] **Step 4: Run both evaluation modes**

Run: `caffeinate -i uv run gaffer evaluate --mode current`
Run: `caffeinate -i uv run gaffer evaluate --mode benchmark`
Expected: two reports; both merge into `reports/evaluation.json` without
clobbering each other.

- [ ] **Step 5: Evaluate gate G2 and record**

Extract into the spec's §13 Outcome:

| cut | metric | v4a | v4b | gate |
| --- | --- | --- | --- | --- |
| benchmark | haulers RMSE | 5.245 | | ≤ 5.245 (target 5.17) |
| benchmark | blanks RMSE | 1.673 | | — |
| benchmark | zeros RMSE | 1.074 | | out of scope this cycle |
| current | haulers RMSE | 4.950 | | ≤ 4.950 |

**G2 passes when** benchmark haulers RMSE ≤ 5.245 *and* current-mode haulers
RMSE ≤ 4.950. The FPLReview-parity target of 5.17 is a target, not a gate.

If G2 fails, drop the offending feature block — features are additive and
LightGBM's `cols_` intersect makes removal safe, so deleting a block from
`ATTACK_FEATURES` (Task 19) is the whole change — re-run
`gaffer train && gaffer evaluate --mode benchmark`, and record which block
was dropped and why. Try the blocks in this order: team-level
(`opp_us_xga_*`, `opp_ppda_*`), then shrunken rates, then the player per-90s,
since that is increasing order of how much signal the research expected from
each.

- [ ] **Step 6: Commit**

```bash
git add src/gaffer/features/engineer.py docs/superpowers/specs/2026-08-25-gaffer-v4b-model-design.md reports/evaluation.json
git commit -m "measure: pin the shrinkage k and record gate G2

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 22: Anytime-goalscorer odds

**Files:**
- Modify: `src/gaffer/data/odds.py` (append after `odds_frame`)
- Test: `tests/test_odds.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_odds.py`:

```python
# --- anytime goalscorer props ---------------------------------------------

from gaffer.data.odds import (AGS_EG_CAP, AGS_MARKET, ags_frame,
                              next_gw_event_ids, normalize_ags)

_AGS_EVENT = {
    "id": "evt1", "home_team": "Arsenal", "away_team": "Manchester City",
    "commence_time": "2026-08-29T14:00:00Z",
    "bookmakers": [{"key": "bk1", "markets": [
        {"key": "player_goal_scorer_anytime", "outcomes": [
            {"name": "Bukayo Saka", "price": 3.0},
            {"name": "Kai Havertz", "price": 3.5},
            {"name": "Erling Haaland", "price": 1.8}]}]}]}


def test_get_player_goalscorer_odds_without_a_key_makes_no_request():
    def refuse(request):
        raise AssertionError("no key means no request")

    assert OddsClient("", client=_client(refuse)).get_player_goalscorer_odds(
        ["evt1"]) is None


def test_get_player_goalscorer_odds_requests_the_event_endpoint(tmp_path,
                                                                monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    seen = {}

    def handler(request):
        seen["url"] = str(request.url).split("?")[0]
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=_AGS_EVENT)

    out = OddsClient("k", client=_client(handler)).get_player_goalscorer_odds(
        ["evt1"])
    assert seen["url"] == (
        "https://api.the-odds-api.com/v4/sports/soccer_epl/events/evt1/odds")
    assert seen["params"]["markets"] == AGS_MARKET
    assert out == [_AGS_EVENT]


def test_get_player_goalscorer_odds_returns_none_on_an_exhausted_quota(
        tmp_path, monkeypatch):
    """401/402/429 on the free tier is the normal end of the month, not an
    error worth failing the weekly run over."""
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    client = OddsClient("k", client=_client(
        lambda r: httpx.Response(402)), retries=1)
    assert client.get_player_goalscorer_odds(["evt1"]) is None


def test_next_gw_event_ids_picks_only_the_coming_gameweek():
    """The 29 Aug kickoff sits inside GW2's deadline window in ``_EVENTS``;
    asking for any other gameweek must spend no requests."""
    assert next_gw_event_ids([_AGS_EVENT], _EVENTS, gw=2) == ["evt1"]
    assert next_gw_event_ids([_AGS_EVENT], _EVENTS, gw=1) == []
    assert next_gw_event_ids([], _EVENTS, gw=2) == []


def test_normalize_ags_scales_lambdas_to_the_match_odds_mu():
    """One-sided prices carry an overround that no devig can strip, so the
    market-consistent fix is to make the team's implied goals match the
    number the two-sided match odds already gave us."""
    lam = normalize_ags({"Bukayo Saka": 3.0, "Kai Havertz": 3.5}, mu=1.6)
    assert abs(sum(lam.values()) - 1.6) < 1e-12
    # Ordering survives the scaling: the shorter price stays the bigger lambda.
    assert lam["Bukayo Saka"] > lam["Kai Havertz"]


def test_normalize_ags_on_an_empty_book_is_empty():
    assert normalize_ags({}, mu=1.6) == {}


def test_normalize_ags_with_a_zero_mu_is_all_zero():
    lam = normalize_ags({"A": 3.0}, mu=0.0)
    assert lam == {"A": 0.0}


def test_ags_frame_maps_names_and_teams_onto_codes():
    players = pd.DataFrame([
        {"code": 11, "name": "Bukayo Saka", "team_code": 3},
        {"code": 12, "name": "Kai Havertz", "team_code": 3},
        {"code": 13, "name": "Erling Haaland", "team_code": 43}])
    odds_df = odds_frame(SAMPLE_ODDS, _TEAMS, _EVENTS)
    out = ags_frame([_AGS_EVENT], players, _TEAMS, _EVENTS, odds_df)
    assert set(out.columns) == {"code", "gw", "team_code", "opp_code",
                                "lambda_ags"}
    assert set(out["code"]) == {11, 12, 13}
    # Arsenal's two priced players carry Arsenal's devigged mu between them.
    arsenal = out[out["team_code"] == 3]
    mu = float(odds_df[(odds_df["team_code"] == 3)]["odds_e_goals_for"].iloc[0])
    assert abs(arsenal["lambda_ags"].sum() - mu) < 1e-9


def test_ags_frame_drops_players_the_bootstrap_does_not_carry():
    players = pd.DataFrame([{"code": 11, "name": "Bukayo Saka",
                             "team_code": 3}])
    out = ags_frame([_AGS_EVENT], players, _TEAMS,
                    _EVENTS, odds_frame(SAMPLE_ODDS, _TEAMS, _EVENTS))
    assert set(out["code"]) == {11}


def test_ags_frame_without_match_odds_for_the_fixture_is_empty():
    """No devigged mu means no normalization target, and an un-normalized
    one-sided price is an overround, not a probability."""
    players = pd.DataFrame([{"code": 11, "name": "Bukayo Saka",
                             "team_code": 3}])
    out = ags_frame([_AGS_EVENT], players, _TEAMS, _EVENTS,
                    pd.DataFrame(columns=ODDS_FRAME_COLS))
    assert out.empty


def test_ags_frame_on_none_is_empty():
    players = pd.DataFrame([{"code": 11, "name": "Bukayo Saka",
                             "team_code": 3}])
    assert ags_frame(None, players, _TEAMS, _EVENTS,
                     odds_frame(SAMPLE_ODDS, _TEAMS, _EVENTS)).empty


def test_ags_cap_is_a_sane_per_appearance_ceiling():
    assert AGS_EG_CAP == 2.0
```

Add `ODDS_FRAME_COLS` to the file's existing
`from gaffer.data.odds import ...` line.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_odds.py -k ags -v`
Expected: FAIL — `ImportError: cannot import name 'AGS_EG_CAP' from 'gaffer.data.odds'`

- [ ] **Step 3: Write minimal implementation**

Add to `OddsClient` in `src/gaffer/data/odds.py`:

```python
    def get_player_goalscorer_odds(self, event_ids: list[str]) -> list | None:
        """Anytime-goalscorer prices for the given fixtures, best effort.

        One request per event — the-odds-api has no bulk player-props
        endpoint — so the caller passes only the *next* gameweek's fixtures
        and takes one snapshot per advise run; ten calls a week fits inside
        the free tier's monthly budget.

        Returns ``None`` on a missing key, an exhausted quota (401/402/429) or
        a transport failure, exactly like :meth:`get_epl_odds`: player props
        are the most optional signal in the model and must never be able to
        block a week's advice.
        """
        if not self.api_key:
            return None
        out = []
        for event_id in event_ids:
            try:
                data = self._get(
                    f"sports/soccer_epl/events/{event_id}/odds",
                    params={"regions": "eu", "markets": AGS_MARKET,
                            "oddsFormat": "decimal", "apiKey": self.api_key},
                    snapshot=f"ags-{event_id}")
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                print(f"player props unavailable ({exc})")
                return None
            if data:
                out.append(data)
        return out or None
```

Append to `src/gaffer/data/odds.py`:

```python
AGS_MARKET = "player_goal_scorer_anytime"
AGS_EG_CAP = 2.0
"""Ceiling on odds-implied expected goals *per appearance*.

``lambda / p_play`` divides by a probability, so a fringe player with a
0.05 chance of playing and a long price would otherwise come out at an
absurd per-appearance rate. Nobody in this league is a two-goals-a-game
player; the cap is where the arithmetic stops being a signal.
"""

AGS_FRAME_COLS = ["code", "gw", "team_code", "opp_code", "lambda_ags"]


def next_gw_event_ids(raw_odds: list, events: pd.DataFrame,
                      gw: int) -> list[str]:
    """The-odds-api event ids whose kickoff falls in gameweek ``gw``.

    The free tier is metered per request, so only the gameweek being advised
    is worth spending calls on.
    """
    windows = _gw_windows(events)
    out = []
    for fixture in raw_odds or []:
        kickoff = pd.to_datetime(fixture["commence_time"], utc=True,
                                 format="mixed")
        found = next((g for start, end, g in windows
                      if start <= kickoff < end), None)
        if found == gw and fixture.get("id"):
            out.append(str(fixture["id"]))
    return out


def normalize_ags(prices: dict[str, float], mu: float) -> dict[str, float]:
    """One-sided anytime prices -> per-player expected goals summing to ``mu``.

    Anytime-scorer markets quote backs only, so there is no complementary
    price to devig against and neither Shin nor proportional normalization
    applies. What *is* available is a second, two-sided estimate of the same
    quantity: the devigged match odds already say how many goals this team is
    expected to score. Converting each price to a rate with
    ``lambda = -ln(1 - p)`` and scaling the lot so they sum to that ``mu`` is
    the market-consistent way to strip the one-sided overround — it keeps the
    market's *relative* view of who scores and takes the *level* from the
    market's own better-measured number.
    """
    raw = {}
    for name, price in prices.items():
        p = min(max(1.0 / float(price), 1e-9), 1.0 - 1e-9)
        raw[name] = -math.log(1.0 - p)
    total = sum(raw.values())
    if not raw or total <= 0.0:
        return {name: 0.0 for name in raw}
    scale = float(mu) / total
    return {name: value * scale for name, value in raw.items()}


def ags_frame(raw_ags: list | None, players: pd.DataFrame,
              teams: pd.DataFrame, events: pd.DataFrame,
              odds_df: pd.DataFrame) -> pd.DataFrame:
    """Player props -> ``[code, gw, team_code, opp_code, lambda_ags]``.

    Each fixture's priced players are split by club, normalized against that
    club's devigged ``odds_e_goals_for`` from :func:`odds_frame`, and matched
    to FPL codes by normalized name *and* club. A fixture with no match-odds
    row is skipped entirely: without a devigged mu there is nothing to
    normalize against, and an un-normalized one-sided book is an overround
    rather than a set of probabilities.

    Players the bootstrap does not carry are dropped; FPL players nobody
    priced simply get no row and keep pure model output downstream.
    """
    from gaffer.data.names import normalize_name

    if raw_ags is None or odds_df is None or odds_df.empty:
        return pd.DataFrame(columns=AGS_FRAME_COLS)
    code_of_team = dict(zip(teams["name"], teams["code"]))
    by_name_team = {(normalize_name(r.name), int(r.team_code)): int(r.code)
                    for r in players.itertuples()}
    mu_of = {(int(r.team_code), int(r.opp_code), int(r.gw)):
             float(r.odds_e_goals_for) for r in odds_df.itertuples()}
    windows = _gw_windows(events)

    rows = []
    for fixture in raw_ags:
        books = fixture.get("bookmakers") or []
        market = _market(books[0], AGS_MARKET) if books else None
        if market is None:
            continue
        try:
            home = resolve_team(fixture["home_team"])
            away = resolve_team(fixture["away_team"])
        except GafferError as exc:
            print(f"player props: {exc}")
            continue
        if home not in code_of_team or away not in code_of_team:
            continue
        home_code, away_code = code_of_team[home], code_of_team[away]
        kickoff = pd.to_datetime(fixture["commence_time"], utc=True,
                                 format="mixed")
        gw = next((g for start, end, g in windows
                   if start <= kickoff < end), None)
        if gw is None:
            continue

        # Split the book by the club each priced player actually plays for:
        # the market lists both sides together and normalization is per team.
        by_team: dict[int, dict[str, float]] = {home_code: {}, away_code: {}}
        matched: dict[str, int] = {}
        for outcome in market.get("outcomes", []):
            name = normalize_name(outcome.get("name"))
            for team_code in (home_code, away_code):
                code = by_name_team.get((name, int(team_code)))
                if code is not None:
                    by_team[team_code][str(outcome["name"])] = float(
                        outcome["price"])
                    matched[str(outcome["name"])] = code
                    break

        for team_code, opp_code in ((home_code, away_code),
                                    (away_code, home_code)):
            mu = mu_of.get((int(team_code), int(opp_code), int(gw)))
            if mu is None or not by_team[team_code]:
                continue
            for name, lam in normalize_ags(by_team[team_code], mu).items():
                rows.append({"code": matched[name], "gw": int(gw),
                             "team_code": int(team_code),
                             "opp_code": int(opp_code), "lambda_ags": lam})
    return pd.DataFrame(rows, columns=AGS_FRAME_COLS)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_odds.py -v`
Expected: PASS (whole file, including the 12 new tests)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/data/odds.py tests/test_odds.py
git commit -m "feat: anytime-goalscorer odds normalized against the match mu

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 23: Blend AGS into `e_goals` and verify G3

**Files:**
- Modify: `src/gaffer/data/odds.py` (append after `ags_frame`)
- Modify: `src/gaffer/advise.py:463-468` (`run_advise`)
- Test: `tests/test_odds.py` (append)
- Test: `tests/test_degradation.py` (remove the two xfail decorators)
- Modify: `docs/superpowers/specs/2026-08-25-gaffer-v4b-model-design.md` §13 Outcome

- [ ] **Step 1: Write the failing test**

Append to `tests/test_odds.py`:

```python
from gaffer.data.odds import AGS_BLEND_WEIGHT_DEFAULT, blend_attacking_odds


def _comp() -> pd.DataFrame:
    return pd.DataFrame({
        "code": [11, 12], "gw": [1, 1], "opp_code": [43, 43],
        "p_play": [0.9, 0.5], "e_goals": [0.20, 0.10],
        "e_assists": [0.15, 0.05]})


def _ags() -> pd.DataFrame:
    return pd.DataFrame({"code": [11], "gw": [1], "team_code": [3],
                         "opp_code": [43], "lambda_ags": [0.45]})


def test_blend_attacking_odds_mixes_the_two_expectations():
    out = blend_attacking_odds(_comp(), _ags(), weight=0.5)
    # e_goals_odds = lambda / p_play = 0.45 / 0.9 = 0.5
    assert abs(out.loc[0, "e_goals_odds"] - 0.5) < 1e-12
    assert abs(out.loc[0, "e_goals"] - (0.5 * 0.5 + 0.5 * 0.20)) < 1e-12


def test_blend_attacking_odds_leaves_unpriced_players_alone():
    out = blend_attacking_odds(_comp(), _ags(), weight=0.5)
    assert out.loc[1, "e_goals"] == 0.10
    assert pd.isna(out.loc[1, "e_goals_odds"])


def test_blend_attacking_odds_caps_the_per_appearance_rate():
    """A fringe player with a long price and a tiny p_play would otherwise
    imply an absurd per-appearance rate."""
    comp = _comp()
    comp.loc[0, "p_play"] = 0.05
    out = blend_attacking_odds(comp, _ags(), weight=1.0)
    assert out.loc[0, "e_goals"] == AGS_EG_CAP


def test_blend_attacking_odds_ignores_a_zero_p_play():
    comp = _comp()
    comp.loc[0, "p_play"] = 0.0
    out = blend_attacking_odds(comp, _ags(), weight=1.0)
    assert out.loc[0, "e_goals"] == 0.20


def test_blend_attacking_odds_does_not_add_or_reorder_rows():
    """Components are stitched positionally everywhere downstream."""
    out = blend_attacking_odds(_comp(), _ags(), weight=0.5)
    assert list(out["code"]) == [11, 12]
    assert len(out) == 2


def test_blend_attacking_odds_leaves_assists_untouched():
    """The free tier drops assist props, so there is nothing to blend there
    and pretending otherwise would double-count the goals signal."""
    out = blend_attacking_odds(_comp(), _ags(), weight=1.0)
    assert list(out["e_assists"]) == [0.15, 0.05]


def test_default_ags_weight_is_a_half():
    """No historical AGS record exists to fit on — a known limitation, an
    even split until a season of snapshots accumulates."""
    assert AGS_BLEND_WEIGHT_DEFAULT == 0.5


def test_run_advise_blends_player_props_before_assembling_ep():
    """Source-level seam (no cheap end-to-end harness for run_advise): the
    AGS blend has to land on the component frame before assemble_ep reads
    it, and the protected calibration literal must survive intact."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    comp = src.index("comp = predict_components(")
    blend = src.index("blend_attacking_odds(")
    assemble = src.index("ep_matrix(apply_calibration(assemble_ep(")
    assert comp < blend < assemble
    assert "cfg.player_props" in src
    assert "except Exception" in src[blend - 600:blend + 600]


def test_run_advise_still_orders_the_league_tilt_seam():
    """The other two protected orderings must not have moved."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    assert (src.index("fetch_rival_entries(") < src.index("tilt_ep(")
            < src.index("pool = build_pool("))
    assert "build_pool(players, pool_ep," in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_odds.py -k blend_attacking -v`
Expected: FAIL — `ImportError: cannot import name 'AGS_BLEND_WEIGHT_DEFAULT' from 'gaffer.data.odds'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/gaffer/data/odds.py`:

```python
AGS_BLEND_WEIGHT_DEFAULT = 0.5
"""Share of ``e_goals`` taken from the anytime-scorer market.

Every other weight in this codebase is fitted; this one cannot be. The-odds-
api serves only live prices, so there is no historical anytime-scorer record
to fit against — a known limitation, revisited once a season of weekly
snapshots has accumulated (``data/raw/ags-*.json``). Half is the honest prior
for two estimators nobody has measured against each other yet.
"""


def blend_attacking_odds(comp: pd.DataFrame, ags: pd.DataFrame | None,
                         weight: float = AGS_BLEND_WEIGHT_DEFAULT
                         ) -> pd.DataFrame:
    """Blend odds-implied expected goals into the model's ``e_goals``.

    ``lambda_ags`` is a per-*fixture* expectation, while ``e_goals`` is a
    per-*appearance* rate that assembly multiplies by ``p_play`` — so the
    market number is divided by ``p_play`` before the two are comparable, and
    capped at :data:`AGS_EG_CAP` because that division blows up for a fringe
    player. Rows with no price, or no chance of playing, keep pure model
    output.

    Called before ``assemble_ep``'s inputs are built, which keeps the
    protected ``ep_matrix(apply_calibration(assemble_ep(`` literal in
    ``run_advise`` exactly where it is. A missing or empty ``ags`` returns the
    caller's frame untouched — the no-key path has to be byte-identical to
    the no-AGS path, and gate G3 tests that it is.
    """
    if ags is None or ags.empty or "e_goals" not in comp.columns:
        return comp
    keyed = (ags[["code", "gw", "opp_code", "lambda_ags"]]
             .drop_duplicates(subset=["code", "gw", "opp_code"]))
    out = comp.merge(keyed, on=["code", "gw", "opp_code"], how="left",
                     validate="many_to_one")
    p_play = pd.to_numeric(out["p_play"], errors="coerce")
    has = out["lambda_ags"].notna() & (p_play > 0)
    out["e_goals_odds"] = float("nan")
    out.loc[has, "e_goals_odds"] = (
        out.loc[has, "lambda_ags"] / p_play[has]).clip(upper=AGS_EG_CAP)
    w = float(weight)
    out.loc[has, "e_goals"] = (w * out.loc[has, "e_goals_odds"]
                               + (1.0 - w) * out.loc[has, "e_goals"])
    return out
```

In `src/gaffer/advise.py`, extend the odds import:

```python
from gaffer.data.odds import (OddsClient, ags_frame, blend_attacking_odds,
                              next_gw_event_ids, odds_frame)
```

and insert the AGS block in `run_advise` between `predict_components` and the
calibration load:

```python
    comp = predict_components(pred_frame, tg_future, players)
    # Player props are the most optional signal here: the free tier meters
    # every request, the market may not exist for a fixture, and a quota that
    # ran out mid-month must cost the blend and nothing else. Only the next
    # gameweek's fixtures are priced, so only they are worth a request.
    ags = None
    if cfg.odds_api_key and cfg.player_props and raw_odds:
        try:
            event_ids = next_gw_event_ids(raw_odds, events, gw)
            raw_ags = OddsClient(cfg.odds_api_key).get_player_goalscorer_odds(
                event_ids)
            if raw_ags:
                ags = ags_frame(raw_ags, players, teams, events, odds_df)
        except Exception as e:  # noqa: BLE001 — props must never block advice
            print(f"player props unusable, continuing without: {e}")
    comp = blend_attacking_odds(comp, ags, weight=cfg.ags_blend_weight)
    # Optional artifact: model directories trained before calibration existed
    # have no such file, and None means the identity map.
    cal = load_model("calibration") if model_exists("calibration") else None
```

`raw_odds` is currently assigned only inside the `if cfg.odds_api_key:` block,
so hoist its initialization beside `odds_df`:

```python
    odds_df = None
    raw_odds = None
    if cfg.odds_api_key:
        try:
            raw_odds = OddsClient(cfg.odds_api_key).get_epl_odds()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_odds.py tests/test_advise.py tests/test_assemble.py -v`
Expected: PASS — the three protected source-text tests included

Remove both `@pytest.mark.xfail` decorators added in Task 20 from
`tests/test_degradation.py`.

Run: `uv run pytest tests/test_degradation.py -v`
Expected: PASS (9 passed, 0 xfailed)

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 5: Verify gate G3**

Two halves, both required.

*No-key half (automated):* the two degradation tests above are the gate.
`blend_attacking_odds` on `None` returns the caller's frame object unchanged,
so the no-AGS path is byte-identical by construction.

*Live half (spot check):* with `[odds] api_key` set in `config.toml`, on a
week whose fixtures the market has priced.

1. Set `[odds] player_props = false`, run `caffeinate -i uv run gaffer advise`,
   and copy the result aside:
   `cp data/live/predictions/gw<N>.parquet /tmp/ep_no_ags.parquet`
   (substituting the gameweek the run reported).
2. Set `[odds] player_props = true`, run `caffeinate -i uv run gaffer advise`
   again.
3. Diff the two:

```bash
uv run python -c "
import pandas as pd
off = pd.read_parquet('/tmp/ep_no_ags.parquet')[['code','name','ep']]
on = pd.read_parquet('data/live/predictions/gw<N>.parquet')[['code','ep']]
j = off.merge(on, on='code', suffixes=('_off','_on'))
j['delta'] = j['ep_on'] - j['ep_off']
moved = j[j['delta'].abs() > 1e-9]
print('moved:', len(moved), 'of', len(j))
print('max abs delta:', moved['delta'].abs().max())
print(moved.reindex(moved['delta'].abs().sort_values(ascending=False).index)
      .head(15).to_string(index=False))
"
```

Record in the spec's §13 Outcome:

- how many players moved at all (should be roughly the number of priced
  players in the gameweek, ~100-200),
- the largest absolute EP delta (**a delta above ~1.5 points is not
  plausible** for a 0.5-weight blend on a capped goals term and means the
  normalization or the cap is wrong — investigate before shipping),
- whether the biggest movers are the players the market disagrees with the
  model about, by name, and whether that disagreement reads as sensible.

**G3 passes when** the no-key path is identical *and* the live deltas are
bounded and plausible by that inspection.

- [ ] **Step 6: Commit**

```bash
git add src/gaffer/data/odds.py src/gaffer/advise.py tests/test_odds.py tests/test_degradation.py docs/superpowers/specs/2026-08-25-gaffer-v4b-model-design.md
git commit -m "feat: blend anytime-goalscorer odds into e_goals in the advise path

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 24: The final evaluation

Run-and-record. This is the cycle's after-photo, and the only place the spec's
§13 Outcome becomes complete.

**Files:**
- Modify: `docs/superpowers/specs/2026-08-25-gaffer-v4b-model-design.md` §13 Outcome
- Modify: `reports/evaluation.json` (written by the runs)

- [ ] **Step 1: Confirm the suite is green**

Run: `uv run pytest`
Expected: PASS, **at least 475 tests** (v4a's count) — this cycle adds
roughly 150 more, so a total below ~620 means a file was not collected.

Run (from `frontend/`): `npx vitest run`
Expected: PASS (58+)

Run (from `frontend/`): `npx tsc -b`
Expected: no output, exit 0

- [ ] **Step 2: Refit everything from scratch**

Run: `caffeinate -i uv run gaffer build-history`
Run: `caffeinate -i uv run gaffer understat`
Run: `caffeinate -i uv run gaffer train`
Expected: each prints its summary line; `gaffer train` writes
`models/blend.params.json` with the fitted weight.

- [ ] **Step 3: Run both evaluation modes**

Run: `caffeinate -i uv run gaffer evaluate --mode current`
Run: `caffeinate -i uv run gaffer evaluate --mode benchmark`
Expected: two reports, both merged into `reports/evaluation.json`.

- [ ] **Step 4: Fill in the spec's Outcome**

Replace §13 of
`docs/superpowers/specs/2026-08-25-gaffer-v4b-model-design.md` with the
measured record:

- **Fitted w** and **chosen ξ** and **chosen k**, with the grids that
  produced them (the tables from Tasks 11 and 21).
- **G1**: CS log loss before/after, the reliability curve before/after, and
  the stratified no-regression check.
- **G2**: the benchmark and current-mode haulers/blanks/tickers/zeros table
  against v4a and against OpenFPL's published numbers.
- **G3**: the no-key identity result and the live spot-check numbers.
- **Ingestion counts**: football-data matched/unmatched per season, and the
  Understat mapping's exact/cross-club/override/unmatched counts.
- **Anything dropped**: any feature block removed under G2's fallback, and
  whether `TEAM_MODEL` ended on `"dixon_coles"` or `"gbm"`.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-08-25-gaffer-v4b-model-design.md reports/evaluation.json src/gaffer/assets/understat_overrides.json
git commit -m "measure: v4b outcome tables for G1-G3 and the benchmark deltas

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Execution Notes

- **Python tests:** `uv run pytest` from the repo root. A single file:
  `uv run pytest tests/test_dixon_coles.py -v`.
- **Frontend:** unchanged this cycle. `npx vitest run` and `npx tsc -b` from
  `frontend/` are verification only, in Task 24. The Quality page re-renders
  whatever `reports/evaluation.json` holds, so no UI work is needed.
- **The full suite must be green before every commit**, not just the file you
  touched.
- **Long runs go under `caffeinate -i`.** `gaffer understat` is ~1900 pages at
  one second each; `gaffer evaluate --mode benchmark` is a full refit plus 38
  gameweeks of prediction; the ξ grid is three of those. Machine sleep has
  killed long runs in this repo before. None of the *coding* tasks need a real
  run — every test uses fixtures or mock transports — so the real runs live in
  Tasks 11, 15, 21, 23 and 24 only.
- **No network in tests, ever.** httpx clients are injected and driven by
  `httpx.MockTransport`, matching `tests/test_odds.py`'s existing convention.
  A test that would hit understat.com or football-data.co.uk is a bug.
- **Never touch `.claude/`.** It is untracked and must stay untracked.
  `git add -A` and `git add .` are forbidden anywhere in this plan; every
  commit step lists its files explicitly.
- **Protected source-text tests.** `tests/test_assemble.py`,
  `tests/test_odds.py` and `tests/test_advise.py` assert on the *source text*
  of `run_advise` / `predict_components`: the literal
  `ep_matrix(apply_calibration(assemble_ep(`, `blend_team_odds(` appearing
  before `comp.merge(tp`, and the ordering `fetch_rival_entries(` <
  `tilt_ep(` < `pool = build_pool(` with the literal
  `build_pool(players, pool_ep,`. Tasks 10, 19 and 23 all edit `advise.py`;
  each one ends by running the whole suite for exactly this reason. If one of
  these fails, the fix is to restore the literal, never to relax the test.
- **`TeamModel` stays.** Spec §9 keeps it for one cycle as G1's fallback. Do
  not delete it, its tests, or `TEAM_FEATURES`, even after G1 passes.
- **`devig` stays too**, as the documented proportional fallback and as the
  devigger for two-way totals. Only the 1X2 triples move to Shin.
- **Elo stays.** Spec §5: `compute_elo` and the `elo_diff` / `team_elo` /
  `opp_elo` features remain in the attacking, saves and minutes heads — cheap
  and already validated. Only the team CS/GC head stops using them, and it
  does so by being a different class, not by anything being deleted.
  `TEAM_FEATURES` is untouched.
- **No imputation for missing Understat stats.** LightGBM splits on NaN
  natively, and "no shot data for this match" is genuinely different
  information from "no shots". Any `fillna(0)` on a `us_*` column is a bug.
- **Ordering.** Tasks 1-4 are independent of everything after them. Tasks 5-10
  must land in order and 11 measures them. Tasks 12-15 are independent of
  5-11 and can be worked in parallel with them if two workers are available.
  Tasks 16-19 need 15's parquets to exist for the *measurement* but not to
  compile — their tests build frames by hand. Task 20 needs 19; Task 21
  measures 16-19. Tasks 22-23 need only Task 1. Task 24 needs everything.
