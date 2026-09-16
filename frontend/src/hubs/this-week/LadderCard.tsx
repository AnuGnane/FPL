import { useCallback, useEffect, useState } from 'react'
import { errorText } from '../../api/client'
import { usePageData } from '../../api/pageData'
import { useJob } from '../../api/useJob'
import { useSettingWrite } from '../../api/useSettingWrite'
import {
  Button, Callout, Card, Disclosure, INPUT_CLASS, Skeleton, StackedRows,
  TABLE_CLASS, THEAD_CLASS, thClass, useIsMobile,
} from '../../kit'
import type { LadderPayload, SettingRow, SettingsPanel } from '../../types'
import RungRow, { type RungRowProps, rungStackedRow } from './RungRow'
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

export default function LadderCard() {
  const mobile = useIsMobile()
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

  // The hook clears the panel before the rebuild rather than after it (v17h
  // §5). The selects are drawn from the cached panel, so a cap changed here
  // would otherwise read back as the old one for as long as the rebuild takes
  // — and the Settings tab on the Model hub writes the same file from the
  // other side of the app. A refused write is the card's own callout, not a
  // toast, and it stops the rebuild: the ladder on screen is still the one the
  // server banked.
  const writeSetting = useSettingWrite({
    onError: (e) => setSaveFailed(errorText(e)),
  })

  const setSetting = async (key: SettingKeyName, value: number) => {
    setSaveFailed(null)
    if (!await writeSetting(key, value)) return
    rebuild()
  }

  const busy = job.status === 'queued' || job.status === 'running'
  const rungs = data?.rungs ?? []
  // Narrowed once, here, rather than asserted non-null at the one place the
  // list is mapped: the guard the JSX reads is `steps.length`, so the two
  // have to be the same expression (v18f §2.2).
  const steps = data?.steps ?? []
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

  /** One rung's props, built once (v19c §2.1): the table row and the phone's
   *  stacked row are the same rung said twice, and a prop computed in two
   *  places is how they stop being. */
  const rungProps = (r: typeof rungs[number], i: number): RungRowProps => ({
    rung: r,
    bank,
    below: rungs.find((x) => x.key === r.same_as),
    weeks,
    open: open === r.key,
    onToggle: () => setOpen(open === r.key ? null : r.key),
    isCap: r.key === data?.cap_rung,
    beyond: capIndex >= 0 && i > capIndex,
    recommended: r.key === data?.recommended,
    chosen: r.key === data?.chosen,
  })

  return (
    <Card
      title="Transfer ladder"
      id="ladder"
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
      {/* v19d §2.3: five lines that are worth reading once and are in the
          way on the tenth visit. Open on a first visit, folded after the
          reader folds it. */}
      <Disclosure summary="How to read this" storageKey="ladder-help">
        <p className="mb-3 text-text-muted">
          Every rung of appetite solved on the same board, then every plan
          scored on the same {data?.n_draws || 200} noise draws — so the rows
          are comparable and the players they share cancel out. Your cap is
          highlighted; the rungs beyond it stay visible so you can see what it
          costs. The walk steps up one rung at a time and stops at the first
          rung that does not clear the bar; the rung it stops on is the advice.
        </p>
      </Disclosure>
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
      {/* v19c §2.1: eight columns in a phone-wide scroller put every figure
          out of sight of its heading, and the rung the reader came for is the
          one he has to scroll to reach. Stacked, each rung is a heading line
          and its numbers, and the disclosure is the same open the table's
          toggle owns — so rotating the phone keeps the rung open. */}
      {!busy && rungs.length > 0 && mobile && (
        <StackedRows testId="ladder-stacked"
                     rows={rungs.map((r, i) => rungStackedRow(rungProps(r, i)))} />
      )}
      {!busy && rungs.length > 0 && !mobile && (
        <div className="overflow-x-auto">
          <table className={TABLE_CLASS}>
            <thead className={THEAD_CLASS}>
              <tr>
                <th scope="col" className={thClass()}>Rung</th>
                <th scope="col" className={thClass()}>Moves</th>
                <th scope="col" className={thClass(true)}>Cost</th>
                <th scope="col" className={thClass(true)}>GW xPts</th>
                <th scope="col" className={thClass(true)}>{weeks}-GW xPts</th>
                <th scope="col" className={thClass(true)}>vs bank</th>
                <th scope="col" className={thClass()}>P(beats bank)</th>
                <th scope="col" className={thClass()}>P(best)</th>
              </tr>
            </thead>
            <tbody>
              {rungs.map((r, i) => (
                <RungRow key={r.key} {...rungProps(r, i)} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!busy && steps.length > 0 && (
        <ul className="mt-2 flex flex-col gap-0.5 text-text-secondary" data-testid="ladder-steps">
          {steps.map((s) => (
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
