import { describe, expect, it } from 'vitest'
import type { Advice } from '../../types'
import { componentsPath, squadBreakdown, squadRows } from './squadRows'

/** Salah is in the XI with a club and a fixture, Wirtz is the buy the plan
 *  brings into it, Gabriel is the sell sitting on the bench with neither a
 *  players row nor an enriched identity. */
const ADVICE = {
  gw: 5,
  xi: [{ code: 1, name: 'Salah', position: 'MID', ep: 6.4,
         team_short: 'LIV', team_code: 14,
         next_fixture: { opponent_short: 'MUN', home: true,
                         kickoff_utc: '2026-09-12T14:00:00Z',
                         difficulty: 0.31 } },
       { code: 3, name: 'Wirtz', position: 'MID', ep: 6.1 }],
  bench: [{ code: 2, name: 'Gabriel', position: 'DEF', ep: 4.6 }],
  captain: { code: 1, name: 'Salah', ep: 6.4 },
  vice: { code: 3, name: 'Wirtz', ep: 6.1 },
  buys: [{ code: 3, name: 'Wirtz', ep: 6.1, frequency: 0.82 }],
  sells: [{ code: 2, name: 'Gabriel', ep: 4.6, frequency: 0.79 }],
  hits: 0,
  expected_pts: 61.2,
  chip_table: [],
  strategy: null,
} satisfies Advice

/** Salah's row says FWD where the advice says MID, so the two operands of the
 *  position fallback can be told apart; Wirtz is second in the penalty order,
 *  which is not the same as taking them. */
const PLAYERS = [
  { code: 1, name: 'Salah', position: 'FWD', ownership: 42.1, league_eo: 61.5,
    last4: [2, 9], news: 'Knock', chance_of_playing: 75, penalties_order: 1,
    field_eo: 55.2, field_class: 'shield' },
  { code: 3, name: 'Wirtz', position: 'MID', ownership: 8.4, league_eo: 12.0,
    last4: [5, 3], news: '', chance_of_playing: null, penalties_order: 2,
    field_eo: 9.1, field_class: null },
] as never

/** Code 2 is the player the sweep decomposed but could not fit a minutes
 *  model to: he is in the payload with every band field null. */
const COMPONENTS = {
  gw: 5,
  players: [{
    code: 1, ep: 6.4, ep_lo: 4.0, ep_hi: 8.8, p_haul: 0.21, p_blank: 0.18,
    fixtures: [{ components: [{ label: 'Goals', points: 3.1 }],
                 pen_taker: 0.6, minutes: { xmins: 88 } }],
  }, {
    code: 2, ep: 4.6, ep_lo: null, ep_hi: null, p_haul: null, p_blank: null,
    fixtures: [{ components: [{ label: 'Clean sheet', points: 1.4 }],
                 pen_taker: null, minutes: { xmins: null } }],
  }],
} as never

