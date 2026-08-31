import { useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import {
  Badge, Card, EmptyState, ExplainModal, Loading, PlayerCard, Stat,
  TONE_CLASS, fmtDelta, fmtNum, toneOf,
} from '../../kit'
import type {
  ReviewData, ReviewGw, ReviewLabel, ReviewLane, ReviewLaneName,
} from '../../types'

const LANE_ORDER: ReviewLaneName[] = ['transfers', 'captaincy', 'bench', 'chip']

const LANE_TITLE: Record<ReviewLaneName, string> = {
  transfers: 'Transfers',
  captaincy: 'Captaincy',
  bench: 'Bench order',
  chip: 'Chip',
}

// The bands are the spec's, pre-registered before any gameweek was graded.
// Aligned is deliberately neutral rather than green: following the model is
// not a good week, it is a week with nothing to learn from.
const LABEL_VARIANT: Record<ReviewLabel, 'positive' | 'negative' | 'neutral'> = {
  Brilliant: 'positive',
  Good: 'positive',
  Aligned: 'neutral',
  Inaccuracy: 'negative',
  Blunder: 'negative',
}

const NO_ADVICE = 'no surviving advice — this gameweek is graded on '
  + 'reconciliation and hindsight alone'

const LATE_RUN = 'every banked run of this gameweek was written after the '
  + 'deadline, so the model saw team news you could not act on'

/** A whole number as a string, or an em dash. `Stat` would render a raw
 *  number through `fmtNum` and print "61.0" for a points total. */
function num(value: number | null): string {
  return value === null || value === undefined ? '—' : String(value)
}

// The lanes stay text. `mine` and `model` are comma-joined name strings built
// server-side out of a set of players whose codes are discarded before the
// payload is written, so there is no code to open a modal with and matching a
// name back to one client-side would be a guess wearing a link (plan A6).
function LaneRow({ lane }: { lane: ReviewLane }) {
  const graded = lane.delta_pts !== null
  return (
    <div data-testid={`lane-${lane.lane}`} title={lane.note ?? undefined}
         className="flex flex-wrap items-baseline gap-2 py-1.5">
      <span className="w-28 text-text-muted">{LANE_TITLE[lane.lane]}</span>
      {lane.label ? (
        <Badge variant={LABEL_VARIANT[lane.label]}>{lane.label}</Badge>
      ) : <Badge variant="neutral">not graded</Badge>}
      <span className={`num ${TONE_CLASS[toneOf(lane.delta_pts)]}`}>
        {graded ? `${fmtDelta(lane.delta_pts, 0)} pts` : '—'}
      </span>
      <span className={`num text-xs ${TONE_CLASS[toneOf(lane.delta_pwin)]}`}>
        {/* An ungraded lane has no answer in either currency, whatever the
            server sent in this field. */}
        {!graded || lane.delta_pwin === null
          ? '—' : `${fmtDelta(lane.delta_pwin)} pp`}
      </span>
      <span className="text-xs text-text-faint">
        you {lane.mine ?? '—'} · model {lane.model ?? '—'}
      </span>
    </div>
  )
}

function GwCard({ row, onSelect }:
  { row: ReviewGw; onSelect: (code: number) => void }) {
  const lanes = LANE_ORDER
    .map((name) => row.lanes.find((lane) => lane.lane === name))
    .filter((lane): lane is ReviewLane => lane !== undefined)
  return (
    <Card
      title={`GW${row.gw}`}
      heading={(
        // `Card.title` is a string; rich heading content goes in `heading`,
        // which is what the h3 renders. The badges belong in the heading
        // because they qualify the whole gameweek, not one lane of it.
        <span className="inline-flex flex-wrap items-center gap-2">
          {`GW${row.gw}`}
          {row.post_deadline
            ? <Badge variant="negative" title={LATE_RUN}>late run</Badge>
            : null}
          {row.reconciled === false ? (
            <Badge variant="negative">
              {`did not reconcile — FPL says ${row.official_points}`}
            </Badge>
          ) : null}
        </span>
      )}
      className="mb-4"
    >
      <div className="mb-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {/* Every value is pre-formatted as a string: `Stat` runs a raw
            number through fmtNum, which would print a points total as
            "61.0". These are counts, not measurements. */}
        <Stat label="You" value={num(row.my_points)} />
        <Stat label="Model" value={num(row.model_points)} />
        <Stat label="Accuracy" value={num(row.accuracy)} />
        <Stat label="Bench" value={num(row.points_on_bench)} />
      </div>
      {row.no_advice
        ? <p className="text-sm text-text-muted">{NO_ADVICE}</p>
        : <div className="divide-y divide-divider">
            {lanes.map((lane) => <LaneRow key={lane.lane} lane={lane} />)}
          </div>}
      <p data-testid={`hindsight-${row.gw}`}
         className="mt-3 text-sm text-text-muted">
        {row.hindsight.points === null
          ? 'No legal eleven could be rebuilt from the fifteen you owned, so '
            + 'there is no hindsight comparison for this gameweek.'
          : `Best eleven you owned: ${row.hindsight.points} — you scored `
            + `${row.my_points ?? '—'}, so selection left `
            + `${row.hindsight.gap} on the table.`}
      </p>
      {row.misses.length > 0 && (
        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-sm
                        text-text-muted">
          <span>Flagged and skipped:</span>
          {row.misses.map((m) => (
            <span key={m.code} className="flex items-center gap-1">
              <PlayerCard
                size="chip"
                code={m.code}
                name={m.name}
                // The review payload names no position for a miss; the card
                // needs one only to pick the keeper's kit, and the plain shirt
                // is what a null team code draws anyway.
                position=""
                teamShort={null}
                teamCode={null}
                ep={null}
                onSelect={onSelect}
              />
              <span className="num">{`+${m.gain} over ${m.over}`}</span>
            </span>
          ))}
        </div>
      )}
      {row.notices.map((notice) => (
        <p key={notice} className="mt-1 text-xs text-text-faint">{notice}</p>
      ))}
    </Card>
  )
}

