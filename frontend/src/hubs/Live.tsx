import { useCallback, useEffect, useState } from 'react'
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip,
  XAxis, YAxis,
} from 'recharts'
import { apiGet } from '../api/client'
import {
  type Column, Callout, Card, Chip, DataTable, EmptyState, ExplainModal,
  Loading, PageHeader, PlayerCard, SERIES_COLOURS, Stat, TABLE_CLASS,
  THEAD_CLASS, TR_CLASS, fmtNum, tdClass, thClass,
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
  // Season-consistent with Projected beside it: `race` off the wire is this
  // gameweek only, so the pre-gameweek total is added back before it is shown.
  // A column that read 67.5 next to a 172 would be measuring a different
  // thing under the same heading.
  { key: 'race', header: 'Race', numeric: true,
    value: (r) => (r.race == null ? '–' : fmtNum(r.pre_total + r.race, 1)) },
  { key: 'delta', header: 'Move', value: (r) => arrow(r.delta) },
]

export default function Live() {
  const [data, setData] = useState<LiveState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [active, setActive] = useState(true)
  const [auto, setAuto] = useState(true)
  // PlayerCard has no modal inside it (that was PlayerName's bargain), so the
  // host owns one: `onSelect` names a code and the page decides what that
  // means.
  const [explain, setExplain] = useState<number | null>(null)

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
          <Callout className="mb-3">{data.race_notice}</Callout>
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
                  background: 'var(--color-raised)',
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
              {/* You are the first series, so you take the brightest of the
                  four greys and the heavier stroke (plan R6). */}
              <Line type="monotone" dataKey="you" name="You" dot={false}
                    strokeWidth={2.5} stroke={SERIES_COLOURS[0]} />
              <Line type="monotone" dataKey="rival"
                    name={data.rival_name ?? 'Top rival'} dot={false}
                    strokeWidth={1.5} stroke={SERIES_COLOURS[1]} />
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
          <Callout className="mb-3">{data.notice}</Callout>
        )}
        <div className="overflow-x-auto">
          <table className={TABLE_CLASS}>
            <thead className={THEAD_CLASS}>
              <tr>
                <th className={thClass()}>Player</th>
                <th className={thClass(true)}>Pts</th>
                <th className={thClass(true)}>Bonus</th>
                <th className={thClass(true)}>Mins</th>
                <th className={thClass(true)}>Left</th>
                <th className={thClass()}>Status</th>
                <th className={thClass(true)}>Top 10k EO</th>
                <th className={thClass(true)}>Owned</th>
              </tr>
            </thead>
            <tbody>
              {data.players.map((player) => (
                <tr key={player.element} className={TR_CLASS}>
                  <td className={tdClass()}>
                    <span className="inline-flex flex-wrap items-center
                                     gap-1.5">
                      <PlayerCard
                        size="chip"
                        code={player.code}
                        name={player.name}
                        position={player.position}
                        // /api/live carries no team field and this cycle adds
                        // no server code (plan A4): the bundled plain shirt is
                        // the honest answer, not a guessed crest.
                        teamShort={null}
                        teamCode={null}
                        // What the model still expects from him, which is null
                        // once his matches are over — an em dash, not a zero.
                        ep={player.remaining_ep ?? null}
                        onSelect={setExplain}
                      />
                      {player.multiplier > 1 && ' (C)'}
                      {/* Out of your XI and into it: a direction relative to
                          the team the reader is watching (rule 1). */}
                      {player.projected_out && (
                        <Chip
                          tone="down"
                          title={'His matches are over and he did not play, '
                                 + 'so FPL will substitute him.'}>
                          auto-sub out
                        </Chip>
                      )}
                      {player.projected_in && (
                        <Chip
                          tone="up"
                          title={'Projected to come on for a starter whose '
                                 + 'matches are over.'}>
                          {`auto-sub in · ${player.sub_reason ?? ''}`}
                        </Chip>
                      )}
                    </span>
                  </td>
                  <td className={`${tdClass(true)} text-text`}>
                    {player.points}
                  </td>
                  <td className={`${tdClass(true)} ${
                    player.provisional_bonus > 0
                      ? 'text-up' : 'text-text-faint'}`}>
                    {player.provisional_bonus > 0
                      ? `+${player.provisional_bonus}` : '–'}
                  </td>
                  <td className={`${tdClass(true)} text-text-secondary`}>
                    {player.minutes}
                  </td>
                  <td className={`${tdClass(true)} text-text-secondary`}>
                    {player.remaining_ep == null
                      ? '–' : fmtNum(player.remaining_ep, 1)}
                  </td>
                  <td className={`${tdClass()} text-text-muted`}>{player.status}</td>
                  <td className={`${tdClass(true)} text-text-secondary`}>
                    {player.tier_eo == null ? '–'
                      : `${player.tier_eo}% ±${player.tier_eo_se ?? 0}`}
                  </td>
                  <td className={`${tdClass(true)} text-text-muted`}>
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
                   className="border-l-2 border-border pl-3">
                <p className="label">{ROLE_LABEL[place.role]}</p>
                <p className="text-text">{place.name}</p>
                <p className={`tn ${place.margin >= 0
                  ? 'text-down' : 'text-up'}`}>
                  {place.margin >= 0
                    ? `${place.margin} ahead · need +${place.need} beyond `
                      + 'your current projection'
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
      {explain !== null && (
        <ExplainModal code={explain} onClose={() => setExplain(null)} />
      )}
    </>
  )
}
