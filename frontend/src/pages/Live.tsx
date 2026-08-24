import { useEffect, useRef, useState } from 'react'
import { apiGet } from '../api/client'
import PlayerName from '../components/PlayerName'
import type { LiveState } from '../types'

const POLL_MS = 60000

function arrow(delta: number): string {
  if (delta > 0) return `▲${delta}`
  if (delta < 0) return `▼${-delta}`
  return '–'
}

export default function Live() {
  const [data, setData] = useState<LiveState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<number | null>(null)

  useEffect(() => {
    let live = true
    const stop = () => {
      if (timer.current !== null) {
        window.clearInterval(timer.current)
        timer.current = null
      }
    }
    const load = () => apiGet<LiveState>('/api/live')
      .then((body) => {
        if (!live) return
        setData(body)
        setError(null)
        if (!body.active) stop()      // quiet between gameweeks (spec §3.5)
      })
      .catch((e: Error) => { if (live) setError(e.message) })
    load()
    timer.current = window.setInterval(load, POLL_MS)
    return () => { live = false; stop() }
  }, [])

  if (error) return <p className="bad">{error}</p>
  if (!data) return <p className="muted">Loading…</p>
  if (!data.active) {
    return (
      <div className="card">
        <h2>Live</h2>
        <p className="muted">No gameweek in progress — nothing to track.</p>
      </div>
    )
  }

  return (
    <>
      <h2>GW{data.gw} live</h2>
      <div className="card">
        <p>
          You: <strong>{data.my_points}</strong> ·{' '}
          {data.matches_in_play} match(es) in play
        </p>
        <p className="muted">
          Bonus is provisional (reconstructed from BPS) and no autosubs are
          applied.
        </p>
        <table>
          <thead>
            <tr>
              <th>Player</th><th>Pts</th><th>Bonus</th><th>Mins</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {data.players.map((player) => (
              <tr key={player.element}>
                <td>
                  <PlayerName code={player.code} name={player.name} />
                  {player.multiplier > 1 && ' (C)'}
                </td>
                <td>{player.points}</td>
                <td>{player.provisional_bonus > 0
                  ? `+${player.provisional_bonus}` : '–'}</td>
                <td>{player.minutes}</td>
                <td className="muted">{player.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card">
        <h2>League, live</h2>
        <table>
          <thead>
            <tr><th>Team</th><th>Live</th><th>Projected</th><th>Move</th></tr>
          </thead>
          <tbody>
            {data.table.map((row) => (
              <tr key={row.entry}>
                <td>{row.name}</td>
                <td>{row.live}</td>
                <td>{row.projected}</td>
                <td>{arrow(row.delta)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
