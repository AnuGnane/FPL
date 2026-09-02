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

export interface MoveFrequency {
  kind: 'buy' | 'sell' | 'hit' | 'chip' | 'captain' | 'no_transfer'
  code: number
  gw: number
  label: string
  count: number
  frequency: number
}

export interface ScenarioReport {
  n: number
  completed: number
  failures: number
  seed: number
  hold: boolean
  captain_frequency: number
  near_misses: Array<{ kind: string; code: number; gw: number; label: string
                       frequency: number }>
}

export interface Staleness {
  advice_gw: number
  current_gw: number | null
  generated_at: string
  deadline: string
  deadline_passed: boolean
  stale: boolean
  reason: string
  // Fresh advice can still be underinformed: the newest gameweek the model
  // has ingested, and the warning when that lags the gameweek just played.
  data_through_gw: number | null
  data_warning: string | null
}

export interface Strategy {
  lam: number
  gap: number
  weeks_left: number
  stance: string
  rival_name: string
}

/** One row of the advice payload's own chip table.
 *
 *  `threshold`, `play_now` and `note` are written by `run_advise` alongside
 *  the raw `evaluate_chips` columns — optional here because a payload banked
 *  before the chip policy landed (and, for `note`, any non-free-hit row) has
 *  none of them. */
export interface AdviceChipRow {
  chip: string
  gw: number
  gain: number
  per_week?: number | null
  threshold?: number | null
  play_now?: boolean
  note?: string | null
}

export interface Advice {
  gw: number
  xi: PlayerRef[]
  bench: PlayerRef[]
  captain: PlayerRef
  vice: PlayerRef
  buys: PlayerRef[]
  sells: PlayerRef[]
  hits: number
  expected_pts: number
  chip_table: AdviceChipRow[]
  strategy: Strategy | null
  // v4c: present only when the scenario sweep ran. Optional so an advice
  // payload written before v4c still types.
  move_frequencies?: MoveFrequency[]
  raw_optimum_agrees?: boolean | null
  scenarios?: ScenarioReport | null
  captain_field?: CaptainField
}

/** Where the captain stands against the top 10k (v10b §F1a).
 *
 * Absent — not null — when the backend had nothing to say: no field log, no
 * events row, or an element it could not resolve to a player. `eo` is null
 * when only the bootstrap's modal captain was available. `note` is the
 * server's own sentence and is rendered verbatim; formatting it here would be
 * a second voice saying the same number a slightly different way.
 */
export interface CaptainField {
  code: number
  eo: number | null
  se: number | null
  n: number | null
  gw: number
  field_class: 'shield' | 'sword' | null
  most_captained?: { code: number; name: string | null; gw: number } | null
  note: string
}

export interface AdviceLatest {
  gw: number
  mode: string
  deadline: string
  advice: Advice
  staleness: Staleness
}

export interface ChipPlanRow {
  chip: string
  weeks: Array<{ gw: number; gain: number; per_week: number }>
  best_gw: number
  best_gain: number
  /** Gain divided by the horizon weeks the chip is credited with. A wildcard
   *  covers every week from the one it is played, so only this is comparable
   *  between its weeks; for the one-week chips it equals best_gain. */
  best_gain_per_week: number
  /** How many gameweeks were scored — the window "best" was chosen from. */
  weeks_scored: number
  now_gain: number | null
  play_now_delta: number | null
  /** θ for this chip in the current gameweek: the surplus the best remaining
   *  week is expected to offer. Computed since v4c and declared only in
   *  v10b — until then the server computed it and pydantic dropped it. */
  threshold_now?: number | null
  play_now?: boolean | null
  /** θ per week, aligned by index with `weeks`. */
  thetas?: number[]
  /** `[from_gw, last_gw]`. The first element is the gameweek asked about, not
   *  the window's opening — so this reads "expires after GW19", never
   *  "window starts at". */
  window?: number[]
}

export interface ChipPlan {
  gw: number
  chips: ChipPlanRow[]
}

/** v10b §F2a. Mirrors the pydantic models field for field. */
export interface OutlookTeam {
  code: number
  /** Null when the teams snapshot was unreadable: the counts still hold and
   *  only the label is missing. */
  short_name: string | null
}

