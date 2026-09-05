import {
  Bar, Card, Chip, PosBadge, TABLE_CLASS, THEAD_CLASS, TR_CLASS, fmtNum,
  fmtPct, tdClass, thClass,
} from '../../kit'

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
}

export default function MovesCard(
  { buys, sells, hits, capLine }: MovesCardProps,
) {
  const rows: Array<['IN' | 'OUT', Move]> = [
    ...buys.map((m) => ['IN', m] as ['IN', Move]),
    ...sells.map((m) => ['OUT', m] as ['OUT', Move]),
  ]
  return (
    <Card title="Recommended moves">
      {capLine && (
        <p className="mb-2 text-text-secondary" data-testid="moves-cap-line">
          {capLine}
        </p>
      )}
      {rows.length === 0
        ? <p className="text-text-muted">No transfers — bank the free transfer.</p>
        : (
          <div className="overflow-x-auto">
          <table className={TABLE_CLASS}>
            <thead className={THEAD_CLASS}>
              <tr>
                <th className={thClass()}>Move</th>
                <th className={thClass()}>Player</th>
                <th className={thClass(true)}>xPts</th>
                <th className={thClass()}>Sims</th>
                <th className={thClass()} />
              </tr>
            </thead>
            <tbody>
              {rows.map(([side, move]) => (
                <tr key={`${side}-${move.code}`} className={TR_CLASS}>
                  <td className={tdClass()}>
                    {/* In/out is a direction (rule 1). */}
                    <Chip tone={side === 'IN' ? 'up' : 'down'}>{side}</Chip>
                  </td>
                  <td className={`${tdClass()} text-text`}>
                    <span className="inline-flex items-center gap-1.5">
                      <PosBadge pos={move.position} variant="dot" />
                      {move.name}
                    </span>
                  </td>
                  <td className={`${tdClass(true)} text-text`}>
                    {fmtNum(move.ep)}
                  </td>
                  <td className={tdClass()}>
                    {/* Scenario support: several rows, one ceiling (rule 7). */}
                    <Bar testId="sims" fraction={move.frequency ?? null}
                         text={fmtPct(move.frequency ?? null)} />
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
          {hits} hit{hits === 1 ? '' : 's'}:{' '}
          <span className="tn text-down">{`−${hits * 4} pts`}</span>
        </p>
      )}
    </Card>
  )
}
