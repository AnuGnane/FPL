import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ContextStrip from './ContextStrip'

const PROPS = {
  gw: 5,
  deadline: '2099-09-18T17:30:00Z',
  captain: 'Haaland',
  moves: 1,
  pts: 58.2,
}

describe('ContextStrip (v19d §2.1)', () => {
  it('names the gameweek, the captain and how many moves there are', () => {
    render(<ContextStrip {...PROPS} />)
    const strip = screen.getByTestId('context-strip')
    expect(strip).toHaveTextContent('GW5')
    expect(strip).toHaveTextContent('captain Haaland')
    expect(strip).toHaveTextContent('1 move')
    expect(strip).toHaveTextContent('58.2 pts')
  })

  it('counts more than one move in the plural', () => {
    render(<ContextStrip {...PROPS} moves={2} />)
    expect(screen.getByTestId('context-strip')).toHaveTextContent('2 moves')
  })

  it('prints the countdown without the deadline stamp the header carries', () => {
    render(<ContextStrip {...PROPS} />)
    // The short form: the page already prints the absolute instant once, in
    // the header, and twice is the same appointment in two voices.
    expect(screen.getByTestId('countdown-short').textContent)
      .not.toMatch(/deadline/)
  })

  it('offers one anchor per section of the page, in the page’s own order', () => {
    render(<ContextStrip {...PROPS} />)
    const hrefs = screen.getAllByRole('link').map((a) => a.getAttribute('href'))
    expect(hrefs).toEqual(['#squad', '#moves', '#ladder', '#brief', '#why',
      '#news'])
  })

  it('sticks to the top of the page rather than scrolling away with it', () => {
    render(<ContextStrip {...PROPS} />)
    expect(screen.getByTestId('context-strip').className)
      .toMatch(/sticky top-0/)
  })
})
