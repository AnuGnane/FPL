import { useEffect, useState } from 'react'
import { ApiError, apiGet, apiPost } from '../../api/client'
import { useJob } from '../../api/useJob'
import ConstraintsPanel from '../../components/ConstraintsPanel'
import PlanDiffTable from '../../components/PlanDiffTable'
import PlayerName from '../../components/PlayerName'
import { Card, EmptyState, PosBadge } from '../../kit'
import type {
  ChipsWorkbench, ChipSquadPlayer, SquadDiff, WhatIfRequest, WhatIfResult,
} from '../../types'

const LABELS: Record<string, string> = {
  wildcard: 'Wildcard',
  bboost: 'Bench Boost',
  freehit: 'Free Hit',
  '3xc': 'Triple Captain',
}

// The chip table speaks the solver's names; the What-If request speaks the
// API's two-letter codes. A row the mapping does not know is left alone
// rather than mapped to 'none', which would silently re-solve without a chip
// and look like the chip was worth nothing.
const CHIP_CODES: Record<string, WhatIfRequest['chip']> = {
  wildcard: 'wc',
  bboost: 'bb',
  freehit: 'fh',
  '3xc': 'tc',
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
               background: gain >= bar
                 ? 'var(--color-sage)' : 'var(--color-border)' }}
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
          <li key={p.code} className="flex items-center gap-1.5">
            <PosBadge pos={p.position} variant="dot" />
            <PlayerName code={p.code} name={p.name} />
            <span className="num ml-auto text-text-muted">
              £{p.price}m · {p.ep} xPts
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
      <Card>
        <p className="text-text-muted">
          No wildcard available in this half of the season.
        </p>
      </Card>
    )
  }
  return (
    <Card title="Wildcard now">
      <p className={wildcard.recommend ? 'text-sage' : 'text-text-muted'}>
        Worth <span className="num">{wildcard.gain_over_horizon}</span> expected
        points over the horizon —
        {wildcard.recommend ? ' worth playing.' : ' not worth it yet.'}
      </p>
      <div className="pitch-row" style={{ alignItems: 'flex-start' }}>
        <SquadColumn title="Kept" players={wildcard.kept} />
        <SquadColumn title="Out" players={wildcard.dropped} />
        <SquadColumn title="In" players={wildcard.added} />
      </div>
    </Card>
  )
}

const EMPTY: WhatIfRequest = {
  lock: [], ban: [], force_in: [], max_hits: 0, chip: 'wc', horizon: null,
}

export default function ChipsTab() {
  const [data, setData] = useState<ChipsWorkbench | null>(null)
  const [empty, setEmpty] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<'table' | 'wildcard'>('table')
  const [request, setRequest] = useState<WhatIfRequest>(EMPTY)
  const [chip, setChip] = useState<string>('wildcard')
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

  // Picking a chip is the whole point of the page: "Try it" has to re-solve
  // the chip the reader is looking at, not the wildcard it happened to open
  // on.
  const pick = (name: string) => {
    setChip(name)
    const code = CHIP_CODES[name]
    if (code) setRequest((r) => ({ ...r, chip: code }))
  }

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

  if (error) return <p className="text-rust">{error}</p>
  if (empty) {
    return (
      <EmptyState
        title="No chips to weigh"
        detail={empty}
        action="Run advise"
      />
    )
  }
  if (!data) return <p className="text-text-muted">Loading…</p>

  const busy = job.status === 'queued' || job.status === 'running'
  const diff = job.result as WhatIfResult | null

  return (
    <>
      <div className="chips">
        <button onClick={() => setTab('table')} disabled={tab === 'table'}>
          Chip table
        </button>
        <button onClick={() => { setTab('wildcard'); pick('wildcard') }}
                disabled={tab === 'wildcard'}>
          Wildcard
        </button>
      </div>
      {tab === 'table' && (
        <Card title="Gain against the bar">
          {data.chips.length === 0 && (
            <EmptyState
              title="No chips available"
              detail="Both chips for this half of the season are already
                      played, so there is nothing left to weigh."
              action="Run advise"
            />
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
                    className={row.play_now ? 'changed' : undefined}
                    aria-selected={row.chip === chip}>
                  <td>
                    <button className="player-link"
                            onClick={() => pick(row.chip)}>
                      {LABELS[row.chip] ?? row.chip}
                    </button>
                  </td>
                  <td className="num">GW{row.gw}</td>
                  <td><span className="num">{row.gain}</span></td>
                  <td><span className="num">{row.threshold ?? '—'}</span></td>
                  <td><span className="num">{row.per_week ?? '—'}</span></td>
                  <td>
                    <GainBar gain={row.gain} threshold={row.threshold} />
                    {row.note && (
                      <span className="text-text-muted"> {row.note}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      {tab === 'wildcard' && <WildcardTab wildcard={data.wildcard} />}
      <Card title="Try it">
        <p className="text-text-muted">
          A front door onto the What-If Lab with{' '}
          <strong>{LABELS[chip] ?? chip}</strong> prefilled — the same solver,
          the same baseline. Pick another row above to try that one instead.
        </p>
        <ConstraintsPanel value={request} onChange={setRequest} />
        <button onClick={solve} disabled={busy}>
          {busy ? 'Solving…' : 'Re-solve'}
        </button>
        {invalid && <p className="text-rust">{invalid}</p>}
        {job.status === 'error' && <p className="text-rust">{job.error}</p>}
      </Card>
      {diff && <PlanDiffTable diff={diff} />}
    </>
  )
}
