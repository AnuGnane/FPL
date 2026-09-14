import type {
  ComponentFixture, ComponentPlayer, ComponentsBreakdown, FixtureMatrixData,
  MatrixTeam, PlayerRow,
} from '../../types'

/**
 * What the compare panel derives from the two fetched bodies — the components
 * breakdown and the fixture matrix — before anything is drawn.
 *
 * Cut out of `ComparePanel.tsx` in v18f §2.1, where it sat between the two
 * `usePageData` reads and four hundred lines of markup and could only be
 * tested by rendering the whole panel. Both functions take the *bodies*
 * rather than an already-joined structure, because the join is the part that
 * has gone wrong before: it is by `code`, never by name, and a player the
 * payload does not carry has to come back as a number rather than a hole.
 */

/** One row of the grouped chart: the label, then the summed points under each
 *  player's code. Keyed by code, not by name — two players can share a
 *  surname, and a series keyed by one of them would silently overwrite the
 *  other's bars. The name rides on the series as its label, which is what the
 *  legend and the tooltip print. */
export type CompareChartRow = Record<string, string | number>

/**
 * One row per component label, one column per player: the shape Recharts
 * stacks, and the shape that makes "where does his EP come from" readable.
 *
 * The labels are every label the payload mentions, so a term one player has
 * and the other does not is still a row — with a zero in the column of the
 * player who has no such term, which is the honest cell for "this player
 * scores nothing here" and is also what a player missing from the payload
 * altogether gets, rather than a hole that arrives in the chart as NaN.
 */
export function compareRows(players: PlayerRow[],
                            components: ComponentsBreakdown | null):
CompareChartRow[] {
  const labels = new Set<string>()
  for (const player of components?.players ?? []) {
    for (const fixture of player.fixtures) {
      for (const component of fixture.components) labels.add(component.label)
    }
  }
  return [...labels].map((label) => {
    const row: CompareChartRow = { label }
    for (const player of players) {
      const found = components?.players.find((p) => p.code === player.code)
      row[String(player.code)] = found?.fixtures.reduce((total, fixture) => (
        total + (fixture.components.find((c) => c.label === label)?.points ?? 0)
      ), 0) ?? 0
    }
    return row
  })
}

/** One player's column of the panel: his breakdown rows and the two totals
 *  under them, his set-piece and fixture context, and the requested
 *  gameweek's fixtures. */
export interface CompareColumn {
  /** His entry in the breakdown, or `undefined` when the payload has none for
   *  him — the panel still prints his row from the explorer. */
  comp: ComponentPlayer | undefined
  /** His club's row of the fixture matrix, for the difficulty chips. */
  team: MatrixTeam | undefined
  /** `[label, points]`, heaviest first by absolute size, so the term that
   *  moved the forecast most is the top bar whichever way it moved. */
  rows: [string, number][]
  /** The rows summed: the horizon total the caption is about. */
  total: number
  /** The largest absolute term, floored, so a bar can be drawn against it. */
  scale: number
  /** How much of the Goals term is penalty duty, over the horizon. */
  pen: number
  /** The requested gameweek's fixtures, both of them on a double. */
  here: ComponentFixture[]
  /** Expected minutes across those fixtures, or `null` when one of them has
   *  none. */
  xmSum: number | null
}

export function compareColumn(player: PlayerRow, gw: number,
                              components: ComponentsBreakdown | null,
                              matrix: FixtureMatrixData | null):
CompareColumn {
  const team = matrix?.teams.find((t) => t.code === player.team_code)
  const comp = components?.players.find((p) => p.code === player.code)
  // One row per label, summed over the horizon the payload holds — the same
  // reduction the grouped chart above performs, transposed. Zeros stay
  // dropped: that is `components.py`'s own honesty rule ("a panel whose job is
  // showing what moved should not print nine zeroes to get to the one number
  // that did") and not this cycle's to overturn. The rows still sum to the
  // total printed under them.
  const terms = new Map<string, number>()
  for (const fixture of comp?.fixtures ?? []) {
    for (const c of fixture.components) {
      terms.set(c.label, (terms.get(c.label) ?? 0) + c.points)
    }
  }
  const rows = [...terms].sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
  const total = rows.reduce((sum, [, points]) => sum + points, 0)
  const scale = Math.max(...rows.map(([, p]) => Math.abs(p)), 0.01)
  // Every term is already inside Goals — it was folded into e_goals before
  // the terms were assembled — so it is an annotation under that row and
  // never a twelfth component.
  const pen = (comp?.fixtures ?? [])
    .reduce((sum, f) => sum + (f.pen_taker ?? 0), 0)
  // The requested gameweek's fixtures, both of them on a double. Not a mean:
  // p_play averaged over two fixtures is a probability of nothing, and p60
  // does not add. xMins is the one of the three that does, so a total is shown
  // beside the pair (plan A5).
  // A total missing one of its terms is not a smaller total: 88′ printed
  // beside two fixtures reads as the pair, and it would be one of them.
  // `plan.py`'s bank convention, on the one quantity here that adds — any null
  // fixture blanks the total.
  const here = (comp?.fixtures ?? []).filter((f) => f.gw === gw)
  const xmSum = here.some((f) => f.minutes.xmins == null)
    ? null
    : here.reduce((sum, f) => sum + (f.minutes.xmins ?? 0), 0)
  return { comp, team, rows, total, scale, pen, here, xmSum }
}
