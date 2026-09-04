/* eslint-disable */
/**
 * GENERATED — do not edit.
 *
 * `scripts/gen_types.py` writes `src/schemas.json` from
 * `src/gaffer/web/schemas.py`; `src/types.generated.test.ts` compiles that
 * with json-schema-to-typescript (pinned 16.0.0) and asserts this file is the
 * result. Edit the pydantic model, re-run both, commit all three.
 *
 * The hand-written half of the client's types — and the narrowings of the
 * eleven `Wire*` models, six of which carry a `dict[str, Any]` the browser
 * reads by hand, three of which carry a list an older payload can omit, one of
 * which only references a narrowed model, and one of which is looser inside
 * the unvalidated advice artifact than in the model — lives in `types.ts`,
 * which re-exports this file.
 */
export interface GafferApi {
  [k: string]: unknown
}
/**
 * What changed between the two newest runs of one gameweek.
 *
 * ``available`` is false on a first run of the week — the ordinary case, not
 * an error — and everything else is then empty, so the client renders
 * nothing without having to special-case a status code.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "AdviceDiff".
 */
export interface AdviceDiff {
  available: boolean
  buys_added: AdvicePlayer[]
  buys_dropped: AdvicePlayer[]
  captain_from: AdvicePlayer | null
  captain_to: AdvicePlayer | null
  changed: boolean
  chip_from: string | null
  chip_to: string | null
  current_at: string | null
  /**
   * Players whose expected points moved between the two newest component
   * breakdowns. Independent of ``available``: a first run of the week has no
   * plan to diff and may still have a retrain to report (plan A10).
   */
  ep_movers: EpMover[]
  /**
   * How many moved, or ``None`` when there is no predecessor breakdown to
   * compare against. ``None`` and ``0`` are different claims — "we have not
   * retrained since you looked" against "the retrain changed nothing" — and
   * the strip renders only the second.
   */
  ep_movers_count: number | null
  expected_pts_delta: number
  gw: number
  previous_at: string | null
  sells_added: AdvicePlayer[]
  sells_dropped: AdvicePlayer[]
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "AdvicePlayer".
 */
export interface AdvicePlayer {
  code: number
  name: string
}
/**
 * One player the newest retrain moved, in the gameweek being decided.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "EpMover".
 */
export interface EpMover {
  code: number
  delta: number
  ep_now: number
  ep_prev: number
  name: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "ArtifactItem".
 */
export interface ArtifactItem {
  bytes: number
  name: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "BackupHealth".
 */
export interface BackupHealth {
  bytes: number
  modified_at: string
  path: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "BenchmarkEvaluation".
 */
export interface BenchmarkEvaluation {
  caveat: string
  git_sha: string
  references: {
    [k: string]: {
      [k: string]: ReferenceMetrics
    }
  }
  run_at: string
  stratified: {
    [k: string]: {
      [k: string]: CategoryMetrics
    }
  }
  test_season: string
}
/**
 * A published number: no row count, because we did not measure it.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "ReferenceMetrics".
 */
export interface ReferenceMetrics {
  mae: number
  rmse: number
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "CategoryMetrics".
 */
export interface CategoryMetrics {
  mae: number
  n: number
  rmse: number
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "CalibrationGw".
 */
export interface CalibrationGw {
  gw: number
  heads: {
    [k: string]: CalibrationHead
  }
  n: number
}
/**
 * One probability head's calibration for one gameweek, or a refusal.
 *
 * ``status`` rather than a missing key: a head under
 * ``evaluation.MIN_CALIBRATION_SAMPLES`` has the same shape as a scored one
 * with nulls in it, so the card renders "not enough data" from a field
 * instead of branching on absence.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "CalibrationHead".
 */
export interface CalibrationHead {
  brier: number | null
  log_loss: number | null
  n: number
  reliability: ReliabilityBin[]
  status: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "ReliabilityBin".
 */
export interface ReliabilityBin {
  n: number
  obs: number
  pred: number
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "ChipPlan".
 */
export interface ChipPlan {
  chips: ChipPlanRow[]
  gw: number
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "ChipPlanRow".
 */
export interface ChipPlanRow {
  best_gain: number
  best_gain_per_week: number
  best_gw: number
  chip: string
  now_gain: number | null
  play_now: boolean | null
  play_now_delta: number | null
  /**
   * θ per week, aligned by index with ``weeks``. Built at the router by
   * looping the same ``(chip, gw) -> float`` callable, because putting it in
   * ``chip_plan``'s week rows would be an ``optimize/**`` edit for a display
   * field (plan A9).
   */
  thetas: number[]
  /**
   * θ for this chip in the current gameweek: the surplus the best remaining
   * week is expected to offer. ``chip_plan`` has always computed it and this
   * model has never declared it, so until v10b it was computed and dropped —
   * the ``odds_blend_weight`` failure, repeated. An undeclared field never
   * reaches the page and nothing fails while it doesn't.
   */
  threshold_now: number | null
  /**
   * See ``ChipWorkbenchRow.threshold_source``. Filled at the router from the
   * same lookup ``thetas`` is built from (v12 W3 §4.2).
   */
  threshold_source: string | null
  weeks: ChipWeek[]
  /**
   * How many gameweeks were looked at, so the UI can say how far ahead
   * "best" reaches rather than implying the whole season.
   */
  weeks_scored: number
  /**
   * ``[from_gw, last_gw]`` from ``chip_policy.chip_windows``. Note the first
   * element is the gameweek asked about, not the window's opening — the UI says
   * "expires after GW19" and never "window starts at".
   */
  window: number[]
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "ChipWeek".
 */
export interface ChipWeek {
  gain: number
  gw: number
  /**
   * ``gain`` divided by the horizon weeks the chip is credited with — the
   * weeks from ``gw`` onwards for a wildcard, one for every other chip.
   */
  per_week: number
}
/**
 * One (chip, gameweek) cell of the advice run's own chip table.
 *
 * ``threshold`` is the θ bar that week — the surplus the best remaining week
 * is expected to offer — so the workbench can draw the gain against the bar
 * rather than against an arbitrary axis. Both it and ``play_now`` are
 * optional because an advice payload written before the chip policy landed
 * carries neither.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "ChipWorkbenchRow".
 */
export interface ChipWorkbenchRow {
  chip: string
  gain: number
  gw: number
  /**
   * The second week of a chip *pair* — the bench boost's, where ``gw`` is
   * the wildcard's. ``None`` on every single-chip row, which is every row on
   * every payload written before v12 and every row until the fixture list
   * carries a double.
   */
  gw2: number | null
  note: string | null
  per_week: number | null
  play_now: boolean
  threshold: number | null
  /**
   * Where ``threshold`` came from: ``"theta"``, or ``"flat: <reason>"``.
   *
   * Three distinct fallbacks produce a flat bar and they are not the same
   * news — no asset, no surplus for this chip, a gameweek outside the
   * calibrated window — so the reason travels with the number rather than
   * being guessed at from it. ``None`` on a payload written before v12
   * (v12 W3 §4.2).
   */
  threshold_source: string | null
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "ChipsWorkbench".
 */
export interface ChipsWorkbench {
  chips: ChipWorkbenchRow[]
  gw: number
  wildcard: SquadDiff | null
}
/**
 * A candidate squad against the one you own, resolved server-side.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "SquadDiff".
 */
export interface SquadDiff {
  added: SquadPlayerRef[]
  dropped: SquadPlayerRef[]
  gain_over_horizon: number
  kept: SquadPlayerRef[]
  recommend: boolean
  /**
   * The bar ``recommend`` was decided against. Until v12 this was always
   * the flat 8.0 and was never served, so the card asserted a verdict and
   * showed nothing of the rule behind it (v12 W3 §4.2).
   */
  threshold: number | null
  /**
   * See ``ChipWorkbenchRow.threshold_source``.
   */
  threshold_source: string | null
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "SquadPlayerRef".
 */
export interface SquadPlayerRef {
  code: number
  ep: number
  name: string
  position: string
  price: number
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "Component".
 */
export interface Component {
  label: string
  points: number
}
/**
 * One player-fixture's additive terms.
 *
 * Deliberately shaped like :class:`FixtureExplain` (the explain modal's
 * per-fixture row) without being it: this one is read from the saved
 * components parquet with no model loading at all, and carries only what a
 * why-panel renders.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "ComponentFixture".
 */
export interface ComponentFixture {
  components: Component[]
  ep: number
  gw: number
  home: boolean
  kickoff_time: string | null
  minutes: MinutesOutput
  opponent: string
  /**
   * How much of the Goals term is penalty duty, when any of it is.
   *
   * Not a component: the increment was folded into ``e_goals`` before
   * ``assemble_ep`` ran, so it is already inside ``components``' Goals row and
   * listing it beside them would stop them summing to ``ep``. It rides along
   * as an annotation the panel prints under Goals, and is ``None`` — not 0.0 —
   * for the great majority of rows that have no penalty duty at all, so the
   * panel can tell "no term" from "a term that rounded to zero".
   */
  pen_taker: number | null
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "MinutesOutput".
 */
export interface MinutesOutput {
  /**
   * The same convention, on the probability beside it. 0.0 here is
   * "expected off before the hour", which is a forecast a frame banked
   * without a minutes model never made — and it is the number ``xmins``
   * weights the second half by, so a zero propagates into a claim about
   * minutes as well.
   */
  p60: number | null
  /**
   * ``None`` — never 0.0 — for a frame banked without a minutes model. Zero
   * here reads as "expected not to play", which is the strongest claim this
   * payload can make about a player, and the compare radar drew it as a
   * zero-length spoke on the minutes axis.
   */
  p_play: number | null
  /**
   * Expected minutes, ``p_play * (45 + 45 * p60)``. ``None`` when either
   * probability is missing: an un-modelled player is not a player expected to
   * play no minutes.
   */
  xmins: number | null
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "ComponentPlayer".
 */
export interface ComponentPlayer {
  code: number
  /**
   * Summed over every fixture in this payload — a horizon total, not a
   * gameweek's, because the components parquet carries the whole solve
   * horizon.
   */
  ep: number
  /**
   * Expected points for the *requested* gameweek alone.
   *
   * ``ep`` above is a horizon sum — the components parquet carries every
   * gameweek in the solve horizon — so it is not a number the σ table has ever
   * seen. The band brackets this one instead (plan A2).
   */
  ep_gw: number | null
  ep_hi: number | null
  /**
   * p25 / p75 of the distribution ``noise_ep`` draws from. ``None``, never
   * zero, when the frame carries no minutes model for him.
   */
  ep_lo: number | null
  fixtures: ComponentFixture[]
  name: string
  p_blank: number | null
  /**
   * ``uncertainty.Band.p_haul``: P(total points >= 10) in the tail of the
   * whole forecast. The advice payload's attacking quantity is a different
   * number on a different scale and is served as ``p_attacking_haul``
   * (spec D3).
   */
  p_haul: number | null
  position: string
  /**
   * The scenario sweep's own σ for this player-gameweek, in points.
   */
  sigma: number | null
  team_name: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "ComponentsBreakdown".
 */
export interface ComponentsBreakdown {
  gw: number
  players: ComponentPlayer[]
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "ConfidenceData".
 */
export interface ConfidenceData {
  captain: ConfidenceTier
}
/**
 * One record-derived claim, with the counts that back it.
 *
 * ``text`` is the whole product — a sentence quoting counts. The counts are
 * carried beside it so a caller can style the tier without re-parsing prose,
 * never so it can compute a rate: the absence of a percentage anywhere in
 * this model is the point of it (spec D3).
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "ConfidenceTier".
 */
export interface ConfidenceTier {
  aligned: number
  /**
   * Reviewed gameweeks where the lane was actually comparable. The gap
   * between this and ``reviewed`` is the weeks the model's captain was not in
   * the eleven, which is not evidence either way.
   */
  graded: number
  losses: number
  reviewed: number
  text: string
  tier: 'early' | 'mixed' | 'backed'
  wins: number
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "CoreInsightsHealth".
 */
export interface CoreInsightsHealth {
  collected: boolean
  season: string
  tables: CoreInsightsTable[]
  /**
   * What has to happen before these numbers mean anything, or ``None`` when
   * they already do. Spec §1: a view whose data does not exist yet says what
   * it is waiting for and never renders zeros as if they were measurements.
   */
  waiting_for: string | null
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "CoreInsightsTable".
 */
export interface CoreInsightsTable {
  /**
   * Newest kickoff date in the table, ``YYYY-MM-DD``, or ``None`` when the
   * table has no dated rows. A table with rows and no date is possible — the
   * player table is keyed on gameweek, not on a timestamp — and reads as its
   * highest gameweek instead.
   */
  latest: string | null
  rows: number
  table: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "CurrentEvaluation".
 */
export interface CurrentEvaluation {
  baselines: {
    [k: string]: {
      [k: string]: CategoryMetrics
    }
  }
  git_sha: string
  heads: {
    [k: string]: HeadMetrics
  }
  holdout_slots: number
  run_at: string
  /**
   * cut ("all" / "starters") -> return category -> metrics.
   */
  stratified: {
    [k: string]: {
      [k: string]: CategoryMetrics
    }
  }
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "HeadMetrics".
 */
export interface HeadMetrics {
  /**
   * ``None`` for a head with nothing to score — see
   * :func:`gaffer.evaluation.head_metrics`. Nullable rather than NaN because
   * NaN is not JSON.
   */
  log_loss: number | null
  reliability: ReliabilityBin[]
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "DecompositionCell".
 */
export interface DecompositionCell {
  hits: number
  per_gw: number
  total: number
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "DecompositionData".
 */
export interface DecompositionData {
  /**
   * ``{model,oracle}_h{1,3}`` -> that replay's outcome.
   */
  cells: {
    [k: string]: DecompositionCell
  }
  /**
   * oracle_h3 - model_h3: what better forecasting could still win.
   */
  forecast_gap_h3: number
  git_sha: string
  /**
   * oracle_h3 - oracle_h1: the ceiling on multi-week planning.
   */
  planning_ceiling: number
  run_at: string
  season: string
  start_gw: number
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "Digest".
 */
export interface Digest {
  /**
   * Set only on a digest that failed to build. A run that crashes still
   * banks an artifact so the card can say "Friday's briefing did not build"
   * rather than falling back to the never-run empty state.
   */
  error: string | null
  generated_at: string
  gw: number | null
  headline: string
  kind: string
  sections: DigestSection[]
}
/**
 * One block of a digest. ``bits`` is prose the client joins.
 *
 * The DiffStrip idiom: clauses assembled server-side, rendered by joining
 * them, so there is no markdown dependency anywhere in the client. A section
 * with no bits never reaches here — the builder drops it (plan A5).
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "DigestSection".
 */
export interface DigestSection {
  bits: string[]
  key: string
  title: string
}
/**
 * The newest digest, or a stated absence.
 *
 * ``available`` false covers all three ways there is nothing to show — never
 * run, deleted, unparseable — because the card's empty state says the same
 * sentence for each of them: press the button, or wait for Friday.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "DigestPanel".
 */
export interface DigestPanel {
  available: boolean
  digest: Digest | null
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "DraftCompare".
 */
export interface DraftCompare {
  gw: number
  rows: DraftCompareRow[]
  weeks: number
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "DraftCompareRow".
 */
export interface DraftCompareRow {
  buys: WirePlayerRef[]
  captain: WirePlayerRef | null
  chip: string | null
  delta_xpts: number | null
  /**
   * Why this row is empty. An infeasible draft is a row with a reason, not
   * a failed comparison.
   */
  error: string | null
  expected_pts: number | null
  hits: number | null
  /**
   * Gameweeks this row's plan actually covers, which is not always the
   * comparison's. A free hit is a one-week squad; ``DraftCompare.weeks`` is
   * the shorter shared window every row was then *scored* over.
   */
  horizon: number | null
  horizon_pts: number | null
  /**
   * The unconstrained optimum, so every other row has a "worse than what".
   */
  is_reference: boolean
  name: string
  sells: WirePlayerRef[]
  solved_at: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "WirePlayerRef".
 */
export interface WirePlayerRef {
  code: number
  ep: number
  name: string
  next_fixture: NextFixture | null
  position: string
  team_code: number | null
  team_short: string | null
}
/**
 * One team's next game in the advised gameweek.
 *
 * Resolved at serve time from the banked fixture list, never solved for.
 * Two of the four fields are independently optional and mean different
 * things when null: ``kickoff_utc`` is null while FPL still has the date as
 * TBC, and ``difficulty`` is null when the ticker could rate nothing — a
 * chip in a neutral colour rather than a chip that is not drawn.
 *
 * A team with *no* game gets ``next_fixture: null`` on the player instead of
 * this model with empty fields, because "he does not play" and "he plays and
 * we know less than usual about it" are different sentences.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "NextFixture".
 */
export interface NextFixture {
  difficulty: number | null
  home: boolean
  kickoff_utc: string | null
  opponent_short: string | null
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "DraftCompareRequest".
 */
export interface DraftCompareRequest {
  names: string[]
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "DraftList".
 */
export interface DraftList {
  drafts: DraftRow[]
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "DraftRow".
 */
export interface DraftRow {
  constraints: WhatIfRequest
  created_at: string
  name: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "WhatIfRequest".
 */
export interface WhatIfRequest {
  ban: number[]
  chip: 'none' | 'wc' | 'bb' | 'fh' | 'tc'
  force_in: number[]
  /**
   * Owned players the solve must sell in the first horizon gameweek.
   *
   * He is then out of the squad **for the whole horizon**: ``milp`` pins squad
   * membership to 0 in every week, not only the first, so this is not a sale
   * the solver may reverse later. The bank is credited with his selling price.
   *
   * Not ``ban``: banning an owned player removes him from the candidate pool
   * entirely, so he never enters the squad and — because he leaves the pool
   * rather than the squad — the sale money never arrives. This says "sell
   * him", which is the instruction the planner board's handoff has been
   * approximating with ``ban`` since v11.
   */
  force_out: number[]
  horizon: number | null
  lock: number[]
  max_hits: number
  max_transfers: number | null
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "DraftSaveRequest".
 */
export interface DraftSaveRequest {
  constraints: WhatIfRequest
  name: string
}
/**
 * v12 W4 §5.3. One gameweek against a synthetic field drawn from EO.
 *
 * Three headline numbers and two of them are ``None`` today. Each null has
 * its own sentence rather than a shared one, because they are waiting for
 * different things: ``p_green`` for a banked field sample, ``p_top10k`` for
 * a score series that does not exist anywhere, ``rank_slope`` for graded
 * gameweeks. Spec §1: a view whose data does not exist says what it is
 * waiting for and never renders a zero as a measurement.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "FieldRank".
 */
export interface FieldRank {
  /**
   * Which gameweek's sample the EO came from, or ``None`` when none did.
   *
   * Not :attr:`gw`. The field sample for plan gameweek N is banked under
   * N-1 — picks 404 before a deadline, so the scrape reads the last scored
   * week — and §3.3's ``deadline_eo`` extrapolates it one gameweek forward.
   * Two different gameweek numbers in one payload is exactly the kind of
   * thing a reader has to be told rather than left to infer.
   */
  eo_gw: number | null
  /**
   * ``"deadline-trend"`` (§3.3's extrapolation), ``"last-sample"`` (the
   * newest scrape), or ``"none"``. A trend EO and a last-sample EO are
   * different numbers and the panel says which it used.
   */
  eo_source: string
  /**
   * Independent field populations the headline was averaged over
   * (:data:`gaffer.league_sim.FIELD_DRAWS`). Provenance, like ``n`` and
   * ``seed``: which three hundred managers were drawn is a source of noise in
   * its own right.
   */
  field_draws: number
  field_median_ep: number | null
  gw: number
  managers: number
  my_ep: number | null
  n: number
  p_green: number | null
  p_top10k: number | null
  /**
   * Overall-rank places per point, from the graded ledger. Negative: more
   * points is a better (smaller) rank.
   */
  rank_slope: number | null
  rank_slope_rows: number
  rank_waiting_for: string | null
  seed: number
  top10k_waiting_for: string | null
  /**
   * Players in my squad the field sample never saw.
   *
   * ``eo_from_picks`` omits anyone no sampled entry started, so a genuine
   * differential is routinely absent from the EO table. He is simulated at
   * ownership 0.0 — nobody in the field has him — and counted here so the
   * panel can say how much of my week the sample cannot speak to.
   */
  unsampled_picks: number
  waiting_for: string | null
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "FixtureExplain".
 */
export interface FixtureExplain {
  calibration_delta: number
  components: Component[]
  ep: number
  gw: number
  home: boolean
  kickoff_time: string | null
  minutes: MinutesOutput
  odds: OddsInfluence
  opponent: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "OddsInfluence".
 */
export interface OddsInfluence {
  e_gc_blended: number
  e_gc_model: number
  e_goals_against: number | null
  p_cs_blended: number
  p_cs_model: number
  weight: number
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "FixtureMatrixData".
 */
export interface FixtureMatrixData {
  gws: number[]
  source: 'dixon_coles' | 'none'
  teams: MatrixTeam[]
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "MatrixTeam".
 */
export interface MatrixTeam {
  cells: MatrixCell[]
  code: number
  mean_attack: number
  mean_defence: number
  name: string
  short_name: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "MatrixCell".
 */
export interface MatrixCell {
  /**
   * Difficulty for your attackers, 0 easiest to 1 hardest.
   *
   * Driven by the opponent's *defence* strength: a mean defence is a hard
   * fixture to score in.
   */
  attack: number
  /**
   * Difficulty of keeping a clean sheet, 0 easiest to 1 hardest.
   *
   * Driven by the opponent's *attack* strength.
   */
  defence: number
  gw: number
  home: boolean
  opponent: string
}
/**
 * Doubles and blanks in the season ahead (v10b §F2a).
 *
 * Every failure is a 200 with a ``note`` rather than an error: this renders
 * as one card beside populated cards, and a 422 there is indistinguishable
 * from a broken endpoint.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "FixtureOutlook".
 */
export interface FixtureOutlook {
  from_gw: number | null
  /**
   * A claim about the **served slice**, not the season: both flags are
   * computed over the same ``weeks`` this response carries, so a ``from_gw``
   * narrows them together with the rows.
   *
   * Declared rather than derived on the client, for the reason v9d's
   * ``available`` exists: the empty state is the common case for months, and a
   * client branching on ``weeks.every(w => !w.doubles.length)`` is a client
   * that will one day branch on ``weeks.length`` by mistake.
   */
  has_blanks: boolean
  has_doubles: boolean
  note: string | null
  /**
   * False when the teams snapshot was unreadable and the codes above are
   * raw team ids. The counts hold; the names do not.
   */
  teams_known: boolean
  weeks: OutlookWeek[]
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "OutlookWeek".
 */
export interface OutlookWeek {
  blanks: OutlookTeam[]
  doubles: OutlookTeam[]
  fixtures: number
  gw: number
}
/**
 * A club in the outlook. ``short_name`` is null when the teams snapshot
 * could not be read — the counts are still true, only the label is missing,
 * and losing the whole answer over a cosmetic join is the wrong trade.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "OutlookTeam".
 */
export interface OutlookTeam {
  code: number
  short_name: string | null
}
/**
 * One (gameweek, player) whose status moved before the deadline.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "FlagChange".
 */
export interface FlagChange {
  chance_of_playing: number | null
  code: number
  /**
   * The last status recorded **before** the deadline. A snapshot taken
   * afterwards told nobody anything and is not in this window.
   */
  final_status: string
  /**
   * The snapshot day the status first differed from what it had been —
   * the first day a manager could have acted, not the last.
   */
  first_change: string
  from_status: string
  gw: number
  lead_days: number
  started: boolean
}
/**
 * v12 §3.1's readout, or its refusal.
 *
 * ``available`` is what the card branches on, and ``note`` is the sentence
 * it prints when the answer is no. Both are on the payload rather than in
 * the page because the CLI prints the same sentence, and two copies of an
 * empty state drift.
 *
 * The scorer's ``changes`` — every status move it found, one row each — is
 * **deliberately not declared here**, so pydantic drops it on the way out.
 * It is the evidence behind the histogram and it stays in the artifact for
 * anyone who wants their own bands over it, but nothing on the page reads
 * it and it is the only field on this payload that grows without bound: one
 * row per player per move per gameweek, all season. ``rows`` carries the
 * count that the page does show.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "FlagLatencyData".
 */
export interface FlagLatencyData {
  available: boolean
  checked_covered_gws: number[]
  covered_gws: number[]
  git_sha: string
  histogram: LeadBucket[]
  late_flags: FlagChange[]
  min_snap_dates: number
  note: string | null
  rows: number
  run_at: string
  snap_dates: number
}
/**
 * One band of the lead-time histogram, split by what happened.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "LeadBucket".
 */
export interface LeadBucket {
  bucket: string
  missed: number
  started: number
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "Freshness".
 */
export interface Freshness {
  rows: FreshnessRow[]
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "FreshnessRow".
 */
export interface FreshnessRow {
  /**
   * Hours since the file was written, or ``None`` for "never".
   *
   * Never 0.0 for an absent file. Zero is "just now", which is the strongest
   * claim this row can make and the exact opposite of what an absent file
   * means. The client colours on ``None`` first and on the number second.
   */
  age_hours: number | null
  modified_at: string | null
  /**
   * What was actually stat'd, so a surprising age is diagnosable.
   */
  path: string | null
  source: 'refresh' | 'odds' | 'field' | 'advise' | 'backup'
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "GapPoint".
 */
export interface GapPoint {
  /**
   * Your total minus the leader's, negative when you are behind.
   */
  gap: number
  gw: number
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "GwPoint".
 */
export interface GwPoint {
  gw: number
  points: number
  total: number
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "HistoryRun".
 */
export interface HistoryRun {
  actual_pts: number | null
  buys: string[]
  captain: string
  deadline: string
  expected_pts: number
  gw: number
  hits: number
  sells: string[]
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "JobAccepted".
 */
export interface JobAccepted {
  job_id: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "JobRunView".
 */
export interface JobRunView {
  error: string | null
  finished_at: string | null
  id: string
  kind: string
  line_count: number
  started_at: string
  status: 'queued' | 'running' | 'done' | 'failed'
  summary: string | null
}
/**
 * The v7 runner's accept body. ``JobAccepted`` above still serves the v6
 * queue endpoints, whose clients read only ``job_id``.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "JobStarted".
 */
export interface JobStarted {
  job_id: string
  kind: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "JournalData".
 */
export interface JournalData {
  built_at: string | null
  cumulative: JournalPoint[]
  rows: JournalRow[]
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "JournalPoint".
 */
export interface JournalPoint {
  actual: number
  delta: number
  gw: number
  model: number
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "JournalRow".
 */
export interface JournalRow {
  actual_captain: string | null
  actual_pts: number
  delta: number
  gw: number
  model_buys: string[]
  model_captain: string | null
  model_pts: number
  model_sells: string[]
  /**
   * Every banked run of this gameweek was written after its deadline, so
   * the model's side of the comparison had the team news the user did not.
   */
  post_deadline: boolean
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "LadderCap".
 */
export interface LadderCap {
  max_hits: number | null
  max_transfers: number | null
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "LadderPayload".
 */
export interface LadderPayload {
  cap: LadderCap
  /**
   * Set when the saved ``max_transfers`` has no rung of its own.
   */
  cap_note: string | null
  /**
   * The highlighted row, resolved through ``same_as`` to a row that
   * carries numbers.
   */
  cap_rung: string | null
  /**
   * The row the saved cap literally names, before that resolution.
   */
  cap_rung_requested: string | null
  /**
   * Where ``cap`` came from: ``"config"``, the live settings the card
   * writes, or ``"state"`` when that could not be read and the caps the saved
   * solve ran under stood in.
   */
  cap_source: string | null
  free_transfers: number | null
  generated_at: string | null
  gw: number | null
  gws: number[]
  n_draws: number
  /**
   * Why ``rungs`` is empty, when it is: no state, or no ladder banked.
   */
  note: string | null
  /**
   * Rungs dropped because they would not solve.
   */
  notes: string[]
  recommended: string | null
  /**
   * Why ``recommended`` is ``None``, when it is.
   */
  recommended_note: string | null
  rungs: LadderRung[]
  seed: number | null
  /**
   * Player-weeks that fell back to the outcome σ for want of a band.
   */
  sigma_fallbacks: number
  sigma_source: string | null
  wall_s: number | null
}
/**
 * One row. Every number is ``None`` on a ``same_as`` row, which repeats
 * the rung below rather than re-solving it.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "LadderRung".
 */
export interface LadderRung {
  /**
   * The first week's hits, in points.
   */
  cost: number
  /**
   * Hits taken in the **first** week — the decision on the table now.
   */
  hits: number
  horizon_cost: number
  /**
   * Hits over the whole horizon, which is what ``horizon_pts`` and
   * ``mean_pts`` are already net of.
   */
  horizon_hits: number
  horizon_pts: number | null
  key: string
  mean_pts: number | null
  objective: number | null
  p10_pts: number | null
  p90_pts: number | null
  p_beats_bank: number | null
  p_beats_top: number | null
  p_best: number | null
  plan_by_gw: LadderWeek[]
  same_as: string | null
  transfers: number
  vs_below: LadderVsBelow | null
  week_pts: number | null
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "LadderWeek".
 */
export interface LadderWeek {
  bench: WirePlayerRef[]
  buys: WirePlayerRef[]
  captain: WirePlayerRef
  expected_pts: number
  gw: number
  hits: number
  sells: WirePlayerRef[]
  vice: WirePlayerRef
  xi: WirePlayerRef[]
}
/**
 * What the extra hit bought, against the previous distinct rung.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "LadderVsBelow".
 */
export interface LadderVsBelow {
  /**
   * The **horizon** hit cost this rung carries over the rung below.
   * ``max_hits`` is a per-gameweek cap, so a rung can pay it every week, and
   * it is the horizon figure that ``delta_mean_pts`` is net of.
   */
  delta_cost: number
  /**
   * The first week's difference alone.
   */
  delta_cost_now: number
  delta_mean_pts: number
  dropped_buys: WirePlayerRef[]
  dropped_sells: WirePlayerRef[]
  extra_buys: WirePlayerRef[]
  extra_sells: WirePlayerRef[]
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "LaunchdHealth".
 */
export interface LaunchdHealth {
  last_line: string | null
  log: string
  modified_at: string | null
  present: boolean
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "LeagueRaceData".
 */
export interface LeagueRaceData {
  entry_id: number
  gap: GapPoint[]
  lam: number
  lam_explained: string
  league_id: number
  stance: string
  standings: StandingRow[]
  trajectory: Trajectory[]
  win_probability: WinProb[]
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "StandingRow".
 */
export interface StandingRow {
  entry: number
  event_total: number
  is_you: boolean
  name: string
  player_name: string
  rank: number
  total: number
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "Trajectory".
 */
export interface Trajectory {
  entry: number
  name: string
  points: GwPoint[]
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "WinProb".
 */
export interface WinProb {
  name: string
  p_win: number
  total: number
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "LeagueSimData".
 */
export interface LeagueSimData {
  entries: number
  exp_finish: number
  /**
   * v12 W4 §5.3's panel. ``None`` only when the simulation itself could not
   * be built; an unanswerable question is a ``FieldRank`` full of nulls with
   * their reasons, not an absent object.
   */
  field: FieldRank | null
  /**
   * The sampled field's weekly rate, or ``None`` when nothing is banked —
   * in which case rivals do not drift however ``rival_drift`` is set.
   */
  field_rate: number | null
  gw: number
  history: SimPoint[]
  /**
   * ``league_mode.win_probability``'s parametric answer, kept beside the
   * simulated one until the UI has fully switched (spec §3).
   */
  legacy_win_probability: WinProb[]
  margin_quantiles: {
    [k: string]: number
  }
  n: number
  notice: string | null
  p_top3: number
  p_win: number
  per_rival: RivalBeat[]
  rival_drift: number
  seed: number
  weeks_left: number
}
/**
 * One banked gameweek of the headline, for the card's sparkline.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "SimPoint".
 */
export interface SimPoint {
  exp_finish: number
  gw: number
  p_top3: number
  p_win: number
  run_at: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "RivalBeat".
 */
export interface RivalBeat {
  entry: number
  name: string
  /**
   * ``None`` when the entry's squad could not be read at all (private, or
   * joined after the gameweek). Such an entry is listed but not simulated —
   * see ``league_sim.is_readable`` — and the card renders a dash.
   */
  p_beat: number | null
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "LeagueWhatIfPin".
 */
export interface LeagueWhatIfPin {
  /**
   * A gaffer player *code*, not a season element id — the explorer, the
   * squad table and the compare panel all speak codes, and the router maps to
   * elements against the same snapshot they were rendered from.
   */
  code: number
  event: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "LeagueWhatIfRequest".
 */
export interface LeagueWhatIfRequest {
  /**
   * Answer from the cache or not at all (204).
   *
   * This Week's captaincy chip sets it. That page is the one opened on a
   * Thursday evening, the chip is decoration, and a cold cache means fifty
   * entry-picks requests at the FPL API fired by a page load — at the hour
   * every FPL manager in the country is loading pages. The League What-if tab
   * leaves it false: there the simulation *is* the page.
   */
  cached_only?: boolean
  captain_override: number | null
  pins: LeagueWhatIfPin[]
  rival_captain_blanks: number | null
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "LeagueWhatIfResult".
 */
export interface LeagueWhatIfResult {
  baseline_exp_finish: number
  baseline_p_win: number
  delta_p_win: number
  delta_rank: number
  exp_finish: number
  p_win: number
  table: LeagueWhatIfRow[]
  unknown_codes: number[]
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "LeagueWhatIfRow".
 */
export interface LeagueWhatIfRow {
  entry: number
  exp_finish: number
  is_you: boolean
  name: string
  /**
   * This entry's win frequency in the same run as the headline, or ``None``
   * when its squad could not be read (``league_sim.is_readable``).
   */
  p_win: number | null
  total: number
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "LivePlayer".
 */
export interface LivePlayer {
  code: number
  element: number
  minutes: number
  multiplier: number
  name: string
  points: number
  position: string
  projected_in: boolean
  projected_out: boolean
  provisional_bonus: number
  remaining_ep: number | null
  selected_by_percent: number | null
  status: 'played' | 'playing' | 'yet to play'
  /**
   * The other half of a projected substitution, so a chip can name him.
   */
  sub_partner: number | null
  /**
   * ``"played"`` or ``"yet to play"``: how certain the incoming man is.
   */
  sub_reason: string | null
  tier_eo: number | null
  tier_eo_se: number | null
}
/**
 * One poll's snapshot of the race, held in memory for this session only.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "LiveRacePoint".
 */
export interface LiveRacePoint {
  at: string
  /**
   * The tracked rival's race value — the entry pinned in ``rival_name``,
   * which is the top entry in the league that is not me. He is the leader
   * only when I am not; when I am leading he is the man in second.
   */
  rival: number | null
  you: number
}
/**
 * One league place worth watching, priced in points.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "LiveSafety".
 */
export interface LiveSafety {
  entry: number
  /**
   * Their projected total minus mine. Positive means they are ahead.
   */
  margin: number
  name: string
  /**
   * What I must add beyond my projection to pass them; 0 when I lead.
   */
  need: number
  role: 'above' | 'below' | 'leader'
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "LiveState".
 */
export interface LiveState {
  active: boolean
  gw: number | null
  matches_in_play: number
  my_points: number
  my_projected_points: number
  my_race: number | null
  notice: string | null
  players: LivePlayer[]
  /**
   * The race's own degradation line. Deliberately not ``notice``, which is
   * the tier-EO line and belongs to a different card.
   */
  race_notice: string | null
  /**
   * This gameweek's saved ``advice.expected_pts``, when there is one.
   */
  race_reference: number | null
  race_series: LiveRacePoint[]
  /**
   * The entry the trajectory follows: the highest-placed entry that is not
   * me, picked on the gameweek's first poll and then pinned for the rest of it
   * so the line cannot change whose points it is plotting mid-afternoon.
   */
  rival_name: string | null
  safety: LiveSafety[]
  table: LiveTableRow[]
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "LiveTableRow".
 */
export interface LiveTableRow {
  delta: number
  entry: number
  live: number
  name: string
  pre_total: number
  projected: number
  projected_live: number | null
  /**
   * ``projected_live + remaining_ep``: where this gameweek is heading.
   */
  race: number | null
  remaining_ep: number | null
}
/**
 * One player-gameweek the forecast got most wrong.
 *
 * ``miss`` is ``actual - ep``, so it is signed: a positive one is a player
 * the model under-rated and a negative one is a transfer it may have talked
 * somebody into. Both directions are shown, which is why the card sorts on
 * the absolute value and prints the sign.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "MissRow".
 */
export interface MissRow {
  actual: number
  code: number
  ep: number
  minutes: number
  miss: number
  name: string
  position: string
  price: number | null
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "MissesData".
 */
export interface MissesData {
  /**
   * ``None`` when no gameweek has both a banked forecast and a banked
   * result. That is an absent card, not a card of zeros (spec D1).
   */
  gw: number | null
  rows: MissRow[]
}
/**
 * One watched player FPL's predictor has near a threshold tonight.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "MoverRow".
 */
export interface MoverRow {
  /**
   * FPL is still fitting this player's price model — an early-season caveat
   * the row carries rather than a reason to hide it.
   */
  calibrating: boolean
  code: number
  /**
   * ``rise`` or ``drop``. Never ``flat``: this list is only ever rows past
   * the alert threshold, where the price log (which sees everyone) has a third
   * value.
   */
  direction: string
  name: string
  /**
   * In millions, the way the UI shows a price — not the 0.1m integer the
   * bootstrap carries.
   */
  now_cost: number
  price_change_percent: number
  /**
   * ``squad`` / ``plan`` / ``watchlist``, resolved in that order. The
   * answer to "why is he on this list?", on the row itself.
   */
  source: string
}
/**
 * Tonight's likely price changes among players the manager cares about.
 *
 * ``as_of`` is the age of the *reading*, not of the request: this is served
 * off ``data/live/players.parquet`` and never off the network, so a panel
 * that did not say how stale it was would be a panel claiming to know
 * something about tonight when it might be quoting Tuesday.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "MoversPanel".
 */
export interface MoversPanel {
  as_of: string | null
  available: boolean
  rows: MoverRow[]
}
/**
 * A player a report names but does not price.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "NamedPlayer".
 */
export interface NamedPlayer {
  code: number
  name: string
  position: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "NewsPanelData".
 */
export interface NewsPanelData {
  gw: number
  moved: number
  rows: NewsRow[]
}
/**
 * One player the news layer moved, with the evidence that moved him.
 *
 * Both sides of every number, because the panel's claim is a *difference*:
 * "we think 5%, the official flag says 75%" is the sentence, and either half
 * on its own is not.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "NewsRow".
 */
export interface NewsRow {
  chance_of_playing: number | null
  code: number
  e_min_flags: number
  e_min_news: number
  expected_return_gw: number | null
  fetched_at: string | null
  injury_type: string | null
  /**
   * ``xi`` / ``doubt`` / ``out`` — ``p_start_hint`` named, because a
   * probability in a caption reads as a forecast rather than as a listing.
   */
  lineup_hint: string | null
  name: string
  official_note: string | null
  p_play_flags: number
  p_play_news: number
  p_start_hint: number | null
  source: string | null
  status: string | null
  team_name: string
}
/**
 * Gate N2's standing readout.
 *
 * ``rows`` is the field that says whether any of it means anything: the log
 * is written every week and scored only once a gameweek has been played, so
 * a fresh install carries a payload with ``rows: 0``, an empty ``overall``
 * and no gameweeks. That is not an error state — it is "come back Monday".
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "NewsShadowData".
 */
export interface NewsShadowData {
  by_gw: NewsShadowGw[]
  git_sha: string
  overall:
    | NewsShadowSummary
    | {
        [k: string]: unknown
      }
  rows: number
  run_at: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "NewsShadowGw".
 */
export interface NewsShadowGw {
  brier_flags: number
  brier_news: number
  cum_brier_flags: number
  cum_brier_news: number
  cum_mae_flags: number
  cum_mae_news: number
  gw: number
  mae_flags: number
  mae_news: number
  rows: number
}
/**
 * Both sides of gate N2's two metrics over one slice of the log.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "NewsShadowSummary".
 */
export interface NewsShadowSummary {
  brier_flags: number
  brier_news: number
  mae_flags: number
  mae_news: number
  rows: number
}
/**
 * One pin. At least one of the two values must be present.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "OverrideRequest".
 */
export interface OverrideRequest {
  code: number
  e_min: number | null
  note: string
  p_play: number | null
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "OverrideRow".
 */
export interface OverrideRow {
  code: number
  e_min: number | null
  model_e_min: number | null
  /**
   * What the served pipeline had for him when the pin was made, so the
   * why-panel can say "the model had 0.82" without re-deriving anything.
   */
  model_p_play: number | null
  name: string
  note: string
  p_play: number | null
  set_at: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "OverridesPanel".
 */
export interface OverridesPanel {
  /**
   * ``[news] overrides``. False means the pins are stored and *not* being
   * applied, which the panel says out loud rather than showing nothing.
   */
  active: boolean
  rows: OverrideRow[]
  /**
   * Accepted, and worth a second look. Set on a write whose two numbers
   * disagree with each other — expected minutes implying a player starts,
   * beside a probability of playing that says he probably does not. A refusal
   * would be wrong (the manager is allowed to mean it) and silence would be
   * worse, so the dialog shows this and stays open.
   */
  warning: string | null
}
/**
 * ``reports/pen_tracker.json``, as written by ``gaffer track-pens``.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "PenTrackerData".
 */
export interface PenTrackerData {
  gws: PenTrackerGw[]
  notes: string[]
  season: string
  season_totals: PenTrackerTotals
}
/**
 * One finished gameweek of the penalty tracker.
 *
 * Every field but ``gw`` is optional because ``pen_tracker.safe_gw_block``
 * writes one of two shapes: the full block, or ``{"gw": N, "error": ...}``
 * when that week would not read. One optional-field model rather than a
 * union — a union would make the client discriminate before it can render
 * a row that is a row either way.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "PenTrackerGw".
 */
export interface PenTrackerGw {
  component_rows: number | null
  covered_rows: number | null
  error: string | null
  gw: number
  instrument: string | null
  pens_by_first_choice: number | null
  pens_per_team_game: number | null
  pens_taken: number | null
  predicted_ep_pen_taker: number | null
  predicted_takers: number | null
  realized_pen_points: number | null
  rows: number | null
  taker_hit_rate: number | null
  team_games: number | null
}
/**
 * The season line. All optional: a report that degraded before it
 * reached a single finished gameweek writes ``{}`` here.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "PenTrackerTotals".
 */
export interface PenTrackerTotals {
  gws: number | null
  instruments: string[]
  league_pens_pg_served: number | null
  pens_by_first_choice: number | null
  pens_per_team_game: number | null
  pens_taken: number | null
  predicted_ep_pen_taker: number | null
  realized_pen_points: number | null
  taker_hit_rate: number | null
  team_games: number | null
}
/**
 * A plan the solver ranked behind the recommended one (v12 W3 §4.3).
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "PlanAlternative".
 */
export interface PlanAlternative {
  /**
   * Objective points behind the recommended plan — **signed**.
   *
   * Negative means this plan prices *above* the recommendation, which happens
   * because the recommendation carries the scenario sweep's moves as
   * constraints and this one does not. ``None`` when the artifact's number
   * could not be read; never 0.0, which is "exactly level".
   */
  gap: number | null
  /**
   * ``"Plan B"`` / ``"Plan C"``, assigned by position at the router. The
   * artifact stores the order and not the name, so a payload written by one
   * build reads correctly on another.
   */
  label: string
  weeks: PlanGw[]
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "PlanGw".
 */
export interface PlanGw {
  /**
   * What is left in the bank after this week's moves, in millions.
   *
   * ``None`` means *unknown*, and it means it for one reason: some move in
   * this week or an earlier one had no price, so the running total is broken
   * and stays broken. Never 0.0 — that is "fully invested", which is a real
   * and different state a manager can be in.
   */
  bank: number | null
  buys: PlanMove[]
  captain: PlanMove | null
  chip: string | null
  expected_pts: number
  gw: number
  hit_cost: number
  hits: number
  sells: PlanMove[]
  /**
   * Why this week's moves, in the objective's own terms (v12 W5 §6.5).
   *
   * ``None`` only when the trace could not be computed at all — a week that
   * does nothing carries a trace with no moves, because "this week does
   * nothing" and "the trace is broken" must not look alike on the board.
   *
   * Always ``None`` on an alternative plan: the trace is the objective's terms
   * at the plan the solver *returned*, and Plan B was returned by a different
   * solve. The board says so under the strip.
   */
  trace: PlanWeekTrace | null
  vice: PlanMove | null
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "PlanMove".
 */
export interface PlanMove {
  code: number
  ep: number
  name: string
  position: string
  /**
   * Buy price for an in, sell value for an out — in millions.
   */
  price: number | null
}
/**
 * One planned week's charges. Four of them are week-level on purpose:
 * a week with two transfers and one hit cannot attribute the hit to one of
 * them, and splitting it would be arithmetic dressed as a finding.
 *
 * Three of the objective's terms are **not** here — the XI, captain and vice
 * weightings and the bench seats (``milp.py:813-835``, including
 * ``_decision_scales``' per-week autosub scales). They price the whole squad
 * rather than a swap, so these numbers do not sum to ``expected_pts`` and
 * are not meant to. The board's caption says so in the same words.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "PlanWeekTrace".
 */
export interface PlanWeekTrace {
  /**
   * ``itb_value * bank`` on the horizon's **last** week, which is the only
   * week the objective prices the bank at (``milp.py:889``). ``None``
   * elsewhere, and ``None`` when the running bank is unknown.
   */
  bank_value: number | null
  ep_gain: number | null
  ft_after: number
  ft_basis: 'flat' | 'lambda'
  /**
   * What one banked free transfer is worth, priced at the horizon's end:
   * flat ``ft_value``, or λ at **this week's** banked count and the weeks left
   * after the horizon's last gameweek. The count is the week's and only the
   * basis is terminal, because the end of the horizon is the only place the
   * objective prices a free transfer at all (``milp.py:878-888``).
   */
  ft_shadow: number | null
  /**
   * The per-transfer friction this week, decayed exactly as the objective
   * decays it (``milp.py:867``).
   *
   * Charged even in a week the chip table recommends a wildcard for: the plan
   * on this payload is the base solve, which the solver returned with the
   * transfers charged and the free-transfer recurrence running. The week's
   * ``note`` says so.
   */
  ft_use_penalty: number
  ft_used: number
  gw: number
  hit_cost: number
  moves: PlanMoveTrace[]
  note: string
  price_charge: number | null
  theta: number | null
}
/**
 * One transfer, priced against the objective's own terms (v12 W5 §6.5).
 *
 * Not a counterfactual. ``ep_gain`` is the decayed expected-points
 * difference of a position-matched swap over the rest of the horizon — the
 * objective's own arithmetic at the plan the solver returned — and **not**
 * "the plan is this much worse without this move", which would need a
 * re-solve. ``None`` everywhere means unknown, never a measured zero.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "PlanMoveTrace".
 */
export interface PlanMoveTrace {
  buy_code: number | null
  buy_name: string
  ep_gain: number | null
  lambda_tilt: number | null
  note: string
  sell_code: number | null
  sell_name: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "PlanSummary".
 */
export interface PlanSummary {
  bench: WirePlayerRef[]
  buys: WirePlayerRef[]
  captain: WirePlayerRef
  /**
   * Raw expected points for ``gw`` alone, net of hits.
   */
  expected_pts: number
  gw: number
  hits: number
  /**
   * The same measure summed over the gameweeks the two plans share.
   */
  horizon_pts: number
  sells: WirePlayerRef[]
  vice: WirePlayerRef
  xi: WirePlayerRef[]
}
/**
 * v12 §3.2's readout, or its refusal.
 *
 * ``recall_population`` is a field rather than a footnote: recall here is
 * over the rows that carried a verdict, and the same word over every absent
 * player in the gameweek would be a much harsher number about a much larger
 * population.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "PresserGradesData".
 */
export interface PresserGradesData {
  absent_rows: number
  available: boolean
  by_source: SourceRows[]
  confusion: VerdictRow[]
  git_sha: string
  graded_gws: number[]
  note: string | null
  per_class: VerdictScore[]
  recall_population: string
  rows: number
  run_at: string
  verdicts_banked: number
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "SourceRows".
 */
export interface SourceRows {
  rows: number
  source: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "VerdictRow".
 */
export interface VerdictRow {
  n: number
  not_started: number
  started: number
  verdict: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "VerdictScore".
 */
export interface VerdictScore {
  n: number
  /**
   * P(did not start | this verdict). Absence is the event every class
   * claims, which is what makes the four numbers comparable.
   */
  precision: number
  recall: number
  verdict: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "PricePoint".
 */
export interface PricePoint {
  gw: number
  price: number
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "PriceSeries".
 */
export interface PriceSeries {
  code: number
  name: string
  points: PricePoint[]
}
/**
 * Whichever modes have been run. Each is independent and may be absent.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "QualityData".
 */
export interface QualityData {
  benchmark: BenchmarkEvaluation | null
  current: CurrentEvaluation | null
  decomposition: DecompositionData | null
  flag_latency: FlagLatencyData | null
  news_shadow: NewsShadowData | null
  presser_grades: PresserGradesData | null
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "ReviewAccuracyPoint".
 */
export interface ReviewAccuracyPoint {
  accuracy: number
  gw: number
}
/**
 * One gameweek's banked grade. Every field but ``gw`` has a default, so
 * a ledger written by an older build still renders.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "ReviewGw".
 */
export interface ReviewGw {
  accuracy: number | null
  chip: string | null
  gw: number
  hindsight: ReviewHindsight
  hits: number
  lanes: ReviewLane[]
  misses: ReviewMiss[]
  model_chip: string | null
  model_points: number | null
  my_points: number | null
  no_advice: boolean
  notices: string[]
  official_gross: number | null
  official_points: number | null
  our_bench_points: number | null
  /**
   * My overall FPL rank at the end of this gameweek.
   *
   * ``None`` for two situations the reader must not see merged: a gameweek
   * whose entry history was never banked, and — for the whole of this season's
   * existing ledger — **a gameweek graded before the field existed.** Grades
   * are banked and never re-derived (spec D2), so the trajectory begins empty
   * and fills forward from the next graded week. A chart drawing this must
   * show a gap, never a zero and never a line through it: zero is the best
   * rank in the game.
   */
  overall_rank: number | null
  points_on_bench: number | null
  post_deadline: boolean
  /**
   * The snapshot named above cannot be trusted to predate the deadline.
   *
   * **Two causes, and the reader must not be told only the first.** Either
   * every snapshot for the gameweek was written after the deadline, or the
   * run did not record when the deadline was — which is the ordinary state of
   * a gameweek graded late, after ``ADVICE_HISTORY_KEEP`` pruned the payload
   * the deadline was carried on. In that second case an in-time snapshot may
   * well exist on disk; there is simply nothing left to compare its stamp
   * against, and guessing would be worse than saying so.
   *
   * Either way the claim is the same and it is the weaker one: this table may
   * have seen team news nobody could act on. Related to ``post_deadline``
   * above — which is about the advice payload rather than the EP table — and
   * the two can disagree.
   */
  projection_post_deadline: boolean
  /**
   * The UTC stamp of the frozen EP table this grade was read against.
   *
   * ``None`` for a gameweek graded before v12 W5 existed, and for one where no
   * snapshot was ever written. Grades are banked and never re-derived (spec
   * D2), so every row already in the ledger keeps ``None`` for ever and the
   * column fills forward from the next graded week — drawn as absent, never as
   * a zero or a blank that reads like one.
   */
  projection_snapshot: string | null
  pwin_granularity_pp: number | null
  pwin_n: number | null
  pwin_seed: number | null
  reconciled: boolean | null
  reviewed_at: string | null
}
/**
 * The best legal eleven out of the fifteen I owned, by actual points.
 *
 * ``points`` and ``gap`` are ``None`` — never zero — when no legal eleven
 * could be built at all, which is what a fifteen the results frame does not
 * cover looks like. A zero there would bank a *negative* gap.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "ReviewHindsight".
 */
export interface ReviewHindsight {
  captain: number | null
  gap: number | null
  points: number | null
  xi: number[]
}
/**
 * One graded decision lane (spec D5).
 *
 * ``delta_pts`` and ``label`` are ``None`` — never zero — for a lane that
 * could not be built: the model's captain was not in my eleven, the model
 * sold a player I never owned, either side played a wildcard. "The model had
 * no opinion I could have acted on" and "the model agreed with me" are
 * different facts and the UI colours them differently.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "ReviewLane".
 */
export interface ReviewLane {
  aligned: boolean
  delta_pts: number | null
  /**
   * My choice minus the model's, in percentage points of P(win the
   * league). ``0.0`` on the bench and chip lanes by construction — the
   * simulation normalises every squad to its eleven and one armband.
   */
  delta_pwin: number | null
  label: ('Brilliant' | 'Good' | 'Aligned' | 'Inaccuracy' | 'Blunder') | null
  lane: 'transfers' | 'captaincy' | 'bench' | 'chip'
  mine: string | null
  model: string | null
  note: string | null
}
/**
 * A move the model flagged, I did not make, and that returned anyway.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "ReviewMiss".
 */
export interface ReviewMiss {
  code: number
  gain: number
  name: string
  over: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "ReviewLaneTotal".
 */
export interface ReviewLaneTotal {
  /**
   * How many gameweeks this lane was gradeable in. ``pts`` of zero over
   * ``graded`` of zero is "never measured", not "never wrong".
   */
  graded: number
  /**
   * Graded weeks this lane gained / lost points, counted strictly.
   *
   * A zero delta is neither, so ``wins + losses <= graded`` with slack — the
   * difference is the weeks I did exactly what the model did. A UI that
   * rendered ``wins / (wins + losses)`` would silently drop those weeks; the
   * denominator is ``graded``.
   */
  losses: number
  pts: number
  pwin: number
  wins: number
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "RivalDetailData".
 */
export interface RivalDetailData {
  captain: SquadPlayer | null
  chips_used: string[]
  entry: number
  live_points: number | null
  name: string
  player_name: string
  shared: SquadPlayer[]
  squad: SquadPlayer[]
  squad_gw: number
  team_value: number
  their_differentials: SquadPlayer[]
  total: number
  your_differentials: SquadPlayer[]
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "SquadPlayer".
 */
export interface SquadPlayer {
  code: number
  element: number
  is_captain: boolean
  multiplier: number
  name: string
  position: string
  price: number
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "RivalSummary".
 */
export interface RivalSummary {
  differentials: number
  entry: number
  event_total: number
  name: string
  overlap: number
  player_name: string
  rank: number
  total: number
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "SensitivityMove".
 */
export interface SensitivityMove {
  code: number
  count: number
  frequency: number
  gw: number
  kind: string
  label: string
  name: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "SensitivityPlan".
 */
export interface SensitivityPlan {
  buys: NamedPlayer[]
  captain: NamedPlayer | null
  count: number
  hits: number
  sells: NamedPlayer[]
  /**
   * Horizon expected points on the **true** EP table, so two signatures are
   * compared on the board the manager faces rather than on their own draws.
   */
  value: number
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "SensitivityReport".
 */
export interface SensitivityReport {
  available: boolean
  completed: number
  /**
   * The scenario sweep's own *estimation* noise on the players that
   * separate the two plans, in quadrature (plan A6).
   *
   * Not the σ behind the EP bands, and the difference is the point. A band
   * answers "what might he score" and is dominated by football's own variance.
   * This answers "how wrong might my forecast be" — the only question a margin
   * between two plans solved off the same board can be threatened by — and so
   * it stays on ``optimize.scenarios``' calibrated table alone.
   *
   * Computed at serve time from the banked components frame rather than stored
   * in the report, so a report swept before this field existed still gets the
   * line. ``None`` when there is no runner-up, no components frame, or nothing
   * in the symmetric difference — the card then prints its margin unqualified,
   * which is what it did before.
   */
  decision_sigma: number | null
  failures: number
  frequencies: SensitivityMove[]
  generated_at: string | null
  gw: number | null
  horizon: number
  k: number
  margin: number | null
  modal: SensitivityPlan | null
  notice: string | null
  runner_up: SensitivityPlan | null
  seed: number | null
  verdict: string | null
  wall_s: number | null
}
/**
 * One editable setting, as the Settings tab receives it (v12 W5 §6.2).
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "SettingRow".
 */
export interface SettingRow {
  help: string
  hi: number | null
  key: string
  kind: 'int' | 'float' | 'bool' | 'floats3' | 'pool'
  label: string
  lo: number | null
  section: string
  /**
   * Which file this value came from. ``local`` is ``config.local.toml``,
   * ``base`` is ``config.toml``, ``default`` is the dataclass — and the three
   * are different facts: only a ``local`` value can be reset.
   */
  source: 'local' | 'base' | 'default'
  /**
   * Whatever the merged config holds. ``None`` only for ``bench_curve``,
   * where it means "no curve — one flat bench weight", which is a real
   * setting and not an absent one.
   */
  value: unknown
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "SettingWrite".
 */
export interface SettingWrite {
  key: string
  /**
   * ``None`` removes the key from the overlay, so the value falls back to
   * ``config.toml`` or the dataclass default.
   */
  value: unknown
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "SettingsPanel".
 */
export interface SettingsPanel {
  apply_note: string
  /**
   * Why ``config.local.toml`` is being ignored, or ``None``. Also carries
   * the "no config.toml at all" case, which is the state a cold clone is in.
   */
  overlay_error: string | null
  rows: SettingRow[]
  /**
   * Whitelisted settings this build's ``Config`` does not have. Named
   * rather than dropped: a form that is quietly shorter is a setting nobody
   * can find and nobody knows is missing.
   */
  unavailable: string[]
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "SourceHealth".
 */
export interface SourceHealth {
  age_hours: number | null
  modified_at: string | null
  path: string
  present: boolean
  source: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "Staleness".
 */
export interface Staleness {
  advice_gw: number
  current_gw: number | null
  data_through_gw: number | null
  data_warning: string | null
  deadline: string
  deadline_passed: boolean
  generated_at: string
  reason: string
  stale: boolean
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "TickerCell".
 */
export interface TickerCell {
  difficulty: number
  gw: number
  home: boolean
  opponent: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "TickerData".
 */
export interface TickerData {
  gws: number[]
  source: 'odds' | 'elo'
  teams: TickerTeam[]
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "TickerTeam".
 */
export interface TickerTeam {
  cells: TickerCell[]
  code: number
  mean_difficulty: number
  name: string
  short_name: string
}
/**
 * One of the next three league games, as the explain panel lists them.
 *
 * Deliberately *not* ``NextFixture`` (``:87``), whose name it shadowed until
 * v12 W5: that one is the advised gameweek's single game, with an opponent
 * short name, a kickoff and a difficulty; this one is a gameweek number and
 * an opponent's full name. Two response models under one name gave the
 * schema generator two definitions it could only tell apart by mangling
 * both, and gave every ``from .schemas import NextFixture`` in the tree the
 * second class rather than the first.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "UpcomingFixture".
 */
export interface UpcomingFixture {
  gw: number
  home: boolean
  opponent: string
}
/**
 * A star, and optionally a sentence about why.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "WatchRequest".
 */
export interface WatchRequest {
  code: number
  /**
   * Three requests, not two. ``None`` — the key omitted — is "star him and
   * say nothing about the note", which keeps whatever note and star date the
   * row already has; ``""`` is "clear the note", which is what a cleared
   * textbox on the Watchlist tab sends; text sets it.
   *
   * The first two used to be one value, so a star from the explorer destroyed
   * a note typed on the Watchlist tab. Only a caller that means to write the
   * note sends the key at all.
   */
  note?: string | null
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "WatchRow".
 */
export interface WatchRow {
  code: number
  name: string
  note: string
  set_at: string
}
/**
 * Every starred player, name-resolved.
 *
 * ``rows`` is empty on a fresh clone and on a broken store alike — the
 * distinction is a printed line on the server, not a field here, because a
 * client that rendered "your watchlist may be corrupt" would be showing the
 * user a problem they cannot act on.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "WatchlistPanel".
 */
export interface WatchlistPanel {
  rows: WatchRow[]
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "WhatIfResult".
 */
export interface WhatIfResult {
  baseline: PlanSummary
  captain_changed: boolean
  delta_xpts: number
  transfers_changed: boolean
  verdict: string
  xi_in: WirePlayerRef[]
  xi_out: WirePlayerRef[]
  yours: PlanSummary
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "WireAdviceLatest".
 */
export interface WireAdviceLatest {
  advice: {
    [k: string]: unknown
  }
  deadline: string
  gw: number
  mode: string
  staleness: Staleness
}
/**
 * The banked report, or the honest empty one.
 *
 * ``available`` is what the card branches on. The route answers 200 either
 * way (spec §4) because this card sits beside populated ones and a 422 there
 * is indistinguishable from a broken endpoint.
 *
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "WireCalibrationReport".
 */
export interface WireCalibrationReport {
  available: boolean
  cumulative: {
    [k: string]: CalibrationHead
  }
  excluded: {
    [k: string]: unknown
  }[]
  gameweeks: CalibrationGw[]
  git_sha: string | null
  missing: number[]
  note: string | null
  omitted: {
    [k: string]: string
  }
  per_gw_omitted: {
    [k: string]: string
  }
  run_at: string | null
  season: string | null
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "WireHealth".
 */
export interface WireHealth {
  artifacts: ArtifactItem[]
  core_insights: CoreInsightsHealth | null
  data: SourceHealth[]
  data_through_gw: number | null
  /**
   * The newest ``gaffer-*.tar.gz`` in the configured backup directory.
   *
   * ``None`` means *never*, and the tab renders it as "never — run `gaffer
   * backup`" rather than as a blank cell. A zero-byte dict would have been the
   * other option and it is worse: it renders as a backup that happened and was
   * empty, which is the one outcome this feature exists to prevent.
   */
  last_backup: BackupHealth | null
  launchd: LaunchdHealth
  model_health: {
    [k: string]: unknown
  } | null
  models: WireModelHealth[]
  odds_key_present: boolean
  /**
   * What ``config.toml`` says this season is.
   */
  season_config: string | null
  /**
   * What the last refresh actually banked, derived from the events' own
   * deadlines. Read off disk, never off the API: this endpoint is polled by a
   * tab and must not depend on FPL being up.
   */
  season_ingested: string | null
  /**
   * Does the banked data's season match ``config.current_season``?
   *
   * Three states, not two. ``None`` is *cannot tell* — no events snapshot, or
   * deadlines that will not parse — and it is not an alarm: a cold clone has
   * no data to disagree with. The banner draws on ``False`` alone.
   */
  season_ok: boolean | null
  /**
   * Players per position the solver may consider, on top of the ones you own.
   *
   * Named for what it is on the wire — a solver pool — since a schema field
   * carries no TOML section with it. The value is ``optimizer_top_n()``'s, so
   * it is what an actual solve would get rather than what the file says.
   */
  solver_top_n: {
    [k: string]: number
  } | null
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "WireModelHealth".
 */
export interface WireModelHealth {
  metrics: {
    [k: string]: unknown
  }
  name: string
  saved_at: string | null
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "WireHistory".
 */
export interface WireHistory {
  backtests: {
    [k: string]: unknown
  }[]
  prices: PriceSeries[]
  runs: HistoryRun[]
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "WirePlanTimeline".
 */
export interface WirePlanTimeline {
  /**
   * Empty on every artifact written before v12, and on any run with
   * ``[optimizer] alt_plan_max_gap = 0``. The board draws no tab strip for an
   * empty list rather than a strip with one tab in it (v12 W3 §4.3).
   */
  alternatives: PlanAlternative[]
  /**
   * What is in the bank before the horizon's first move, in millions.
   *
   * ``SolveState.bank`` in tenths, through the same conversion every price on
   * this payload takes. ``None`` means the solve state carried no usable
   * figure — never 0.0, which is "fully invested".
   */
  bank: number | null
  generated_at: string
  gw: number
  weeks: PlanGw[]
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "WirePlayerExplain".
 */
export interface WirePlayerExplain {
  code: number
  ep_next: number
  fixtures: FixtureExplain[]
  name: string
  next_fixtures: UpcomingFixture[]
  position: string
  /**
   * ``penalties`` / ``free_kicks`` / ``corners``, each the user's override
   * file's word where it has one and FPL's otherwise — the same numbers
   * :class:`PlayerRow` serves, from the same loader.
   */
  set_pieces: {
    [k: string]: number | null
  }
  /**
   * Which of ``set_pieces``' three orders came from the user's override
   * file, a cleared one included. Additive and default-empty, so a client that
   * does not read it is unaffected.
   */
  set_pieces_manual: string[]
  team_name: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "WirePlayerRow".
 */
export interface WirePlayerRow {
  available: boolean
  chance_of_playing: number | null
  code: number
  corners_order: number | null
  element: number
  ep_hi: number | null
  ep_horizon: number
  /**
   * p25 of the noise model's distribution for ``ep_next`` — see
   * :mod:`gaffer.uncertainty`. Deliberately **not** ``ep_next`` minus
   * something: the calibrated path recentres, so the pair is quartiles rather
   * than a symmetric interval, and the UI labels it that way.
   *
   * ``None`` — never ``ep_next`` — when the components frame carries no
   * minutes model for him, or is absent altogether. A zero-width band on the
   * least-known player in the pool would read as certainty.
   */
  ep_lo: number | null
  ep_next: number
  /**
   * ``shield`` | ``sword`` | ``threat``, or ``None`` for the quadrant with
   * nothing to say.
   *
   * A ``Literal`` and not a ``str``, since v12 W5: ``routers.players
   * .field_class`` returns exactly these three and ``None``, the client has
   * always typed it as those three, and only the schema was saying ``str`` —
   * which the generated types then repeated, and the pitch's shirt colours
   * stopped compiling against.
   */
  field_class: ('shield' | 'sword' | 'threat') | null
  /**
   * Top-10k effective ownership from the latest banked scrape.
   *
   * ``None`` means *unknown*, and it means it in two different situations
   * that the UI renders identically and correctly: no field log at all, or a
   * log that does not carry this player because no sampled entry started him.
   * Neither is 0.0, which the reader would take as a measured differential.
   */
  field_eo: number | null
  /**
   * Field EO projected forward one gameweek, in percent.
   *
   * ``None`` means *no trend*, which is what one gameweek of samples buys —
   * and never 0.0, which is the different and stronger claim that nobody in
   * the top 10k starts him. Same contract as ``field_eo`` above.
   */
  field_eo_deadline: number | null
  /**
   * The observed move between the last two sampled gameweeks, in points of
   * EO. ``None`` when there is no earlier sample; ``0.0`` is a measurement —
   * the field held steady.
   */
  field_eo_delta: number | null
  /**
   * How many sampled entries the figure was measured over.
   *
   * ±2.8 from three hundred entries and ±2.8 from thirty are different claims
   * and the page is entitled to say which one it is showing.
   */
  field_n: number | null
  /**
   * The standard error on ``field_eo``, in percentage points.
   *
   * ``None`` for exactly the situations ``field_eo`` is ``None`` for, and — the
   * part worth stating — **never 0.0**. Zero here would be a claim of perfect
   * precision drawn from a sample of a few hundred entries, which is a stronger
   * statement than any number on this row is entitled to make.
   */
  field_se: number | null
  free_kicks_order: number | null
  in_squad: boolean
  /**
   * Points from the last four *finished* gameweeks, oldest first.
   *
   * Empty when ``data/live/player_gw.parquet`` has not been written — the
   * sparkline then renders an em dash rather than a flat line at zero.
   */
  last4: number[]
  league_eo: number
  name: string
  news: string
  ownership: number
  /**
   * ``P(points <= 2)`` under the same distribution.
   */
  p_blank: number | null
  /**
   * ``P(points >= 10)`` under the same distribution. Crude by construction:
   * it prices *forecast* error, not football's own variance.
   *
   * This is ``uncertainty.Band.p_haul``, the whole-forecast tail — *not*
   * ``models.assemble.p_haul``, which is P(2+ attacking returns) under a
   * Poisson and is served on the advice payload as ``p_attacking_haul``. Two
   * quantities, one page, one name until v9c (spec D3).
   */
  p_haul: number | null
  penalties_order: number | null
  position: string
  price: number
  /**
   * Kinds of set piece whose order above came from ``data/set_pieces.toml``
   * rather than from FPL. Empty on every machine with no override file.
   *
   * Includes a *cleared* order: a file that lists his club's queue and leaves
   * him out serves him ``None``, and that blank is the file's word as much as
   * a rank is. Only ``penalties`` reaches expected points; the other two move
   * the numbers on this row and nothing else.
   */
  set_piece_manual: string[]
  status: string
  team_code: number
  team_name: string
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "WireReview".
 */
export interface WireReview {
  gws: ReviewGw[]
  summary: WireReviewSummary | null
}
/**
 * This interface was referenced by `GafferApi`'s JSON-Schema
 * via the `definition` "WireReviewSummary".
 */
export interface WireReviewSummary {
  accuracy: ReviewAccuracyPoint[]
  best: {
    [k: string]: unknown
  } | null
  gws: number[]
  hindsight_gap: number
  hindsight_gap_gws: number
  lanes: {
    [k: string]: ReviewLaneTotal
  }
  points_on_bench: number
  /**
   * How many gameweeks that total covers. A season of unbanked histories
   * sums to zero over zero gameweeks, which is not an empty bench.
   */
  points_on_bench_gws: number
  reconciled_gws: number
  unreconciled_gws: number
  worst: {
    [k: string]: unknown
  } | null
}