export default function ReviewTab() {
  const [data, setData] = useState<ReviewData | null>(null)
  // One modal for the whole tab rather than one per gameweek card.
  const [explain, setExplain] = useState<number | null>(null)

  useEffect(() => {
    apiGet<ReviewData>('/api/review').then(setData)
      .catch(() => setData({ gws: [], summary: null }))
  }, [])

  if (!data) return <Loading />
  if (data.gws.length === 0) {
    return (
      // `EmptyState` renders an unwired action as a shell command, so the
      // action is the command — "Review last week" is the label on the
      // hub's own JobButton, which sits above this tab and is the other way
      // to run exactly this.
      <EmptyState
        title="Nothing reviewed yet"
        detail="The review grades the decisions you made against the ones the
                model made before the same deadline, so it needs a gameweek
                whose results FPL has finalised. The hub's Review last week
                button runs the same thing."
        action="gaffer review"
      />
    )
  }

  return (
    <div>
      {data.summary && (
        <Card title="Season ledger" className="mb-4">
          <div className="mb-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {LANE_ORDER.map((name) => {
              const cell = data.summary!.lanes[name]
              return (
                <div key={name} data-testid={`season-${name}`}
                     className="rounded-card border border-border bg-card
                                px-4 py-3">
                  <p className="label">{LANE_TITLE[name]}</p>
                  <p className={`num mt-1 text-2xl
                                 ${TONE_CLASS[toneOf(cell?.pts ?? 0)]}`}>
                    {cell && cell.graded > 0 ? fmtDelta(cell.pts, 0) : '—'}
                  </p>
                  <p className="num mt-1 text-xs text-text-faint">
                    {cell && cell.graded > 0
                      ? `${fmtDelta(cell.pwin)} pp over ${cell.graded} GW`
                      : 'never graded'}
                  </p>
                </div>
              )
            })}
          </div>
          <p className="text-sm text-text-muted">
            {/* Both totals name the gameweeks they cover: a season of
                unbanked histories sums to zero, which is not a season of
                empty benches. */}
            Bench points this season: {data.summary.points_on_bench} over{' '}
            {data.summary.points_on_bench_gws} GW. Selection left{' '}
            {data.summary.hindsight_gap} on the table over{' '}
            {data.summary.hindsight_gap_gws} GW.{' '}
            {data.summary.unreconciled_gws > 0
              ? `${data.summary.unreconciled_gws} gameweek(s) did not
                 reconcile against FPL's own score.`
              : 'Every reviewed gameweek reconciles against FPL’s own '
                + 'score.'}
          </p>
          {data.summary.worst && (
            <p className="mt-1 text-sm text-text-muted">
              Worst single decision: GW{data.summary.worst.gw}{' '}
              {LANE_TITLE[data.summary.worst.lane]}{' '}
              {fmtNum(data.summary.worst.delta_pts, 0)} pts.
            </p>
          )}
        </Card>
      )}
      {[...data.gws].reverse().map((row) => (
        <GwCard key={row.gw} row={row} onSelect={setExplain} />
      ))}
      {explain !== null && (
        <ExplainModal code={explain} onClose={() => setExplain(null)} />
      )}
    </div>
  )
}
