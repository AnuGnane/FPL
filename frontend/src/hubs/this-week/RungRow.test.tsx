import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import type { LadderRung } from '../../types'
import RungRow from './RungRow'

// The ladder's rows, moved beside them in v18f §2.1 out of
// `LadderCard.test.tsx`, which keeps every case about the card around them —
// its selects, its rebuild, its notes. The fixture is that file's ladder, cut
// down to the rungs these cases read.

const ref = (code: number, name: string, ep = 5.0) =>
  ({ code, name, position: 'MID', ep,
     next_fixture: null, team_code: null, team_short: null })

const week = (gw: number, hits: number, buys: ReturnType<typeof ref>[],
              sells: ReturnType<typeof ref>[]) => ({
  gw, hits, buys, sells,
  xi: [ref(1, 'Keeper'), ref(2, 'Back')], bench: [ref(3, 'Sub')],
  captain: ref(2, 'Back'), vice: ref(1, 'Keeper'), expected_pts: 60,
})

const RUNGS: LadderRung[] = [
  { key: 'bank', hits: 0, transfers: 0, cost: 0, same_as: null,
    horizon_hits: 0, horizon_cost: 0, label: 'bank',
    plan_by_gw: [week(3, 0, [], [])], week_pts: 60, horizon_pts: 180,
    objective: 170, mean_pts: 180, p10_pts: 160, p90_pts: 200,
    p_beats_bank: null, p_beats_top: 0.42, p_best: 0.2, vs_below: null },
  { key: 'hits0', hits: 0, transfers: 1, cost: 0, same_as: null,
    horizon_hits: 0, horizon_cost: 0, label: 'free transfers only',
    plan_by_gw: [week(3, 0, [ref(20, 'Star')], [ref(16, 'Dud')])],
    week_pts: 63, horizon_pts: 186, objective: 176, mean_pts: 186,
    p10_pts: 165, p90_pts: 207, p_beats_bank: 0.71, p_beats_top: 0.5,
    p_best: 0.3,
    vs_below: { extra_buys: [ref(20, 'Star')], extra_sells: [ref(16, 'Dud')],
                dropped_buys: [], dropped_sells: [], delta_mean_pts: 6,
                delta_cost: 0, delta_cost_now: 0 } },
  // The caps are per week, so a one-hit plan spends a hit in every horizon
  // week: 4 now, 12 over the three.
  { key: 'hits1', hits: 1, transfers: 2, cost: 4, same_as: null,
    horizon_hits: 3, horizon_cost: 12, label: '1 hit',
    plan_by_gw: [week(3, 1, [ref(20, 'Star'), ref(19, 'Second')],
                      [ref(16, 'Dud'), ref(17, 'Filler')])],
    week_pts: 64, horizon_pts: 188, objective: 177, mean_pts: 188,
    p10_pts: 166, p90_pts: 210, p_beats_bank: 0.74, p_beats_top: null,
    p_best: 0.5,
    vs_below: { extra_buys: [ref(19, 'Second')],
                extra_sells: [ref(17, 'Filler')], dropped_buys: [],
                dropped_sells: [], delta_mean_pts: 1.9, delta_cost: 12,
                delta_cost_now: 4 } },
  { key: 'hits2', hits: 1, transfers: 2, cost: 4, same_as: 'hits1',
    horizon_hits: 3, horizon_cost: 12, label: '2 hits',
    plan_by_gw: [], week_pts: null, horizon_pts: null, objective: null,
    mean_pts: null, p10_pts: null, p90_pts: null, p_beats_bank: null,
    p_beats_top: null, p_best: null, vs_below: null },
  { key: 'hits3', hits: 1, transfers: 2, cost: 4, same_as: 'hits1',
    horizon_hits: 3, horizon_cost: 12, label: '3 hits',
    plan_by_gw: [], week_pts: null, horizon_pts: null, objective: null,
    mean_pts: null, p10_pts: null, p90_pts: null, p_beats_bank: null,
    p_beats_top: null, p_best: null, vs_below: null },
]

/** The card's own loop, with the payload's cap, recommendation and choice —
 *  the rows are read together, so they are drawn together. */
function Ladder({ rungs = RUNGS }: { rungs?: LadderRung[] }) {
  const [open, setOpen] = useState<string | null>(null)
  const bank = rungs.find((r) => r.key === 'bank')
  const capIndex = rungs.findIndex((r) => r.key === 'hits2')
  return (
    <table>
      <tbody>
        {rungs.map((r, i) => (
          <RungRow
            key={r.key}
            rung={r}
            bank={bank}
            below={rungs.find((x) => x.key === r.same_as)}
            weeks={3}
            open={open === r.key}
            onToggle={() => setOpen(open === r.key ? null : r.key)}
            isCap={r.key === 'hits2'}
            beyond={capIndex >= 0 && i > capIndex}
            recommended={r.key === 'hits1'}
            chosen={r.key === 'hits0'}
          />
        ))}
      </tbody>
    </table>
  )
}

