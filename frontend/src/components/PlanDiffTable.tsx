import type { WhatIfResult } from '../types'
import PlayerName from './PlayerName'

// Both plans are scored the way the solver scores them: the captain's points
// counted twice and hit costs already subtracted. That is a different measure
// from This Week's plain XI sum, so the rows say so.
const PTS_NOTE = '(incl. captain, after hits)'

function names(players: { code: number; name: string }[]) {
  return players.map((player) => player.name).join(', ') || '—'
}

export default function PlanDiffTable({ diff }: { diff: WhatIfResult }) {
  const rows: Array<[string, string, string, boolean]> = [
    [`xPts this GW ${PTS_NOTE}`, String(diff.baseline.expected_pts),
      String(diff.yours.expected_pts),
      diff.baseline.expected_pts !== diff.yours.expected_pts],
    // delta_xpts is the horizon difference, so it belongs on this row.
    [`xPts over horizon ${PTS_NOTE}`, String(diff.baseline.horizon_pts),
      String(diff.yours.horizon_pts), diff.delta_xpts !== 0],
    ['Transfers in', names(diff.baseline.buys), names(diff.yours.buys),
      diff.transfers_changed],
    ['Transfers out', names(diff.baseline.sells), names(diff.yours.sells),
      diff.transfers_changed],
    ['Hits', String(diff.baseline.hits), String(diff.yours.hits),
      diff.baseline.hits !== diff.yours.hits],
    ['Captain', diff.baseline.captain.name, diff.yours.captain.name,
      diff.captain_changed],
  ]
  return (
    <div className="card">
      <h2>Original vs yours</h2>
      <table>
        <thead>
          <tr><th /><th>Original</th><th>Yours</th></tr>
        </thead>
        <tbody>
          {rows.map(([label, original, yours, changed]) => (
            <tr key={label} className={changed ? 'changed' : undefined}>
              <td>{label}</td>
              <td>{original}</td>
              <td>{yours}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3>XI changes</h3>
      <p>
        In:{' '}
        {diff.xi_in.length === 0 ? '—' : diff.xi_in.map((player) => (
          <span key={player.code}>
            <PlayerName code={player.code} name={player.name} />{' '}
          </span>
        ))}
      </p>
      <p>
        Out:{' '}
        {diff.xi_out.length === 0 ? '—' : diff.xi_out.map((player) => (
          <span key={player.code}>
            <PlayerName code={player.code} name={player.name} />{' '}
          </span>
        ))}
      </p>
      <p className={diff.delta_xpts < 0 ? 'bad' : 'good'}>{diff.verdict}</p>
    </div>
  )
}
