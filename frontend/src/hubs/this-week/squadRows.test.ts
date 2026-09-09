import { describe, expect, it } from 'vitest'
import { componentsPath, squadBreakdown, squadRows } from './squadRows'

const ADVICE = {
  xi: [{ code: 1, name: 'Salah', position: 'MID', ep: 6.4,
         team_short: 'LIV', team_code: 14,
         next_fixture: { opponent_short: 'MUN', home: true,
                         kickoff_utc: '2026-09-12T14:00:00Z',
                         difficulty: 0.31 } }],
  bench: [{ code: 2, name: 'Gabriel', position: 'DEF', ep: 4.6 }],
  buys: [{ code: 3, name: 'Wirtz', ep: 6.1, frequency: 0.82 }],
  sells: [{ code: 2, name: 'Gabriel', ep: 4.6, frequency: 0.79 }],
} as never

const PLAYERS = [
  { code: 1, name: 'Salah', position: 'MID', ownership: 42.1, league_eo: 61.5,
    last4: [2, 9], news: 'Knock', chance_of_playing: 75, penalties_order: 1,
    field_eo: 55.2, field_class: 'shield' },
] as never

const COMPONENTS = {
  gw: 5,
  players: [{
    code: 1, ep: 6.4, ep_lo: 4.0, ep_hi: 8.8, p_haul: 0.21, p_blank: 0.18,
    fixtures: [{ components: [{ label: 'Goals', points: 3.1 }],
                 pen_taker: 0.6, minutes: { xmins: 88 } }],
  }],
} as never

describe('squadRows', () => {
  it('lays the XI out before the bench, in the order the advice named them',
     () => {
       const rows = squadRows(ADVICE, PLAYERS, COMPONENTS)
       expect(rows.map((r) => r.code)).toEqual([1, 2])
     })

  it('joins the players row on by code', () => {
    const [salah] = squadRows(ADVICE, PLAYERS, COMPONENTS)
    expect(salah.ownership).toBe(42.1)
    expect(salah.leagueEo).toBe(61.5)
    expect(salah.news).toBe('Knock')
    expect(salah.penalties).toBe(true)
  })

  it('carries the band, the haul and the blank off the components payload',
     () => {
       const [salah] = squadRows(ADVICE, PLAYERS, COMPONENTS)
       expect(salah.epLo).toBe(4.0)
       expect(salah.epHi).toBe(8.8)
       expect(salah.pHaul).toBe(0.21)
       expect(salah.xmins).toBe(88)
     })

  it('leaves the band null when there is no components payload — no minutes '
     + 'model is no band, not a band of width zero', () => {
       const [salah] = squadRows(ADVICE, PLAYERS, null)
       expect(salah.epLo).toBeNull()
       expect(salah.epHi).toBeNull()
       expect(salah.xmins).toBeNull()
     })

  it('gives an unknown ownership NaN and an unknown field EO null, which are '
     + 'different questions', () => {
       const [, gabriel] = squadRows(ADVICE, PLAYERS, COMPONENTS)
       expect(gabriel.ownership).toBeNaN()
       expect(gabriel.leagueEo).toBeNaN()
       expect(gabriel.fieldEo).toBeNull()
       expect(gabriel.fieldClass).toBeNull()
     })

  it('leaves the club null rather than inventing one when the advice was '
     + 'written without a snapshot', () => {
       const [, gabriel] = squadRows(ADVICE, PLAYERS, COMPONENTS)
       expect(gabriel.teamShort).toBeNull()
       expect(gabriel.teamCode).toBeNull()
       expect(gabriel.nextFixture).toBeNull()
     })

  it('prefers the advice position and falls back to the players row', () => {
    // The fixtures are `as never` so they can stay partial; a spread needs an
    // object type back.
    const advice = { ...(ADVICE as object),
                     xi: [{ code: 1, name: 'Salah', ep: 6.4 }] }
    const [salah] = squadRows(advice as never, PLAYERS, COMPONENTS)
    expect(salah.position).toBe('MID')
  })

  it('carries the sim share of a player the plan is moving', () => {
    const [, gabriel] = squadRows(ADVICE, PLAYERS, COMPONENTS)
    expect(gabriel.simPct).toBe(0.79)
  })

  it('leaves the sim share null for a player the plan is not moving', () => {
    const [salah] = squadRows(ADVICE, PLAYERS, COMPONENTS)
    expect(salah.simPct).toBeNull()
  })
})

describe('squadBreakdown', () => {
  it('keys the first fixture of each player by code', () => {
    const out = squadBreakdown(COMPONENTS)
    expect(out[1].ep).toBe(6.4)
    expect(out[1].penTaker).toBe(0.6)
    expect(out[1].components).toEqual([{ label: 'Goals', points: 3.1 }])
  })

  it('is empty for no payload', () => {
    expect(squadBreakdown(null)).toEqual({})
  })

  it('skips a player with no fixture rather than inventing one', () => {
    const out = squadBreakdown(
      { gw: 5, players: [{ code: 9, ep: 1, fixtures: [] }] } as never)
    expect(out).toEqual({})
  })
})

describe('componentsPath', () => {
  it('names the codes it wants, in the order it was given them', () => {
    expect(componentsPath(5, [3, 1, 2])).toBe('/api/components/5?codes=3,1,2')
  })

  it('asks for the whole gameweek when it wants nobody in particular', () => {
    expect(componentsPath(5, [])).toBe('/api/components/5')
  })
})