export interface OutlookWeek {
  gw: number
  fixtures: number
  doubles: OutlookTeam[]
  blanks: OutlookTeam[]
}

export interface FixtureOutlook {
  from_gw: number | null
  weeks: OutlookWeek[]
  /** Declared by the server rather than derived here: the empty state is the
   *  common case for months, and a client branching on the emptiness of two
   *  arrays is a client that will one day branch on `weeks.length`. */
  has_doubles: boolean
  has_blanks: boolean
  teams_known: boolean
  note: string | null
}

export interface Component { label: string; points: number }

export interface FixtureExplain {
  gw: number
  opponent: string
  home: boolean
  kickoff_time: string | null
  components: Component[]
  minutes: { p_play: number | null; p60: number | null }
  calibration_delta: number
  odds: {
    weight: number
    e_goals_against: number | null
    p_cs_model: number
    p_cs_blended: number
    e_gc_model: number
    e_gc_blended: number
  }
  ep: number
}

export interface PlayerExplain {
  code: number
  name: string
  position: string
  team_name: string
  ep_next: number
  fixtures: FixtureExplain[]
  next_fixtures: Array<{ gw: number; opponent: string; home: boolean }>
  set_pieces: Record<string, number | null>
}

export interface PlanSummary {
  gw: number
  xi: PlayerRef[]
  bench: PlayerRef[]
  captain: PlayerRef
  vice: PlayerRef
  buys: PlayerRef[]
  sells: PlayerRef[]
  hits: number
  // Both point measures count the captain twice and subtract hit costs, so
  // they read higher than This Week's plain XI sum. Label them wherever shown.
  expected_pts: number
  horizon_pts: number
}

export interface WhatIfResult {
  baseline: PlanSummary
  yours: PlanSummary
  delta_xpts: number
  xi_in: PlayerRef[]
  xi_out: PlayerRef[]
  transfers_changed: boolean
  captain_changed: boolean
  verdict: string
}

export interface WhatIfRequest {
  lock: number[]
  ban: number[]
  force_in: number[]
  max_hits: number
  chip: 'none' | 'wc' | 'bb' | 'fh' | 'tc'
  horizon: number | null
}

export interface PlayerRow {
  code: number
  element: number
  name: string
  position: string
  team_code: number
  team_name: string
  price: number
  ep_next: number
  ep_horizon: number
  ownership: number
  league_eo: number
  /** Top-10k EO from the latest field scrape; null = never scraped, or no
   *  sampled entry started him. Never 0 for "unknown". */
  field_eo: number | null
  /** The standard error on `field_eo`, in percentage points. Null wherever
   *  `field_eo` is null, and — the part worth stating — never 0: zero would be
   *  a claim of perfect precision from a sample of a few hundred entries. */
  field_se: number | null
  /** How many sampled entries the figure was measured over. ±2.8 from three
   *  hundred and ±2.8 from thirty are different claims. */
  field_n: number | null
  field_class: 'shield' | 'sword' | 'threat' | null
  available: boolean
  status: string
  news: string
  chance_of_playing: number | null
  penalties_order: number | null
  free_kicks_order: number | null
  corners_order: number | null
  in_squad: boolean
  last4: number[]
  /** p25 of the scenario sweep's own noise on `ep_next`. Null — never
   *  `ep_next` — when the minutes model has nothing to say about him. Not a
   *  symmetric interval: the calibrated path recentres, so the pair is
   *  quartiles and the UI labels it that way. */
  ep_lo: number | null
  ep_hi: number | null
  /** P(10+ points) and P(2 or fewer) under the same distribution. Crude by
   *  construction: they price forecast error, not football's variance. */
  p_haul: number | null
  p_blank: number | null
}

export interface StandingRow {
  entry: number
  name: string
  player_name: string
  rank: number
  total: number
  event_total: number
  is_you: boolean
}

