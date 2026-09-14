import { useState } from 'react'
import { errorText } from '../../api/client'
import { usePageData } from '../../api/pageData'
import { useJob } from '../../api/useJob'
import {
  Bar, Button, Callout, Card, EmptyState, Loading, PlayerName,
  Segmented, Skeleton, TABLE_CLASS, THEAD_CLASS, TR_CLASS, fmtNum, tdClass,
  thClass,
} from '../../kit'
import ChipOutlook from './ChipOutlook'
import ConstraintsPanel from './ConstraintsPanel'
import PlanDiffTable from './PlanDiffTable'
import { CHIP_CODES, LABELS } from './chips'
import { useWhatIfSubmit } from './useWhatIfSubmit'
import type {
  ChipsWorkbench, SquadDiff, SquadPlayerRef, WhatIfRequest, WhatIfResult,
} from '../../types'

// A chip's gain is only ever read against its own threshold, so the bar is
// scaled to the threshold rather than to the largest gain on the table: a
// wildcard worth 9 against a bar of 8 and a bench boost worth 3 against a bar
// of 4 are two different answers, and a shared axis would draw them as the
// same one.
function GainBar({ gain, threshold }: { gain: number
                                        threshold: number | null }) {
  const bar = threshold ?? gain
  // Rule 1: over the bar is a direction — this chip is worth playing. Under
  // it the fill is information, so it stays grey.
  return (
    <Bar
      fraction={bar > 0 ? gain / bar : 0}
      tone={gain >= bar ? 'up' : 'neutral'}
      width={96}
      testId={`gain-${gain}-${bar}`}
      aria-label={`${gain} against a bar of ${bar}`}
    />
  )
}

// θ or the pre-v4c constant, in the words the server sent. A bar with no
// source is a payload written before v12 and says nothing rather than
// guessing (v12 W3 §4.2).
function BarSource({ source }: { source?: string | null }) {
  if (!source || source === 'unknown') return null
  // T8-T11 review, Important 2: a chip *pair*'s bar is its two chips' bars
  // added, and its source spells the sum out — "theta: wildcard 8.00 + bboost
  // 4.00" — so the marker matches on the leading token rather than on the
  // whole string, which would have read a θ bar as flat.
  const theta = source === 'theta' || source.startsWith('theta:')
  return (
    <span className="ml-1 text-text-faint" data-testid="bar-source"
          title={source === 'theta'
            ? 'θ: the surplus the best remaining week is expected to offer '
              + '(v4c stopping rule)'
            : source}>
      {theta ? 'θ' : 'flat'}
    </span>
  )
}

