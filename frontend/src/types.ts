export interface PlayerRef {
  code: number
  name: string
  position?: string
  ep: number
  tag?: string
}

export interface Staleness {
  advice_gw: number
  current_gw: number | null
  generated_at: string
  deadline: string
  deadline_passed: boolean
  stale: boolean
  reason: string
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
  chip_table: Array<{ chip: string; gw: number; gain: number }>
  strategy: Strategy | null
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
  weeks: Array<{ gw: number; gain: number }>
  best_gw: number
  best_gain: number
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