export interface LeagueRaceData {
  league_id: number
  entry_id: number
  standings: StandingRow[]
  trajectory: Array<{
    entry: number
    name: string
    points: Array<{ gw: number; points: number; total: number }>
  }>
  gap: Array<{ gw: number; gap: number }>
  win_probability: WinProb[]
  lam: number
  stance: string
  lam_explained: string
}

export interface SquadPlayer {
  code: number
  element: number
  name: string
  position: string
  price: number
  is_captain: boolean
  multiplier: number
}

export interface RivalSummary {
  entry: number
  name: string
  player_name: string
  rank: number
  total: number
  event_total: number
  overlap: number
  differentials: number
}

export interface RivalDetailData {
  entry: number
  name: string
  player_name: string
  total: number
  team_value: number
  chips_used: string[]
  captain: SquadPlayer | null
  // The gameweek the squad was picked in: picks are public only for finished
  // gameweeks, so this trails `live_points`' gameweek while one is in play.
  squad_gw: number
  squad: SquadPlayer[]
  shared: SquadPlayer[]
  their_differentials: SquadPlayer[]
  your_differentials: SquadPlayer[]
  live_points: number | null
}

export interface LivePlayer {
  element: number
  code: number
  name: string
  position: string
  multiplier: number
  points: number
  provisional_bonus: number
  minutes: number
  status: 'played' | 'playing' | 'yet to play'
  tier_eo?: number | null
  tier_eo_se?: number | null
  selected_by_percent?: number | null
  // v8d
  projected_out?: boolean
  projected_in?: boolean
  sub_partner?: number | null
  sub_reason?: string | null
  remaining_ep?: number | null
}

export interface LiveTableRow {
  entry: number
  name: string
  pre_total: number
  live: number
  projected: number
  delta: number
  projected_live?: number | null
  remaining_ep?: number | null
  race?: number | null
}

export interface LiveSafety {
  entry: number
  name: string
  role: 'above' | 'below' | 'leader'
  margin: number
  need: number
}

export interface LiveRacePoint {
  at: string
  you: number
  rival?: number | null
}

export interface LiveState {
  active: boolean
  gw: number | null
  my_points: number
  matches_in_play: number
  players: LivePlayer[]
  table: LiveTableRow[]
  notice?: string | null
  my_projected_points?: number
  my_race?: number | null
  race_reference?: number | null
  race_series?: LiveRacePoint[]
  safety?: LiveSafety[]
  rival_name?: string | null
  race_notice?: string | null
}

export interface HistoryData {
  runs: Array<{
    gw: number
    deadline: string
    captain: string
    buys: string[]
    sells: string[]
    hits: number
    expected_pts: number
    actual_pts: number | null
  }>
  prices: Array<{
    code: number
    name: string
    points: Array<{ gw: number; price: number }>
  }>
  backtests: Array<Record<string, unknown>>
}

export interface HealthData {
  data: Array<{
    source: string
    path: string
    present: boolean
    modified_at: string | null
    age_hours: number | null
  }>
  models: Array<{
    name: string
    saved_at: string | null
    metrics: Record<string, unknown>
  }>
  launchd: {
    log: string
    present: boolean
    modified_at: string | null
    last_line: string | null
  }
  odds_key_present: boolean
  model_health: Record<string, unknown> | null
  artifacts: Array<{ name: string; bytes: number }>
  // Three states, not two: null is "cannot tell" (no events snapshot yet),
  // and the mismatch banner draws on false alone.
  season_ok?: boolean | null
  season_config?: string | null
  season_ingested?: string | null
}

export interface TickerData {
  gws: number[]
  source: 'odds' | 'elo'
  teams: Array<{
    code: number
    name: string
    short_name: string
    mean_difficulty: number
    cells: Array<{
      gw: number
      opponent: string
      home: boolean
      difficulty: number
    }>
  }>
}

export interface CategoryMetrics {
  rmse: number
  mae: number
  n: number
}

export interface ReferenceMetrics {
  rmse: number
  mae: number
}

export interface ReliabilityBin {
  n: number
  pred: number
  obs: number
}

export interface HeadMetrics {
  /** null for a head with nothing to score — NaN is not JSON. */
  log_loss: number | null
  reliability: ReliabilityBin[]
}