describe('the rung row', () => {
  it('lists one row per rung with the moves, the cost and the odds', () => {
    render(<Ladder />)
    const row = screen.getByText('1 hit').closest('tr')!
    expect(row).toHaveTextContent('Star, Second')
    expect(row).toHaveTextContent('−4')
    expect(row).toHaveTextContent('74%')     // P(beats bank)
    expect(row).toHaveTextContent('50%')     // P(best)
    expect(screen.getByText('bank', { selector: 'button' }).closest('tr')).toHaveTextContent('—')
  })

  it('highlights the cap rung and mutes the rungs beyond it', () => {
    render(<Ladder />)
    const cap = screen.getByText('2 hits').closest('tr')!
    expect(cap).toHaveAttribute('data-cap', 'true')
    const beyond = screen.getByText('3 hits').closest('tr')!
    expect(beyond).toHaveClass('text-text-faint')
    expect(beyond).toHaveAttribute('title', 'beyond your cap')
    expect(cap).not.toHaveClass('text-text-faint')
  })

  it('tints the cap rung accent and draws the odds as bars with the percent beside', () => {
    render(<Ladder />)
    const cap = screen.getByText('2 hits').closest('tr')!
    expect(cap).toHaveClass('bg-accent-tint')
    const rec = screen.getByText('1 hit').closest('tr')!
    expect(within(rec).getByTestId('p-beats-bank-fill')).toHaveStyle({ width: '74%' })
    expect(within(rec).getByTestId('p-best-fill')).toHaveStyle({ width: '50%' })
    expect(rec).toHaveTextContent('74%')
  })

  it('prints the horizon cost in down ink beside the cost now', () => {
    render(<Ladder />)
    const row = screen.getByText('1 hit').closest('tr')!
    const horizon = within(row).getByText(/over \d+ GWs?/)
    expect(horizon).toHaveClass('text-down')
  })

  it('marks the recommended rung and says when a rung repeats the one below', () => {
    render(<Ladder />)
    const rec = screen.getByText('1 hit').closest('tr')!
    expect(within(rec).getByText('recommended')).toBeInTheDocument()
    expect(screen.getByText('2 hits').closest('tr'))
      .toHaveTextContent(/solver would not spend it — same as 1 hit/)
  })

  it('expands a rung to show what the last hit bought', async () => {
    render(<Ladder />)
    await userEvent.click(screen.getByText('1 hit'))
    expect(screen.getByText(/\+ Second for Filler/)).toBeInTheDocument()
    // The delta is net of the *horizon* hit bill; the first week's share is
    // spelled out beside it.
    expect(screen.getByText(/\+1.9 xPts over 3 GWs, −12/))
      .toBeInTheDocument()
    expect(screen.getByText(/−4 of it now/)).toBeInTheDocument()
    expect(screen.getByText('Back')).toBeInTheDocument()   // the XI
  })

  it('prints the first week’s hit cost and the horizon cost when they differ',
     () => {
       render(<Ladder />)
       const row = screen.getByText('1 hit').closest('tr')!
       expect(row).toHaveTextContent('−4 now · −12 over 3 GWs')
       // A rung that spends the same either way says it once.
       expect(screen.getByText('bank', { selector: 'button' }).closest('tr')).toHaveTextContent('0')
     })

  it('prints a single cost when the horizon bill equals the first week’s',
     () => {
       render(<Ladder rungs={RUNGS.map((r) => (r.key === 'hits1'
         ? { ...r, horizon_hits: 1, horizon_cost: 4 } : r))} />)
       const row = screen.getByText('1 hit').closest('tr')!
       expect(row).toHaveTextContent('−4')
       expect(row).not.toHaveTextContent('over 3 GWs')
     })

  it('opens a rung from the keyboard, which the row alone could not', () => {
    // v18f §2.2. The label is a button so Tab reaches it and Enter works it;
    // the row keeps its own click, so the mouse is unchanged.
    render(<Ladder />)
    const label = screen.getByText('1 hit', { selector: 'button' })
    expect(label).toHaveAttribute('aria-expanded', 'false')
    label.focus()
    expect(label).toHaveFocus()
    fireEvent.keyDown(label, { key: 'Enter', code: 'Enter' })
    fireEvent.click(label)
    expect(screen.getByText(/\+ Second for Filler/)).toBeInTheDocument()
    expect(screen.getByText('1 hit', { selector: 'button' }))
      .toHaveAttribute('aria-expanded', 'true')
  })

  it('closes an open rung when it is clicked again', () => {
    // The row is the toggle, so the second click is what puts the panel away
    // — and the card holds one open rung at a time.
    const { container } = render(<Ladder />)
    const row = screen.getByText('1 hit').closest('tr')!
    fireEvent.click(row)
    expect(screen.getByText(/\+ Second for Filler/)).toBeInTheDocument()
    fireEvent.click(row)
    expect(screen.queryByText(/\+ Second for Filler/)).toBeNull()
    expect(container.querySelectorAll('tr')).toHaveLength(RUNGS.length)
  })
})
