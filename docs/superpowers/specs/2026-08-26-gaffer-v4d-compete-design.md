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

*Amended in review:* a `z_deadband = 0.25` was reinstated — `|z|` under it
is treated as level (`z = 0`, `lam = 0.0`, stance neutral). tanh alone is
never zero off an exact dead heat, so without the band the whole v4d path
(extra solves, captain overrides) ran every single gameweek and the lam=0
rails described an unreachable production state (review B3).

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
EO percent: `ep' = ep · (1 + lam · (1 − cover_p)) / (1 + max(lam, 0))`.
The divisor is a review amendment (B2): unnormalized, a chasing lam
multiplied essentially the whole board up while `hit_cost`, `ft_value` and
`itb_value` stayed priced in raw points, silently discounting all three.
Anchored, chasing leaves uncovered players at raw ep and marks covered ones
down by 1/(1+lam); defending was already anchored and is unchanged. With
equal rival
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
*Amended in review (B4):* the override also needs a margin — the challenger
must beat the incumbent's tilted score by `CAPTAIN_OVERRIDE_MARGIN = 0.15`
xPts, so a hairline tie-break inside model error never flips the armband.
The vice follows the tilted ranking (second place), per this section's
"same tilted score" rule. Note all covering/captaincy inputs are the *last
completed* GW's picks — armbands for the week being planned are not public
pre-deadline — and every rendered string says "last armband" accordingly.
Implemented at the existing captain-override seam in `advise.py` — no
`policy.py` change.

## 7. Tier-resolved live EO (`gaffer live`)

New module `data/tier_eo.py`: sample `TIER_SAMPLE = 300` entries uniformly
from the top 10k of the overall classic league (league 314; standings pages
are 50 entries each, so sample 300 distinct (page ≤ 200, slot) pairs),
fetch each entry's live picks, and compute EO-with-captaincy from the
sample plus a standard error per player. Cached per GW
(`data/raw/tier_eo/{gw}.json`). *Amended in review (I5/I6):* the error bar
is the sample SE of the EO estimator itself (stdev of per-entry multiplier
contributions / √n), not the binomial SE of plain ownership; the true cost
of 300 uniform slots is ~455 calls (~155 distinct pages + 300 picks), not
~306, paced by a 50 ms sleep per picks fetch; and an empty sample is cached
too, with its own notice, so a bad week cannot re-trigger the sweep on
every poll. The live tracker table gains two columns — `top10k EO ±se`
and overall `selected_by_percent` — next to the existing league EO. Failure
anywhere (rate limit, page shape change) degrades to the current two-column
table with a one-line notice; the tracker never blocks on tier EO.

## 8. Config

