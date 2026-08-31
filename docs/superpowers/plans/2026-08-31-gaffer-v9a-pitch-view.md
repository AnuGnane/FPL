# Gaffer v9a Pitch View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** give This Week an FPL-style pitch. Shirts instead of names in boxes, the bench drawn as a bench, team identity on every card, captain and vice armbands, and a per-player next-fixture chip that says who he plays and how hard it is. Nothing trains, nothing solves, and no number on the page is recomputed — every new field is a *lookup* into something the backend already banks.

**Architecture:** two seams, both outside the model. A **cache-and-serve** seam: one new router (`src/gaffer/web/routers/assets.py`) that fetches a shirt or a photo from the official CDN once, banks the bytes under `data/live/assets/`, and serves them from disk forever after — with a bundled SVG for every failure, so the pitch renders identically with the network unplugged. And a **resolve-at-serve-time** seam: one new module (`src/gaffer/web/identity.py`) that the advice router calls to decorate the payload's player entries with team identity and the week's fixture, joining three files already on disk. On the frontend, one new kit component (`PlayerCard`) and one new hub component (`SquadPitch`), plus a segmented toggle that makes the pitch This Week's default and leaves `SquadTable` one click away, unchanged.

**Tech Stack:** Python 3.12, uv, pandas/pyarrow, FastAPI + pydantic, httpx, pytest; React 19 + TypeScript + vitest + Tailwind.

**Prerequisite:** work on branch `feat/gaffer-v9a`. Authoritative spec: `docs/superpowers/specs/2026-08-31-gaffer-v9a-pitch-view-design.md`. Measurement rules: `docs/superpowers/CONVENTIONS.md`.

```bash
git checkout main && git pull --ff-only && git checkout -b feat/gaffer-v9a
```

**Protected — must show zero diffs at the end (Task 9 audits this). This cycle authorizes no exceptions at all:**
`src/gaffer/advise.py`, `src/gaffer/set_pieces.py`, `src/gaffer/optimize/**`,
`src/gaffer/web/jobs.py`, `src/gaffer/web/routers/jobs.py`,
`src/gaffer/web/routers/whatif.py`,
`tests/test_advise.py`, `tests/test_odds.py`, `tests/test_web_jobs.py`,
**every** pre-existing `tests/test_*_degradation.py` (v6, v7*, v8a, v8b, v8c, v8d, v8e, v8f, v8g),
`scripts/s2_replay.py`.

**Import-only:** `src/gaffer/journal.py`, `src/gaffer/backtest.py`, and the whole of `src/gaffer/optimize/`. This cycle imports nothing from any of them.

`src/gaffer/advise.py` is protected and stays that way, and that has one consequence this plan states up front rather than letting a task discover it at the keyboard. **The advice payload's player entries are written by `advise.py`** — `_named()` at `advise.py:~866` emits exactly `{code, name, position, ep}` and `run_advise` writes `reports/gw{N}-advice.json` from it. Adding `team_short` there is an edit inside a protected file, so this cycle does not do it. The three new fields are resolved **at serve time** in `src/gaffer/web/identity.py` and applied by `routers/advice.py`, which is the precedent that file already sets: `with_positions` (advice.py:85-108) backfills `position` onto an advice payload written before positions existed, for exactly this reason. Two things follow and both are wins — the enrichment applies to *every* advice file already on disk without a re-solve, and the on-disk artifact's bytes do not change, so nothing that reads it needs a migration.

Zero new job kinds (the count stays 12), zero new plists, **zero new config keys**. See A7: a config key would break a count pin inside `tests/test_v8f_degradation.py`, which is protected.

If a task appears to need an edit inside a protected or import-only file, the plan is wrong: stop and report rather than editing.

**Staging rule:** every `git add` below names exact files. Never `git add -A`. Never stage `data/`, `reports/`, `models/`, `logs/`, `.claude/`, `src/gaffer/web/static/` or `config.toml`. The only binary this cycle commits is two hand-written SVGs under `src/gaffer/assets/`; no cached shirt or photo is ever staged.

**Gate rule (CONVENTIONS.md §7):** implementers build the driver and never run the gates. Task 9 is the checklist, unfilled.

**Suite baselines (measured on `main`, 2026-08-31):** 2664 python tests; 460 frontend tests + 1 skipped. Every task's final run must leave both pre-existing suites green. There is no stop-point in this cycle.

**Commit trailer — every commit:**

```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
```

---

## Ambiguities the spec left open, and how this plan settles them

Eleven things D1–D5 do not pin, decided here once so no task decides them twice.

**A1 — the new pitch is `SquadPitch`, because `PitchView` is already taken.** D3 names the new component `frontend/src/hubs/this-week/PitchView.tsx`, and there is already a `frontend/src/kit/PitchView.tsx` — a plain formation grid of bordered name boxes, exported from the kit barrel, pinned by `kit/index.test.ts:7`, and rendered on This Week today (`ThisWeek.tsx:219`). Two files called `PitchView` in one tree is a permanent tax on every reader for a one-time naming convenience.

So the new component is `frontend/src/hubs/this-week/SquadPitch.tsx`, and `kit/PitchView` is left **exactly** as it is: still exported, still tested, still pinned. It stops being rendered by This Week at Task 6 and it is not deleted — it is the smallest possible pitch primitive, the barrel test names it, and deleting kit surface to tidy up an unrelated cycle is how a v9b task discovers it needed the thing. If v9b wants one pitch component, that is v9b's decision to make with both in front of it.

**A2 — the enrichment happens at serve time, in an unprotected module, and the artifact on disk does not change.** Stated in the preamble because it is the constraint the whole backend half is shaped around. `src/gaffer/web/identity.py` is a pure read-only function of three banked files; `routers/advice.py:latest()` calls it immediately after `with_positions`, on the same payload, for the same reason.

The corollary is a rule for the whole module: **`identity.py` never raises**. A missing `fixtures_all.parquet`, a `teams.parquet` without `short_name`, a bootstrap without `team_code`, a payload whose `xi` is not a list — every one of them returns the payload it was handed, unchanged, with a printed line. This Week's advice already renders without any of these fields; a decoration that can 500 the page it decorates is worse than no decoration.

**A3 — all six player keys are enriched, not just the XI.** `routers/advice.py:PLAYER_KEYS` is `("xi", "bench", "buys", "sells", "captain", "vice")` and `identity.py` walks the same tuple `with_positions` does. The pitch only needs `xi` and `bench` this cycle, but the cost is one dict lookup per entry over a payload of roughly twenty entries, and the alternative is v9b editing this function to widen it — which is a diff in a file this cycle should leave settled. `buys` and `sells` carrying a shirt is exactly what D5's item (1) is about.

**A4 — the chip's difficulty is the ticker's number, obtained by calling the ticker.** D2 says the chip reuses `meta.py`'s odds-implied rating rather than FPL's FDR. That number is computed inside the body of `routers/meta.ticker()` (meta.py:212-266) — the odds lookup, the Elo fallback, the rate-once-from-the-home-side rule and the clamp are all local to the route function.

`identity.py` therefore **calls `meta.ticker(weeks=2)`** and indexes its cells by `(team_code, gw)`, rather than reimplementing sixty lines of Elo and Poisson arithmetic beside it. Two copies of that calculation would be two answers to "how hard is this fixture", drawn on the same page in the same colour scale, and the first week they disagreed would be a bug nobody could see. `weeks=2` rather than `1` because `ticker` slices the first *n* unfinished gameweeks and a mid-week reload can find the advice GW second in that window.

The call is wrapped: any failure means `difficulty: None` on every chip and the rest of the fixture — opponent, home, kickoff — still renders. A chip that says "MCI (H) Sat 15:00" in a neutral colour is the whole feature minus its tint. `meta.py` itself is **not** edited.

**A5 — the fixture is the first unfinished one in the advice gameweek, and both of its optional fields can be null independently.** `next_fixture` is resolved from `data/live/fixtures_all.parquet` filtered to `gw == advice_gw` and `finished` false, sorted by `kickoff_time`, first row per team.

- A team with no such row gets `next_fixture: null`, and the card says **"Blank"** — the honest word, not an empty chip and not a zero.
- A DGW keeps the first fixture and gains nothing else this cycle (D2, explicitly).
- `kickoff_utc` is the banked string passed through unparsed, and it is `str | None`: FPL publishes fixtures with a null `kickoff_time` while a date is still TBC, and a chip reading "MCI (H) TBC" is true where an invented kickoff would not be. Formatting is the client's job — the server has no business guessing the reader's timezone.
- `difficulty` is `float | None` per A4.

So `NextFixture` present with two nulls inside it is a legitimate state, and it means something different from `next_fixture: null`. The first is "he has a fixture and we know less about it than usual"; the second is "he does not play".

**A6 — team identity comes from `players.parquet` joined to `teams.parquet`, keyed on `code`.** `data/live/players.parquet` carries `code`, `team_id` and `team_code`; `data/live/teams.parquet` carries `team_id`, `code`, `name`, `short_name`. `team_code` is the number the shirt CDN wants and `short_name` is the string the card prints, so the join is player `code` → `team_code` → `short_name`.

A player absent from the snapshot, or a snapshot without a `team_code` column, gets `team_short: null` and `team_code: null` — and a null `team_code` is what makes the card draw the bundled plain shirt instead of requesting a shirt for a team that does not exist. Nulls, never a sentinel: a `team_code` of `0` would be a real request to the CDN for nothing.

**A7 — no config key, and the CDN bases are module constants.** D1's spec §2 permits `[assets] base_url` "if a CDN-base override proves necessary". It is not worth what it costs: `tests/test_v8f_degradation.py` pins the config field count, that file is on this cycle's protected list, and a new key would break a protected rail to buy a knob only the gate uses.

`SHIRT_BASE` and `PHOTO_BASE` are module constants in `routers/assets.py`. Tests monkeypatch them. G1's dead-upstream check uses the spec's own first form — kill the network and reload — which is a stronger test anyway, because it exercises the timeout path a wrong hostname does not.

**A8 — the allowlist is the banked bootstrap, and the path is never built from a string.** The endpoint is not an open proxy (spec §2). `{team_code}` and `{player_code}` are declared `int` in the route signature, so FastAPI's own path converter answers `422` to `../../etc/passwd` before any handler runs, and the cache filename is then built by interpolating a *parsed integer* — there is no code path in which a caller-supplied string reaches a filesystem path. Both halves are asserted in Task 1 and pinned again in Task 7.

On top of that, a code that is not in `players.parquet` (photos) or `teams.parquet` (shirts) is a `404` with no fetch attempted. A cold clone with no snapshot has an empty allowlist and therefore refuses everything with a `404` — deliberately, and it is the right failure: the pitch falls back to silhouettes, which is precisely the state a machine with no banked data should be in.

**A9 — a cache hit never touches the network, and a fallback is never written to disk.** The three-state contract, in order:

1. **Hit** — the file exists under `data/live/assets/`: read and serve, `Cache-Control: public, max-age=604800, immutable`. No HTTP client is constructed. Task 1 asserts this with a spy, not with a timing.
2. **Miss, fetch succeeds** — write through a temp file and `os.replace` (the store idiom, so a killed process cannot leave a truncated PNG that every later hit serves), then serve with the same long header.
3. **Miss, fetch fails or the write fails** — serve the bundled SVG with `Cache-Control: public, max-age=60` and write **nothing**. Short max-age because the failure is the transient one: the browser must come back and ask again in a minute, not cache a silhouette for a week. "Write nothing" is a rail: a fallback banked into the cache directory would be served as a hit forever, and the pitch would never recover from one bad evening.

**A10 — the fallbacks are two hand-written SVGs shipped in the package, not generated.** `src/gaffer/assets/shirt_fallback.svg` and `player_fallback.svg`, beside the JSON files that package already ships, read through `importlib.resources` exactly as `load_bootstrap_sample` reads its payload. `pyproject.toml`'s wheel `artifacts` list gains `src/gaffer/assets/*.svg` — it currently names only `*.json`, so an installed wheel would ship a package that cannot answer its own fallback.

They are `currentColor`-free and theme-neutral: a mid-grey plain shirt and a mid-grey head-and-shoulders silhouette, both on a transparent ground, both legible on the green pitch and on a card in either theme.

**A11 — the two cards on This Week become one, because the XI would otherwise be drawn twice.** This Week today renders a "Starting XI" card holding `kit/PitchView` and, below it, a "Squad" card holding `SquadTable` — the same eleven players in both, plus the bench in the second. Adding a third rendering of the XI would be absurd.

So the "Starting XI" card becomes the host: its `action` slot keeps the captain/vice/odds line and gains the segmented **Pitch | Table** toggle, its body is `SquadPitch` or `SquadTable` depending, and the separate "Squad" card is removed. `SquadTable` and its props are not touched — it is the same component with the same rows, rendered from a different parent (D3: "SquadTable is unchanged").

The toggle is component state defaulting to `'pitch'` (D3). Not `localStorage`: persisting a view preference is a real feature with a real question behind it (per-hub? per-device? does it survive a rebuild?) and inventing an answer inside a lean UI cycle is how a preference store gets built by accident. D5 is where that belongs if anyone wants it.

---

## File structure

| File | Status | Responsibility |
| --- | --- | --- |
| `src/gaffer/assets/shirt_fallback.svg` | Create | T1: the plain shirt. |
| `src/gaffer/assets/player_fallback.svg` | Create | T1: the silhouette. |
| `pyproject.toml` | Modify (L36) | T1: ship the SVGs in the wheel. |
| `src/gaffer/web/routers/assets.py` | Create | T1: `GET /api/assets/{shirt,photo}/{code}`. |
| `tests/test_web_assets.py` | Create | T1. |
| `src/gaffer/web/app.py` | Modify (L26-31 imports, L69-92 includes) | T1. |
| `src/gaffer/web/identity.py` | Create | T2: team identity + next fixture, at serve time. |
| `tests/test_web_identity.py` | Create | T2. |
| `src/gaffer/web/schemas.py` | Modify (append `NextFixture`; `PlayerRef` L73-78) | T2. |
| `src/gaffer/web/routers/advice.py` | Modify (`latest`, L111-120) | T2. |
| `tests/test_web_advice_identity.py` | Create | T2. |
| `frontend/src/types.ts` | Modify (L1-10 `PlayerRef`, append `NextFixture`) | T3. |
| `frontend/src/types.test.ts` | Create | T3: the lockstep pin. |
| `frontend/src/kit/PlayerCard.tsx` | Create | T4: the shared card. |
| `frontend/src/kit/PlayerCard.test.tsx` | Create | T4. |
| `frontend/src/kit/index.ts` | Modify (append) | T4. |
| `frontend/src/kit/index.test.ts` | Modify (L6-8) | T4. |
| `frontend/src/hubs/this-week/SquadPitch.tsx` | Create | T5: the pitch. |
| `frontend/src/hubs/this-week/SquadPitch.test.tsx` | Create | T5. |
| `frontend/src/hubs/this-week/SquadTable.tsx` | Modify (`SquadRow` L7-26) | T5: three fields. |
| `frontend/src/hubs/ThisWeek.tsx` | Modify (L3-17, L101-129, L196-228) | T6: the toggle. |
| `frontend/src/hubs/ThisWeek.test.tsx` | Modify | T6. |
| `tests/test_v9a_degradation.py` | Create | T7: G2. |
| `README.md` | Modify | T8. |
| `docs/superpowers/specs/2026-08-31-gaffer-v9a-pitch-view-design.md` | Modify (§5) | T9. |

