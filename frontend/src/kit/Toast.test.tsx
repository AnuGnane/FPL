import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ToastOutlet, {
  DISMISS_MS, MAX_TOASTS, currentToasts, resetToasts, toast,
} from './Toast'

beforeEach(() => { resetToasts(); vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers(); resetToasts() })

describe('Toast', () => {
  it('announces politely rather than interrupting', () => {
    render(<ToastOutlet />)
    act(() => { toast('positive', 'Pinned Haaland.') })
    // Polite, not assertive: an acknowledgement must not cut across whatever
    // a screen reader is in the middle of saying.
    expect(screen.getByTestId('toast-outlet'))
      .toHaveAttribute('aria-live', 'polite')
    expect(screen.getByText('Pinned Haaland.')).toBeInTheDocument()
  })

  it('keeps the newest three and drops the oldest', () => {
    render(<ToastOutlet />)
    act(() => {
      for (const n of [1, 2, 3, 4]) toast('negative', `failure ${n}`)
    })
    expect(screen.getAllByTestId('toast')).toHaveLength(MAX_TOASTS)
    // The oldest goes, not the newest: a burst of failures should leave the
    // three most recent on screen, and the first one is the least useful.
    expect(screen.queryByText('failure 1')).not.toBeInTheDocument()
    expect(screen.getByText('failure 4')).toBeInTheDocument()
  })

  it('dismisses itself', () => {
    render(<ToastOutlet />)
    act(() => { toast('positive', 'Saved.') })
    act(() => { vi.advanceTimersByTime(DISMISS_MS + 1) })
    expect(screen.queryByTestId('toast')).not.toBeInTheDocument()
  })

  it('is a no-op, not a crash, with no outlet mounted', () => {
    // PinDialog and OverridesCard are rendered bare by their own suites, with
    // no AppShell anywhere (plan A7). A toast raised there must be silent.
    expect(() => toast('negative', 'nobody is listening')).not.toThrow()
    expect(currentToasts()).toHaveLength(1)
  })

  it('does not let an old timer dismiss a later toast with a recycled id',
    () => {
      // The reviewer's flake, reproduced. Raise a toast, let the suite reset
      // between cases *without* the timer firing, then raise another: if ids
      // restarted at 1 and the first timer were still pending, it would land
      // on the second toast and clear a message nobody had read.
      render(<ToastOutlet />)
      act(() => { toast('positive', 'from the earlier test') })
      act(() => { vi.advanceTimersByTime(DISMISS_MS / 2) })
      act(() => { resetToasts() })

      act(() => { toast('negative', 'from the later test') })
      // Past the moment the first toast's timer would have fired.
      act(() => { vi.advanceTimersByTime(DISMISS_MS / 2 + 100) })
      expect(screen.getByText('from the later test')).toBeInTheDocument()
      // And it still expires on its own schedule.
      act(() => { vi.advanceTimersByTime(DISMISS_MS) })
      expect(screen.queryByTestId('toast')).not.toBeInTheDocument()
    })

  it('cancels the timer of a toast the cap pushed off the end', () => {
    render(<ToastOutlet />)
    act(() => { for (const n of [1, 2, 3, 4]) toast('negative', `f${n}`) })
    // f1 was dropped by the cap; its pending dismissal must not survive to
    // fire against an id that is live by then.
    act(() => { vi.advanceTimersByTime(DISMISS_MS + 1) })
    expect(currentToasts()).toHaveLength(0)
  })
})
