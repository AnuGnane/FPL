import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiGet } from '../api/client'
import type { RivalSummary } from '../types'

export default function Rivals() {
  const [rows, setRows] = useState<RivalSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    setError(null)
    apiGet<RivalSummary[]>('/api/league/rivals').then(setRows)
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
  if (!rows) return <p className="muted">Loading…</p>

  return (
    <div className="card">
      <h2>Rivals</h2>
      <table>
        <thead>
          <tr>
            <th>#</th><th>Team</th><th>Manager</th><th>Total</th>
            <th>Shared</th><th>Their differentials</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.entry}>
              <td>{row.rank}</td>
              <td><Link to={`/league/rivals/${row.entry}`}>{row.name}</Link></td>
              <td>{row.player_name}</td>
              <td>{row.total}</td>
              <td>{row.overlap}</td>
              <td>{row.differentials}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