---

## Task 1 — the asset cache: fetch once, serve from disk, never break

**Files:**
- Create `src/gaffer/assets/shirt_fallback.svg`
- Create `src/gaffer/assets/player_fallback.svg`
- Modify `pyproject.toml`
- Create `src/gaffer/web/routers/assets.py`
- Create `tests/test_web_assets.py`
- Modify `src/gaffer/web/app.py`

- [ ] **Write the failing test.** Create `tests/test_web_assets.py`:

```python
"""``/api/assets``: the image cache that must never be an open proxy and must
never break a page.

Three states and their order are the whole contract (plan A9): a hit reads
disk and constructs no HTTP client at all, a miss fetches once and banks the
bytes, and every failure serves a bundled SVG and writes nothing. The last
clause is the one with teeth — a silhouette banked into the cache would be
served as a hit forever, and one bad evening would cost the pitch its shirts
for the season.

The allowlist tests are the security half. The endpoint fetches from a third
party on a caller's say-so, so "which codes may be asked for" is answered by
the banked bootstrap and by nothing else, and the path a code turns into is
built from a parsed integer rather than from anything the caller typed.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.data import store
from gaffer.web.app import create_app
from gaffer.web.routers import assets

PLAYERS = pd.DataFrame({
    "code": [223094, 154561],
    "name": ["Haaland", "Raya"],
    "position": ["FWD", "GKP"],
    "team_id": [13, 1],
    "team_code": [43, 3],
    "now_cost": [150, 60],
})

TEAMS = pd.DataFrame({
    "team_id": [1, 13],
    "code": [3, 43],
    "name": ["Arsenal", "Man City"],
    "short_name": ["ARS", "MCI"],
})

PNG = b"\x89PNG\r\n\x1a\n" + b"fake-photo-bytes"
WEBP = b"RIFF" + b"fake-shirt-bytes"


class FakeResponse:
    def __init__(self, content: bytes, status: int = 200):
        self.content = content
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    """A clone with a banked bootstrap, an empty cache and a counted CDN."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    (tmp_path / "data" / "live").mkdir(parents=True)
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    TEAMS.to_parquet(tmp_path / "data/live/teams.parquet", index=False)
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return WEBP if "shirt" in url else PNG

    monkeypatch.setattr(assets, "_fetch", fetch)
    return tmp_path, TestClient(create_app()), calls


# --- the happy path -------------------------------------------------

def test_a_cold_shirt_is_fetched_once_and_banked(wired):
    tmp_path, client, calls = wired
    response = client.get("/api/assets/shirt/43")
    assert response.status_code == 200
    assert response.content == WEBP
    assert response.headers["content-type"] == "image/webp"
    assert len(calls) == 1
    assert (tmp_path / "data/live/assets/shirt_43.webp").read_bytes() == WEBP


def test_a_cold_photo_is_fetched_once_and_banked(wired):
    tmp_path, client, calls = wired
    response = client.get("/api/assets/photo/223094")
    assert response.status_code == 200
    assert response.content == PNG
    assert response.headers["content-type"] == "image/png"
    assert (tmp_path / "data/live/assets/photo_223094.png").read_bytes() == PNG


def test_the_keeper_shirt_is_a_different_file_and_a_different_url(wired):
    """A9: two variants of one team's shirt, so a cached outfield shirt must
    not answer a request for the keeper's."""
    tmp_path, client, calls = wired
    client.get("/api/assets/shirt/43")
    client.get("/api/assets/shirt/43?keeper=true")
    assert (tmp_path / "data/live/assets/shirt_43_1.webp").exists()
    assert len(calls) == 2
    assert calls[1].endswith("shirt_43_1-66.webp")


def test_a_hit_never_constructs_an_http_client(wired, monkeypatch):
    """The rail that matters most on a page drawing fifteen shirts: the
    second load of This Week makes zero outbound requests."""
    _tmp, client, calls = wired
    client.get("/api/assets/shirt/43")

    def forbidden(url: str) -> bytes:
        raise AssertionError(f"a cache hit refetched {url}")

    monkeypatch.setattr(assets, "_fetch", forbidden)
    assert client.get("/api/assets/shirt/43").content == WEBP
    assert len(calls) == 1


def test_a_hit_is_served_with_a_long_immutable_cache_header(wired):
    _tmp, client, _calls = wired
    client.get("/api/assets/shirt/43")
    header = client.get("/api/assets/shirt/43").headers["cache-control"]
    assert "max-age=604800" in header and "immutable" in header


# --- the fallback ---------------------------------------------------

def test_a_dead_upstream_serves_the_bundled_shirt(wired, monkeypatch):
    _tmp, client, _calls = wired
    monkeypatch.setattr(assets, "_fetch", lambda url: (_ for _ in ()).throw(
        RuntimeError("connection refused")))
    response = client.get("/api/assets/shirt/43")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/svg+xml"
    assert b"<svg" in response.content


def test_a_dead_upstream_serves_the_bundled_silhouette(wired, monkeypatch):
    _tmp, client, _calls = wired
    monkeypatch.setattr(assets, "_fetch", lambda url: (_ for _ in ()).throw(
        RuntimeError("connection refused")))
    response = client.get("/api/assets/photo/223094")
    assert response.status_code == 200
    assert b"<svg" in response.content


def test_a_fallback_carries_a_short_max_age_and_no_immutable(wired,
                                                             monkeypatch):
    """The failure is the transient one. A week-long silhouette would outlive
    the outage that caused it by six days and twenty-three hours."""
    _tmp, client, _calls = wired
    monkeypatch.setattr(assets, "_fetch", lambda url: (_ for _ in ()).throw(
        RuntimeError("connection refused")))
    header = client.get("/api/assets/shirt/43").headers["cache-control"]
    assert "max-age=60" in header and "immutable" not in header


def test_a_fallback_is_never_banked(wired, monkeypatch):
    """A9's rail: a banked silhouette would be served as a hit forever."""
    tmp_path, client, _calls = wired
    monkeypatch.setattr(assets, "_fetch", lambda url: (_ for _ in ()).throw(
        RuntimeError("connection refused")))
    client.get("/api/assets/shirt/43")
    cache = tmp_path / "data/live/assets"
    assert not cache.exists() or list(cache.iterdir()) == []


def test_an_empty_body_from_the_cdn_is_a_fallback_not_a_banked_zero_byte_file(
        wired, monkeypatch):
    tmp_path, client, _calls = wired
    monkeypatch.setattr(assets, "_fetch", lambda url: b"")
    assert b"<svg" in client.get("/api/assets/shirt/43").content
    assert not (tmp_path / "data/live/assets/shirt_43.webp").exists()


def test_an_unwritable_cache_still_serves_the_fetched_bytes(wired,
                                                            monkeypatch):
    """The bytes are in hand. A read-only disk costs the *cache*, not the
    shirt — the user gets his pitch and the next load refetches."""
    _tmp, client, _calls = wired
    monkeypatch.setattr(assets, "_bank", lambda path, data: (
        _ for _ in ()).throw(OSError("read-only file system")))
    response = client.get("/api/assets/shirt/43")
    assert response.status_code == 200
    assert response.content == WEBP


def test_the_write_leaves_no_temp_file_behind(wired):
    tmp_path, client, _calls = wired
    client.get("/api/assets/shirt/43")
    assert list((tmp_path / "data/live/assets").glob("*.tmp")) == []


# --- the allowlist and the path -------------------------------------

def test_a_team_code_the_bootstrap_does_not_know_is_a_404(wired):
    _tmp, client, calls = wired
    assert client.get("/api/assets/shirt/999").status_code == 404
    assert calls == []


def test_a_player_code_the_bootstrap_does_not_know_is_a_404(wired):
    _tmp, client, calls = wired
    assert client.get("/api/assets/photo/999999").status_code == 404
    assert calls == []


def test_a_clone_with_no_snapshot_refuses_everything_rather_than_proxying(
        wired):
    """An empty allowlist is the right failure: the pitch falls back to
    silhouettes, which is the state a machine with no data should be in."""
    tmp_path, client, calls = wired
    (tmp_path / "data/live/players.parquet").unlink()
    (tmp_path / "data/live/teams.parquet").unlink()
    assert client.get("/api/assets/shirt/43").status_code == 404
    assert client.get("/api/assets/photo/223094").status_code == 404
    assert calls == []


@pytest.mark.parametrize("code", [
    "../../etc/passwd", "..%2F..%2Fetc%2Fpasswd", "43/../../secret",
    "43.webp", "-43", "0x2b", "43%00",
])
def test_a_non_integer_code_never_reaches_the_handler(wired, code):
    """A8: the route declares ``int``, so the converter refuses before any
    handler runs and no caller-supplied string can reach a path."""
    tmp_path, client, calls = wired
    assert client.get(f"/api/assets/shirt/{code}").status_code in (404, 422)
    assert calls == []
    assert not (tmp_path / "data/live/assets").exists()


def test_nothing_is_ever_written_outside_the_cache_directory(wired):
    tmp_path, client, _calls = wired
    client.get("/api/assets/shirt/43")
    client.get("/api/assets/photo/223094")
    written = {p.parent for p in (tmp_path / "data").rglob("*") if p.is_file()}
    assert written <= {tmp_path / "data/live",
                       tmp_path / "data/live/assets"}


# --- the urls the spec verified -------------------------------------

def test_the_fetched_urls_are_the_ones_the_spec_curled(wired):
    """D1 records these as verified against the live CDN on 2026-08-31. If
    they change, this test is where that is discovered."""
    _tmp, client, calls = wired
    client.get("/api/assets/shirt/43")
    client.get("/api/assets/photo/223094")
    assert calls[0] == ("https://fantasy.premierleague.com/dist/img/shirts/"
                        "standard/shirt_43-66.webp")
    assert calls[1] == ("https://resources.premierleague.com/premierleague/"
                        "photos/players/110x140/p223094.png")
```

Run it: `uv run pytest -q tests/test_web_assets.py` — expect `ImportError` on `gaffer.web.routers.assets`.

- [ ] **Draw the fallbacks.** Create `src/gaffer/assets/shirt_fallback.svg`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 66 66" width="66"
     height="66" role="img" aria-label="shirt unavailable">
  <title>shirt unavailable</title>
  <path d="M23 8 L13 13 L8 27 L17 30 L17 58 L49 58 L49 30 L58 27 L53 13
           L43 8 L38 14 Q33 18 28 14 Z"
        fill="#8d939c" stroke="#6b7178" stroke-width="1.5"
        stroke-linejoin="round"/>
</svg>
```

Create `src/gaffer/assets/player_fallback.svg`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 110 140" width="110"
     height="140" role="img" aria-label="photo unavailable">
  <title>photo unavailable</title>
  <circle cx="55" cy="48" r="26" fill="#8d939c"/>
  <path d="M12 140 Q12 88 55 88 Q98 88 98 140 Z" fill="#8d939c"/>
</svg>
```

Both are theme-neutral mid-grey on a transparent ground (A10): they sit on the green pitch and on a card in either theme, and neither needs a palette token the browser cannot resolve inside an `<img>`.

- [ ] **Ship them in the wheel.** In `pyproject.toml`, extend the wheel artifacts (L36) so the JSON line reads:

```toml
artifacts = ["src/gaffer/assets/*.json", "src/gaffer/assets/*.svg",
             "src/gaffer/report/templates/*.j2",
             "src/gaffer/web/static/**/*"]
```

Without this an installed wheel ships a package that cannot answer its own fallback — the exact failure the fallback exists to prevent.

- [ ] **Implement.** Create `src/gaffer/web/routers/assets.py`:

```python
"""``GET /api/assets/{shirt,photo}/{code}`` — kit and faces, cached locally.

The frontend speaks only to this backend: every byte on the page arrives via
``/api/*`` or the bundled static directory, and the pitch keeps that posture
rather than hotlinking fifteen images from premierleague.com on every load
(spec D1). So the browser asks this router, this router asks the official CDN
**once**, the bytes land under ``data/live/assets/``, and every request after
that is a disk read.

Three states, in order, and the order is the contract:

1. a **hit** reads the banked file and constructs no HTTP client at all;
2. a **miss** fetches once, banks through a temp file, and serves;
3. **any failure** serves a bundled SVG with a short max-age and writes
   nothing.

The third clause is the one worth defending. A silhouette written into the
cache directory would be indistinguishable from a real shirt on every later
request, so one evening without a network would cost the pitch its kit until
somebody found the directory and deleted it by hand. Failures are served, not
stored.

This is not a proxy. It fetches only for codes the banked bootstrap already
contains — a team code out of ``teams.parquet`` or a player code out of
``players.parquet`` — and the route declares both as ``int``, so nothing a
caller types ever reaches a filesystem path. A clone with no snapshot has an
empty allowlist and answers 404 to everything, which is correct: a machine
with no data should be drawing silhouettes.

Licensing: player and kit imagery is Premier League property. A local
single-user cache for personal display is the same use the official site
makes of it. ``data/`` is untracked, the cache is never staged, and nothing
here redistributes anything.
"""

from __future__ import annotations

import os
from importlib.resources import files
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Query, Response

from gaffer.data import store

router = APIRouter(prefix="/api/assets", tags=["assets"])

SHIRT_BASE = "https://fantasy.premierleague.com/dist/img/shirts/standard"
PHOTO_BASE = ("https://resources.premierleague.com/premierleague/photos/"
              "players/110x140")
"""The two CDN roots, verified by curl on 2026-08-31 (spec D1).

Module constants rather than config keys, deliberately: a new config field
would break the field-count pin inside ``tests/test_v8f_degradation.py``,
which this cycle protects, and the only caller who wanted a knob was a gate
that has a better way to test the same thing (plan A7). Tests monkeypatch
these; the live gate unplugs the network.
"""

CACHE_REL = "live/assets"

TIMEOUT = 5.0
"""Seconds. Short on purpose: this call sits inside a page load, and a CDN
that is thinking about it is, for the reader's purposes, down."""

HIT_CACHE = "public, max-age=604800, immutable"
"""A week, immutable. A shirt for a team code does not change mid-season, and
the browser asking again every load would defeat the point of banking."""

MISS_CACHE = "public, max-age=60"
"""A minute, and no ``immutable``. The fallback means "we could not reach the
CDN just now", which is a sentence with a short shelf life."""

FALLBACKS = {"shirt": "shirt_fallback.svg", "photo": "player_fallback.svg"}


def _cache_dir() -> Path:
    """``data/live/assets``, resolved at call time.

    ``store.DATA_DIR`` is read here rather than bound at import so a test that
    redirects the data root redirects the cache with it.
    """
    return store.DATA_DIR / CACHE_REL


def _fetch(url: str) -> bytes:
    """One GET, with a timeout. The only outbound call in this module.

    A named module-level function rather than an inline ``httpx.get`` so that
    a test can replace it and *count* the calls — the cache-hit rail is an
    assertion about how many times this ran, and that is not observable
    through a client constructed inside a handler.
    """
    response = httpx.get(url, timeout=TIMEOUT, follow_redirects=True)
    response.raise_for_status()
    return response.content


def _bank(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` through a temp file and ``os.replace``.

    The store's idiom, for the store's reason: a process killed mid-write
    would otherwise leave a truncated image that every later request serves as
    a valid hit. Separately named so a test can make the write fail without
    making the fetch fail.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _fallback(kind: str) -> Response:
    """The bundled SVG, served and never stored (module docstring, clause 3).

    Read through ``importlib.resources`` rather than a repo-relative path so
    an installed wheel serves its own copy — ``gaffer.assets``'s idiom.
    """
    svg = files("gaffer.assets").joinpath(FALLBACKS[kind]).read_bytes()
    return Response(content=svg, media_type="image/svg+xml",
                    headers={"Cache-Control": MISS_CACHE})


