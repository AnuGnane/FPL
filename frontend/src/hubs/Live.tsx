import { useCallback, useEffect, useState } from 'react'
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip,
  XAxis, YAxis,
} from 'recharts'
import { apiGet } from '../api/client'
import {
  type Column, Badge, Card, DataTable, EmptyState, Loading, PageHeader,
  PlayerName, Stat, fmtNum,
} from '../kit'
import type { LiveState, LiveTableRow } from '../types'

const POLL_MS = 60000

const ROLE_LABEL: Record<string, string> = {
  above: 'One place above',
  below: 'One place below',
  leader: 'The leader',
}

/** The series carries ISO instants; the axis wants a wall clock. */
function clock(at: string): string {
  return at.slice(11, 16)
}

function arrow(delta: number): string {
  if (delta > 0) return `▲${delta}`
  if (delta < 0) return `▼${-delta}`
  return '–'
}

const TABLE_COLUMNS: Column<LiveTableRow>[] = [
  { key: 'name', header: 'Team', primary: true, value: (r) => r.name },
  { key: 'live', header: 'Live', primary: true, numeric: true,
    value: (r) => r.live },
  { key: 'projected', header: 'Projected', primary: true, numeric: true,
    value: (r) => r.projected },
  { key: 'race', header: 'Race', numeric: true,
    value: (r) => (r.race == null ? '–' : fmtNum(r.race, 1)) },
  { key: 'delta', header: 'Move', value: (r) => arrow(r.delta) },
]

