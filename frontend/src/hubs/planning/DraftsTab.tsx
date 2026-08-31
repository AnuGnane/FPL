import { useCallback, useEffect, useState } from 'react'
import { apiDelete, apiGet, apiPost } from '../../api/client'
import { useJob } from '../../api/useJob'
import { Card, JobLog, fmtNum } from '../../kit'
import type { DraftCompare, DraftList, WhatIfRequest } from '../../types'

const MAX_COMPARE = 6

export default function DraftsTab({ current }: { current: WhatIfRequest }) {
  const [drafts, setDrafts] = useState<DraftList>({ drafts: [] })
  const [name, setName] = useState('')
  const [picked, setPicked] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const job = useJob()

  const load = useCallback(() => {
    apiGet<DraftList>('/api/drafts').then(setDrafts).catch(() => {})
  }, [])
  useEffect(() => { load() }, [load])

  const save = async () => {
    setError(null)
    try {
      setDrafts(await apiPost<DraftList>('/api/drafts',
                                         { name, constraints: current }))
      setName('')
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const toggle = (draft: string) => setPicked((prev) => (
    prev.includes(draft) ? prev.filter((d) => d !== draft)
      : [...prev, draft].slice(0, MAX_COMPARE)))

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
          <button type="button" onClick={save} disabled={!name.trim()}
                  className="rounded-card border border-border bg-card px-3
                             py-2 text-text-secondary hover:text-text
                             disabled:text-text-faint">
            Save the current What-If
          </button>
          <button
            type="button"
            disabled={picked.length === 0 || job.status === 'running'}
            onClick={() => job.start('/api/drafts/compare',
                                     { names: picked })}
            className="rounded-card border border-border bg-card px-3 py-2
                       text-text-secondary hover:text-text
                       disabled:text-text-faint"
          >
            {job.status === 'running' ? 'Comparing…' : 'Compare'}
          </button>
        </div>
        {error && <p className="mb-3 text-rust">{error}</p>}
        {drafts.drafts.length === 0
          ? <p className="text-text-muted">No drafts yet.</p>
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
                          onClick={() => apiDelete<DraftList>(
                            `/api/drafts/${encodeURIComponent(draft.name)}`)
                            .then(setDrafts).catch(() => load())}
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
      {result && (
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
