import { render } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'
import Th from './Th'
import { thClass } from './table'

/** Its own container each time, so a test may render two and compare them. */
function head(node: ReactNode): HTMLTableCellElement {
  const { container } = render(
    <table><thead><tr>{node}</tr></thead></table>)
  const th = container.querySelector('th')
  if (th === null) throw new Error('no header rendered')
  return th
}

describe('Th', () => {
  it('is a column header, which is the whole point of it', () => {
    expect(head(<Th>Team</Th>)).toHaveAttribute('scope', 'col')
  })

  it('draws exactly the class the hand-written headers drew', () => {
    // Byte-for-byte `thClass`, so a table that swaps a `<th>` for this one
    // renders the same pixels (v18f gate, part 1).
    expect(head(<Th numeric>xPts</Th>).className).toBe(thClass(true))
    expect(head(<Th>Team</Th>).className).toBe(thClass(false))
  })

  it('appends an extra class after the shared one, in that order', () => {
    expect(head(<Th className="w-8" />).className).toBe(`${thClass()} w-8`)
  })

  it('says which way a sorted column points, and stays quiet otherwise', () => {
    expect(head(<Th sort="descending">Total</Th>))
      .toHaveAttribute('aria-sort', 'descending')
    expect(head(<Th>Total</Th>)).not.toHaveAttribute('aria-sort')
  })
})