def _allowed_codes(rel: str, column: str) -> set[int]:
    """The banked bootstrap's codes, or an empty set. Never raises.

    An empty set refuses every request, which is the correct behaviour on a
    clone that has never run ``gaffer advise``: with no data there is no
    allowlist, and without an allowlist this would be an open proxy.
    """
    try:
        if not store.exists(rel):
            return set()
        frame = store.load(rel)
        return {int(c) for c in frame[column].dropna()}
    except Exception as exc:  # noqa: BLE001 — a bad snapshot allows nothing
        print(f"asset allowlist unreadable ({rel}): {exc}")
        return set()


def _serve(kind: str, cache_name: str, url: str, media_type: str) -> Response:
    """Hit, else fetch-and-bank, else fall back. The whole contract."""
    path = _cache_dir() / cache_name
    try:
        if path.is_file():
            return Response(content=path.read_bytes(), media_type=media_type,
                            headers={"Cache-Control": HIT_CACHE})
    except OSError as exc:
        # A banked file we cannot read is a miss, not an error: fall through
        # and try the CDN rather than serving a silhouette for a file that is
        # sitting right there.
        print(f"asset cache unreadable ({cache_name}): {exc}")
    try:
        data = _fetch(url)
    except Exception as exc:  # noqa: BLE001 — a page never 500s over an image
        print(f"asset fetch failed ({url}): {exc}")
        return _fallback(kind)
    if not data:
        # A 200 with no body. Banking it would cache the emptiness.
        print(f"asset fetch returned no bytes ({url})")
        return _fallback(kind)
    try:
        _bank(path, data)
    except Exception as exc:  # noqa: BLE001
        # The bytes are already in hand: a read-only disk costs the cache,
        # not the shirt, and the next load simply fetches again.
        print(f"asset not cached ({cache_name}): {exc}")
    return Response(content=data, media_type=media_type,
                    headers={"Cache-Control": HIT_CACHE})


@router.get("/shirt/{team_code}")
def shirt(team_code: int,
          keeper: bool = Query(False,
                               description="the goalkeeper's variant")
          ) -> Response:
    """One team's kit. ``team_code`` is ``teams[].code`` in the bootstrap.

    The keeper wears a different shirt and is therefore a different file and a
    different URL: a cached outfield shirt must never answer a request for the
    goalkeeper's, or the pitch draws the wrong kit on the one player whose
    kit is always different.
    """
    if team_code not in _allowed_codes("live/teams.parquet", "code"):
        raise HTTPException(status_code=404,
                            detail=f"team {team_code} is not in the banked "
                                   f"bootstrap")
    suffix = "_1" if keeper else ""
    return _serve("shirt", f"shirt_{team_code}{suffix}.webp",
                  f"{SHIRT_BASE}/shirt_{team_code}{suffix}-66.webp",
                  "image/webp")


@router.get("/photo/{player_code}")
def photo(player_code: int) -> Response:
    """One player's face. ``player_code`` is ``elements[].code``.

    Not drawn on the pitch this cycle (spec §3) — the endpoint ships now so
    the cache warms behind the v9b identity rollout, and so the fallback path
    has been exercised for a season before anything depends on it.
    """
    if player_code not in _allowed_codes("live/players.parquet", "code"):
        raise HTTPException(status_code=404,
                            detail=f"player {player_code} is not in the "
                                   f"banked bootstrap")
    return _serve("photo", f"photo_{player_code}.png",
                  f"{PHOTO_BASE}/p{player_code}.png", "image/png")
```

- [ ] **Register it.** In `src/gaffer/web/app.py`, extend the router import (L26-31) so the first line reads:

```python
from gaffer.web.routers import (advice, assets, chips, components, confidence,
                                digest,
                                drafts, fixtures, jobs, journal, league,
                                league_sim, live, meta, misses, news,
                                overrides, plan,
                                players, prices, quality, review, sensitivity,
                                watchlist, whatif)
```

and add the include immediately after `advice` (L69), keeping the list alphabetical:

```python
    app.include_router(assets.router)
```

Note the SPA fallback (app.py:98-115) already refuses to answer any path starting `/api/`, so a 404 from this router stays a JSON 404 and never becomes the HTML shell — which matters here more than elsewhere, because an `<img>` handed an HTML document renders as a broken-image icon and G1 explicitly checks there are none.

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_web_assets.py tests/test_web_app.py
```

- [ ] **Commit.**

```bash
git add src/gaffer/web/routers/assets.py tests/test_web_assets.py \
  src/gaffer/web/app.py src/gaffer/assets/shirt_fallback.svg \
  src/gaffer/assets/player_fallback.svg pyproject.toml \
  && git commit -m "$(cat <<'EOF'
feat: cache shirts and player photos locally instead of hotlinking them

GET /api/assets/{shirt,photo}/{code}: fetch once from the official CDN, bank
under data/live/assets/, serve from disk forever after. Every failure serves a
bundled SVG with a short max-age and writes nothing, so one evening without a
network cannot cost the pitch its kit. Not a proxy — only codes the banked
bootstrap already contains, and the route parses an int before any path.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 2 — team identity and the week's fixture, resolved at serve time

**Files:**
- Create `src/gaffer/web/identity.py`
- Create `tests/test_web_identity.py`
- Modify `src/gaffer/web/schemas.py`
- Modify `src/gaffer/web/routers/advice.py`
- Create `tests/test_web_advice_identity.py`

**Read the preamble and A2 before starting.** `advise.py` writes the payload's player entries and is protected. This task does not touch it, and the enrichment is a decoration applied on the way out of `/api/advice/latest`.

- [ ] **Write the failing test.** Create `tests/test_web_identity.py`:

```python
"""Team identity and the week's fixture, joined onto an advice payload.

Nothing here computes anything. Every field is a lookup into a file the
backend already banks — ``players.parquet`` for a player's team,
``teams.parquet`` for its short name, ``fixtures_all.parquet`` for the week's
game — and the tests are therefore almost entirely about what happens when one
of those files is missing, short a column, or says nothing about a player.

The rule the whole module is shaped around (plan A2): **this never raises**.
This Week rendered its advice without any of these fields yesterday, and a
decoration that can 500 the page it decorates is worse than no decoration.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.data import store
from gaffer.web import identity

PLAYERS = pd.DataFrame({
    # 44 "Nomad" carries a team_code no row in TEAMS claims — the null-short-
    # name case. 55 is the away side of the one GW5 fixture.
    "code": [11, 22, 33, 44, 55],
    "name": ["Saka", "Haaland", "Rice", "Nomad", "Mainoo"],
    "position": ["MID", "FWD", "MID", "DEF", "MID"],
    "team_id": [1, 13, 1, 99, 14],
    "team_code": [3, 43, 3, 91, 1],
    "now_cost": [101, 150, 65, 45, 50],
})

TEAMS = pd.DataFrame({
    "team_id": [1, 13, 14],
    "code": [3, 43, 1],
    "name": ["Arsenal", "Man City", "Man Utd"],
    "short_name": ["ARS", "MCI", "MUN"],
})

# GW5: Arsenal host Man Utd; Man City are blank. One finished GW4 row, so the
# "unfinished only" filter has something to exclude.
FIXTURES = pd.DataFrame({
    "gw": [4, 5],
    "home_id": [1, 1],
    "away_id": [13, 14],
    "kickoff_time": ["2026-09-05T14:00:00Z", "2026-09-12T14:00:00Z"],
    "home_goals": [2.0, None],
    "away_goals": [1.0, None],
    "finished": [True, False],
})

PAYLOAD = {
    "gw": 5,
    "xi": [{"code": 11, "name": "Saka", "position": "MID", "ep": 5.1}],
    "bench": [{"code": 22, "name": "Haaland", "position": "FWD", "ep": 6.2}],
    "buys": [{"code": 33, "name": "Rice", "position": "MID", "ep": 4.0}],
    "sells": [],
    "captain": {"code": 11, "name": "Saka", "position": "MID", "ep": 5.1},
    "vice": {"code": 22, "name": "Haaland", "position": "FWD", "ep": 6.2},
}


def _ticker(*cells):
    """A ``Ticker`` shaped exactly as ``routers/meta.ticker`` returns one.

    Stubbing the *ticker* rather than ``identity._difficulty_by_team`` keeps
    the module's own indexing under test in every case: A4's whole claim is
    that the chip's number is the ticker's number, and a stub that replaced
    the join would stop asserting it.
    """
    from gaffer.web.schemas import Ticker, TickerCell, TickerTeam

    return Ticker(gws=[5], source="odds", teams=[
        TickerTeam(code=code, name=str(code), short_name=str(code),
                   mean_difficulty=diff,
                   cells=[TickerCell(gw=gw, opponent="?", home=True,
                                     difficulty=diff)])
        for code, gw, diff in cells])


@pytest.fixture()
def banked(tmp_path, monkeypatch):
    from gaffer.web.routers import meta

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    (tmp_path / "data" / "live").mkdir(parents=True)
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    TEAMS.to_parquet(tmp_path / "data/live/teams.parquet", index=False)
    FIXTURES.to_parquet(tmp_path / "data/live/fixtures_all.parquet",
                        index=False)
    # Arsenal rated 0.31 in GW5, Man Utd 0.69. The ticker's own odds/Elo reads
    # want banked odds files this fixture deliberately does not write.
    monkeypatch.setattr(meta, "ticker",
                        lambda weeks=8: _ticker((3, 5, 0.31), (1, 5, 0.69)))
    return tmp_path


# --- team identity --------------------------------------------------

def test_a_player_gains_his_team_short_name_and_code(banked):
    out = identity.with_identity(PAYLOAD, 5)
    assert out["xi"][0]["team_short"] == "ARS"
    assert out["xi"][0]["team_code"] == 3


def test_every_player_key_is_enriched_not_only_the_xi(banked):
    """A3: the bench, the moves and both armbands, so v9b needs no edit."""
    out = identity.with_identity(PAYLOAD, 5)
    assert out["bench"][0]["team_short"] == "MCI"
    assert out["buys"][0]["team_short"] == "ARS"
    assert out["captain"]["team_short"] == "ARS"
    assert out["vice"]["team_short"] == "MCI"


def test_a_player_the_snapshot_has_never_heard_of_gets_nulls(banked):
    out = identity.with_identity(
        {"gw": 5, "xi": [{"code": 777, "name": "Ghost", "ep": 0.0}]}, 5)
    assert out["xi"][0]["team_short"] is None
    assert out["xi"][0]["team_code"] is None
    assert out["xi"][0]["next_fixture"] is None


def test_a_team_code_with_no_row_in_teams_gets_a_null_short_name(banked):
    """A6: nulls, never a sentinel. A ``team_code`` of 0 would be a real
    request to the CDN for a shirt that does not exist."""
    out = identity.with_identity(
        {"gw": 5, "xi": [{"code": 44, "name": "Nomad", "ep": 1.0}]}, 5)
    assert out["xi"][0]["team_code"] == 91
    assert out["xi"][0]["team_short"] is None


def test_a_snapshot_without_a_team_code_column_is_nulls_not_a_raise(
        banked, tmp_path, capsys):
    """G2's rail, at the source."""
    PLAYERS.drop(columns=["team_code"]).to_parquet(
        tmp_path / "data/live/players.parquet", index=False)
    out = identity.with_identity(PAYLOAD, 5)
    assert out["xi"][0]["team_code"] is None
    assert out["xi"][0]["team_short"] is None
    assert "identity" in capsys.readouterr().out


# --- the fixture ----------------------------------------------------

def test_the_fixture_names_the_opponent_the_side_and_the_kickoff(banked):
    fx = identity.with_identity(PAYLOAD, 5)["xi"][0]["next_fixture"]
    assert fx == {"opponent_short": "MUN", "home": True,
                  "kickoff_utc": "2026-09-12T14:00:00Z", "difficulty": 0.31}


def test_the_away_side_reads_as_away_with_the_other_opponent(banked):
    """One fixture, two rows: the home team's player sees (H) and the away
    team's sees (A), and neither borrows the other's opponent."""
    home = identity.with_identity(
        {"gw": 5, "xi": [{"code": 11, "name": "Saka", "ep": 5.1}]}, 5)
    away = identity.with_identity(
        {"gw": 5, "xi": [{"code": 55, "name": "Mainoo", "ep": 3.0}]}, 5)
    assert home["xi"][0]["next_fixture"]["home"] is True
    assert home["xi"][0]["next_fixture"]["opponent_short"] == "MUN"
    assert away["xi"][0]["next_fixture"]["home"] is False
    assert away["xi"][0]["next_fixture"]["opponent_short"] == "ARS"


def test_a_blank_gameweek_is_a_null_fixture_not_an_empty_one(banked):
    """D2: the chip says "blank" honestly rather than drawing a chip with
    nothing in it."""
    out = identity.with_identity(
        {"gw": 5, "bench": [{"code": 22, "name": "Haaland", "ep": 6.2}]}, 5)
    assert out["bench"][0]["next_fixture"] is None


def test_a_finished_fixture_in_the_same_gameweek_is_not_offered(banked,
                                                                tmp_path):
    played = FIXTURES.copy()
    played.loc[1, "finished"] = True
    played.to_parquet(tmp_path / "data/live/fixtures_all.parquet",
                      index=False)
    assert identity.with_identity(PAYLOAD, 5)["xi"][0]["next_fixture"] is None


def test_a_double_gameweek_keeps_only_the_first_fixture(banked, tmp_path):
    """D2, explicitly: the second fixture is a v9b question."""
    dgw = pd.concat([FIXTURES, pd.DataFrame({
        "gw": [5], "home_id": [14], "away_id": [1],
        "kickoff_time": ["2026-09-15T19:00:00Z"],
        "home_goals": [None], "away_goals": [None], "finished": [False]})],
        ignore_index=True)
    dgw.to_parquet(tmp_path / "data/live/fixtures_all.parquet", index=False)
    fx = identity.with_identity(PAYLOAD, 5)["xi"][0]["next_fixture"]
    assert fx["kickoff_utc"] == "2026-09-12T14:00:00Z"
    assert fx["home"] is True


def test_a_fixture_with_no_kickoff_yet_still_renders_as_a_fixture(banked,
                                                                   tmp_path):
    """A5: "MCI (H) TBC" is true; an invented kickoff is not."""
    tbc = FIXTURES.copy()
    tbc.loc[1, "kickoff_time"] = None
    tbc.to_parquet(tmp_path / "data/live/fixtures_all.parquet", index=False)
    fx = identity.with_identity(PAYLOAD, 5)["xi"][0]["next_fixture"]
    assert fx["opponent_short"] == "MUN"
    assert fx["kickoff_utc"] is None


def test_an_absent_fixture_file_nulls_every_fixture_and_keeps_identity(
        banked, tmp_path, capsys):
    (tmp_path / "data/live/fixtures_all.parquet").unlink()
    out = identity.with_identity(PAYLOAD, 5)
    assert out["xi"][0]["next_fixture"] is None
    assert out["xi"][0]["team_short"] == "ARS"     # identity is independent
    assert "identity" in capsys.readouterr().out