function SquadColumn({ title, players }: { title: string
                                           players: SquadPlayerRef[] }) {
  return (
    <div>
      <h3 className="label mb-1">{title} ({players.length})</h3>
      <ul className="flex flex-col gap-0.5">
        {players.map((p) => (
          <li key={p.code} className="flex items-center gap-1.5">
            <PlayerName code={p.code} name={p.name} pos={p.position} />
            <span className="tn ml-auto text-text-muted">
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
      {/* Rule 1: worth playing or not is a verdict against the bar. */}
      <p className={wildcard.recommend ? 'text-up' : 'text-text-muted'}>
        Worth <span className="tn">{wildcard.gain_over_horizon}</span> expected
        points over the horizon —
        {wildcard.recommend ? ' worth playing.' : ' not worth it yet.'}
      </p>
      {wildcard.threshold !== null && wildcard.threshold !== undefined && (
        <p className="mt-1 text-text-faint" data-testid="wildcard-bar">
          {`Against a bar of ${wildcard.threshold}`}
          {/* The reason is written server-side and rendered verbatim. It
              already begins "flat: …", so the old wrapper printed "flat
              fallback — flat: …", and it printed the sentinel "unknown" as
              though that were a reason. A lookup too old to explain itself
              now says nothing here, exactly as BarSource does. */}
          {wildcard.threshold_source === 'theta'
            ? ' (θ — the best remaining week’s expected surplus)'
            : (!wildcard.threshold_source
               || wildcard.threshold_source === 'unknown')
                ? ''
                : ` (${wildcard.threshold_source})`}
        </p>
      )}
      <div className="mt-3 grid items-start gap-4 sm:grid-cols-3">
        <SquadColumn title="Kept" players={wildcard.kept} />
        <SquadColumn title="Out" players={wildcard.dropped} />
        <SquadColumn title="In" players={wildcard.added} />
      </div>
    </Card>
  )
}

const EMPTY: WhatIfRequest = {
  lock: [], ban: [], force_in: [], force_out: [], max_hits: 0,
  max_transfers: null, chip: 'wc', horizon: null,
}

export default function ChipsTab() {
  const page = usePageData<ChipsWorkbench>('/api/chips')
  const [tab, setTab] = useState<'table' | 'wildcard' | 'outlook'>('table')
  const [request, setRequest] = useState<WhatIfRequest>(EMPTY)
  const [chip, setChip] = useState<string>('wildcard')
  const [invalid, setInvalid] = useState<string | null>(null)
  const job = useJob({ slot: 'chips' })

  // Picking a chip is the whole point of the page: "Try it" has to re-solve
  // the chip the reader is looking at, not the wildcard it happened to open
  // on.
  const pick = (name: string) => {
    setChip(name)
    const code = CHIP_CODES[name]
    if (code) setRequest((r) => ({ ...r, chip: code }))
  }

  // T8-T11 review, Important 3. `pick` leaves `request.chip` alone for a chip
  // the mapping does not know — which is right, since 'none' would re-solve
  // without a chip — but the arm below then submitted whatever the *previous*
  // pick had set. Picking the wildcard-plus-bench-boost row and pressing
  // "Try it" re-solved a plain wildcard under the pair's label: the strongest
  // way to be wrong about a chip, because the page names one and the solver
  // runs another. The lab has no arm for a pair (there is no two-chip What-If
  // request), so the honest answer is to withhold the button and say so.
  const armed = CHIP_CODES[chip] !== undefined

  // Posted through the shared submit rather than useJob.start so a structured
  // 422 renders next to the inputs, exactly as the What-If Lab does it
  // (v18f §2.1 — one copy of the two lines both tabs wrote).
  const submit = useWhatIfSubmit(job, (e) => {
    // `errorText` is the one place that unwraps a refusal's `{constraint,
    // error, players}` body; this used to hand-roll the same three cases
    // and got a fourth — a detail object with no `error` key — wrong
    // (v18e §2.3).
    setInvalid(errorText(e))
  })

  const solve = async () => {
    setInvalid(null)
    await submit(request)
  }

  const busy = job.status === 'queued' || job.status === 'running'
  const diff = job.result as WhatIfResult | null

  // The split `Loaded` makes on the status, made here because this card
  // already made it and made it better: `/api/chips` answers 404 for a
  // gameweek nobody has advised (chips.py:60) and the server's own sentence
  // says what to run, so the empty state carries it rather than a generic
  // callout. 422 joins 404 because a cold clone never reaches chips.py's own
  // 404 — every read under it raises a `GafferError` the app-wide handler
  // maps (app.py:67-69), and both statuses mean the same thing: run the job
  // (v18e §2.2, ruling 7).
  const absent = page.status === 404 || page.status === 422
  if (page.error !== null && absent) {
    return (
      <EmptyState
        title="No chips to weigh"
        detail={page.error}
        action="Run advise"
      />
    )
  }
  if (page.error !== null) {
    return (
      <Card title="Chips unavailable">
        <Callout tone="error">{page.error}</Callout>
      </Card>
    )
  }
  if (page.data === null) return <Loading />
  const data = page.data

  return (
    <>
      {/* Deliberately not carded: a segmented control belongs above the
          panel it switches, the way the hub's own tab strip does. */}
      {/* `flex-wrap` rather than a scroller: v9b left this control at two
          buttons because two already fit, and a third reopens that. Wrapping
          is the cheapest answer and the one responsive.test.tsx's existing
          rail already recognises — no third way of making a strip narrow. */}
      <Segmented
        className="mb-4 flex-wrap"
        label="Chips panel"
        value={tab}
        options={[{ value: 'table', label: 'Chip table' },
                  { value: 'wildcard', label: 'Wildcard' },
                  { value: 'outlook', label: 'Season outlook' }]}
        onChange={(key) => {
          setTab(key)
          if (key === 'wildcard') pick('wildcard')
        }}
      />
      {tab === 'outlook' && <ChipOutlook />}
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
          <div className="overflow-x-auto">
          <table className={TABLE_CLASS}>
            <thead className={THEAD_CLASS}>
              <tr>
                <th scope="col" className={thClass()}>Chip</th>
                <th scope="col" className={thClass(true)}>GW</th>
                <th scope="col" className={thClass(true)}>Gain</th>
                <th scope="col" className={thClass(true)}>Bar</th>
                <th scope="col" className={thClass(true)}>Per week</th>
                <th scope="col" className={thClass()}>Against the bar</th>
              </tr>
            </thead>
            <tbody>
              {data.chips.map((row) => (
                <tr key={`${row.chip}-${row.gw}`}
                    className={TR_CLASS}
                    data-play-now={String(row.play_now)}
                    aria-selected={row.chip === chip}>
                  {/* Rule 1: "play it now" is this row clearing its bar. */}
                  <td className={tdClass()}>
                    <button
                      type="button"
                      onClick={() => pick(row.chip)}
                      className={`hover:underline ${row.play_now
                        ? 'text-up' : 'text-text'}`}
                    >
                      {LABELS[row.chip] ?? row.chip}
                    </button>
                  </td>
                  <td className={`${tdClass(true)} text-text-secondary`}>
                    {row.gw2 == null ? `GW${row.gw}`
                      : `GW${row.gw} + GW${row.gw2}`}
                  </td>
                  <td className={`${tdClass(true)} ${row.play_now
                    ? 'text-up' : 'text-text'}`}>{row.gain}</td>
                  <td className={`${tdClass(true)} text-text-muted`}>
                    {row.threshold ?? '—'}
                    <BarSource source={row.threshold_source} />
                  </td>
                  <td className={`${tdClass(true)} text-text-muted`}>
                    {row.per_week ?? '—'}
                  </td>
                  <td className={tdClass()}>
                    <GainBar gain={row.gain} threshold={row.threshold} />
                    {row.note && (
                      <span className="ml-2 text-text-muted">{row.note}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </Card>
      )}
      {tab === 'wildcard' && <WildcardTab wildcard={data.wildcard} />}
      <Card title="Try it" className="mb-4">
        <p className="text-text-muted">
          {armed ? (
            <>
              A front door onto the What-If Lab with{' '}
              <strong>{LABELS[chip] ?? chip}</strong> prefilled — the same
              solver, the same baseline. Pick another row above to try that
              one instead.
            </>
          ) : (
            'A chip pair has no What-If arm — the single wildcard and bench '
            + 'boost do. Pick either of those rows above to re-solve it.'
          )}
        </p>
        <ConstraintsPanel value={request} onChange={setRequest} />
        <Button onClick={solve} disabled={busy || !armed}>
          {busy ? 'Solving…' : 'Re-solve'}
        </Button>
        {invalid && (
          <Callout tone="error" className="mt-2">{invalid}</Callout>
        )}
        {job.status === 'error' && (
          <Callout tone="error" className="mt-2">{job.error}</Callout>
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
