import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiGet } from '../api/client'
import LineChart from '../components/LineChart'
import type { LeagueRaceData } from '../types'

const COLOURS = ['#4ade80', '#f0b429', '#60a5fa', '#e5534b', '#c084fc']

export default function LeagueRace() {
  const [data, setData] = useState<LeagueRaceData | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    setError(null)
    apiGet<LeagueRaceData>('/api/league/race').then(setData)
      .catch((e: Error) => setError(e.message))
  }
  useEffect(load, [])

  if (error) {
    return (
      <div className="card">
        <p className="bad">{error}</p>
        <button onClick={load}>Retry</button>
      </div>
    )
  }
  if (!data) return <p className="muted">Loading…</p>

  return (
    <>
      <h2>League Race</h2>
      <div className="card">
        <h2>Standings</h2>
        <table>
          <thead>
            <tr><th>#</th><th>Team</th><th>GW</th><th>Total</th></tr>
          </thead>
          <tbody>
            {data.standings.map((row) => (
              <tr key={row.entry} className={row.is_you ? 'you' : undefined}>
                <td>{row.rank}</td>
                <td>
                  {row.is_you ? row.name : (
                    <Link to={`/league/rivals/${row.entry}`}>{row.name}</Link>
                  )}
                </td>
                <td>{row.event_total}</td>
                <td>{row.total}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <Link to="/league/rivals">All rival squads →</Link>
      </div>
      <div className="card">
        <h2>Trajectory</h2>
        <LineChart
          label="Points by gameweek"
          series={data.trajectory.map((t, index) => ({
            name: t.name,
            colour: COLOURS[index % COLOURS.length],
            points: t.points.map((p) => ({ x: p.gw, y: p.total })),
          }))}
        />
      </div>
      <div className="card">
        <h2>Gap to the leader</h2>
        <LineChart
          label="Gap to the leader"
          series={[{
            name: 'gap',
            colour: '#f0b429',
            points: data.gap.map((g) => ({ x: g.gw, y: g.gap })),
          }]}
        />
      </div>
      <div className="card">
        <h2>Win probability</h2>
        <table>
          <tbody>
            {data.win_probability.map((row) => (
              <tr key={row.name}>
                <td>{row.name}</td>
                <td>{Math.round(row.p_win * 100)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">{data.lam_explained}</p>
      </div>
    </>
  )
}
