import { Fragment, useCallback, useEffect, useState } from 'react'
import { apiGet, apiPost, errorText } from '../../api/client'
import { useJob } from '../../api/useJob'
import {
  Bar, Button, Callout, Card, Chip, INPUT_CLASS, PlayerName, Skeleton,
  TABLE_CLASS, THEAD_CLASS, TONE_CLASS, TONE_TINT_CLASS, TR_CLASS,
  TR_EXPANDED_CLASS, TR_SELECTED_CLASS, fmtNum, tdClass, thClass, toneOf,
} from '../../kit'
import type {
  LadderPayload, LadderRung, LadderStep, PlayerRef,
} from '../../types'

/** `[optimizer]` value meaning "no cap" — `gaffer.config.NO_CAP`. */
export const NO_CAP = 15

/** The bars the select offers; the saved value is added by `withCurrent`
 *  when it is not one of them (a hand-edited 0.62 must not render blank). */
export const HIT_BARS = [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.9, 0.95]

/** "1 free transfer · cap 2 hits" — the heading, and MovesCard's line. */
export function capText(p: LadderPayload): string {
  const ft = p.free_transfers ?? 0
  const bits = [`${ft} free transfer${ft === 1 ? '' : 's'}`]
  const hits = p.cap.max_hits
  bits.push(hits === null || hits === undefined
    ? 'hits uncapped'
    : `cap ${hits} hit${hits === 1 ? '' : 's'}`)
  const moves = p.cap.max_transfers
  if (moves === 0) bits.push('bank')
  else if (moves !== null && moves !== undefined) {
    bits.push(`max ${moves} transfer${moves === 1 ? '' : 's'}`)
  }
  return bits.join(' · ')
}

/** The row's name, taken from the *key* rather than from `hits`.
 *
 *  A `same_as` rung repeats the plan below it, so it carries that plan's hit
 *  count: `hits2` deferring to `hits1` has `hits === 1`. Labelling off
 *  `r.hits` would print two rows called "1 hit" and lose the rung the reader
 *  is actually being told about. The key is the rung's identity. */
function rungLabel(r: LadderRung): string {
  if (r.key === 'bank') return 'Bank'
  if (r.key === 'open') return 'No cap'
  const m = /^hits(\d+)$/.exec(r.key)
  const n = m ? Number(m[1]) : r.hits
  if (n === 0) return 'No hits'
  return `${n} hit${n === 1 ? '' : 's'}`
}

/** The offered options, plus the current value when it is not among them.
 *
 *  Both caps accept any whole number the config does, and the ladder has
 *  rungs for only a few of them: a `max_hits` of 5 saved by hand is a legal
 *  setting this select does not offer. Without a row for it the select
 *  renders blank, which reads as "no cap set" and makes the next change a
 *  move off a value the user was never shown. */
export function withCurrent(options: number[], value: number): number[] {
  return options.includes(value) ? options : [...options, value].sort(
    (a, b) => a - b)
}

/** A signed hit bill: `−4`, or `0` when nothing was spent. */
function costText(n: number): string {
  return n > 0 ? `\u2212${n}` : '0'
}

/** The cost cell.
 *
 *  `max_hits` is a *per-week* cap, so a rung that takes one hit takes it in
 *  every horizon week: the decision on the table costs 4, the plan behind it
 *  costs 12. Printing only one of those misprices the row, so both go in
 *  whenever they differ — the horizon figure in `down`, because it is the
 *  bill the reader is being warned about (spec §6.3). */
function RungCost({ rung, weeks }: { rung: LadderRung; weeks: number }) {
  if (rung.horizon_cost === rung.cost) return <>{costText(rung.cost)}</>
  return (
    <>
      <span>{costText(rung.cost)} now</span>
      <span className="text-text-muted"> · </span>
      <span className="text-down">
        {`${costText(rung.horizon_cost)} over ${weeks} GW${weeks === 1 ? '' : 's'}`}
      </span>
    </>
  )
}

function pct(v: number | null | undefined): string {
  return v === null || v === undefined ? '—' : `${Math.round(v * 100)}%`
}

/** "Bank → No hits: taken, 79% — expected points alone". */
export function stepText(step: LadderStep, rungs: LadderRung[]): string {
  const label = (key: string) => {
    const r = rungs.find((x) => x.key === key)
    return r ? rungLabel(r) : key
  }
  return `${label(step.below)} → ${label(step.above)}: `
    + `${step.taken ? 'taken' : 'refused'}, ${pct(step.share)} — ${step.reason}`
}

