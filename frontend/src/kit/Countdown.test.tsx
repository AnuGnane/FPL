import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Countdown from './Countdown'

// v19a §2.1. Every claim here is about a duration, so the clock is frozen and
// `Date` is faked with the timers — a countdown tested against the real wall
// clock asserts a different number every time it runs.
const FAKE_TIMERS = ['setTimeout', 'setInterval', 'clearTimeout',
  'clearInterval', 'Date'] as const

const DEADLINE = '2026-09-18T17:30:00Z'

let consoleError: ReturnType<typeof vi.spyOn>

function at(iso: string) {
  vi.setSystemTime(new Date(iso))
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: [...FAKE_TIMERS] })
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  const unwrapped = consoleError.mock.calls.filter(
    ([first]) => typeof first === 'string' && first.includes('act('))
  consoleError.mockRestore()
  vi.useRealTimers()
  // The rail this file borrows from `api/useJob.test.tsx`: a tick that lands
  // outside `act` is a render React has not settled, and the assertion after
  // it is reading a frame that never existed.
  expect(unwrapped).toEqual([])
})

describe('the countdown', () => {
  it('reads days and hours when the deadline is more than a day away', () => {
    at('2026-09-16T13:30:00Z')
    render(<Countdown deadline={DEADLINE} gw={5} />)
    expect(screen.getByTestId('countdown'))
      .toHaveTextContent(/^2d 4h to the GW5 deadline · /)
  })

  it('reads hours and minutes inside the last day', () => {
    at('2026-09-18T13:18:00Z')
    render(<Countdown deadline={DEADLINE} gw={5} />)
    expect(screen.getByTestId('countdown'))
      .toHaveTextContent(/^4h 12m to the GW5 deadline · /)
  })

  it('reads bare minutes inside the last hour', () => {
    at('2026-09-18T16:48:00Z')
    render(<Countdown deadline={DEADLINE} gw={5} />)
    expect(screen.getByTestId('countdown'))
      .toHaveTextContent(/^42 min to the GW5 deadline · /)
  })

  it('says the deadline passed rather than counting upwards', () => {
    // The moment itself is past, not "0 min": a reader who can no longer act
    // must be told that, and a zero reads as "just", which is the opposite.
    at('2026-09-18T17:30:00Z')
    render(<Countdown deadline={DEADLINE} gw={5} />)
    expect(screen.getByTestId('countdown')).toHaveTextContent(/^deadline passed · /)
    expect(screen.getByTestId('countdown')).not.toHaveTextContent('GW5')
  })

  it('still names the absolute time once the deadline has passed', () => {
    at('2026-09-19T09:00:00Z')
    render(<Countdown deadline={DEADLINE} gw={5} />)
    const text = screen.getByTestId('countdown').textContent ?? ''
    expect(text).toMatch(/Fri/)
    expect(text).toMatch(/Sep/)
    expect(text).toMatch(/18/)
    // To the minute. A page that re-renders once a minute printing seconds
    // claims a precision it does not keep.
    expect(text).not.toMatch(/:\d\d:\d\d/)
  })

  it('moves on its own a minute later', () => {
    at('2026-09-18T16:48:00Z')
    render(<Countdown deadline={DEADLINE} gw={5} />)
    expect(screen.getByTestId('countdown')).toHaveTextContent('42 min')
    act(() => { vi.advanceTimersByTime(60_000) })
    expect(screen.getByTestId('countdown')).toHaveTextContent('41 min')
  })

  it('stops ticking when the page that held it goes away', () => {
    at('2026-09-18T16:48:00Z')
    const { unmount } = render(<Countdown deadline={DEADLINE} gw={5} />)
    unmount()
    // An interval left running after the unmount sets state on a component
    // that is gone, which React reports through `console.error` — the spy the
    // afterEach reads.
    act(() => { vi.advanceTimersByTime(600_000) })
    expect(vi.getTimerCount()).toBe(0)
  })
})
