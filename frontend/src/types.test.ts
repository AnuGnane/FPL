import { describe, expect, it } from 'vitest'
import {
  JOB_KINDS, JOB_KIND_LABEL, type JobKind, type JobRunView,
  type LeagueSimData, type LeagueWhatIfResult,
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
    }
    expect(sim.per_rival[0].p_beat).toBeGreaterThan(0)
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
