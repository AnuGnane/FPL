import { Card, PlayerName, TONE_CLASS, fmtNum, toneOf } from '../../kit'
import type { WhatIfResult } from '../../types'

// Both plans are scored the way the solver scores them: the captain's points
// counted twice and hit costs already subtracted. That is a different measure
// from This Week's plain XI sum, so the rows say so.
const PTS_NOTE = '(incl. captain, after hits)'

function names(players: { code: number; name: string }[]) {
  return players.map((player) => player.name).join(', ') || '—'
}

interface Row {
  label: string
  original: string
  yours: string
  changed: boolean
  numeric?: boolean
}

export default function PlanDiffTable({ diff }: { diff: WhatIfResult }) {
  const rows: Row[] = [
    { label: `xPts this GW ${PTS_NOTE}`,
      original: fmtNum(diff.baseline.expected_pts),
      yours: fmtNum(diff.yours.expected_pts),
      changed: diff.baseline.expected_pts !== diff.yours.expected_pts,
      numeric: true },
    // delta_xpts is the horizon difference, so it belongs on this row.
    { label: `xPts over horizon ${PTS_NOTE}`,
      original: fmtNum(diff.baseline.horizon_pts),
      yours: fmtNum(diff.yours.horizon_pts),
      changed: diff.delta_xpts !== 0, numeric: true },
    { label: 'Transfers in', original: names(diff.baseline.buys),
      yours: names(diff.yours.buys), changed: diff.transfers_changed },
    { label: 'Transfers out', original: names(diff.baseline.sells),
      yours: names(diff.yours.sells), changed: diff.transfers_changed },
    { label: 'Hits', original: String(diff.baseline.hits),
      yours: String(diff.yours.hits),
      changed: diff.baseline.hits !== diff.yours.hits, numeric: true },
    { label: 'Captain', original: diff.baseline.captain.name,
      yours: diff.yours.captain.name, changed: diff.captain_changed },
  ]

  return (
    <Card title="Original vs yours" className="mb-4">
      <table className="w-full">
        <thead>
          <tr>
            <th />
            <th className="label pb-1 text-right">Original</th>
            <th className="label pb-1 text-right">Yours</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.label}
              data-changed={String(row.changed)}
              // A changed row is the whole point of the table, so it is the
              // one that keeps full-strength text; the rest recede.
              className="border-t border-divider"
            >
              <td className={`py-1.5 ${row.changed
                ? 'text-text' : 'text-text-muted'}`}>
                {row.changed && (
                  <span aria-hidden className="mr-1.5 text-info">●</span>
                )}
                {row.label}
              </td>
              <td className={`py-1.5 text-right ${row.numeric ? 'num' : ''}
                ${row.changed ? 'text-text-secondary' : 'text-text-muted'}`}>
                {row.original}
              </td>
              <td className={`py-1.5 text-right ${row.numeric ? 'num' : ''}
                ${row.changed ? 'text-text' : 'text-text-muted'}`}>
                {row.yours}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {([['In', diff.xi_in], ['Out', diff.xi_out]] as const).map(
          ([side, players]) => (
            <div key={side}>
              <p className="label mb-1">XI {side}</p>
              {players.length === 0
                ? <p className="text-text-muted">—</p>
                : (
                  <ul className="flex flex-col gap-0.5">
                    {players.map((player) => (
                      <li key={player.code}>
                        <PlayerName code={player.code} name={player.name}
                                    pos={player.position ?? null} />
                      </li>
                    ))}
                  </ul>
                  )}
            </div>
          ))}
      </div>
      <p className={`mt-4 ${TONE_CLASS[toneOf(diff.delta_xpts)]}`}>
        {diff.verdict}
      </p>
    </Card>
  )
}
