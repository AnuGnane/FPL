import { useEffect, useState } from 'react'
import { ApiError, apiGet, apiPost } from '../../api/client'
import { useJob } from '../../api/useJob'
import {
  Bar, Button, Callout, Card, Chip, EmptyState, Loading, PlayerName,
  Segmented, Skeleton, TABLE_CLASS, THEAD_CLASS, TR_CLASS, fmtNum, tdClass,
  thClass,
} from '../../kit'
import ConstraintsPanel from './ConstraintsPanel'
import PlanDiffTable from './PlanDiffTable'
import type {
  ChipPlan, ChipsWorkbench, ChipSquadPlayer, FixtureOutlook, SquadDiff,
  WhatIfRequest, WhatIfResult,
} from '../../types'

const LABELS: Record<string, string> = {
  wildcard: 'Wildcard',
  bboost: 'Bench Boost',
  freehit: 'Free Hit',
  '3xc': 'Triple Captain',
  // v12 W3 §4.5: the one chip *pair*, named rather than composed.
  'wildcard+bboost': 'Wildcard + Bench Boost',
}

// The chip table speaks the solver's names; the What-If request speaks the
// API's two-letter codes. A row the mapping does not know is left alone
// rather than mapped to 'none', which would silently re-solve without a chip
// and look like the chip was worth nothing.
// Exported since v11: the planner board maps the same chip names onto the same
// codes when it prefills the lab, and two copies of this table would drift.
export const CHIP_CODES: Record<string, WhatIfRequest['chip']> = {
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
                                           players: ChipSquadPlayer[] }) {
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
  const [data, setData] = useState<ChipsWorkbench | null>(null)
  const [empty, setEmpty] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<'table' | 'wildcard' | 'outlook'>('table')
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

  // T8-T11 review, Important 3. `pick` leaves `request.chip` alone for a chip
  // the mapping does not know — which is right, since 'none' would re-solve
  // without a chip — but the arm below then submitted whatever the *previous*
  // pick had set. Picking the wildcard-plus-bench-boost row and pressing
  // "Try it" re-solved a plain wildcard under the pair's label: the strongest
  // way to be wrong about a chip, because the page names one and the solver
  // runs another. The lab has no arm for a pair (there is no two-chip What-If
  // request), so the honest answer is to withhold the button and say so.
  const armed = CHIP_CODES[chip] !== undefined

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
        <Callout tone="error">{error}</Callout>
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
                <th className={thClass()}>Chip</th>
                <th className={thClass(true)}>GW</th>
                <th className={thClass(true)}>Gain</th>
                <th className={thClass(true)}>Bar</th>
                <th className={thClass(true)}>Per week</th>
                <th className={thClass()}>Against the bar</th>
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


/** The season ahead: what each chip's bar does over the coming weeks, and
 *  which weeks are doubles or blanks (v10b §F2c).
 *
 *  Two independent fetches, on purpose. `/api/chips/plan` re-solves a handful
 *  of small MILPs and `/api/fixtures/outlook` reads a parquet; they fail for
 *  unrelated reasons, and a tab that blanks both because one is down is worse
 *  than a tab that shows the half it has.
 *
 *  It reports and does not instruct. θ is the bar the advise run itself
 *  solved against — the same expression, from the same asset — so this panel
 *  says where the season stands, not what to do about it.
 */
function ChipOutlook() {
  const [plan, setPlan] = useState<ChipPlan | null>(null)
  const [outlook, setOutlook] = useState<FixtureOutlook | null>(null)
  const [planError, setPlanError] = useState<string | null>(null)
  const [outlookError, setOutlookError] = useState<string | null>(null)

  useEffect(() => {
    apiGet<ChipPlan>('/api/chips/plan').then(setPlan)
      .catch((e: Error) => setPlanError(e.message))
    apiGet<FixtureOutlook>('/api/fixtures/outlook').then(setOutlook)
      .catch((e: Error) => setOutlookError(e.message))
  }, [])

  if (!plan && !outlook && !planError && !outlookError) return <Loading />

  const weeks = outlook?.weeks ?? []
  // The filter is for *display* — which rows are worth a line in the table.
  // Whether there is anything scheduled at all is the server's answer, and
  // the empty-state copy reads it off the served flags rather than
  // re-deriving it here: `has_doubles` is a claim about the served slice, and
  // the rows are only what this slice happens to carry. v9d's `available`,
  // same reasoning.
  //
  // So `has_doubles && interesting.length === 0` renders neither the empty
  // state nor the table. That gap is unreachable in this client: the flags are
  // computed over the same slice the rows come from, and this component sends
  // no `from`, so the slice is the whole published list. If a caller ever does
  // narrow it, the honest render is nothing rather than a contradiction.
  const interesting = weeks.filter(
    (w) => w.doubles.length > 0 || w.blanks.length > 0)
  const nothingScheduled = !outlook?.has_doubles && !outlook?.has_blanks

  return (
    <div data-testid="chip-outlook">
      <Card title="The season ahead" className="mb-4">
        <p className="mb-3 text-text-muted" data-testid="outlook-caveat">
          Planning, not advice: this is where each chip&rsquo;s bar sits over
          the coming weeks and which weeks are unusual. What to play this week
          is This Week&rsquo;s answer.
        </p>
        {planError && <Callout tone="error">{planError}</Callout>}
        {plan?.chips.map((row) => {
          const expiry = row.window?.[1]
          return (
            <div key={row.chip} data-testid={`outlook-chip-${row.chip}`}
                 className="mb-3 border-t border-divider pt-2">
              <div className="flex flex-wrap items-baseline gap-x-3">
                <span className="text-text">{LABELS[row.chip] ?? row.chip}</span>
                <span className="tn text-text-secondary">
                  {`best GW${row.best_gw} · ${fmtNum(row.best_gain, 1)} pts`}
                </span>
                <span className="tn text-text-muted">
                  {`θ ${fmtNum(row.threshold_now ?? null, 1)}`}
                </span>
                {expiry != null && (
                  <span className="text-text-muted">
                    {`expires after GW${expiry}`}
                  </span>
                )}
              </div>
              <ThetaTrack weeks={row.weeks} thetas={row.thetas} />
            </div>
          )
        })}
      </Card>
      <Card title="Doubles and blanks">
        {outlookError && <Callout tone="error">{outlookError}</Callout>}
        {/* Only alongside rows: on a fresh clone the server serves no weeks
            at all, and "club names unavailable" over an empty table is a
            complaint about names nothing was going to print. */}
        {outlook != null && outlook.weeks.length > 0
          && outlook.teams_known === false && (
          <p className="mb-2 text-text-muted"
             data-testid="outlook-teams-unknown">
            Club names unavailable — counts still hold.
          </p>
        )}
        {outlook && nothingScheduled && (
          <EmptyState
            title="Nothing unusual scheduled"
            detail={outlook.note
              ?? 'No doubles or blanks are scheduled yet — rearrangements '
                + 'usually start appearing around the cup rounds.'}
            action="Refresh data"
          />
        )}
        {interesting.length > 0 && (
          <div className="overflow-x-auto">
            <table className={TABLE_CLASS}>
              <thead className={THEAD_CLASS}>
                <tr>
                  <th className={thClass()}>GW</th>
                  <th className={thClass(true)}>Fixtures</th>
                  <th className={thClass()}>Doubles</th>
                  <th className={thClass()}>Blanks</th>
                </tr>
              </thead>
              <tbody>
                {interesting.map((w) => (
                  <tr key={w.gw} className={TR_CLASS}
                      data-testid={`outlook-week-${w.gw}`}>
                    <td className={`${tdClass()} tn`}>GW{w.gw}</td>
                    <td className={`${tdClass(true)} text-text-secondary`}>
                      {w.fixtures}
                    </td>
                    {/* Rule 1: an extra fixture is a week going your way and
                        a blank is one going against you. */}
                    <td className={`${tdClass()} text-up`}>
                      {w.doubles.map(teamLabel).join(', ') || '—'}
                    </td>
                    <td className={`${tdClass()} text-down`}>
                      {w.blanks.map(teamLabel).join(', ') || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}

/** A club, named if the teams snapshot could be read and numbered if not.
 *  The raw id is shown rather than hidden: a count with an unnameable club in
 *  it is still a true count, and pretending the row is not there is worse. */
function teamLabel(team: { code: number; short_name: string | null }): string {
  return team.short_name ?? `#${team.code}`
}

/** θ per week beside the gain that week offers, aligned by index.
 *
 *  A compact strip rather than a chart: the question is "does any week ahead
 *  clear its bar", which is a row of comparisons, and the weeks are few. */
function ThetaTrack(
  { weeks, thetas }: {
    weeks: Array<{ gw: number; gain: number }>
    thetas: number[]
  },
) {
  if (weeks.length === 0) return null
  return (
    <div className="mt-1 flex flex-wrap gap-2" data-testid="theta-track">
      {weeks.map((w, i) => {
        const theta = thetas[i]
        const over = theta !== undefined && w.gain >= theta
        // Rule 1: clearing the bar is the direction the strip is read for;
        // a week under it is information and stays grey.
        return (
          <Chip key={w.gw}
                tone={over ? 'up' : 'neutral'}
                className="tn"
                title={theta === undefined
                  ? `GW${w.gw}: gain ${w.gain.toFixed(1)}`
                  : `GW${w.gw}: gain ${w.gain.toFixed(1)} against a bar of `
                    + theta.toFixed(1)}>
            {`GW${w.gw} ${w.gain.toFixed(1)}`}
          </Chip>
        )
      })}
    </div>
  )
}
