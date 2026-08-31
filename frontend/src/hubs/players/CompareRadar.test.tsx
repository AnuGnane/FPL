import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import CompareRadar, { AXES, axisValues, normalize } from './CompareRadar'
import type { ComponentsBreakdown, FixtureMatrixData, PlayerRow } from
  '../../types'

// Recharts measures its container, which jsdom reports as 0x0 — and reaches
// for a ResizeObserver jsdom does not have. Stub it to a fixed box, the same
// way every other chart test in this hub does.
vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts')
  const { cloneElement, isValidElement } = await import('react')
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div style={{ width: 400, height: 300 }}>
        {isValidElement(children)
          ? cloneElement(children as React.ReactElement<Record<string, unknown>>,
                         { width: 400, height: 300 })
          : children}
      </div>
    ),
  }
})

function player(over: Partial<PlayerRow>): PlayerRow {
  return {
    code: 1, element: 1, name: 'A', position: 'MID', team_code: 3,
    team_name: 'Arsenal', price: 10, ep_next: 5, ep_horizon: 10,
    ownership: 10, league_eo: 10, field_eo: null, field_class: null,
    available: true, status: 'a', news: '', chance_of_playing: null,
    penalties_order: null, free_kicks_order: null, corners_order: null,
    in_squad: false, last4: [], ep_lo: null, ep_hi: null, p_haul: null,
    p_blank: null, ...over,
  }
}

const COMPONENTS: ComponentsBreakdown = {
  gw: 5,
  players: [{
    code: 1, name: 'A', position: 'MID', team_name: 'Arsenal', ep: 5,
    ep_gw: 5, sigma: 1, ep_lo: 4, ep_hi: 6, p_haul: 0.1, p_blank: 0.2,
    fixtures: [{ gw: 5, opponent: 'City', home: true, kickoff_time: null,
                 components: [{ label: 'Goals', points: 2 },
                              { label: 'Assists', points: 1 },
                              { label: 'Minutes', points: 2 }],
                 pen_taker: null, minutes: { p_play: 0.9, p60: 0.8 },
                 ep: 5 }],
  }],
}

const MATRIX: FixtureMatrixData = {
  gws: [5], source: 'dixon_coles',
  teams: [{ code: 3, name: 'Arsenal', short_name: 'ARS', mean_attack: 0.2,
            mean_defence: 0.8,
            cells: [{ gw: 5, opponent: 'MCI', home: true,
                      attack: 0.2, defence: 0.8 }] }],
}

describe('normalize', () => {
  it('spreads a pool across 0 to 100', () => {
    expect(normalize(1, [1, 3, 5])).toBe(0)
    expect(normalize(5, [1, 3, 5])).toBe(100)
    expect(normalize(3, [1, 3, 5])).toBe(50)
  })

  it('puts a degenerate pool in the middle rather than dividing by zero', () => {
    // A9: one player, or a pool where every value is identical. 50 says "no
    // information", which is true; 0 or 100 would be a verdict.
    expect(normalize(4, [4])).toBe(50)
    expect(normalize(4, [4, 4, 4])).toBe(50)
  })

  it('clamps a value from outside its own pool', () => {
    expect(normalize(9, [1, 3, 5])).toBe(100)
  })
})

describe('axisValues', () => {
  it('reads attacking share off the components, not off a new endpoint', () => {
    const v = axisValues(player({ code: 1 }), COMPONENTS, MATRIX, 5)
    expect(v.attacking).toBeCloseTo(0.6)   // (2 + 1) / 5
  })

  it('reads minutes security off the first fixture', () => {
    expect(axisValues(player({ code: 1 }), COMPONENTS, MATRIX, 5).minutes)
      .toBeCloseTo(0.9)
  })

  it('scores set-piece duty by queue position across all three duties', () => {
    const both = axisValues(
      player({ penalties_order: 1, corners_order: 1 }), null, null, 5)
    const one = axisValues(player({ penalties_order: 2 }), null, null, 5)
    expect(both.setPieces).toBeGreaterThan(one.setPieces)
    expect(both.setPieces).toBeLessThanOrEqual(1)
  })

  it('reads a defender’s fixtures off the defence score', () => {
    const def = axisValues(player({ position: 'DEF' }), null, MATRIX, 5)
    const mid = axisValues(player({ position: 'MID' }), null, MATRIX, 5)
    // Easy to score against (attack 0.2), hard to keep out (defence 0.8):
    // the same fixture is a good one for a midfielder and a bad one for a
    // defender, and one number cannot say both.
    expect(mid.fixtures).toBeGreaterThan(def.fixtures)
  })

  it('has an opinion about nothing when nothing has been fetched', () => {
    const v = axisValues(player({}), null, null, 5)
    expect(v.attacking).toBe(0)
    expect(v.fixtures).toBe(0.5)   // no matrix is not a hard fixture
  })

  it('leaves minutes null when nothing has modelled them', () => {
    // N4. Zero on this axis is the claim "he is expected not to play", which
    // is the strongest thing the chart can say about a player and exactly
    // wrong for one the minutes model has never seen.
    expect(axisValues(player({}), null, null, 5).minutes).toBeNull()
  })
})

