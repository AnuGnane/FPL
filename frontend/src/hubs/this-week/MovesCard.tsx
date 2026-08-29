import { Badge, Card, fmtNum, fmtPct } from '../../kit'

export interface Move {
  code: number
  name: string
  ep: number
  frequency?: number | null
  tag?: string | null
}

export interface MovesCardProps {
  buys: Move[]
  sells: Move[]
  hits: number
}

export default function MovesCard({ buys, sells, hits }: MovesCardProps) {
  const rows: Array<[string, Move]> = [
    ...buys.map((m) => ['IN', m] as [string, Move]),
    ...sells.map((m) => ['OUT', m] as [string, Move]),
  ]
  return (
    <Card title="Recommended moves">
      {rows.length === 0
        ? <p className="text-text-muted">No transfers — bank the free transfer.</p>
        : (
          <table className="w-full">
            <thead>
              <tr>
                <th className="label text-left">Move</th>
                <th className="label text-left">Player</th>
                <th className="label text-right">xPts</th>
                <th className="label text-right">sim%</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map(([side, move]) => (
                <tr key={`${side}-${move.code}`} className="border-t border-divider">
                  <td className={`py-1 ${side === 'IN' ? 'text-sage' : 'text-rust'}`}>
                    {side}
                  </td>
                  <td className="py-1 text-text">{move.name}</td>
                  <td className="num py-1 text-right text-text">
                    {fmtNum(move.ep)}
                  </td>
                  <td className="num py-1 text-right text-text-secondary">
                    {fmtPct(move.frequency ?? null)}
                  </td>
                  <td className="py-1 text-right">
                    {move.tag && <Badge variant="info">{move.tag}</Badge>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          )}
      {hits > 0 && (
        <p className="mt-3 text-rust">
          {hits} hit{hits === 1 ? '' : 's'}:{' '}
          <span className="num">-{hits * 4} pts</span>
        </p>
      )}
    </Card>
  )
}
