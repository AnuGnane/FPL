import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'
import type { AdviceDiff, ComponentPlayer, ComponentsBreakdown } from '../types'

function DiffStrip({ diff }: { diff: AdviceDiff }) {
  const bits: string[] = []
  if (diff.buys_added.length || diff.buys_dropped.length) {
    const inNames = diff.buys_added.map((p) => p.name).join(', ') || 'nobody'
    const outNames = diff.buys_dropped.map((p) => p.name).join(', ')
      || 'nobody'
    bits.push(`buying ${inNames} instead of ${outNames}`)
  }
  if (diff.sells_added.length || diff.sells_dropped.length) {
    const inNames = diff.sells_added.map((p) => p.name).join(', ') || 'nobody'
    const outNames = diff.sells_dropped.map((p) => p.name).join(', ')
      || 'nobody'
    bits.push(`selling ${inNames} instead of ${outNames}`)
  }
  if (diff.captain_to) {
    bits.push(`captain ${diff.captain_from?.name ?? 'none'} → `
      + `${diff.captain_to.name}`)
  }
  if (diff.chip_to) bits.push(`now recommending ${diff.chip_to}`)
  if (diff.chip_from && !diff.chip_to) {
    bits.push(`no longer recommending ${diff.chip_from}`)
  }
  const delta = diff.expected_pts_delta
  return (
    <div className="banner">
      <span>
        <strong>Since last run</strong>{' '}
        <span className="muted">({diff.previous_at})</span>:{' '}
        {bits.length === 0 ? 'the same plan' : bits.join('; ')}.{' '}
        <span className={delta >= 0 ? 'good' : 'bad'}>
          {delta >= 0 ? '+' : ''}{delta} xPts
        </span>
      </span>
    </div>
  )
}

function PlayerRow({ player }: { player: ComponentPlayer }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <tr>
        <td>
          <button className="player-link" onClick={() => setOpen(!open)}>
            {player.name}
          </button>
        </td>
        <td>{player.position}</td>
        <td>{player.team_name}</td>
        <td>{player.ep}</td>
      </tr>
      {open && player.fixtures.map((fixture, i) => (
        <tr key={`${player.code}-${i}`}>
          <td colSpan={4}>
            <p className="muted">
              {fixture.home ? 'vs' : 'at'} {fixture.opponent} — plays{' '}
              {Math.round(fixture.minutes.p_play * 100)}%, 60+{' '}
              {Math.round(fixture.minutes.p60 * 100)}% · {fixture.ep} xPts
            </p>
            <table>
              <tbody>
                {fixture.components.map((c) => (
                  <tr key={c.label}>
                    <td>{c.label}</td>
                    <td>{c.points}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </td>
        </tr>
      ))}
    </>
  )
}

/**
 * Why this plan: the EP decomposition behind every player it names, and what
 * changed since the previous run of the same gameweek.
 *
 * Both halves fail quietly and separately. A missing components parquet hides
 * the whole panel (there is nothing to explain with); a first run of the week
 * hides only the strip, because "no previous run" is not a fault.
 */
export default function WhyPanel({ gw, codes }: { gw: number
                                                  codes: number[] }) {
  const [data, setData] = useState<ComponentsBreakdown | null>(null)
  const [diff, setDiff] = useState<AdviceDiff | null>(null)

  useEffect(() => {
    if (codes.length === 0) return
    const query = `?codes=${codes.join(',')}`
    apiGet<ComponentsBreakdown>(`/api/components/${gw}${query}`)
      .then(setData).catch(() => setData(null))
    apiGet<AdviceDiff>('/api/advice/diff').then(setDiff).catch(() => setDiff(null))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gw, codes.join(',')])

  if (!data || data.players.length === 0) return null

  return (
    <>
      {diff?.available && diff.changed && <DiffStrip diff={diff} />}
      <div className="card">
        <h2>Why this plan</h2>
        <p className="muted">
          Click a name for the terms that produced his expected points.
        </p>
        <table>
          <thead>
            <tr><th>Player</th><th>Pos</th><th>Club</th><th>xPts</th></tr>
          </thead>
          <tbody>
            {data.players.map((player) => (
              <PlayerRow key={player.code} player={player} />
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