export type StratifiedTable = Record<string, CategoryMetrics>

export interface CurrentEvaluation {
  run_at: string
  git_sha: string
  holdout_slots: number
  stratified: Record<string, StratifiedTable>
  heads: Record<string, HeadMetrics>
  baselines: Record<string, StratifiedTable>
}

export interface BenchmarkEvaluation {
  run_at: string
  git_sha: string
  test_season: string
  stratified: Record<string, StratifiedTable>
  references: Record<string, Record<string, ReferenceMetrics>>
  caveat: string
}

export interface DecompositionCell {
  total: number
  per_gw: number
  hits: number
}

export interface DecompositionData {
  run_at: string
  git_sha: string
  season: string
  start_gw: number
  cells: Record<string, DecompositionCell>
  forecast_gap_h3: number
  planning_ceiling: number
}

export interface QualityData {
  current: CurrentEvaluation | null
  benchmark: BenchmarkEvaluation | null
  decomposition: DecompositionData | null
  news_shadow: NewsShadowData | null
}

export interface ChipWorkbenchRow {
  chip: string
  gw: number
  gain: number
  per_week: number | null
  /** The θ bar for that chip in that week — the surplus the best remaining
   *  week is expected to offer. Null on advice written before the chip
   *  policy landed. */
  threshold: number | null
  play_now: boolean
  note: string | null
}

export interface ChipSquadPlayer {
  code: number
  name: string
  position: string
  price: number
  ep: number
}

export interface SquadDiff {
  gain_over_horizon: number
  recommend: boolean
  kept: ChipSquadPlayer[]
  dropped: ChipSquadPlayer[]
  added: ChipSquadPlayer[]
}

export interface ChipsWorkbench {
  gw: number
  chips: ChipWorkbenchRow[]
  wildcard: SquadDiff | null
}

export interface ComponentFixture {
  gw: number
  opponent: string
  home: boolean
  kickoff_time: string | null
  components: Component[]
  /**
   * How much of the Goals term is penalty duty, when any of it is. Not a
   * component: it was folded into e_goals before the terms were assembled, so
   * it is already inside Goals and the panel prints it as an annotation under
   * that row rather than as a line of its own.
   */
  pen_taker: number | null
  // `xmins` is p_play * (45 + 45 * p60), derived server-side. Null where the
  // minutes model has no opinion, which the xMin column prints as an em dash —
  // an un-modelled player is not a player expected to play no minutes.
  // `p_play` is null, never 0, for a frame with no minutes model: zero there
  // would say the model expects him not to play. `p60` carries the same
  // convention — zero there says he will not see the hour out.
  minutes: { p_play: number | null; p60: number | null
             xmins?: number | null }
  ep: number
}

export interface ComponentPlayer {
  code: number
  name: string
  position: string
  team_name: string
  ep: number
  /** The requested gameweek's EP alone. `ep` above is a horizon sum, which is
   *  not a number the σ table has ever seen — this is the one the band
   *  brackets. */
  ep_gw: number | null
  sigma: number | null
  ep_lo: number | null
  ep_hi: number | null
  p_haul: number | null
  p_blank: number | null
  fixtures: ComponentFixture[]
}

export interface ComponentsBreakdown {
  gw: number
  players: ComponentPlayer[]
}

export interface AdvicePlayerRef {
  code: number
  name: string
}

export interface EpMover {
  code: number
  name: string
  ep_prev: number
  ep_now: number
  delta: number
}

export interface AdviceDiff {
  gw: number
  /** False on a first run of the week — the ordinary case, not an error. */
  available: boolean
  changed: boolean
  previous_at: string | null
  current_at: string | null
  buys_added: AdvicePlayerRef[]
  buys_dropped: AdvicePlayerRef[]
  sells_added: AdvicePlayerRef[]
  sells_dropped: AdvicePlayerRef[]
  captain_from: AdvicePlayerRef | null
  captain_to: AdvicePlayerRef | null
  chip_from: string | null
  chip_to: string | null
  expected_pts_delta: number
  ep_movers: EpMover[]
  /** null when there is no predecessor breakdown — not the same as 0. */
  ep_movers_count: number | null
}

