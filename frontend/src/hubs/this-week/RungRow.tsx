import { Fragment } from 'react'
import {
  Bar, Chip, PlayerName, TONE_CLASS, TONE_TINT_CLASS, TR_CLASS,
  TR_EXPANDED_CLASS, TR_SELECTED_CLASS, fmtNum, tdClass, toneOf,
} from '../../kit'
import type { LadderRung, PlayerRef } from '../../types'

/**
 * One rung of the transfer ladder, and the panel it opens.
 *
 * Cut out of `LadderCard.tsx` in v18f §2.1 with the helpers only the row and
 * its panel used: the card around it is the ladder's controls, its notes and
 * its rebuild, and the row is the ladder itself.
 */

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

export interface RungRowProps {
  rung: LadderRung
  /** The rung the vs-bank column is measured against, which is a rung of the
   *  same ladder and not a number: a payload with no bank rung has nothing to
   *  compare against and the column says so. */
  bank: LadderRung | undefined
  /** The rung this one repeats, when `same_as` names one — passed rather than
   *  looked up, because only the card holds the whole ladder. */
  below: LadderRung | undefined
  /** Gameweeks in the horizon, for the cost cell's sentence. */
  weeks: number
  open: boolean
  onToggle: () => void
  isCap: boolean
  /** Past the cap: still drawn, so the reader can see what the cap costs. */
  beyond: boolean
  recommended: boolean
  chosen: boolean
}

export default function RungRow({
  rung: r, bank, below, weeks, open, onToggle, isCap, beyond, recommended,
  chosen,
}: RungRowProps) {
  const vsBank = (r.mean_pts !== null && r.mean_pts !== undefined
    && bank?.mean_pts !== null && bank?.mean_pts !== undefined)
    ? r.mean_pts - bank.mean_pts : null
  const label = r.label
  // Lifted out of the cell only to keep the line under a hundred; the string
  // it builds is the one the card built.
  const vsBankClass = vsBank === null || r.key === 'bank'
    ? '' : TONE_TINT_CLASS[toneOf(vsBank)]
  const rowClass = [
    'cursor-pointer', TR_CLASS,
    isCap ? TR_SELECTED_CLASS : '',
    beyond ? 'text-text-faint' : 'text-text',
  ].join(' ')
  return (
    <Fragment>
      <tr
        data-cap={isCap ? 'true' : undefined}
        title={beyond ? 'beyond your cap' : undefined}
        className={rowClass}
        onClick={onToggle}
      >
        <td className={tdClass()}>
          <span className="inline-flex items-center gap-1.5">
            {label}
            {recommended && <Chip>recommended</Chip>}
            {chosen && <Chip tone="up">chosen</Chip>}
          </span>
        </td>
        {r.same_as
          ? (
            <td className={`${tdClass()} text-text-muted`} colSpan={7}>
              solver would not spend it — same as{' '}
              {below ? below.label : r.same_as}
            </td>
            )
          : (
            <>
              <td className={tdClass()}>{movesText(r)}</td>
              <td className={tdClass(true)}><RungCost rung={r} weeks={weeks} /></td>
              <td className={tdClass(true)}>{fmtNum(r.week_pts)}</td>
              <td className={tdClass(true)}>{fmtNum(r.mean_pts)}</td>
              <td className={`${tdClass(true)} ${vsBankClass}`}>
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
      {open && !r.same_as && (
        <tr className={TR_EXPANDED_CLASS}>
          <td className="px-2.5 py-3" colSpan={8}>
            <Expanded rung={r} weeks={weeks} />
          </td>
        </tr>
      )}
    </Fragment>
  )
}
