import { fireEvent, render, screen } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { describe, expect, it } from 'vitest'
import PlayerCard, { PLAIN_SHIRT, lensBackground } from './PlayerCard'
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

/** The card's own frame — the element the tile classes and the lens tint
 *  land on, whether it rendered as a div or as a button. */
const frame = () => document.querySelector('[data-code="11"]') as HTMLElement

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

  it('draws the fixture chip with the opponent and the side, the kickoff '
     + 'in its title', () => {
    card()
    const chip = screen.getByTestId('fixture-chip')
    expect(chip).toHaveTextContent('MUN (H)')
    // R3: the tile is not where a captain is chosen, so the kickoff moved
    // out of the chip's face and into what it says on hover.
    expect(chip).toHaveAttribute('title', expect.stringMatching(/\d/))
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
    expect(chip).toHaveAttribute('title', expect.stringContaining('TBC'))
  })

  it('speaks difficulty in the tint language, not a colour ramp', () => {
    // Rule 1: easy and hard are directions. An unrated fixture is grey
    // rather than the midpoint of a ramp, which would read as "average" —
    // a claim the ticker did not make.
    card()
    expect(screen.getByTestId('fixture-chip'))
      .toHaveAttribute('data-tone', 'up')
    card({ fixture: { ...FIXTURE, difficulty: 0.9 } })
    expect(screen.getAllByTestId('fixture-chip')[1])
      .toHaveAttribute('data-tone', 'down')
    card({ fixture: { ...FIXTURE, difficulty: null } })
    expect(screen.getAllByTestId('fixture-chip')[2])
      .toHaveAttribute('data-tone', 'neutral')
  })

  it('is a 92px tile with a 26px shirt at pitch size', () => {
    card()
    expect(frame().className).toContain('w-[92px]')
    expect(screen.getByRole('img')).toHaveAttribute('width', '26')
  })

  it('tags the captain after the name as a square C, the vice as a grey V',
     () => {
    card({ armband: 'C' })
    expect(screen.getByTitle('Captain')).toHaveTextContent('C')
    expect(screen.getByTitle('Captain').className).not.toContain('rounded-full')
    card({ armband: 'V' })
    expect(screen.getByTitle('Vice-captain')).toHaveTextContent('V')
  })

  it('flags doubt in amber (rule 2)', () => {
    card({ news: 'Knock', chanceOfPlaying: 75 })
    expect(screen.getByText('75%')).toHaveAttribute('data-tone', 'warn')
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

  it('lays the chip out along the row, not down it', () => {
    const { container } = render(
      <PlayerCard size="chip" code={1} name="Raya" position="GKP"
                  teamShort={null} teamCode={null} ep={4.2} />)
    const card = container.querySelector('[data-code="1"]')!
    // A 76px vertical stack is right on grass and wrong in the first cell of
    // an eight-column table, where it triples the row height (plan A2).
    expect(card.className).toContain('inline-flex')
    expect(card.className).not.toContain('flex-col items-center')
    // The fixture chip is a pitch affordance: a table row has no space for
    // "MCI (H) Sat 15:00" and the reader is not choosing a captain here.
    expect(screen.queryByTestId('fixture-chip')).not.toBeInTheDocument()
  })

  it('prints an em dash, not a zero, for a player with no expected points', () => {
    // Live has `remaining_ep: null` for a player whose match is over, and
    // ReviewMiss has no EP at all. A confident 0.0 under a name is a lie
    // (plan A3).
    render(<PlayerCard size="chip" code={2} name="Salah" position="MID"
                       teamShort={null} teamCode={null} ep={null} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('still draws the pitch card exactly as it did', () => {
    render(<PlayerCard code={3} name="Haaland" position="FWD"
                       teamShort="MCI" teamCode={43} ep={7.1} fixture={null} />)
    // The pitch is v9a's and this cycle does not touch it: the fixture chip
    // is present and "Blank" is still the word for no fixture.
    expect(screen.getByTestId('fixture-chip')).toHaveTextContent('Blank')
  })
})

describe('PlayerCard: the EO lens (v14)', () => {
  it('draws no inline background without a lens ownership', () => {
    // The assertion that keeps the prop genuinely optional: every existing
    // caller renders the default frame, unchanged.
    card()
    expect(frame().style.backgroundColor).toBe('')
  })

  it('tints the tile background by lens ownership', () => {
    card({ lensEo: 80 })
    expect(frame().style.backgroundColor).not.toBe('')
  })

  it('mixes more of the text colour in the more he is owned', () => {
    expect(lensBackground(80)).not.toBe(lensBackground(10))
    expect(lensBackground(80)).toContain('var(--color-text)')
  })

  it('names the field class in the title, never as a colour', () => {
    card({ lensEo: 45.7, fieldClass: 'shield' })
    expect(frame()).toHaveAttribute('title', expect.stringContaining('shield'))
  })
})
