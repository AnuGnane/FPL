import type { LadderPayload } from '../../types'

/** "1 free transfer · cap 2 hits" — the heading, and MovesCard's line.
 *
 *  Its own module (v17h §3): This Week prints the line beside the moves and
 *  the ladder card prints it above its table, and both now read the payload
 *  from the cache rather than one handing it to the other, so neither card
 *  should have to import the other to say it. */
export function capText(p: LadderPayload): string {
  const ft = p.free_transfers ?? 0
  const bits = [`${ft} free transfer${ft === 1 ? '' : 's'}`]
  const hits = p.cap.max_hits
  bits.push(hits === null || hits === undefined
    ? 'hits uncapped'
    : `cap ${hits} hit${hits === 1 ? '' : 's'}`)
  const moves = p.cap.max_transfers
  if (moves === 0) bits.push('bank')
  else if (moves !== null && moves !== undefined) {
    bits.push(`max ${moves} transfer${moves === 1 ? '' : 's'}`)
  }
  return bits.join(' · ')
}
