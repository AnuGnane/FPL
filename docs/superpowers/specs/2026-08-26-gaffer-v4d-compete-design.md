# Gaffer v4d "Compete" — Design

Approved approach: **A — upgrade behind the existing seams** (2026-08-26).
League mode keeps its public surface; the internals become rank-aware. The
MILP is untouched. Research basis: `research/2026-08-25-improvement-research.md`
finding 6 (Browne goal-reaching, Haugh & Singal rank payoffs, observed-squad
covering as our structural advantage).

Brainstorm decisions: optimize **win the league** (not one rival, not top-k);
σ **estimated from league history** (pin as fallback); covering via **EP tilt
v2** (no MILP objective change); gate = **league replay vs recorded rivals**;
tracker gains **sampled top-10k EO**.

## 1. Goal

Replace the ad-hoc one-rival λ ramp with the z-dial the research prescribes,
computed against the whole league; make covering computable from rivals'
actual squads instead of proxied by league EO; make captaincy EO-aware
mean-variance instead of argmax EP; and resolve live EO by tier. Everything
degrades exactly to v1 points-max at z = 0 (and to v4c behaviour when league
mode is off).

## 2. Current state and seams (all kept)

- `league_mode.py`: `compute_strategy(my_total, rivals, current_gw) ->
  Strategy(lam, gap, weeks_left, stance, rival_name)`; `tilt_ep(ep_by,
  eo_pct, lam)`; `SIGMA = 18.0` pin; `LAMBDA_CAP = 0.5`.
- `data/league.py`: `fetch_rival_entries`, `fetch_rival_picks` (current GW),
  `effective_ownership`.
- `advise.py` protected ordering (tests/test_advise.py:73):
  `fetch_rival_entries(` < `compute_strategy(` < `tilt_ep(` <
  `pool = build_pool(`. All v4d advise-path work happens inside those calls'
  implementations, not around them.
- `live_gw.py`: league-EO captain table, threat board.
- v4c layers sit downstream: the scenario sweep noises and gates whatever
  tilted EP the pool was built from — the dial composes with v4c for free.

## 3. The z-dial (`league_mode.py` v2)

**z** is the deficit to the *win condition* in units of remaining-horizon
margin spread:

- Behind the leader: `z = (leader_total − my_total) / (σ_m · √W)` with
  `W = 38 − current_gw + 1`, σ_m = margin σ vs the leader (§4). z > 0.
- Ahead of everyone: the threat is the *pack*, not one rival:
  `z = −min_r (my_total − total_r) / (σ_mr · √W)` over all rivals r —
  i.e. the nearest threat in normalized units (the rival with the largest
  P(catch me), not the largest raw total). z < 0.

`Strategy` v2 carries `z`, `sigma_m`, `lam`, `gap`, `weeks_left`, `stance`,
`rival_name`, and the new `cover` weight table (§5). The tilt magnitude is
`lam = LAMBDA_CAP · tanh(|z| / Z_SCALE) · sign(z)` with `Z_SCALE = 1.5` and
`LAMBDA_CAP = 0.5` kept — smooth in z (the old clamp ramp had a dead zone
then a hard saturation), sign positive = chase/split, negative =
defend/cover. `z = 0` (no rivals, or dead-heat) gives `lam = 0.0` exactly
and `tilt_ep` returns the input unchanged — the existing regression test
stays the rail.

## 4. σ from league history (`league_mode.py` + `data/league.py`)

New fetcher `fetch_rival_history(client, entries) -> DataFrame` (entry, gw,
points) from the FPL entry-history endpoint, cached per GW under
`data/raw/league/` like existing raw payloads. σ_m for a rival = standard
deviation of the per-GW margin series `my_points_gw − rival_points_gw` over
this season's completed GWs. Fallbacks, in order: fewer than
`SIGMA_MIN_WEEKS = 6` completed GWs → pooled league-wide margin σ; no
history at all (GW1) → the existing `SIGMA = 18.0` pin, renamed
`SIGMA_FALLBACK`. Bounded to `[8.0, 30.0]` — a two-week fluke of identical
squads must not make z explode. The margin σ is squad-overlap-aware for
free: mirrored squads produce small margins, so small σ, so gaps count for
more — exactly the behaviour the pin got wrong.

## 5. Covering weights from observed squads

League EO answers "who does the league own"; covering answers "who do the
rivals *that matter* own". Per player p:

`cover_p = min(Σ_r w_r · own_{r,p}, 1)` , with

- `own_{r,p}` ∈ {0, 1, 2}: not owned / owned / captained by rival r this GW
  (from `fetch_rival_picks`) — captaincy counts double, and the sum is
  clamped to [0, 1] *after* weighting, exactly as the old
  `min(EO%/100, 1)` clamps league EO.
- `w_r` = rival r's threat weight: `softmax_r(−|gap_r| / (σ_mr · √W))`
  over rivals on the relevant side (the leader when behind; all rivals
  within `3·σ_mr·√W` behind me when ahead). Weights sum to 1; a rival 200
  points adrift contributes ~nothing.

