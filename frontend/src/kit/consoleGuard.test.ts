import { describe, expect, it } from 'vitest'
import {
  EXPECTED, assertExpected, isExpected, startConsoleGuard, stopConsoleGuard,
} from './consoleGuard'

// Holiday F-185: the families recorded on 2026-10-22, quoted as the libraries
// print them (the act text is React 18's format string). F-186 closed the act
// warnings at source, so that family is no longer expected.
const ROUTER = '⚠️ React Router Future Flag Warning: React Router will begin '
  + 'wrapping state updates in `React.startTransition` in v7.'
const ACT = 'Warning: An update to %s inside a test was not wrapped in act(...).'

describe('consoleGuard', () => {
  it('holds only the router family once the act warnings are closed', () => {
    expect(EXPECTED).toHaveLength(1)
    expect(isExpected(ROUTER)).toBe(true)
    expect(() => assertExpected([ROUTER])).not.toThrow()
  })

  it('fails a test that prints an act warning again', () => {
    expect(isExpected(ACT)).toBe(false)
    expect(() => assertExpected([ACT])).toThrow(/not wrapped in act/)
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
