import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { apiGet } from '../../api/client'
import {
  Badge, Card, ExplainModal, Loading, PageHeader, PlayerCard, fmtNum,
} from '../../kit'
import type { RivalDetailData, SquadPlayer } from '../../types'

function SquadList({ title, players }:
  { title: string; players: SquadPlayer[] }) {
  // One modal per list. The four lists are independent and only one card can
  // have a chip pressed at a time within a list, so lifting it to the page
  // would buy nothing but a prop.
  const [explain, setExplain] = useState<number | null>(null)
  return (
    <Card title={`${title} (${players.length})`} className="mb-4">
      {players.length === 0
        ? <p className="text-text-muted">Nobody.</p>
        : (
          <ul className="flex flex-col gap-1">
            {players.map((player) => (
              <li key={player.code} className="flex items-center gap-1.5">
                <PlayerCard
                  size="chip"
                  code={player.code}
                  name={player.name}
                  position={player.position}
                  // /api/league/rivals/{id} carries no team field and this
                  // cycle adds no server code (plan A4).
                  teamShort={null}
                  teamCode={null}
                  // A rival's squad is priced, not projected: the payload has
                  // his price and no expected points (plan A3).
                  ep={null}
                  onSelect={setExplain}
                />
                <span className="num ml-auto text-text-muted">
                  £{player.price}m
                </span>
              </li>
            ))}
          </ul>
          )}
      {explain !== null && (
        <ExplainModal code={explain} onClose={() => setExplain(null)} />
      )}
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
      <>
        <PageHeader title="Rival" />
        <Card title="Could not load this rival">
          <p className="text-rust">{error}</p>
          <button
            type="button"
            onClick={load}
            className="mt-3 rounded-card border border-border bg-base px-3 py-2
                       text-text-secondary hover:text-text"
          >
            Retry
          </button>
        </Card>
      </>
    )
  }
  if (!data) {
    return (
      <>
        <PageHeader title="Rival" />
        <Loading />
      </>
    )
  }

  return (
    <>
      <PageHeader
        title={data.name}
        context={`${data.player_name} · ${fmtNum(data.total, 0)} pts`}
      />
      <Card title="Their season" className="mb-4">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
          <div>
            <dt className="label">Team value</dt>
            <dd className="num text-text">£{data.team_value}m</dd>
          </div>
          <div>
            <dt className="label">Armband</dt>
            {/* Kept as one sentence: "Captain: X" is how the page has always
                named it, and splitting it across elements would only make the
                label say the same word twice. */}
            <dd className="text-text">
              Captain: {data.captain ? data.captain.name : 'unknown'}
            </dd>
          </div>
          <div>
            <dt className="label">Chips used</dt>
            <dd className="mt-0.5 flex flex-wrap gap-1">
              {data.chips_used.length === 0
                ? <span className="text-text-muted">none</span>
                : data.chips_used.map((chip) => (
                  <Badge key={chip} variant="info">{chip}</Badge>
                ))}
            </dd>
          </div>
        </dl>
        {data.live_points !== null && (
          <p className="mt-3 text-sage">
            <span className="num">{data.live_points}</span> live points this
            gameweek
          </p>
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