describe('squadRows', () => {
  it('lays the XI out before the bench, in the order the advice named them',
     () => {
       const rows = squadRows(ADVICE, PLAYERS, COMPONENTS)
       expect(rows.map((r) => r.code)).toEqual([1, 3, 2])
     })

  it('takes the name and the points off the advice, which is the run\'s own '
     + 'answer', () => {
       const [salah] = squadRows(ADVICE, PLAYERS, COMPONENTS)
       expect(salah.name).toBe('Salah')
       expect(salah.ep).toBe(6.4)
     })

  it('joins the players row on by code', () => {
    const [salah] = squadRows(ADVICE, PLAYERS, COMPONENTS)
    expect(salah.ownership).toBe(42.1)
    expect(salah.leagueEo).toBe(61.5)
    expect(salah.news).toBe('Knock')
    expect(salah.last4).toEqual([2, 9])
    expect(salah.chanceOfPlaying).toBe(75)
    expect(salah.penalties).toBe(true)
    expect(salah.fieldEo).toBe(55.2)
    expect(salah.fieldClass).toBe('shield')
  })

  it('gives the penalty chip to the first taker and to nobody behind him',
     () => {
       const [, wirtz] = squadRows(ADVICE, PLAYERS, COMPONENTS)
       expect(wirtz.penalties).toBe(false)
     })

  it('leaves a player with no players row blank rather than filling him in',
     () => {
       const [, , gabriel] = squadRows(ADVICE, PLAYERS, COMPONENTS)
       expect(gabriel.news).toBe('')
       expect(gabriel.last4).toEqual([])
       expect(gabriel.chanceOfPlaying).toBeNull()
       expect(gabriel.penalties).toBe(false)
     })

  it('carries the band, the haul and the blank off the components payload',
     () => {
       const [salah] = squadRows(ADVICE, PLAYERS, COMPONENTS)
       expect(salah.epLo).toBe(4.0)
       expect(salah.epHi).toBe(8.8)
       expect(salah.pHaul).toBe(0.21)
       expect(salah.pBlank).toBe(0.18)
       expect(salah.xmins).toBe(88)
     })

  it('leaves the band null for a decomposed player with no minutes model — '
     + 'no model is no band, not a band of width zero', () => {
       const [, , gabriel] = squadRows(ADVICE, PLAYERS, COMPONENTS)
       expect(gabriel.epLo).toBeNull()
       expect(gabriel.epHi).toBeNull()
       expect(gabriel.pHaul).toBeNull()
       expect(gabriel.pBlank).toBeNull()
       expect(gabriel.xmins).toBeNull()
     })

  it('leaves the band null when there is no components payload at all', () => {
    const [salah] = squadRows(ADVICE, PLAYERS, null)
    expect(salah.epLo).toBeNull()
    expect(salah.epHi).toBeNull()
    expect(salah.pHaul).toBeNull()
    expect(salah.pBlank).toBeNull()
    expect(salah.xmins).toBeNull()
  })

  it('gives an unknown ownership NaN and an unknown field EO null, which are '
     + 'different questions', () => {
       const [, , gabriel] = squadRows(ADVICE, PLAYERS, COMPONENTS)
       expect(gabriel.ownership).toBeNaN()
       expect(gabriel.leagueEo).toBeNaN()
       expect(gabriel.fieldEo).toBeNull()
       expect(gabriel.fieldClass).toBeNull()
     })

  it('passes the club and the next fixture through as the backend resolved '
     + 'them', () => {
       const [salah] = squadRows(ADVICE, PLAYERS, COMPONENTS)
       expect(salah.teamShort).toBe('LIV')
       expect(salah.teamCode).toBe(14)
       expect(salah.nextFixture?.opponent_short).toBe('MUN')
     })

  it('leaves the club null rather than inventing one when the advice was '
     + 'written without a snapshot', () => {
       const [, , gabriel] = squadRows(ADVICE, PLAYERS, COMPONENTS)
       expect(gabriel.teamShort).toBeNull()
       expect(gabriel.teamCode).toBeNull()
       expect(gabriel.nextFixture).toBeNull()
     })

  it('prefers the position the advice named over the one on the players row',
     () => {
       const [salah] = squadRows(ADVICE, PLAYERS, COMPONENTS)
       expect(salah.position).toBe('MID')
     })

  it('falls back to the players row when the advice names no position', () => {
    const advice = { ...ADVICE, xi: [{ code: 1, name: 'Salah', ep: 6.4 }] }
    const [salah] = squadRows(advice, PLAYERS, COMPONENTS)
    expect(salah.position).toBe('FWD')
  })

  it('leaves the position empty when neither the advice nor a players row '
     + 'names one', () => {
       const advice = { ...ADVICE, xi: [{ code: 2, name: 'Gabriel', ep: 4.6 }] }
       const [gabriel] = squadRows(advice, PLAYERS, COMPONENTS)
       expect(gabriel.position).toBe('')
     })

  it('carries the sim share of a player the plan is selling', () => {
    const [, , gabriel] = squadRows(ADVICE, PLAYERS, COMPONENTS)
    expect(gabriel.simPct).toBe(0.79)
  })

  it('carries the sim share of a player the plan is buying', () => {
    const [, wirtz] = squadRows(ADVICE, PLAYERS, COMPONENTS)
    expect(wirtz.simPct).toBe(0.82)
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

  it('leaves the pen share null for a fixture with no penalty duty in it',
     () => {
       expect(squadBreakdown(COMPONENTS)[2].penTaker).toBeNull()
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
