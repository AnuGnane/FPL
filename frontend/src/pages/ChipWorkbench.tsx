import { useEffect, useState } from 'react'
import { ApiError, apiGet, apiPost } from '../api/client'
import { useJob } from '../api/useJob'
import ConstraintsPanel from '../components/ConstraintsPanel'
import PlanDiffTable from '../components/PlanDiffTable'
import PlayerName from '../components/PlayerName'
import type {
  ChipsWorkbench, ChipSquadPlayer, SquadDiff, WhatIfRequest, WhatIfResult,
} from '../types'

const LABELS: Record<string, string> = {
  wildcard: 'Wildcard',
  bboost: 'Bench Boost',
  freehit: 'Free Hit',
  '3xc': 'Triple Captain',
}

// A chip's gain is only ever read against its own threshold, so the bar is
// scaled to the threshold rather than to the largest gain on the table: a
// wildcard worth 9 against a bar of 8 and a bench boost worth 3 against a bar
// of 4 are two different answers, and a shared axis would draw them as the
// same one.
function GainBar({ gain, threshold }: { gain: number
                                        threshold: number | null }) {
  const bar = threshold ?? gain
  const width = bar > 0 ? Math.min(100, (gain / bar) * 100) : 0
  return (
    <span
      className="bar"
      style={{ display: 'inline-block', width: `${Math.max(2, width)}%`,
               background: gain >= bar ? 'var(--good)' : 'var(--line)' }}
      aria-label={`${gain} against a bar of ${bar}`}
    />
  )
}

function SquadColumn({ title, players }: { title: string
                                           players: ChipSquadPlayer[] }) {
  return (
    <div>
      <h3>{title} ({players.length})</h3>
      <ul>
        {players.map((p) => (
          <li key={p.code}>
            <PlayerName code={p.code} name={p.name} />{' '}
            <span className="muted">
              {p.position} · £{p.price}m · {p.ep} xPts
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function WildcardTab({ wildcard }: { wildcard: SquadDiff | null }) {
  if (wildcard === null) {
    return (
      <div className="card">
        <p className="muted">
          No wildcard available in this half of the season.
        </p>
      </div>
    )
  }
  return (
    <div className="card">
      <h2>Wildcard now</h2>
      <p className={wildcard.recommend ? 'good' : 'muted'}>
        Worth {wildcard.gain_over_horizon} expected points over the horizon —
        {wildcard.recommend ? ' worth playing.' : ' not worth it yet.'}
      </p>
      <div className="pitch-row" style={{ alignItems: 'flex-start' }}>
        <SquadColumn title="Kept" players={wildcard.kept} />
        <SquadColumn title="Out" players={wildcard.dropped} />
        <SquadColumn title="In" players={wildcard.added} />
      </div>
    </div>
  )
}

const EMPTY: WhatIfRequest = {
  lock: [], ban: [], force_in: [], max_hits: 0, chip: 'wc', horizon: null,
}

export default function ChipWorkbench() {
  const [data, setData] = useState<ChipsWorkbench | null>(null)
  const [empty, setEmpty] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<'table' | 'wildcard'>('table')
  const [request, setRequest] = useState<WhatIfRequest>(EMPTY)
  const [invalid, setInvalid] = useState<string | null>(null)
  const job = useJob()

  useEffect(() => {
    apiGet<ChipsWorkbench>('/api/chips').then(setData).catch((e: Error) => {
      // 404 is the ordinary "nothing has been advised yet" state, and the
      // server's own sentence says what to run.
      if (e instanceof ApiError && e.status === 404) setEmpty(e.message)
      else setError(e.message)
    })
  }, [])

  const solve = async () => {
    setInvalid(null)
    job.reset()
    try {
      // Posted here rather than through useJob.start so a structured 422
      // renders next to the inputs, exactly as the What-If Lab does it.
      const { job_id } = await apiPost<{ job_id: string }>('/api/whatif',
        request)
      job.attach(job_id)
    } catch (e) {
      setInvalid(e instanceof ApiError && typeof e.detail === 'object'
        && e.detail !== null
        ? (e.detail as { error: string }).error
        : e instanceof Error ? e.message : String(e))
    }
  }

  if (error) return <p className="bad">{error}</p>
  if (empty) {
    return (
      <>
        <h2>Chips</h2>
        <div className="card"><p className="muted">{empty}</p></div>
      </>
    )
  }
  if (!data) return <p className="muted">Loading…</p>

  const busy = job.status === 'queued' || job.status === 'running'
  const diff = job.result as WhatIfResult | null

  return (
    <>
      <h2>Chips · GW{data.gw}</h2>
      <div className="chips">
        <button onClick={() => setTab('table')} disabled={tab === 'table'}>
          Chip table
        </button>
        <button onClick={() => setTab('wildcard')}
                disabled={tab === 'wildcard'}>
          Wildcard
        </button>
      </div>
      {tab === 'table' && (
        <div className="card">
          <h2>Gain against the bar</h2>
          {data.chips.length === 0 && (
            <p className="muted">No chips available.</p>
          )}
          <table>
            <thead>
              <tr>
                <th>Chip</th><th>GW</th><th>Gain</th><th>Bar</th>
                <th>Per week</th><th />
              </tr>
            </thead>
            <tbody>
              {data.chips.map((row) => (
                <tr key={`${row.chip}-${row.gw}`}
                    className={row.play_now ? 'changed' : undefined}>
                  <td>{LABELS[row.chip] ?? row.chip}</td>
                  <td>GW{row.gw}</td>
                  <td>{row.gain}</td>
                  <td>{row.threshold ?? '—'}</td>
                  <td>{row.per_week ?? '—'}</td>
                  <td>
                    <GainBar gain={row.gain} threshold={row.threshold} />
                    {row.note && (
                      <span className="muted"> {row.note}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {tab === 'wildcard' && <WildcardTab wildcard={data.wildcard} />}
      <div className="card">
        <h2>Try it</h2>
        <p className="muted">
          A front door onto the What-If Lab with the chip prefilled — the
          same solver, the same baseline.
        </p>
        <ConstraintsPanel value={request} onChange={setRequest} />
        <button onClick={solve} disabled={busy}>
          {busy ? 'Solving…' : 'Re-solve'}
        </button>
        {invalid && <p className="bad">{invalid}</p>}
        {job.status === 'error' && <p className="bad">{job.error}</p>}
      </div>
      {diff && <PlanDiffTable diff={diff} />}
    </>
  )
}
