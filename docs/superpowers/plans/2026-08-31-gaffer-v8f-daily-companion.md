# Gaffer v8f Daily Companion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** turn gaffer from a tool you poll into a system that watches for you. Five things it cannot do today — keep a price history instead of printing one and forgetting it, star a player it is not already planning to buy, tell you on a Friday evening what needs doing without you opening it, tell you on a Tuesday morning how last week went, and say which players the retrain actually moved.

**Architecture:** a banking-and-reporting cycle. One new append-only store (`data/live/price_log.parquet`, the snapshot.py idiom), one new tiny JSON store (`reports/watchlist.json`, the overrides.py idiom), one new read-only reporting module (`src/gaffer/digest.py`) that joins seven things already on disk into two artifacts and one local notification, and one bounded predecessor copy (`components_gw{N}_prev.parquet`) that finally makes the retrain diff say something about players. Two new job kinds, two new plists, one new config key. Nothing trains, nothing solves, no model changes, and every card is **absent** — not zeroed — when its input is absent.

**Tech Stack:** Python 3.12, uv, pandas/pyarrow, FastAPI + pydantic, typer, pytest; React 19 + TypeScript + vitest.

**Prerequisite:** work on branch `feat/gaffer-v8f`. Authoritative spec: `docs/superpowers/specs/2026-08-31-gaffer-v8f-daily-companion-design.md`. Measurement rules: `docs/superpowers/CONVENTIONS.md`.

**Protected — must show zero diffs at the end (Task 10 audits this), except the seven authorized pin lines named in Task 5's STOP:**
`src/gaffer/advise.py`, `src/gaffer/set_pieces.py`, `src/gaffer/optimize/**`,
`src/gaffer/web/jobs.py`, `src/gaffer/web/routers/jobs.py`,
`src/gaffer/web/routers/whatif.py`,
`tests/test_advise.py`, `tests/test_odds.py`, `tests/test_web_jobs.py`,
every pre-v8f `tests/test_*_degradation.py` (v6, v7*, v8a, v8b, v8c, v8d, v8e, v8g),
`scripts/s2_replay.py`.

**Import-only:** `src/gaffer/journal.py`, `src/gaffer/backtest.py`, and the whole of `src/gaffer/optimize/`. This cycle imports nothing at all from `optimize`.

`src/gaffer/advise.py` is protected and stays that way, which has one consequence the plan must state up front rather than let a task discover: **the advice payload's `price_alerts` watch set does not change.** It stays `buys + sells + owned` (advise.py:858-860), because widening it would need an edit inside a protected file. The wider watch set — squad, plan, *and* the watchlist — belongs to the web card, which computes its own alerts server-side from the banked bootstrap snapshot (A4). The two lists therefore differ by exactly the starred players, deliberately, and the card says which source each row came from.

If a task appears to need an edit inside a protected or import-only file, the plan is wrong: stop and report rather than editing.

**Staging rule:** every `git add` below names exact files. Never `git add -A`. Never stage `data/`, `reports/`, `models/`, `logs/`, `.claude/` or `config.toml`. v8f commits no data asset.

**Gate rule (CONVENTIONS.md §7):** implementers build the driver and never run the gates. Task 10 is the checklist, unfilled.

**Suite baselines:** 2468 python tests; 441 frontend tests + 1 skipped. Every task's final run must leave the pre-existing suites green — with the single exception of the moment described in Task 5's STOP, which is the only point in this cycle where a protected file changes.

**Commit trailer — every commit:**

```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
```

---

## Ambiguities the spec left open, and how this plan settles them

Eleven things the spec does not pin, decided here once so no task has to decide them twice.

**A1 — the price log's row is the predictor's reading, not a price change.** One row per player per UTC day with exactly the six fields D1 names: `snap_date`, `code`, `now_cost`, `price_change_percent`, `direction`, `calibrating`. Every player in the bootstrap gets a row, not only the ones near a threshold — the whole point of banking is that the interesting question ("what did the predictor say about him three days *before* he rose?") is not answerable from a file that only kept the alerts. `direction` is therefore three-valued here where `price_alerts` has two: `rise` above zero, `drop` below, `flat` at exactly zero, and null where the predictor published nothing (a locked player, a pre-season row). `flat` is a reading and null is the absence of one, and collapsing them would make "the predictor had no opinion" indistinguishable from "the predictor said no movement".

No `name` column. Names live in `data/live/players.parquet` and a code is a stable join key, whereas a web name is not — banking Wirtz's display name every day for a season stores nothing but the day FPL changed it.

`snap_date` is UTC and is the idempotency key, exactly as `snapshot.snap_date` is, for the same reason: FPL applies price changes at roughly 00:00 UK and the nightly job runs at 23:15 local, so a machine that travels or crosses a clock change must not bank two "days" for one. `price_log.py` imports `snap_date` from `gaffer.snapshot` rather than restating it — one definition of "today" across both logs, or the two drift apart in exactly the week somebody wants to join them.

**A2 — the price log is banked by `gaffer prices`, and banking never changes what `prices` prints.** The CLI's stdout contract is pinned (D1c) and the banking is instrumentation bolted beside it, in its own `try`, printing its own line. An unwritable `data/` directory costs the day's row and nothing else: the alert list still prints, the command still exits zero. That ordering matters — the bank happens **after** the alerts are printed, so a failure in the new code cannot swallow the output the command has always produced.

**A3 — the watchlist is codes plus a note, capped at 100, and is never an input to anything the model solves.** `reports/watchlist.json`, `{"watchlist": {"<code>": {"note": str, "set_at": iso}}}` — `overrides.py`'s shape minus the two numbers, because the two numbers are the entire reason overrides validate as hard as they do and a watchlist claims nothing about a player at all. A hundred rather than overrides' fifty: a pin is a claim the manager is making and fifty claims is a second model, whereas a watchlist is a shortlist and a hundred is two squads' worth of candidates.

It is read by exactly two things — the movers watch set (A4) and the Friday digest's flagged section — and by nothing that solves, trains, or scores. A star is a bookmark.

**A4 — the movers card recomputes its alerts server-side from the banked bootstrap snapshot, and says so.** Not from the advice payload's `price_alerts`, whose watch set is frozen by advise.py's protection (see the preamble), and not from the FPL API, because a card on a page must not make a network call on a page load. `GET /api/prices/movers` reads `data/live/players.parquet` — the snapshot every `refresh` and every `advise` rewrites — and runs `price_alerts` over `owned ∪ plan ∪ watchlist`.

The consequence is that the card can be stale, so it carries `as_of`, the snapshot file's mtime, and the card prints it. A movers strip that silently showed Tuesday's predictor readings on a Friday evening would be worse than no strip: the whole feature is "tell me what is about to happen tonight".

`source` per row is `squad`, `plan` or `watchlist`, resolved in that order, so a starred player who is also in the squad reads as `squad`. The label is what makes the card explicable — "why is he here?" has an answer on the row.

**A5 — a digest section is absent, never empty.** Both digests return `{"kind", "generated_at", "gw", "headline", "sections": [...]}` where each section is `{"key", "title", "bits": [str]}`. A section whose input is missing does not appear in the list. This is the DiffStrip `bits[]` idiom (WhyPanel.tsx:10-48) lifted whole: prose assembled server-side into a list of clauses, rendered client-side by joining them, so there is no markdown dependency and no template.

The rule has teeth. A Friday with no ledger is a Friday briefing with five sections rather than a Friday briefing containing "Last week: no data". A Tuesday before the first review is a debrief whose only section is the staleness one, and its `headline` says the season has not been reviewed yet — which is a true sentence, where a debrief of zeros would be four false ones.

