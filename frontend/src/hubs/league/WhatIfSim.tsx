import { useEffect, useState } from 'react'
import { apiPost } from '../../api/client'
import {
  Card, Chip, EmptyState, Loading, TABLE_CLASS, THEAD_CLASS, TR_CLASS, fmtPct,
  tdClass, thClass,
} from '../../kit'
import type {
  LeagueWhatIfEvent, LeagueWhatIfRequest, LeagueWhatIfResult,
} from '../../types'

export interface WhatIfSquadPlayer {
  code: number
  name: string
  position: string
}

export interface WhatIfRival {
  entry: number
  name: string
}

export interface WhatIfSimProps {
  squad: WhatIfSquadPlayer[]
  rivals: WhatIfRival[]
}

const EVENTS: LeagueWhatIfEvent[] = ['haul', 'score', 'blank']

/**
 * "What would that week do to my title odds?"
 *
 * Deliberately not the squad What-If Lab. That one re-solves the MILP under
 * constraints and answers "what should I do"; this one pins events into the
 * coming gameweek and answers "what would happen" — no transfer is proposed
 * and no solve is run. Keeping them apart is spec D5.
 *
 * Nothing is requested until something is pinned: an empty panel and the
 * league card would otherwise ask the same question twice on every page load.
 */
export default function WhatIfSim({ squad, rivals }: WhatIfSimProps) {
  const [pins, setPins] = useState<Record<number, LeagueWhatIfEvent>>({})
  const [captain, setCaptain] = useState<number | null>(null)
  const [rivalBlank, setRivalBlank] = useState<number | null>(null)
  const [result, setResult] = useState<LeagueWhatIfResult | null>(null)
  const [failed, setFailed] = useState(false)
  const [busy, setBusy] = useState(false)

  const empty = Object.keys(pins).length === 0 && captain === null
    && rivalBlank === null

  useEffect(() => {
    if (empty) { setResult(null); setFailed(false); return }
    const body: LeagueWhatIfRequest = {
      pins: Object.entries(pins).map(([code, event]) => (
        { code: Number(code), event })),
      captain_override: captain,
      rival_captain_blanks: rivalBlank,
    }
    let cancelled = false
    setBusy(true)
    apiPost<LeagueWhatIfResult>('/api/league/whatif', body)
      .then((out) => { if (!cancelled) { setResult(out); setFailed(false) } })
      .catch(() => { if (!cancelled) { setResult(null); setFailed(true) } })
      .finally(() => { if (!cancelled) setBusy(false) })
    return () => { cancelled = true }
  }, [pins, captain, rivalBlank, empty])

  if (squad.length === 0) {
    return (
      <EmptyState
        title="No squad to play with"
        detail="The league what-if prices events against your saved squad, so
                it needs one. Come back once there is one banked."
        action="Run advise"
      />
    )
  }

  const toggle = (code: number, event: LeagueWhatIfEvent) => {
    setPins((prev) => {
      const next = { ...prev }
      if (next[code] === event) delete next[code]
      else next[code] = event
      return next
    })
  }

  return (
    <>
      <Card title="Pin an event" className="mb-4">
        <div className="overflow-x-auto">
        <table className={TABLE_CLASS}>
          <thead className={THEAD_CLASS}>
            <tr>
              <th className={thClass()}>Player</th>
              {EVENTS.map((e) => (
                <th key={e} className={`${thClass(true)} capitalize`}>{e}</th>
              ))}
              <th className={thClass(true)}>Captain</th>
            </tr>
          </thead>
          <tbody>
            {squad.map((player) => (
              <tr key={player.code} className={TR_CLASS}>
                <td className={`${tdClass()} text-text-secondary`}>
                  {player.name}
                </td>
                {EVENTS.map((event) => (
                  <td key={event} className={`${tdClass()} text-right`}>
                    <button
                      type="button"
                      data-testid={`pin-${player.code}-${event}`}
                      aria-pressed={pins[player.code] === event}
                      onClick={() => toggle(player.code, event)}
                      className={`px-2 py-0.5 text-xs ${
                        pins[player.code] === event
                          ? 'text-text underline' : 'text-text-muted'}`}
                    >
                      {event}
                    </button>
                  </td>
                ))}
                <td className={`${tdClass()} text-right`}>
                  <button
                    type="button"
                    data-testid={`captain-${player.code}`}
                    aria-pressed={captain === player.code}
                    onClick={() => setCaptain(
                      captain === player.code ? null : player.code)}
                    className={`px-2 py-0.5 text-xs ${
                      captain === player.code
                        ? 'text-text underline' : 'text-text-muted'}`}
                  >
                    (C)
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
        {rivals.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="label">Rival captain blanks</span>
            {rivals.map((rival) => (
              <button
                key={rival.entry}
                type="button"
                data-testid={`rival-blank-${rival.entry}`}
                aria-pressed={rivalBlank === rival.entry}
                onClick={() => setRivalBlank(
                  rivalBlank === rival.entry ? null : rival.entry)}
                className={`px-2 py-0.5 text-xs ${
                  rivalBlank === rival.entry
                    ? 'text-text underline' : 'text-text-muted'}`}
              >
                {rival.name}
              </button>
            ))}
          </div>
        )}
        <div className="mt-3">
          <button type="button" className="text-xs text-text-muted underline"
                  onClick={() => {
                    setPins({}); setCaptain(null); setRivalBlank(null)
                  }}>
            Clear
          </button>
        </div>
      </Card>

      {empty && (
        <Card>
          <p className="text-text-muted">
            Pick an event above — a haul, a blank, a different armband — and
            the league is re-simulated with it pinned into this gameweek.
          </p>
        </Card>
      )}
      {!empty && failed && (
        <Card>
          <p className="text-text-muted">
            The simulation could not be run. Untick something and try again,
            or check the server.
          </p>
        </Card>
      )}
      {!empty && busy && !result && <Loading />}
      {!empty && result && (
        <Card title="If that happened">
          <div className="mb-3 flex items-baseline gap-3">
            {/* Whole percentage points, and whole places to one decimal.
                At n = 2,000 the Monte Carlo standard error on a probability
                near 0.5 is about 0.9pp; printing a tenth of a point would
                be printing the seed. ``fmtPct`` below rounds to whole
                percent for the same reason. */}
            <span className="tn text-[22px] font-semibold text-text"
                  data-testid="delta-p-win">
              {`${result.delta_p_win >= 0 ? '+' : ''}${
                Math.round(result.delta_p_win * 100)} pp`}
            </span>
            <span className="text-text-muted">
              {`title odds ${fmtPct(result.baseline_p_win)} → `}
              {fmtPct(result.p_win)}
              {`, expected finish ${result.baseline_exp_finish.toFixed(1)} → `}
              {result.exp_finish.toFixed(1)}
            </span>
          </div>
          {result.unknown_codes.length > 0 && (
            <p className="mb-2 text-text-muted">
              {`Not in this week's squad data, so ignored: ${
                result.unknown_codes.join(', ')}.`}
            </p>
          )}
          <div className="overflow-x-auto">
          <table className={TABLE_CLASS}>
            <thead className={THEAD_CLASS}>
              <tr>
                <th className={thClass()}>Team</th>
                <th className={thClass(true)}>Total</th>
                <th className={thClass(true)}>P(win)</th>
              </tr>
            </thead>
            <tbody>
              {result.table.map((row) => (
                <tr key={row.entry} data-testid={`whatif-row-${row.entry}`}
                    className={TR_CLASS}>
                  <td className={`${tdClass()} text-text-secondary`}>
                    {row.name}
                    {/* Chip takes no className here, so the gap is a span. */}
                    {row.is_you && (
                      <span className="ml-2"><Chip>you</Chip></span>
                    )}
                  </td>
                  <td className={`${tdClass(true)} text-text-muted`}>
                    {row.total}
                  </td>
                  <td className={`${tdClass(true)} text-text`}>
                    {row.p_win === null ? '—' : fmtPct(row.p_win)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </Card>
      )}
    </>
  )
}
