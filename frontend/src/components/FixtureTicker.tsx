import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'
import type { TickerData } from '../types'

// Difficulty is already normalised to [0, 1] server-side, so the colour is a
// straight green-to-red interpolation with no client-side scaling to disagree
// with the numbers in the tooltip.
function colour(difficulty: number): string {
  const hue = Math.round((1 - difficulty) * 120)
  return `hsl(${hue} 55% 32%)`
}

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

  if (error) return <p className="bad">{error}</p>
  if (!data) return <p className="muted">Loading…</p>

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
    <div className="card">
      <h2>Fixture ticker</h2>
      <p className="muted">
        {data.source === 'odds'
          ? 'Difficulty is odds-implied, from banked bookmaker prices.'
          : 'Difficulty is Elo-implied, from finished results.'}
      </p>
      {data.source === 'elo' && oddsKeyPresent !== true && (
        <p className="muted">
          No banked odds for these gameweeks — add an odds key for
          market-implied numbers.
        </p>
      )}
      <table className="ticker">
        <thead>
          <tr>
            <th>Team</th>
            {data.gws.map((gw) => (
              <th key={gw}>
                <button className="player-link" onClick={() => toggle(gw)}>
                  GW{gw}
                </button>
              </th>
            ))}
            <th>Mean</th>
          </tr>
        </thead>
        <tbody>
          {teams.map((team) => (
            <tr key={team.code}>
              <th scope="row">{team.name}</th>
              {data.gws.map((gw) => {
                const cell = team.cells.find((c) => c.gw === gw)
                if (!cell) return <td key={gw} className="muted">–</td>
                return (
                  <td
                    key={gw}
                    style={{ background: colour(cell.difficulty) }}
                    title={`${team.short_name} ${cell.home ? 'vs' : 'at'} `
                      + `${cell.opponent} (GW${gw}) — ${cell.difficulty}`}
                  >
                    {cell.opponent} ({cell.home ? 'H' : 'A'})
                  </td>
                )
              })}
              <td>{team.mean_difficulty}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
