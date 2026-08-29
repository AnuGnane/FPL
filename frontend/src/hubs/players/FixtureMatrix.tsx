import { useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import { EmptyState } from '../../kit'
import type { FixtureMatrixData, MatrixCell } from '../../types'

type View = 'attack' | 'defence'

/** Sage (easy) through the card colour to rust (hard) — the meaning scale. */
function background(score: number): string {
  const eased = Math.min(Math.max(score, 0), 1)
  return eased < 0.5
    ? `color-mix(in srgb, var(--color-sage) ${
        Math.round((0.5 - eased) * 160)}%, var(--color-card))`
    : `color-mix(in srgb, var(--color-rust) ${
        Math.round((eased - 0.5) * 160)}%, var(--color-card))`
}

export default function FixtureMatrix({ from }: { from: number }) {
  const [data, setData] = useState<FixtureMatrixData | null>(null)
  const [view, setView] = useState<View>('attack')

  useEffect(() => {
    apiGet<FixtureMatrixData>(`/api/fixtures/matrix?from=${from}&n=6`)
      .then(setData)
      .catch(() => setData({ gws: [], teams: [], source: 'none' }))
  }, [from])

  if (!data) return <p className="text-text-muted">Loading…</p>
  if (data.source === 'none' || data.teams.length === 0) {
    return (
      <EmptyState
        title="No fixture difficulty yet"
        detail="The matrix prices fixtures with the trained Dixon-Coles team
                model, and no team model has been fitted on this machine."
        action="gaffer train"
      />
    )
  }

  const score = (cell: MatrixCell) => view === 'attack' ? cell.attack : cell.defence

  return (
    <div>
      <div className="mb-3 flex gap-2">
        {(['attack', 'defence'] as View[]).map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => setView(option)}
            className={`rounded-card border px-3 py-1 ${view === option
              ? 'border-text text-text' : 'border-border text-text-muted'}`}
          >
            {option === 'attack' ? 'Attacking' : 'Clean sheet'}
          </button>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="label text-left">Team</th>
              {data.gws.map((gw) => (
                <th key={gw} className="label text-center">GW{gw}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.teams.map((team) => (
              <tr key={team.code}>
                <th scope="row" className="py-1 text-left text-text">
                  {team.short_name}
                </th>
                {data.gws.map((gw) => {
                  const cell = team.cells.find((c) => c.gw === gw)
                  if (!cell) {
                    return (
                      <td key={gw} className="px-1 py-1 text-center
                                              text-text-faint">—</td>
                    )
                  }
                  return (
                    <td
                      key={gw}
                      data-testid={`matrix-cell-${team.code}-${gw}`}
                      data-score={String(score(cell))}
                      style={{ background: background(score(cell)) }}
                      className="px-1 py-1 text-center text-text"
                    >
                      {cell.home ? cell.opponent
                                 : cell.opponent.toLowerCase()}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