`tilt_ep` v2 signature keeps `(ep_by, cover, lam)` shape but the second
argument is now the cover table (fraction in [0,1]) instead of raw league
EO percent: `ep' = ep · (1 + lam · (1 − cover_p))`. With equal rival
weights and no captaincy term this reduces to the old league-EO tilt — the
generalization is strict, and the old behaviour is one weight table away
for tests. `advise.py` builds `cover` inside the existing
`compute_strategy(`/`tilt_ep(` call sites (protected ordering untouched).

## 6. EO-aware mean-variance captaincy

After the (v4c-gated) plan is fixed, the captain among the XI is re-picked
by tilted score rather than raw EP:

`cap_score_p = ep_p · (1 + lam · (1 − cap_cover_p))`

where `cap_cover_p = Σ_r w_r · [rival r captains p]` (same threat weights).
Behind (lam > 0): a captain nobody relevant is captaining scores higher —
the variance-seeking split the rank payoff implies. Ahead (lam < 0): mirror
the threats' armbands. Ties and the lam = 0 case reproduce today's argmax-EP
captain exactly (rail). The vice keeps the existing rule applied to the
same tilted score. The report/CLI show both picks whenever they differ:
`Captain: X (covering Y's armband)` / `(differential vs Y)` with the raw-EP
captain on the demoted line, mirroring the v4c raw-optimum treatment.

Authority order, explicit: the v4c scenario plurality picks the candidate
captain first; when league mode is active and `lam ≠ 0` the tilted score
over the final XI is the **last word** (it may override the plurality pick,
and the report then shows the overridden pick on the demoted line). At
`lam = 0` the tilt is the identity and v4c behaviour stands unchanged.
Implemented at the existing captain-override seam in `advise.py` — no
`policy.py` change.

## 7. Tier-resolved live EO (`gaffer live`)

New module `data/tier_eo.py`: sample `TIER_SAMPLE = 300` entries uniformly
from the top 10k of the overall classic league (league 314; standings pages
are 50 entries each, so sample 300 distinct (page ≤ 200, slot) pairs),
fetch each entry's live picks, and compute EO-with-captaincy from the
sample plus a binomial standard error per player. Cached per GW
(`data/raw/tier_eo/{gw}.json`); one live session costs ≤ ~306 API calls
(6 page fetches re-used across samples on the same page), throttled by the
existing client. The live tracker table gains two columns — `top10k EO ±se`
and overall `selected_by_percent` — next to the existing league EO. Failure
anywhere (rate limit, page shape change) degrades to the current two-column
table with a one-line notice; the tracker never blocks on tier EO.

## 8. Config

`[league]` (new section; all defaults = today's behaviour):

- `z_scale = 1.5`, `lambda_cap = 0.5` (moves from constant),
- `sigma_floor = 8.0`, `sigma_cap = 30.0`, `sigma_min_weeks = 6`,
- `tier_eo = true` (live tracker only), `tier_sample = 300`.

League mode itself stays gated by the existing `league_id` presence; no new
master switch. `lam = 0` short-circuits are the rail, not config.

## 9. Gate E1 — league replay vs recorded rivals

Prerequisite tooling (part of the cycle): `fetch_rival_history` above plus
`fetch_rival_picks_history(entries, season)` — recorded picks per rival per
GW of 2025-26 via the entry-picks endpoint, cached permanently under
`data/raw/league/2025-26/` (they are historical facts).

The gate: replay 2025-26 GW20–38 with the dial ON vs OFF, my squad replayed
by the existing backtest loop with `tilt_ep` active (OFF = lam forced 0),
rivals scoring their recorded actual points. Injected starting gaps at GW20:
{−60, −30, −10, 0, +10, +30, +60} relative to the recorded leader. Measured
per gap: final rank-1 indicator and final margin. **E1 passes when** the
dial-ON win count across the gap grid ≥ dial-OFF, **and** dial-ON total
points at gap 0 are within 15 of dial-OFF (the tilt must buy rank with
variance, not burn meaningful EP), **and** the z = 0 path is byte-identical
(rail). One season, one league — recorded as such; a synthetic-gap grid is
the honest widening we can afford without inventing rivals.

Failure handling per project rule: a failing half ships behind `lam = 0`
with the negative result recorded.

## 10. Not in this cycle

Explicit MILP overlap terms; P(top-k) for k > 1; multi-league juggling;
global-rank (Çay ownership-weighted) objective; per-player variance from
the component heads (σ stays score-level); LiveFPL scraping; any use of
tier EO in the optimizer (tracker display only).

## 11. Testing

No network in tests (httpx.MockTransport for the two new fetchers and the
standings sampler). Unit: z sign/magnitude cases incl. dead-heat and
runaway-leader; σ estimator fallback chain and bounds; cover table with
captained/absent players and one-sided threat sets; tilt_ep v2 reduction to
the old formula under equal weights; captaincy tilt reduction at lam = 0;
sampler page/slot uniqueness and SE math. Rails: lam = 0 advise byte-identical
(extends test_v4c_degradation.py pattern); protected ordering suites
untouched; live tracker renders with tier EO absent. Gate E1 is
orchestrator-run with a throwaway driver, like D1.

## 12. Outcome

(Filled as the cycle lands: ingestion counts, σ estimates observed, E1
table, review round record.)