describe('CompareRadar', () => {
  it('draws one series per compared player', () => {
    render(<CompareRadar gw={5}
                         players={[player({ code: 1, name: 'A' }),
                                   player({ code: 2, name: 'B' })]}
                         pool={[]} components={COMPONENTS} matrix={MATRIX} />)
    expect(screen.getByLabelText('player comparison radar'))
      .toBeInTheDocument()
  })

  it('states what the axes are normalized against', () => {
    render(<CompareRadar gw={5}
                         players={[player({ code: 1 }), player({ code: 2 })]}
                         pool={[player({ code: 1 }), player({ code: 2 }),
                                player({ code: 3 })]}
                         components={COMPONENTS} matrix={MATRIX} />)
    expect(screen.getByText(/against the 3 players currently listed/))
      .toBeInTheDocument()
  })

  it('falls back to the selection when no pool was handed down', () => {
    render(<CompareRadar gw={5}
                         players={[player({ code: 1 }), player({ code: 2 })]}
                         pool={[]} components={COMPONENTS} matrix={MATRIX} />)
    expect(screen.getByText(/against the 2 players being compared/))
      .toBeInTheDocument()
  })

  it('captions a comparison across positions rather than suppressing it', () => {
    render(<CompareRadar gw={5}
                         players={[player({ code: 1, position: 'GKP' }),
                                   player({ code: 2, position: 'FWD' })]}
                         pool={[]} components={COMPONENTS} matrix={MATRIX} />)
    expect(screen.getByText(/different jobs/i)).toBeInTheDocument()
    // Captioned, not hidden: the chart is still the fastest way to see that
    // they are not comparable.
    expect(screen.getByLabelText('player comparison radar')).toBeInTheDocument()
  })

  it('says nothing about positions when they match', () => {
    render(<CompareRadar gw={5}
                         players={[player({ code: 1, position: 'MID' }),
                                   player({ code: 2, position: 'MID' })]}
                         pool={[]} components={COMPONENTS} matrix={MATRIX} />)
    expect(screen.queryByText(/different jobs/i)).toBeNull()
  })

  it('draws nothing at all until the payloads it reads have landed', () => {
    // N6. Every axis is normalized against a pool, and a pool of identical
    // values normalizes to 50 — so the first paint with nothing fetched is a
    // perfectly regular pentagon at the halfway mark on every axis, which
    // reads as a finding rather than as a spinner.
    render(<CompareRadar gw={5}
                         players={[player({ code: 1 }), player({ code: 2 })]}
                         pool={[]} components={null} matrix={null} />)
    expect(screen.queryByLabelText('player comparison radar')).toBeNull()
    expect(screen.getByText(/still loading/i)).toBeInTheDocument()
  })

  it('names every axis it draws in the caption', () => {
    // N4. Three of the five were described and two — minutes and set pieces
    // — were left for the reader to guess at.
    render(<CompareRadar gw={5}
                         players={[player({ code: 1 }), player({ code: 2 })]}
                         pool={[]} components={COMPONENTS} matrix={MATRIX} />)
    const caption = screen.getByText(/Each axis is scaled/)
    for (const word of [/attacking/i, /minutes/i, /set-piece/i, /fixtures/i,
                        /form/i]) {
      expect(caption.textContent).toMatch(word)
    }
  })

  it('has exactly the five axes the spec names', () => {
    expect(AXES.map(([key]) => key)).toEqual([
      'attacking', 'minutes', 'setPieces', 'fixtures', 'form'])
  })
})
