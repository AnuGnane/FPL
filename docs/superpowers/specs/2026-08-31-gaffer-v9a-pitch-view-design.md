# gaffer v9a — pitch view

Date: 2026-08-31. Parent: user request post-v8 ("next game the player play on the starting xi tab integrated in aswell as the sub bench - similar to how FPL already show it ... the kit and pictures of the player"). Lean UI cycle.
Goal: give This Week an FPL-style pitch — shirts/photos, team names, captain/vice armbands, a per-player next-fixture chip, and the bench as a bench — without touching the model or the solver.

## 0. Decisions

- **D1 — Assets come through a backend cache, never hotlinked from the browser.** The frontend speaks only to the FastAPI backend today (every byte via `/api/*` or the bundled static dir); the pitch keeps that posture. New `GET /api/assets/shirt/{team_code}` and `GET /api/assets/photo/{player_code}`: on first request the backend fetches from the official CDN, banks the bytes under `data/live/assets/` (untracked, like all of `data/`), and serves from disk forever after with long-lived cache headers; on fetch failure it serves a bundled neutral-silhouette/plain-shirt SVG with a short max-age — the pitch renders identically with zero network. **Verified URL patterns** (curl, 2026-08-31): photos `https://resources.premierleague.com/premierleague/photos/players/110x140/p{player_code}.png` → 200 `image/png` (p223094 = Haaland); outfield shirts `https://fantasy.premierleague.com/dist/img/shirts/standard/shirt_{team_code}-66.webp` → 200 `image/webp` (43 = MCI); keeper variant `shirt_{team_code}_1-66.webp` → 200 (verified 43_1, 3_1). `player_code` and `team_code` are both already in the banked bootstrap (`elements[].code`, `elements[].team_code`, `teams[].code`). Licensing note: player and kit imagery is Premier League property — a local single-user cache for personal display is the same use the official site makes, but the cache stays untracked and is never redistributed.
- **D2 — The squad payload grows identity and fixture fields; nothing is recomputed.** `SquadRow` (schemas.py, additive) gains `team_short: str | None`, `team_code: int | None`, and `next_fixture: NextFixture | None` where `NextFixture = {opponent_short, home: bool, kickoff_utc, difficulty: float | None}`. All four resolve at serve time from data the backend already banks: bootstrap for team identity, `live/fixtures_all.parquet` for the first unfinished fixture per team in the advice GW, and the ticker's odds-implied difficulty (meta.py already rates each fixture 0–1 from the home side — the chip reuses that number and its colour scale rather than FPL's cruder FDR). A player whose team has no fixture that GW gets `next_fixture: null` and the chip says "blank" honestly. DGW: `next_fixture` stays the *first* fixture and gains nothing else this cycle.
- **D3 — PitchView is the This Week default; the table is one click away.** New `frontend/src/hubs/this-week/PitchView.tsx`: green-gradient pitch, four formation rows (GK/DEF/MID/FWD from the XI's positions), bench strip below in bench order (GK first, then outfield in listed order), each player a `PlayerCard` — shirt (photo on tap/hover is out; the card IS the shirt per FPL's own pitch), web name plate, team short-name, EP, the next-fixture chip ("MCI (H) Sat 15:00", difficulty-tinted), C/V armband badges from the plan's captain/vice, and the existing news/doubt flag idiom. A segmented Pitch|Table toggle sits above; SquadTable is unchanged and remains the data-dense view. Multiplier styling (TC/BB) only if the plan payload already names the chip — no new chip plumbing.
- **D4 — One shared PlayerCard, sized for reuse.** The card is a kit-level component (`frontend/src/kit/PlayerCard.tsx`) with `size: 'pitch' | 'chip'` so v9b can reuse it in Live, the league compare and the review lanes without a redesign. This cycle wires it into the pitch only.
- **D5 — v9b polish backlog** (ranked; recorded here, built later): (1) reuse PlayerCard identity across Live/League/Review so every player mention carries shirt + team; (2) skeleton/loading states for job-triggered panels — buttons fire jobs but panels sit blank while polling; (3) mobile pass over the v8 additions (DigestCard, race chart, calibration cards) which were desktop-first; (4) toast feedback on star/pin/override actions — today the only acknowledgement is a server-side print; (5) empty-state copy audit extending the cold-clone idiom to the v8 cards; (6) chart-token unification so sparklines, bands and reliability curves share one axis/colour grammar; (7) light-theme audit of v8 cards for hard-coded dark tokens; (8) fixture-difficulty tinting reused on Planning's horizon table.

## 1. Gates (orchestrator-run)

- **G1 (live)** — real season: open This Week and see the pitch by default with the current advised XI in four rows, bench below, C/V badges on the right heads, every shirt real (network tab: all images from `/api/assets/`, none from premierleague.com); the next-fixture chips name the actual GW3 opponents with kickoffs; kill the network (or point the CDN base at a dead host) and reload — silhouettes/plain shirts, no broken-image icons, no console errors; toggle to Table and back; a doubtful player carries his flag on the pitch.
- **G2 (rails)** — `tests/test_v9a_degradation.py`: asset endpoint with dead upstream ⇒ bundled fallback bytes, 200, short max-age, nothing written; corrupt/absent `fixtures_all` ⇒ `next_fixture` null for all rows, squad panel otherwise byte-identical in its pre-existing fields; bootstrap missing `team_code` ⇒ nulls, no raise; cache hit never refetches (spy); path traversal in `{code}` rejected; the squad payload's pre-existing fields byte-identical to main for the same inputs; protected-ordering pins forward. Job kinds stay 12 — no pin updates this cycle.
- **G3 (suites + audit)** — full suites, tsc, build, zero protected diffs, zero pin diffs, security greps clean.

## 2. Constraints

Protected list as prior cycles (advise.py, set_pieces.py, optimize/**, web/jobs.py, routers/jobs.py, routers/whatif.py, the pre-existing test rails, s2_replay.py; journal.py/backtest.py import-only). Never stage data/, reports/, models/, logs/, config.toml, web/static/. Asset fetches happen only in the backend, with a timeout, and only for codes present in the banked bootstrap (allowlist — the endpoint is not an open proxy). No new job kinds, no new plists, no config keys unless a CDN-base override proves necessary (then `[assets] base_url` in config.example.toml with the real default).

## 3. Out of scope

Photos on the pitch cards (FPL's own pitch uses shirts; photos land with v9b's identity rollout — the endpoint ships now so the cache warms); DGW second-fixture chips; opposition difficulty beyond the ticker's number; animating substitutions; any Live-tab pitch (v9b); the rest of the D5 backlog.

## 4. Outcome

(Filled at cycle end.)

## 5. Gate checklist (built by the implementer, run by the orchestrator)

**G3 — suites, types, build, audit (measured by the implementer):**

- [x] `uv run pytest -q` — 2746 passed (main baseline 2664 + 82 new: 29
      `test_web_assets`, 26 `test_web_identity`, 5 `test_web_advice_identity`,
      22 `test_v9a_degradation`)
- [x] `npx tsc --noEmit` — clean
- [x] `npx vitest run` — 498 passed, 1 skipped (main baseline 460 + 38 new: 4
      `types.test`, 17 `PlayerCard`, 10 `SquadPitch`, 7 `ThisWeek`)
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

**G2 — rails:** `uv run pytest -q tests/test_v9a_degradation.py` (22 passed),
plus every pre-existing `test_*_degradation.py` unmodified
(`uv run pytest -q tests/ -k degradation` — 218 passed).
