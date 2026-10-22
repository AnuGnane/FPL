import { describe, expect, it } from 'vitest'
import {
  EXPECTED, assertExpected, isExpected, startConsoleGuard, stopConsoleGuard,
} from './consoleGuard'

// Holiday F-185: the two families recorded on 2026-10-22, quoted as the
// libraries print them (the act text is React 18's format string).
const ROUTER = '⚠️ React Router Future Flag Warning: React Router will begin '
  + 'wrapping state updates in `React.startTransition` in v7.'
const ACT = 'Warning: An update to %s inside a test was not wrapped in act(...).'

describe('consoleGuard', () => {
  it('holds exactly the two families recorded when it landed', () => {
    expect(EXPECTED).toHaveLength(2)
    expect(isExpected(ROUTER)).toBe(true)
    expect(isExpected(ACT)).toBe(true)
    expect(() => assertExpected([ROUTER, ACT])).not.toThrow()
  })

  it('does not expect a message outside those families', () => {
    expect(isExpected('unexpected')).toBe(false)
    expect(() => assertExpected([ROUTER, 'unexpected'])).toThrow(/unexpected/)
  })

  it('fails a test that writes an unexpected console error', () => {
    // The setup file's beforeEach has started the guard; this ends it the way
    // its afterEach does, then starts it again so that hook sees a clean slate.
    expect(() => {
      console.error('unexpected')
      stopConsoleGuard()
    }).toThrow(/unexpected console output.*unexpected/)
    startConsoleGuard()
  })
})
