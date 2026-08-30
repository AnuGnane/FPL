import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { apiGet } from '../../api/client'
import PlayerName from '../../components/PlayerName'
import { Card, PosBadge } from '../../kit'
import type { RivalDetailData, SquadPlayer } from '../../types'

function SquadList({ title, players }:
  { title: string; players: SquadPlayer[] }) {
  return (
    <Card title={`${title} (${players.length})`}>
      <ul>
        {players.map((player) => (
          <li key={player.code} className="flex items-center gap-1.5">
            <PosBadge pos={player.position} variant="dot" />
            <PlayerName code={player.code} name={player.name} />
            <span className="num ml-auto text-text-muted">
              £{player.price}m
            </span>
          </li>
        ))}
      </ul>
    </Card>
  )
}

export default function RivalDetail() {
  const { id: entryId } = useParams()
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
      <Card>
        <p className="text-rust">{error}</p>
        <button onClick={load}>Retry</button>
      </Card>
    )
  }
  if (!data) return <p className="text-text-muted">Loading…</p>

  return (
    <>
      <h2>{data.name} · {data.player_name} · {data.total} pts</h2>
      <Card>
        <p>Team value £{data.team_value}m</p>
        <p>Captain: {data.captain ? data.captain.name : 'unknown'}</p>
        <p>
          Chips used:{' '}
          {data.chips_used.length === 0 ? 'none' : data.chips_used.map((chip) =>
            <span className="tag" key={chip}>{chip}</span>)}
        </p>
        {data.live_points !== null && (
          <p className="text-sage">{data.live_points} live points this gameweek</p>
        )}
      </Card>
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
