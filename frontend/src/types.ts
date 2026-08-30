export interface PlayerRef {
  code: number
  name: string
  position?: string
  ep: number
  tag?: string
  /** Share of noised scenarios that contained this move. Absent when the
   *  scenario sweep did not run ([scenarios] n = 0). */
  frequency?: number
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
}

export interface Component { label: string; points: number }

export interface FixtureExplain {
  gw: number
  opponent: string
  home: boolean
  kickoff_time: string | null
  components: Component[]
  minutes: { p_play: number; p60: number }
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
  available: boolean
  status: string
  news: string
  chance_of_playing: number | null
  penalties_order: number | null
  free_kicks_order: number | null
  corners_order: number | null
  in_squad: boolean
  last4: number[]
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
  win_probability: Array<{ name: string; total: number; p_win: number }>
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
}

export interface LiveTableRow {
  entry: number
  name: string
  pre_total: number
  live: number
  projected: number
  delta: number
}

export interface LiveState {
  active: boolean
  gw: number | null
  my_points: number
  matches_in_play: number
  players: LivePlayer[]
  table: LiveTableRow[]
  notice?: string | null
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
  minutes: { p_play: number; p60: number; xmins?: number | null }
  ep: number
}

export interface ComponentPlayer {
  code: number
  name: string
  position: string
  team_name: string
  ep: number
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

export const JOB_KINDS = ['advise', 'advise-fast', 'evaluate', 'refresh-data',
  'news-shadow', 'snapshot', 'track-pens'] as const

export type JobKind = typeof JOB_KINDS[number]

export const JOB_KIND_LABEL: Record<JobKind, string> = {
  advise: 'Run advise',
  'advise-fast': 'Fast advise',
  evaluate: 'Evaluate',
  'refresh-data': 'Refresh data',
  'news-shadow': 'Score news shadow',
  snapshot: 'Snapshot news',
  'track-pens': 'Track pens',
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
}

export interface PlanTimeline {
  gw: number
  generated_at: string
  weeks: PlanGw[]
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
