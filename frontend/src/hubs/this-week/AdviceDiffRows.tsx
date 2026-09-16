import { TONE_CLASS, fmtDelta, toneOf } from '../../kit'
import type { AdviceDiff } from '../../types'

/**
 * What one served plan says that another did not, as a sentence.
 *
 * Lifted out of `WhyPanel`'s "Since last run" strip in v19e §2.2 without a
 * character of its markup changing, because the History tab's week-against-
 * week comparison asks the same question of the same payload — and a second
 * wording of "buying X instead of Y" would be the one diff told two ways.
 * The strip keeps its own Callout and its own heading; only the sentence is
 * shared, since that is the only part both surfaces mean identically.
 */

/**
 * Mirrors `artifacts.EP_MOVER_THRESHOLD`, the server-side constant the movers
 * list is already filtered by. Repeated here only to name the number in the
 * sentence — the filtering happens once, on the server.
 */
const EP_MOVER_THRESHOLD = 0.5

export default function AdviceDiffRows({ diff }: { diff: AdviceDiff }) {
  const bits: string[] = []
  if (diff.buys_added.length || diff.buys_dropped.length) {
    const inNames = diff.buys_added.map((p) => p.name).join(', ') || 'nobody'
    const outNames = diff.buys_dropped.map((p) => p.name).join(', ')
      || 'nobody'
    bits.push(`buying ${inNames} instead of ${outNames}`)
  }
  if (diff.sells_added.length || diff.sells_dropped.length) {
    const inNames = diff.sells_added.map((p) => p.name).join(', ') || 'nobody'
    const outNames = diff.sells_dropped.map((p) => p.name).join(', ')
      || 'nobody'
    bits.push(`selling ${inNames} instead of ${outNames}`)
  }
  if (diff.captain_to) {
    bits.push(`captain ${diff.captain_from?.name ?? 'none'} → `
      + `${diff.captain_to.name}`)
  }
  if (diff.chip_to) bits.push(`now recommending ${diff.chip_to}`)
  if (diff.chip_from && !diff.chip_to) {
    bits.push(`no longer recommending ${diff.chip_from}`)
  }
  const movers = diff.ep_movers
  if (movers.length > 0) {
    const named = movers.slice(0, 3).map((m) => (
      `${m.name} ${m.delta >= 0 ? '+' : ''}${m.delta.toFixed(1)}`)).join(', ')
    const n = diff.ep_movers_count ?? movers.length
    bits.push(`${n} player${n === 1 ? '' : 's'} moved `
      + `${EP_MOVER_THRESHOLD} xPts or more in the retrain — ${named}`)
  }
  const delta = diff.expected_pts_delta
  return (
    <p className="mt-1 text-text-secondary">
      {bits.length === 0 ? 'The same plan.' : `${bits.join('; ')}.`}{' '}
      {/* Both ornaments below only mean anything against a previous run: a
          movers-only strip must not print a delta of 0.0 xPts. */}
      {diff.available && (
        <span className={`tn ${TONE_CLASS[toneOf(delta)]}`}>
          {fmtDelta(delta)} xPts
        </span>
      )}
    </p>
  )
}
