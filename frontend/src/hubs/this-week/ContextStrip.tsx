import { Countdown, fmtNum } from '../../kit'

/**
 * The week in one line, and a way down the page (v19d §2.1).
 *
 * This Week is about four thousand pixels at 1400 wide with nothing sticky in
 * it, so the four facts a reader came for — which gameweek, how long is left,
 * who has the armband, how many moves — leave the screen as soon as they start
 * reading, and the only way to the news at the bottom is the scrollbar.
 *
 * No negative margins, deliberately: `AppShell`'s `<main>` is `p-4` on a
 * phone and `p-6` above it, and Players widens it further, so a `-mx-*` that
 * had to track three paddings to stay flush is a bug waiting on a fourth.
 * `sticky top-0` with the page's own background under it reads the same — the
 * strip spans exactly the column the cards do, and nothing scrolls past it in
 * the gutters because the gutters are empty.
 */
export interface ContextStripProps {
  gw: number
  /** The served ISO instant the gameweek locks at. */
  deadline: string
  captain: string
  /** How many players the plan buys — the count the reader acts on. */
  moves: number
  /** Expected XI points, as the stat tile above prints them. */
  pts: number
}

/** The page's sections, in the order the page draws them; the `id`s are the
 *  ones `ThisWeek` sets on the `Card`s. */
const SECTIONS: Array<[string, string]> = [
  ['squad', 'Squad'],
  ['moves', 'Moves'],
  ['ladder', 'Ladder'],
  ['brief', 'Brief'],
  ['why', 'Why'],
  ['news', 'News'],
]

export default function ContextStrip(
  { gw, deadline, captain, moves, pts }: ContextStripProps,
) {
  return (
    <div
      data-testid="context-strip"
      className="sticky top-0 z-10 mb-4 flex flex-wrap items-center
                 justify-between gap-x-4 gap-y-1 border-b border-border
                 bg-base py-1.5 text-[13px] text-text-secondary"
    >
      <span className="tn">
        {`GW${gw} · `}
        <Countdown deadline={deadline} gw={gw} short />
        {` · captain ${captain} · ${moves} move${moves === 1 ? '' : 's'}`}
        {` · ${fmtNum(pts)} pts`}
      </span>
      <nav aria-label="On this page" className="flex flex-wrap gap-x-3">
        {SECTIONS.map(([id, label]) => (
          <a key={id} href={`#${id}`}
             className="text-text-muted hover:text-text">
            {label}
          </a>
        ))}
      </nav>
    </div>
  )
}
