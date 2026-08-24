import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { apiGet } from '../api/client'
import PlayerName from '../components/PlayerName'
import type { RivalDetailData, SquadPlayer } from '../types'

function SquadList({ title, players }:
  { title: string; players: SquadPlayer[] }) {
  return (
    <div className="card">
      <h2>{title} ({players.length})</h2>
      <ul>
        {players.map((player) => (
          <li key={player.code}>
            <PlayerName code={player.code} name={player.name} />{' '}
            <span className="muted">{player.position} · £{player.price}m</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function RivalDetail() {
  const { entryId } = useParams()
  const [data, setData] = useState<RivalDetailData | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    setError(null)
    apiGet<RivalDetailData>(`/api/league/rivals/${entryId}`).then(setData)
      .catch((e: Error) => setError(e.message))
  }
  useEffect(load, [entryId])

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
      <h2>{data.name} · {data.player_name} · {data.total} pts</h2>
      <div className="card">
        <p>Team value £{data.team_value}m</p>
        <p>Captain: {data.captain ? data.captain.name : 'unknown'}</p>
        <p>
          Chips used:{' '}
          {data.chips_used.length === 0 ? 'none' : data.chips_used.map((chip) =>
            <span className="tag" key={chip}>{chip}</span>)}
        </p>
        {data.live_points !== null && (
          <p className="good">{data.live_points} live points this gameweek</p>
        )}
      </div>
      {/* Picks are public only for finished gameweeks, so the squad can trail
          the gameweek the live points come from — name the gameweek. */}
      <SquadList title={`Squad · GW${data.squad_gw}`} players={data.squad} />
      <SquadList title="Shared" players={data.shared} />
      <SquadList title="Their differentials"
        players={data.their_differentials} />
      <SquadList title="Your differentials"
        players={data.your_differentials} />
    </>
  )
}
