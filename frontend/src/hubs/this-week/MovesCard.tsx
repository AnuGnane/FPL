import {
  Bar, Card, Chip, PosBadge, StackedRows, TABLE_CLASS, THEAD_CLASS, TR_CLASS,
  fmtNum, fmtPct, tdClass, thClass, useIsMobile,
} from '../../kit'
import type { StackedRow } from '../../kit'
import type {
  OverridesPanel, ServedObjective, ServedRestraint,
} from '../../types.generated'

export interface Move {
  code: number
  name: string
  ep: number
  /** Advice written before v3.1 carries no position; the dot then hides. */
  position?: string | null
  frequency?: number | null
  tag?: string | null
}

export interface MovesCardProps {
  buys: Move[]
  sells: Move[]
  hits: number
  /** v13: "1 free transfer · cap 2 hits", from the ladder payload. */
  capLine?: string | null
  /** v16: the ladder's restraint walk, absent on an older payload; v17b: the
   *  card renders its served `line` verbatim; v17f §2.9: the generated type,
   *  so the card reads what `ServedPlan` writes. */
  restraint?: ServedRestraint | null
  /** v16: the solver's own week, printed when it differs from the served
   *  plan; v17b: the card renders its served `line`. */
  objective?: ServedObjective | null
  /** v19b §2.2: the manager's own team news, so the card that prints the
   *  moves says a pin is waiting on the next solve. The Friday loop is pin,
   *  re-run, apply, and until now nothing on This Week closed it — the pin
   *  was taken on Players and this page never mentioned it again. */
  pins?: OverridesPanel | null
}

/** The pins line, or null when there is nothing to say.
 *
 *  v19b §2.2. Three states and not two: a stored pin that `[news] overrides`
 *  is not applying looks identical to an applied one everywhere else in the
 *  app, and "re-run to apply" would then be a lie — the re-run would change
 *  nothing. No pins is silence, because a manager who has pinned nobody has
 *  no loop to close. */
function pinsText(pins: OverridesPanel | null | undefined): string | null {
  const count = pins?.rows.length ?? 0
  if (!pins || count === 0) return null
  const noun = `${count} pin${count === 1 ? '' : 's'}`
  return pins.active
    ? `${noun} live · re-run to apply`
    : `${noun} stored, not applied ([news] overrides is off)`
}

/** One printed row of the moves table, computed once (v19c §2.1).
 *
 *  Both renderings below read these strings rather than formatting their own,
 *  which is the only thing that stops the phone's stacked row from quietly
 *  disagreeing with the column a laptop reader is looking at. */
interface MoveCells {
  key: string
  side: 'IN' | 'OUT'
  move: Move
  xpts: string
  sims: string
  fraction: number | null
}

/** The player as the table prints him: his position as a dot, then his name. */
function MoveName({ move }: { move: Move }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <PosBadge pos={move.position} variant="dot" />
      {move.name}
    </span>
  )
}

export default function MovesCard(
  { buys, sells, hits, capLine, restraint, objective, pins }: MovesCardProps,
) {
  const mobile = useIsMobile()
  const pinsLine = pinsText(pins)
  const rows: MoveCells[] = [
    ...buys.map((m) => ['IN', m] as ['IN', Move]),
    ...sells.map((m) => ['OUT', m] as ['OUT', Move]),
  ].map(([side, move]) => ({
    key: `${side}-${move.code}`,
    side,
    move,
    xpts: fmtNum(move.ep),
    sims: fmtPct(move.frequency ?? null),
    fraction: move.frequency ?? null,
  }))
  const stacked: StackedRow[] = rows.map((row) => ({
    key: row.key,
    // In/out is a direction (rule 1), and on a phone it is the first thing
    // read rather than a column away.
    lead: <Chip tone={row.side === 'IN' ? 'up' : 'down'}>{row.side}</Chip>,
    title: (
      <span className="inline-flex flex-wrap items-center gap-1.5">
        <MoveName move={row.move} />
        {row.move.tag && <Chip>{row.move.tag}</Chip>}
      </span>
    ),
    // The sims share is the number, not the bar: a bar is several rows
    // against one ceiling (rule 7), and stacked rows are read one at a time.
    pairs: [{ label: 'xPts', value: row.xpts, numeric: true },
            { label: 'Sims', value: row.sims, numeric: true }],
  }))
  return (
    <Card title="Recommended moves">
      {capLine && (
        <p className="mb-2 text-text-secondary" data-testid="moves-cap-line">
          {capLine}
        </p>
      )}
      {pinsLine && (
        <p className="mb-2 text-text-secondary" data-testid="moves-pins-line">
          {pinsLine}
        </p>
      )}
      {restraint?.line && (
        <p className="mb-2 text-text-secondary" data-testid="moves-restraint-line">
          {restraint.line}
        </p>
      )}
      {restraint && !restraint.agrees && objective?.line && (
        <p className="mb-2 text-text-muted" data-testid="moves-objective-line">
          {objective.line}
        </p>
      )}
      {rows.length === 0
        ? <p className="text-text-muted">No transfers — bank the free transfer.</p>
        : mobile
          // v19c §2.1: five columns do not fit a phone, and the scroller they
          // used to sit in put every number out of sight of its heading.
          ? <StackedRows rows={stacked} testId="moves-stacked" />
          : (
          <div className="overflow-x-auto">
          <table className={TABLE_CLASS}>
            <thead className={THEAD_CLASS}>
              <tr>
                <th scope="col" className={thClass()}>Move</th>
                <th scope="col" className={thClass()}>Player</th>
                <th scope="col" className={thClass(true)}>xPts</th>
                <th scope="col" className={thClass()}>Sims</th>
                <th scope="col" className={thClass()} />
              </tr>
            </thead>
            <tbody>
              {rows.map(({ key, side, move, xpts, sims, fraction }) => (
                <tr key={key} className={TR_CLASS}>
                  <td className={tdClass()}>
                    {/* In/out is a direction (rule 1). */}
                    <Chip tone={side === 'IN' ? 'up' : 'down'}>{side}</Chip>
                  </td>
                  <td className={`${tdClass()} text-text`}>
                    <MoveName move={move} />
                  </td>
                  <td className={`${tdClass(true)} text-text`}>
                    {xpts}
                  </td>
                  <td className={tdClass()}>
                    {/* Scenario support: several rows, one ceiling (rule 7). */}
                    <Bar testId="sims" fraction={fraction} text={sims} />
                  </td>
                  <td className={`${tdClass()} text-right`}>
                    {move.tag && <Chip>{move.tag}</Chip>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          )}
      {hits > 0 && (
        <p className="mt-3 text-text-secondary">
          {hits} hit{hits === 1 ? '' : 's'}
          {/* v17b §3.3: the price is the served cost; a payload banked before
              the block carries none, and the count stands alone. */}
          {typeof restraint?.hit_cost === 'number' && (
            <>: <span className="tn text-down">{`−${hits * restraint.hit_cost} pts`}</span></>
          )}
        </p>
      )}
    </Card>
  )
}
