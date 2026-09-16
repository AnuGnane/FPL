import useNow from './useNow'

/** One minute: the smallest unit this ever prints, so the smallest tick that
 *  can change what it says (v19a §2.1). */
const TICK_MS = 60_000

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

/**
 * The deadline in the reader's own zone, to the minute.
 *
 * No seconds: a deadline is a wall-clock appointment, and a page that counts
 * down in minutes printing `18:30:00` claims a precision it is not refreshing
 * at. The locale is the browser's — the server serves an instant, and which
 * calendar words that instant wears is the reader's business.
 */
function stamp(at: Date): string {
  return at.toLocaleString(undefined, {
    weekday: 'short', day: 'numeric', month: 'short',
    hour: '2-digit', minute: '2-digit',
  })
}

/**
 * How long is left, in the two largest units that still say something.
 *
 * "2d 4h" over a day, "4h 12m" under one, "42 min" under an hour. Minutes
 * beside days would be false precision on a tick this slow, and hours alone
 * under an hour would round the last stretch — the one a reader is actually
 * watching — to zero.
 */
export function remainingText(ms: number): string {
  const minutes = Math.floor(ms / MINUTE)
  const hours = Math.floor(ms / HOUR)
  const days = Math.floor(ms / DAY)
  if (days >= 1) return `${days}d ${hours - days * 24}h`
  if (hours >= 1) return `${hours}h ${minutes - hours * 60}m`
  return `${minutes} min`
}

export interface CountdownProps {
  /** The served ISO instant the gameweek locks at. */
  deadline: string
  gw: number
  /** v19d §2.1: the remaining text alone, for the context strip. The strip is
   *  one line that already names the gameweek, and the absolute stamp beside
   *  it would be the deadline said twice on one page. */
  short?: boolean
}

/**
 * "2d 4h to the GW5 deadline · Fri 18 Sep 18:30" (v19a §2.1).
 *
 * This Week used to print the deadline *or* the staleness reason, so the one
 * page a reader opens to decide whether there is still time to act stopped
 * saying so exactly when the board went stale — the state in which the
 * question is most urgent. Both now have a home: the clock here, the reason
 * in the warn Callout below the header.
 */
export default function Countdown({ deadline, gw, short }: CountdownProps) {
  const now = useNow(TICK_MS)
  const at = new Date(deadline)
  const left = at.getTime() - now.getTime()
  // Its own testid, because This Week now prints two of these — the header's
  // full clock and the strip's short one — and a page with two "countdown"s
  // makes every existing assertion about the header ambiguous (v19d §2.1).
  if (short) {
    return (
      <span data-testid="countdown-short">
        {left <= 0 ? 'passed' : remainingText(left)}
      </span>
    )
  }
  return (
    <span data-testid="countdown">
      {left <= 0
        ? `deadline passed · ${stamp(at)}`
        : `${remainingText(left)} to the GW${gw} deadline · ${stamp(at)}`}
    </span>
  )
}
