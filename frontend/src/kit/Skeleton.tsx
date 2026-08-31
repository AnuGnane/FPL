import Card from './Card'

export interface SkeletonProps {
  /** The card's own title, when the frame the data will fill has one. */
  title?: string
  /** How many bars. Roughly the number of rows the answer will have. */
  lines?: number
  /** What is being waited on. Read out; never drawn. */
  label?: string
  className?: string
  /**
   * Draw the bars alone, with no `Card` around them, for a panel that is
   * already inside a card of its own — `SensitivityCard` replaces its body
   * rather than itself, and a card nested in a card is two borders for one
   * idea.
   */
  bare?: boolean
}

/**
 * The job-wait state.
 *
 * `Loading` is the fetch-wait state and stays exactly what it is (plan A8):
 * a sentence in a card, right for the eighty milliseconds a GET takes. A
 * solve is tens of seconds, and a static sentence held for that long reads as
 * a hang — so the panel a job will fill gets pulsing bars in the shape of the
 * answer instead, and the answer replaces them in the same frame rather than
 * appearing below a line of text that then vanishes.
 *
 * The bars are decorative and hidden from assistive technology; the label is
 * the only thing announced, and it goes through `role="status"` so it is read
 * politely when it appears.
 */
export default function Skeleton({
  title, lines = 3, label = 'Working…', className = 'mb-4', bare = false,
}: SkeletonProps) {
  const bars = (
    <div data-testid="skeleton" role="status" className="flex flex-col gap-2">
      <span className="sr-only">{label}</span>
      {Array.from({ length: lines }, (_, i) => (
        <span
          key={i}
          aria-hidden
          data-testid="skeleton-bar"
          className="block h-3 animate-pulse rounded-card bg-base"
          // Ragged rather than uniform: a stack of identical bars reads as a
          // component, and a stack of unequal ones reads as text about to
          // arrive. The width only ever shrinks, so the block stays a block.
          style={{ width: `${Math.max(40, 100 - i * 12)}%` }}
        />
      ))}
    </div>
  )
  if (bare) return bars
  return (
    <Card title={title} className={className}>
      {bars}
    </Card>
  )
}
