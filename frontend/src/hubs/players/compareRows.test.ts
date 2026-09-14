import { describe, expect, it } from 'vitest'
import type {
  ComponentFixture, ComponentPlayer, ComponentsBreakdown, FixtureMatrixData,
  MinutesOutput, PlayerRow,
} from '../../types'
import { compareColumn, compareRows } from './compareRows'

// The panel's derivation, tested as a table in v18f §2.1 — it used to be
// reachable only by rendering four hundred lines of markup and reading the
// bars back out of the DOM. `ComparePanel.test.tsx` keeps every case about
// what the panel draws.

const term = (label: string, points: number) => ({ label, points })

const MINUTES: MinutesOutput = { p_play: 0.9, p60: 0.8, xmins: 81 }

const fixture = (gw: number, components: { label: string; points: number }[],
                 minutes: MinutesOutput = MINUTES,
                 pen: number | null = null): ComponentFixture => ({
  gw, components, ep: 0, home: true, kickoff_time: null, minutes,
  opponent: 'BOU', pen_taker: pen,
})

const player = (code: number, name: string,
                fixtures: ComponentFixture[]): ComponentPlayer => ({
  code, name, ep: 0, ep_gw: null, ep_hi: null, ep_lo: null, fixtures,
  p_blank: null, p_haul: null, position: 'MID', sigma: null,
  team_name: 'Spurs',
})

const row = (code: number, name: string): PlayerRow => ({
  code, element: code, name, position: 'MID', team_code: 6,
  team_name: 'Spurs', price: 8.0, ep_next: 5.0, ep_horizon: 10.0,
  ownership: 12.0, league_eo: 20.0, available: true, status: 'a', news: '',
  chance_of_playing: null, penalties_order: null, free_kicks_order: null,
  corners_order: null, set_piece_manual: [], in_squad: false,
  last4: [2, 3, 4, 5], field_eo: null, field_se: null, field_n: null,
  field_eo_deadline: null, field_eo_delta: null, field_class: null,
  ep_lo: null, ep_hi: null, p_haul: null, p_blank: null,
})

const BODY: ComponentsBreakdown = {
  gw: 5,
  players: [
    player(1, 'Salah', [fixture(5, [term('Goals', 2.4), term('Cards', -0.3)],
                                undefined, 0.4),
                        fixture(6, [term('Goals', 1.6)])]),
    // No Cards term at all: a player whose forecast carries no such row.
    player(2, 'Saka', [fixture(5, [term('Goals', 1.1), term('Bonus', 0.5)])]),
  ],
}

const MATRIX: FixtureMatrixData = {
  gws: [5, 6], source: 'dixon_coles',
  teams: [{ code: 6, name: 'Spurs', short_name: 'TOT', cells: [],
            mean_attack: 0.5, mean_defence: 0.5 }],
}

describe('the grouped chart rows', () => {
  it('gives every label a column per player, summed over the horizon', () => {
    const rows = compareRows([row(1, 'Salah'), row(2, 'Saka')], BODY)
    expect(rows.map((r) => r.label)).toEqual(['Goals', 'Cards', 'Bonus'])
    // Both of Salah's fixtures, added: the chart is the horizon, not the week.
    expect(rows[0]['1']).toBeCloseTo(4.0)
    expect(rows[0]['2']).toBeCloseTo(1.1)
  })

  it('gives a player with no such term a zero rather than a hole', () => {
    const rows = compareRows([row(1, 'Salah'), row(2, 'Saka')], BODY)
    const cards = rows.find((r) => r.label === 'Cards')!
    expect(cards['2']).toBe(0)
  })

  it('gives a player the payload does not carry a number, never NaN', () => {
    // A cell of NaN reaches Recharts as a bar of no height with no reason
    // given; the panel's own empty state is what says a half could not be
    // read.
    const rows = compareRows([row(1, 'Salah'), row(99, 'Nobody')], BODY)
    for (const r of rows) expect(Number.isNaN(r['99'])).toBe(false)
    expect(rows[0]['99']).toBe(0)
  })

  it('keeps a negative term negative', () => {
    const rows = compareRows([row(1, 'Salah')], BODY)
    expect(rows.find((r) => r.label === 'Cards')!['1']).toBeCloseTo(-0.3)
  })

  it('has no rows at all when the breakdown has not landed', () => {
    expect(compareRows([row(1, 'Salah')], null)).toEqual([])
  })
})

describe('one player’s column', () => {
  it('sorts the terms by how far they moved the forecast, either way', () => {
    // Heaviest first by absolute size: a −0.3 outranks a +0.2, because the
    // question the bars answer is what moved the number.
    const body: ComponentsBreakdown = { gw: 5, players: [
      player(1, 'Salah', [fixture(5, [term('Bonus', 0.2),
                                      term('Cards', -0.3),
                                      term('Goals', 2.4)])]),
    ] }
    const column = compareColumn(row(1, 'Salah'), 5, body, MATRIX)
    expect(column.rows).toEqual([['Goals', 2.4], ['Cards', -0.3],
                                 ['Bonus', 0.2]])
    expect(column.total).toBeCloseTo(2.3)
    expect(column.scale).toBeCloseTo(2.4)
  })

  it('finds the club’s fixture row by code', () => {
    expect(compareColumn(row(1, 'Salah'), 5, BODY, MATRIX).team?.short_name)
      .toBe('TOT')
  })

  it('is an empty column for a player the breakdown does not carry', () => {
    const column = compareColumn(row(99, 'Nobody'), 5, BODY, MATRIX)
    expect(column.comp).toBeUndefined()
    expect(column.rows).toEqual([])
    expect(column.total).toBe(0)
    // Floored, so a bar drawn against it is a division by a number.
    expect(column.scale).toBe(0.01)
    expect(column.here).toEqual([])
  })

  it('adds the penalty duty across the horizon, not the week', () => {
    expect(compareColumn(row(1, 'Salah'), 5, BODY, MATRIX).pen).toBeCloseTo(0.4)
  })

  it('keeps only the requested gameweek’s fixtures and totals their minutes',
     () => {
       const column = compareColumn(row(1, 'Salah'), 5, BODY, MATRIX)
       expect(column.here.map((f) => f.gw)).toEqual([5])
       expect(column.xmSum).toBe(81)
     })

  it('blanks the minutes total when one of a double has none', () => {
    // 88′ printed beside two fixtures reads as the pair, and it would be one
    // of them.
    const body: ComponentsBreakdown = { gw: 5, players: [
      player(1, 'Salah', [
        fixture(5, [term('Goals', 1)], MINUTES),
        fixture(5, [term('Goals', 1)],
                { p_play: null, p60: null, xmins: null }),
      ]),
    ] }
    const column = compareColumn(row(1, 'Salah'), 5, body, MATRIX)
    expect(column.here).toHaveLength(2)
    expect(column.xmSum).toBeNull()
  })
})
