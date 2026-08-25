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
  chip_table: Array<{ chip: string; gw: number; gain: number
                      per_week: number }>
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
}
