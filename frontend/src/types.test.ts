import { describe, expect, it } from 'vitest'
import type { NextFixture, PlayerRef } from './types'

/**
 * The mirror check. `types.ts` is hand-maintained against `schemas.py`, and a
 * compile-time assertion is the only thing standing between the two files and
 * a season of silent drift. These tests do almost nothing at runtime — they
 * exist so that `tsc --noEmit` fails when a field's name or nullability moves
 * on one side and not the other.
 */
describe('the v9a identity fields', () => {
  it('lets a player carry a team and a fixture', () => {
    const fixture: NextFixture = {
      opponent_short: 'MUN',
      home: true,
      kickoff_utc: '2026-09-12T14:00:00Z',
      difficulty: 0.31,
    }
    const player: PlayerRef = {
      code: 11, name: 'Saka', position: 'MID', ep: 5.1,
      team_short: 'ARS', team_code: 3, next_fixture: fixture,
    }
    expect(player.next_fixture?.opponent_short).toBe('MUN')
  })

  it('lets both optional halves of a fixture be null independently', () => {
    // A5: "MUN (H) TBC" in a neutral colour is a real state, and it means
    // something different from having no fixture at all.
    const tbc: NextFixture = {
      opponent_short: 'MUN', home: false, kickoff_utc: null, difficulty: null,
    }
    expect(tbc.kickoff_utc).toBeNull()
  })

  it('lets a blank gameweek be a null fixture, not an empty one', () => {
    const blank: PlayerRef = {
      code: 22, name: 'Haaland', ep: 6.2,
      team_short: 'MCI', team_code: 43, next_fixture: null,
    }
    expect(blank.next_fixture).toBeNull()
  })

  it('still types a player with no identity at all', () => {
    // /api/plan and the what-if lab build PlayerRefs without the enrichment.
    const bare: PlayerRef = { code: 33, name: 'Rice', ep: 4.0 }
    expect(bare.team_short).toBeUndefined()
  })
})
