import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { currentToasts } from '../../kit'
import MovesCard, { movesText } from './MovesCard'
import type { AdviceDiff } from '../../types'

/** A clipboard, or the absence of one: `navigator.clipboard` is undefined
 *  over plain http on some phones, which is the whole reason the fallback
 *  exists (v19d §2.4). */
function clipboard(writeText: ((t: string) => Promise<void>) | null) {
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: writeText === null ? undefined : { writeText },
  })
}

afterEach(() => { clipboard(null) })

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
    render(<MovesCard buys={BUYS} sells={SELLS} hits={2}
      restraint={{ chosen: 'hits1', bar: 0.6, agrees: true, note: null,
                   steps: [], hit_cost: 4, label: null, line: null }} />)
    expect(screen.getByText('\u22128 pts')).toBeInTheDocument()
  })

  it('prints the count alone when no cost is served', () => {
    render(<MovesCard buys={BUYS} sells={SELLS} hits={2} />)
    expect(screen.getByText(/2 hits/)).toBeInTheDocument()
    expect(screen.queryByText(/pts/)).toBeNull()
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

  // v19b §2.2. The pins line closes the Friday loop on the page the loop ends
  // on: pin, re-run, apply. Three states, because a stored pin that `[news]
  // overrides` is not applying would otherwise be reported as one waiting for
  // a solve, and the re-run it asks for would change nothing.
  it('says how many pins are waiting for the next solve', () => {
    render(<MovesCard buys={BUYS} sells={SELLS} hits={0}
                      pins={{ active: true, warning: null, rows: [
                        { code: 1 }, { code: 2 }] as never }} />)
    expect(screen.getByTestId('moves-pins-line'))
      .toHaveTextContent('2 pins live · re-run to apply')
  })

  it('counts one pin in the singular', () => {
    render(<MovesCard buys={BUYS} sells={SELLS} hits={0}
                      pins={{ active: true, warning: null,
                              rows: [{ code: 1 }] as never }} />)
    expect(screen.getByTestId('moves-pins-line'))
      .toHaveTextContent('1 pin live · re-run to apply')
  })

  it('names the setting when the pins are stored but not applied', () => {
    render(<MovesCard buys={BUYS} sells={SELLS} hits={0}
                      pins={{ active: false, warning: null, rows: [
                        { code: 1 }, { code: 2 }] as never }} />)
    expect(screen.getByTestId('moves-pins-line'))
      .toHaveTextContent('2 pins stored, not applied ([news] overrides is off)')
  })

  it('says nothing about pins when the manager has taken none', () => {
    render(<MovesCard buys={BUYS} sells={SELLS} hits={0}
                      pins={{ active: true, warning: null, rows: [] }} />)
    expect(screen.queryByTestId('moves-pins-line')).not.toBeInTheDocument()
  })

  it('says nothing about pins when the panel has not loaded', () => {
    render(<MovesCard buys={BUYS} sells={SELLS} hits={0} pins={null} />)
    expect(screen.queryByTestId('moves-pins-line')).not.toBeInTheDocument()
  })

  it('prints no cap line without one', () => {
    render(<MovesCard buys={[]} sells={[]} hits={0} />)
    expect(screen.queryByTestId('moves-cap-line')).not.toBeInTheDocument()
    expect(screen.getByText(/bank the free transfer/i)).toBeInTheDocument()
  })

  it('prints the restraint line and, when they differ, what the objective wanted', () => {
    render(<MovesCard buys={[]} sells={[]} hits={0}
      restraint={{ chosen: 'hits0', bar: 0.6, agrees: false, note: null,
        label: 'free transfers only', hit_cost: 4,
        line: 'restraint: free transfers only; the step to 1 hit was refused, '
          + '46% — Rice is 0% to play',
        steps: [{ below: 'bank', above: 'hits0', share: 0.79, taken: true,
                  reason: 'expected points alone', reason_kind: 'points',
                  line: 'bank → free transfers only: taken, 79% — expected points alone' },
                { below: 'hits0', above: 'hits1', share: 0.46, taken: false,
                  reason: 'Rice is 0% to play', reason_kind: 'flagged',
                  line: 'free transfers only → 1 hit: refused, 46% — Rice is 0% to play' }] }}
      objective={{ buys: [{ code: 5, name: 'Isak', ep: 6, position: 'FWD', price: 8.5 }],
                   sells: [{ code: 6, name: 'Rice', ep: 2, position: 'MID', price: 6.5 }],
                   hits: 1, expected_pts: 63, week: null,
                   line: 'the objective wanted: Isak in; Rice out; 1 hit' }} />)
    expect(screen.getByTestId('moves-restraint-line')).toHaveTextContent(
      'restraint: free transfers only; the step to 1 hit was refused, 46% — Rice is 0% to play')
    expect(screen.getByTestId('moves-objective-line')).toHaveTextContent(
      'the objective wanted: Isak in; Rice out; 1 hit')
  })

  it('prints neither line on a payload without the walk', () => {
    render(<MovesCard buys={[]} sells={[]} hits={0} />)
    expect(screen.queryByTestId('moves-restraint-line')).toBeNull()
  })

  // --- v19d §2.4: something to take away -----------------------------------

  it('writes the moves as one out, one in, then the hits and the captain', () => {
    expect(movesText(BUYS, SELLS, 1, 'Haaland'))
      .toBe('OUT Isak → IN Wirtz\n1 hit · captain Haaland')
  })

  it('gives an unpaired move a line of its own rather than a partner', () => {
    expect(movesText(BUYS, [], 0, 'Haaland'))
      .toBe('IN Wirtz\ncaptain Haaland')
  })

  it('copies the moves to the clipboard and says so', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    clipboard(writeText)
    render(<MovesCard buys={BUYS} sells={SELLS} hits={1} captain="Haaland" />)
    await userEvent.click(screen.getByRole('button', { name: 'Copy' }))
    expect(writeText).toHaveBeenCalledWith(
      'OUT Isak → IN Wirtz\n1 hit · captain Haaland')
    await waitFor(() => expect(currentToasts()[0]?.text).toBe('Moves copied'))
  })

  it('shows the text to copy by hand when the browser has no clipboard',
    async () => {
      // Plain http on a LAN: the API is simply not there, and a button that
      // silently does nothing is worse than no button.
      clipboard(null)
      render(<MovesCard buys={BUYS} sells={SELLS} hits={1} captain="Haaland" />)
      expect(screen.queryByTestId('moves-text')).toBeNull()
      await userEvent.click(screen.getByRole('button', { name: 'Copy' }))
      expect(screen.getByTestId('moves-text'))
        .toHaveTextContent('OUT Isak → IN Wirtz')
    })

  it('links to the rendered report for the gameweek it is showing', () => {
    render(<MovesCard buys={BUYS} sells={SELLS} hits={0} gw={5} />)
    expect(screen.getByRole('link', { name: 'Open the GW5 report' }))
      .toHaveAttribute('href', '/reports/gw5-report.html')
  })

  it('offers no report link on a card that was given no gameweek', () => {
    render(<MovesCard buys={BUYS} sells={SELLS} hits={0} />)
    expect(screen.queryByRole('link')).toBeNull()
  })
})