The artifacts are `reports/digest_friday.json` and `reports/digest_tuesday.json`, replace-on-write through a temp file and `os.replace` (`overrides.save_overrides`'s idiom). Replace rather than append: a digest is about *now*, and a log of forty Fridays is a thing nobody reads that the ledger already keeps properly.

**A6 — the digest reads, and never writes anything but its own artifact.** Named because the temptation is real and the failure would be expensive: `review.append_ledger` takes a lock and is the ledger's only writer, and a Tuesday digest that re-graded a gameweek in order to report on it would be a second writer on a locked store, run by a launchd job, at the same hour as the review job. The digest calls `review.load_ledger()` and `review.season_summary()` and stops there. Same for `league_sim.load_sim_history()`, `misses.biggest_misses()`, `artifacts.load_advice()`, `artifacts.load_availability()` and `presser_log.load_presser_log()`: every one of them is already a never-raising reader, and the digest adds no writer beside any of them.

**A7 — the notification is best-effort, is not a dependency, and is off in tests.** `subprocess.run(['osascript', '-e', script], ...)` with a timeout, wrapped so that every failure — no `osascript` (a Linux CI box), a refused notification permission, a timeout, a non-zero exit — is swallowed and printed. It returns `True`/`False` so a test can assert it was *not* called, which is the rail that matters: `notify=False` must produce zero `osascript` invocations, not a suppressed one.

The gating is an explicit `notify: bool` argument on `run_digest`, and the config key that feeds it (`[digest] notify`) is wired at the CLI and job-kind seam in Task 5. That split is deliberate and is what lets this cycle have exactly **one** stop-point: adding a config field breaks a protected count pin, adding a job kind breaks five more, and both edits happen at the same moment (Task 5's STOP) rather than at two.

The script is built with `json.dumps` on both the title and the body, which is what makes a player named `O'Brien` — or a note the user typed — safe inside an AppleScript string literal. Never string concatenation into a shell; `shell=False` throughout.

**A8 — the two new plists need no change to the installer's convention.** `install_automation.sh:5-12` loops over *plist names* and substitutes only `__PROJECT_DIR__`; the command line lives inside each plist's own `ProgramArguments`, not in the loop. So `com.gaffer.digest-friday.plist` whose body is `uv run gaffer digest --kind friday` drops into the existing loop unchanged, and the loop gains two words. The alternative — teaching the loop to map a job name to a different command — would be a convention change bought for nothing.

Friday 17:00 and Tuesday 09:30, both `StartCalendarInterval` with a `Weekday` (6 and 2 respectively; launchd's Sunday is 0). 09:30 rather than 09:00 so the Tuesday debrief reads a ledger the 09:00 review job has already written, and 17:00 on Friday because the pressers are in and the deadline is not.

**A9 — `ep_movers` compares each frame's own first gameweek, and one predecessor is the whole history.** `save_components` copies the existing `components_gw{N}.parquet` to `components_gw{N}_prev.parquet` before overwriting it — one slot, bounded, no rotation, because the question is "what did tonight's retrain change" and a third file answers no question anybody asked. A copy failure is printed and swallowed: banking the *current* components is the function's actual job and a lost diff is not worth a failed advise run.

The diff is keyed on `code` and compares, in each frame independently, the sum of `ep` over that frame's own **minimum** gameweek. Not `(code, gw)` across the union: a retrain that also rolls the horizon forward would then report every player as having "moved" from a gameweek that is no longer in the file. The first gameweek is the week being decided, it is the only one both frames are certain to share, and it is the number on This Week's screen.

`ep_movers` returns `[]` when there is no predecessor **and** the payload distinguishes that from "nothing moved": `ep_movers_count` is `None` when there is no prev file and an integer otherwise. The first advise run after this cycle merges therefore says nothing at all rather than claiming a quiet retrain, and the second says something true.

**A10 — the movers strip renders when there is anything to say, which is not the same as `available`.** `WhyPanel.tsx:154` currently gates DiffStrip on `diff.available && diff.changed`, and `available` is false on a first run of the week. But a first run of the week is exactly when a retrain happened, so `ep_movers` can be non-empty while `available` is false. The condition widens to `(diff.available && diff.changed) || diff.ep_movers.length > 0`, and the strip's two `available`-only ornaments — the `previous_at` stamp and the xPts delta — are each guarded so a movers-only strip does not print a timestamp of `null` beside a delta of `0.0`.

**A11 — the Digest card renders the newest of the two artifacts, and the movers strip lives inside it.** `GET /api/digest` compares the two files' `generated_at` strings and serves the later one; `?kind=friday|tuesday` pins a choice. Newest-wins rather than day-of-week-wins because the artifact's own timestamp is a fact and the browser's clock is not, and because a user who presses the Tuesday button on a Saturday should see what they just generated.

The card sits on This Week immediately after `MovesCard` (ThisWeek.tsx:233), which is where the reading order puts it: the plan, then the week around the plan. It fetches its own data on `PensSection`'s self-fetching idiom, so a missing digest cannot blank the moves above it.

---

## File structure

| File | Status | Responsibility |
| --- | --- | --- |
| `src/gaffer/price_log.py` | Create | T1: the daily predictor bank. |
| `tests/test_price_log.py` | Create | T1. |
| `src/gaffer/cli.py` | Modify (`prices` L198-212; append `digest`) | T1/T5. |
| `tests/test_cli_prices.py` | Create | T1. |
| `src/gaffer/watchlist.py` | Create | T2: the starred-player store. |
| `tests/test_watchlist.py` | Create | T2. |
| `src/gaffer/web/routers/watchlist.py` | Create | T2: `GET/POST/DELETE /api/watchlist`. |
| `tests/test_web_watchlist.py` | Create | T2. |
| `src/gaffer/web/schemas.py` | Modify (append) | T2/T3/T4/T6. |
| `src/gaffer/web/app.py` | Modify (L26-29 imports, L67-88 includes) | T2/T3/T7. |
| `frontend/src/hubs/Players.tsx` | Modify (L19-45, L126-139) | T2: the star column. |
| `frontend/src/hubs/Players.test.tsx` | Modify | T2. |
| `src/gaffer/web/routers/prices.py` | Create | T3: `GET /api/prices/movers`. |
| `tests/test_web_prices.py` | Create | T3. |
| `src/gaffer/digest.py` | Create | T4: both digests, the notifier, the store. |
| `tests/test_digest.py` | Create | T4. |
| `src/gaffer/config.py` | Modify (L100-107 field, L176-178 loader) | T5: `[digest] notify`. |
| `src/gaffer/web/job_kinds.py` | Modify (append + L154-165) | T5: two kinds. |
| `tests/test_web_job_kinds_v8f.py` | Create | T5. |
| `scripts/com.gaffer.digest-friday.plist` | Create | T5. |
| `scripts/com.gaffer.digest-tuesday.plist` | Create | T5. |
| `scripts/install_automation.sh` | Modify (L5, L13) | T5. |
| `tests/test_web_job_kinds.py` | Modify (L24-28) | T5: the sorted-list pin. |
| `tests/test_web_job_kinds_v8b.py` | Modify (L16) | T5: the count pin. |
| `tests/test_web_job_kinds_v8c.py` | Modify (L19-27) | T5: the sorted-list pin. |
| `frontend/src/types.ts` | Modify (L556-573, L625-642, append) | T5/T6/T7. |
| `src/gaffer/artifacts.py` | Modify (`save_components` L106-111, append `ep_movers`) | T6. |
| `tests/test_ep_movers.py` | Create | T6. |
| `src/gaffer/web/routers/advice.py` | Modify (L122-155) | T6: `ep_movers` on the diff. |
| `tests/test_web_advice_movers.py` | Create | T6. |
| `frontend/src/hubs/this-week/WhyPanel.tsx` | Modify (L10-48, L154) | T6: the DiffStrip line. |
| `frontend/src/hubs/this-week/WhyPanel.test.tsx` | Modify | T6. |
| `src/gaffer/web/routers/digest.py` | Create | T7: `GET /api/digest`. |
| `tests/test_web_digest.py` | Create | T7. |
| `frontend/src/hubs/this-week/DigestCard.tsx` | Create | T7. |
| `frontend/src/hubs/this-week/DigestCard.test.tsx` | Create | T7. |
| `frontend/src/hubs/ThisWeek.tsx` | Modify (L11-17 imports, L231-234) | T7. |
| `tests/test_v8f_degradation.py` | Create | T8: G2. |
| `README.md` | Modify | T9. |

---

## Task 1 — the price log, and the nightly job that fills it

**Files:**
- Create `src/gaffer/price_log.py`
- Create `tests/test_price_log.py`
- Modify `src/gaffer/cli.py` (`prices`, L198-212)
- Create `tests/test_cli_prices.py`

- [ ] **Write the failing test.** Create `tests/test_price_log.py`:

```python
"""The daily price bank: what FPL's own predictor said, kept.

``gaffer prices`` has always printed tonight's likely changes and forgotten
them, which makes the one question worth asking unanswerable — "what was the
predictor saying about him three days before he rose?". These tests are the
snapshot log's tests asked about a different frame: the same idempotency key,
the same append-by-rewrite, the same atomic replace, and the same absolute
refusal to raise on a scheduled job's behalf.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.data import store
from gaffer.price_log import (PRICE_LOG_COLS, PRICE_LOG_PATH, append_prices,
                              bank_prices, load_price_log, price_rows)

PLAYERS = pd.DataFrame({
    "code": [11, 22, 33, 44],
    "name": ["Saka", "Haaland", "Rice", "Locked"],
    "now_cost": [101, 150, 65, 45],
    "price_change_percent": [98.5, -100.0, 0.0, float("nan")],
    "price_change_calibrating": [False, False, True, False],
})


@pytest.fixture(autouse=True)
def _tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    (tmp_path / "data" / "live").mkdir(parents=True)


def test_every_player_is_banked_not_only_the_alerts():
    """The whole reason to bank rather than print: the interesting row is the
    one that was *not* an alert on the day it was written."""
    rows = price_rows(PLAYERS, day="2026-08-31")
    assert len(rows) == 4
    assert list(rows.columns) == PRICE_LOG_COLS


def test_the_direction_is_three_valued_here_and_null_is_not_flat():
    """A1: ``flat`` is a reading, null is the absence of one, and collapsing
    them would hide "the predictor published nothing about him"."""
    rows = price_rows(PLAYERS, day="2026-08-31").set_index("code")
    assert rows.loc[11, "direction"] == "rise"
    assert rows.loc[22, "direction"] == "drop"
    assert rows.loc[33, "direction"] == "flat"
    assert pd.isna(rows.loc[44, "direction"])
    assert pd.isna(rows.loc[44, "price_change_percent"])


def test_the_calibrating_flag_rides_along():
    rows = price_rows(PLAYERS, day="2026-08-31").set_index("code")
    assert bool(rows.loc[33, "calibrating"]) is True
    assert bool(rows.loc[11, "calibrating"]) is False


def test_a_missing_calibrating_column_is_false_not_a_crash():
    """The bootstrap gained the field mid-season once already; a frame from an
    older cache must bank as "not calibrating" rather than fail the job."""
    rows = price_rows(PLAYERS.drop(columns=["price_change_calibrating"]),
                      day="2026-08-31")
    assert not rows["calibrating"].any()


def test_re_running_the_same_day_replaces_rather_than_accumulates():
    append_prices(price_rows(PLAYERS, day="2026-08-31"))
    append_prices(price_rows(PLAYERS, day="2026-08-31"))
    assert len(load_price_log()) == 4


def test_a_second_day_is_kept_beside_the_first():
    append_prices(price_rows(PLAYERS, day="2026-08-30"))
    append_prices(price_rows(PLAYERS, day="2026-08-31"))
    log = load_price_log()
    assert len(log) == 8
    assert set(log["snap_date"]) == {"2026-08-30", "2026-08-31"}


def test_the_two_days_share_one_dtype_per_column():
    """A quiet day and a busy one must not write two incompatible schemas
    into one growing file — the trade ``snapshot_rows`` makes."""
    quiet = PLAYERS.assign(price_change_percent=float("nan"))
    append_prices(price_rows(quiet, day="2026-08-30"))
    append_prices(price_rows(PLAYERS, day="2026-08-31"))
    log = load_price_log()
    assert str(log["price_change_percent"].dtype) == "float64"
    assert str(log["code"].dtype) == "int64"


def test_the_rewrite_leaves_no_temp_file_behind():
    append_prices(price_rows(PLAYERS, day="2026-08-31"))
    assert not (store.DATA_DIR / (PRICE_LOG_PATH + ".tmp")).exists()


def test_an_empty_log_reads_as_the_right_shape():
    assert list(load_price_log().columns) == PRICE_LOG_COLS
    assert load_price_log().empty


def test_banking_answers_the_row_count():
    assert bank_prices(PLAYERS, day="2026-08-31") == 4


def test_an_unwritable_store_costs_the_day_and_nothing_else(monkeypatch,
                                                            capsys):
    """The nightly job's contract. ``prices`` still printed its alerts before
    this ran (A2), so a failure here must be a printed line, not an
    exception."""
    def boom(*_args, **_kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr("gaffer.price_log.append_prices", boom)
    assert bank_prices(PLAYERS, day="2026-08-31") is None
    assert "price log not written" in capsys.readouterr().out


@pytest.mark.parametrize("frame", [None, pd.DataFrame(),
                                   pd.DataFrame({"code": [1]})])
def test_an_unusable_frame_banks_nothing(frame, capsys):
    assert bank_prices(frame, day="2026-08-31") is None
    assert "price log not written" in capsys.readouterr().out


def test_the_day_comes_from_the_snapshot_logs_own_clock():
    """One definition of "today" across both daily logs, or the two drift
    apart in exactly the week somebody wants to join them."""
    import gaffer.price_log as pl
    import gaffer.snapshot as snap

    assert pl.snap_date is snap.snap_date


def test_banking_with_no_day_stamps_today(monkeypatch):
    monkeypatch.setattr("gaffer.price_log.snap_date", lambda: "2026-12-25")
    bank_prices(PLAYERS)
    assert set(load_price_log()["snap_date"]) == {"2026-12-25"}
```

Run it: `uv run pytest -q tests/test_price_log.py` — expect `ModuleNotFoundError`.

- [ ] **Implement.** Create `src/gaffer/price_log.py`:

```python
"""The daily price bank: FPL's own predictor, kept instead of printed.

``gaffer prices`` has been stateless since it was written — it reads
``price_change_percent`` out of the bootstrap, prints whoever is near a
threshold, and forgets. That is enough to answer "who moves tonight" and
nothing else, and the questions worth asking are all the other ones: how long
does a player sit at ninety before he rises, does the predictor lead or lag
the transfer counts, and is a rise on a Tuesday worth planning around. None of
them are answerable from a file that only kept the alerts, so this log keeps
**every** player's reading, every day.

It is the availability log's twin and shares its every mechanic on purpose:
one row per player per UTC day, ``snap_date`` as the idempotency key,
append-by-rewrite because parquet has no append, and an ``os.replace`` at the
end so a job killed mid-write costs the day rather than the season. Even the
clock is shared — :func:`gaffer.snapshot.snap_date` is imported rather than
restated, because two definitions of "today" in one project is a bug waiting
for the week somebody joins the two logs.

Nothing here is a trained feature. The log is being accrued now so that a
future cycle has a season of it to justify a price-timing term with; today it
is banked and read by nobody, which is the correct order to do that in.

Nothing here may raise. The caller is a launchd job at 23:15 with nowhere to
report a traceback, and it has already printed the output the user actually
asked for by the time this runs.
"""

from __future__ import annotations

import os

import pandas as pd

from gaffer.data import store
from gaffer.snapshot import snap_date

PRICE_LOG_PATH = "live/price_log.parquet"

PRICE_LOG_COLS = ["snap_date", "code", "now_cost", "price_change_percent",
                  "direction", "calibrating"]
"""Six columns, and deliberately no ``name``.

A code is a stable join key and a web name is not: banking a display name
every day for a season stores nothing but the day FPL decided to spell it
differently. Names come from ``data/live/players.parquet`` at read time.
"""

_REQUIRED = {"code", "now_cost", "price_change_percent"}


def _direction(pct: pd.Series) -> pd.Series:
    """``rise`` / ``drop`` / ``flat``, and null where nothing was published.

    Three-valued where :func:`gaffer.prices.price_alerts` is two-valued,
    because that function only ever sees rows past a threshold and this one
    sees the whole league. The null matters most: a locked player, or one FPL
    has not started predicting for, is not a player the predictor said would
    hold his price.
    """
    out = pd.Series(pd.NA, index=pct.index, dtype="object")
    out[pct > 0] = "rise"
    out[pct < 0] = "drop"
    out[pct == 0] = "flat"
    return out.astype("string")


def price_rows(players: pd.DataFrame, day: str | None = None) -> pd.DataFrame:
    """The bootstrap's price fields -> dated log rows, one per player.

    Dtypes are forced rather than inferred, the trade
    :func:`gaffer.snapshot.snapshot_rows` makes: parquet wants one dtype per
    column, and a pre-season day on which nobody has a published prediction
    would otherwise write an all-null object column into a file whose other
    days are floats.
    """
    if players is None or not isinstance(players, pd.DataFrame):
        raise ValueError("no player frame to bank")
    if not _REQUIRED.issubset(players.columns):
        missing = sorted(_REQUIRED - set(players.columns))
        raise ValueError(f"player frame is missing {', '.join(missing)}")
    if players.empty:
        raise ValueError("player frame is empty")

    pct = pd.to_numeric(players["price_change_percent"], errors="coerce")
    calibrating = players.get("price_change_calibrating")
    if calibrating is None:
        # The bootstrap gained this field mid-season once already. An older
        # cache banks as "not calibrating", which is what it means.
        calibrating = pd.Series(False, index=players.index)
    out = pd.DataFrame({
        "snap_date": str(day or snap_date()),
        "code": pd.to_numeric(players["code"],
                              errors="coerce").astype("int64"),
        "now_cost": pd.to_numeric(players["now_cost"],
                                  errors="coerce").astype("Int64"),
        "price_change_percent": pct.astype("float64"),
        "direction": _direction(pct),
        "calibrating": pd.Series(calibrating, index=players.index).fillna(
            False).astype(bool),
    })
    return out[PRICE_LOG_COLS].reset_index(drop=True)


def append_prices(rows: pd.DataFrame) -> int:
    """Rewrite the log with ``rows`` replacing anything from the same day.

    :func:`gaffer.snapshot.append_snapshot`'s body, for the same reasons in
    the same order: parquet has no append and a few hundred rows a day is
    cheap to re-emit; replacement keyed on ``snap_date`` is what makes a hand
    re-run free; and the temp-file-plus-``os.replace`` is what stops a job
    killed mid-parquet from costing every day already banked.

    ``store.DATA_DIR`` is read here rather than bound at import so a test that
    redirects it redirects both paths together.
    """
    existing = (store.load(PRICE_LOG_PATH) if store.exists(PRICE_LOG_PATH)
                else pd.DataFrame(columns=PRICE_LOG_COLS))
    for col in PRICE_LOG_COLS:
        if col not in existing.columns:
            existing[col] = None
    days = set(rows["snap_date"].astype(str))
    kept = existing[~existing["snap_date"].astype(str).isin(days)]
    frames = [f[PRICE_LOG_COLS] for f in (kept, rows) if not f.empty]
    merged = (pd.concat(frames, ignore_index=True) if frames
              else rows[PRICE_LOG_COLS])
    tmp_rel = PRICE_LOG_PATH + ".tmp"
    tmp = store.DATA_DIR / tmp_rel
    try:
        store.save(merged, tmp_rel)
        os.replace(tmp, store.DATA_DIR / PRICE_LOG_PATH)
    finally:
        tmp.unlink(missing_ok=True)
    return int(len(rows))


def load_price_log() -> pd.DataFrame:
    """Every banked day, or an empty frame with the right columns."""
    if not store.exists(PRICE_LOG_PATH):
        return pd.DataFrame(columns=PRICE_LOG_COLS)
    return store.load(PRICE_LOG_PATH)


def bank_prices(players: pd.DataFrame | None,
                day: str | None = None) -> int | None:
    """Bank today's predictor readings. Rows written, or ``None``.

    Every failure lands in the one ``except`` and becomes a printed line. This
    is instrumentation running after the command has already printed what the
    user asked for, and instrumentation never blocks: a read-only disk on one
    Tuesday night should cost that Tuesday's row and absolutely nothing else.
    """
    try:
        rows = price_rows(players, day=day)
        n = append_prices(rows)
        print(f"Banked {n} price readings for "
              f"{rows['snap_date'].iloc[0]} to {PRICE_LOG_PATH}.")
        return n
    except Exception as exc:  # noqa: BLE001 — a scheduled job never blocks
        print(f"price log not written: {exc}")
        return None
```

- [ ] **Write the CLI test.** Create `tests/test_cli_prices.py`:

```python
"""``gaffer prices``: the stdout contract, and the bank bolted beside it.

D1c pins the printed output, so the interesting assertions are all about what
must *not* change — and about the ordering that guarantees it. The banking
runs after the alerts are printed, so a broken bank is a line of apology under
a complete alert list rather than a missing alert list.
"""

from __future__ import annotations

import pandas as pd
import pytest
from typer.testing import CliRunner

from gaffer.cli import app

RUNNER = CliRunner()

BOOTSTRAP = {"elements": [], "teams": [], "events": []}

PLAYERS = pd.DataFrame({
    "code": [11, 22],
    "name": ["Saka", "Rice"],
    "position": ["MID", "MID"],
    "now_cost": [101, 65],
    "selected_by_percent": [40.0, 12.0],
    "price_change_percent": [98.5, 3.0],
    "price_change_calibrating": [False, False],
})


@pytest.fixture()
def wired(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("gaffer.api.client.FPLClient.get_bootstrap",
                        lambda self: BOOTSTRAP)
    monkeypatch.setattr("gaffer.data.bootstrap.build_players",
                        lambda raw: PLAYERS)
    return tmp_path


def test_the_printed_contract_is_unchanged(wired):
    result = RUNNER.invoke(app, ["prices"])
    assert result.exit_code == 0
    assert "Saka: rise (98.5%)" in result.stdout
    assert "Rice" not in result.stdout          # below the 90 threshold


def test_the_run_banks_every_player_not_only_the_alert(wired):
    from gaffer.price_log import load_price_log

    assert RUNNER.invoke(app, ["prices"]).exit_code == 0
    log = load_price_log()
    assert sorted(log["code"]) == [11, 22]
    assert "Banked 2 price readings" in RUNNER.invoke(app,
                                                     ["prices"]).stdout


def test_a_second_run_the_same_day_does_not_duplicate(wired):
    from gaffer.price_log import load_price_log

    RUNNER.invoke(app, ["prices"])
    RUNNER.invoke(app, ["prices"])
    assert len(load_price_log()) == 2


def test_a_failing_bank_still_prints_the_alerts(wired, monkeypatch):
    """A2's ordering, asserted: the user's answer comes first."""
    monkeypatch.setattr("gaffer.price_log.append_prices",
                        lambda rows: (_ for _ in ()).throw(
                            OSError("read-only file system")))
    result = RUNNER.invoke(app, ["prices"])
    assert result.exit_code == 0
    assert "Saka: rise (98.5%)" in result.stdout
    assert "price log not written" in result.stdout


def test_a_dead_api_is_still_not_a_traceback(wired, monkeypatch):
    def boom(self):
        raise RuntimeError("connection refused")

    monkeypatch.setattr("gaffer.api.client.FPLClient.get_bootstrap", boom)
    result = RUNNER.invoke(app, ["prices"])
    assert result.exit_code == 0
    assert "price check failed" in result.stdout
```

- [ ] **Rewrite the command.** In `src/gaffer/cli.py`, replace the whole `prices` command (L198-212) with:

```python
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
```

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_price_log.py tests/test_cli_prices.py \
  tests/test_snapshot.py tests/test_prices.py
```

- [ ] **Commit.**

```bash
git add src/gaffer/price_log.py tests/test_price_log.py src/gaffer/cli.py \
  tests/test_cli_prices.py && git commit -m "$(cat <<'EOF'
feat: bank FPL's price predictor daily instead of printing and forgetting it

Every player, every UTC day, the availability log's mechanics exactly. The
printed alert list is unchanged; the bank runs after it and never blocks.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 2 — the watchlist: a store, an endpoint, and a star in the explorer

**Files:**
- Create `src/gaffer/watchlist.py`
- Create `tests/test_watchlist.py`
- Create `src/gaffer/web/routers/watchlist.py`
- Create `tests/test_web_watchlist.py`
- Modify `src/gaffer/web/schemas.py`
- Modify `src/gaffer/web/app.py`
- Modify `frontend/src/types.ts`
- Modify `frontend/src/hubs/Players.tsx`
- Modify `frontend/src/hubs/Players.test.tsx`

- [ ] **Write the failing test.** Create `tests/test_watchlist.py`:

```python
"""The starred-player store: a bookmark, and nothing more than a bookmark.

``overrides.py``'s shape with the two numbers removed, which removes most of
its tests with them — there is no range to clip, no coherence to warn about
and no model that has to obey anything. What is left is the part that still
matters on a store the availability pass and a launchd job both read: an
absent file is an empty list, a corrupt one is an empty list, a write is
atomic, and a cap exists.
"""

from __future__ import annotations

import json

import pytest

from gaffer import artifacts
from gaffer.errors import GafferError
from gaffer.watchlist import (MAX_WATCHED, NOTE_MAX, load_watchlist,
                              save_watchlist, unwatch, watch, watched_codes)


@pytest.fixture(autouse=True)
def _tmp_reports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()


def test_an_absent_store_is_an_empty_watchlist():
    assert load_watchlist() == {}
    assert watched_codes() == []


def test_a_star_round_trips_with_its_note():
    watch(11, note="rotation risk, watch the presser")
    rows = load_watchlist()
    assert list(rows) == [11]
    assert rows[11]["note"] == "rotation risk, watch the presser"
    assert rows[11]["set_at"]


def test_a_second_star_on_the_same_player_replaces_the_note():
    watch(11, note="first")
    watch(11, note="second")
    assert load_watchlist()[11]["note"] == "second"
    assert len(load_watchlist()) == 1


def test_a_star_needs_no_note_at_all():
    """A bookmark with nothing written on it is still a bookmark — the whole
    difference between this store and the override store."""
    watch(11)
    assert load_watchlist()[11]["note"] == ""


def test_codes_come_back_sorted_and_as_integers():
    """JSON object keys are strings by definition; this is where they stop
    being strings, so a caller looking one up with an int cannot miss."""
    for code in (33, 11, 22):
        watch(code)
    assert watched_codes() == [11, 22, 33]


def test_unwatching_removes_one_and_reports_whether_it_did():
    watch(11)
    assert unwatch(11) is True
    assert unwatch(11) is False
    assert load_watchlist() == {}


def test_an_unknown_code_is_refused_when_a_universe_is_given():
    with pytest.raises(GafferError, match="not in the current player list"):
        watch(999, known_codes=[11, 22])


def test_the_universe_check_is_skipped_when_there_is_no_universe():
    watch(999)
    assert watched_codes() == [999]


def test_a_long_note_is_refused_rather_than_truncated():
    """A silently halved note is a sentence the user did not write."""
    with pytest.raises(GafferError, match="longer than"):
        watch(11, note="x" * (NOTE_MAX + 1))


def test_the_cap_refuses_the_hundred_and_first_but_not_a_re_star():
    for code in range(1, MAX_WATCHED + 1):
        watch(code)
    with pytest.raises(GafferError, match="is the cap"):
        watch(MAX_WATCHED + 1)
    watch(1, note="re-starring an existing one is always allowed")
    assert len(load_watchlist()) == MAX_WATCHED


def test_a_corrupt_store_reads_as_an_empty_one(capsys):
    (artifacts.REPORTS / "watchlist.json").write_text("{not json")
    assert load_watchlist() == {}
    assert "watchlist store unreadable" in capsys.readouterr().out


@pytest.mark.parametrize("payload", ['[]', '{"watchlist": []}',
                                     '{"watchlist": {"11": "nonsense"}}',
                                     '{}'])
def test_a_store_whose_shape_has_drifted_reads_as_empty_or_skips_the_row(
        payload):
    (artifacts.REPORTS / "watchlist.json").write_text(payload)
    assert load_watchlist() in ({}, {})


def test_the_write_is_atomic_and_leaves_no_temp_behind():
    watch(11)
    assert not (artifacts.REPORTS / "watchlist.json.tmp").exists()
    assert json.loads(
        (artifacts.REPORTS / "watchlist.json").read_text())["watchlist"]


def test_saving_an_empty_store_is_a_file_not_a_deletion():
    """``unwatch`` of the last star must leave a readable empty store rather
    than an absent one that a half-written file is indistinguishable from."""
    watch(11)
    unwatch(11)
    assert (artifacts.REPORTS / "watchlist.json").exists()
    assert load_watchlist() == {}


def test_saving_creates_the_reports_directory_on_a_fresh_clone(tmp_path):
    (tmp_path / "reports").rmdir()
    save_watchlist({11: {"note": "", "set_at": ""}})
    assert load_watchlist()[11]["note"] == ""
```

- [ ] **Implement.** Create `src/gaffer/watchlist.py`:

```python
"""The watchlist: players the manager is keeping an eye on.

The tool has always had an implicit watchlist — the squad, plus whoever this
week's solve wants to buy — and that is the set ``gaffer prices`` and the
advice payload's alerts have watched. It is the wrong set for the question a
manager actually asks on a Wednesday, which is about the player he is
*thinking* about and the optimizer has not recommended yet. There was nowhere
to write that player down.

This is that place, and it is deliberately the smallest thing that could be:
a code, an optional note, and a timestamp. It is :mod:`gaffer.overrides`'s
store with the two numbers taken out, and taking them out removes the entire
reason that module validates as hard as it does. An override is a claim the
model must obey. A star claims nothing — it widens the price-alert watch set
(:mod:`gaffer.web.routers.prices`) and it adds a section to the Friday digest,
and that is the complete list of things it can do.

Nothing here is read by anything that solves, trains, or scores, and nothing
here is ever a feature. A star is a bookmark.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from gaffer import artifacts
from gaffer.errors import GafferError

MAX_WATCHED = 100
"""Stars beyond which this stopped being a shortlist.

A hundred where :data:`gaffer.overrides.MAX_OVERRIDES` is fifty, and the
difference is the point. Fifty pins is a second model; a hundred bookmarks is
two squads' worth of candidates, which is what a manager comparing options
across a wildcard actually has open.
"""

NOTE_MAX = 200
"""Characters. Refused rather than truncated, for ``overrides.py``'s reason: a
silently halved note is a sentence the user did not write."""


def watchlist_path() -> Path:
    """``reports/watchlist.json``, resolved at call time.

    ``artifacts.REPORTS`` is relative, so a test that changes directory
    changes this with it — the trade every other report store makes.
    """
    return artifacts.REPORTS / "watchlist.json"


def load_watchlist() -> dict[int, dict]:
    """``{code: {note, set_at}}``. Never raises.

    An absent file, a hand-edited one, a half-written one and a file whose
    top-level shape has drifted all come back as ``{}``. The print is what
    makes the difference between "nothing is starred" and "the store is
    broken" visible, because a silently empty watchlist is a card that looks
    like it is working.
    """
    path = watchlist_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
        rows = raw.get("watchlist") if isinstance(raw, dict) else None
        if not isinstance(rows, dict):
            return {}
        out: dict[int, dict] = {}
        for code, row in rows.items():
            if not isinstance(row, dict):
                continue
            out[int(code)] = {"note": str(row.get("note") or ""),
                              "set_at": str(row.get("set_at") or "")}
        return out
    except Exception as exc:  # noqa: BLE001 — a bad store is an empty one
        print(f"watchlist store unreadable, ignoring it: {exc}")
        return {}


def save_watchlist(rows: dict[int, dict]) -> Path:
    """Write the whole store through a temp file and ``os.replace``.

    ``overrides.save_overrides``'s idiom. An empty store is written as an
    empty object rather than deleted: a reader cannot tell an absent file from
    a half-written one, and unstarring the last player should not put the
    store into the state a crash would.
    """
    payload = {"watchlist": {str(code): dict(row)
                             for code, row in sorted(rows.items())}}
    artifacts.REPORTS.mkdir(parents=True, exist_ok=True)
    path = watchlist_path()
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=1, allow_nan=False))
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def watched_codes() -> list[int]:
    """Every starred code, ascending. The one thing most callers want."""
    return sorted(load_watchlist())


def watch(code: int, *, note: str = "", known_codes=None) -> dict:
    """Star ``code``. Re-starring replaces the note and the timestamp.

    ``known_codes`` is the universe the star has to belong to, supplied by the
    caller so this module needs no data layer; omitting it skips the check,
    which is for tests and for callers that have already validated.

    The cap is checked only for a code that is not already starred, so a user
    at exactly the cap can still edit every note he has.
    """
    code = int(code)
    if known_codes is not None and code not in {int(c) for c in known_codes}:
        raise GafferError(
            f"player {code} is not in the current player list — star a code "
            f"the tool knows about")
    if len(str(note or "")) > NOTE_MAX:
        raise GafferError(f"note is longer than {NOTE_MAX} characters")
    rows = load_watchlist()
    if code not in rows and len(rows) >= MAX_WATCHED:
        raise GafferError(
            f"{MAX_WATCHED} starred players is the cap — unstar one first")
    row = {"note": str(note or ""),
           "set_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    rows[code] = row
    save_watchlist(rows)
    return row


def unwatch(code: int) -> bool:
    """Remove one star. ``False`` when there was nothing to remove."""
    rows = load_watchlist()
    if int(code) not in rows:
        return False
    rows.pop(int(code))
    save_watchlist(rows)
    return True


def watch_targets() -> dict[int, str]:
    """``{code: source}`` over squad, plan and watchlist, in that order.

    Everyone the manager is watching, explicit and implicit. The stars are
    this module's own store; the squad and the plan are read off the newest
    banked solve state and advice payload, which is why the imports are local
    — a module the CLI touches to print ``--help`` should not pull in the
    artifact layer, and neither should the store's own tests.

    A resolution order rather than a set union, so every row can say *why* it
    is there. A starred player who is also in the squad reads as ``squad``:
    the strongest reason is the true one, and "you own him" is a better answer
    to "why am I being told about this?" than "you bookmarked him".

    Never raises, and every read degrades on its own. A clone that has never
    solved has no squad and no plan and still has its stars; a clone with a
    solve state but no advice file has a squad and no plan. Two callers share
    it — the movers endpoint and the Friday digest — and two copies of this
    would be two different answers to "who am I watching?".
    """
    from gaffer.artifacts import latest_gw, load_advice, load_solve_state

    out: dict[int, str] = {}
    gw = None
    try:
        gw = latest_gw()
    except Exception as exc:  # noqa: BLE001 — a watch set is never fatal
        print(f"watch set: no advice on disk ({exc})")
    if gw is not None:
        try:
            for code in load_solve_state(int(gw)).owned_codes:
                out.setdefault(int(code), "squad")
        except Exception as exc:  # noqa: BLE001
            print(f"watch set: no solve state for GW{gw} ({exc})")
        try:
            advice = load_advice(int(gw))
            for key in ("buys", "sells"):
                for player in advice.get(key) or []:
                    code = (player or {}).get("code")
                    if code is not None:
                        out.setdefault(int(code), "plan")
        except Exception as exc:  # noqa: BLE001
            print(f"watch set: no advice payload for GW{gw} ({exc})")
    for code in watched_codes():
        out.setdefault(int(code), "watchlist")
    return out
```

Add its tests to `tests/test_watchlist.py`:

```python
def test_the_watch_target_of_a_bare_clone_is_the_stars_alone():
    """No solve state, no advice payload — and a star is still a star."""
    watch(11)
    assert watch_targets() == {11: "watchlist"}


def test_the_watch_target_is_empty_when_nothing_is_watched_at_all():
    assert watch_targets() == {}
```

(extend the import at the top of the file with `watch_targets`.)

- [ ] **Add the schemas.** Append to `src/gaffer/web/schemas.py`:

```python
class WatchRequest(BaseModel):
    """A star, and optionally a sentence about why."""

    code: int
    note: str = ""


class WatchRow(BaseModel):
    code: int
    name: str
    note: str
    set_at: str


class WatchlistPanel(BaseModel):
    """Every starred player, name-resolved.

    ``rows`` is empty on a fresh clone and on a broken store alike — the
    distinction is a printed line on the server, not a field here, because a
    client that rendered "your watchlist may be corrupt" would be showing the
    user a problem they cannot act on.
    """

    rows: list[WatchRow] = Field(default_factory=list)
```

- [ ] **Write the endpoint test.** Create `tests/test_web_watchlist.py`:

```python
"""``/api/watchlist``: three verbs over a store that must never 500.

The write path is the ``/api/overrides`` write path with its numeric
validation removed, so the tests that remain are the ones about the parts that
did not go away: the unknown code, the cap, the note length, and a delete of
something that was never there.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.web.app import create_app

PLAYERS = pd.DataFrame({
    "code": [11, 22, 33],
    "name": ["Saka", "Haaland", "Rice"],
    "position": ["MID", "FWD", "MID"],
    "team_code": [3, 4, 3],
    "now_cost": [101, 150, 65],
})


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    return TestClient(create_app())


def test_an_empty_watchlist_is_a_200_with_no_rows(client):
    assert client.get("/api/watchlist").json() == {"rows": []}


def test_starring_answers_the_whole_panel_name_resolved(client):
    body = client.post("/api/watchlist",
                       json={"code": 11, "note": "presser"}).json()
    assert body["rows"] == [{"code": 11, "name": "Saka", "note": "presser",
                             "set_at": body["rows"][0]["set_at"]}]


def test_the_rows_come_back_sorted_by_code(client):
    for code in (33, 11, 22):
        client.post("/api/watchlist", json={"code": code})
    assert [r["code"] for r in client.get("/api/watchlist").json()["rows"]] \
        == [11, 22, 33]


def test_an_unknown_player_is_a_structured_422(client):
    response = client.post("/api/watchlist", json={"code": 999})
    assert response.status_code == 422
    assert response.json()["detail"]["constraint"] == "unknown_player"
    assert response.json()["detail"]["players"] == [999]


def test_a_clone_with_no_player_snapshot_says_what_to_run(client, tmp_path):
    (tmp_path / "data/live/players.parquet").unlink()
    response = client.post("/api/watchlist", json={"code": 11})
    assert response.status_code == 422
    assert response.json()["detail"]["constraint"] == "no_player_list"
    assert "gaffer advise" in response.json()["detail"]["error"]


def test_reading_still_works_with_no_player_snapshot(client, tmp_path):
    """A read is never worth a 500: a panel with a code where a name should
    be is worth more than an error page."""
    client.post("/api/watchlist", json={"code": 11})
    (tmp_path / "data/live/players.parquet").unlink()
    body = client.get("/api/watchlist").json()
    assert body["rows"][0]["name"] == "11"


def test_a_long_note_is_a_422_naming_the_limit(client):
    response = client.post("/api/watchlist",
                           json={"code": 11, "note": "x" * 500})
    assert response.status_code == 422
    assert response.json()["detail"]["constraint"] == "watch_value"


def test_unstarring_answers_the_remaining_panel(client):
    client.post("/api/watchlist", json={"code": 11})
    client.post("/api/watchlist", json={"code": 22})
    assert [r["code"] for r in
            client.delete("/api/watchlist/11").json()["rows"]] == [22]


def test_unstarring_something_that_was_never_starred_is_a_404(client):
    assert client.delete("/api/watchlist/11").status_code == 404


def test_a_corrupt_store_reads_as_an_empty_panel(client, tmp_path):
    (tmp_path / "reports/watchlist.json").write_text("{not json")
    assert client.get("/api/watchlist").json() == {"rows": []}
```

- [ ] **Implement the router.** Create `src/gaffer/web/routers/watchlist.py`:

```python
"""GET/POST/DELETE ``/api/watchlist`` — the players the manager is watching.

``routers/overrides.py``'s shape, minus everything that made that endpoint
validate hard: there are no numbers here for a model to obey, so there is
nothing to clip, nothing to warn about and nothing to compare against what the
pipeline thought. What survives is the structure — reads never fail, writes
fail in the what-if lab's ``{constraint, error, players}`` shape so the client
can render the reason beside the field that caused it.

The store itself is :mod:`gaffer.watchlist`; nothing here does arithmetic.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from gaffer.artifacts import load_snapshot
from gaffer.errors import GafferError
from gaffer.watchlist import load_watchlist, unwatch, watch
from gaffer.web.schemas import WatchlistPanel, WatchRequest, WatchRow

router = APIRouter(prefix="/api", tags=["watchlist"])


def _fail(constraint: str, error: str, players: list[int]) -> HTTPException:
    """The what-if lab's structured 422, reused so the UI has one shape."""
    return HTTPException(status_code=422,
                         detail={"constraint": constraint, "error": error,
                                 "players": players})


def names() -> dict[int, str]:
    """``{code: name}`` from the bootstrap snapshot, or ``{}``.

    Exported rather than private: the movers endpoint and the digest both need
    exactly this map off exactly this file, and three copies of a four-line
    read is how three different failure modes get invented.
    """
    try:
        players = load_snapshot("live/players.parquet")
        return {int(r.code): str(r.name) for r in players.itertuples()}
    except Exception as exc:  # noqa: BLE001 — a read is never worth a 500
        print(f"watchlist panel: player snapshot unreadable ({exc})")
        return {}


def _panel() -> WatchlistPanel:
    resolved = names()
    return WatchlistPanel(rows=[
        WatchRow(code=code, name=resolved.get(code, str(code)),
                 note=str(row.get("note") or ""),
                 set_at=str(row.get("set_at") or ""))
        for code, row in sorted(load_watchlist().items())])


@router.get("/watchlist", response_model=WatchlistPanel)
def watchlist() -> WatchlistPanel:
    return _panel()


@router.post("/watchlist", response_model=WatchlistPanel)
def star(req: WatchRequest) -> WatchlistPanel:
    known = names()
    if not known:
        raise _fail("no_player_list",
                    "no player snapshot on disk — run `gaffer advise` before "
                    "starring anyone", [int(req.code)])
    if int(req.code) not in known:
        raise _fail("unknown_player",
                    f"player {req.code} is not in the current player list",
                    [int(req.code)])
    try:
        watch(int(req.code), note=req.note, known_codes=list(known))
    except GafferError as exc:
        raise _fail("watch_value", str(exc), [int(req.code)]) from exc
    return _panel()


@router.delete("/watchlist/{code}", response_model=WatchlistPanel)
def unstar(code: int) -> WatchlistPanel:
    if not unwatch(int(code)):
        raise HTTPException(status_code=404,
                            detail=f"player {code} is not starred")
    return _panel()
```

- [ ] **Register it.** In `src/gaffer/web/app.py`, extend the router import (L26-29) so the tuple reads `... sensitivity, watchlist, whatif)`, and add after the `sensitivity` include (L86):

```python
    app.include_router(watchlist.router)
```

- [ ] **Add the frontend types.** In `frontend/src/types.ts`, append:

```ts
export interface WatchRow {
  code: number
  name: string
  note: string
  set_at: string
}

export interface WatchlistPanel {
  rows: WatchRow[]
}
```

- [ ] **Write the frontend test.** Add to `frontend/src/hubs/Players.test.tsx` (keep every existing test):

```tsx
describe('the watchlist star', () => {
  it('reads the standing stars once and marks their rows', async () => {
    // The pinned-codes idiom: one read on mount, then kept current from the
    // endpoint's own answer, so the table says which rows are starred without
    // a round trip per row.
    render(<Players />)
    expect(await screen.findByLabelText('unstar Saka')).toBeInTheDocument()
    expect(screen.getByLabelText('star Haaland')).toBeInTheDocument()
  })

  it('stars a player and flips the button without refetching the table',
     async () => {
    render(<Players />)
    fireEvent.click(await screen.findByLabelText('star Haaland'))
    expect(await screen.findByLabelText('unstar Haaland')).toBeInTheDocument()
  })

  it('unstars a starred player', async () => {
    render(<Players />)
    fireEvent.click(await screen.findByLabelText('unstar Saka'))
    expect(await screen.findByLabelText('star Saka')).toBeInTheDocument()
  })

  it('leaves the explorer usable when the watchlist endpoint is down',
     async () => {
    // The whole hub must render on a clone whose reports/ directory is empty.
    server.use(http.get('/api/watchlist', () => HttpResponse.error()))
    render(<Players />)
    expect(await screen.findByText('Saka')).toBeInTheDocument()
    expect(screen.getByLabelText('star Saka')).toBeInTheDocument()
  })
})
```

Wire the MSW handlers this file already uses with `/api/watchlist` returning `{ rows: [{ code: 11, name: 'Saka', note: '', set_at: '' }] }` for GET, and echoing an updated panel for POST/DELETE.

- [ ] **Implement the star column.** In `frontend/src/hubs/Players.tsx`, add to the type import (L9) `WatchlistPanel`, and beside the `pinned` state (L35):

```tsx
  // Starred codes. Read once on mount and then kept current from each write's
  // own answer, exactly as `pinned` is: the alternative is a GET per star, on
  // a table of six hundred rows.
  const [starred, setStarred] = useState<number[]>([])
```

after the overrides effect (L45):

```tsx
  useEffect(() => {
    apiGet<WatchlistPanel>('/api/watchlist')
      .then((panel) => setStarred(panel.rows.map((r) => r.code)))
      .catch(() => setStarred([]))
  }, [])

  // A star is a bookmark, so a failed write is silence rather than an error
  // state: the button simply does not flip, and the explorer is untouched.
  const toggleStar = (code: number) => {
    const on = starred.includes(code)
    const request = on
      ? apiDelete<WatchlistPanel>(`/api/watchlist/${code}`)
      : apiPost<WatchlistPanel>('/api/watchlist', { code, note: '' })
    request.then((panel) => setStarred(panel.rows.map((r) => r.code)))
      .catch(() => {})
  }
```

and a column immediately before the `pin` column (L125), so the two live together at the end of the row:

```tsx
    {
      key: 'star', header: '', value: () => '',
      render: (r) => (
        <button
          type="button"
          aria-label={`${starred.includes(r.code) ? 'unstar' : 'star'} `
            + `${r.name}`}
          onClick={() => toggleStar(r.code)}
          className="px-1 text-text-muted hover:text-text"
        >
          {starred.includes(r.code) ? '★' : '☆'}
        </button>
      ),
    },
```

Extend the `apiGet` import on L3 to `import { apiDelete, apiGet, apiPost } from '../api/client'`. All three already exist (`frontend/src/api/client.ts:44`, `:48`, `:56`) — this cycle adds no client helper.

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_watchlist.py tests/test_web_watchlist.py \
  tests/test_web_overrides.py
cd frontend && npx tsc --noEmit && npx vitest run src/hubs/Players.test.tsx
```

- [ ] **Commit.**

```bash
git add src/gaffer/watchlist.py tests/test_watchlist.py \
  src/gaffer/web/routers/watchlist.py tests/test_web_watchlist.py \
  src/gaffer/web/schemas.py src/gaffer/web/app.py frontend/src/types.ts \
  frontend/src/hubs/Players.tsx \
  frontend/src/hubs/Players.test.tsx && git commit -m "$(cat <<'EOF'
feat: a watchlist — star a player the optimizer has not recommended

The override store's shape with the numbers taken out, which takes the
validation out with them: a star claims nothing, so nothing has to obey it.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 3 — tonight's movers, server-side, over the wider watch set

**Files:**
- Create `src/gaffer/web/routers/prices.py`
- Create `tests/test_web_prices.py`
- Modify `src/gaffer/web/schemas.py`
- Modify `src/gaffer/web/app.py`
- Modify `frontend/src/types.ts`

- [ ] **Write the failing test.** Create `tests/test_web_prices.py`:

```python
"""``/api/prices/movers``: the alert list the advice payload cannot carry.

``advise.py`` is protected, so the payload's watch set is frozen at
squad-plus-plan and cannot learn about the watchlist. This endpoint is where
the wider set lives, and the tests are mostly about the two properties that
buys: it never reaches the network, and it never lies about how old its
reading is.
"""

from __future__ import annotations

import json
import os

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import SolveState, save_solve_state
from gaffer.web.app import create_app

GW = 5

PLAYERS = pd.DataFrame({
    "code": [11, 22, 33, 44, 55],
    "name": ["Saka", "Haaland", "Rice", "Starred", "Nobody"],
    "position": ["MID", "FWD", "MID", "DEF", "GKP"],
    "team_code": [3, 4, 3, 5, 6],
    "now_cost": [101, 150, 65, 45, 40],
    "price_change_percent": [98.5, -100.0, 12.0, 95.0, 99.9],
    "price_change_calibrating": [False, False, False, True, False],
})

POOL = pd.DataFrame([
    {"code": 11, "name": "Saka", "position": "MID", "team_code": 3,
     "cost": 101, "sell": 101, "owned": True, "gw": GW, "ep_raw": 5.0},
])

ADVICE = {"gw": GW, "buys": [{"code": 22, "name": "Haaland"}],
          "sells": [{"code": 33, "name": "Rice"}], "hits": 0,
          "xi": [], "bench": [], "expected_pts": 60.0,
          "captain": {"code": 11, "name": "Saka"},
          "vice": {"code": 22, "name": "Haaland"}}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    (tmp_path / f"reports/gw{GW}-advice.json").write_text(json.dumps(ADVICE))
    save_solve_state(SolveState(
        gw=GW, gws=[GW], deadline="2026-09-01T11:00:00Z",
        generated_at="2026-08-31T09:00:00Z", mode="weekly", bank=0,
        free_transfers=1, owned_codes=[11], lam=0.0, league_eo={},
        avail_by_gw={GW: []},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.0, "horizon": 1, "hit_cost": 4,
             "max_transfers": 2, "bank_weight": 0.0},
        pool=POOL))
    return TestClient(create_app())


def _rows(client):
    return {r["code"]: r for r in client.get("/api/prices/movers")
            .json()["rows"]}


def test_the_squad_and_the_plan_are_watched(client):
    rows = _rows(client)
    assert rows[11]["source"] == "squad"
    assert rows[22]["source"] == "plan"


def test_a_player_in_neither_is_not_watched_however_close_he_is(client):
    """Player 55 is at 99.9% and belongs to nobody. An alert about a player
    the manager has no relationship with is noise."""
    assert 55 not in _rows(client)


def test_starring_a_player_puts_him_in_the_watch_set(client):
    assert 44 not in _rows(client)
    client.post("/api/watchlist", json={"code": 44})
    assert _rows(client)[44]["source"] == "watchlist"


def test_a_starred_squad_player_reads_as_squad(client):
    """A4's resolution order. "Why is he here?" has one answer per row, and
    the strongest reason is the true one."""
    client.post("/api/watchlist", json={"code": 11})
    assert _rows(client)[11]["source"] == "squad"


def test_below_the_threshold_is_not_a_mover(client):
    """Rice is in the plan and sitting at 12% — watched, but not moving."""
    assert 33 not in _rows(client)


def test_the_direction_and_the_calibrating_caveat_ride_the_row(client):
    client.post("/api/watchlist", json={"code": 44})
    rows = _rows(client)
    assert rows[11]["direction"] == "rise"
    assert rows[22]["direction"] == "drop"
    assert rows[44]["calibrating"] is True
    assert rows[11]["calibrating"] is False


def test_the_rows_are_sorted_by_how_close_the_change_is(client):
    codes = [r["code"] for r in client.get("/api/prices/movers")
             .json()["rows"]]
    assert codes == [22, 11]        # |-100| before |98.5|


def test_the_payload_says_how_old_its_reading_is(client, tmp_path):
    """A4: a movers strip showing Tuesday's predictor on a Friday evening is
    worse than no strip at all, so the age is a field and the card prints
    it."""
    path = tmp_path / "data/live/players.parquet"
    os.utime(path, (1_756_000_000, 1_756_000_000))
    body = client.get("/api/prices/movers").json()
    assert body["as_of"].startswith("2025-")
    assert body["available"] is True


def test_no_player_snapshot_is_an_unavailable_panel_not_a_500(client,
                                                              tmp_path):
    (tmp_path / "data/live/players.parquet").unlink()
    body = client.get("/api/prices/movers").json()
    assert body == {"available": False, "as_of": None, "rows": []}


def test_no_solve_state_still_serves_the_watchlist(client, tmp_path):
    """A clone that has never solved has no squad and no plan, but a star is
    a star."""
    client.post("/api/watchlist", json={"code": 44})
    for name in tmp_path.glob("reports/solve_state*"):
        name.unlink()
    for name in tmp_path.glob("reports/gw*-advice.json"):
        name.unlink()
    rows = _rows(client)
    assert list(rows) == [44]
    assert rows[44]["source"] == "watchlist"


def test_a_corrupt_players_snapshot_is_unavailable_not_a_500(client,
                                                             tmp_path):
    (tmp_path / "data/live/players.parquet").write_text("garbage")
    assert client.get("/api/prices/movers").json()["available"] is False


def test_the_endpoint_never_touches_the_network(client, monkeypatch):
    """A card on a page must not make an API call on a page load — least of
    all on the Thursday evening everybody is loading the page."""
    def boom(*_args, **_kwargs):
        raise AssertionError("the movers card reached the network")

    monkeypatch.setattr("gaffer.api.client.FPLClient.get_bootstrap", boom)
    assert client.get("/api/prices/movers").status_code == 200
```

- [ ] **Add the schemas.** Append to `src/gaffer/web/schemas.py`:

```python
class MoverRow(BaseModel):
    """One watched player FPL's predictor has near a threshold tonight."""

    code: int
    name: str
    now_cost: float
    """In millions, the way the UI shows a price — not the 0.1m integer the
    bootstrap carries."""
    price_change_percent: float
    direction: str
    """``rise`` or ``drop``. Never ``flat``: this list is only ever rows past
    the alert threshold, where the price log (which sees everyone) has a third
    value."""
    calibrating: bool
    """FPL is still fitting this player's price model — an early-season caveat
    the row carries rather than a reason to hide it."""
    source: str
    """``squad`` / ``plan`` / ``watchlist``, resolved in that order. The
    answer to "why is he on this list?", on the row itself."""


class MoversPanel(BaseModel):
    """Tonight's likely price changes among players the manager cares about.

    ``as_of`` is the age of the *reading*, not of the request: this is served
    off ``data/live/players.parquet`` and never off the network, so a panel
    that did not say how stale it was would be a panel claiming to know
    something about tonight when it might be quoting Tuesday.
    """

    available: bool
    as_of: str | None = None
    rows: list[MoverRow] = Field(default_factory=list)
```

- [ ] **Implement the router.** Create `src/gaffer/web/routers/prices.py`:

```python
"""``GET /api/prices/movers`` — tonight's changes among watched players.

The advice payload has carried ``price_alerts`` since v2, over a watch set of
squad-plus-plan, and it will keep carrying exactly that: ``advise.py`` is
protected and widening the set there is not a change this cycle is allowed to
make. So the wider set — squad, plan, **and** the watchlist — lives here
instead, and the two lists differ by exactly the starred players on purpose.

Two properties are worth stating because both are load-bearing.

It never touches the network. The reading comes off
``data/live/players.parquet``, the snapshot every ``refresh`` and every
``advise`` rewrites, because a card that fetched the bootstrap on a page load
would fetch it once per visitor on the one evening every visitor is looking.

It therefore says how old the reading is. ``as_of`` is that file's mtime, the
card prints it, and a panel that quietly showed Tuesday's predictor readings
on a Friday evening would be worse than showing nothing — the whole claim the
card makes is about *tonight*.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter

from gaffer.data import store
from gaffer.prices import price_alerts
from gaffer.watchlist import watch_targets
from gaffer.web.schemas import MoverRow, MoversPanel

router = APIRouter(prefix="/api/prices", tags=["prices"])

PLAYERS_PATH = "live/players.parquet"


def _snapshot() -> tuple[pd.DataFrame | None, str | None]:
    """The banked bootstrap slice and its age, or ``(None, None)``.

    An absent file and an unreadable one are the same answer: the panel is
    unavailable and the page renders without it. The mtime is read before the
    parquet so a file that exists but will not parse still cannot 500.
    """
    if not store.exists(PLAYERS_PATH):
        return None, None
    path = store.DATA_DIR / PLAYERS_PATH
    try:
        stamp = datetime.fromtimestamp(path.stat().st_mtime,
                                       tz=timezone.utc).isoformat(
                                           timespec="seconds")
    except OSError:
        stamp = None
    try:
        return store.load(PLAYERS_PATH), stamp
    except Exception as exc:  # noqa: BLE001 — a card is never worth a 500
        print(f"movers: player snapshot unreadable ({exc})")
        return None, stamp


def _cost(value) -> float:
    """The bootstrap's 0.1m integer as the millions the UI shows."""
    try:
        out = float(value) / 10.0
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(out) else round(out, 1)


@router.get("/movers", response_model=MoversPanel)
def movers() -> MoversPanel:
    players, as_of = _snapshot()
    if players is None or players.empty:
        return MoversPanel(available=False, as_of=as_of)
    sources = watch_targets()
    if not sources:
        # Not "unavailable": the snapshot is fine and nothing is watched, and
        # the card's empty state should say so rather than say it is broken.
        return MoversPanel(available=True, as_of=as_of)
    try:
        alerts = price_alerts(players, list(sources))
    except Exception as exc:  # noqa: BLE001 — a card is never worth a 500
        print(f"movers: price alerts unavailable ({exc})")
        return MoversPanel(available=False, as_of=as_of)
    cost_of = dict(zip(players["code"], players.get("now_cost", [])))
    return MoversPanel(available=True, as_of=as_of, rows=[
        MoverRow(code=int(r.code), name=str(r.name),
                 now_cost=_cost(cost_of.get(int(r.code))),
                 price_change_percent=round(float(r.price_change_percent), 1),
                 direction=str(r.direction),
                 calibrating=bool(r.calibrating),
                 source=sources.get(int(r.code), "watchlist"))
        for r in alerts.itertuples()])
```

- [ ] **Register it.** In `src/gaffer/web/app.py`, add `prices` to the router import tuple and add after the `players` include:

```python
    app.include_router(prices.router)
```

- [ ] **Add the frontend types.** In `frontend/src/types.ts`, append:

```ts
export interface MoverRow {
  code: number
  name: string
  now_cost: number
  price_change_percent: number
  /** 'rise' | 'drop' — never 'flat'; this list is alerts only. */
  direction: string
  calibrating: boolean
  /** 'squad' | 'plan' | 'watchlist' — why this row is on the list. */
  source: string
}

export interface MoversPanel {
  available: boolean
  /** When the reading was taken, not when it was fetched. */
  as_of: string | null
  rows: MoverRow[]
}
```

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_web_prices.py tests/test_prices.py \
  tests/test_web_watchlist.py
cd frontend && npx tsc --noEmit
```

- [ ] **Commit.**

```bash
git add src/gaffer/web/routers/prices.py tests/test_web_prices.py \
  src/gaffer/web/schemas.py src/gaffer/web/app.py frontend/src/types.ts \
  && git commit -m "$(cat <<'EOF'
feat: serve tonight's movers over squad + plan + watchlist

The wider watch set the advice payload cannot carry, computed server-side off
the banked bootstrap so a page load never reaches the network — and carrying
the age of its own reading, because the claim is about tonight.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 4 — the two digests, and the notification that delivers them

**Files:**
- Create `src/gaffer/digest.py`
- Create `tests/test_digest.py`

Note the seam this task deliberately does **not** cross: `run_digest` takes an explicit `notify: bool` argument and reads no config. The config key that feeds it is added in Task 5, together with the two job kinds, so that every protected pin this cycle breaks is broken at one moment rather than two (A7). A task that reaches for `serving_config()` here has re-opened a stop-point the plan closed.

- [ ] **Write the failing test.** Create `tests/test_digest.py`:

```python
"""The Friday briefing and the Tuesday debrief: seven reads, no writes.

Two rules carry almost every test in this file.

A section whose input is missing is **absent**, never present-and-empty (plan
A5). "Last week: no data" is a sentence about the tool; the absence of a
section is a sentence about the season, and only one of those is worth a card.

And the digest is a reader (A6). ``review.append_ledger`` takes a lock and is
the ledger's only writer; a Tuesday digest that re-graded a gameweek in order
to report on it would be a second writer on a locked store, run by a launchd
job, at the same hour as the review job. So there is a test that asserts the
module contains no writer at all beyond its own artifact.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from gaffer import artifacts
from gaffer.digest import (DIGEST_KINDS, friday_briefing, load_digest,
                           run_digest, save_digest, tuesday_debrief)

GW = 5

EVENTS = pd.DataFrame({
    "gw": [4, 5, 6],
    "deadline_time": ["2026-08-24T11:00:00Z", "2026-09-04T17:30:00Z",
                      "2026-09-11T17:30:00Z"],
    "is_current": [True, False, False],
    "is_next": [False, True, False],
    "finished": [True, False, False],
    "data_checked": [True, False, False],
})

ADVICE = {
    "gw": GW, "hits": 0, "expected_pts": 61.4,
    "buys": [{"code": 22, "name": "Haaland", "ep": 7.2}],
    "sells": [{"code": 33, "name": "Rice", "ep": 3.1}],
    "captain": {"code": 22, "name": "Haaland", "ep": 7.2},
    "vice": {"code": 11, "name": "Saka", "ep": 5.4},
    "alternatives": [{"code": 44, "name": "Semenyo", "ep": 6.9,
                      "league_eo": 4.0}],
    "xi": [], "bench": [],
}

AVAILABILITY = pd.DataFrame({
    "code": [11, 22, 33],
    "status": ["d", "a", "i"],
    "chance_of_playing": [50.0, 100.0, 0.0],
    "llm_verdict": ["doubt", "fit", "out"],
    "override": [False, False, False],
})

LEDGER = [{"gw": 4, "my_points": 58, "model_points": 63, "accuracy": 71,
           "points_on_bench": 6,
           "hindsight": {"gap": 9},
           "lanes": [{"lane": "captaincy", "delta_pts": -4,
                      "label": "Blunder", "aligned": False},
                     {"lane": "transfers", "delta_pts": 1,
                      "label": "Brilliant", "aligned": False}]}]

SIM_HISTORY = [{"gw": 3, "p_win": 0.14, "p_top3": 0.4, "exp_finish": 3.1,
                "run_at": "2026-08-20T09:00:00Z", "n": 2000, "seed": 7},
               {"gw": 4, "p_win": 0.19, "p_top3": 0.5, "exp_finish": 2.6,
                "run_at": "2026-08-27T09:00:00Z", "n": 2000, "seed": 7}]


@pytest.fixture()
def bare(tmp_path, monkeypatch):
    """A clone with a reports directory and absolutely nothing in it."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    (tmp_path / "data" / "live").mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def furnished(bare, monkeypatch):
    EVENTS.to_parquet(bare / "data/live/events.parquet", index=False)
    (bare / f"reports/gw{GW}-advice.json").write_text(json.dumps(ADVICE))
    artifacts.save_availability(AVAILABILITY, GW)
    (bare / "reports/decision_ledger.json").write_text(
        json.dumps({"gws": LEDGER}))
    (bare / "reports/league_sim_history.json").write_text(
        json.dumps({"gws": SIM_HISTORY}))
    monkeypatch.setattr("gaffer.digest.latest_gw", lambda: GW)
    monkeypatch.setattr("gaffer.digest.upcoming_gw", lambda: GW)
    monkeypatch.setattr("gaffer.digest.watch_targets",
                        lambda: {11: "squad", 22: "plan"})
    return bare


def _sections(payload) -> dict[str, dict]:
    return {s["key"]: s for s in payload["sections"]}


# --- the envelope -----------------------------------------------------

def test_both_kinds_answer_the_same_envelope(furnished):
    for payload in (friday_briefing(), tuesday_debrief()):
        assert set(payload) == {"kind", "generated_at", "gw", "headline",
                                "sections"}
        assert payload["kind"] in DIGEST_KINDS
        assert isinstance(payload["headline"], str) and payload["headline"]
        assert all(isinstance(s["bits"], list) for s in payload["sections"])


def test_every_bit_is_a_string_because_the_card_joins_them(furnished):
    """The DiffStrip prose idiom, and the reason there is no markdown
    dependency anywhere in this cycle."""
    for payload in (friday_briefing(), tuesday_debrief()):
        for section in payload["sections"]:
            assert all(isinstance(bit, str) and bit for bit in
                       section["bits"])


# --- Friday -----------------------------------------------------------

def test_the_briefing_counts_down_to_the_deadline(furnished):
    section = _sections(friday_briefing())["deadline"]
    assert "GW5" in section["title"] or "GW5" in " ".join(section["bits"])


def test_the_briefing_names_the_move_and_the_armband(furnished):
    bits = " ".join(_sections(friday_briefing())["move"]["bits"])
    assert "Haaland" in bits and "Rice" in bits
    assert "Haaland" in " ".join(_sections(friday_briefing())["move"]["bits"])


def test_the_briefing_flags_only_watched_players(furnished):
    """Player 33 is injured and neither owned nor planned nor starred, so he
    is somebody else's problem."""
    bits = " ".join(_sections(friday_briefing())["flagged"]["bits"])
    assert "50" in bits or "doubt" in bits
    assert "33" not in bits


def test_a_squad_with_nothing_wrong_with_it_has_no_flagged_section(
        furnished):
    artifacts.save_availability(
        AVAILABILITY.assign(status="a", chance_of_playing=100.0,
                            llm_verdict="fit"), GW)
    assert "flagged" not in _sections(friday_briefing())


def test_the_briefing_offers_one_differential(furnished):
    bits = " ".join(_sections(friday_briefing())["differential"]["bits"])
    assert "Semenyo" in bits


def test_no_advice_at_all_is_a_briefing_that_says_to_run_one(bare,
                                                             monkeypatch):
    monkeypatch.setattr("gaffer.digest.latest_gw", lambda: None)
    monkeypatch.setattr("gaffer.digest.watch_targets", dict)
    payload = friday_briefing()
    assert "move" not in _sections(payload)
    assert "gaffer advise" in payload["headline"]


def test_the_staleness_warning_rides_the_briefing_when_there_is_one(
        furnished, monkeypatch):
    monkeypatch.setattr("gaffer.digest.data_warning",
                        lambda upcoming, through: "model has no data for GW4")
    assert "GW4" in " ".join(_sections(friday_briefing())["staleness"]
                             ["bits"])


def test_no_staleness_warning_is_no_staleness_section(furnished,
                                                      monkeypatch):
    monkeypatch.setattr("gaffer.digest.data_warning",
                        lambda upcoming, through: None)
    assert "staleness" not in _sections(friday_briefing())


# --- Tuesday ----------------------------------------------------------

def test_the_debrief_reports_the_newest_reviewed_gameweek(furnished):
    payload = tuesday_debrief()
    assert payload["gw"] == 4
    bits = " ".join(_sections(payload)["verdict"]["bits"])
    assert "58" in bits and "63" in bits and "71" in bits


def test_the_debrief_names_the_worst_lane_with_its_label(furnished):
    bits = " ".join(_sections(tuesday_debrief())["verdict"]["bits"])
    assert "captaincy" in bits and "Blunder" in bits


def test_the_debrief_reports_the_hindsight_gap(furnished):
    assert "9" in " ".join(_sections(tuesday_debrief())["hindsight"]["bits"])


def test_the_debrief_reports_the_p_win_movement_since_the_previous_gw(
        furnished):
    bits = " ".join(_sections(tuesday_debrief())["league"]["bits"])
    assert "19" in bits            # 0.19 as a percentage
    assert "+" in bits             # it went up from 0.14


def test_one_simulated_gameweek_is_a_level_not_a_movement(furnished,
                                                          tmp_path):
    (tmp_path / "reports/league_sim_history.json").write_text(
        json.dumps({"gws": SIM_HISTORY[:1]}))
    bits = " ".join(_sections(tuesday_debrief())["league"]["bits"])
    assert "14" in bits and "+" not in bits and "-" not in bits


def test_an_unreviewed_season_is_a_debrief_that_says_so(bare, monkeypatch):
    monkeypatch.setattr("gaffer.digest.latest_gw", lambda: None)
    payload = tuesday_debrief()
    assert _sections(payload) == {} or "verdict" not in _sections(payload)
    assert "not been reviewed" in payload["headline"]
    assert payload["gw"] is None


def test_a_corrupt_ledger_is_an_unreviewed_season(furnished, tmp_path):
    (tmp_path / "reports/decision_ledger.json").write_text("{not json")
    assert "verdict" not in _sections(tuesday_debrief())


def test_no_sim_history_is_no_league_section(furnished, tmp_path):
    (tmp_path / "reports/league_sim_history.json").unlink()
    assert "league" not in _sections(tuesday_debrief())


# --- the store --------------------------------------------------------

def test_a_digest_round_trips_through_its_artifact(furnished):
    payload = friday_briefing()
    save_digest("friday", payload)
    assert load_digest("friday") == payload


def test_loading_a_digest_that_was_never_written_is_none(bare):
    assert load_digest("friday") is None


def test_a_corrupt_digest_artifact_reads_as_none(bare):
    (artifacts.REPORTS / "digest_friday.json").write_text("{not json")
    assert load_digest("friday") is None


def test_writing_replaces_rather_than_appends(furnished):
    save_digest("friday", friday_briefing())
    save_digest("friday", {**friday_briefing(), "headline": "second"})
    assert load_digest("friday")["headline"] == "second"


def test_the_write_leaves_no_temp_behind(furnished):
    save_digest("friday", friday_briefing())
    assert not (artifacts.REPORTS / "digest_friday.json.tmp").exists()


# --- the runner and the notification ---------------------------------

def test_running_writes_the_artifact_and_prints_one_line(furnished, capsys):
    payload = run_digest("friday", notify=False)
    assert load_digest("friday") == payload
    printed = capsys.readouterr().out.strip().splitlines()
    assert len(printed) == 1
    assert payload["headline"] in printed[0]


def test_notify_false_makes_no_osascript_call_at_all(furnished, monkeypatch):
    """A7: not a suppressed call — no call. The spy is the rail."""
    calls = []
    monkeypatch.setattr("gaffer.digest.subprocess.run",
                        lambda *a, **k: calls.append(a))
    run_digest("friday", notify=False)
    assert calls == []


def test_notify_true_sends_the_headline(furnished, monkeypatch):
    calls = []

    def spy(args, **kwargs):
        calls.append(args)
        class R:  # noqa: D401 — a stand-in CompletedProcess
            returncode = 0
        return R()

    monkeypatch.setattr("gaffer.digest.subprocess.run", spy)
    payload = run_digest("friday", notify=True)
    assert calls and calls[0][0] == "osascript"
    assert payload["headline"] in " ".join(calls[0])
    # shell=False throughout: an argv list, never a command string.
    assert isinstance(calls[0], list)


def test_a_quote_in_a_players_note_cannot_break_the_applescript(furnished,
                                                                monkeypatch):
    """``json.dumps`` on both halves is what makes O'Brien — and whatever the
    user typed into a watchlist note — safe inside a string literal."""
    from gaffer.digest import _script

    script = _script('He said "go"', "O'Brien \\ out")
    assert script.count('display notification') == 1
    assert "\\\"go\\\"" in script


@pytest.mark.parametrize("failure", [
    FileNotFoundError("osascript"), OSError("no such process"),
    TimeoutError("timed out")])
def test_every_notification_failure_is_swallowed(furnished, monkeypatch,
                                                 failure, capsys):
    """A Linux CI box, a refused permission, a hung binary. None of them is a
    reason for a launchd job to fail."""
    def boom(*_a, **_k):
        raise failure

    monkeypatch.setattr("gaffer.digest.subprocess.run", boom)
    assert run_digest("friday", notify=True) is not None
    assert "notification not shown" in capsys.readouterr().out


def test_an_unknown_kind_is_refused_rather_than_guessed(furnished):
    from gaffer.errors import GafferError

    with pytest.raises(GafferError, match="unknown digest kind"):
        run_digest("wednesday")


def test_a_run_that_cannot_write_still_returns_the_payload(furnished,
                                                           monkeypatch,
                                                           capsys):
    monkeypatch.setattr("gaffer.digest.save_digest",
                        lambda kind, payload: (_ for _ in ()).throw(
                            OSError("read-only file system")))
    assert run_digest("friday", notify=False) is not None
    assert "digest not written" in capsys.readouterr().out


def test_a_total_failure_is_none_and_not_a_traceback(furnished, monkeypatch):
    monkeypatch.setattr("gaffer.digest.friday_briefing",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert run_digest("friday", notify=False) is None


# --- A6: the digest is a reader --------------------------------------

def test_the_module_writes_nothing_but_its_own_artifact():
    """The rail that keeps a Tuesday morning safe. ``append_ledger`` holds a
    lock and runs at 09:00; a digest at 09:30 that wrote to the same store
    would be the second writer nobody designed for."""
    import inspect

    import gaffer.digest as mod

    src = inspect.getsource(mod)
    for forbidden in ("append_ledger", "append_sim_history", "run_review",
                      "save_availability", "save_components",
                      "append_snapshot", "save_solve_state"):
        assert forbidden not in src, forbidden
```

- [ ] **Implement.** Create `src/gaffer/digest.py`:

```python
"""The Friday briefing and the Tuesday debrief.

Everything this module reports has been on disk for cycles. The advice, the
availability frame, the presser verdicts, the price predictor, the decision
ledger, the league simulation history and the biggest misses are all banked,
all readable, and all findable only by opening the tool and clicking through
four hubs. That is the gap: a manager who forgets to look on a Friday evening
does not get told, and a system that only answers when polled is not a
companion.

So this module joins the seven and says two sentences on a schedule. Friday at
17:00, after the pressers and before the deadline: what the plan is, who is
flagged, what moves tonight, and one differential. Tuesday at 09:30, after the
09:00 review job has banked the week: how it went, what it cost, and where the
league sits now.

Three constraints shape all of it.

**A section whose input is missing is absent, not empty.** "Last week: no
data" is a sentence about the tool; the absence of a section is a sentence
about the season, and a manager reading a digest on his phone deserves the
second one. Every builder below returns ``None`` rather than an empty section,
and the assembler drops the ``None``s.

**Nothing here writes anything but its own artifact.** ``append_ledger`` holds
a lock and is the ledger's only writer, and the review job that calls it runs
half an hour before the Tuesday digest. A digest that re-graded a gameweek in
order to report on it would be a second writer on a locked store on a
schedule, which is the kind of bug that shows up once in November and takes a
weekend. Every input here comes through a loader that already never raises.

**Nothing here may raise.** The caller is a launchd job with nowhere to report
a traceback. :func:`run_digest` has one ``except`` and returns ``None``.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from gaffer import artifacts
from gaffer.artifacts import (data_warning, ingested_through, latest_gw,
                              load_advice, load_availability, load_snapshot,
                              upcoming_gw)
from gaffer.errors import GafferError
from gaffer.watchlist import load_watchlist, watch_targets

DIGEST_KINDS = ("friday", "tuesday")

NOTIFY_TIMEOUT_S = 10
"""Seconds to wait for ``osascript``. Long enough for a cold Notification
Centre, short enough that a hung binary cannot wedge a launchd job."""

DOUBT_VERDICTS = {"doubt", "out", "major_doubt"}
"""The classifier verdicts worth waking somebody about. ``fit`` and an absent
verdict are both "nothing to say"."""


# --- the store --------------------------------------------------------

def digest_path(kind: str) -> Path:
    """``reports/digest_{kind}.json``, resolved at call time."""
    return artifacts.REPORTS / f"digest_{kind}.json"


def save_digest(kind: str, payload: dict) -> Path:
    """Write one digest through a temp file and ``os.replace``.

    Replace rather than append. A digest is about *now*, the ledger already
    keeps the season's history properly, and a log of forty Fridays is a file
    nobody reads that costs a schema decision.
    """
    artifacts.REPORTS.mkdir(parents=True, exist_ok=True)
    path = digest_path(kind)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=1, allow_nan=False))
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def load_digest(kind: str) -> dict | None:
    """One banked digest, or ``None``. Never raises."""
    path = digest_path(kind)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001 — a corrupt digest is no digest
        print(f"digest {kind} unreadable, ignoring it: {exc}")
        return None
    return payload if isinstance(payload, dict) else None


# --- section helpers --------------------------------------------------

def _section(key: str, title: str, bits: list[str | None]) -> dict | None:
    """One section, or ``None`` when nothing survived.

    The single place the absent-not-empty rule is enforced, so a builder can
    hand in a list with holes in it and get either a section worth rendering
    or nothing at all.
    """
    kept = [str(bit) for bit in bits if bit]
    return {"key": key, "title": title, "bits": kept} if kept else None


def _names() -> dict[int, str]:
    """``{code: name}`` from the bootstrap snapshot, or ``{}``."""
    try:
        players = load_snapshot("live/players.parquet")
        return {int(r.code): str(r.name) for r in players.itertuples()}
    except Exception as exc:  # noqa: BLE001 — a name is not worth a failure
        print(f"digest: player snapshot unreadable ({exc})")
        return {}


def _advice(gw: int | None) -> dict | None:
    if gw is None:
        return None
    try:
        return load_advice(int(gw))
    except Exception as exc:  # noqa: BLE001
        print(f"digest: no advice payload for GW{gw} ({exc})")
        return None


def _deadline_bits(gw: int | None) -> list[str | None]:
    """How long is left, from the events snapshot rather than the network."""
    if gw is None:
        return []
    try:
        events = load_snapshot("live/events.parquet")
        row = events[pd.to_numeric(events["gw"], errors="coerce") == int(gw)]
        if row.empty:
            return []
        when = pd.to_datetime(row["deadline_time"].iloc[0], utc=True,
                              format="mixed")
    except Exception as exc:  # noqa: BLE001
        print(f"digest: no deadline for GW{gw} ({exc})")
        return []
    hours = (when - pd.Timestamp.now(tz="UTC")).total_seconds() / 3600.0
    stamp = when.strftime("%a %d %b %H:%M UTC")
    if hours < 0:
        # A digest generated after the deadline is still worth writing — it is
        # what a Saturday morning re-run produces — and saying "in -3 hours"
        # would be worse than saying nothing about the countdown.
        return [f"GW{gw} deadline was {stamp}."]
    if hours < 48:
        return [f"GW{gw} deadline {stamp} — {round(hours)} hours away."]
    return [f"GW{gw} deadline {stamp} — {round(hours / 24)} days away."]


def _flagged_bits(gw: int | None, watched: dict[int, str],
                  names: dict[int, str]) -> list[str | None]:
    """Watched players the availability pass or a presser is unhappy about.

    Restricted to the watch set on purpose: an injury list of the whole league
    is a website, and this is a message about the manager's own week.
    """
    if gw is None or not watched:
        return []
    bits: list[str | None] = []
    try:
        avail = load_availability(int(gw))
    except Exception as exc:  # noqa: BLE001
        print(f"digest: no availability for GW{gw} ({exc})")
        avail = None
    if avail is not None and "code" in getattr(avail, "columns", []):
        codes = pd.to_numeric(avail["code"], errors="coerce")
        rows = avail[codes.isin(list(watched))]
        for row in rows.itertuples():
            code = int(getattr(row, "code"))
            name = names.get(code, str(code))
            status = str(getattr(row, "status", "") or "")
            chance = getattr(row, "chance_of_playing", None)
            verdict = str(getattr(row, "llm_verdict", "") or "")
            pieces = []
            if status and status != "a":
                pieces.append(f"status {status}")
            if chance is not None and not (isinstance(chance, float)
                                           and math.isnan(chance)) \
                    and float(chance) < 100.0:
                pieces.append(f"{int(float(chance))}% to play")
            if verdict in DOUBT_VERDICTS:
                pieces.append(f"news says {verdict}")
            if pieces:
                bits.append(f"{name} — {', '.join(pieces)}"
                            f" ({watched.get(code, 'watchlist')})")
    bits.extend(_presser_bits(gw, watched, names))
    return bits


def _presser_bits(gw: int, watched: dict[int, str],
                  names: dict[int, str]) -> list[str]:
    """Anything the press-conference log said about a watched player."""
    try:
        from gaffer.data.news.presser_log import load_presser_log

        log = load_presser_log()
    except Exception as exc:  # noqa: BLE001
        print(f"digest: no presser log ({exc})")
        return []
    if log is None or log.empty or "code" not in log.columns:
        return []
    rows = log[(pd.to_numeric(log["gw"], errors="coerce") == int(gw))
               & (pd.to_numeric(log["code"],
                                errors="coerce").isin(list(watched)))]
    out = []
    for row in rows.itertuples():
        verdict = str(getattr(row, "verdict", "") or "")
        if verdict and verdict in DOUBT_VERDICTS:
            code = int(getattr(row, "code"))
            out.append(f"{names.get(code, str(code))} — the presser said "
                       f"{verdict}")
    return out


def _movers_bits(watched: dict[int, str],
                 names: dict[int, str]) -> list[str | None]:
    """Tonight's likely changes, off the same banked snapshot the card uses."""
    if not watched:
        return []
    try:
        from gaffer.data import store
        from gaffer.prices import price_alerts

        if not store.exists("live/players.parquet"):
            return []
        alerts = price_alerts(store.load("live/players.parquet"),
                              list(watched))
    except Exception as exc:  # noqa: BLE001
        print(f"digest: no price readings ({exc})")
        return []
    out: list[str | None] = []
    for row in alerts.itertuples():
        code = int(getattr(row, "code"))
        caveat = " (FPL still calibrating him)" \
            if bool(getattr(row, "calibrating", False)) else ""
        out.append(f"{names.get(code, str(row.name))} may "
                   f"{row.direction} tonight "
                   f"({round(float(row.price_change_percent))}%)"
                   f"{caveat}")
    return out


# --- Friday -----------------------------------------------------------

def friday_briefing() -> dict:
    """What needs doing before the deadline.

    Never raises: every read below is a loader that already answers ``None``
    or an empty frame on failure, and the ones that are not are wrapped.
    """
    gw = None
    try:
        gw = latest_gw()
    except Exception as exc:  # noqa: BLE001
        print(f"digest: no advice on disk ({exc})")
    names = _names()
    watched = watch_targets()
    advice = _advice(gw)

    sections = []
    sections.append(_section("deadline", "Deadline", _deadline_bits(gw)))

    if advice is not None:
        buys = ", ".join(str(p.get("name")) for p in advice.get("buys") or [])
        sells = ", ".join(str(p.get("name"))
                          for p in advice.get("sells") or [])
        captain = (advice.get("captain") or {}).get("name")
        hits = int(advice.get("hits") or 0)
        move = (f"{buys or 'nobody'} in, {sells or 'nobody'} out"
                + (f" — {hits} hit{'s' if hits != 1 else ''}" if hits else ""))
        sections.append(_section("move", "The plan", [
            move,
            f"Captain {captain}." if captain else None,
            f"{advice.get('expected_pts')} expected points from the XI."
            if advice.get("expected_pts") is not None else None]))

    sections.append(_section("flagged", "Watch out for",
                             _flagged_bits(gw, watched, names)))
    sections.append(_section("movers", "Prices tonight",
                             _movers_bits(watched, names)))

    if advice is not None:
        alts = advice.get("alternatives") or []
        top = alts[0] if alts else None
        sections.append(_section("differential", "One to consider", [
            f"{top.get('name')} — {top.get('ep')} xPts"
            + (f", {top.get('league_eo')}% league ownership"
               if top.get("league_eo") is not None else "")
            if top else None]))

    try:
        warning = data_warning(upcoming_gw(), ingested_through())
    except Exception as exc:  # noqa: BLE001
        print(f"digest: no staleness reading ({exc})")
        warning = None
    sections.append(_section("staleness", "Data", [warning]))

    kept = [s for s in sections if s is not None]
    if advice is None:
        headline = ("No advice on disk — run `gaffer advise` before the "
                    "deadline.")
    else:
        cap = (advice.get("captain") or {}).get("name") or "nobody"
        buys = advice.get("buys") or []
        headline = (f"GW{gw}: captain {cap}, "
                    + (f"{len(buys)} transfer"
                       f"{'s' if len(buys) != 1 else ''}." if buys
                       else "no transfers."))
    return {"kind": "friday", "generated_at": _now(), "gw": gw,
            "headline": headline, "sections": kept}


# --- Tuesday ----------------------------------------------------------

def tuesday_debrief() -> dict:
    """How last week actually went, off the ledger the review job banked."""
    from gaffer.review import load_ledger, season_summary

    ledger = load_ledger()
    row = ledger[-1] if ledger else None
    gw = int(row["gw"]) if row else None

    sections = []
    if row is not None:
        graded = [lane for lane in (row.get("lanes") or [])
                  if lane.get("delta_pts") is not None]
        worst = min(graded, key=lambda lane: lane["delta_pts"]) \
            if graded else None
        sections.append(_section("verdict", f"GW{gw}", [
            f"You scored {row.get('my_points')}; the model's plan scored "
            f"{row.get('model_points')}."
            if row.get("model_points") is not None else
            f"You scored {row.get('my_points')}.",
            f"Accuracy {row.get('accuracy')}."
            if row.get("accuracy") is not None else None,
            f"Worst lane: {worst['lane']} {worst['delta_pts']:+d} "
            f"({worst.get('label')})." if worst else None,
            f"{row.get('points_on_bench')} points left on the bench."
            if row.get("points_on_bench") is not None else None]))
        gap = (row.get("hindsight") or {}).get("gap")
        sections.append(_section("hindsight", "Hindsight XI", [
            f"The best eleven from your fifteen would have scored {gap} more."
            if gap is not None else None]))

    sections.append(_section("league", "League", _league_bits()))
    sections.append(_section("miss", "Biggest miss", _miss_bits()))

    summary = season_summary(ledger)
    if summary is not None:
        worst = summary.get("worst")
        sections.append(_section("season", "Season so far", [
            f"{len(summary.get('gws') or [])} gameweeks reviewed.",
            f"{summary.get('hindsight_gap')} points lost to bench and "
            f"armband across {summary.get('hindsight_gap_gws')} of them."
            if summary.get("hindsight_gap_gws") else None,
            f"Worst single decision so far: GW{worst.get('gw')} "
            f"{worst.get('lane')} ({worst.get('label')})."
            if worst else None]))

    kept = [s for s in sections if s is not None]
    headline = (f"GW{gw}: you {row.get('my_points')}, model "
                f"{row.get('model_points')}." if row is not None
                else "The season has not been reviewed yet — run "
                     "`gaffer review`.")
    return {"kind": "tuesday", "generated_at": _now(), "gw": gw,
            "headline": headline, "sections": kept}


def _league_bits() -> list[str | None]:
    """Where the title race sits, and which way it moved.

    One simulated gameweek is a *level*, not a movement: reporting "+14pp"
    against nothing would invent a trend out of a first reading.
    """
    try:
        from gaffer.league_sim import load_sim_history

        history = load_sim_history()
    except Exception as exc:  # noqa: BLE001
        print(f"digest: no league sim history ({exc})")
        return []
    if not history:
        return []
    now = history[-1]
    current = float(now.get("p_win") or 0.0)
    bits = [f"Win probability {round(current * 100)}% after GW{now.get('gw')}."]
    if len(history) > 1:
        before = float(history[-2].get("p_win") or 0.0)
        delta = round((current - before) * 100)
        bits.append(f"{delta:+d}pp since GW{history[-2].get('gw')}.")
    return bits


def _miss_bits() -> list[str | None]:
    """The single largest forecast error of the newest scored week.

    Deliberately not the debrief's own gameweek. ``scoreable_gw`` is the
    largest week with *both* a components parquet and played rows, which is
    the only week a miss can be computed for; the reviewed week may predate
    the oldest components file on a clone, and a section that silently
    reported a different week than the heading claimed would be worse than no
    section. The bit names its gameweek for exactly that reason.
    """
    try:
        from gaffer.misses import biggest_misses, scoreable_gw

        target = scoreable_gw()
        if target is None:
            return []
        rows = biggest_misses(int(target))
    except Exception as exc:  # noqa: BLE001
        print(f"digest: no miss table ({exc})")
        return []
    if not rows:
        return []
    top = rows[0]
    direction = "over" if top["miss"] < 0 else "under"
    return [f"GW{target}: {top['name']} — forecast {top['ep']}, scored "
            f"{top['actual']}. The model {direction}rated him by "
            f"{abs(top['miss'])}."]


# --- the notification -------------------------------------------------

def _script(title: str, body: str) -> str:
    """The AppleScript one-liner, with both halves safely quoted.

    ``json.dumps`` rather than an f-string with quotes round it: a player
    called O'Brien, a watchlist note with a double quote in it, or a backslash
    anywhere would otherwise either break the script or — worse — change what
    it does. JSON string escaping and AppleScript string escaping agree on
    every character that matters here.
    """
    return (f"display notification {json.dumps(body)} "
            f"with title {json.dumps(title)}")


def _notify(title: str, body: str) -> bool:
    """Show a macOS notification. ``True`` if it went out.

    Best-effort in the strongest sense: no ``osascript`` at all (a Linux CI
    box), a refused Notification Centre permission, a non-zero exit and a hang
    are each a printed line and a ``False``. ``shell=False`` throughout — the
    argv list is the whole defence against everything ``_script`` quotes.
    """
    try:
        done = subprocess.run(["osascript", "-e", _script(title, body)],
                              capture_output=True, timeout=NOTIFY_TIMEOUT_S,
                              check=False)
        if done.returncode != 0:
            print(f"notification not shown: osascript exited "
                  f"{done.returncode}")
            return False
        return True
    except Exception as exc:  # noqa: BLE001 — never a reason to fail a job
        print(f"notification not shown: {exc}")
        return False


# --- the runner -------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def format_digest(payload: dict) -> str:
    """The one line the CLI and the launchd log both print."""
    return (f"{payload.get('kind', '?').title()} digest: "
            f"{payload.get('headline')} "
            f"({len(payload.get('sections') or [])} sections)")


TITLES = {"friday": "Gaffer — Friday briefing",
          "tuesday": "Gaffer — Tuesday debrief"}


def run_digest(kind: str, *, notify: bool = True) -> dict | None:
    """Build one digest, bank it, print one line, maybe notify.

    ``notify`` is an argument and not a config read on purpose: this module
    knows how to send a notification and has no opinion about whether it
    should, and the caller that reads ``[digest] notify`` is the CLI command
    and the job kind (plan A7).

    An unknown kind raises — it can only come from a typo in a plist or a
    hand-typed CLI flag, and guessing "friday" for "wednesday" would be a
    silently wrong digest on a schedule. Everything else is swallowed: a
    Friday with no network is a Friday with no briefing, not a traceback in
    ``logs/digest-friday.log``.
    """
    if kind not in DIGEST_KINDS:
        raise GafferError(
            f"unknown digest kind {kind!r} — expected one of "
            f"{', '.join(DIGEST_KINDS)}")
    try:
        payload = (friday_briefing() if kind == "friday"
                   else tuesday_debrief())
    except Exception as exc:  # noqa: BLE001 — a scheduled job never blocks
        print(f"digest not built: {exc}")
        return None
    try:
        save_digest(kind, payload)
    except Exception as exc:  # noqa: BLE001
        # The payload is still worth returning and printing: a read-only disk
        # should not also cost the user the sentence they were owed.
        print(f"digest not written: {exc}")
    print(format_digest(payload))
    if notify:
        _notify(TITLES[kind], payload["headline"])
    return payload
```

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_digest.py tests/test_review.py \
  tests/test_league_sim.py tests/test_misses.py
```

- [ ] **Commit.**

```bash
git add src/gaffer/digest.py tests/test_digest.py && git commit -m "$(cat <<'EOF'
feat: Friday briefing and Tuesday debrief, joined from seven banked reads

Absent sections rather than empty ones, a reader that writes nothing but its
own artifact, and a best-effort osascript notification behind an argument.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 5 — the CLI command, two job kinds, two plists, one config key

**Files:**
- Modify `src/gaffer/config.py`
- Modify `src/gaffer/cli.py` (append `digest`)
- Modify `src/gaffer/web/job_kinds.py`
- Create `tests/test_web_job_kinds_v8f.py`
- Create `scripts/com.gaffer.digest-friday.plist`
- Create `scripts/com.gaffer.digest-tuesday.plist`
- Modify `scripts/install_automation.sh`
- Modify `frontend/src/types.ts`
- Modify `tests/test_web_job_kinds.py`, `tests/test_web_job_kinds_v8b.py`, `tests/test_web_job_kinds_v8c.py`
- Modify (**PROTECTED — authorized below only**) `tests/test_v8b_degradation.py`, `tests/test_v8c_degradation.py`, `tests/test_v8d_degradation.py`, `tests/test_v8e_degradation.py`, `tests/test_v8g_degradation.py`

---

### 🛑 STOP — the one protected edit in this cycle

**Do not begin Task 5 until the orchestrator has explicitly authorized the seven line edits below.** This is the only point in v8f where a protected file changes. Every other task in this plan is purely additive to unprotected files, and this task is arranged so that both breaking changes — the two job kinds and the one config key — land at the same moment, so there is exactly one authorization to give.

**Why the pins break.** Five degradation suites and one job-kind suite assert `len(JOB_KINDS) == 10`; v8f makes it 12. One degradation suite asserts `len(dataclasses.fields(Config)) == 47`; v8f makes it 48. Both pins exist precisely so that a cycle cannot add a job kind or a config key by accident, so both must be updated deliberately, by hand, with the new number and a comment naming this cycle — not silenced, not parameterized, and not made to read the value they are pinning.

**The seven lines, in protected files (verified against the current tree):**

| File | Line | From | To |
| --- | --- | --- | --- |
| `tests/test_v8b_degradation.py` | 214 | `assert len(job_kinds.JOB_KINDS) == 10` | `== 12` |
| `tests/test_v8c_degradation.py` | 193 | `assert len(job_kinds.JOB_KINDS) == 10` | `== 12` |
| `tests/test_v8d_degradation.py` | 176 | `assert len(JOB_KINDS) == 10` | `== 12` |
| `tests/test_v8e_degradation.py` | 188 | `assert len(JOB_KINDS) == 10` | `== 12` |
| `tests/test_v8g_degradation.py` | 257 | `assert len(JOB_KINDS) == 10` | `== 12` |
| `tests/test_v8g_degradation.py` | 280 | `assert len(names) == 47` | `== 48` |
| `tests/test_web_job_kinds_v8b.py` | 16 | `assert len(job_kinds.JOB_KINDS) == 10` | `== 12` |

`tests/test_web_job_kinds_v8b.py` is a job-kind suite rather than a degradation suite and is **not** on the protected list; it is named here anyway so the count of "places that say ten" is complete and nobody hunts for a seventh.

**Four further pins break and are unprotected — edit them freely as part of this task, no authorization needed:**

| File | Line | What it pins |
| --- | --- | --- |
| `tests/test_web_job_kinds.py` | 24-28 | the sorted list of kind names |
| `tests/test_web_job_kinds_v8c.py` | 19-27 | the sorted list, and its lockstep comment |
| `frontend/src/types.ts` | 625-627 | `JOB_KINDS` — the browser's copy of the list |
| `frontend/src/types.ts` | 631-642 | `JOB_KIND_LABEL` — one label per kind, exhaustive by type |

**Also update the surrounding comment on each protected line**, so the next cycle reads why the number moved rather than finding a bare integer:

- the five job-kind lines gain `# v8f added digest-friday and digest-tuesday as the eleventh and twelfth.`
- `tests/test_v8g_degradation.py:278-279`'s comment changes from "47 keys as of v8f. v8g adds none" to `# 48 keys as of v8f, which added [digest] notify. v8g adds none, so any` (keeping the second half of the sentence).

**Nothing else in any protected file may change.** Task 10 diffs them and expects exactly these seven lines plus their comments.

---

- [ ] **Wait for authorization. Then make the seven authorized edits and the four unprotected ones**, and confirm the suites fail in exactly the expected direction before writing any implementation:

```bash
uv run pytest -q tests/test_v8b_degradation.py tests/test_v8c_degradation.py \
  tests/test_v8d_degradation.py tests/test_v8e_degradation.py \
  tests/test_v8g_degradation.py tests/test_web_job_kinds.py \
  tests/test_web_job_kinds_v8b.py tests/test_web_job_kinds_v8c.py
```

Every failure must be a count or a list mismatch on a kind or a config key this task is about to add. A failure anywhere else means an edit landed in the wrong place — revert and report.

- [ ] **Write the failing test.** Create `tests/test_web_job_kinds_v8f.py`:

```python
"""The eleventh and twelfth kinds: ``digest-friday`` and ``digest-tuesday``.

``run_sensitivity_job``'s shape, twice: the module owns the work and the
printing, the wrapper owns the one-line job record. The one thing these two
add over that pattern is the config read — ``run_digest`` takes ``notify`` as
an argument and has no opinion about whether it should fire, and this is the
seam where the opinion comes from (plan A7).
"""

from __future__ import annotations

import dataclasses
import inspect

import pytest

from gaffer.config import Config
from gaffer.web import job_kinds


def test_both_digest_kinds_are_registered():
    assert job_kinds.JOB_KINDS["digest-friday"] is job_kinds.run_digest_friday
    assert job_kinds.JOB_KINDS["digest-tuesday"] \
        is job_kinds.run_digest_tuesday


def test_the_registry_is_exactly_twelve_kinds():
    assert sorted(job_kinds.JOB_KINDS) == [
        "advise", "advise-fast", "digest-friday", "digest-tuesday",
        "evaluate", "field-scrape", "news-shadow", "refresh-data", "review",
        "sensitivity", "snapshot", "track-pens"]


def test_every_kind_is_still_a_zero_argument_callable():
    """The runner calls these with no arguments; a wrapper that grew a
    parameter would be a 500 at press-the-button time."""
    for kind, fn in job_kinds.JOB_KINDS.items():
        params = inspect.signature(fn).parameters
        assert all(p.default is not inspect.Parameter.empty
                   for p in params.values()), kind


def test_the_wrapper_returns_the_record_the_runner_shows(monkeypatch,
                                                         capsys):
    monkeypatch.setattr(
        "gaffer.digest.run_digest",
        lambda kind, notify=True: {"kind": kind, "gw": 5,
                                   "headline": "GW5: captain Haaland.",
                                   "sections": [{"key": "move",
                                                 "title": "t",
                                                 "bits": ["b"]}]})
    assert job_kinds.run_digest_friday() == {"kind": "friday", "gw": 5,
                                             "sections": 1}
    assert "captain Haaland" in capsys.readouterr().out


def test_a_degraded_digest_is_still_a_finished_job(monkeypatch):
    """``run_digest`` answers ``None`` on a bad Friday — no advice, no
    network, an unwritable disk. The job reports zero sections rather than
    failing the run, which is ``run_field_scrape_job``'s trade exactly."""
    monkeypatch.setattr("gaffer.digest.run_digest",
                        lambda kind, notify=True: None)
    assert job_kinds.run_digest_tuesday() == {"kind": "tuesday", "gw": None,
                                              "sections": 0}


def test_the_notify_switch_reaches_the_module(monkeypatch):
    seen = {}

    def spy(kind, notify=True):
        seen["kind"], seen["notify"] = kind, notify
        return None

    monkeypatch.setattr("gaffer.digest.run_digest", spy)
    monkeypatch.setattr("gaffer.web.job_kinds._notify_enabled", lambda: False)
    job_kinds.run_digest_friday()
    assert seen == {"kind": "friday", "notify": False}


def test_the_switch_defaults_on_with_no_config_at_all(monkeypatch, tmp_path):
    """A clone with no config.toml still gets its notification: the key is a
    way to turn a working thing off, not a thing to find before it works."""
    from gaffer.config import serving_config

    monkeypatch.chdir(tmp_path)
    serving_config.cache_clear()
    try:
        assert job_kinds._notify_enabled() is True
    finally:
        serving_config.cache_clear()


def test_the_config_carries_exactly_one_new_key():
    names = {f.name for f in dataclasses.fields(Config)}
    assert "digest_notify" in names
    assert not [n for n in names if "digest" in n and n != "digest_notify"]


def test_the_key_reads_from_its_own_toml_section(tmp_path, monkeypatch):
    from gaffer.config import load_config

    path = tmp_path / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n"
                    "[digest]\nnotify = false\n")
    assert load_config(path).digest_notify is False


def test_an_absent_digest_section_leaves_the_default(tmp_path):
    from gaffer.config import load_config

    path = tmp_path / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n")
    assert load_config(path).digest_notify is True
```

- [ ] **Add the config key.** In `src/gaffer/config.py`, append to the dataclass after `news_overrides` (L107):

```python
    # v8f. The only switch this cycle adds. On by default, for the reason the
    # override switch is: a notification nobody has to enable is the whole
    # feature, and a switch that must be found before the tool works is a
    # feature nobody finds. Off is for a machine that is not the user's own —
    # a server, a CI box, a shared laptop — where a launchd job firing
    # Notification Centre would be somebody else's surprise.
    digest_notify: bool = True
```

and in `load_config`, beside the other section reads (after `news = raw.get("news", {})`, L119):

```python
    digest = raw.get("digest", {})
```

with the field read on the last line of the `Config(...)` construction, after `news_overrides=` (L177):

```python
        digest_notify=bool(digest.get("notify", True)),
```

Add the section to `config.example.toml` too, commented, with the same sentence.

- [ ] **Add the CLI command.** In `src/gaffer/cli.py`, after `review` (L277):

```python
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
```

- [ ] **Add the job kinds.** In `src/gaffer/web/job_kinds.py`, after `run_sensitivity_job` (L152):

```python
def _notify_enabled() -> bool:
    """``[digest] notify``, read the way every other serve-time switch is.

    Its own function rather than an inline read so the rail that asserts the
    switch reaches the module has one thing to patch, and so a clone with no
    ``config.toml`` — which ``serving_config`` degrades to defaults for — gets
    its notification rather than an exception.
    """
    from gaffer.config import serving_config

    return bool(serving_config().digest_notify)


def _digest_job(kind: str) -> dict:
    """One digest kind's job body. ``run_digest`` does the work and prints.

    ``None`` back from ``run_digest`` is a *finished* job with zero sections,
    not a failed one — ``run_field_scrape_job``'s trade, for the same reason:
    a Friday with no advice on disk is a real and ordinary state, and a red
    job record for it would train the user to ignore red job records.
    """
    from gaffer.digest import run_digest

    payload = run_digest(kind, notify=_notify_enabled()) or {}
    return {"kind": kind, "gw": payload.get("gw"),
            "sections": len(payload.get("sections") or [])}


def run_digest_friday() -> dict:
    """``gaffer digest --kind friday`` — the pre-deadline briefing (v8f D3)."""
    return _digest_job("friday")


def run_digest_tuesday() -> dict:
    """``gaffer digest --kind tuesday`` — the post-review debrief (v8f D3)."""
    return _digest_job("tuesday")
```

and two entries at the end of `JOB_KINDS` (L164):

```python
    "sensitivity": run_sensitivity_job,
    "digest-friday": run_digest_friday,
    "digest-tuesday": run_digest_tuesday,
}
```

- [ ] **Update the browser's copy.** In `frontend/src/types.ts`, L625-627 and the label map:

```ts
export const JOB_KINDS = ['advise', 'advise-fast', 'evaluate', 'refresh-data',
  'news-shadow', 'snapshot', 'track-pens', 'field-scrape', 'review',
  'sensitivity', 'digest-friday', 'digest-tuesday'] as const
```

and inside `JOB_KIND_LABEL`, after `sensitivity`:

```ts
  'digest-friday': 'Friday briefing',
  'digest-tuesday': 'Tuesday debrief',
```

- [ ] **Write the two plists.** Create `scripts/com.gaffer.digest-friday.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.gaffer.digest-friday</string>
  <key>ProgramArguments</key><array>
    <string>/bin/zsh</string><string>-lc</string>
    <string>cd __PROJECT_DIR__ &amp;&amp; uv run gaffer digest --kind friday &gt;&gt; logs/digest-friday.log 2&gt;&amp;1</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key><integer>5</integer>
    <key>Hour</key><integer>17</integer><key>Minute</key><integer>0</integer>
  </dict>
</dict></plist>
```

and `scripts/com.gaffer.digest-tuesday.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.gaffer.digest-tuesday</string>
  <key>ProgramArguments</key><array>
    <string>/bin/zsh</string><string>-lc</string>
    <string>cd __PROJECT_DIR__ &amp;&amp; uv run gaffer digest --kind tuesday &gt;&gt; logs/digest-tuesday.log 2&gt;&amp;1</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key><integer>2</integer>
    <key>Hour</key><integer>9</integer><key>Minute</key><integer>30</integer>
  </dict>
</dict></plist>
```

Weekday 5 is launchd's Friday and 2 its Tuesday (Sunday is 0). 09:30 rather than 09:00 so the debrief reads a ledger the 09:00 `com.gaffer.review` job has already written — half an hour is generous for a review of one gameweek and the two jobs are independent, so a slow review costs a stale debrief rather than a wrong one.

- [ ] **Extend the installer.** In `scripts/install_automation.sh`, the loop on L5 gains two words and the echo on L13 gains a clause (A8 — the loop iterates plist *names* and each plist carries its own command, so no convention changes):

```zsh
for name in advise prices snapshot field review digest-friday digest-tuesday; do
```

```zsh
echo "Installed: Thursday 18:00 advise run + nightly 23:15 price check + daily 17:00 availability snapshot + Sat/Sun 12:30 field scrape + Tuesday 09:00 decision review + Friday 17:00 briefing + Tuesday 09:30 debrief."
```

- [ ] **Verify.** The whole python suite, because this is the task that touched shared pins:

```bash
uv run pytest -q
cd frontend && npx tsc --noEmit && npx vitest run
zsh -n scripts/install_automation.sh
plutil -lint scripts/com.gaffer.digest-friday.plist \
  scripts/com.gaffer.digest-tuesday.plist
```

Expect 2468 + the new tests, all green, and zero failures anywhere in the five protected degradation suites.

- [ ] **Commit.** The protected pin edits go in this commit and are named in its body, so `git log` records the authorization alongside the change:

```bash
git add src/gaffer/config.py config.example.toml src/gaffer/cli.py \
  src/gaffer/web/job_kinds.py tests/test_web_job_kinds_v8f.py \
  tests/test_web_job_kinds.py tests/test_web_job_kinds_v8b.py \
  tests/test_web_job_kinds_v8c.py tests/test_v8b_degradation.py \
  tests/test_v8c_degradation.py tests/test_v8d_degradation.py \
  tests/test_v8e_degradation.py tests/test_v8g_degradation.py \
  frontend/src/types.ts scripts/com.gaffer.digest-friday.plist \
  scripts/com.gaffer.digest-tuesday.plist scripts/install_automation.sh \
  && git commit -m "$(cat <<'EOF'
feat: gaffer digest — CLI, two job kinds, two plists, one config key

The two digests reach a schedule. Job kinds go 10 -> 12 and the config gains
[digest] notify, so seven count pins move by hand with the orchestrator's
authorization: five protected degradation suites, one job-kind suite, and the
config-field pin in test_v8g_degradation.

The installer needs no convention change — its loop iterates plist names and
each plist carries its own command line.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 6 — the retrain diff finally says something about players

**Files:**
- Modify `src/gaffer/artifacts.py` (`save_components` L106-111; append `ep_movers`)
- Create `tests/test_ep_movers.py`
- Modify `src/gaffer/web/routers/advice.py` (L122-155)
- Modify `src/gaffer/web/schemas.py`
- Create `tests/test_web_advice_movers.py`
- Modify `frontend/src/types.ts`
- Modify `frontend/src/hubs/this-week/WhyPanel.tsx` (L10-48, L154)
- Modify `frontend/src/hubs/this-week/WhyPanel.test.tsx`

- [ ] **Write the failing test.** Create `tests/test_ep_movers.py`:

```python
"""One predecessor components file, and the diff it makes possible.

"Since last run" has always been able to say the plan changed and never able
to say *why*. The why is in the components parquet, which every advise run
overwrites — so the fix is one bounded copy and a join.

Three claims carry the file. The copy is a copy, taken before the overwrite
and never accumulating past one slot. Its failure costs the diff and never the
run, because banking the current components is the function's actual job. And
the diff compares each frame's own first gameweek (plan A9), so a retrain that
also rolled the horizon forward does not report the whole pool as having moved
out of a gameweek that is no longer in the file.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.artifacts import (COMPONENT_COLS, components_path, ep_movers,
                              load_components, prev_components_path,
                              save_components)

GW = 5


def _frame(rows: list[dict]) -> pd.DataFrame:
    out = pd.DataFrame(rows)
    for col in COMPONENT_COLS:
        if col not in out.columns:
            out[col] = float("nan")
    return out[COMPONENT_COLS]


BEFORE = _frame([
    {"code": 11, "name": "Saka", "gw": GW, "ep": 5.0},
    {"code": 22, "name": "Haaland", "gw": GW, "ep": 7.0},
    {"code": 33, "name": "Rice", "gw": GW, "ep": 3.0},
    {"code": 11, "name": "Saka", "gw": GW + 1, "ep": 4.0},
])

AFTER = _frame([
    {"code": 11, "name": "Saka", "gw": GW, "ep": 6.4},     # +1.4
    {"code": 22, "name": "Haaland", "gw": GW, "ep": 6.1},  # -0.9
    {"code": 33, "name": "Rice", "gw": GW, "ep": 3.2},     # +0.2, below
    {"code": 44, "name": "New", "gw": GW, "ep": 8.0},      # no predecessor
    {"code": 11, "name": "Saka", "gw": GW + 1, "ep": 9.9},
])


@pytest.fixture(autouse=True)
def _reports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()


def test_the_first_save_takes_no_copy_because_there_is_nothing_to_copy():
    save_components(BEFORE, GW)
    assert not prev_components_path(GW).exists()


def test_the_second_save_preserves_the_first():
    save_components(BEFORE, GW)
    save_components(AFTER, GW)
    assert load_components(GW)["ep"].sum() == pytest.approx(
        AFTER["ep"].sum())
    prev = pd.read_parquet(prev_components_path(GW))
    assert prev["ep"].sum() == pytest.approx(BEFORE["ep"].sum())


def test_a_third_save_keeps_one_slot_not_two():
    """Bounded. The question is "what did tonight's retrain change", and a
    third file answers no question anybody asked."""
    save_components(BEFORE, GW)
    save_components(AFTER, GW)
    save_components(BEFORE, GW)
    prev = pd.read_parquet(prev_components_path(GW))
    assert prev["ep"].sum() == pytest.approx(AFTER["ep"].sum())
    assert not (components_path(GW).parent
                / f"components_gw{GW}_prev_prev.parquet").exists()


def test_a_failed_copy_costs_the_diff_and_not_the_run(monkeypatch, capsys):
    save_components(BEFORE, GW)
    monkeypatch.setattr("gaffer.artifacts.shutil.copyfile",
                        lambda *a: (_ for _ in ()).throw(OSError("full")))
    assert save_components(AFTER, GW) == components_path(GW)
    assert load_components(GW)["ep"].sum() == pytest.approx(
        AFTER["ep"].sum())
    assert "no predecessor kept" in capsys.readouterr().out


# --- the diff ---------------------------------------------------------

def test_no_predecessor_is_none_rather_than_an_empty_list():
    """A9: "we have not retrained since you last looked" and "the retrain
    changed nothing" are different sentences, and the payload must be able to
    tell them apart."""
    save_components(BEFORE, GW)
    assert ep_movers(GW) is None


def test_the_movers_come_back_biggest_absolute_change_first():
    save_components(BEFORE, GW)
    save_components(AFTER, GW)
    movers = ep_movers(GW)
    assert [m["code"] for m in movers] == [11, 22]
    assert movers[0]["ep_prev"] == pytest.approx(5.0)
    assert movers[0]["ep_now"] == pytest.approx(6.4)
    assert movers[0]["delta"] == pytest.approx(1.4)
    assert movers[0]["name"] == "Saka"


def test_a_player_below_the_threshold_is_not_a_mover():
    save_components(BEFORE, GW)
    save_components(AFTER, GW)
    assert 33 not in [m["code"] for m in ep_movers(GW)]


def test_the_threshold_is_a_parameter():
    save_components(BEFORE, GW)
    save_components(AFTER, GW)
    assert [m["code"] for m in ep_movers(GW, threshold=0.1)] == [11, 22, 33]


def test_a_player_with_no_predecessor_row_is_not_a_mover():
    """He did not *move* — he appeared. Reporting a new pool entrant as
    "+8.0 EP" would be the diff's most eye-catching and least true row."""
    save_components(BEFORE, GW)
    save_components(AFTER, GW)
    assert 44 not in [m["code"] for m in ep_movers(GW)]


def test_only_each_frames_own_first_gameweek_is_compared():
    """A9. Saka's GW6 EP moved by 5.9 and is not reported: the diff is about
    the week being decided, which is the only one both frames must share."""
    save_components(BEFORE, GW)
    save_components(AFTER, GW)
    assert all(abs(m["delta"]) < 5.0 for m in ep_movers(GW))


def test_a_double_gameweek_sums_its_fixtures_on_both_sides():
    save_components(_frame([
        {"code": 11, "name": "Saka", "gw": GW, "ep": 2.0},
        {"code": 11, "name": "Saka", "gw": GW, "ep": 2.0}]), GW)
    save_components(_frame([
        {"code": 11, "name": "Saka", "gw": GW, "ep": 3.5},
        {"code": 11, "name": "Saka", "gw": GW, "ep": 3.5}]), GW)
    assert ep_movers(GW)[0]["delta"] == pytest.approx(3.0)


def test_a_horizon_that_rolled_forward_compares_the_two_first_weeks():
    """The case A9 exists for: last night's run decided GW5, tonight's decides
    GW6, and each frame's own opening week is the comparable one."""
    save_components(_frame([{"code": 11, "name": "Saka", "gw": GW,
                             "ep": 5.0}]), GW)
    save_components(_frame([{"code": 11, "name": "Saka", "gw": GW + 1,
                             "ep": 6.2}]), GW)
    assert ep_movers(GW)[0]["delta"] == pytest.approx(1.2)


@pytest.mark.parametrize("payload", ["garbage", ""])
def test_an_unreadable_predecessor_is_none_not_an_exception(payload):
    save_components(BEFORE, GW)
    save_components(AFTER, GW)
    prev_components_path(GW).write_text(payload)
    assert ep_movers(GW) is None


def test_a_predecessor_with_no_ep_column_is_none():
    save_components(BEFORE, GW)
    save_components(AFTER, GW)
    BEFORE.drop(columns=["ep"]).to_parquet(prev_components_path(GW),
                                           index=False)
    assert ep_movers(GW) is None


def test_a_missing_current_file_is_none():
    assert ep_movers(999) is None


def test_nothing_moving_is_an_empty_list_not_none():
    """The other half of A9: once there is a predecessor, "nothing moved" is
    a claim the payload is entitled to make."""
    save_components(BEFORE, GW)
    save_components(BEFORE, GW)
    assert ep_movers(GW) == []
```

- [ ] **Implement the copy and the diff.** In `src/gaffer/artifacts.py`, add `import shutil` to the imports and replace `save_components` (L106-111) with:

```python
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
```

and append at the end of the module:

```python
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
```

- [ ] **Write the endpoint test.** Create `tests/test_web_advice_movers.py`:

```python
"""``ep_movers`` on ``/api/advice/diff``: additive, and honestly absent.

The endpoint's existing contract is that it is never an error, so the new
fields have to survive every path the old ones already survive — including the
one where ``available`` is false. That case is the interesting one: a first
run of the week is exactly when a retrain happened, so the movers can be
non-empty while there is no plan diff at all (plan A10).
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import (COMPONENT_COLS, append_advice_history,
                              save_components)
from gaffer.web.app import create_app

GW = 5


def _frame(eps: dict[int, float]) -> pd.DataFrame:
    out = pd.DataFrame([{"code": code, "name": f"P{code}", "gw": GW,
                         "ep": ep} for code, ep in eps.items()])
    for col in COMPONENT_COLS:
        if col not in out.columns:
            out[col] = float("nan")
    return out[COMPONENT_COLS]


ADVICE = {"gw": GW, "buys": [], "sells": [], "expected_pts": 60.0,
          "captain": {"code": 11, "name": "P11"}}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    (tmp_path / f"reports/gw{GW}-advice.json").write_text(json.dumps(ADVICE))
    return TestClient(create_app())


def test_no_predecessor_is_a_null_count_not_a_zero(client):
    """The first run after this cycle merges says nothing rather than
    claiming a quiet retrain."""
    save_components(_frame({11: 5.0}), GW)
    body = client.get(f"/api/advice/diff?gw={GW}").json()
    assert body["ep_movers"] == []
    assert body["ep_movers_count"] is None


def test_a_second_run_reports_what_moved(client):
    save_components(_frame({11: 5.0, 22: 7.0}), GW)
    save_components(_frame({11: 6.4, 22: 7.1}), GW)
    body = client.get(f"/api/advice/diff?gw={GW}").json()
    assert body["ep_movers_count"] == 1
    assert body["ep_movers"][0]["name"] == "P11"
    assert body["ep_movers"][0]["delta"] == pytest.approx(1.4)


def test_a_retrain_that_moved_nobody_is_a_count_of_zero(client):
    save_components(_frame({11: 5.0}), GW)
    save_components(_frame({11: 5.0}), GW)
    body = client.get(f"/api/advice/diff?gw={GW}").json()
    assert body["ep_movers"] == [] and body["ep_movers_count"] == 0


def test_the_movers_ride_a_first_run_of_the_week(client):
    """A10: ``available`` is false and there is still something true to
    say."""
    save_components(_frame({11: 5.0}), GW)
    save_components(_frame({11: 6.4}), GW)
    body = client.get(f"/api/advice/diff?gw={GW}").json()
    assert body["available"] is False
    assert body["ep_movers_count"] == 1


def test_the_movers_ride_a_full_diff_too(client):
    save_components(_frame({11: 5.0}), GW)
    save_components(_frame({11: 6.4}), GW)
    append_advice_history(ADVICE, GW)
    append_advice_history({**ADVICE, "expected_pts": 62.0}, GW)
    body = client.get(f"/api/advice/diff?gw={GW}").json()
    assert body["available"] is True and body["changed"] is True
    assert body["ep_movers_count"] == 1


def test_no_advice_at_all_is_still_not_an_error(client, tmp_path):
    (tmp_path / f"reports/gw{GW}-advice.json").unlink()
    body = client.get("/api/advice/diff").json()
    assert body["available"] is False and body["ep_movers"] == []


def test_a_corrupt_predecessor_is_a_null_count_not_a_500(client, tmp_path):
    from gaffer.artifacts import prev_components_path

    save_components(_frame({11: 5.0}), GW)
    save_components(_frame({11: 6.4}), GW)
    prev_components_path(GW).write_text("garbage")
    body = client.get(f"/api/advice/diff?gw={GW}").json()
    assert body["ep_movers_count"] is None
```

- [ ] **Extend the schema.** In `src/gaffer/web/schemas.py`, add before `AdviceDiff`:

```python
class EpMover(BaseModel):
    """One player the newest retrain moved, in the gameweek being decided."""

    code: int
    name: str
    ep_prev: float
    ep_now: float
    delta: float
```

and append to `AdviceDiff`:

```python
    ep_movers: list[EpMover] = Field(default_factory=list)
    """Players whose expected points moved between the two newest component
    breakdowns. Independent of ``available``: a first run of the week has no
    plan to diff and may still have a retrain to report (plan A10)."""
    ep_movers_count: int | None = None
    """How many moved, or ``None`` when there is no predecessor breakdown to
    compare against. ``None`` and ``0`` are different claims — "we have not
    retrained since you looked" against "the retrain changed nothing" — and
    the strip renders only the second."""
```

- [ ] **Serve them.** In `src/gaffer/web/routers/advice.py`, extend the `gaffer.artifacts` import with `ep_movers` and rewrite `diff` (L122-155) so the movers are computed once, before every early return:

```python
@router.get("/diff", response_model=AdviceDiff)
def diff(gw: int | None = None) -> AdviceDiff:
    """The "since last run" strip: this run against the one before it.

    Same gameweek only. Re-running on Friday after the press conferences is
    the case this exists for, and comparing Friday's GW5 plan with last week's
    GW4 plan would answer a question nobody asked.

    Never an error. A first run of the week, a wiped ``reports/`` directory
    and a history file that will not parse all land in the same place: the
    strip is not shown, and the rest of This Week renders exactly as it did.

    The EP movers are computed before every one of those exits, because they
    are not about the plan at all — they are about the *model*, and a first
    run of the week is exactly when a retrain happened (plan A10).
    """
    target = gw if gw is not None else latest_gw()
    if target is None:
        return AdviceDiff(gw=0, available=False)
    movers = ep_movers(int(target))
    extra = {"ep_movers": movers or [],
             "ep_movers_count": None if movers is None else len(movers)}
    files = advice_history_files(int(target))
    if len(files) < 2:
        return AdviceDiff(gw=int(target), available=False, **extra)
    previous_path, current_path = files[-2], files[-1]
    try:
        previous = json.loads(previous_path.read_text())
        current = json.loads(current_path.read_text())
    except (OSError, ValueError) as exc:
        # OSError as well as ValueError: the file was listed a moment ago, so
        # a rerun rotating history underneath the read, or a permission the
        # server lost, is exactly as much of a "no diff to show" as malformed
        # JSON is — and the strip promises never to be an error.
        print(f"advice history unreadable, no diff shown: {exc}")
        return AdviceDiff(gw=int(target), available=False, **extra)
    out = diff_advice(previous, current)
    return AdviceDiff(
        gw=int(target), available=True,
        previous_at=previous_path.stem.partition("-")[2],
        current_at=current_path.stem.partition("-")[2], **out, **extra)
```

- [ ] **Extend the frontend type.** In `frontend/src/types.ts`, add before `AdviceDiff`:

```ts
export interface EpMover {
  code: number
  name: string
  ep_prev: number
  ep_now: number
  delta: number
}
```

and inside `AdviceDiff`, after `expected_pts_delta`:

```ts
  ep_movers: EpMover[]
  /** null when there is no predecessor breakdown — not the same as 0. */
  ep_movers_count: number | null
```

- [ ] **Write the frontend test.** Add to `frontend/src/hubs/this-week/WhyPanel.test.tsx`:

```tsx
describe('the retrain movers line', () => {
  it('names the count and the top three', async () => {
    server.use(http.get('/api/advice/diff', () => HttpResponse.json({
      ...EMPTY_DIFF, available: true, changed: true, ep_movers_count: 5,
      ep_movers: [
        { code: 1, name: 'Saka', ep_prev: 5.0, ep_now: 6.4, delta: 1.4 },
        { code: 2, name: 'Rice', ep_prev: 4.0, ep_now: 3.1, delta: -0.9 },
        { code: 3, name: 'Gvardiol', ep_prev: 4.0, ep_now: 4.7, delta: 0.7 },
        { code: 4, name: 'Wirtz', ep_prev: 4.0, ep_now: 4.6, delta: 0.6 },
        { code: 5, name: 'Isak', ep_prev: 4.0, ep_now: 4.6, delta: 0.6 },
      ],
    })))
    render(<WhyPanel gw={5} codes={[]} />)
    const line = await screen.findByText(/5 players moved/)
    expect(line.textContent).toContain('Saka')
    expect(line.textContent).toContain('Gvardiol')
    expect(line.textContent).not.toContain('Isak')
  })

  it('shows the strip on a first run of the week when only movers exist',
     async () => {
    // A10: `available` is false, so the old condition hid a true statement.
    server.use(http.get('/api/advice/diff', () => HttpResponse.json({
      ...EMPTY_DIFF, available: false, ep_movers_count: 1,
      ep_movers: [
        { code: 1, name: 'Saka', ep_prev: 5.0, ep_now: 6.4, delta: 1.4 }],
    })))
    render(<WhyPanel gw={5} codes={[]} />)
    expect(await screen.findByText(/1 player moved/)).toBeInTheDocument()
    // and none of the ornaments that only make sense against a previous run
    expect(screen.queryByText(/xPts$/)).not.toBeInTheDocument()
  })

  it('says nothing about movers when there is no predecessor', async () => {
    server.use(http.get('/api/advice/diff', () => HttpResponse.json({
      ...EMPTY_DIFF, available: true, changed: true,
      ep_movers_count: null, ep_movers: [],
    })))
    render(<WhyPanel gw={5} codes={[]} />)
    expect(await screen.findByText(/Since last run/)).toBeInTheDocument()
    expect(screen.queryByText(/moved/)).not.toBeInTheDocument()
  })

  it('says nothing when the retrain moved nobody', async () => {
    server.use(http.get('/api/advice/diff', () => HttpResponse.json({
      ...EMPTY_DIFF, available: true, changed: true,
      ep_movers_count: 0, ep_movers: [],
    })))
    render(<WhyPanel gw={5} codes={[]} />)
    expect(screen.queryByText(/moved/)).not.toBeInTheDocument()
  })
})
```

(Define `EMPTY_DIFF` beside the file's existing fixtures as an `AdviceDiff` with every list empty, `ep_movers: []` and `ep_movers_count: null`, and extend the file's default handler with the two new fields so the existing tests still typecheck.)

- [ ] **Implement the strip.** In `frontend/src/hubs/this-week/WhyPanel.tsx`, add the movers clause to `DiffStrip`'s `bits` after the chip clauses (L31) and guard the two `available`-only ornaments:

```tsx
  if (diff.ep_movers.length > 0) {
    const named = diff.ep_movers.slice(0, 3).map((m) => (
      `${m.name} ${m.delta >= 0 ? '+' : ''}${m.delta.toFixed(1)}`)).join(', ')
    const n = diff.ep_movers_count ?? diff.ep_movers.length
    bits.push(`${n} player${n === 1 ? '' : 's'} moved `
      + `${EP_MOVER_THRESHOLD} xPts or more in the retrain — ${named}`)
  }
```

with `const EP_MOVER_THRESHOLD = 0.5` beside it and a comment naming `artifacts.EP_MOVER_THRESHOLD` as the server-side constant it mirrors. Then in the returned markup, `{diff.previous_at}` becomes `{diff.available ? diff.previous_at : 'since the last retrain'}`, the header stays "Since last run", and the delta span is wrapped:

```tsx
        {diff.available && (
          <span className={`num ${TONE_CLASS[toneOf(delta)]}`}>
            {fmtDelta(delta)} xPts
          </span>
        )}
```

Finally, L154's condition widens:

```tsx
      {diff && ((diff.available && diff.changed) || diff.ep_movers.length > 0)
        && <DiffStrip diff={diff} />}
```

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_ep_movers.py tests/test_artifacts.py \
  tests/test_web_advice.py tests/test_web_advice_movers.py \
  tests/test_advise.py
cd frontend && npx tsc --noEmit \
  && npx vitest run src/hubs/this-week/WhyPanel.test.tsx
```

`tests/test_advise.py` is protected and is run — not edited — because `save_components` is on the advise path and its contract must be unchanged.

- [ ] **Commit.**

```bash
git add src/gaffer/artifacts.py tests/test_ep_movers.py \
  src/gaffer/web/routers/advice.py src/gaffer/web/schemas.py \
  tests/test_web_advice_movers.py frontend/src/types.ts \
  frontend/src/hubs/this-week/WhyPanel.tsx \
  frontend/src/hubs/this-week/WhyPanel.test.tsx && git commit -m "$(cat <<'EOF'
feat: name the players the retrain moved

One bounded predecessor components file and a first-gameweek join. A missing
predecessor is a null count, not a zero: the first run after this merges says
nothing rather than claiming a quiet retrain.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 7 — the Digest card on This Week

**Files:**
- Create `src/gaffer/web/routers/digest.py`
- Create `tests/test_web_digest.py`
- Modify `src/gaffer/web/schemas.py`
- Modify `src/gaffer/web/app.py`
- Modify `frontend/src/types.ts`
- Create `frontend/src/hubs/this-week/DigestCard.tsx`
- Create `frontend/src/hubs/this-week/DigestCard.test.tsx`
- Modify `frontend/src/hubs/ThisWeek.tsx`

- [ ] **Write the failing test.** Create `tests/test_web_digest.py`:

```python
"""``GET /api/digest``: whichever digest is newest, or an honest nothing."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from gaffer import artifacts
from gaffer.web.app import create_app

FRIDAY = {"kind": "friday", "generated_at": "2026-08-28T17:00:00+00:00",
          "gw": 5, "headline": "GW5: captain Haaland, 1 transfer.",
          "sections": [{"key": "move", "title": "The plan",
                        "bits": ["Haaland in, Rice out"]}]}
TUESDAY = {"kind": "tuesday", "generated_at": "2026-09-01T09:30:00+00:00",
           "gw": 4, "headline": "GW4: you 58, model 63.",
           "sections": [{"key": "verdict", "title": "GW4",
                         "bits": ["You scored 58."]}]}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    return TestClient(create_app())


def _write(kind, payload):
    (artifacts.REPORTS / f"digest_{kind}.json").write_text(
        json.dumps(payload))


def test_no_digest_at_all_is_an_unavailable_panel(client):
    body = client.get("/api/digest").json()
    assert body["available"] is False and body["digest"] is None


def test_one_digest_is_served_whole(client):
    _write("friday", FRIDAY)
    body = client.get("/api/digest").json()
    assert body["available"] is True
    assert body["digest"]["headline"] == FRIDAY["headline"]
    assert body["digest"]["sections"][0]["bits"] == ["Haaland in, Rice out"]


def test_the_newer_of_the_two_wins(client):
    """A11: the artifact's own timestamp is a fact and the browser's clock is
    not."""
    _write("friday", FRIDAY)
    _write("tuesday", TUESDAY)
    assert client.get("/api/digest").json()["digest"]["kind"] == "tuesday"


def test_a_kind_can_be_pinned(client):
    _write("friday", FRIDAY)
    _write("tuesday", TUESDAY)
    assert client.get("/api/digest?kind=friday").json()["digest"]["kind"] \
        == "friday"


def test_pinning_a_kind_that_has_never_run_is_unavailable_not_a_fallback(
        client):
    _write("tuesday", TUESDAY)
    body = client.get("/api/digest?kind=friday").json()
    assert body["available"] is False


def test_an_unknown_kind_is_a_422_naming_the_two(client):
    response = client.get("/api/digest?kind=wednesday")
    assert response.status_code == 422
    assert "friday" in response.json()["detail"]


def test_a_corrupt_artifact_is_unavailable_not_a_500(client):
    (artifacts.REPORTS / "digest_friday.json").write_text("{not json")
    assert client.get("/api/digest").json()["available"] is False


def test_a_digest_missing_its_timestamp_still_serves(client):
    """A hand-edited or older artifact sorts last rather than crashing the
    comparison."""
    _write("friday", {k: v for k, v in FRIDAY.items()
                      if k != "generated_at"})
    body = client.get("/api/digest").json()
    assert body["available"] is True
    assert body["digest"]["generated_at"] == ""
```

- [ ] **Add the schemas.** Append to `src/gaffer/web/schemas.py`:

```python
class DigestSection(BaseModel):
    """One block of a digest. ``bits`` is prose the client joins.

    The DiffStrip idiom: clauses assembled server-side, rendered by joining
    them, so there is no markdown dependency anywhere in the client. A section
    with no bits never reaches here — the builder drops it (plan A5).
    """

    key: str
    title: str
    bits: list[str] = Field(default_factory=list)


class Digest(BaseModel):
    kind: str
    generated_at: str = ""
    gw: int | None = None
    headline: str
    sections: list[DigestSection] = Field(default_factory=list)


class DigestPanel(BaseModel):
    """The newest digest, or a stated absence.

    ``available`` false covers all three ways there is nothing to show — never
    run, deleted, unparseable — because the card's empty state says the same
    sentence for each of them: press the button, or wait for Friday.
    """

    available: bool
    digest: Digest | None = None
```

- [ ] **Implement the router.** Create `src/gaffer/web/routers/digest.py`:

```python
"""``GET /api/digest`` — the newest of the two banked digests.

Newest-wins rather than day-of-week-wins (plan A11): the artifact's own
``generated_at`` is a fact, the browser's clock is not, and a user who presses
**Tuesday debrief** on a Saturday should see the thing they just made.

Nothing here builds a digest. Building one reads seven files and can take a
second; a GET on a page load may not. The card renders what the schedule — or
a button — has already banked, and its empty state says so.
"""

from __future__ import annotations

from fastapi import APIRouter

from gaffer.digest import DIGEST_KINDS, load_digest
from gaffer.errors import GafferError
from gaffer.web.schemas import Digest, DigestPanel

router = APIRouter(prefix="/api", tags=["digest"])


@router.get("/digest", response_model=DigestPanel)
def digest(kind: str | None = None) -> DigestPanel:
    if kind is not None and kind not in DIGEST_KINDS:
        raise GafferError(
            f"unknown digest kind {kind!r} — expected one of "
            f"{', '.join(DIGEST_KINDS)}")
    kinds = (kind,) if kind is not None else DIGEST_KINDS
    found = [payload for payload in (load_digest(k) for k in kinds)
             if payload is not None]
    if not found:
        return DigestPanel(available=False)
    # An artifact with no timestamp sorts last rather than raising: a
    # hand-edited or older file is still worth showing when it is the only
    # one there is.
    newest = max(found, key=lambda p: str(p.get("generated_at") or ""))
    try:
        return DigestPanel(available=True, digest=Digest(**newest))
    except Exception as exc:  # noqa: BLE001 — a card is never worth a 500
        print(f"digest panel: artifact does not fit the schema ({exc})")
        return DigestPanel(available=False)
```

- [ ] **Register it.** In `src/gaffer/web/app.py`, add `digest` to the router import tuple and include it after `components`:

```python
    app.include_router(digest.router)
```

- [ ] **Add the frontend types.** In `frontend/src/types.ts`, append:

```ts
export interface DigestSection {
  key: string
  title: string
  /** Clauses the card joins — no markdown anywhere in this feature. */
  bits: string[]
}

export interface Digest {
  kind: string
  generated_at: string
  gw: number | null
  headline: string
  sections: DigestSection[]
}

export interface DigestPanel {
  available: boolean
  digest: Digest | null
}
```

- [ ] **Write the card's test.** Create `frontend/src/hubs/this-week/DigestCard.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '../../test/server'
import DigestCard from './DigestCard'

const DIGEST = {
  available: true,
  digest: {
    kind: 'friday', generated_at: '2026-08-28T17:00:00+00:00', gw: 5,
    headline: 'GW5: captain Haaland, 1 transfer.',
    sections: [
      { key: 'move', title: 'The plan',
        bits: ['Haaland in, Rice out', 'Captain Haaland.'] },
      { key: 'movers', title: 'Prices tonight',
        bits: ['Saka may rise tonight (98%)'] },
    ],
  },
}

describe('DigestCard', () => {
  it('renders the headline and every section', async () => {
    server.use(http.get('/api/digest', () => HttpResponse.json(DIGEST)))
    render(<DigestCard />)
    expect(await screen.findByText(DIGEST.digest.headline))
      .toBeInTheDocument()
    expect(screen.getByText('The plan')).toBeInTheDocument()
    expect(screen.getByText('Prices tonight')).toBeInTheDocument()
  })

  it('joins each section\'s bits into one sentence', async () => {
    server.use(http.get('/api/digest', () => HttpResponse.json(DIGEST)))
    render(<DigestCard />)
    expect(await screen.findByText(/Haaland in, Rice out.*Captain Haaland/))
      .toBeInTheDocument()
  })

  it('names which digest it is and when it was made', async () => {
    server.use(http.get('/api/digest', () => HttpResponse.json(DIGEST)))
    render(<DigestCard />)
    expect(await screen.findByText(/Friday/)).toBeInTheDocument()
  })

  it('offers the two buttons when there is no digest yet', async () => {
    server.use(http.get('/api/digest',
                        () => HttpResponse.json({ available: false,
                                                  digest: null })))
    render(<DigestCard />)
    expect(await screen.findByText(/No digest yet/)).toBeInTheDocument()
  })

  it('renders nothing at all when the endpoint is down', async () => {
    // The card is decoration on a page that already has its advice: a failure
    // is silence, never an error state above the recommended moves.
    server.use(http.get('/api/digest', () => HttpResponse.error()))
    const { container } = render(<DigestCard />)
    await new Promise((r) => { setTimeout(r, 0) })
    expect(container.textContent).toBe('')
  })
})
```

- [ ] **Implement the card.** Create `frontend/src/hubs/this-week/DigestCard.tsx`:

```tsx
import { useCallback, useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import { Card, JobButton } from '../../kit'
import type { DigestPanel } from '../../types'

const KIND_LABEL: Record<string, string> = {
  friday: 'Friday briefing',
  tuesday: 'Tuesday debrief',
}

/**
 * The newest banked digest, rendered as prose.
 *
 * Self-fetching on `PensSection`'s pattern, and deliberately silent on
 * failure: This Week already has its advice by the time this mounts, and a
 * missing digest must never put an error above the recommended moves.
 *
 * The card renders what the schedule banked — it never builds one, because
 * building reads seven files and a page load cannot wait for that. The two
 * job buttons are how a user builds one on demand.
 */
export default function DigestCard() {
  const [panel, setPanel] = useState<DigestPanel | null>(null)

  const load = useCallback(() => {
    apiGet<DigestPanel>('/api/digest').then(setPanel).catch(() => {})
  }, [])
  useEffect(load, [load])

  if (panel === null) return null

  const buttons = (
    <div className="flex flex-wrap gap-2">
      <JobButton kind="digest-friday" onDone={load} />
      <JobButton kind="digest-tuesday" onDone={load} />
    </div>
  )

  if (!panel.available || panel.digest === null) {
    return (
      <Card title="Digest" className="mb-4" action={buttons}>
        <p className="text-text-muted">
          No digest yet — the Friday briefing runs at 17:00 and the Tuesday
          debrief at 09:30, or build one now.
        </p>
      </Card>
    )
  }

  const { digest } = panel
  const stamp = digest.generated_at
    ? new Date(digest.generated_at).toLocaleString()
    : ''
  return (
    <Card
      title="Digest"
      className="mb-4"
      action={(
        <div className="flex flex-wrap items-baseline gap-3">
          <span className="text-text-muted">
            {KIND_LABEL[digest.kind] ?? digest.kind}
            {stamp && ` · ${stamp}`}
          </span>
          {buttons}
        </div>
      )}
    >
      <p className="text-text">{digest.headline}</p>
      <dl className="mt-3 space-y-2">
        {digest.sections.map((section) => (
          <div key={section.key}>
            <dt className="label">{section.title}</dt>
            {/* The bits[] prose idiom: the server assembled the clauses and
                the client joins them, which is why nothing in this feature
                needs a markdown renderer. */}
            <dd className="text-text-secondary">{`${section.bits.join('. ')}.`}</dd>
          </div>
        ))}
      </dl>
    </Card>
  )
}
```

- [ ] **Place it on the page.** In `frontend/src/hubs/ThisWeek.tsx`, add `import DigestCard from './this-week/DigestCard'` beside the other card imports (L11-17) and insert it immediately after the `MovesCard` block (L231-233):

```tsx
      <div className="mb-4">
        <MovesCard buys={advice.buys} sells={advice.sells} hits={advice.hits} />
      </div>
      {/* The plan, then the week around the plan. */}
      <DigestCard />
      <WhyPanel gw={data.gw} codes={squad.map((r) => r.code)} />
```

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_web_digest.py tests/test_digest.py
cd frontend && npx tsc --noEmit \
  && npx vitest run src/hubs/this-week/DigestCard.test.tsx \
       src/hubs/ThisWeek.test.tsx
```

- [ ] **Commit.**

```bash
git add src/gaffer/web/routers/digest.py tests/test_web_digest.py \
  src/gaffer/web/schemas.py src/gaffer/web/app.py frontend/src/types.ts \
  frontend/src/hubs/this-week/DigestCard.tsx \
  frontend/src/hubs/this-week/DigestCard.test.tsx \
  frontend/src/hubs/ThisWeek.tsx && git commit -m "$(cat <<'EOF'
feat: the Digest card on This Week

Newest of the two artifacts, rendered as prose from bits[] — no markdown
dependency — with the two job buttons for building one on demand.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 8 — the degradation rails (gate G2)

**Files:**
- Create `tests/test_v8f_degradation.py`

Every rail here is a state a real machine reaches: a full disk on a Tuesday night, a `reports/` directory a user cleaned out, a Friday with no network, a clone that has never solved. The suite exists so that none of them is a traceback in a launchd log.

- [ ] **Write it.** Create `tests/test_v8f_degradation.py`:

```python
"""v8f degradation rails (gate G2).

Five stores this cycle touches and one schedule it adds to, each asked the
same question: what happens on the day it is not there? The answer has to be
the same every time — a printed line, a smaller payload, an absent card — and
never an exception out of a scheduled job or a 500 out of a page.

The last two rails are pins rather than degradations. The job-kind count and
the config-key count moved this cycle, deliberately and with authorization
(the plan's Task 5 STOP), and asserting the new numbers from this cycle's own
file is what makes the *next* cycle's accidental addition fail in its own
suite rather than in five older ones.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer import artifacts
from gaffer.data import store
from gaffer.web.app import create_app

GW = 5

PLAYERS = pd.DataFrame({
    "code": [11, 22], "name": ["Saka", "Haaland"],
    "position": ["MID", "FWD"], "team_code": [3, 4],
    "now_cost": [101, 150], "selected_by_percent": [40.0, 60.0],
    "price_change_percent": [98.0, 1.0],
    "price_change_calibrating": [False, False],
})


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    (tmp_path / "data" / "live").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    return tmp_path, TestClient(create_app())


# --- rail 1: an unwritable price log ---------------------------------

def test_an_unwritable_price_log_costs_the_day_and_nothing_else(app,
                                                                capsys):
    """The nightly job at 23:15 has already printed the user's answer by the
    time the bank runs, so a full disk must be a line, not an exception."""
    from gaffer.price_log import bank_prices

    _, _client = app
    assert bank_prices(PLAYERS.drop(columns=["now_cost"])) is None
    assert "price log not written" in capsys.readouterr().out


def test_a_price_log_that_was_never_written_reads_as_empty(app):
    from gaffer.price_log import PRICE_LOG_COLS, load_price_log

    assert load_price_log().empty
    assert list(load_price_log().columns) == PRICE_LOG_COLS


# --- rail 2: the watchlist ------------------------------------------

@pytest.mark.parametrize("payload", ["{not json", "[]", '{"watchlist": 3}'])
def test_a_corrupt_watchlist_is_an_empty_one(app, payload):
    tmp_path, client = app
    (tmp_path / "reports/watchlist.json").write_text(payload)
    assert client.get("/api/watchlist").json() == {"rows": []}


def test_a_corrupt_watchlist_leaves_the_explorer_alone(app):
    """The star column is a bookmark. A broken store must not blank a table
    of six hundred players."""
    tmp_path, client = app
    (tmp_path / "reports/watchlist.json").write_text("{not json")
    assert client.get("/api/players").status_code == 200


def test_a_missing_reports_directory_still_serves_the_watchlist(app):
    tmp_path, client = app
    (tmp_path / "reports").rmdir()
    assert client.get("/api/watchlist").json() == {"rows": []}


# --- rail 3: the movers card ----------------------------------------

def test_no_player_snapshot_is_an_unavailable_movers_panel(app):
    tmp_path, client = app
    (tmp_path / "data/live/players.parquet").unlink()
    body = client.get("/api/prices/movers").json()
    assert body["available"] is False and body["rows"] == []


def test_nothing_watched_is_available_and_empty_not_unavailable(app):
    """"You are watching nobody" is a working card with an empty state; it is
    not a broken one."""
    _, client = app
    body = client.get("/api/prices/movers").json()
    assert body["available"] is True and body["rows"] == []


# --- rail 4: the digests --------------------------------------------

def test_a_friday_with_nothing_on_disk_still_writes_a_briefing(app):
    from gaffer.digest import load_digest, run_digest

    _, _client = app
    payload = run_digest("friday", notify=False)
    assert payload is not None
    assert load_digest("friday") is not None
    # A5: no advice, so no move section, and the headline says what to run.
    assert "move" not in {s["key"] for s in payload["sections"]}
    assert "gaffer advise" in payload["headline"]


def test_a_tuesday_with_no_ledger_says_the_season_is_unreviewed(app):
    from gaffer.digest import run_digest

    _, _client = app
    payload = run_digest("tuesday", notify=False)
    assert payload is not None and payload["gw"] is None
    assert "not been reviewed" in payload["headline"]


def test_notify_false_makes_no_osascript_call(app, monkeypatch):
    """The rail that matters: not a suppressed call — no call."""
    from gaffer import digest as mod

    calls = []
    monkeypatch.setattr(mod.subprocess, "run",
                        lambda *a, **k: calls.append(a))
    mod.run_digest("friday", notify=False)
    assert calls == []


def test_a_missing_osascript_binary_is_not_a_failed_job(app, monkeypatch,
                                                        capsys):
    from gaffer import digest as mod

    monkeypatch.setattr(mod.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(
                            FileNotFoundError("osascript")))
    assert mod.run_digest("friday", notify=True) is not None
    assert "notification not shown" in capsys.readouterr().out


def test_the_digest_endpoint_is_never_a_500(app):
    tmp_path, client = app
    (tmp_path / "reports/digest_friday.json").write_text("{not json")
    assert client.get("/api/digest").json()["available"] is False


def test_the_digest_writes_nothing_but_its_own_artifact(app):
    """A6, asserted as a source screen: the review job holds a lock on the
    ledger at 09:00 and the debrief runs at 09:30."""
    import inspect

    import gaffer.digest as mod

    src = inspect.getsource(mod)
    for forbidden in ("append_ledger", "append_sim_history", "run_review",
                      "save_availability", "save_components",
                      "append_snapshot", "save_solve_state"):
        assert forbidden not in src, forbidden


# --- rail 5: the retrain diff ---------------------------------------

def test_no_predecessor_breakdown_is_an_absent_claim_not_a_quiet_one(app):
    """A9. The first advise run after this cycle merges must say nothing."""
    from gaffer.artifacts import COMPONENT_COLS, ep_movers, save_components

    tmp_path, client = app
    frame = pd.DataFrame([{"code": 11, "name": "Saka", "gw": GW, "ep": 5.0}])
    for col in COMPONENT_COLS:
        if col not in frame.columns:
            frame[col] = float("nan")
    save_components(frame[COMPONENT_COLS], GW)
    (tmp_path / f"reports/gw{GW}-advice.json").write_text(
        json.dumps({"gw": GW, "buys": [], "sells": []}))
    assert ep_movers(GW) is None
    assert client.get(f"/api/advice/diff?gw={GW}").json()["ep_movers_count"] \
        is None


def test_a_failed_predecessor_copy_never_fails_an_advise_run(app,
                                                             monkeypatch):
    from gaffer.artifacts import (COMPONENT_COLS, components_path,
                                  save_components)

    frame = pd.DataFrame([{"code": 11, "name": "Saka", "gw": GW, "ep": 5.0}])
    for col in COMPONENT_COLS:
        if col not in frame.columns:
            frame[col] = float("nan")
    save_components(frame[COMPONENT_COLS], GW)
    monkeypatch.setattr("gaffer.artifacts.shutil.copyfile",
                        lambda *a: (_ for _ in ()).throw(OSError("full")))
    assert save_components(frame[COMPONENT_COLS], GW) == components_path(GW)


# --- rail 6: the pins v8f moved, asserted from v8f's own file -------

def test_v8f_adds_exactly_two_job_kinds():
    """The pin six other suites assert, asserted a seventh time from this
    cycle's own file, so a v8h kind fails here rather than in somebody
    else's."""
    from gaffer.web.job_kinds import JOB_KINDS

    assert len(JOB_KINDS) == 12
    assert "digest-friday" in JOB_KINDS and "digest-tuesday" in JOB_KINDS


def test_v8f_added_exactly_one_config_key():
    """Spec §2: ``[digest] notify`` only. A second key would be a switch
    nobody finds and a degraded state nobody tests."""
    import dataclasses

    from gaffer.config import Config

    names = {f.name for f in dataclasses.fields(Config)}
    assert "digest_notify" in names
    assert not [n for n in names
                if ("watch" in n or "digest" in n or "price_log" in n)
                and n != "digest_notify"]
    # 48 keys as of v8f. Any change to this number is a config key a later
    # cycle had no business adding without moving the pin deliberately.
    assert len(names) == 48


# --- rail 7: protected ordering, forward ----------------------------

def test_the_advice_payloads_watch_set_is_still_squad_plus_plan():
    """advise.py is protected, so the payload's alerts stay narrow and the
    *web* card carries the wider set. A future cycle that widened one without
    the other would give the user two different answers to one question."""
    import inspect

    from gaffer import advise

    src = inspect.getsource(advise.run_advise)
    assert "watch = set(first.buys + first.sells + owned_now)" in src


def test_the_availability_pass_still_ends_with_the_override():
    """v8e's ordering pin, carried forward: v8f touches none of that path and
    the rail says so out loud rather than by omission."""
    import inspect

    from gaffer.models import availability

    assert "_override_first_gw(out)" in inspect.getsource(
        availability.apply_availability)
```

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_v8f_degradation.py
uv run pytest -q tests/test_v6_degradation.py tests/test_v8b_degradation.py \
  tests/test_v8c_degradation.py tests/test_v8d_degradation.py \
  tests/test_v8e_degradation.py tests/test_v8g_degradation.py
```

If `test_the_advice_payloads_watch_set_is_still_squad_plus_plan` fails, read `advise.py:858` and pin the line that is actually there — do **not** edit `advise.py`.

- [ ] **Commit.**

```bash
git add tests/test_v8f_degradation.py && git commit -m "$(cat <<'EOF'
test: v8f degradation rails

Five stores and one schedule, each asked what happens on the day it is not
there. Plus the two pins this cycle moved, asserted from its own file.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 9 — the documentation

**Files:**
- Modify `README.md`

- [ ] **Update the artifact and store list** (around L505-517), adding four entries in the existing voice:

```markdown
- `data/live/price_log.parquet` — one row per player per UTC day: FPL's own
  price predictor reading, banked by the nightly `prices` job. Every player,
  not only the ones near a threshold — the row worth having in February is
  the one that was not an alert in August. Read by nobody yet; a season of it
  is what a price-timing term would need.
- `reports/watchlist.json` — starred players, up to a hundred, each with an
  optional note. Widens the movers card's watch set and adds a section to the
  Friday digest, and is read by nothing that solves or trains.
- `reports/digest_friday.json` / `reports/digest_tuesday.json` — the newest
  briefing and debrief, replace-on-write. A section whose input is missing is
  absent rather than empty.
- `reports/components_gw{N}_prev.parquet` — the previous run's component
  breakdown, one slot, kept so "since last run" can name the players the
  retrain moved rather than only saying the plan changed.
```

- [ ] **Add a Digests section** after the "Price changes" section:

```markdown
## Digests

Two scheduled summaries, each written to `reports/` and shown as a macOS
notification.

- **Friday 17:00** — `gaffer digest --kind friday`. The deadline countdown,
  the advised move and captain, watched players the news layer or a press
  conference is unhappy about, tonight's likely price changes, one
  differential from the alternatives table, and the data-staleness warning if
  there is one.
- **Tuesday 09:30** — `gaffer digest --kind tuesday`, half an hour after the
  review job. Last week's score against the model's, the worst lane and its
  label, the hindsight-XI gap, the league win probability and which way it
  moved, and the largest forecast miss.

Both appear on This Week as the **Digest** card, newest first, and both have a
button there. A section with nothing to say does not appear at all: "no data"
is a sentence about the tool, and its absence is a sentence about the season.

The notification is best-effort — it runs `osascript`, swallows every failure,
and is macOS-only. Turn it off with:

    [digest]
    notify = false
```

- [ ] **Update the Automation section** (L526-556): five plists become seven, and the schedule list gains the two digests. The removal line becomes:

```
launchctl unload ~/Library/LaunchAgents/com.gaffer.{advise,prices,snapshot,field,review,digest-friday,digest-tuesday}.plist
```

- [ ] **Update the command table** (L55): `gaffer prices` now reads "Likely price changes tonight among the 200 most-owned players; banks every player's reading to `data/live/price_log.parquet`." Add a row for `gaffer digest --kind friday|tuesday`.

- [ ] **Add the watchlist to the Players hub description** (around L204): one sentence saying the explorer's star column is a bookmark that widens the price-alert watch set and feeds the Friday digest, and claims nothing the model has to obey — the sentence that keeps a reader from confusing it with a pin.

- [ ] **Commit.**

```bash
git add README.md && git commit -m "$(cat <<'EOF'
docs: v8f — price log, watchlist, digests, retrain movers

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 10 — the gate checklist (orchestrator-run, unfilled)

CONVENTIONS.md §7: the implementer builds this and does not run it.

- [ ] **G3 first — suites, types, build, and the protected audit.**

```bash
uv run pytest -q
cd frontend && npx tsc --noEmit && npx vitest run && npm run build
```

Expect 2468 + this cycle's new tests green, and 441 + 1 skipped + this cycle's new frontend tests green.

Then the protected diff, which must show **exactly** the seven lines Task 5's STOP authorized and their comments, and nothing else:

```bash
git diff main --stat -- src/gaffer/advise.py src/gaffer/set_pieces.py \
  'src/gaffer/optimize/**' src/gaffer/web/jobs.py \
  src/gaffer/web/routers/jobs.py src/gaffer/web/routers/whatif.py \
  tests/test_advise.py tests/test_odds.py tests/test_web_jobs.py \
  scripts/s2_replay.py
# must be empty

git diff main -- tests/test_v8b_degradation.py tests/test_v8c_degradation.py \
  tests/test_v8d_degradation.py tests/test_v8e_degradation.py \
  tests/test_v8g_degradation.py
# must be exactly six changed assertion lines (four "10 -> 12", one "10 -> 12",
# one "47 -> 48") plus their comments — nothing else
```

Security ritual (CONVENTIONS.md §8): grep the whole branch diff for keys, and confirm `git show main:config.toml` fails.

- [ ] **G1 — live runs.** Each is a real command against the real season, not a fixture.

- [ ] `gaffer prices` — the alert list prints as it always did; `data/live/price_log.parquet` gains one row per player. Run it twice and confirm the row count does not double.
- [ ] `gaffer digest --kind friday` — writes `reports/digest_friday.json`, prints one line, and shows (or best-effort-skips) a notification. Open This Week and confirm the Digest card renders it.
- [ ] `gaffer digest --kind tuesday` — reflects the **real** GW1 ledger row, with its actual lanes and accuracy, not a placeholder.
- [ ] Star a player through the explorer's ☆ button, confirm he appears in `GET /api/prices/movers` with `source: "watchlist"` (if he is near a threshold) and in the next Friday briefing's flagged section.
- [ ] `gaffer advise` once: the diff strip says nothing about movers (`ep_movers_count` null). Run it again: the strip names the players that moved.
- [ ] `./scripts/install_automation.sh`, then `launchctl list | grep com.gaffer` shows seven jobs including the two digests.

- [ ] **G2 — rails.** `uv run pytest -q tests/test_v8f_degradation.py`, plus every pre-existing `test_*_degradation.py`.

- [ ] **Fill spec §4 (Outcome)** with what shipped, what did not, and any residual — and, per CONVENTIONS.md §4, transcribe the G1 evidence verbatim rather than summarising it.

---

## Notes for the implementer

- **Task order matters in two places only.** Task 4 must precede Task 5 (the job kinds import `run_digest`), and Task 2 must precede Task 3 (the movers endpoint imports `watch_targets`). Everything else is independent and can be parallelised.
- **Task 5 is the only stop-point.** If any other task finds itself wanting a config key, a job kind, or an edit inside a protected file, the plan is wrong: stop and report.
- **`advise.py` stays narrow on purpose.** The advice payload's `price_alerts` and the movers card's list are two different sets, and `tests/test_v8f_degradation.py` pins that they stay that way. Making them agree is a v8h decision, not a bug to fix mid-cycle.
