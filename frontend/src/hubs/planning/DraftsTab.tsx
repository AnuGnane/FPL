import { useCallback, useEffect, useState } from 'react'
import { apiDelete, apiGet, apiPost, errorText } from '../../api/client'
import { useJob } from '../../api/useJob'
import {
  Card, EmptyState, JobLog, Skeleton, fmtNum, toast,
} from '../../kit'
import type {
  DraftCompare, DraftCompareRequest, DraftList, DraftSaveRequest,
  WhatIfRequest,
} from '../../types'

/** `drafts.MAX_COMPARE`: the server's solve budget for one comparison. */
const MAX_COMPARE = 6
/** `drafts.MAX_DRAFTS`: what the store keeps. Represented here so the cap is
 *  a disabled button with a reason rather than a 422 after the click. */
const MAX_DRAFTS = 12

export default function DraftsTab({ current }: { current: WhatIfRequest }) {
  const [drafts, setDrafts] = useState<DraftList>({ drafts: [] })
  const [name, setName] = useState('')
  const [picked, setPicked] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const job = useJob('drafts-compare')

  const load = useCallback(() => {
    apiGet<DraftList>('/api/drafts').then(setDrafts).catch(() => {})
  }, [])
  useEffect(() => { load() }, [load])

  const full = drafts.drafts.length >= MAX_DRAFTS

  const save = async () => {
    setError(null)
    try {
      const body: DraftSaveRequest = { name, constraints: current }
      setDrafts(await apiPost<DraftList>('/api/drafts', body))
      toast('positive', `Saved "${name}".`)
      setName('')
    } catch (e) {
      const text = errorText(e)
      setError(text)
      toast('negative', `Could not save "${name}" — ${text}`)
    }
  }

  // Untick, or tick — but at the cap the new name is refused rather than
  // sliced off the end, which used to tick a box and compare something else.
  const toggle = (draft: string) => setPicked((prev) => {
    if (prev.includes(draft)) return prev.filter((d) => d !== draft)
    return prev.length >= MAX_COMPARE ? prev : [...prev, draft]
  })

  const remove = async (draft: string) => {
    try {
      setDrafts(await apiDelete<DraftList>(
        `/api/drafts/${encodeURIComponent(draft)}`))
      toast('positive', `Deleted "${draft}".`)
    } catch (e) {
      toast('negative', `Could not delete "${draft}" — ${errorText(e)}`)
      load()
    }
    // A deleted name left ticked is a name the compare endpoint answers 422
    // unknown_draft for.
    setPicked((prev) => prev.filter((d) => d !== draft))
  }

  const compare = () => {
    const body: DraftCompareRequest = { names: picked }
    job.start('/api/drafts/compare', body)
  }

  const result = job.result as DraftCompare | null

  return (
    <>
      <Card title="Drafts" className="mb-4">
        <p className="mb-3 text-text-muted">
          A draft is the constraints you asked for, not the squad you got, so
          it still means something after Thursday's price changes. Comparing
          re-solves each one against today's board.
        </p>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <input
            className="rounded-card border border-border bg-base px-2 py-1
                       text-text"
            aria-label="draft name"
            placeholder="Name this what-if"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button type="button" onClick={save}
                  disabled={!name.trim() || full}
                  className="rounded-card border border-border bg-card px-3
                             py-2 text-text-secondary hover:text-text
                             disabled:text-text-faint">
            Save the current What-If
          </button>
          <button
            type="button"
            disabled={picked.length === 0 || job.status === 'running'}
            onClick={compare}
            className="rounded-card border border-border bg-card px-3 py-2
                       text-text-secondary hover:text-text
                       disabled:text-text-faint"
          >
            {job.status === 'running' ? 'Comparing…' : 'Compare'}
          </button>
        </div>
        {full && (
          <p className="mb-3 text-text-muted">
            Twelve drafts is the cap the store keeps — delete one to save
            another.
          </p>
        )}
        {error && <p className="mb-3 text-rust">{error}</p>}
        {drafts.drafts.length === 0
          ? (
            <EmptyState
              title="No drafts yet"
              detail="A draft is a set of What-If constraints under a name, so
                      it still means something after Thursday's price changes.
                      Set some constraints on the What-If tab, then name them
                      here."
              // The exact label on the button three lines above it.
              action="Save the current What-If"
            />
            )
          : (
            <ul className="flex flex-col gap-2">
              {drafts.drafts.map((draft) => (
                <li key={draft.name}
                    className="flex items-baseline justify-between gap-3">
                  <label className="flex items-center gap-2">
                    <input type="checkbox"
                           aria-label={`compare ${draft.name}`}
                           checked={picked.includes(draft.name)}
                           disabled={!picked.includes(draft.name)
                             && picked.length >= MAX_COMPARE}
                           onChange={() => toggle(draft.name)} />
                    <span className="text-text">{draft.name}</span>
                    <span className="text-text-muted">
                      {summarize(draft.constraints)}
                    </span>
                  </label>
                  <button type="button" aria-label={`delete ${draft.name}`}
                          onClick={() => remove(draft.name)}
                          className="rounded-card border border-border px-2
                                     py-1 text-text-muted hover:text-text">
                    Delete
                  </button>
                </li>
              ))}
            </ul>
            )}
      </Card>
      {job.status === 'error' && (
        <JobLog status="failed" lines={[]} error={job.error ?? 'failed'} />
      )}
      {(job.status === 'queued' || job.status === 'running') && (
        <Skeleton title="Comparing" lines={picked.length || 3}
                  label="Re-solving each draft against today's board…" />
      )}
      {/* Guarded with the same condition so a re-compare clears the old
          table rather than pulsing above a previous run's answer. */}
      {result && job.status !== 'queued' && job.status !== 'running' && (
        <Card title={`Compared over ${result.weeks} weeks`} className="mb-4">
          <table className="w-full">
            <thead>
              <tr>
                <th className="label pb-1 text-left">Draft</th>
                <th className="label pb-1 text-right">Horizon xPts</th>
                <th className="label pb-1 text-right">vs optimum</th>
                <th className="label pb-1 text-right">Hits</th>
                <th className="label pb-1 text-left">Chip</th>
                <th className="label pb-1 text-left">Week 1</th>
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row) => (
                <tr key={row.name}>
                  <td className="py-1.5 text-text">{row.name}</td>
                  <td className="num py-1.5 text-right">
                    {row.horizon_pts === null
                      ? '–' : fmtNum(row.horizon_pts, 1)}
                  </td>
                  <td className="num py-1.5 text-right text-text-secondary">
                    {row.is_reference || row.delta_xpts === null
                      ? '–' : fmtNum(row.delta_xpts, 1)}
                  </td>
                  <td className="num py-1.5 text-right">{row.hits ?? '–'}</td>
                  <td className="py-1.5 text-text-secondary">
                    {row.chip ?? '–'}
                    {row.horizon !== null && result.weeks < row.horizon
                      && ` · ${row.horizon}-week plan`}
                  </td>
                  <td className="py-1.5 text-text-secondary">
                    {row.error
                      ? <span className="text-rust">{row.error}</span>
                      : moves(row.buys, row.sells)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-text-muted">
            Solved {result.rows[0]?.solved_at?.slice(0, 16).replace('T', ' ')}
            {' '}against the saved GW{result.gw} board.
            {result.rows.some((r) => r.horizon !== null
              && r.horizon > result.weeks)
              && ' Every row is scored over the shortest plan in the'
                 + ' comparison — a free hit covers one week.'}
          </p>
        </Card>
      )}
    </>
  )
}

function summarize(c: WhatIfRequest): string {
  const bits = []
  if (c.lock.length) bits.push(`${c.lock.length} locked`)
  if (c.ban.length) bits.push(`${c.ban.length} banned`)
  if (c.force_in.length) bits.push(`${c.force_in.length} forced in`)
  if (c.max_hits) bits.push(`up to ${c.max_hits} hits`)
  if (c.chip !== 'none') bits.push(c.chip)
  if (c.horizon) bits.push(`${c.horizon} weeks`)
  return bits.length ? `· ${bits.join(', ')}` : '· no constraints'
}

function moves(buys: { name: string }[], sells: { name: string }[]): string {
  if (!buys.length && !sells.length) return 'hold'
  return `${sells.map((p) => p.name).join(', ') || '—'} → `
    + `${buys.map((p) => p.name).join(', ') || '—'}`
}