export interface NewsRow {
  code: number
  name: string
  team_name: string
  p_play_news: number
  p_play_flags: number
  e_min_news: number
  e_min_flags: number
  status: string | null
  chance_of_playing: number | null
  official_note: string | null
  injury_type: string | null
  expected_return_gw: number | null
  p_start_hint: number | null
  /** 'xi' | 'doubt' | 'out', or null when no line-up named him. */
  lineup_hint: string | null
  source: string | null
  fetched_at: string | null
}

export interface NewsPanelData {
  gw: number
  moved: number
  rows: NewsRow[]
}

export interface NewsShadowSummary {
  brier_news: number
  brier_flags: number
  mae_news: number
  mae_flags: number
  rows: number
}

export interface NewsShadowGw extends NewsShadowSummary {
  gw: number
  cum_brier_news: number
  cum_brier_flags: number
  cum_mae_news: number
  cum_mae_flags: number
}

export interface NewsShadowData {
  run_at: string
  git_sha: string
  /** Zero until a gameweek the log covers has actually been played. */
  rows: number
  overall: Partial<NewsShadowSummary>
  by_gw: NewsShadowGw[]
}

/** One probability head's calibration, or its refusal (v9d §4). */
export interface CalibrationHead {
  /** 'scored' or 'insufficient' — a field rather than a missing key, so the
   *  card renders "not enough data" without branching on absence. */
  status: string
  n: number
  brier: number | null
  log_loss: number | null
  reliability: ReliabilityBin[]
}

export interface CalibrationGw {
  gw: number
  /** Joined player-fixture rows for the week — how much data the gameweek
   *  had, not how much any head graded. Per-head counts diverge from it and
   *  from each other (p_cs is club-fixture grain, p_haul drops rows with no
   *  banked e_goals), so each head carries its own `n` and the card prints
   *  that one beside the cell. */
  n: number
  heads: Record<string, CalibrationHead>
}

export interface CalibrationData {
  available: boolean
  run_at: string | null
  git_sha: string | null
  season: string | null
  gameweeks: CalibrationGw[]
  cumulative: Record<string, CalibrationHead>
  /** Head -> why it is not graded. p_start is never banked. */
  omitted: Record<string, string>
  /** Head -> why it has no per-gameweek column, though it is graded in the
   *  cumulative row. p_cs is one clean sheet per club-fixture, about twenty
   *  a gameweek, under the report's sample floor.
   *
   *  Required, not optional: `CalibrationReport.per_gw_omitted` is a pydantic
   *  field defaulting to `{}` (`web/schemas.py:962`), so it is on the wire
   *  even when empty. The card reads it unguarded, and this is the line that
   *  says why no `?? {}` is needed. */
  per_gw_omitted: Record<string, string>
  excluded: Array<{ gw: number; reason: string }>
  missing: number[]
  note: string | null
}

export const JOB_KINDS = ['advise', 'advise-fast', 'evaluate', 'refresh-data',
  'news-shadow', 'snapshot', 'track-pens', 'field-scrape', 'review',
  'sensitivity', 'digest-friday', 'digest-tuesday'] as const

export type JobKind = typeof JOB_KINDS[number]

export const JOB_KIND_LABEL: Record<JobKind, string> = {
  advise: 'Run advise',
  'advise-fast': 'Fast advise',
  evaluate: 'Evaluate',
  'refresh-data': 'Refresh data',
  'news-shadow': 'Score news shadow',
  snapshot: 'Snapshot news',
  'track-pens': 'Track pens',
  'field-scrape': 'Field scrape',
  review: 'Review last week',
  sensitivity: 'Run sensitivity',
  'digest-friday': 'Friday briefing',
  'digest-tuesday': 'Tuesday debrief',
}

export interface JobRunView {
  id: string
  kind: JobKind
  status: 'queued' | 'running' | 'done' | 'failed'
  started_at: string
  finished_at: string | null
  error: string | null
  summary: string | null
  line_count: number
}

