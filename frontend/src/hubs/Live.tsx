import { useCallback, useEffect, useState } from 'react'
import { apiGet } from '../api/client'
import {
  type Column, Card, DataTable, EmptyState, Loading, PageHeader, PlayerName,
  Stat, fmtNum,
} from '../kit'
import type { LiveState, LiveTableRow } from '../types'

const POLL_MS = 60000

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
        <Stat label="Matches in play" value={fmtNum(data.matches_in_play, 0)} />
      </div>
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
                <th className="label pb-1 text-left">Status</th>
                <th className="label pb-1 text-right">Top 10k EO</th>
                <th className="label pb-1 text-right">Owned</th>
              </tr>
            </thead>
            <tbody>
              {data.players.map((player) => (
                <tr key={player.element} className="border-t border-divider">
                  <td className="py-1.5">
                    <span className="inline-flex items-center gap-1.5">
                      <PlayerName code={player.code} name={player.name}
                                  pos={player.position} />
                      {player.multiplier > 1 && ' (C)'}
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
