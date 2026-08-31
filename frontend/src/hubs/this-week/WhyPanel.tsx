import { Fragment, useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import {
  Card, PosBadge, TONE_CLASS, fmtDelta, fmtNum, fmtPct, toneOf,
} from '../../kit'
import type {
  AdviceDiff, ComponentPlayer, ComponentsBreakdown, OverridesPanel,
} from '../../types'

/**
 * Mirrors `artifacts.EP_MOVER_THRESHOLD`, the server-side constant the movers
 * list is already filtered by. Repeated here only to name the number in the
 * sentence — the filtering happens once, on the server.
 */
const EP_MOVER_THRESHOLD = 0.5

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
  // Defaulted rather than indexed straight: the strip is decoration on a page
  // that already has its advice, and a payload banked or served without the
  // field must cost the movers line, never This Week.
  const movers = diff.ep_movers ?? []
  if (movers.length > 0) {
    const named = movers.slice(0, 3).map((m) => (
      `${m.name} ${m.delta >= 0 ? '+' : ''}${m.delta.toFixed(1)}`)).join(', ')
    const n = diff.ep_movers_count ?? movers.length
    bits.push(`${n} player${n === 1 ? '' : 's'} moved `
      + `${EP_MOVER_THRESHOLD} xPts or more in the retrain — ${named}`)
  }
  const delta = diff.expected_pts_delta
  return (
    <div className="mb-4 rounded-card border border-border border-l-2
                    border-l-info bg-card px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="label">Since last run</p>
        <p className="num text-text-faint">
          {diff.available ? diff.previous_at : 'since the last retrain'}
        </p>
      </div>
      <p className="mt-1 text-text-secondary">
        {bits.length === 0 ? 'The same plan.' : `${bits.join('; ')}.`}{' '}
        {/* Both ornaments below only mean anything against a previous run: a
            movers-only strip must not print a delta of 0.0 xPts. */}
        {diff.available && (
          <span className={`num ${TONE_CLASS[toneOf(delta)]}`}>
            {fmtDelta(delta)} xPts
          </span>
        )}
      </p>
    </div>
  )
}

function PlayerRow({ player }: { player: ComponentPlayer }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <tr className="border-t border-divider">
        <td className="py-1.5">
          <button type="button" onClick={() => setOpen(!open)}
                  className="inline-flex items-center gap-1.5 text-text
                             hover:underline">
            <span aria-hidden className="text-text-muted">
              {open ? '▾' : '▸'}
            </span>
            {player.name}
          </button>
        </td>
        <td className="py-1.5"><PosBadge pos={player.position} /></td>
        <td className="py-1.5 text-text-secondary">{player.team_name}</td>
        <td className="num py-1.5 text-right text-text">
          {fmtNum(player.ep)}
        </td>
      </tr>
      {open && player.fixtures.map((fixture, i) => (
        <tr key={`${player.code}-${i}`} className="border-t border-divider">
          <td colSpan={4} className="px-3 py-3">
            <p className="text-text-muted">
              {fixture.home ? 'vs' : 'at'} {fixture.opponent} — plays{' '}
              {fmtPct(fixture.minutes.p_play)}, 60+{' '}
              {fmtPct(fixture.minutes.p60)} · {fmtNum(fixture.ep)} xPts
            </p>
            <table className="mt-2 w-full">
              <tbody>
                {fixture.components.map((c) => (
                  <Fragment key={c.label}>
                    <tr>
                      <td className="py-0.5 text-text-secondary">{c.label}</td>
                      <td className="num py-0.5 text-right text-text">
                        {fmtNum(c.points)}
                      </td>
                    </tr>
                    {/* Penalty duty is already inside Goals — it was folded
                        into e_goals before the terms were assembled — so it
                        annotates that row instead of adding a row, which
                        would stop the column summing to the xPts above. */}
                    {c.label === 'Goals' && fixture.pen_taker !== null
                      && fixture.pen_taker !== undefined && (
                      <tr>
                        <td className="num py-0.5 text-text-faint" colSpan={2}>
                          of which penalty duty{' '}
                          {fixture.pen_taker >= 0 ? '+' : ''}
                          {fixture.pen_taker}
                        </td>
                      </tr>
                    )}
                  </Fragment>
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
  const [pins, setPins] = useState<OverridesPanel | null>(null)

  useEffect(() => {
    if (codes.length === 0) return
    const query = `?codes=${codes.join(',')}`
    apiGet<ComponentsBreakdown>(`/api/components/${gw}${query}`)
      .then(setData).catch(() => setData(null))
    // The gw the page is showing, not whatever the server last wrote: This
    // Week can be asked for an explicit gameweek, and a strip comparing a
    // different week's two runs answers a question nobody asked.
    apiGet<AdviceDiff>(`/api/advice/diff?gw=${gw}`)
      .then(setDiff).catch(() => setDiff(null))
    // The manager's own team news, so the panel that explains the plan can
    // say which parts of it he wrote himself.
    apiGet<OverridesPanel>('/api/overrides').then(setPins).catch(
      () => setPins(null))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gw, codes.join(',')])

  if (!data || data.players.length === 0) return null

  // "Your pins are in this plan" has to be true of every line under it. The
  // store is the manager's whole pin list, including players this week's plan
  // never names, and those belong on the Players page rather than here.
  const shown = (pins?.rows ?? []).filter((row) => codes.includes(row.code))

  return (
    <>
      {/* A10: a first run of the week has no plan to diff and is exactly when
          a retrain happened, so the movers alone are worth the strip. */}
      {diff && ((diff.available && diff.changed)
                || (diff.ep_movers ?? []).length > 0)
        && <DiffStrip diff={diff} />}
      {pins && shown.length > 0 && (
        <div className="mb-4 rounded-card border-l-2 border-info bg-base px-3
                        py-2">
          <p className="label mb-1">Your pins are in this plan</p>
          {shown.map((row) => (
            <p key={row.code} className="text-text-secondary">
              {`You pinned ${row.name} `}
              {row.p_play !== null && `p_play ${fmtNum(row.p_play, 2)}`}
              {row.p_play !== null && row.model_p_play !== null
                && ` — the model had ${fmtNum(row.model_p_play, 2)}`}
              {row.e_min !== null
                && ` · ${fmtNum(row.e_min, 0)} minutes`}
              {row.note && ` — ${row.note}`}
              {!pins.active && ' (not currently applied)'}
            </p>
          ))}
        </div>
      )}
      <Card title="Why this plan" className="mb-4">
        <p className="mb-2 text-text-muted">
          Click a name for the terms that produced his expected points.
        </p>
        <table className="w-full">
          <thead>
            <tr>
              <th className="label pb-1 text-left">Player</th>
              <th className="label pb-1 text-left">Pos</th>
              <th className="label pb-1 text-left">Club</th>
              <th className="label pb-1 text-right">xPts</th>
            </tr>
          </thead>
          <tbody>
            {data.players.map((player) => (
              <PlayerRow key={player.code} player={player} />
            ))}
          </tbody>
        </table>
      </Card>
    </>
  )
}