/** Last week's served plan against this week's, as the card is handed it. */
function diff(): AdviceDiff {
  return {
    gw: 5, gw_from: 4, gw_to: 5, available: true, changed: true,
    current_at: null, previous_at: null,
    buys_added: [{ code: 9, name: 'Bruno Fernandes' }],
    buys_dropped: [{ code: 8, name: 'Palmer' }],
    sells_added: [], sells_dropped: [],
    captain_from: { code: 1, name: 'Salah' },
    captain_to: { code: 1, name: 'Salah' },
    chip_from: null, chip_to: null, expected_pts_delta: 1.4,
    ep_movers: [], ep_movers_count: null,
  } as AdviceDiff
}

describe('the since line (v19e §2.3)', () => {
  it('names the week, the armband, the swap and the points', () => {
    render(<MovesCard buys={BUYS} sells={SELLS} hits={0}
                      since={diff()} />)
    expect(screen.getByTestId('moves-since')).toHaveTextContent(
      'since GW4: captain unchanged · 1 buy swapped '
      + '(Palmer → Bruno Fernandes) · +1.4 pts')
  })

  it('names both captains when the armband moved', () => {
    render(<MovesCard buys={BUYS} sells={SELLS} hits={0}
                      since={{ ...diff(),
                               captain_to: { code: 2, name: 'Haaland' } }} />)
    expect(screen.getByTestId('moves-since'))
      .toHaveTextContent('captain Salah → Haaland')
  })

  it('drops the swap clause when the buys are the same players', () => {
    render(<MovesCard buys={BUYS} sells={SELLS} hits={0}
                      since={{ ...diff(), buys_added: [],
                               buys_dropped: [],
                               expected_pts_delta: -0.6 }} />)
    expect(screen.getByTestId('moves-since'))
      .toHaveTextContent('since GW4: captain unchanged · -0.6 pts')
  })

  it('says nothing at all when there is no plan for the week before', () => {
    render(<MovesCard buys={BUYS} sells={SELLS} hits={0}
                      since={{ ...diff(), available: false }} />)
    expect(screen.queryByTestId('moves-since')).toBeNull()
  })

  it('says nothing on a card that was handed no comparison', () => {
    render(<MovesCard buys={BUYS} sells={SELLS} hits={0} />)
    expect(screen.queryByTestId('moves-since')).toBeNull()
  })
})
