import { fireEvent, render, screen } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { describe, expect, it } from 'vitest'
import PlayerCard, { PLAIN_SHIRT } from './PlayerCard'
import type { NextFixture } from '../types'

const FIXTURE: NextFixture = {
  opponent_short: 'MUN', home: true,
  kickoff_utc: '2026-09-12T14:00:00Z', difficulty: 0.31,
}

function card(over: Partial<ComponentProps<typeof PlayerCard>> = {}) {
  return render(
    <PlayerCard
      code={11} name="Saka" position="MID" teamShort="ARS" teamCode={3}
      ep={5.1} fixture={FIXTURE} {...over}
    />,
  )
}

describe('PlayerCard', () => {
  it('draws the shirt through the backend, never the CDN', () => {
    // D1: every byte on the page arrives via /api/*. A hotlinked shirt would
    // also be the one request that leaks the reader's IP to a third party.
    card()
    expect(screen.getByRole('img', { name: /ARS/ }))
      .toHaveAttribute('src', '/api/assets/shirt/3')
  })

  it('asks for the keeper variant for a goalkeeper', () => {
    card({ position: 'GKP' })
    expect(screen.getByRole('img', { name: /ARS/ }))
      .toHaveAttribute('src', '/api/assets/shirt/3?keeper=true')
  })

  it('draws a plain shirt for a player with no team code', () => {
    // A6: nulls, never a sentinel. Shirt 0 is not a request worth making —
    // the endpoint allowlists the banked bootstrap, so it is a 404 by design
    // — and the card draws the bundled plain shirt itself instead.
    card({ teamCode: null, teamShort: null })
    const shirt = screen.getByRole('img', { name: /shirt/i })
    expect(shirt).toHaveAttribute('src', PLAIN_SHIRT)
    expect(shirt.getAttribute('src')).not.toContain('/api/assets/')
    expect(shirt.getAttribute('src')).not.toContain('undefined')
  })

  it('leaves that plain shirt visible rather than drawing a gap', () => {
    // The blocker this test exists for: a hidden image is a hole in the
    // formation row, and a hole reads as a bug where a plain shirt reads as
    // "we do not know his club".
    card({ teamCode: null, teamShort: null })
    const shirt = screen.getByRole('img', { name: /shirt/i })
    expect(shirt).toBeVisible()
    expect(shirt.style.visibility).not.toBe('hidden')
  })

  it('swaps a failed request to the plain shirt instead of hiding it', () => {
    // A live 404 or a dead network must degrade to the same picture, with no
    // broken-image icon on the pitch (gate G1 checks for none).
    card()
    const shirt = screen.getByRole('img', { name: /ARS/ })
    fireEvent.error(shirt)
    expect(shirt).toHaveAttribute('src', PLAIN_SHIRT)
    expect(shirt).toBeVisible()
    expect(shirt.style.visibility).not.toBe('hidden')
  })

  it('names the player, his club and his expected points', () => {
    card()
    expect(screen.getByText('Saka')).toBeInTheDocument()
    expect(screen.getByText('ARS')).toBeInTheDocument()
    expect(screen.getByText('5.1')).toBeInTheDocument()
  })

  it('draws the fixture chip with the opponent, the side and the kickoff',
     () => {
    card()
    const chip = screen.getByTestId('fixture-chip')
    expect(chip).toHaveTextContent('MUN (H)')
    expect(chip.textContent).toMatch(/\d/)   // some rendered kickoff
  })

  it('says Blank rather than drawing an empty chip', () => {
    // D2: honest, not zeroed.
    card({ fixture: null })
    expect(screen.getByTestId('fixture-chip')).toHaveTextContent('Blank')
  })

  it('renders a fixture whose kickoff is still TBC', () => {
    card({ fixture: { ...FIXTURE, kickoff_utc: null } })
    const chip = screen.getByTestId('fixture-chip')
    expect(chip).toHaveTextContent('MUN (H)')
    expect(chip).toHaveTextContent('TBC')
  })

  it('tints the chip by difficulty and leaves an unrated one neutral', () => {
    const { rerender } = card()
    const tinted = screen.getByTestId('fixture-chip').style.backgroundColor
    rerender(
      <PlayerCard code={11} name="Saka" position="MID" teamShort="ARS"
                  teamCode={3} ep={5.1}
                  fixture={{ ...FIXTURE, difficulty: null }} />,
    )
    expect(screen.getByTestId('fixture-chip').style.backgroundColor)
      .not.toBe(tinted)
  })

  it('wears the captain armband', () => {
    card({ armband: 'C' })
    expect(screen.getByTitle('Captain')).toHaveTextContent('C')
    expect(screen.queryByTitle('Vice-captain')).not.toBeInTheDocument()
  })

  it('wears the vice armband', () => {
    card({ armband: 'V' })
    expect(screen.getByTitle('Vice-captain')).toHaveTextContent('V')
  })

  it('carries a news flag with the chance of playing', () => {
    card({ news: 'Knock — 75% chance of playing', chanceOfPlaying: 75 })
    expect(screen.getByText('75%')).toBeInTheDocument()
  })

  it('flags news with no percentage as News', () => {
    card({ news: 'Suspended', chanceOfPlaying: null })
    expect(screen.getByText('News')).toBeInTheDocument()
  })

  it('is a button only when something is listening', () => {
    const { rerender } = card()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    rerender(
      <PlayerCard code={11} name="Saka" position="MID" teamShort="ARS"
                  teamCode={3} ep={5.1} fixture={FIXTURE}
                  onSelect={() => {}} />,
    )
    expect(screen.getByRole('button')).toBeInTheDocument()
  })

  it('renders the chip size without the fixture furniture', () => {
    // D4: the compact form v9b puts in a Live row or a league compare.
    card({ size: 'chip' })
    expect(screen.getByText('Saka')).toBeInTheDocument()
    expect(screen.queryByTestId('fixture-chip')).not.toBeInTheDocument()
  })

  it('still names the player when everything optional is missing', () => {
    render(<PlayerCard code={99} name="Nobody" position="" teamShort={null}
                       teamCode={null} ep={0} fixture={null} />)
    expect(screen.getByText('Nobody')).toBeInTheDocument()
  })
})
