import { Card } from '../../../kit'
import type { CurrentEvaluation } from '../../../types'
import { Reliability } from './shared'
import StratifiedTableView from './StratifiedTableView'

// Cut from `QualityTab.tsx` in v19h §2.1: the tab was 546 lines of
// hand tables, and a section nobody can find is a section nobody checks.
// Markup and class strings are the v18f ones, byte for byte — the Model
// screenshot pair is the proof.

const HEADS: Array<[string, string]> = [
  ['p_play', 'P(plays)'],
  ['p60', 'P(60+ minutes)'],
  // v8a has emitted this since the trichotomy landed and nothing rendered it.
  // p_play is a sum of two modes, so a model that sharpens the start/cameo
  // split while leaving the sum alone is invisible in the two above.
  ['p_start', 'P(starts)'],
  ['cs', 'P(clean sheet)'],
]

// The holdout run: the stratified table beside its two baselines, and the
// reliability curve of every probability head that run banked.
export default function HoldoutSection(
  { current }: { current: CurrentEvaluation },
) {
  return (
    <>
      <Card title="Holdout" className="mb-4">
        <p className="mb-3 text-text-muted">
          Last-10-slot holdout, {current.holdout_slots} gameweeks, sha{' '}
          {current.git_sha}, run {current.run_at}.
        </p>
        <StratifiedTableView
          columns={[
            ['Model (all)', current.stratified.all ?? {}],
            ['Model (starters)', current.stratified.starters ?? {}],
            ['Last-5 mean', current.baselines.last5 ?? {}],
            ['Last-38 mean', current.baselines.last38_ppg ?? {}],
          ]}
        />
      </Card>
      <Card title="Calibration" className="mb-4">
        {/* Named apart from "Calibration by gameweek" below, which grades the
            probabilities the weekly run actually served. This one is the
            holdout. */}
        <p className="mb-3 text-text-muted">
          From the holdout run above, not the weeks actually served.
        </p>
        {HEADS.map(([key, label]) => {
          const head = current.heads[key]
          return head === undefined ? null
            : <Reliability key={key} label={label} head={head} />
        })}
      </Card>
    </>
  )
}