export default function Live() {
  const [data, setData] = useState<LiveState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [active, setActive] = useState(true)
  const [auto, setAuto] = useState(true)

  const load = useCallback(() => apiGet<LiveState>('/api/live')
    .then((body) => {
      setData(body)
      setError(null)
      setActive(body.active)
    })
    .catch((e: Error) => { setError(e.message) }), [])

  useEffect(() => { void load() }, [load])

  useEffect(() => {
    // Quiet between gameweeks (spec §3.5): nothing moves, so nothing polls.
    if (!auto || !active) return
    const timer = window.setInterval(load, POLL_MS)
    return () => window.clearInterval(timer)
  }, [auto, active, load])

  const pollToggle = (
    <label className="flex items-center gap-2 text-text-secondary">
      <input type="checkbox" checked={auto}
             onChange={(e) => setAuto(e.target.checked)} />
      Auto-refresh
    </label>
  )

  const header = (
    <PageHeader
      title="Live"
      context={data && data.gw !== null
        ? `GW${data.gw} · ${data.matches_in_play} matches in play`
        : undefined}
      action={pollToggle}
    />
  )

  // A cold clone has no live snapshot at all, which is an ordinary state and
  // not a crash: say what populates it rather than showing a bare error line
  // (spec §9).
  if (error) {
    return (
      <>
        {header}
        <EmptyState
          title="No live data yet"
          detail={error}
          action="gaffer refresh-data"
        />
      </>
    )
  }
  if (!data) {
    return (
      <>
        {header}
        <Loading />
      </>
    )
  }

  if (!data.active) {
    return (
      <>
        {header}
        <EmptyState
          title="No gameweek in progress"
          detail="The live view wakes up when the first match of a gameweek
                  kicks off. Nothing is in play right now."
          action="Come back at kick-off"
        />
      </>
    )
  }

  return (
    <>
      {header}
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Your points" value={fmtNum(data.my_points, 0)} />
        <Stat label="Projected"
              value={fmtNum(data.my_projected_points ?? data.my_points, 0)} />
        <Stat label="Race"
              value={data.my_race == null ? '–' : fmtNum(data.my_race, 1)} />
        <Stat label="Matches in play" value={fmtNum(data.matches_in_play, 0)} />
      </div>
      <Card
        title="Race to full time"
        className="mb-4"
        action={(
          <span className="text-text-muted">
            Projected points plus what the model still expects from every
            player whose match is unfinished.
          </span>
        )}
      >
        {data.race_notice && (
          <p className="mb-3 rounded-card border-l-2 border-info bg-base px-3
                        py-2 text-text-muted">
            {data.race_notice}
          </p>
        )}
        {(data.race_series?.length ?? 0) < 2 ? (
          <p className="text-text-muted">
            The trajectory builds as the page polls — one point a minute from
            the moment you opened it, and it starts again when the server
            restarts.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={data.race_series}>
              <CartesianGrid stroke="var(--color-divider)" vertical={false} />
              <XAxis dataKey="at" tickFormatter={clock}
                     stroke="var(--color-text-muted)" />
              <YAxis stroke="var(--color-text-muted)" />
              <Tooltip
                labelFormatter={clock}
                contentStyle={{
                  background: 'var(--color-card)',
                  border: '1px solid var(--color-border)',
                }} />
              {data.race_reference != null && (
                <ReferenceLine
                  y={data.race_reference}
                  stroke="var(--color-text-muted)"
                  strokeDasharray="4 4"
                  label={{ value: `plan ${data.race_reference}`,
                           position: 'insideTopRight',
                           fill: 'var(--color-text-muted)', fontSize: 11 }} />
              )}
              <Line type="monotone" dataKey="you" name="You" dot={false}
                    strokeWidth={2.5} stroke="var(--color-sage)" />
              <Line type="monotone" dataKey="leader"
                    name={data.leader_name ?? 'Top rival'} dot={false}
                    strokeWidth={1.5} stroke="var(--color-info)" />
            </LineChart>
          </ResponsiveContainer>
        )}
      </Card>
      <Card
        title="Your players"
        className="mb-4"
        action={(
          <span className="text-text-muted">
            Bonus is provisional (reconstructed from BPS); no autosubs applied.
          </span>
        )}
      >
        {data.notice && (
          <p className="mb-3 rounded-card border-l-2 border-info bg-base px-3
                        py-2 text-text-muted">
            {data.notice}
          </p>
        )}
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                <th className="label pb-1 text-left">Player</th>
                <th className="label pb-1 text-right">Pts</th>
                <th className="label pb-1 text-right">Bonus</th>
                <th className="label pb-1 text-right">Mins</th>
                <th className="label pb-1 text-right">Left</th>
                <th className="label pb-1 text-left">Status</th>
                <th className="label pb-1 text-right">Top 10k EO</th>
                <th className="label pb-1 text-right">Owned</th>
              </tr>
            </thead>
            <tbody>
              {data.players.map((player) => (
                <tr key={player.element} className="border-t border-divider">
                  <td className="py-1.5">
                    <span className="inline-flex flex-wrap items-center
                                     gap-1.5">
                      <PlayerName code={player.code} name={player.name}
                                  pos={player.position} />
                      {player.multiplier > 1 && ' (C)'}
                      {player.projected_out && (
                        <Badge variant="negative"
                               title="His matches are over and he did not
                                      play, so FPL will substitute him.">
                          auto-sub out
                        </Badge>
                      )}
                      {player.projected_in && (
                        <Badge variant="positive"
                               title="Projected to come on for a starter whose
                                      matches are over.">
                          {`auto-sub in · ${player.sub_reason ?? ''}`}
                        </Badge>
                      )}
                    </span>
                  </td>
                  <td className="num py-1.5 text-right text-text">
                    {player.points}
                  </td>
                  <td className={`num py-1.5 text-right ${
                    player.provisional_bonus > 0
                      ? 'text-sage' : 'text-text-faint'}`}>
                    {player.provisional_bonus > 0
                      ? `+${player.provisional_bonus}` : '–'}
                  </td>
                  <td className="num py-1.5 text-right text-text-secondary">
                    {player.minutes}
                  </td>
                  <td className="num py-1.5 text-right text-text-secondary">
                    {player.remaining_ep == null
                      ? '–' : fmtNum(player.remaining_ep, 1)}
                  </td>
                  <td className="py-1.5 text-text-muted">{player.status}</td>
                  <td className="num py-1.5 text-right text-text-secondary">
                    {player.tier_eo == null ? '–'
                      : `${player.tier_eo}% ±${player.tier_eo_se ?? 0}`}
                  </td>
                  <td className="num py-1.5 text-right text-text-muted">
                    {player.selected_by_percent == null ? '–'
                      : `${player.selected_by_percent}%`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      {(data.safety?.length ?? 0) > 0 && (
        <div className="mb-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {data.safety?.map((place) => (
              <div key={`${place.role}-${place.entry}`}
                   className="rounded-card border border-border bg-card px-4
                              py-3">
                <p className="label">{ROLE_LABEL[place.role]}</p>
                <p className="text-text">{place.name}</p>
                <p className={`num ${place.margin >= 0
                  ? 'text-rust' : 'text-sage'}`}>
                  {place.margin >= 0
                    ? `${place.margin} ahead · need +${place.need}`
                    : `${-place.margin} clear`}
                </p>
              </div>
            ))}
          </div>
          <p className="mt-2 text-text-muted">
            League places only. Overall rank needs the whole field's live
            scores, which no public endpoint gives.
          </p>
        </div>
      )}
      <Card title="League, live">
        <DataTable
          columns={TABLE_COLUMNS}
          rows={data.table}
          rowKey={(r) => r.entry}
          rowLabel={(r) => r.name}
        />
      </Card>
    </>
  )
}
