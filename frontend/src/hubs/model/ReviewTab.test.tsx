import { render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ReviewTab from './ReviewTab'
import type { ReviewData } from '../../types'

const LANES: ReviewData['gws'][number]['lanes'] = [
  { lane: 'transfers', delta_pts: -7, delta_pwin: -0.3, label: 'Blunder',
    aligned: false, mine: 'no move', model: 'Blank->Guehi', note: null },
  { lane: 'captaincy', delta_pts: 4, delta_pwin: 0.2, label: 'Brilliant',
    aligned: false, mine: 'Salah', model: 'Haaland', note: null },
  { lane: 'bench', delta_pts: 0, delta_pwin: 0, label: 'Aligned',
    aligned: true, mine: 'A, B', model: 'A, B', note: null },
  // delta_pwin 0 rather than null on purpose: an older banked row can carry
  // it, so the em-dash rail has to hold on the shape the server could emit.
  { lane: 'chip', delta_pts: null, delta_pwin: 0, label: null,
    aligned: false, mine: 'none', model: 'wildcard',
    note: 'a wildcard changes the squad' },
]

const DATA: ReviewData = {
  gws: [{
    gw: 2, reviewed_at: '2026-09-01T09:00:00+00:00', no_advice: false,
    post_deadline: false, my_points: 61, official_points: 61,
    official_gross: 65, hits: 1, reconciled: true, chip: null,
    model_chip: 'bboost', points_on_bench: 5, overall_rank: 412233,
    our_bench_points: 5,
    model_points: 68, accuracy: 89, pwin_n: 2000, pwin_seed: 20260831,
    pwin_granularity_pp: 0.05, lanes: LANES,
    misses: [{ code: 16, name: 'Guehi', over: 'Blank', gain: 15 }],
    hindsight: { points: 74, xi: [1, 2, 3], captain: 3, gap: 13 },
    notices: [],
  }],
  summary: {
    gws: [2], lanes: {
      transfers: { pts: -7, pwin: -0.3, graded: 1, wins: 0, losses: 1 },
      captaincy: { pts: 4, pwin: 0.2, graded: 1, wins: 1, losses: 0 },
      bench: { pts: 0, pwin: 0, graded: 1, wins: 0, losses: 0 },
      chip: { pts: 0, pwin: 0, graded: 0, wins: 0, losses: 0 },
    },
    accuracy: [{ gw: 2, accuracy: 89 }], points_on_bench: 5,
    points_on_bench_gws: 1, hindsight_gap: 13, hindsight_gap_gws: 1,
    reconciled_gws: 1, unreconciled_gws: 0,
    best: { ...LANES[1], gw: 2 }, worst: { ...LANES[0], gw: 2 },
  },
}

function mock(data: ReviewData | Error) {
  vi.stubGlobal('fetch', vi.fn(() => (data instanceof Error
    ? Promise.reject(data)
    : Promise.resolve({ ok: true, json: () => Promise.resolve(data) }))))
}

describe('ReviewTab', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('shows an empty state before anything has been reviewed', async () => {
    mock({ gws: [], summary: null })
    render(<ReviewTab />)
    expect(await screen.findByText(/Nothing reviewed yet/i)).toBeTruthy()
  })

  it('names a command in the empty state, not a button it cannot press',
     async () => {
       // An unwired `action` renders as a <code> block, so it has to read as
       // something you can type. "Review last week" is the label on the hub's
       // JobButton and belongs in the prose.
       mock({ gws: [], summary: null })
       render(<ReviewTab />)
       const empty = await screen.findByTestId('empty-state')
       expect(empty.querySelector('code')?.textContent).toBe('gaffer review')
       expect(empty.querySelector('button')).toBeNull()
     })

  it('falls back to the empty state when the request fails', async () => {
    mock(new Error('offline'))
    render(<ReviewTab />)
    expect(await screen.findByText(/Nothing reviewed yet/i)).toBeTruthy()
  })

  it('renders a card per reviewed gameweek with its accuracy', async () => {
    mock(DATA)
    render(<ReviewTab />)
    expect(await screen.findByText('GW2')).toBeTruthy()
    expect(screen.getByText('89')).toBeTruthy()
  })

  it('labels every graded lane', async () => {
    mock(DATA)
    render(<ReviewTab />)
    await waitFor(() => screen.getByText('Blunder'))
    expect(screen.getByText('Brilliant')).toBeTruthy()
    expect(screen.getByText('Aligned')).toBeTruthy()
  })

  it('renders an ungraded lane as an em dash, never as a nought', async () => {
    mock(DATA)
    render(<ReviewTab />)
    const chip = await screen.findByTestId('lane-chip')
    expect(chip.textContent).toContain('—')
    expect(chip.textContent).not.toContain('0.0')
  })

  it('shows the note explaining why a lane was not graded', async () => {
    mock(DATA)
    render(<ReviewTab />)
    const chip = await screen.findByTestId('lane-chip')
    expect(chip.getAttribute('title')).toContain('wildcard')
  })

  it('spells out the hindsight gap in plain words', async () => {
    mock(DATA)
    render(<ReviewTab />)
    expect(await screen.findByTestId('hindsight-2')).toBeTruthy()
    expect(screen.getByTestId('hindsight-2').textContent)
      .toContain('74')
  })

  it('lists the moves flagged and skipped', async () => {
    mock(DATA)
    render(<ReviewTab />)
    // Not a bare findByText(/Guehi/): the same name is in the transfers
    // lane's "model Blank->Guehi", so the match must be the misses line.
    const flagged = await screen.findByText(/Flagged and skipped/)
    // The name is a chip now, so the sentence's own text no longer carries
    // it: the miss reads as a card with the gain beside it.
    expect(flagged.parentElement!.textContent).toContain('Guehi')
    expect(flagged.parentElement!.textContent).toContain('+15 over Blank')
    expect(screen.getByRole('button', { name: /Guehi/ })).toBeInTheDocument()
  })

  it('badges a gameweek that did not reconcile', async () => {
    mock({
      ...DATA,
      gws: [{ ...DATA.gws[0], reconciled: false, official_points: 63 }],
    })
    render(<ReviewTab />)
    expect(await screen.findByText(/did not reconcile/i)).toBeTruthy()
  })

  it('badges advice that was banked after the deadline', async () => {
    mock({ ...DATA, gws: [{ ...DATA.gws[0], post_deadline: true }] })
    render(<ReviewTab />)
    expect(await screen.findByText(/late run/i)).toBeTruthy()
  })

  it('names the projections a gameweek was graded against', async () => {
    mock({
      ...DATA,
      gws: [{ ...DATA.gws[0], projection_snapshot: '20260903T090000Z' }],
    })
    render(<ReviewTab />)
    const line = await screen.findByTestId('review-projections-2')
    expect(line.textContent).toBe('projections 20260903')
    // The visible label is the date; advise runs several times a week, so the
    // hour has to be somewhere and the tooltip is where.
    expect(line.getAttribute('title')).toContain('20260903 09:00 UTC')
    expect(line.getAttribute('title')).toContain('before the deadline')
  })

  it('says a gameweek whose every projection run was late', async () => {
    mock({
      ...DATA,
      gws: [{ ...DATA.gws[0], projection_snapshot: '20260905T090000Z',
              projection_post_deadline: true }],
    })
    render(<ReviewTab />)
    const line = await screen.findByTestId('review-projections-2')
    expect(line.textContent).toContain('(late)')
    // Two causes, and the tooltip must name both. The flag is also set when
    // the run never recorded a deadline, in which case an in-time snapshot
    // may well be the one named — "every run was late" would be a claim the
    // server did not make.
    const title = line.getAttribute('title') ?? ''
    expect(title).toContain('20260905 09:00 UTC')
    expect(title).toContain('written after the deadline')
    expect(title).toContain('did not record when the deadline was')
  })

  it('renders nothing at all when no projections were frozen', async () => {
    // Absent, never an em dash. Every row banked before v12 W5 is in this
    // state for ever, and a dash in the heading would read as a measurement
    // that came back empty rather than one that was never taken.
    mock({ ...DATA, gws: [{ ...DATA.gws[0], projection_snapshot: null }] })
    render(<ReviewTab />)
    // Wait on the card actually rendering before asserting an absence, or the
    // assertion passes against a tab that has not finished fetching yet.
    await screen.findByTestId('hindsight-2')
    expect(screen.queryByTestId('review-projections-2')).toBeNull()
  })

  it('says so when a gameweek has no surviving advice', async () => {
    mock({
      ...DATA,
      gws: [{ ...DATA.gws[0], no_advice: true, accuracy: null,
              model_points: null }],
    })
    render(<ReviewTab />)
    expect(await screen.findByText(/no surviving advice/i)).toBeTruthy()
  })

  it('says so when no legal eleven could be rebuilt', async () => {
    mock({
      ...DATA,
      gws: [{ ...DATA.gws[0],
              hindsight: { points: null, xi: [], captain: null, gap: null } }],
    })
    render(<ReviewTab />)
    const line = await screen.findByTestId('hindsight-2')
    expect(line.textContent).toContain('no hindsight comparison')
  })

  it('names the gameweeks the season totals cover', async () => {
    mock(DATA)
    render(<ReviewTab />)
    expect((await screen.findByText(/Bench points this season/)).textContent)
      .toContain('over 1 GW')
  })

  it('sums each lane over the season', async () => {
    mock(DATA)
    render(<ReviewTab />)
    expect(await screen.findByTestId('season-transfers')).toBeTruthy()
    expect(screen.getByTestId('season-transfers').textContent).toContain('-7')
  })

  it('marks a lane that was never gradeable rather than scoring it 0',
     async () => {
       mock(DATA)
       render(<ReviewTab />)
       const cell = await screen.findByTestId('season-chip')
       expect(cell.textContent).toContain('never graded')
     })

  it('leaves the lane rows as text, because they carry no player code', () => {
    // Not an oversight: ReviewLane.mine/model are comma-joined name strings
    // built server-side out of a set of players whose codes are discarded
    // before the payload is written (plan A6).
    mock(DATA)
    render(<ReviewTab />)
    return waitFor(() => {
      expect(within(screen.getByTestId('lane-captaincy'))
        .queryByRole('button')).toBeNull()
    })
  })

  it('already names the command for its pre-first-review state', async () => {
    // Audited 2026-08-31 and left alone (plan A12).
    mock({ gws: [], summary: null })
    render(<ReviewTab />)
    expect(await screen.findByTestId('empty-state')).toBeInTheDocument()
    expect(screen.getByText('gaffer review')).toBeInTheDocument()
  })
})