def test_a_corrupt_fixture_file_is_a_printed_line_not_a_raise(banked,
                                                              tmp_path,
                                                              capsys):
    (tmp_path / "data/live/fixtures_all.parquet").write_bytes(b"not parquet")
    out = identity.with_identity(PAYLOAD, 5)
    assert out["xi"][0]["next_fixture"] is None
    assert "identity" in capsys.readouterr().out


# --- the difficulty -------------------------------------------------

def test_the_difficulty_is_the_tickers_own_number(banked):
    """A4: not a second calculation drawn in the same colour scale.

    Arsenal are rated 0.31 by the stubbed ticker and 0.31 is what lands on
    Saka's chip — the join, keyed on ``(team_code, gw)``, is what is under
    test here.
    """
    assert identity.with_identity(PAYLOAD, 5)[
        "xi"][0]["next_fixture"]["difficulty"] == 0.31


def test_each_side_takes_its_own_rating_not_the_fixtures(banked):
    """The ticker rates a fixture once from the home side and gives the away
    side the complement; both numbers are already in its cells, so the join
    must not hand one team the other's."""
    away = identity.with_identity(
        {"gw": 5, "xi": [{"code": 55, "name": "Mainoo", "ep": 3.0}]}, 5)
    assert away["xi"][0]["next_fixture"]["difficulty"] == 0.69


def test_a_fixture_the_ticker_cannot_rate_keeps_everything_but_the_tint(
        banked, monkeypatch):
    """A4: a chip in a neutral colour is the whole feature minus its tint."""
    from gaffer.web.routers import meta

    monkeypatch.setattr(meta, "ticker", lambda weeks=8: _ticker())
    fx = identity.with_identity(PAYLOAD, 5)["xi"][0]["next_fixture"]
    assert fx["difficulty"] is None
    assert fx["opponent_short"] == "MUN"


def test_a_ticker_that_raises_is_swallowed_into_no_difficulty(banked,
                                                              monkeypatch,
                                                              capsys):
    from gaffer.web.routers import meta

    monkeypatch.setattr(meta, "ticker", lambda weeks=8: (_ for _ in ()).throw(
        RuntimeError("no odds, no elo, no fixtures")))
    fx = identity.with_identity(PAYLOAD, 5)["xi"][0]["next_fixture"]
    assert fx["difficulty"] is None
    assert "difficulty" in capsys.readouterr().out


# --- the never-raises rule ------------------------------------------

@pytest.mark.parametrize("payload", [
    {}, {"gw": 5}, {"gw": 5, "xi": None}, {"gw": 5, "xi": "nonsense"},
    {"gw": 5, "xi": [None, 3, "x"]}, {"gw": 5, "captain": {"name": "no code"}},
])
def test_a_payload_whose_shape_has_drifted_comes_back_unharmed(banked,
                                                               payload):
    assert identity.with_identity(payload, 5) is not None


