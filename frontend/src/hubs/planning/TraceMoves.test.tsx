import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { PlanMoveTrace } from '../../types'
import TraceMoves from './TraceMoves'

// v12 W5 §6.5 — "Why this move". Accounting over the objective's own terms at
// the plan the solver returned; the board still never solves. Moved beside
// the rows in v18f §2.1, out of `PlannerBoard.test.tsx`, which keeps every
// case about the disclosure that holds them.

const MOVE: PlanMoveTrace = {
  buy_code: 1, buy_name: 'Wirtz', sell_code: 2, sell_name: 'Isak',
  ep_gain: 3.5, lambda_tilt: 0.0, note: '',
}

describe('the move trace', () => {
  it('renders the pair and its signed gain', () => {
    render(<TraceMoves moves={[MOVE]} gw={5} />)
    const move = screen.getByTestId('board-why-move-5-1')
    expect(move).toHaveTextContent('Isak → Wirtz')
    // Signed, because the sign is the whole claim: fmtDelta prints '+3.5'.
    expect(move).toHaveTextContent('+3.5')
  })

  it('renders an em dash and the note for a gain it could not price', () => {
    // Never a zero. "We could not price this" and "this swap is worth
    // nothing" are different facts and must not print the same.
    render(<TraceMoves gw={5} moves={[{ ...MOVE, ep_gain: null,
      note: 'player 2 is not in the pool the solver used' }]} />)
    const move = screen.getByTestId('board-why-move-5-1')
    expect(move).toHaveTextContent('—')
    expect(move).not.toHaveTextContent('0.0')
    expect(move).toHaveTextContent('not in the pool')
  })

  it('draws the objective’s own rows without a week’s id or note', () => {
    // v16 §4's panel is the second caller, and it is deliberately barer: the
    // per-move test id names a week it has none of, and the note belongs to
    // the disclosure the board draws under that week.
    const { container } = render(
      <TraceMoves moves={[{ ...MOVE, note: 'priced off a stale pool' }]} />)
    expect(screen.getByText('Isak → Wirtz')).toBeInTheDocument()
    expect(screen.queryByText('priced off a stale pool')).toBeNull()
    expect(container.querySelector('[data-testid]')).toBeNull()
  })
})
