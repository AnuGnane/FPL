import { useCallback, useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import { Card, JobButton, fmtNum } from '../../kit'
import type { SensitivityReport } from '../../types'

/** Moves worth showing: the ones that are neither certain nor negligible are
 *  the whole point, but a 100% row is the reassurance and a 5% row is the
 *  warning, so the cut is on nothing at all. */
const KINDS = ['buy', 'sell', 'captain', 'chip']

function pct(frequency: number): string {
  return `${Math.round(frequency * 100)}%`
}

export default function SensitivityCard() {
  const [data, setData] = useState<SensitivityReport | null>(null)
  const load = useCallback(() => {
    apiGet<SensitivityReport>('/api/sensitivity')
      .then(setData)
      .catch(() => setData(null))
  }, [])
  useEffect(() => { load() }, [load])

  const rows = (data?.frequencies ?? [])
    .filter((r) => KINDS.includes(r.kind))
    .sort((a, b) => b.frequency - a.frequency)
    .slice(0, 12)

  return (
    <Card
      title="How robust is this plan?"
      className="mb-4"
      action={<JobButton kind="sensitivity" onDone={load} />}
    >
      <p className="mb-3 text-text-muted">
        The same board re-solved twenty times with every expected-points cell
        knocked by its own plausible error. A move that survives most of them
        is an edge; one that does not is the optimizer reading the noise.
      </p>
      {!data?.available && (
        <p className="text-text-muted">
          {data?.notice ?? 'No sensitivity report yet.'}
        </p>
      )}
      {data?.available && (
        <>
          {data.verdict && <p className="mb-3 text-text">{data.verdict}</p>}
          {data.notice && (
            <p className="mb-3 rounded-card border-l-2 border-info bg-base
                          px-3 py-2 text-text-muted">
              {data.notice}
            </p>
          )}
          <table className="w-full">
            <thead>
              <tr>
                <th className="label pb-1 text-left">Move</th>
                <th className="label pb-1 text-left">Player</th>
                <th className="label pb-1 text-right">Solves</th>
                <th className="label pb-1 text-right">Share</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.kind}-${r.code}-${r.gw}`}>
                  <td className="py-1.5 text-text-secondary">{r.label}</td>
                  <td className="py-1.5 text-text">{r.name || '—'}</td>
                  <td className="num py-1.5 text-right text-text-secondary">
                    {r.count}/{data.completed}
                  </td>
                  <td className="num py-1.5 text-right">{pct(r.frequency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-text-muted">
            {data.margin === null
              ? 'Every re-solve reached the same decision.'
              : `The best differing plan is ${fmtNum(data.margin, 1)} expected `
                + 'points behind.'}
            {data.wall_s !== null && ` Swept in ${fmtNum(data.wall_s, 0)}s, `}
            {data.seed !== null && `seed ${data.seed}.`}
          </p>
        </>
      )}
    </Card>
  )
}