export interface PlanMove {
  code: number
  name: string
  position: string
  ep: number
  price: number | null
}

export interface PlanGw {
  gw: number
  buys: PlanMove[]
  sells: PlanMove[]
  hits: number
  hit_cost: number
  chip: string | null
  captain: PlanMove | null
  vice: PlanMove | null
  expected_pts: number
  /** What is left in the bank after this week's moves, in millions.
   *
   *  Null is *unknown*, never 0.0 — that is "fully invested", a real and
   *  different state. Once a move with no price breaks the running total it
   *  stays broken: this week and every later one are null. */
  bank: number | null
}

export interface PlanTimeline {
  gw: number
  generated_at: string
  weeks: PlanGw[]
  /** The bank before the horizon's first move, in millions. Null is unknown
   *  and never 0.0, exactly as on each week. */
  bank: number | null
}

export interface MatrixCell {
  gw: number
  opponent: string
  home: boolean
  /** Difficulty for attackers, 0 easiest to 1 hardest. */
  attack: number
  /** Difficulty of keeping a clean sheet, 0 easiest to 1 hardest. */
  defence: number
}

export interface MatrixTeam {
  code: number
  name: string
  short_name: string
  cells: MatrixCell[]
  mean_attack: number
  mean_defence: number
}

export interface FixtureMatrixData {
  gws: number[]
  teams: MatrixTeam[]
  source: 'dixon_coles' | 'none'
}

export interface JournalRow {
  gw: number
  model_pts: number
  actual_pts: number
  delta: number
  model_captain: string | null
  actual_captain: string | null
  model_buys: string[]
  model_sells: string[]
  /** Every banked run of this gameweek was written after its deadline: the
   *  model's side of this row saw team news the user did not. */
  post_deadline?: boolean
}

export interface JournalPoint {
  gw: number
  model: number
  actual: number
  delta: number
}

export interface JournalData {
  rows: JournalRow[]
  cumulative: JournalPoint[]
  built_at: string | null
}

/**
 * One gameweek of `reports/pen_tracker.json`. Everything but `gw` is optional
 * because a week that would not read is written as `{gw, error}` — the same
 * one-model-two-shapes contract the server's `PenTrackerGw` carries.
 */
export interface PenTrackerGw {
  gw: number
  instrument?: string | null
  rows?: number | null
  covered_rows?: number | null
  team_games?: number | null
  component_rows?: number | null
  predicted_ep_pen_taker?: number | null
  predicted_takers?: number | null
  pens_taken?: number | null
  pens_by_first_choice?: number | null
  taker_hit_rate?: number | null
  pens_per_team_game?: number | null
  realized_pen_points?: number | null
  error?: string | null
}

export interface PenTrackerTotals {
  gws?: number | null
  instruments?: string[]
  team_games?: number | null
  predicted_ep_pen_taker?: number | null
  pens_taken?: number | null
  pens_by_first_choice?: number | null
  taker_hit_rate?: number | null
  pens_per_team_game?: number | null
  league_pens_pg_served?: number | null
  realized_pen_points?: number | null
}

export interface PenTrackerData {
  season: string
  gws: PenTrackerGw[]
  season_totals: PenTrackerTotals
  notes: string[]
}

/** One row of the pre-v8c parametric pairwise table — see
 *  web/schemas.py::WinProb. */
export interface WinProb {
  name: string
  total: number
  p_win: number
}

/** GET /api/league/sim — see web/schemas.py::LeagueSimData. */
export interface RivalBeat {
  entry: number
  name: string
  /** null when the entry's squad could not be read (private, or joined after
   *  the gameweek) — listed, but left out of the simulated race. */
  p_beat: number | null
}

export interface SimPoint {
  gw: number
  p_win: number
  p_top3: number
  exp_finish: number
  run_at: string
}

export interface LeagueSimData {
  gw: number
  entries: number
  weeks_left: number
  /** Simulations per run, and the seed they were drawn under. Rendered next
   *  to the headline: a probability with no n beside it is a decoration. */
  n: number
  seed: number
  rival_drift: number
  p_win: number
  p_top3: number
  exp_finish: number
  per_rival: RivalBeat[]
  margin_quantiles: Record<string, number>
  history: SimPoint[]
  /** null when no field sample is banked — rivals then do not drift. */
  field_rate: number | null
  notice: string | null
  legacy_win_probability: WinProb[]
}