def test_a_cold_clone_with_no_snapshots_at_all_returns_the_payload(tmp_path,
                                                                   monkeypatch,
                                                                   capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    out = identity.with_identity(PAYLOAD, 5)
    assert out["xi"][0]["name"] == "Saka"
    assert out["xi"][0]["team_short"] is None


def test_the_pre_existing_fields_are_byte_identical(banked):
    """G2: the enrichment is additive and touches nothing that was there."""
    out = identity.with_identity(PAYLOAD, 5)
    before = PAYLOAD["xi"][0]
    after = out["xi"][0]
    assert all(after[k] == v for k, v in before.items())
    assert set(after) - set(before) == {"team_short", "team_code",
                                        "next_fixture"}


def test_the_input_payload_is_not_mutated(banked):
    """The caller hands us ``load_advice``'s dict; a route that mutated it
    would leak enrichment into anything that cached it."""
    identity.with_identity(PAYLOAD, 5)
    assert "team_short" not in PAYLOAD["xi"][0]
```

Run it: `uv run pytest -q tests/test_web_identity.py` — expect `ImportError`.

- [ ] **Implement.** Create `src/gaffer/web/identity.py`:

```python
"""Team identity and the week's fixture, joined onto an advice payload.

The pitch needs three things the advice artifact does not carry: which club a
player belongs to, which shirt to draw for that club, and who he plays this
week. All three are already on disk — ``players.parquet`` knows every player's
``team_code``, ``teams.parquet`` turns that into a short name, and
``fixtures_all.parquet`` holds the week's games — and none of them is a number
the model produced. So nothing here computes: this module is three joins and a
lookup.

It resolves at **serve time** rather than at solve time, and that is a
constraint rather than a preference. ``gaffer.advise`` writes the payload's
player entries and is a protected file, so the fields cannot be added where
the payload is built. Serving is where ``routers/advice.py`` already backfills
``position`` onto payloads written before positions existed
(``with_positions``), for the same reason, and the same two benefits follow:
every advice file already on disk gains the fields without a re-solve, and the
artifact's own bytes never change.

**Nothing here raises.** This Week rendered its advice without any of these
fields yesterday; a decoration that can 500 the page it decorates is worse
than no decoration. Every read is wrapped, every failure prints, and the
worst case is the payload handed back exactly as it arrived.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from gaffer.data import store

PLAYER_KEYS = ("xi", "bench", "buys", "sells", "captain", "vice")
"""The advice keys holding player dicts.

Deliberately the same tuple ``routers/advice.PLAYER_KEYS`` walks, and
deliberately wider than the pitch needs: enriching ``buys`` and ``sells``
costs one dict lookup each on a payload of about twenty entries, and it is
what lets v9b put a shirt beside a transfer without editing this function
(plan A3).
"""

NEW_FIELDS = ("team_short", "team_code", "next_fixture")
"""What this module adds, and the complete list of it. Anything already on an
entry is left exactly as it was."""


def _teams() -> tuple[dict[int, str], dict[int, int]]:
    """``({team_code: short_name}, {team_id: team_code})``, or two empty maps.

    Both directions come off one file read because both are needed on every
    call: the first names a club, the second turns a fixture's ``home_id``
    into the code the shirt endpoint and the identity field speak.
    """
    try:
        teams = store.load("live/teams.parquet")
        return ({int(c): str(s)
                 for c, s in zip(teams["code"], teams["short_name"])},
                {int(i): int(c)
                 for i, c in zip(teams["team_id"], teams["code"])})
    except Exception as exc:  # noqa: BLE001 — identity is never fatal
        print(f"identity: teams snapshot unreadable ({exc})")
        return {}, {}


def _player_teams() -> dict[int, int]:
    """``{player_code: team_code}``, or an empty map.

    A missing ``team_code`` column is the case G2 names explicitly: a bootstrap
    from an older cache must produce nulls and a printed line, not a
    ``KeyError`` on the way out of a page.
    """
    try:
        players = store.load("live/players.parquet")
        if "team_code" not in players.columns:
            raise KeyError("players snapshot has no team_code column")
        pairs = players[["code", "team_code"]].dropna()
        return {int(c): int(t)
                for c, t in zip(pairs["code"], pairs["team_code"])}
    except Exception as exc:  # noqa: BLE001
        print(f"identity: player snapshot unreadable ({exc})")
        return {}


def _fixture_by_team(gw: int, code_of: dict[int, int],
                     short_of: dict[int, str]) -> dict[int, dict]:
    """``{team_code: {opponent_short, home, kickoff_utc}}`` for one gameweek.

    The first **unfinished** fixture per team, by kickoff. Unfinished because a
    team that has already played this week has no next fixture in it, and
    first-by-kickoff because a double gameweek keeps only its opener this
    cycle (spec D2) and "the opener" has to mean the same thing on every
    reload.

    ``kickoff_utc`` is the banked string passed through unparsed. FPL
    publishes fixtures with a null kickoff while the date is TBC, and a chip
    reading "MUN (H) TBC" is true where an invented time would not be.
    Formatting belongs to the client, which knows the reader's timezone.
    """
    out: dict[int, dict] = {}
    try:
        if not store.exists("live/fixtures_all.parquet"):
            raise FileNotFoundError("data/live/fixtures_all.parquet")
        fixtures = store.load("live/fixtures_all.parquet")
        week = fixtures[(fixtures["gw"] == int(gw))
                        & (~fixtures["finished"].astype(bool))]
        week = week.sort_values("kickoff_time", na_position="last")
    except Exception as exc:  # noqa: BLE001
        print(f"identity: fixtures unreadable, no next-fixture chips ({exc})")
        return {}
    for fx in week.itertuples():
        home = code_of.get(int(fx.home_id))
        away = code_of.get(int(fx.away_id))
        if home is None or away is None:
            continue
        kickoff = getattr(fx, "kickoff_time", None)
        kickoff = None if kickoff is None or pd.isna(kickoff) else str(kickoff)
        for own, other, is_home in ((home, away, True), (away, home, False)):
            # setdefault, not assignment: the frame is sorted by kickoff, so
            # the first row a team appears in is its opener.
            out.setdefault(own, {"opponent_short": short_of.get(other),
                                 "home": is_home, "kickoff_utc": kickoff})
    return out


def _difficulty_by_team(gws: list[int]) -> dict[tuple[int, int], float]:
    """``{(team_code, gw): difficulty}`` from the ticker's own rating.

    The ticker is *called*, not reimplemented (plan A4). Its odds lookup, its
    Elo fallback, its rate-the-fixture-once-from-the-home-side rule and its
    clamp are sixty lines inside ``routers/meta.ticker``, and a second copy
    beside them would be a second answer to "how hard is this fixture" drawn
    on the same page in the same colour scale — a disagreement nobody could
    see. ``weeks=2`` rather than 1 because ``ticker`` slices the first *n*
    unfinished gameweeks and a mid-week reload can find the advice gameweek
    second in that window.

    Every failure is an empty map, which means every chip renders without its
    tint and with everything else intact.
    """
    from gaffer.web.routers import meta

    try:
        table = meta.ticker(weeks=2)
    except Exception as exc:  # noqa: BLE001 — a tint is never fatal
        print(f"identity: no fixture difficulty available ({exc})")
        return {}
    wanted = {int(g) for g in gws}
    return {(int(team.code), int(cell.gw)): float(cell.difficulty)
            for team in table.teams for cell in team.cells
            if int(cell.gw) in wanted}


def with_identity(payload: dict, gw: int) -> dict:
    """Return ``payload`` with ``team_short``/``team_code``/``next_fixture``.

    Additive and non-mutating: the caller's dict is the one ``load_advice``
    returned, and a route that enriched it in place would leak the decoration
    into anything holding a reference. Pre-existing keys on every entry are
    passed through untouched, which is what makes the G2 byte-identity rail
    hold.

    ``gw`` is the advice gameweek, supplied by the caller rather than read off
    the payload: the router already knows it, and a payload whose ``gw`` field
    is missing should still get its shirts.
    """
    try:
        short_of, code_of = _teams()
        team_of = _player_teams()
        fixtures = _fixture_by_team(int(gw), code_of, short_of)
        difficulty = _difficulty_by_team([int(gw)])
    except Exception as exc:  # noqa: BLE001 — the whole join is decoration
        print(f"identity: not applied ({exc})")
        return payload

    def decorate(entry: Any) -> Any:
        if not isinstance(entry, dict) or "code" not in entry:
            return entry
        try:
            code = int(entry["code"])
        except (TypeError, ValueError):
            return entry
        team_code = team_of.get(code)
        fixture = None
        if team_code is not None and team_code in fixtures:
            fixture = dict(fixtures[team_code])
            fixture["difficulty"] = difficulty.get((team_code, int(gw)))
        return {**entry,
                "team_short": short_of.get(team_code)
                if team_code is not None else None,
                "team_code": team_code,
                "next_fixture": fixture}

    out = dict(payload)
    for key in PLAYER_KEYS:
        value = out.get(key)
        if isinstance(value, list):
            out[key] = [decorate(e) for e in value]
        elif isinstance(value, dict):
            out[key] = decorate(value)
    return out
```

- [ ] **Add the schema.** In `src/gaffer/web/schemas.py`, insert immediately **before** `class PlayerRef` (L73) and extend `PlayerRef` itself so the pair reads:

```python
class NextFixture(BaseModel):
    """One team's next game in the advised gameweek.

    Resolved at serve time from the banked fixture list, never solved for.
    Two of the four fields are independently optional and mean different
    things when null: ``kickoff_utc`` is null while FPL still has the date as
    TBC, and ``difficulty`` is null when the ticker could rate nothing — a
    chip in a neutral colour rather than a chip that is not drawn.

    A team with *no* game gets ``next_fixture: null`` on the player instead of
    this model with empty fields, because "he does not play" and "he plays and
    we know less than usual about it" are different sentences.
    """

    opponent_short: str | None = None
    home: bool
    kickoff_utc: str | None = None
    difficulty: float | None = None


class PlayerRef(BaseModel):
    code: int
    name: str
    position: str | None = None
    ep: float
    tag: str | None = None
    frequency: float | None = None
    # v9a: identity, resolved at serve time by ``gaffer.web.identity`` and
    # never written into the advice artifact — ``advise.py`` is protected, so
    # the fields are a decoration on the way out of the route. All three
    # default to None, so a plan payload built without the enrichment (the
    # what-if lab, ``/api/plan``) types exactly as it did.
    team_short: str | None = None
    team_code: int | None = None
    next_fixture: NextFixture | None = None
```

The pre-existing `PlayerRef` body is `code/name/position/ep` with `tag` and `frequency` optional in the frontend mirror only; keep whatever the file currently declares for those four and add only the three commented lines plus `NextFixture`. **Do not** change a field's existing optionality — `/api/plan` and `/api/league/whatif` validate through this model and a tightened field would 500 them.

- [ ] **Write the route test.** Create `tests/test_web_advice_identity.py`:

```python
"""``/api/advice/latest`` serves the enrichment, and survives without it."""

from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.data import store
from gaffer.web.app import create_app

GW = 5

PLAYERS = pd.DataFrame({
    "code": [11, 22], "name": ["Saka", "Haaland"],
    "position": ["MID", "FWD"], "team_id": [1, 13], "team_code": [3, 43],
    "now_cost": [101, 150], "selected_by_percent": [40.0, 60.0],
})
TEAMS = pd.DataFrame({"team_id": [1, 13, 14], "code": [3, 43, 1],
                      "name": ["Arsenal", "Man City", "Man Utd"],
                      "short_name": ["ARS", "MCI", "MUN"]})
FIXTURES = pd.DataFrame({
    "gw": [5], "home_id": [1], "away_id": [14],
    "kickoff_time": ["2026-09-12T14:00:00Z"],
    "home_goals": [None], "away_goals": [None], "finished": [False]})

ADVICE = {
    "gw": GW, "hits": 0, "expected_pts": 54.3,
    "xi": [{"code": 11, "name": "Saka", "position": "MID", "ep": 5.1}],
    "bench": [{"code": 22, "name": "Haaland", "position": "FWD", "ep": 6.2}],
    "buys": [], "sells": [],
    "captain": {"code": 11, "name": "Saka", "position": "MID", "ep": 5.1},
    "vice": {"code": 22, "name": "Haaland", "position": "FWD", "ep": 6.2},
    "chip_table": [], "strategy": None,
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A clone with one solved gameweek, wired the way the advice tests wire
    it: a real artifact on disk and a real solve state beside it."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    (tmp_path / "data" / "live").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    TEAMS.to_parquet(tmp_path / "data/live/teams.parquet", index=False)
    FIXTURES.to_parquet(tmp_path / "data/live/fixtures_all.parquet",
                        index=False)
    (tmp_path / "reports" / f"gw{GW}-advice.json").write_text(
        json.dumps(ADVICE))
    _write_solve_state(tmp_path)
    return tmp_path, TestClient(create_app())


def _write_solve_state(tmp_path):
    """Reuse the project's own helper so this test cannot drift from the
    shape ``load_solve_state`` expects."""
    from gaffer.artifacts import SolveState, save_solve_state

    save_solve_state(SolveState(
        gw=GW, gws=[GW], deadline="2026-09-11T17:30:00Z",
        generated_at="2026-09-10T20:00:00+00:00", mode="weekly", bank=0.5,
        free_transfers=1, owned_codes=[11, 22], lam=0.0, league_eo={},
        cover={}, avail_by_gw={}, opt={},
        pool=pd.DataFrame({"code": [11, 22], "position": ["MID", "FWD"]})))


def test_the_payload_carries_identity_and_the_weeks_fixture(client):
    _tmp, api = client
    advice = api.get("/api/advice/latest").json()["advice"]
    assert advice["xi"][0]["team_short"] == "ARS"
    assert advice["xi"][0]["team_code"] == 3
    assert advice["xi"][0]["next_fixture"]["opponent_short"] == "MUN"
    assert advice["xi"][0]["next_fixture"]["home"] is True


def test_a_blank_gameweek_player_carries_a_null_fixture(client):
    _tmp, api = client
    advice = api.get("/api/advice/latest").json()["advice"]
    assert advice["bench"][0]["team_short"] == "MCI"
    assert advice["bench"][0]["next_fixture"] is None


def test_positions_are_still_backfilled_alongside(client):
    """The two serve-time decorations compose; neither undoes the other."""
    _tmp, api = client
    advice = api.get("/api/advice/latest").json()["advice"]
    assert advice["xi"][0]["position"] == "MID"


def test_the_route_is_a_200_with_no_fixture_file_at_all(client):
    tmp_path, api = client
    (tmp_path / "data/live/fixtures_all.parquet").unlink()
    advice = api.get("/api/advice/latest").json()["advice"]
    assert advice["xi"][0]["next_fixture"] is None
    assert advice["xi"][0]["team_short"] == "ARS"


def test_the_artifact_on_disk_is_untouched(client):
    """A2: the enrichment is a decoration on the way out, and the file the
    next ``advise`` run diffs against must be byte-identical."""
    tmp_path, api = client
    before = (tmp_path / "reports" / f"gw{GW}-advice.json").read_bytes()
    api.get("/api/advice/latest")
    assert (tmp_path / "reports" / f"gw{GW}-advice.json").read_bytes() \
        == before
```

- [ ] **Wire the route.** In `src/gaffer/web/routers/advice.py`, add to the imports:

```python
from gaffer.web.identity import with_identity
```

and change the body of `latest()` (L111-120) so the payload passes through both decorations:

```python
@router.get("/latest", response_model=AdviceLatest)
def latest() -> AdviceLatest:
    gw = latest_gw()
    if gw is None:
        raise GafferError("no advice on disk yet — run `gaffer advise` first")
    state = load_solve_state(gw)
    # Two serve-time decorations, composed. ``with_positions`` backfills a
    # field ``advise`` did not always write; ``with_identity`` adds three it
    # still does not, because it cannot — ``advise.py`` is protected, so the
    # pitch's team identity and fixture chip are resolved here from files the
    # backend already banks (plan A2). Both are additive, both leave every
    # pre-existing field alone, and both are no-ops on a clone with no
    # snapshots rather than an error.
    payload = with_identity(with_positions(load_advice(gw), state.pool), gw)
    return AdviceLatest(
        gw=gw, mode=state.mode, deadline=state.deadline, advice=payload,
        staleness=staleness_for(gw, state.deadline, state.generated_at))
```

- [ ] **Verify.** The advice route's own suite must be untouched by this.

```bash
uv run pytest -q tests/test_web_identity.py tests/test_web_advice_identity.py \
  tests/test_web_advice.py tests/test_web_advice_movers.py \
  tests/test_web_plan.py tests/test_web_whatif.py tests/test_web_meta.py
```

- [ ] **Commit.**

```bash
git add src/gaffer/web/identity.py tests/test_web_identity.py \
  src/gaffer/web/schemas.py src/gaffer/web/routers/advice.py \
  tests/test_web_advice_identity.py && git commit -m "$(cat <<'EOF'
feat: resolve team identity and the week's fixture onto the advice payload

Three additive fields — team_short, team_code, next_fixture — joined at serve
time from players/teams/fixtures_all, with the chip's difficulty taken from
the ticker's own rating rather than a second copy of it. Serve time rather
than solve time because advise.py writes the payload and is protected; the
artifact on disk is unchanged and every advice file already banked gains the
fields without a re-solve. A blank gameweek is a null fixture, honestly.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 3 — the frontend types, in lockstep

**Files:**
- Modify `frontend/src/types.ts`
- Create `frontend/src/types.test.ts`

A tiny task on purpose. `types.ts` is a hand-maintained mirror of `schemas.py`, and the one failure mode that matters is the two drifting silently — a field the server sends and the client's type does not know about is invisible until somebody reads both files side by side.

- [ ] **Write the failing test.** Create `frontend/src/types.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import type { NextFixture, PlayerRef } from './types'

/**
 * The mirror check. `types.ts` is hand-maintained against `schemas.py`, and a
 * compile-time assertion is the only thing standing between the two files and
 * a season of silent drift. These tests do almost nothing at runtime — they
 * exist so that `tsc --noEmit` fails when a field's name or nullability moves
 * on one side and not the other.
 */
describe('the v9a identity fields', () => {
  it('lets a player carry a team and a fixture', () => {
    const fixture: NextFixture = {
      opponent_short: 'MUN',
      home: true,
      kickoff_utc: '2026-09-12T14:00:00Z',
      difficulty: 0.31,
    }
    const player: PlayerRef = {
      code: 11, name: 'Saka', position: 'MID', ep: 5.1,
      team_short: 'ARS', team_code: 3, next_fixture: fixture,
    }
    expect(player.next_fixture?.opponent_short).toBe('MUN')
  })

  it('lets both optional halves of a fixture be null independently', () => {
    // A5: "MUN (H) TBC" in a neutral colour is a real state, and it means
    // something different from having no fixture at all.
    const tbc: NextFixture = {
      opponent_short: 'MUN', home: false, kickoff_utc: null, difficulty: null,
    }
    expect(tbc.kickoff_utc).toBeNull()
  })

  it('lets a blank gameweek be a null fixture, not an empty one', () => {
    const blank: PlayerRef = {
      code: 22, name: 'Haaland', ep: 6.2,
      team_short: 'MCI', team_code: 43, next_fixture: null,
    }
    expect(blank.next_fixture).toBeNull()
  })

  it('still types a player with no identity at all', () => {
    // /api/plan and the what-if lab build PlayerRefs without the enrichment.
    const bare: PlayerRef = { code: 33, name: 'Rice', ep: 4.0 }
    expect(bare.team_short).toBeUndefined()
  })
})
```

Run it: `cd frontend && npx vitest run src/types.test.ts` — expect a type error on `team_short`.

- [ ] **Implement.** In `frontend/src/types.ts`, insert before `PlayerRef` (L1) and extend it:

```ts
/** One team's next game in the advised gameweek.
 *
 *  Resolved server-side from the banked fixture list — never computed here.
 *  The two optional fields are independently null and mean different things:
 *  `kickoff_utc` is null while FPL still has the date as TBC, and
 *  `difficulty` is null when the ticker could rate nothing, which draws the
 *  chip in a neutral colour rather than not drawing it. */
export interface NextFixture {
  opponent_short: string | null
  home: boolean
  kickoff_utc: string | null
  difficulty: number | null
}

export interface PlayerRef {
  code: number
  name: string
  position?: string
  ep: number
  tag?: string
  /** Share of noised scenarios that contained this move. Absent when the
   *  scenario sweep did not run ([scenarios] n = 0). */
  frequency?: number
  /** v9a. Added by `/api/advice/latest` on the way out, not written into the
   *  advice artifact — so `/api/plan` and the what-if lab send PlayerRefs
   *  without them and all three are optional here. `next_fixture: null` is a
   *  blank gameweek; `undefined` is a payload that was never enriched. */
  team_short?: string | null
  team_code?: number | null
  next_fixture?: NextFixture | null
}
```

- [ ] **Verify.**

```bash
cd frontend && npx tsc --noEmit && npx vitest run src/types.test.ts
```

- [ ] **Commit.**

```bash
git add frontend/src/types.ts frontend/src/types.test.ts \
  && git commit -m "$(cat <<'EOF'
feat: mirror the v9a identity fields into types.ts, with a lockstep test

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 4 — `PlayerCard`: one card, two sizes

**Files:**
- Create `frontend/src/kit/PlayerCard.tsx`
- Create `frontend/src/kit/PlayerCard.test.tsx`
- Modify `frontend/src/kit/index.ts`
- Modify `frontend/src/kit/index.test.ts`

D4: the card is kit-level with `size: 'pitch' | 'chip'` so v9b can put it in Live, the league compare and the review lanes without a redesign. This cycle wires it into the pitch only, and the `'chip'` size ships tested and unused — which is the point of building it here rather than there.

- [ ] **Write the failing test.** Create `frontend/src/kit/PlayerCard.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { describe, expect, it } from 'vitest'
import PlayerCard from './PlayerCard'
import type { NextFixture } from '../types'

const FIXTURE: NextFixture = {
  opponent_short: 'MUN', home: true,
  kickoff_utc: '2026-09-12T14:00:00Z', difficulty: 0.31,
}

function card(over: Partial<ComponentProps<typeof PlayerCard>> = {}) {
  return render(
    <PlayerCard
      code={11} name="Saka" position="MID" teamShort="ARS" teamCode={3}
      ep={5.1} fixture={FIXTURE} {...over}
    />,
  )
}

describe('PlayerCard', () => {
  it('draws the shirt through the backend, never the CDN', () => {
    // D1: every byte on the page arrives via /api/*. A hotlinked shirt would
    // also be the one request that leaks the reader's IP to a third party.
    card()
    expect(screen.getByRole('img', { name: /ARS/ }))
      .toHaveAttribute('src', '/api/assets/shirt/3')
  })

  it('asks for the keeper variant for a goalkeeper', () => {
    card({ position: 'GKP' })
    expect(screen.getByRole('img', { name: /ARS/ }))
      .toHaveAttribute('src', '/api/assets/shirt/3?keeper=true')
  })

  it('draws a plain shirt for a player with no team code', () => {
    // A6: nulls, never a sentinel — a team_code of 0 would be a real request
    // for a shirt that does not exist.
    card({ teamCode: null, teamShort: null })
    expect(screen.getByRole('img', { name: /shirt/i }))
      .toHaveAttribute('src', '/api/assets/shirt/0')
    expect(screen.queryByRole('img', { name: /shirt/i })
      ?.getAttribute('src')).not.toContain('undefined')
  })

  it('names the player, his club and his expected points', () => {
    card()
    expect(screen.getByText('Saka')).toBeInTheDocument()
    expect(screen.getByText('ARS')).toBeInTheDocument()
    expect(screen.getByText('5.1')).toBeInTheDocument()
  })

  it('draws the fixture chip with the opponent, the side and the kickoff',
     () => {
    card()
    const chip = screen.getByTestId('fixture-chip')
    expect(chip).toHaveTextContent('MUN (H)')
    expect(chip.textContent).toMatch(/\d/)   // some rendered kickoff
  })

  it('says Blank rather than drawing an empty chip', () => {
    // D2: honest, not zeroed.
    card({ fixture: null })
    expect(screen.getByTestId('fixture-chip')).toHaveTextContent('Blank')
  })

  it('renders a fixture whose kickoff is still TBC', () => {
    card({ fixture: { ...FIXTURE, kickoff_utc: null } })
    const chip = screen.getByTestId('fixture-chip')
    expect(chip).toHaveTextContent('MUN (H)')
    expect(chip).toHaveTextContent('TBC')
  })

  it('tints the chip by difficulty and leaves an unrated one neutral', () => {
    const { rerender } = card()
    const tinted = screen.getByTestId('fixture-chip').style.backgroundColor
    rerender(
      <PlayerCard code={11} name="Saka" position="MID" teamShort="ARS"
                  teamCode={3} ep={5.1}
                  fixture={{ ...FIXTURE, difficulty: null }} />,
    )
    expect(screen.getByTestId('fixture-chip').style.backgroundColor)
      .not.toBe(tinted)
  })

  it('wears the captain armband', () => {
    card({ armband: 'C' })
    expect(screen.getByTitle('Captain')).toHaveTextContent('C')
    expect(screen.queryByTitle('Vice-captain')).not.toBeInTheDocument()
  })

  it('wears the vice armband', () => {
    card({ armband: 'V' })
    expect(screen.getByTitle('Vice-captain')).toHaveTextContent('V')
  })

  it('carries a news flag with the chance of playing', () => {
    card({ news: 'Knock — 75% chance of playing', chanceOfPlaying: 75 })
    expect(screen.getByText('75%')).toBeInTheDocument()
  })

  it('flags news with no percentage as News', () => {
    card({ news: 'Suspended', chanceOfPlaying: null })
    expect(screen.getByText('News')).toBeInTheDocument()
  })

  it('is a button only when something is listening', () => {
    const { rerender } = card()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    rerender(
      <PlayerCard code={11} name="Saka" position="MID" teamShort="ARS"
                  teamCode={3} ep={5.1} fixture={FIXTURE}
                  onSelect={() => {}} />,
    )
    expect(screen.getByRole('button')).toBeInTheDocument()
  })

  it('renders the chip size without the fixture furniture', () => {
    // D4: the compact form v9b puts in a Live row or a league compare.
    card({ size: 'chip' })
    expect(screen.getByText('Saka')).toBeInTheDocument()
    expect(screen.queryByTestId('fixture-chip')).not.toBeInTheDocument()
  })

  it('still names the player when everything optional is missing', () => {
    render(<PlayerCard code={99} name="Nobody" position="" teamShort={null}
                       teamCode={null} ep={0} fixture={null} />)
    expect(screen.getByText('Nobody')).toBeInTheDocument()
  })
})
```

Run it: `cd frontend && npx vitest run src/kit/PlayerCard.test.tsx` — expect a module-not-found.

- [ ] **Implement.** Create `frontend/src/kit/PlayerCard.tsx`:

```tsx
import Badge from './Badge'
import { fmtNum } from './format'
import { difficultyBackground } from './scale'
import type { NextFixture } from '../types'

/**
 * One player, drawn as FPL draws him: the shirt, the name, the club, the
 * number, and who he plays next.
 *
 * Kit-level and sized rather than hub-level and fixed (spec D4), because
 * every lane that mentions a player wants the same object at a different
 * scale — the pitch draws him large, and v9b's Live rows, league compare and
 * review lanes want him small. Building the small size now and leaving it
 * unused is cheaper than discovering in v9b that the large one hard-codes a
 * pitch.
 *
 * Every image comes from `/api/assets/`, never from premierleague.com: the
 * frontend speaks only to this backend (spec D1), and a hotlinked shirt would
 * be the one request on the page that tells a third party who is reading it.
 * A player with no `teamCode` asks for shirt 0, which the backend refuses and
 * answers with the bundled plain shirt — so the fallback is one code path,
 * not two.
 */

export type PlayerCardSize = 'pitch' | 'chip'

export interface PlayerCardProps {
  code: number
  name: string
  position: string
  teamShort: string | null
  teamCode: number | null
  ep: number
  fixture?: NextFixture | null
  /** `'C'`, `'V'`, or nothing. The plan's armbands, not a judgement. */
  armband?: 'C' | 'V' | null
  /** The multiplier the chip implies, when the payload already names one.
   *  Nothing new is plumbed for this (spec D3) — it is drawn if it arrives. */
  multiplier?: number | null
  news?: string
  chanceOfPlaying?: number | null
  size?: PlayerCardSize
  onSelect?: (code: number) => void
}

/** The keeper's kit is a different file at the same team code. */
function shirtSrc(teamCode: number | null, position: string): string {
  const code = teamCode ?? 0
  return position === 'GKP'
    ? `/api/assets/shirt/${code}?keeper=true`
    : `/api/assets/shirt/${code}`
}

/** Day and time in the reader's own zone.
 *
 *  The server sends UTC and refuses to guess a timezone, which is correct;
 *  this is the only place that knows one. An unparseable stamp reads as TBC
 *  rather than as `Invalid Date`. */
function kickoffLabel(iso: string | null): string {
  if (!iso) return 'TBC'
  const when = new Date(iso)
  if (Number.isNaN(when.getTime())) return 'TBC'
  return when.toLocaleString(undefined, {
    weekday: 'short', hour: '2-digit', minute: '2-digit',
  })
}

function FixtureChip({ fixture }: { fixture: NextFixture | null }) {
  // A blank gameweek is a word, not an empty box: the reader has to be able
  // to tell "he does not play" from "we failed to load his fixture".
  if (!fixture) {
    return (
      <span data-testid="fixture-chip"
            className="rounded px-1 text-[10px] text-text-muted"
            style={{ backgroundColor: 'var(--color-card)' }}>
        Blank
      </span>
    )
  }
  const side = fixture.home ? 'H' : 'A'
  return (
    <span
      data-testid="fixture-chip"
      className="rounded px-1 text-[10px] text-text"
      // An unrated fixture keeps the card colour rather than borrowing the
      // midpoint of the difficulty scale, which would read as "average" —
      // a claim the ticker did not make.
      style={{
        backgroundColor: fixture.difficulty === null
          ? 'var(--color-card)'
          : difficultyBackground(fixture.difficulty),
      }}
      title={fixture.difficulty === null
        ? 'No difficulty rating available for this fixture'
        : `Fixture difficulty ${fixture.difficulty.toFixed(2)} — the ticker's `
          + 'odds-implied rating, not FPL\'s FDR'}
    >
      {`${fixture.opponent_short ?? '???'} (${side}) `}
      {kickoffLabel(fixture.kickoff_utc)}
    </span>
  )
}

export default function PlayerCard({
  code, name, position, teamShort, teamCode, ep, fixture = null,
  armband = null, multiplier = null, news = '', chanceOfPlaying = null,
  size = 'pitch', onSelect,
}: PlayerCardProps) {
  const pitch = size === 'pitch'
  const body = (
    <>
      <span className="relative">
        <img
          src={shirtSrc(teamCode, position)}
          alt={teamShort ? `${teamShort} shirt` : 'shirt'}
          width={pitch ? 44 : 24}
          height={pitch ? 44 : 24}
          // A shirt that fails on *both* the CDN and the bundled SVG must not
          // leave a broken-image icon on the pitch (gate G1 checks for none).
          onError={(e) => { e.currentTarget.style.visibility = 'hidden' }}
          className="mx-auto block"
        />
        {armband && (
          <span
            title={armband === 'C' ? 'Captain' : 'Vice-captain'}
            className={'absolute -right-1 -top-1 flex h-4 w-4 items-center '
              + 'justify-center rounded-full border border-border '
              + 'bg-card text-[9px] font-semibold '
              + (armband === 'C' ? 'text-sage' : 'text-info')}
          >
            {armband}
          </span>
        )}
      </span>
      <span className="mt-0.5 flex items-center justify-center gap-1
                       text-xs text-text">
        <span className="truncate">{name}</span>
        {news && (
          <Badge variant="negative" title={news}>
            {chanceOfPlaying === null ? 'News' : `${chanceOfPlaying}%`}
          </Badge>
        )}
      </span>
      <span className="flex items-center justify-center gap-1
                       text-[10px] text-text-muted">
        {teamShort && <span>{teamShort}</span>}
        <span className="num">{fmtNum(ep)}</span>
        {/* Drawn only when the payload already named a chip (D3): no new
            chip plumbing this cycle. */}
        {multiplier !== null && multiplier > 1 && (
          <span className="num text-sage">{`×${multiplier}`}</span>
        )}
      </span>
      {pitch && <FixtureChip fixture={fixture} />}
    </>
  )

  const className = 'flex w-[76px] flex-col items-center rounded-card '
    + 'border border-border bg-card px-1 py-1 text-center'

  // A div unless something is listening: a button nothing responds to is a
  // focus stop that lies about being interactive.
  return onSelect
    ? (
      <button type="button" data-code={code} className={className}
              onClick={() => onSelect(code)}>
        {body}
      </button>
      )
    : <div data-code={code} className={className}>{body}</div>
}
```

- [ ] **Export it.** In `frontend/src/kit/index.ts`, add beside the other components (keeping the file's alphabetical-ish grouping, immediately after the `PitchView` pair):

```ts
export { default as PlayerCard } from './PlayerCard'
export type { PlayerCardProps, PlayerCardSize } from './PlayerCard'
```

and in `frontend/src/kit/index.test.ts`, extend the barrel's name list (L6-8) to include `'PlayerCard'`:

```ts
    for (const name of ['Badge', 'Card', 'DataTable', 'EmptyState',
      'PageHeader', 'PitchView', 'PlayerCard', 'PosBadge', 'Sparkline',
      'Stat', 'ThresholdBar']) {
```

`kit/PitchView` stays exactly as it is (A1): still exported, still pinned, still tested. It stops being *rendered* at Task 6 and is not deleted.

- [ ] **Verify.**

```bash
cd frontend && npx tsc --noEmit \
  && npx vitest run src/kit/PlayerCard.test.tsx src/kit/index.test.ts \
       src/kit/PitchView.test.tsx
```

- [ ] **Commit.**

```bash
git add frontend/src/kit/PlayerCard.tsx frontend/src/kit/PlayerCard.test.tsx \
  frontend/src/kit/index.ts frontend/src/kit/index.test.ts \
  && git commit -m "$(cat <<'EOF'
feat: PlayerCard — one shirt-and-fixture card, sized for reuse

Kit-level with size: 'pitch' | 'chip' so v9b's Live, league and review lanes
get the same object without a redesign. Every image comes through
/api/assets/; a player with no team code asks for shirt 0 and gets the bundled
plain shirt, so the fallback is one code path rather than two. A blank
gameweek is the word "Blank", and an unrated fixture keeps the card colour
rather than borrowing the midpoint of a scale nobody claimed.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 5 — `SquadPitch`: four rows, a bench strip, and the armbands

**Files:**
- Create `frontend/src/hubs/this-week/SquadPitch.tsx`
- Create `frontend/src/hubs/this-week/SquadPitch.test.tsx`
- Modify `frontend/src/hubs/this-week/SquadTable.tsx` (the `SquadRow` interface only)

`SquadRow` gains the three fields here rather than in Task 6 because both the pitch and the table are rendered from the same array, and one row type is the whole reason the toggle is a toggle rather than two data paths.

- [ ] **Write the failing test.** Create `frontend/src/hubs/this-week/SquadPitch.test.tsx`:

```tsx
import { render, screen, within } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { describe, expect, it } from 'vitest'
import SquadPitch from './SquadPitch'
import type { SquadRow } from './SquadTable'

function row(over: Partial<SquadRow>): SquadRow {
  return {
    code: 1, name: 'Player', position: 'MID', ep: 4.0, epLo: null, epHi: null,
    pHaul: null, pBlank: null, xmins: null, ownership: 0, leagueEo: 0,
    simPct: null, last4: [], news: '', chanceOfPlaying: null,
    penalties: false, teamShort: 'ARS', teamCode: 3,
    nextFixture: { opponent_short: 'MUN', home: true,
                   kickoff_utc: '2026-09-12T14:00:00Z', difficulty: 0.3 },
    ...over,
  }
}

const XI: SquadRow[] = [
  row({ code: 1, name: 'Raya', position: 'GKP' }),
  row({ code: 2, name: 'Saliba', position: 'DEF' }),
  row({ code: 3, name: 'Gabriel', position: 'DEF' }),
  row({ code: 4, name: 'White', position: 'DEF' }),
  row({ code: 5, name: 'Timber', position: 'DEF' }),
  row({ code: 6, name: 'Saka', position: 'MID' }),
  row({ code: 7, name: 'Odegaard', position: 'MID' }),
  row({ code: 8, name: 'Rice', position: 'MID' }),
  row({ code: 9, name: 'Rogers', position: 'MID' }),
  row({ code: 10, name: 'Haaland', position: 'FWD' }),
  row({ code: 11, name: 'Isak', position: 'FWD' }),
]

const BENCH: SquadRow[] = [
  row({ code: 12, name: 'Sels', position: 'GKP' }),
  row({ code: 13, name: 'Andersen', position: 'DEF' }),
  row({ code: 14, name: 'Semenyo', position: 'MID' }),
  row({ code: 15, name: 'Wood', position: 'FWD' }),
]

function pitch(over: Partial<ComponentProps<typeof SquadPitch>> = {}) {
  return render(
    <SquadPitch xi={XI} bench={BENCH} captain={6} vice={10} {...over} />,
  )
}

describe('SquadPitch', () => {
  it('lays the XI out in four formation rows', () => {
    pitch()
    expect(within(screen.getByTestId('pitch-row-GKP'))
      .getAllByText(/Raya/)).toHaveLength(1)
    expect(within(screen.getByTestId('pitch-row-DEF'))
      .getAllByRole('img')).toHaveLength(4)
    expect(within(screen.getByTestId('pitch-row-MID'))
      .getAllByRole('img')).toHaveLength(4)
    expect(within(screen.getByTestId('pitch-row-FWD'))
      .getAllByRole('img')).toHaveLength(2)
  })

  it('omits a line nobody is playing rather than drawing an empty band', () => {
    // A 3-5-2 with no forwards is not a formation, but a payload can arrive
    // mid-solve with a line unfilled and an empty green stripe reads as a bug.
    pitch({ xi: XI.filter((p) => p.position !== 'FWD') })
    expect(screen.queryByTestId('pitch-row-FWD')).not.toBeInTheDocument()
  })

  it('puts a player with no position in a row of his own, not nowhere', () => {
    // Advice written before v3.1 has no `position`. Losing a player off the
    // pitch entirely would be worse than an ugly extra row.
    pitch({ xi: [...XI.slice(0, 10), row({ code: 99, name: 'Legacy',
                                           position: '' })] })
    expect(within(screen.getByTestId('pitch-row-OTHER'))
      .getByText('Legacy')).toBeInTheDocument()
  })

  it('draws the bench below the pitch, in bench order', () => {
    pitch()
    const strip = screen.getByTestId('bench-strip')
    expect(within(strip).getAllByRole('img')).toHaveLength(4)
    const names = within(strip).getAllByText(/Sels|Andersen|Semenyo|Wood/)
      .map((n) => n.textContent)
    expect(names).toEqual(['Sels', 'Andersen', 'Semenyo', 'Wood'])
  })

  it('renders an empty bench without collapsing the pitch', () => {
    pitch({ bench: [] })
    expect(screen.getByTestId('pitch-row-GKP')).toBeInTheDocument()
    expect(screen.queryByTestId('bench-strip')).not.toBeInTheDocument()
  })

  it('puts the armbands on the right two heads', () => {
    pitch()
    expect(screen.getByTitle('Captain')).toBeInTheDocument()
    expect(screen.getByTitle('Vice-captain')).toBeInTheDocument()
  })

  it('gives a benched captain his armband too', () => {
    // Rare and real: a captain the solver benched should not silently lose
    // the band on the one screen that shows it.
    pitch({ captain: 12 })
    const strip = screen.getByTestId('bench-strip')
    expect(within(strip).getByTitle('Captain')).toBeInTheDocument()
  })

  it('carries a doubtful player’s flag onto the pitch', () => {
    pitch({ xi: [...XI.slice(0, 5), row({ code: 6, name: 'Saka',
                                          position: 'MID',
                                          news: 'Knock',
                                          chanceOfPlaying: 50 }),
                 ...XI.slice(6)] })
    expect(screen.getByText('50%')).toBeInTheDocument()
  })

  it('says Blank for a player whose team does not play', () => {
    pitch({ xi: [row({ code: 1, name: 'Raya', position: 'GKP',
                       nextFixture: null }), ...XI.slice(1)] })
    expect(screen.getAllByText('Blank')).toHaveLength(1)
  })

  it('renders with no identity at all, as a cold clone would', () => {
    // Every new field null: no snapshot, no fixtures, no ticker. The pitch is
    // still a pitch.
    pitch({
      xi: XI.map((p) => ({ ...p, teamShort: null, teamCode: null,
                           nextFixture: null })),
      bench: [],
    })
    expect(screen.getByTestId('pitch-row-GKP')).toBeInTheDocument()
    expect(screen.getAllByText('Blank').length).toBeGreaterThan(0)
  })
})
```

Run it: `cd frontend && npx vitest run src/hubs/this-week/SquadPitch.test.tsx`.

- [ ] **Widen the row type.** In `frontend/src/hubs/this-week/SquadTable.tsx`, add three fields to the end of `SquadRow` (L7-26). **Nothing else in that file changes** — no new column, no new render (D3: "SquadTable is unchanged"):

```ts
  penalties: boolean
  /** v9a identity, resolved server-side. The table does not draw any of
   *  these — they live here because the pitch and the table render from one
   *  array, and one row type is the whole reason the toggle is a toggle
   *  rather than two data paths. */
  teamShort: string | null
  teamCode: number | null
  nextFixture: NextFixture | null
```

and extend the file's import at L1-5 with the type:

```ts
import type { NextFixture } from '../../types'
```

- [ ] **Implement.** Create `frontend/src/hubs/this-week/SquadPitch.tsx`:

```tsx
import { PlayerCard } from '../../kit'
import type { SquadRow } from './SquadTable'

/**
 * The XI on a pitch and the bench underneath it, the way FPL draws its own.
 *
 * Four formation rows read off the XI's positions rather than a formation
 * string, because the solver does not emit one and inferring "3-5-2" from
 * eleven positions only to expand it back into rows would be a round trip
 * through a number nobody needs. A line nobody is playing is omitted rather
 * than drawn empty, and a player the artifact gave no position lands in one
 * unstructured row at the bottom — losing him off the pitch entirely would be
 * worse than an ugly extra row, and advice written before v3.1 has no
 * positions at all.
 *
 * The bench is a strip below the grass in the order the payload lists it
 * (GK first, then outfield in bench order), because that order is the
 * substitution priority and re-sorting it would destroy the only information
 * the sequence carries.
 *
 * Every card is `kit/PlayerCard`; nothing about a player is drawn here.
 */

const LINES = ['GKP', 'DEF', 'MID', 'FWD'] as const

export interface SquadPitchProps {
  xi: SquadRow[]
  bench: SquadRow[]
  captain: number
  vice: number
  onSelect?: (code: number) => void
}

function armbandFor(code: number, captain: number,
                    vice: number): 'C' | 'V' | null {
  if (code === captain) return 'C'
  if (code === vice) return 'V'
  return null
}

export default function SquadPitch(
  { xi, bench, captain, vice, onSelect }: SquadPitchProps,
) {
  const loose = xi.filter((p) => !LINES.includes(p.position as never))
  const rows: Array<[string, SquadRow[]]> = [
    ...LINES.map((line) =>
      [line, xi.filter((p) => p.position === line)] as [string, SquadRow[]]),
    ['OTHER', loose] as [string, SquadRow[]],
  ].filter(([, players]) => players.length > 0)

  const card = (player: SquadRow) => (
    <PlayerCard
      key={player.code}
      code={player.code}
      name={player.name}
      position={player.position}
      teamShort={player.teamShort}
      teamCode={player.teamCode}
      ep={player.ep}
      fixture={player.nextFixture}
      armband={armbandFor(player.code, captain, vice)}
      news={player.news}
      chanceOfPlaying={player.chanceOfPlaying}
      onSelect={onSelect}
    />
  )

  return (
    <div>
      <div
        className="flex flex-col justify-between gap-3 rounded-card px-2 py-3"
        // The grass. A gradient rather than a flat green so the four bands
        // read as depth, and a token-free literal because this is the one
        // surface on the page that is not part of the palette — a pitch is
        // green in both themes.
        style={{
          background:
            'linear-gradient(to bottom, #1f6b3a 0%, #2a8049 55%, #1f6b3a 100%)',
        }}
      >
        {rows.map(([line, players]) => (
          <div key={line} data-testid={`pitch-row-${line}`}
               className="flex flex-wrap justify-center gap-1.5">
            {players.map(card)}
          </div>
        ))}
      </div>
      {bench.length > 0 && (
        <div data-testid="bench-strip"
             className="mt-2 rounded-card border border-border bg-surface
                        px-2 py-2">
          <p className="label mb-1">Bench</p>
          <div className="flex flex-wrap justify-center gap-1.5">
            {bench.map(card)}
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Verify.** `SquadTable`'s own suite must still pass untouched — its test file builds `SquadRow`s through a `row()` helper, which will need the three fields added to its defaults. That is a test-fixture edit, not a component change:

```bash
cd frontend && npx tsc --noEmit \
  && npx vitest run src/hubs/this-week/SquadPitch.test.tsx \
       src/hubs/this-week/SquadTable.test.tsx
```

If `SquadTable.test.tsx` fails to compile, add `teamShort: null, teamCode: null, nextFixture: null` to its `ROWS` entries and its `row()` default (SquadTable.test.tsx:6, :72) and nothing else.

- [ ] **Commit.**

```bash
git add frontend/src/hubs/this-week/SquadPitch.tsx \
  frontend/src/hubs/this-week/SquadPitch.test.tsx \
  frontend/src/hubs/this-week/SquadTable.tsx \
  frontend/src/hubs/this-week/SquadTable.test.tsx \
  && git commit -m "$(cat <<'EOF'
feat: SquadPitch — the XI in formation rows with the bench as a bench

Four rows read off the XI's own positions rather than a formation string the
solver does not emit; an unplayed line is omitted rather than drawn empty, and
a player with no position lands in a row of his own rather than off the pitch.
The bench keeps payload order, because that order is the substitution
priority. SquadRow gains the three identity fields so the pitch and the table
render from one array.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 6 — This Week: the pitch by default, the table one click away

**Files:**
- Modify `frontend/src/hubs/ThisWeek.tsx`
- Modify `frontend/src/hubs/ThisWeek.test.tsx`

Read A11 first. This Week today draws the XI twice — once as `kit/PitchView` in a "Starting XI" card and once inside `SquadTable`'s "Squad" card. The new pitch shows the XI *and* the bench, so the two cards collapse into one and the toggle chooses what fills it.

- [ ] **Write the failing test.** Add to `frontend/src/hubs/ThisWeek.test.tsx` (keep every existing test; extend the MSW advice fixture so its `xi`/`bench` entries carry `team_short`, `team_code` and `next_fixture`):

```tsx
describe('the pitch and the table', () => {
  it('shows the pitch by default, with the bench on it', async () => {
    // D3: the pitch is This Week's default. The table is a click away and
    // stays the data-dense view.
    render(<ThisWeek />)
    expect(await screen.findByTestId('pitch-row-GKP')).toBeInTheDocument()
    expect(screen.getByTestId('bench-strip')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('draws each XI player exactly once', async () => {
    // The regression A11 exists to prevent: two cards, both drawing the XI.
    render(<ThisWeek />)
    await screen.findByTestId('pitch-row-GKP')
    expect(screen.getAllByText('Saka')).toHaveLength(1)
  })

  it('switches to the table and back', async () => {
    render(<ThisWeek />)
    fireEvent.click(await screen.findByRole('button', { name: 'Table' }))
    expect(await screen.findByRole('table')).toBeInTheDocument()
    expect(screen.queryByTestId('pitch-row-GKP')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Pitch' }))
    expect(await screen.findByTestId('pitch-row-GKP')).toBeInTheDocument()
  })

  it('says which view is showing', async () => {
    render(<ThisWeek />)
    const pitch = await screen.findByRole('button', { name: 'Pitch' })
    expect(pitch).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Table' }))
      .toHaveAttribute('aria-pressed', 'false')
  })

  it('carries the fixture chips onto the pitch', async () => {
    render(<ThisWeek />)
    expect(await screen.findByText(/MUN \(H\)/)).toBeInTheDocument()
  })

  it('renders the pitch when the advice carries no identity at all', async () => {
    // An advice payload served by a backend that could not read a single
    // snapshot: three undefined fields on every entry. The page is a page.
    server.use(http.get('/api/advice/latest', () =>
      HttpResponse.json(adviceWithout(['team_short', 'team_code',
                                       'next_fixture']))))
    render(<ThisWeek />)
    expect(await screen.findByTestId('pitch-row-GKP')).toBeInTheDocument()
    expect(screen.getAllByText('Blank').length).toBeGreaterThan(0)
  })

  it('keeps the captain line and the odds chip above the pitch', async () => {
    render(<ThisWeek />)
    await screen.findByTestId('pitch-row-GKP')
    expect(screen.getByText(/Captain/)).toBeInTheDocument()
  })
})
```

Add the small helper this file needs beside its existing fixtures:

```tsx
/** The advice fixture with named identity fields stripped, for the
 *  cold-backend case. */
function adviceWithout(fields: string[]) {
  const strip = (p: Record<string, unknown>) => {
    const out = { ...p }
    for (const f of fields) delete out[f]
    return out
  }
  const advice = { ...ADVICE_FIXTURE.advice }
  advice.xi = advice.xi.map(strip)
  advice.bench = advice.bench.map(strip)
  return { ...ADVICE_FIXTURE, advice }
}
```

- [ ] **Implement.** In `frontend/src/hubs/ThisWeek.tsx`:

Change the kit import (L3-6) — `PitchView` goes, nothing replaces it there:

```tsx
import {
  Card, EmptyState, JobButton, Loading, PageHeader, Stat,
  ThresholdBar, fmtNum, fmtPct,
} from '../kit'
```

Add the pitch import beside the other this-week imports (after L15):

```tsx
import SquadPitch from './this-week/SquadPitch'
```

Add the view state beside the other `useState` calls (after L29):

```tsx
  // Pitch by default (spec D3). Component state, not localStorage: persisting
  // a view preference is a real feature with real questions behind it
  // (per hub? per device? across a rebuild?) and inventing an answer inside a
  // lean UI cycle is how a preference store gets built by accident.
  const [view, setView] = useState<'pitch' | 'table'>('pitch')
```

Carry the three new fields into the row mapping (inside the `squad` map, L108-128, after `penalties`):

```tsx
      penalties: (row?.penalties_order ?? 0) === 1,
      // Resolved server-side and passed straight through. `?? null` rather
      // than a default: an advice payload served by a backend that could read
      // no snapshot has these undefined, and the pitch's honest answer to
      // that is a plain shirt and the word "Blank" — not an invented club.
      teamShort: p.team_short ?? null,
      teamCode: p.team_code ?? null,
      nextFixture: p.next_fixture ?? null,
```

and split the array so the pitch can tell the XI from the bench. Immediately after the `squad` map (L129), add:

```tsx
  // One array, two views. The pitch needs the split; the table wants the
  // whole squad in one sortable body, exactly as it always has.
  const xiCodes = new Set(advice.xi.map((p) => p.code))
  const pitchXi = squad.filter((r) => xiCodes.has(r.code))
  const pitchBench = squad.filter((r) => !xiCodes.has(r.code))
```

Replace both cards (L196-228) with the single hosting card:

```tsx
      {/* One card, two views (plan A11). The XI used to be drawn twice — as a
          bare pitch here and again inside the squad table below — and the new
          pitch carries the bench too, so a third rendering would be absurd.
          SquadTable is untouched; it is simply rendered from a different
          parent. */}
      <Card
        title="Squad"
        className="mb-4"
        action={(
          <span className="flex flex-wrap items-center gap-3
                           text-text-muted">
            <span>
              Captain {advice.captain.name}
              {advice.scenarios?.captain_frequency !== undefined
                && ` · ${fmtPct(advice.scenarios.captain_frequency)} of sims`}
              {' · vice '}{advice.vice.name}
              {capOdds !== null && (
                // Whole percentage points. At n = 2,000 the Monte Carlo
                // standard error on a probability near 0.5 is about 0.9pp, so
                // a tenth of a point here is a digit the instrument does not
                // have — and this chip is a glance, not a measurement.
                <span className="ml-2" data-testid="captain-odds-chip">
                  {`· ${capOdds >= 0 ? '+' : ''}`}
                  {`${Math.round(capOdds * 100)}pp `}
                  {'title odds vs vice'}
                </span>
              )}
            </span>
            <span className="flex overflow-hidden rounded-card
                             border border-border">
              {(['pitch', 'table'] as const).map((option) => (
                <button
                  key={option}
                  type="button"
                  aria-pressed={view === option}
                  onClick={() => setView(option)}
                  className={'px-2 py-0.5 capitalize '
                    + (view === option
                      ? 'bg-card text-text'
                      : 'text-text-muted hover:text-text')}
                >
                  {option === 'pitch' ? 'Pitch' : 'Table'}
                </button>
              ))}
            </span>
          </span>
        )}
      >
        {view === 'pitch'
          ? (
            <SquadPitch
              xi={pitchXi}
              bench={pitchBench}
              captain={advice.captain.code}
              vice={advice.vice.code}
            />
            )
          : <SquadTable rows={squad} breakdown={breakdown} />}
        <ConfidenceLine />
      </Card>
```

- [ ] **Verify.**

```bash
cd frontend && npx tsc --noEmit \
  && npx vitest run src/hubs/ThisWeek.test.tsx \
       src/hubs/this-week/SquadPitch.test.tsx \
       src/hubs/this-week/SquadTable.test.tsx \
       src/kit/PitchView.test.tsx src/kit/index.test.ts \
  && npx vitest run && npm run build
```

The full frontend run must be 460 + 1 skipped + this cycle's new tests, all green. `kit/PitchView` is now unrendered but still exported and still tested — that is deliberate (A1) and its suite must stay green.

- [ ] **Commit.**

```bash
git add frontend/src/hubs/ThisWeek.tsx frontend/src/hubs/ThisWeek.test.tsx \
  && git commit -m "$(cat <<'EOF'
feat: This Week opens on the pitch, with the table one click away

The Starting XI card and the Squad card collapse into one: the new pitch
carries the bench, so keeping both would have drawn the XI three times. A
segmented Pitch|Table toggle sits in the card's action line beside the captain
and the title-odds chip, defaulting to the pitch. SquadTable is unchanged.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 7 — the degradation rails (gate G2)

**Files:**
- Create `tests/test_v9a_degradation.py`

Every rail is a state a real machine reaches: an evening with no network, a `data/` directory a user cleaned out, a bootstrap from an older cache, a blank gameweek. The suite exists so that none of them is a broken-image icon on the pitch or a 500 on the page that draws it.

The last two are pins rather than degradations. Nothing about the job kinds or the config fields moved this cycle, and asserting the *unchanged* numbers from this cycle's own file is what makes the next cycle's accidental addition fail here rather than in six older ones.

- [ ] **Write it.** Create `tests/test_v9a_degradation.py`:

```python
"""v9a degradation rails (gate G2).

The pitch is decoration over a page that already worked, so every rail here
asks the same question of a different missing thing: does This Week still
render? The answer has to be the same every time — a plain shirt, a chip that
says "Blank", a printed line on the server — and never a 500, never a
traceback, and never a broken image.

The two pins at the end are not degradations. The job-kind count and the
config-field count did **not** move this cycle (spec §2: no new job kinds, no
new config keys), and asserting the unchanged numbers from this cycle's own
file is what makes the next cycle's accidental addition fail in its own suite
rather than in six older ones.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.data import store
from gaffer.web.app import create_app
from gaffer.web.routers import assets

GW = 5

PLAYERS = pd.DataFrame({
    "code": [11, 22], "name": ["Saka", "Haaland"],
    "position": ["MID", "FWD"], "team_id": [1, 13], "team_code": [3, 43],
    "now_cost": [101, 150], "selected_by_percent": [40.0, 60.0],
})
TEAMS = pd.DataFrame({"team_id": [1, 13, 14], "code": [3, 43, 1],
                      "name": ["Arsenal", "Man City", "Man Utd"],
                      "short_name": ["ARS", "MCI", "MUN"]})
FIXTURES = pd.DataFrame({
    "gw": [GW], "home_id": [1], "away_id": [14],
    "kickoff_time": ["2026-09-12T14:00:00Z"],
    "home_goals": [None], "away_goals": [None], "finished": [False]})

ADVICE = {
    "gw": GW, "hits": 0, "expected_pts": 54.3,
    "xi": [{"code": 11, "name": "Saka", "position": "MID", "ep": 5.1}],
    "bench": [{"code": 22, "name": "Haaland", "position": "FWD", "ep": 6.2}],
    "buys": [], "sells": [],
    "captain": {"code": 11, "name": "Saka", "position": "MID", "ep": 5.1},
    "vice": {"code": 22, "name": "Haaland", "position": "FWD", "ep": 6.2},
    "chip_table": [], "strategy": None,
}

PRE_EXISTING = ("code", "name", "position", "ep")
"""What an advice player entry carried before this cycle. The enrichment is
additive, and this tuple is how the byte-identity rail says so."""


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    from gaffer.artifacts import SolveState, save_solve_state

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    (tmp_path / "data" / "live").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    TEAMS.to_parquet(tmp_path / "data/live/teams.parquet", index=False)
    FIXTURES.to_parquet(tmp_path / "data/live/fixtures_all.parquet",
                        index=False)
    (tmp_path / "reports" / f"gw{GW}-advice.json").write_text(
        json.dumps(ADVICE))
    save_solve_state(SolveState(
        gw=GW, gws=[GW], deadline="2026-09-11T17:30:00Z",
        generated_at="2026-09-10T20:00:00+00:00", mode="weekly", bank=0.5,
        free_transfers=1, owned_codes=[11, 22], lam=0.0, league_eo={},
        cover={}, avail_by_gw={}, opt={},
        pool=pd.DataFrame({"code": [11, 22], "position": ["MID", "FWD"]})))
    monkeypatch.setattr(assets, "_fetch", lambda url: b"fake-image-bytes")
    return tmp_path, TestClient(create_app())


# --- rail 1: a dead upstream --------------------------------------

def test_a_dead_cdn_serves_the_bundled_fallback_with_a_short_max_age(
        wired, monkeypatch):
    """G2, first clause. The pitch renders identically with zero network."""
    _tmp, client = wired
    monkeypatch.setattr(assets, "_fetch", lambda url: (_ for _ in ()).throw(
        RuntimeError("network is unreachable")))
    response = client.get("/api/assets/shirt/3")
    assert response.status_code == 200
    assert b"<svg" in response.content
    assert "max-age=60" in response.headers["cache-control"]


def test_a_dead_cdn_writes_nothing_at_all(wired, monkeypatch):
    tmp_path, client = wired
    monkeypatch.setattr(assets, "_fetch", lambda url: (_ for _ in ()).throw(
        RuntimeError("network is unreachable")))
    client.get("/api/assets/shirt/3")
    client.get("/api/assets/photo/11")
    cache = tmp_path / "data/live/assets"
    assert not cache.exists() or list(cache.iterdir()) == []


def test_a_cache_hit_never_refetches(wired, monkeypatch):
    _tmp, client = wired
    client.get("/api/assets/shirt/3")
    monkeypatch.setattr(assets, "_fetch", lambda url: (_ for _ in ()).throw(
        AssertionError("a cache hit refetched")))
    assert client.get("/api/assets/shirt/3").status_code == 200


# --- rail 2: the allowlist and the path ---------------------------

@pytest.mark.parametrize("path", [
    "/api/assets/shirt/../../etc/passwd",
    "/api/assets/shirt/..%2F..%2Fetc%2Fpasswd",
    "/api/assets/photo/../../../secret",
    "/api/assets/shirt/3.webp",
])
def test_path_traversal_is_refused_before_any_handler_runs(wired, path):
    tmp_path, client = wired
    assert client.get(path).status_code in (404, 422)
    assert not (tmp_path / "data/live/assets").exists()


def test_a_code_outside_the_bootstrap_is_refused_without_a_fetch(wired,
                                                                 monkeypatch):
    """Not an open proxy (spec §2)."""
    _tmp, client = wired
    monkeypatch.setattr(assets, "_fetch", lambda url: (_ for _ in ()).throw(
        AssertionError("fetched for a code the bootstrap does not know")))
    assert client.get("/api/assets/shirt/999").status_code == 404
    assert client.get("/api/assets/photo/999999").status_code == 404


# --- rail 3: a corrupt or absent fixture list ---------------------

def test_a_corrupt_fixture_file_nulls_every_next_fixture(wired):
    tmp_path, client = wired
    (tmp_path / "data/live/fixtures_all.parquet").write_bytes(b"not parquet")
    advice = client.get("/api/advice/latest").json()["advice"]
    assert advice["xi"][0]["next_fixture"] is None
    assert advice["bench"][0]["next_fixture"] is None


def test_an_absent_fixture_file_nulls_every_next_fixture(wired):
    tmp_path, client = wired
    (tmp_path / "data/live/fixtures_all.parquet").unlink()
    advice = client.get("/api/advice/latest").json()["advice"]
    assert advice["xi"][0]["next_fixture"] is None


def test_the_squad_payloads_pre_existing_fields_survive_a_broken_fixture_file(
        wired):
    """G2's byte-identity clause: everything that was there is still there,
    with the same values, and only the three new keys are added."""
    tmp_path, client = wired
    (tmp_path / "data/live/fixtures_all.parquet").unlink()
    advice = client.get("/api/advice/latest").json()["advice"]
    for key in ("xi", "bench"):
        for served, original in zip(advice[key], ADVICE[key]):
            assert all(served[f] == original[f] for f in PRE_EXISTING)
            assert set(served) - set(original) == {"team_short", "team_code",
                                                   "next_fixture"}


def test_a_blank_gameweek_is_a_null_fixture_not_a_zero(wired):
    """D2: the chip says "blank" honestly."""
    _tmp, client = wired
    advice = client.get("/api/advice/latest").json()["advice"]
    # Man City have no GW5 fixture in the banked list.
    assert advice["bench"][0]["team_short"] == "MCI"
    assert advice["bench"][0]["next_fixture"] is None


# --- rail 4: a bootstrap without team identity --------------------

def test_a_players_snapshot_without_team_code_is_nulls_not_a_raise(wired):
    tmp_path, client = wired
    PLAYERS.drop(columns=["team_code"]).to_parquet(
        tmp_path / "data/live/players.parquet", index=False)
    advice = client.get("/api/advice/latest").json()["advice"]
    assert advice["xi"][0]["team_code"] is None
    assert advice["xi"][0]["team_short"] is None


def test_an_absent_teams_snapshot_is_nulls_not_a_raise(wired):
    tmp_path, client = wired
    (tmp_path / "data/live/teams.parquet").unlink()
    advice = client.get("/api/advice/latest").json()["advice"]
    assert advice["xi"][0]["team_short"] is None


def test_a_clone_with_no_snapshots_at_all_still_serves_the_advice(wired):
    """The coldest case: the artifact is on disk and nothing else is."""
    tmp_path, client = wired
    for name in ("players", "teams", "fixtures_all"):
        (tmp_path / f"data/live/{name}.parquet").unlink()
    body = client.get("/api/advice/latest").json()
    assert body["advice"]["xi"][0]["name"] == "Saka"
    assert body["advice"]["xi"][0]["team_short"] is None


# --- rail 5: an unrateable fixture --------------------------------

def test_a_fixture_the_ticker_cannot_rate_keeps_the_chip_and_loses_the_tint(
        wired, monkeypatch):
    from gaffer.web.routers import meta

    _tmp, client = wired
    monkeypatch.setattr(meta, "ticker", lambda weeks=8: (_ for _ in ()).throw(
        RuntimeError("no odds, no elo")))
    fixture = client.get("/api/advice/latest").json()[
        "advice"]["xi"][0]["next_fixture"]
    assert fixture["opponent_short"] == "MUN"
    assert fixture["difficulty"] is None


# --- rail 6: the artifact is never rewritten ----------------------

def test_serving_the_pitch_never_touches_the_advice_artifact(wired):
    """A2. The enrichment is a decoration on the way out; the file the next
    ``advise`` run diffs against must be byte-identical."""
    tmp_path, client = wired
    path = tmp_path / "reports" / f"gw{GW}-advice.json"
    before = path.read_bytes()
    client.get("/api/advice/latest")
    client.get("/api/advice/latest")
    assert path.read_bytes() == before


# --- pins: nothing moved this cycle -------------------------------

def test_the_job_kinds_are_still_twelve(wired):
    """Spec §2: no new job kinds. The pitch is a read, not a run."""
    from gaffer.web.job_kinds import JOB_KINDS

    assert len(JOB_KINDS) == 12


def test_the_config_still_has_no_assets_section(wired):
    """A7: the CDN bases are module constants, deliberately, because a config
    key would have broken a count pin inside a protected rail file."""
    from gaffer.config import Config

    assert not any(f.startswith("assets") for f in Config.__dataclass_fields__)


def test_the_asset_router_is_the_only_new_route_prefix(wired):
    _tmp, client = wired
    paths = {r.path for r in client.app.routes if hasattr(r, "path")}
    new = {p for p in paths if p.startswith("/api/assets")}
    assert new == {"/api/assets/shirt/{team_code}",
                   "/api/assets/photo/{player_code}"}
```

- [ ] **Verify — the new rails and every pre-existing rail file together.**

```bash
uv run pytest -q tests/test_v9a_degradation.py
uv run pytest -q tests/ -k degradation
```

Every pre-existing `test_*_degradation.py` is protected and must pass **unmodified**. If one of them fails, this cycle has broken something it promised not to: stop and report rather than editing the rail.

- [ ] **Commit.**

```bash
git add tests/test_v9a_degradation.py && git commit -m "$(cat <<'EOF'
test: v9a degradation rails

A dead CDN, a corrupt fixture list, a bootstrap with no team_code, a clone
with no snapshots at all, path traversal, and an unrateable fixture — each
asked whether This Week still renders. Plus two pins for things that did not
move: twelve job kinds, no [assets] config section.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 8 — the documentation

**Files:**
- Modify `README.md`

- [ ] **Add an Assets entry to the artifact and store list** (the section listing `data/live/*` files), in the existing voice:

```markdown
- `data/live/assets/` — cached shirt and player images, fetched once from the
  official Premier League CDN by `/api/assets/` and served from disk
  afterwards. Untracked like the rest of `data/`, never redistributed, and
  entirely disposable: delete the directory and the next page load refills
  it. With no network the endpoint serves a bundled plain shirt and
  silhouette instead, so the pitch renders identically offline.
```

- [ ] **Describe the pitch in the This Week section:** two or three sentences saying that This Week opens on a pitch — the XI in formation rows, the bench below it in substitution order, captain and vice armbands, and a per-player chip naming the next opponent, the side and the kickoff, tinted by the *ticker's* odds-implied difficulty rather than FPL's FDR. Say that a player whose team has no fixture reads "Blank" rather than showing an empty chip, and that the **Table** toggle returns the data-dense view unchanged.

- [ ] **Add a sentence on the licensing posture** beside the assets entry: player and kit imagery is Premier League property; the local cache is a single-user copy for personal display, is untracked, and nothing here redistributes it.

- [ ] **Commit.**

```bash
git add README.md && git commit -m "$(cat <<'EOF'
docs: v9a — the pitch, the asset cache, and what it does offline

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 9 — the gate checklist (orchestrator-run, unfilled)

**Files:**
- Modify `docs/superpowers/specs/2026-08-31-gaffer-v9a-pitch-view-design.md` (§5)

CONVENTIONS.md §7: the implementer builds this and does not run it. Fill in the **measured** G3 numbers below from your own final run; leave every G1 box unchecked.

- [ ] **G3 first — suites, types, build, and the protected audit.** Run these and record the real counts:

```bash
uv run pytest -q
cd frontend && npx tsc --noEmit && npx vitest run && npm run build
```

Baselines to beat: 2664 python tests and 460 frontend + 1 skipped, plus this cycle's new tests, all green.

Then the protected diff, which must be **empty** — this cycle authorized no exceptions:

```bash
git diff main --stat -- src/gaffer/advise.py src/gaffer/set_pieces.py \
  'src/gaffer/optimize/**' src/gaffer/web/jobs.py \
  src/gaffer/web/routers/jobs.py src/gaffer/web/routers/whatif.py \
  tests/test_advise.py tests/test_odds.py tests/test_web_jobs.py \
  scripts/s2_replay.py
# must be empty

git diff main --stat -- 'tests/test_*_degradation.py'
# must name tests/test_v9a_degradation.py and nothing else
```

And the pin audit — no counts moved this cycle, so this is a zero:

```bash
git diff main -- tests/test_web_job_kinds.py tests/test_web_job_kinds_v8b.py \
  tests/test_web_job_kinds_v8c.py tests/test_web_job_kinds_v8f.py \
  src/gaffer/config.py config.example.toml
# must be empty
```

Security ritual (CONVENTIONS.md §8): grep the whole branch diff for keys and tokens, confirm no `data/`, `reports/`, `models/`, `logs/` or `config.toml` path appears in `git diff main --stat`, and confirm `git show main:config.toml` fails.

- [ ] **Write §5 into the spec file.** Replace the spec's §5 placeholder with the checklist below, with the G3 numbers filled in from the run above and every G1 box left unchecked.

```markdown
## 5. Gate checklist (built by the implementer, run by the orchestrator)

**G3 — suites, types, build, audit (measured by the implementer):**

- [x] `uv run pytest -q` — <N> passed (main baseline 2664 + <new> new)
- [x] `npx tsc --noEmit` — clean
- [x] `npx vitest run` — <N> passed, 1 skipped (main baseline 460 + <new> new)
- [x] `npm run build` — clean
- [x] Protected diff empty: advise.py, set_pieces.py, optimize/**, jobs.py,
      routers/jobs.py, routers/whatif.py, test_advise.py, test_odds.py,
      test_web_jobs.py, every pre-v9a test_*_degradation.py, s2_replay.py
- [x] Pin diff empty: no job-kind count moved (still 12), no config field
      added, config.example.toml untouched
- [x] Security ritual clean; no data/, reports/, models/, logs/ or config.toml
      in the branch diff

**G1 — live, real season (orchestrator only):**

- [ ] Open This Week: the pitch is the default view, the advised XI is laid
      out in four formation rows, the bench sits below it in bench order.
- [ ] C and V badges sit on the two heads the plan names.
- [ ] Every shirt is real. Network tab: every image request goes to
      `/api/assets/…` and **none** to premierleague.com or
      resources.premierleague.com.
- [ ] The fixture chips name the actual GW opponents with real kickoffs in
      local time, tinted by difficulty.
- [ ] A team with a blank gameweek reads "Blank" rather than an empty chip.
- [ ] Kill the network and reload: plain shirts and silhouettes, **no**
      broken-image icons, **no** console errors.
- [ ] `ls data/live/assets/` shows banked files; reload with the network back
      and the server log shows no refetch for a code already banked.
- [ ] Toggle to Table — the squad table renders exactly as it did before this
      cycle — and back to Pitch.
- [ ] A doubtful player carries his news flag on the pitch card.
- [ ] `curl -s -o /dev/null -w '%{http_code}' localhost:8927/api/assets/shirt/999`
      is 404, and the same for a photo code outside the bootstrap.

**G2 — rails:** `uv run pytest -q tests/test_v9a_degradation.py`, plus every
pre-existing `test_*_degradation.py` unmodified.
```

- [ ] **Fill spec §4 (Outcome)** with what shipped, what did not, and any residual — and, per CONVENTIONS.md §4, transcribe the G1 evidence verbatim rather than summarising it. (Orchestrator, after G1.)

- [ ] **Commit the checklist.**

```bash
git add docs/superpowers/specs/2026-08-31-gaffer-v9a-pitch-view-design.md \
  && git commit -m "$(cat <<'EOF'
docs: v9a gate checklist with the measured G3 numbers, G1 unfilled

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Notes for the implementer

- **Task order matters in three places.** Task 2 must precede Task 3 (the types mirror a schema that has to exist). Task 4 must precede Task 5 (`SquadPitch` renders `PlayerCard`). Task 5 must precede Task 6 (This Week renders `SquadPitch`). Task 1 is independent of all of them and can go first or in parallel; Tasks 7 and 8 need everything before them.
- **There is no stop-point in this cycle.** No config key, no job kind, no plist, no protected edit. If a task finds itself wanting one, the plan is wrong: stop and report. In particular, a `[assets] base_url` key would break a count pin inside `tests/test_v8f_degradation.py`, which is protected — A7 explains why the bases are module constants instead.
- **`advise.py` stays narrow on purpose.** The advice artifact's player entries are still `{code, name, position, ep}` on disk, and the pitch's three fields are added on the way out of the route. That is not a workaround to be tidied up later — it is what makes every advice file already banked render on the new pitch without a re-solve, and it is what keeps the "since last run" diff comparing like with like.
- **`kit/PitchView` is not deleted.** It stops being rendered and stays exported, tested and pinned (A1). Consolidating the two pitch components is a v9b decision to be made with both of them in front of you.
- **Never stage a cached image.** `data/live/assets/` fills up the moment you open This Week. `git add` in this plan names exact files; the only images this cycle commits are the two hand-written SVGs under `src/gaffer/assets/`.