`[league]` (new section; all defaults = today's behaviour):

- `z_scale = 1.5`, `lambda_cap = 0.5` (moves from constant),
  `z_deadband = 0.25` (review amendment, §3),
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

*As run:* the recorded-rivals design proved unfetchable — see §12. The gate
was adapted to a shadow-rival replay preserving every measured criterion.

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

Shipped 2026-08-26/27. Eleven plan tasks (plan
`2026-08-26-gaffer-v4d-compete.md`) via five Opus implementer groups, one
FIX-FIRST adversarial review round (nine fix commits), gate E1 re-run and
passed. Suite 1034 Python + 64 frontend, tsc clean.

### Gate E1 — adapted, then passed

**The spec's recorded-rivals design was unfetchable.** By the time the gate
ran (2026-08-26) the FPL API had rolled to 2026-27: `entry/{id}/event/{gw}/
picks/` and per-GW history for 2025-26 return 404 (probe: GW1 2026-27 picks
200, GW20 2025-26 404; `entry/{id}/history/` "current" holds one 2026-27
row). Nothing was cached locally. Adaptation, recorded as such: the rival is
the **dial-OFF replay itself** — a shadow points-max manager whose per-GW
played XI/captain are the observed squads the ON arm covers against, the
injected gap applied to its trajectory, margin-σ estimated from the real
ON-vs-shadow series. Every measured criterion (win count over the gap grid,
≤15-pt EP cost at gap 0, z=0 byte-identity) survives; what is lost is only
that the rivals are not the user's actual league mates. One rival, one
season — an even narrower base than the spec's honest-widening caveat.

**Result (post-fix run): PASS.** OFF baseline 1079 (GW20–38, chips WC25/
FH33/3xc36/BB37; bit-identical across both runs, incidentally re-proving
the tilt=None path). Gap grid (gap = my_total − shadow at GW20):

| gap | ON total | final margin | win |
|---|---|---|---|
| −60 | 983 | −156 | no |
| −30 | 944 | −165 | no |
| −10 | **1096** | **+7** | **yes** |
| 0 | 1079 | 0 | tie (byte-identical) |
| +10 | 1064 | −5 | no |
| +30 | 1069 | +20 | yes |
| +60 | 1080 | +61 | yes |

ON wins 3, OFF wins 3 (OFF wins exactly its positive gaps), gap-0 delta 0
≤ 15, z=0 byte-identical (dead heat stays inside the deadband all season —
identical totals, chips, and weeks). Reading: the dial **converted a −10
deficit** (+17 net pts from differentials — the headline), holds big leads
almost free (+60 cost 1 pt, +30 cost 10), drops a knife-edge +10 by 5, and
deep chases burn 100–135 pts without converting — the honest price of
saturated variance-seeking against a points-max twin, and the reason the
deadband and tanh cap matter. Net: rank outcomes no worse than points-max,
materially better where it counts, at zero cost when level.

**Confounded first run (recorded for the record):** before the fix round,
the backtest seam priced chips on the tilted pool (finding I4). Defend arms
deferred every chip to GW35–38 (ON+10 played its wildcard GW35 and lost
−16; ON−10 lost −195 with the then-unanchored chase tilt). Post-fix ON−10
flipped from −195 to +7 — the review round changed the measured outcome,
same as v4c's B2.

### Review round (FIX-FIRST → fixed, beaf7eb..6ddd0b7)

Gating: **B1** whatif fed league-EO *percent* into the now fraction-based
`tilt_ep` (every EO ≥ 1% clamped to full cover; `SolveState` gained a
persisted `cover` table, old artifacts fall back to `cover_from_eo`);
**B2** chase tilt inflated the whole board against fixed point-priced
constants (normalization, §5); **B3** dial always-on (deadband, §3);
**B4** hairline captain flips (0.15 xPts margin, §6); **I1** pooled σ
gated on observations not distinct weeks (10 rivals × 1 week passed a
cross-sectional spread off as temporal σ); **I3** backtest logged tilted
`expected_pts` as raw; **I4** backtest chips priced tilted (the E1
confound; chip *selection* now raw, execution solves tilted, mirroring
advise). Cleanups: honest tier-EO SE (I5), empty-sample caching + notice +
true ~455-call cost (I6), dead-heat vs deadband wording (I7), no cache
poisoning on empty history / gw<1 (I8), "last armband" phrasing (I2),
report-CLI parens parity, LeagueParams divisor validation. One plan bug
found by an implementer: the Task-7 vice assertion contradicted this
spec's §6 rule; the spec won.

### Deferred (recorded, not fixed)

- `win_probability` still uses the flat `SIGMA = 18.0` while the dial uses
  estimated per-rival σ — the report's p_win column and λ explanation run
  on two noise models.
- `asdict(strat)` leaks `cover_weights` (internal, keyed by rival entry)
  into the public advice JSON; harmless, untidy.
- The report's captain-options table still ranks/tags "differential" by
  league EO, which can disagree with the tilt note in the same document.
- Tier-EO resamples different entries each GW (seed + gw): week-to-week
  deltas mix real movement with sampling churn. Deliberate; documented.
- E1's evidence base is one season, one shadow rival, and the backtest
  loop has no captaincy-tilt seam — the captaincy half of §6 is covered by
  unit rails only.