export type LeagueWhatIfEvent = 'haul' | 'blank' | 'score'

export interface LeagueWhatIfRequest {
  pins: { code: number, event: LeagueWhatIfEvent }[]
  captain_override?: number | null
  rival_captain_blanks?: number | null
  /** Answer from the server's cache or not at all — a 204 with no body. Set
   *  by This Week's chip, which is decoration and must never make a cold
   *  page load fetch fifty rival squads. */
  cached_only?: boolean
}

export interface LeagueWhatIfRow {
  entry: number
  name: string
  is_you: boolean
  total: number
  /** The entry's win frequency in the same run as the headline — not a
   *  renormalised pairwise number. null when the squad could not be read. */
  p_win: number | null
  exp_finish: number
}

export interface LeagueWhatIfResult {
  baseline_p_win: number
  p_win: number
  delta_p_win: number
  baseline_exp_finish: number
  exp_finish: number
  delta_rank: number
  table: LeagueWhatIfRow[]
  /** Codes the server could not resolve — a stale tab pinning a player who
   *  has left the game. Shown, never swallowed. */
  unknown_codes: number[]
}

export type ReviewLaneName = 'transfers' | 'captaincy' | 'bench' | 'chip'

export type ReviewLabel =
  'Brilliant' | 'Good' | 'Aligned' | 'Inaccuracy' | 'Blunder'

export interface ReviewLane {
  lane: ReviewLaneName
  /** null — never 0 — for a lane that could not be built. */
  delta_pts: number | null
  /** Percentage points of P(win). 0 on bench and chip by construction. */
  delta_pwin: number | null
  label: ReviewLabel | null
  aligned: boolean
  mine: string | null
  model: string | null
  note: string | null
}

export interface ReviewMiss {
  code: number
  name: string
  over: string
  gain: number
}

export interface ReviewHindsight {
  /** null — never 0 — when no legal eleven could be built from the fifteen. */
  points: number | null
  xi: number[]
  captain: number | null
  gap: number | null
}

export interface ReviewGw {
  gw: number
  reviewed_at: string | null
  no_advice: boolean
  post_deadline: boolean
  my_points: number | null
  official_points: number | null
  official_gross: number | null
  hits: number
  reconciled: boolean | null
  chip: string | null
  model_chip: string | null
  points_on_bench: number | null
  /** My overall FPL rank at the end of this gameweek.
   *
   *  Null for a gameweek whose entry history was never banked, and — for every
   *  row already in this season's ledger — for a gameweek graded before the
   *  field existed. Grades are banked and never re-derived, so the trajectory
   *  begins empty and fills forward. A chart must draw a null as a gap: never
   *  a zero, and never a line through it, because zero is the best rank in the
   *  game. */
  overall_rank: number | null
  our_bench_points: number | null
  model_points: number | null
  accuracy: number | null
  pwin_n: number | null
  pwin_seed: number | null
  pwin_granularity_pp: number | null
  lanes: ReviewLane[]
  misses: ReviewMiss[]
  hindsight: ReviewHindsight
  notices: string[]
}

export interface ReviewLaneTotal {
  pts: number
  pwin: number
  graded: number
  /** Graded weeks this lane gained / lost points, counted strictly: a zero
   *  delta is neither, so `wins + losses <= graded` with slack. The
   *  denominator to render against is `graded`, never `wins + losses` —
   *  that would silently drop the weeks I did what the model did. */
  wins: number
  losses: number
}

export interface ReviewSummary {
  gws: number[]
  lanes: Record<string, ReviewLaneTotal>
  accuracy: { gw: number, accuracy: number }[]
  points_on_bench: number
  /** Gameweeks the bench total covers — zero over zero is not an empty
   *  bench. Same for the hindsight gap. */
  points_on_bench_gws: number
  hindsight_gap: number
  hindsight_gap_gws: number
  reconciled_gws: number
  unreconciled_gws: number
  best: (ReviewLane & { gw: number }) | null
  worst: (ReviewLane & { gw: number }) | null
}

