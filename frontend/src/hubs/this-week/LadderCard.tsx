import { Fragment, useCallback, useEffect, useState } from 'react'
import { apiPost, errorText } from '../../api/client'
import { usePageData } from '../../api/pageData'
import { useJob } from '../../api/useJob'
import {
  Bar, Button, Callout, Card, Chip, INPUT_CLASS, PlayerName, Skeleton,
  TABLE_CLASS, THEAD_CLASS, TONE_CLASS, TONE_TINT_CLASS, TR_CLASS,
  TR_EXPANDED_CLASS, TR_SELECTED_CLASS, fmtNum, tdClass, thClass, toneOf,
} from '../../kit'
import type {
  LadderPayload, LadderRung, PlayerRef, SettingRow, SettingsPanel,
} from '../../types'
import { capText } from './ladderText'

const SETTING_KEYS = ['max_hits', 'max_transfers', 'hit_bar'] as const
type SettingKeyName = typeof SETTING_KEYS[number]

/** One select over a settings row.
 *
 *  The options, their words and the saved value are the server's (v17e
 *  §2.6): a hand-edited `max_hits = 5` arrives as an option of its own, so
 *  the card never has to guess what is legal and never renders blank. */
function SettingSelect({ row, disabled, onChange }: {
  row: SettingRow
  disabled: boolean
  onChange: (value: number) => void
}) {
  return (
    <label className="flex items-center gap-2">
      <span className="label">{row.label}</span>
      <select
        aria-label={row.label}
        value={String(row.value)}
        disabled={disabled}
        className={INPUT_CLASS}
        onChange={(e) => onChange(Number(e.target.value))}
      >
        {row.options.map((o) => (
          <option key={String(o.value)} value={String(o.value)}>{o.label}</option>
        ))}
      </select>
    </label>
  )
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

export default function LadderCard() {
  const ladder = usePageData<LadderPayload>('/api/ladder')
  const settings = usePageData<SettingsPanel>('/api/settings')
  const [open, setOpen] = useState<string | null>(null)
  // The write's own failure, which is not the read's: a rejected POST must
  // say so even though the ladder on screen is still the one the server
  // banked.
  const [saveFailed, setSaveFailed] = useState<string | null>(null)
  const job = useJob({ path: '/api/ladder', slot: 'ladder' })

  const data = ladder.data
  const failed = saveFailed ?? ladder.error
  // Two slots, not one (v17e §2.6). `load`'s success path cleared `failed`,
  // so a shared slot lost the settings failure whenever the ladder resolved
  // second — which is the ordering that happens whenever /api/settings is the
  // faster of the two to fail. v17h §2 keeps them apart by construction: each
  // call site of the cache holds its own error.
  //
  // A 200 with no rows is the panel's way of saying config.toml is missing or
  // unreadable, and the reason is in `overlay_error` (v17e §2.6): read from
  // `rows` alone the card would show no selects and no reason at all.
  const rowsFailed = settings.error ?? settings.data?.overlay_error ?? null
  // The selects are these rows (v17e §2.6). A failure leaves the ladder
  // table standing with no selects and the reason in the card's callout:
  // the ladder is the card, the selects are only its controls.
  //
  // Selected and ordered by SETTING_KEYS, so a reordered whitelist
  // cannot reorder the card's controls.
  const panel = settings.data
  const rows: SettingRow[] = panel === null ? [] : SETTING_KEYS
    .map((key) => panel.rows.find((r) => r.key === key))
    .filter((r): r is SettingRow => r !== undefined)

  const rebuild = useCallback(() => {
    setOpen(null)
    job.start()
  }, [job])

  // A finished rebuild is read back from the banked payload rather than the
  // job record, so the card and the next page load agree byte for byte.
  const reloadLadder = ladder.reload
  const reloadRows = settings.reload
  useEffect(() => {
    if (job.status === 'done') { reloadLadder(); reloadRows() }
  }, [job.status, reloadLadder, reloadRows])

  const setSetting = async (key: SettingKeyName, value: number) => {
    setSaveFailed(null)
    try {
      await apiPost('/api/settings', { key, value })
    } catch (e) {
      setSaveFailed(errorText(e))
      return
    }
    rebuild()
  }

  const busy = job.status === 'queued' || job.status === 'running'
  const rungs = data?.rungs ?? []
  const weeks = data?.gws.length ?? 0
  const bank = rungs.find((r) => r.key === 'bank')
  const capIndex = rungs.findIndex((r) => r.key === data?.cap_rung)
  const requested = rungs.find((r) => r.key === data?.cap_rung_requested)
  const resolved = rungs.find((r) => r.key === data?.cap_rung)
  const requestedNote = (data && data.cap_rung_requested !== null
    && data.cap_rung_requested !== data.cap_rung)
    ? `your cap of ${requested?.label ?? data.cap_rung_requested}: the solver `
      + `would not spend it \u2014 same as `
      + `${resolved?.label ?? data.cap_rung ?? '\u2014'}`
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
        {rows.map((row) => (
          <SettingSelect
            key={row.key}
            row={row}
            disabled={busy || !data?.gw}
            onChange={(value) => setSetting(row.key as SettingKeyName, value)}
          />
        ))}
      </div>
      {failed && <Callout tone="error" className="mb-3">{failed}</Callout>}
      {rowsFailed && (
        <Callout tone="error" className="mb-3">{rowsFailed}</Callout>
      )}
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
                const label = r.label
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
                            {below ? below.label : r.same_as}
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
              {s.line}
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
