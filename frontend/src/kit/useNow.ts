import { useEffect, useState } from 'react'

/**
 * The wall clock, re-read on an interval (v19a §2.1).
 *
 * A component that renders a duration is stale the moment it has rendered,
 * and nothing else on the page will re-render it: the payload behind This
 * Week does not change between deadlines, so without a tick of its own the
 * countdown reads whatever it read when the tab was opened. The hook rather
 * than an effect inside `Countdown` because a second reader is already
 * coming (v19d's sticky strip wants the same minute), and two intervals
 * measuring the same thing drift apart.
 */
export default function useNow(ms: number): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), ms)
    return () => window.clearInterval(timer)
  }, [ms])
  return now
}