function movesText(r: LadderRung): string {
  const first = r.plan_by_gw[0]
  if (!first || first.buys.length === 0) return 'no moves'
  return first.buys.map((b) => b.name).join(', ')
}

function names(players: PlayerRef[]): string {
  return players.map((p) => p.name).join(', ')
}

function Players({ players }: { players: PlayerRef[] }) {
  if (players.length === 0) return <span className="text-text-muted">—</span>
  return (
    <ul className="flex flex-col gap-0.5">
      {players.map((p) => (
        <li key={p.code}>
          <PlayerName code={p.code} name={p.name} pos={p.position} />
        </li>
      ))}
    </ul>
  )
}

function Expanded({ rung, weeks }: { rung: LadderRung; weeks: number }) {
  const vb = rung.vs_below
  const first = rung.plan_by_gw[0]
  return (
    <div className="grid gap-4 py-2 sm:grid-cols-2">
      <div>
        <p className="label mb-1">This rung&apos;s squad</p>
        {rung.plan_by_gw.map((w) => (
          <div key={w.gw} className="mb-2">
            <p className="text-text-secondary">
              GW{w.gw}
              {w.hits > 0 && (
                <span className="text-down">
                  {' '}· {w.hits} hit{w.hits === 1 ? '' : 's'}
                </span>
              )}
            </p>
            <div className="grid grid-cols-2 gap-2">
              <div><span className="label">In</span><Players players={w.buys} /></div>
              <div><span className="label">Out</span><Players players={w.sells} /></div>
            </div>
          </div>
        ))}
        {first && (
          <div>
            <p className="label">Starting XI (captain marked)</p>
            <ul className="flex flex-wrap gap-x-2">
              {first.xi.map((p) => (
                <li key={p.code} className="text-text">
                  {/* The name is its own element so it stays findable as the
                      name: "Back (C)" is one string to a text query. */}
                  <span>{p.name}</span>
                  {p.code === first.captain.code && <span> (C)</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      <div>
        <p className="label mb-1">What the last hit bought</p>
        {vb === null || vb === undefined
          ? <p className="text-text-muted">Nothing to compare against.</p>
          : (
            <p className="text-text">
              {vb.extra_buys.length > 0 && `+ ${names(vb.extra_buys)}`}
              {vb.extra_sells.length > 0 && ` for ${names(vb.extra_sells)}`}
              {vb.dropped_buys.length > 0 && ` (drops ${names(vb.dropped_buys)})`}
              {' '}
              <span className={TONE_CLASS[toneOf(vb.delta_mean_pts)]}>
                ({vb.delta_mean_pts >= 0 ? '+' : '−'}
                {fmtNum(Math.abs(vb.delta_mean_pts), 1)} xPts over {weeks} GWs,
                {' '}{costText(vb.delta_cost)})
              </span>
              {/* The delta is net of the whole horizon's hits; the first
                  week's share of that bill is the part being decided now. */}
              {vb.delta_cost_now !== vb.delta_cost && (
                <span className="text-text-muted">
                  {' '}({costText(vb.delta_cost_now)} of it now)
                </span>
              )}
            </p>
            )}
      </div>
    </div>
  )
}

export interface LadderCardProps {
  /** Called with every payload this card loads, so a parent (This Week) can
   *  print the cap line on the moves card without a second request. */
  onLoaded?: (payload: LadderPayload) => void
}

export default function LadderCard({ onLoaded }: LadderCardProps = {}) {
  const [data, setData] = useState<LadderPayload | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const job = useJob('ladder')

  const load = useCallback(() => {
    apiGet<LadderPayload>('/api/ladder')
      .then((payload) => {
        setFailed(null)
        setData(payload)
        onLoaded?.(payload)
      })
      .catch((e) => { setFailed(errorText(e)); setData(null) })
  }, [onLoaded])
  useEffect(() => { load() }, [load])

  const rebuild = useCallback(() => {
    setOpen(null)
    job.start('/api/ladder')
  }, [job])

  // A finished rebuild is read back from the banked payload rather than the
  // job record, so the card and the next page load agree byte for byte.
  useEffect(() => {
    if (job.status === 'done') load()
  }, [job.status, load])

  const setSetting = async (
    key: 'max_hits' | 'max_transfers' | 'hit_bar', value: number,
  ) => {
    try {
      await apiPost('/api/settings', { key, value })
    } catch (e) {
      setFailed(errorText(e))
      return
    }
    rebuild()
  }

  const busy = job.status === 'queued' || job.status === 'running'
  const rungs = data?.rungs ?? []
  const weeks = data?.gws.length ?? 0
  const bank = rungs.find((r) => r.key === 'bank')
  const capIndex = rungs.findIndex((r) => r.key === data?.cap_rung)
  const hitsValue = data?.cap.max_hits ?? NO_CAP
  const movesValue = data?.cap.max_transfers ?? NO_CAP
  const requested = rungs.find((r) => r.key === data?.cap_rung_requested)
  const resolved = rungs.find((r) => r.key === data?.cap_rung)
  const requestedNote = (data && data.cap_rung_requested !== null
    && data.cap_rung_requested !== data.cap_rung)
    ? `your cap of ${(requested ? rungLabel(requested)
        : data.cap_rung_requested).toLowerCase()}: the solver would not `
      + `spend it \u2014 same as `
      + `${(resolved ? rungLabel(resolved) : data.cap_rung ?? '\u2014')
          .toLowerCase()}`
    : null

  return (
    <Card
      title="Transfer ladder"
      className="mb-4"
      action={(
        <Button onClick={rebuild} disabled={busy || !data?.gw}>
          {busy ? 'Rebuilding…' : 'Rebuild'}
        </Button>
      )}
    >
      {data && data.gw !== null && (
        <p className="mb-2 text-text-secondary">
          {capText(data)}
          {/* The saved cap can name a rung the solver refused to spend; the
              highlight then sits on the rung it resolved to, and the reason
              is said here rather than left as a silent jump. */}
          {requestedNote && (
            <span className="text-text-muted">{' · '}{requestedNote}</span>
          )}
        </p>
      )}
      <p className="mb-3 text-text-muted">
        Every rung of appetite solved on the same board, then every plan
        scored on the same {data?.n_draws || 200} noise draws — so the rows
        are comparable and the players they share cancel out. Your cap is
        highlighted; the rungs beyond it stay visible so you can see what it
        costs. The walk steps up one rung at a time and stops at the first
        rung that does not clear the bar; the rung it stops on is the advice.
      </p>
      <div className="mb-3 flex flex-wrap gap-3">
        <label className="flex items-center gap-2">
          <span className="label">Max hits</span>
          <select
            aria-label="Max hits"
            value={hitsValue}
            disabled={busy || !data?.gw}
            onChange={(e) => setSetting('max_hits', Number(e.target.value))}
            className={INPUT_CLASS}
          >
            {withCurrent([0, 1, 2, 3], hitsValue).map((n) => (
              n === NO_CAP ? null
                : <option key={n} value={n}>{n}</option>))}
            <option value={NO_CAP}>no cap</option>
          </select>
        </label>
        <label className="flex items-center gap-2">
          <span className="label">Max transfers</span>
          <select
            aria-label="Max transfers"
            value={movesValue}
            disabled={busy || !data?.gw}
            onChange={(e) => setSetting('max_transfers', Number(e.target.value))}
            className={INPUT_CLASS}
          >
            <option value={0}>bank</option>
            {withCurrent([1, 2, 3, 4, 5], movesValue).map((n) => (
              n === 0 || n === NO_CAP ? null
                : <option key={n} value={n}>{n}</option>))}
            <option value={NO_CAP}>no cap</option>
          </select>
        </label>
        <label className="flex items-center gap-2">
          <span className="label">Hit bar</span>
          <select
            aria-label="Hit bar"
            value={String(data?.bar ?? 0.6)}
            disabled={busy || !data?.gw}
            className={INPUT_CLASS}
            onChange={(e) => setSetting('hit_bar', Number(e.target.value))}
          >
            {withCurrent(HIT_BARS, data?.bar ?? 0.6).map((b) => (
              <option key={b} value={String(b)}>{`${Math.round(b * 100)}%`}</option>))}
          </select>
        </label>
      </div>
      {failed && <Callout tone="error" className="mb-3">{failed}</Callout>}
      {job.status === 'error' && (
        <Callout tone="error" className="mb-3">{job.error}</Callout>
      )}
      {busy && (
        <Skeleton bare lines={5}
                  label="Solving every rung and scoring the draws…" />
      )}
      {!busy && data && rungs.length === 0 && (
        <p className="text-text-muted">{data.note ?? 'No ladder yet.'}</p>
      )}
      {!busy && rungs.length > 0 && (
        <div className="overflow-x-auto">
          <table className={TABLE_CLASS}>
            <thead className={THEAD_CLASS}>
              <tr>
                <th className={thClass()}>Rung</th>
                <th className={thClass()}>Moves</th>
                <th className={thClass(true)}>Cost</th>
                <th className={thClass(true)}>GW xPts</th>
                <th className={thClass(true)}>{weeks}-GW xPts</th>
                <th className={thClass(true)}>vs bank</th>
                <th className={thClass()}>P(beats bank)</th>
                <th className={thClass()}>P(best)</th>
              </tr>
            </thead>
            <tbody>
              {rungs.map((r, i) => {
                const isCap = r.key === data?.cap_rung
                const beyond = capIndex >= 0 && i > capIndex
                const vsBank = (r.mean_pts !== null && r.mean_pts !== undefined
                  && bank?.mean_pts !== null && bank?.mean_pts !== undefined)
                  ? r.mean_pts - bank.mean_pts : null
                const label = rungLabel(r)
                const below = rungs.find((x) => x.key === r.same_as)
                const rowClass = [
                  'cursor-pointer', TR_CLASS,
                  isCap ? TR_SELECTED_CLASS : '',
                  beyond ? 'text-text-faint' : 'text-text',
                ].join(' ')
                return (
                  <Fragment key={r.key}>
                    <tr
                      data-cap={isCap ? 'true' : undefined}
                      title={beyond ? 'beyond your cap' : undefined}
                      className={rowClass}
                      onClick={() => setOpen(open === r.key ? null : r.key)}
                    >
                      <td className={tdClass()}>
                        <span className="inline-flex items-center gap-1.5">
                          {label}
                          {r.key === data?.recommended && <Chip>recommended</Chip>}
                          {r.key === data?.chosen && <Chip tone="up">chosen</Chip>}
                        </span>
                      </td>
                      {r.same_as
                        ? (
                          <td className={`${tdClass()} text-text-muted`} colSpan={7}>
                            solver would not spend it — same as{' '}
                            {(below ? rungLabel(below) : r.same_as).toLowerCase()}
                          </td>
                          )
                        : (
                          <>
                            <td className={tdClass()}>{movesText(r)}</td>
                            <td className={tdClass(true)}><RungCost rung={r} weeks={weeks} /></td>
                            <td className={tdClass(true)}>{fmtNum(r.week_pts)}</td>
                            <td className={tdClass(true)}>{fmtNum(r.mean_pts)}</td>
                            <td className={`${tdClass(true)} ${vsBank === null || r.key === 'bank' ? '' : TONE_TINT_CLASS[toneOf(vsBank)]}`}>
                              {vsBank === null || r.key === 'bank' ? '—'
                                : `${vsBank >= 0 ? '+' : '−'}${fmtNum(Math.abs(vsBank), 1)}`}
                            </td>
                            <td className={tdClass()}>
                              <Bar testId="p-beats-bank" fraction={r.p_beats_bank ?? null}
                                   text={pct(r.p_beats_bank)} />
                            </td>
                            <td className={tdClass()}>
                              <Bar testId="p-best" fraction={r.p_best ?? null}
                                   text={pct(r.p_best)} />
                            </td>
                          </>
                          )}
                    </tr>
                    {open === r.key && !r.same_as && (
                      <tr className={TR_EXPANDED_CLASS}>
                        <td className="px-2.5 py-3" colSpan={8}>
                          <Expanded rung={r} weeks={weeks} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      {!busy && (data?.steps ?? []).length > 0 && (
        <ul className="mt-2 flex flex-col gap-0.5 text-text-secondary" data-testid="ladder-steps">
          {data!.steps.map((s) => (
            <li key={`${s.below}-${s.above}`} className={s.taken ? '' : 'text-text-muted'}>
              {stepText(s, rungs)}
            </li>
          ))}
        </ul>
      )}
      {!busy && data?.served_note && (
        <p className="mt-2 text-text-muted" data-testid="ladder-served-note">{data.served_note}</p>
      )}
      {!busy && data?.cap_note && (
        <p className="mt-2 text-text-muted">{data.cap_note}</p>
      )}
      {!busy && data?.recommended_note && (
        <p className="mt-2 text-text-muted">{data.recommended_note}</p>
      )}
      {!busy && (data?.notes ?? []).map((n) => (
        <p key={n} className="mt-2 text-text-muted">{n}</p>
      ))}
      {!busy && rungs.length > 0 && (
        <p className="mt-2 text-text-muted" data-testid="ladder-points-note">
          Points are raw expected XI + captain over the horizon, undecayed and
          untilted, so they can rank the rungs differently from the objective
          the solver optimises.
        </p>
      )}
    </Card>
  )
}
