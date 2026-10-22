import { describe, expect, it } from 'vitest'
import {
  EXPECTED, assertExpected, isExpected, startConsoleGuard, stopConsoleGuard,
} from './consoleGuard'

// Holiday F-185: the families recorded on 2026-10-22, quoted as the libraries
// print them (the act text is React 18's format string). F-186 closed the act
// warnings at source and F-187 set the router's future flags, so neither is
// expected any more and either one returning fails its test.
const ROUTER = '⚠️ React Router Future Flag Warning: React Router will begin '
  + 'wrapping state updates in `React.startTransition` in v7.'
const ACT = 'Warning: An update to %s inside a test was not wrapped in act(...).'

describe('consoleGuard', () => {
  it('expects nothing once both recorded families are closed', () => {
    expect(EXPECTED).toEqual([])
    expect(() => assertExpected([])).not.toThrow()
  })

  it('fails a test that prints an act warning again', () => {
    expect(isExpected(ACT)).toBe(false)
    expect(() => assertExpected([ACT])).toThrow(/not wrapped in act/)
  })

  it('fails a test that prints the router future-flag notice again', () => {
    expect(isExpected(ROUTER)).toBe(false)
    expect(() => assertExpected([ROUTER])).toThrow(/Future Flag Warning/)
  })

  it('does not expect an arbitrary message', () => {
    expect(isExpected('unexpected')).toBe(false)
    expect(() => assertExpected(['unexpected'])).toThrow(/unexpected/)
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
