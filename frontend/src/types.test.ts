import { describe, expect, it } from 'vitest'
import {
  JOB_KINDS, JOB_KIND_LABEL, type JobKind, type JobRunView,
  type LeagueSimData, type LeagueWhatIfResult, type NextFixture,
  type PlayerRef,
} from './types'

describe('job types', () => {
  it('lists exactly the twelve kinds the backend allows', () => {
    // v8f added digest-friday and digest-tuesday as the eleventh and twelfth.
    expect([...JOB_KINDS]).toEqual(
      ['advise', 'advise-fast', 'evaluate', 'refresh-data', 'news-shadow',
       'snapshot', 'track-pens', 'field-scrape', 'review', 'sensitivity',
       'digest-friday', 'digest-tuesday'])
  })

  it('labels every kind for a button', () => {
    for (const kind of JOB_KINDS) {
      expect(JOB_KIND_LABEL[kind].length).toBeGreaterThan(0)
    }
  })

  it('types a run view the way the router serialises it', () => {
    const run: JobRunView = {
      id: 'abc', kind: 'advise', status: 'running',
      started_at: '2026-08-29T09:00:00+00:00', finished_at: null,
      error: null, summary: null, line_count: 3,
    }
    const kind: JobKind = run.kind
    expect(kind).toBe('advise')
  })
})

describe('league sim types', () => {
  it('types the sim payload the way the router serialises it', () => {
    const sim: LeagueSimData = {
      gw: 7, entries: 8, weeks_left: 32, n: 2000, seed: 20260831,
      rival_drift: 0.5, p_win: 0.21, p_top3: 0.55, exp_finish: 2.9,
      per_rival: [{ entry: 2, name: 'Ten Hag Hive', p_beat: 0.61 }],
      margin_quantiles: { p05: -80, p25: -20, p50: 12, p75: 44, p95: 110 },
      history: [{ gw: 6, p_win: 0.18, p_top3: 0.5, exp_finish: 3.1,
                  run_at: '2026-09-05T09:00:00+00:00' }],
      field_rate: 54.2, notice: null, legacy_win_probability: [],
      // v12 W4 §5.3. Populated the way a real machine serialises it today:
      // a green-arrow probability, and two headlines that are null with the
      // sentence saying what each is waiting for.
      field: {
        gw: 7, n: 2000, seed: 20260831, managers: 300,
        // eo_gw is 6, not 7: the sample can only be banked for the last
        // scored week, and §3.3 extrapolates it one gameweek forward.
        eo_source: 'last-sample', eo_gw: 6, field_draws: 8,
        unsampled_picks: 1, p_green: 0.48, waiting_for: null,
        p_top10k: null, top10k_waiting_for: 'a top-10k weekly score threshold',
        rank_slope: null, rank_slope_rows: 2,
        rank_waiting_for: '2 of 5 graded gameweeks',
        my_ep: 54.1, field_median_ep: 55.3,
      },
    }
    expect(sim.per_rival[0].p_beat).toBeGreaterThan(0)
    expect(sim.field?.p_top10k).toBeNull()
  })

  it('types the what-if result', () => {
    const out: LeagueWhatIfResult = {
      baseline_p_win: 0.21, p_win: 0.14, delta_p_win: -0.07,
      baseline_exp_finish: 2.9, exp_finish: 3.4, delta_rank: 0.5,
      table: [{ entry: 1, name: 'Mine', is_you: true, total: 300,
                p_win: 0.14, exp_finish: 3.4 }],
      unknown_codes: [],
    }
    expect(out.delta_p_win).toBeLessThan(0)
  })
})


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
