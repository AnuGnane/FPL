import { useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import { Card, difficultyBackground, fmtNum } from '../../kit'
import type { TickerData } from '../../types'

export default function FixtureTicker(
  { weeks, oddsKeyPresent }: { weeks: number; oddsKeyPresent?: boolean },
) {
  const [data, setData] = useState<TickerData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sortGw, setSortGw] = useState<number | null>(null)
  const [ascending, setAscending] = useState(true)

  useEffect(() => {
    let live = true
    apiGet<TickerData>(`/api/fixtures/ticker?weeks=${weeks}`)
      .then((body) => { if (live) setData(body) })
      .catch((e: Error) => { if (live) setError(e.message) })
    return () => { live = false }
  }, [weeks])

  if (error) {
    return (
      <Card title="Fixture ticker" className="mb-4">
        <p className="text-rust">{error}</p>
      </Card>
    )
  }
  if (!data) {
    return (
      <Card title="Fixture ticker" className="mb-4">
        <p className="text-text-muted">Loading…</p>
      </Card>
    )
  }

  const teams = [...data.teams]
  if (sortGw !== null) {
    teams.sort((a, b) => {
      const av = a.cells.find((c) => c.gw === sortGw)?.difficulty ?? 1
      const bv = b.cells.find((c) => c.gw === sortGw)?.difficulty ?? 1
      return ascending ? av - bv : bv - av
    })
  }

  const toggle = (gw: number) => {
    if (sortGw === gw) setAscending(!ascending)
    else { setSortGw(gw); setAscending(true) }
  }

  return (
    <Card
      title="Fixture ticker"
      className="mb-4"
      action={(
        <span className="text-text-muted">
          {data.source === 'odds'
            ? 'Difficulty is odds-implied, from banked bookmaker prices.'
            : 'Difficulty is Elo-implied, from finished results.'}
        </span>
      )}
    >
      {data.source === 'elo' && oddsKeyPresent !== true && (
        <p className="mb-3 rounded-card border-l-2 border-info bg-base px-3
                      py-2 text-text-muted">
          No banked odds for these gameweeks — add an odds key for
          market-implied numbers.
        </p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="label pb-1 text-left">Team</th>
              {data.gws.map((gw) => (
                <th key={gw} className="pb-1 text-center">
                  <button type="button" onClick={() => toggle(gw)}
                          className="label hover:text-text">
                    GW{gw}
                    {sortGw === gw ? (ascending ? ' ▴' : ' ▾') : ''}
                  </button>
                </th>
              ))}
              <th className="label pb-1 text-right">Mean</th>
            </tr>
          </thead>
          <tbody>
            {teams.map((team) => (
              <tr key={team.code} className="border-t border-divider">
                <th scope="row"
                    className="py-1 pr-2 text-left font-normal text-text">
                  {team.name}
                </th>
                {data.gws.map((gw) => {
                  const cell = team.cells.find((c) => c.gw === gw)
                  if (!cell) {
                    return (
                      <td key={gw}
                          className="px-1 py-1 text-center text-text-faint">
                        –
                      </td>
                    )
                  }
                  return (
                    <td
                      key={gw}
                      style={{
                        background: difficultyBackground(cell.difficulty),
                      }}
                      className="px-1 py-1 text-center text-text"
                      title={`${team.short_name} ${cell.home ? 'vs' : 'at'} `
                        + `${cell.opponent} (GW${gw}) — ${cell.difficulty}`}
                    >
                      {cell.opponent} ({cell.home ? 'H' : 'A'})
                    </td>
                  )
                })}
                <td className="num py-1 text-right text-text-secondary">
                  {fmtNum(team.mean_difficulty, 2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
