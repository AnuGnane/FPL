import { describe, expect, it } from 'vitest'
import {
  JOB_KINDS, JOB_KIND_LABEL, type JobKind, type JobRunView,
} from './types'

describe('job types', () => {
  it('lists exactly the seven kinds the backend allows', () => {
    expect([...JOB_KINDS]).toEqual(
      ['advise', 'advise-fast', 'evaluate', 'refresh-data', 'news-shadow',
       'snapshot', 'track-pens'])
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
