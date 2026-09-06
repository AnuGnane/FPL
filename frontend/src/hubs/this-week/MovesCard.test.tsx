import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import MovesCard from './MovesCard'

const BUYS = [{ code: 1, name: 'Wirtz', ep: 6.1, frequency: 0.82, tag: 'attack' }]
const SELLS = [{ code: 2, name: 'Isak', ep: 3.2, frequency: 0.79 }]

describe('MovesCard', () => {
  it('lists buys as IN and sells as OUT with their sim percentages', () => {
    render(<MovesCard buys={BUYS} sells={SELLS} hits={0} />)
    expect(screen.getByText('Wirtz').closest('tr')).toHaveTextContent('IN')
    expect(screen.getByText('Isak').closest('tr')).toHaveTextContent('OUT')
    expect(screen.getByText('82%')).toBeInTheDocument()
  })

  it('marks IN as an up chip and OUT as a down chip, with sims as a bar', () => {
    render(<MovesCard buys={BUYS} sells={SELLS} hits={0} />)
    expect(screen.getByText('IN')).toHaveAttribute('data-tone', 'up')
    expect(screen.getByText('OUT')).toHaveAttribute('data-tone', 'down')
    expect(screen.getAllByTestId('sims-fill')[0]).toHaveStyle({ width: '82%' })
  })

  it('prices hits explicitly', () => {
    render(<MovesCard buys={BUYS} sells={SELLS} hits={2} />)
    expect(screen.getByText('\u22128 pts')).toBeInTheDocument()
  })

  it('says to bank the transfer when there are no moves', () => {
    render(<MovesCard buys={[]} sells={[]} hits={0} />)
    expect(screen.getByText(/bank the free transfer/i)).toBeInTheDocument()
  })

  it('renders an em dash for a move with no simulation frequency', () => {
    render(<MovesCard buys={[{ code: 3, name: 'Rice', ep: 5.0 }]} sells={[]}
                      hits={0} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('prints the free-transfer and cap line above the moves when given one', () => {
    render(<MovesCard buys={BUYS} sells={SELLS} hits={0}
                      capLine="1 free transfer · cap 2 hits" />)
    expect(screen.getByTestId('moves-cap-line'))
      .toHaveTextContent('1 free transfer · cap 2 hits')
  })

  it('prints no cap line without one', () => {
    render(<MovesCard buys={[]} sells={[]} hits={0} />)
    expect(screen.queryByTestId('moves-cap-line')).not.toBeInTheDocument()
    expect(screen.getByText(/bank the free transfer/i)).toBeInTheDocument()
  })

  it('prints the restraint line and, when they differ, what the objective wanted', () => {
    render(<MovesCard buys={[]} sells={[]} hits={0}
      restraint={{ chosen: 'hits0', bar: 0.6, agrees: false, note: null,
        steps: [{ below: 'bank', above: 'hits0', share: 0.79, taken: true,
                  reason: 'expected points alone', reason_kind: 'points' },
                { below: 'hits0', above: 'hits1', share: 0.46, taken: false,
                  reason: 'Rice is 0% to play', reason_kind: 'flagged' }] }}
      objective={{ buys: [{ code: 5, name: 'Isak', ep: 6 }], sells: [{ code: 6, name: 'Rice', ep: 2 }],
                   hits: 1, expected_pts: 63 }} />)
    expect(screen.getByTestId('moves-restraint-line')).toHaveTextContent(
      'Free transfers only — the step to 1 hit was refused at 46%: Rice is 0% to play')
    expect(screen.getByTestId('moves-objective-line')).toHaveTextContent(
      'The objective wanted Isak in, Rice out, 1 hit')
  })

  it('prints neither line on a payload without the walk', () => {
    render(<MovesCard buys={[]} sells={[]} hits={0} />)
    expect(screen.queryByTestId('moves-restraint-line')).toBeNull()
  })
})
