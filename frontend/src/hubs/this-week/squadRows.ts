import type { Advice, ComponentsBreakdown, PlayerRow } from '../../types'
import type { SquadBreakdown, SquadRow } from './SquadTable'

/** The squad table's rows: the advice's XI and bench, joined to the players
 *  row and the decomposition by code (v17h §4). Pure, so a row bug is a unit
 *  test rather than a rendered hub. */
export function squadRows(advice: Advice, players: PlayerRow[],
                          components: ComponentsBreakdown | null): SquadRow[] {
  const byCode = new Map(players.map((p) => [p.code, p]))
  return [...advice.xi, ...advice.bench].map((p) => {
    const row = byCode.get(p.code)
    const comp = components?.players.find((c) => c.code === p.code)
    const move = [...advice.buys, ...advice.sells]
      .find((m) => m.code === p.code)
    return {
      code: p.code,
      name: p.name,
      position: p.position ?? row?.position ?? '',
      ep: p.ep,
      // The band comes off the components payload, which keys it (code, gw) —
      // the sweep's own key. Null flows straight through: no minutes model
      // means no band, not a band of width zero.
      epLo: comp?.ep_lo ?? null,
      epHi: comp?.ep_hi ?? null,
      pHaul: comp?.p_haul ?? null,
      pBlank: comp?.p_blank ?? null,
      xmins: comp?.fixtures[0]?.minutes.xmins ?? null,
      ownership: row?.ownership ?? NaN,
      leagueEo: row?.league_eo ?? NaN,
      simPct: move?.frequency ?? null,
      last4: row?.last4 ?? [],
      news: row?.news ?? '',
      chanceOfPlaying: row?.chance_of_playing ?? null,
      penalties: (row?.penalties_order ?? 0) === 1,
      // Resolved server-side and passed straight through. `?? null` rather
      // than a default: an advice payload served by a backend that could read
      // no snapshot has these undefined, and the pitch's honest answer to
      // that is a plain shirt and the word "Blank" — not an invented club.
      teamShort: p.team_short ?? null,
      teamCode: p.team_code ?? null,
      nextFixture: p.next_fixture ?? null,
      // v10b §F1a. Off /api/players, which already computes both against
      // state.owned_codes — the same owned set these rows describe — so the
      // page has one answer to "where does he put me against the field"
      // rather than two. `?? null`, not `?? NaN`: the field EO contract is
      // explicitly "never 0 for unknown", and a NaN reaching a tint
      // comparison is a silent false.
      fieldEo: row?.field_eo ?? null,
      fieldClass: row?.field_class ?? null,
    }
  })
}

/** code -> the first fixture's EP decomposition, for the table's expander. */
export function squadBreakdown(
  components: ComponentsBreakdown | null): Record<number, SquadBreakdown> {
  const breakdown: Record<number, SquadBreakdown> = {}
  for (const player of components?.players ?? []) {
    const fixture = player.fixtures[0]
    if (!fixture) continue
    breakdown[player.code] = {
      ep: player.ep,
      components: fixture.components,
      penTaker: fixture.pen_taker ?? null,
    }
  }
  return breakdown
}

/** The one spelling of the decomposition URL (v17h §3). Nothing calls it yet:
 *  it exists so that when This Week and the Why panel are converted they ask
 *  for the same codes in the same order, and the two cannot drift into a cache
 *  miss that fetches the same thing twice. */
export function componentsPath(gw: number, codes: number[]): string {
  if (codes.length === 0) return `/api/components/${gw}`
  return `/api/components/${gw}?codes=${codes.join(',')}`
}
