import { useEffect, useState } from 'react'
import { ApiError, apiGet, apiPost } from '../../api/client'
import { useJob } from '../../api/useJob'
import {
  Card, EmptyState, Loading, PlayerName, Skeleton, fmtNum,
} from '../../kit'
import ConstraintsPanel from './ConstraintsPanel'
import PlanDiffTable from './PlanDiffTable'
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
    <span className="inline-block h-1.5 w-24 rounded-full bg-base align-middle">
      <span
        className="block h-1.5 rounded-full"
        style={{ width: `${Math.max(2, width)}%`,
                 background: gain >= bar
                   ? 'var(--color-sage)' : 'var(--color-border)' }}
        aria-label={`${gain} against a bar of ${bar}`}
      />
    </span>
  )
}

function SquadColumn({ title, players }: { title: string
                                           players: ChipSquadPlayer[] }) {
  return (
    <div>
      <h3 className="label mb-1">{title} ({players.length})</h3>
      <ul className="flex flex-col gap-0.5">
        {players.map((p) => (
          <li key={p.code} className="flex items-center gap-1.5">
            <PlayerName code={p.code} name={p.name} pos={p.position} />
            <span className="num ml-auto text-text-muted">
              £{fmtNum(p.price)}m · {fmtNum(p.ep)} xPts
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
      <Card title="Wildcard now" className="mb-4">
        <p className="text-text-muted">
          No wildcard available in this half of the season.
        </p>
      </Card>
    )
  }
  return (
    <Card title="Wildcard now" className="mb-4">
      <p className={wildcard.recommend ? 'text-sage' : 'text-text-muted'}>
        Worth <span className="num">{wildcard.gain_over_horizon}</span> expected
        points over the horizon —
        {wildcard.recommend ? ' worth playing.' : ' not worth it yet.'}
      </p>
      <div className="mt-3 grid items-start gap-4 sm:grid-cols-3">
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
  const job = useJob('chips')

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

  if (error) {
    return (
      <Card title="Chips unavailable">
        <p className="text-rust">{error}</p>
      </Card>
    )
  }
  if (empty) {
    return (
      <EmptyState
        title="No chips to weigh"
        detail={empty}
        action="Run advise"
      />
    )
  }
  if (!data) return <Loading />

  const busy = job.status === 'queued' || job.status === 'running'
  const diff = job.result as WhatIfResult | null

  return (
    <>
      {/* Deliberately not carded: a segmented control belongs above the
          panel it switches, the way the hub's own tab strip does. */}
      <div className="mb-4 flex gap-1">
        {([['table', 'Chip table'], ['wildcard', 'Wildcard']] as const).map(
          ([key, label]) => (
            <button
              key={key}
              type="button"
              aria-pressed={tab === key}
              onClick={() => {
                setTab(key)
                if (key === 'wildcard') pick('wildcard')
              }}
              className={`rounded-card border px-3 py-1.5 ${tab === key
                ? 'border-text text-text' : 'border-border text-text-muted'}`}
            >
              {label}
            </button>
          ))}
      </div>
      {tab === 'table' && (
        <Card title="Gain against the bar" className="mb-4">
          {data.chips.length === 0 && (
            <EmptyState
              title="No chips available"
              detail="Both chips for this half of the season are already
                      played, so there is nothing left to weigh."
              action="Run advise"
            />
          )}
          <table className="w-full">
            <thead>
              <tr>
                <th className="label pb-1 text-left">Chip</th>
                <th className="label pb-1 text-right">GW</th>
                <th className="label pb-1 text-right">Gain</th>
                <th className="label pb-1 text-right">Bar</th>
                <th className="label pb-1 text-right">Per week</th>
                <th className="label pb-1 pl-3 text-left">Against the bar</th>
              </tr>
            </thead>
            <tbody>
              {data.chips.map((row) => (
                <tr key={`${row.chip}-${row.gw}`}
                    className="border-t border-divider"
                    data-play-now={String(row.play_now)}
                    aria-selected={row.chip === chip}>
                  <td className="py-1.5">
                    <button
                      type="button"
                      onClick={() => pick(row.chip)}
                      className={`hover:underline ${row.play_now
                        ? 'text-sage' : 'text-text'}`}
                    >
                      {LABELS[row.chip] ?? row.chip}
                    </button>
                  </td>
                  <td className="num py-1.5 text-right text-text-secondary">
                    GW{row.gw}
                  </td>
                  <td className={`num py-1.5 text-right ${row.play_now
                    ? 'text-sage' : 'text-text'}`}>{row.gain}</td>
                  <td className="num py-1.5 text-right text-text-muted">
                    {row.threshold ?? '—'}
                  </td>
                  <td className="num py-1.5 text-right text-text-muted">
                    {row.per_week ?? '—'}
                  </td>
                  <td className="py-1.5 pl-3">
                    <GainBar gain={row.gain} threshold={row.threshold} />
                    {row.note && (
                      <span className="ml-2 text-text-muted">{row.note}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      {tab === 'wildcard' && <WildcardTab wildcard={data.wildcard} />}
      <Card title="Try it" className="mb-4">
        <p className="text-text-muted">
          A front door onto the What-If Lab with{' '}
          <strong>{LABELS[chip] ?? chip}</strong> prefilled — the same solver,
          the same baseline. Pick another row above to try that one instead.
        </p>
        <ConstraintsPanel value={request} onChange={setRequest} />
        <button
          type="button"
          onClick={solve}
          disabled={busy}
          className="rounded-card border border-border bg-base px-3 py-2
                     text-text-secondary hover:text-text
                     disabled:text-text-faint"
        >
          {busy ? 'Solving…' : 'Re-solve'}
        </button>
        {invalid && <p className="mt-2 text-rust">{invalid}</p>}
        {job.status === 'error' && (
          <p className="mt-2 text-rust">{job.error}</p>
        )}
      </Card>
      {busy && (
        <Skeleton title="Re-solving" lines={5}
                  label="Solving with the chip prefilled…" />
      )}
      {diff && !busy && <PlanDiffTable diff={diff} />}
    </>
  )
}