export interface ReviewData {
  gws: ReviewGw[]
  summary: ReviewSummary | null
}

// --- v8e: overrides, sensitivity, drafts -------------------------------

export interface OverrideRow {
  code: number
  name: string
  p_play: number | null
  e_min: number | null
  note: string
  set_at: string
  /** What the model had for him when the pin was made, not now. */
  model_p_play: number | null
  model_e_min: number | null
}

export interface OverridesPanel {
  active: boolean
  rows: OverrideRow[]
  /** Accepted, and worth a second look: an e_min pin that implies a far
   *  higher probability of playing than the p_play beside it. Null when the
   *  two readings are coherent. */
  warning: string | null
}

/** POST /api/overrides. At least one of the two numbers must be present. */
export interface OverrideRequest {
  code: number
  p_play: number | null
  e_min: number | null
  note: string
}

export interface NamedPlayer {
  code: number
  name: string
  position?: string
}

export interface SensitivityMove {
  kind: string
  code: number
  gw: number
  label: string
  name?: string
  count: number
  frequency: number
}

export interface SensitivityPlan {
  count: number
  buys: NamedPlayer[]
  sells: NamedPlayer[]
  captain: NamedPlayer | null
  hits: number
  value: number
}

export interface SensitivityReport {
  available: boolean
  gw: number | null
  k: number
  completed: number
  failures: number
  seed: number | null
  horizon: number
  wall_s: number | null
  generated_at: string | null
  notice: string | null
  frequencies: SensitivityMove[]
  modal: SensitivityPlan | null
  runner_up: SensitivityPlan | null
  margin: number | null
  verdict: string | null
  /** The sweep's own noise on the players that separate the modal plan from
   *  the runner-up, in quadrature. Null when there is no comparison to make. */
  decision_sigma: number | null
}

export interface DraftRow {
  name: string
  created_at: string
  constraints: WhatIfRequest
}

export interface DraftList { drafts: DraftRow[] }

/** POST /api/drafts. */
export interface DraftSaveRequest {
  name: string
  constraints: WhatIfRequest
}

/** POST /api/drafts/compare — at most `MAX_COMPARE` names. */
export interface DraftCompareRequest { names: string[] }

export interface DraftCompareRow {
  name: string
  is_reference: boolean
  solved_at: string
  horizon_pts: number | null
  expected_pts: number | null
  delta_xpts: number | null
  hits: number | null
  chip: string | null
  /** Gameweeks this row's plan covers, which is not always the comparison's:
   *  a free hit is a one-week squad and `DraftCompare.weeks` is the shorter
   *  shared window every row was scored over. */
  horizon: number | null
  buys: PlayerRef[]
  sells: PlayerRef[]
  captain: PlayerRef | null
  error: string | null
}

export interface DraftCompare {
  gw: number
  weeks: number
  rows: DraftCompareRow[]
}

export interface MissRow {
  code: number
  name: string
  position: string
  price: number | null
  ep: number
  actual: number
  minutes: number
  /** actual - ep, signed. Positive is a player the model under-rated;
   *  negative is one it may have talked somebody into buying. */
  miss: number
}

export interface MissesData {
  /** null when no gameweek has both a banked forecast and a banked result —
   *  an absent card, not a card of zeros. */
  gw: number | null
  rows: MissRow[]
}

export interface ConfidenceTier {
  tier: 'early' | 'mixed' | 'backed'
  reviewed: number
  graded: number
  wins: number
  losses: number
  aligned: number
  /** The whole product: a sentence quoting counts. Never a percentage. */
  text: string
}

export interface ConfidenceData {
  captain: ConfidenceTier
}

export interface WatchRow {
  code: number
  name: string
  note: string
  set_at: string
}

export interface WatchlistPanel {
  rows: WatchRow[]
}

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
  /** Set only on a digest whose build failed; the card says so. */
  error: string | null
}

export interface DigestPanel {
  available: boolean
  digest: Digest | null
}
