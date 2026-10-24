import { describe, expect, it } from 'vitest'
import { defined } from './defined'

describe('defined', () => {
  it('returns a present value and throws on a missing one, naming it', () => {
    expect(defined(0, 'zero')).toBe(0)
    expect(() => defined(null, 'the rung row')).toThrow('expected the rung row to be defined')
    expect(() => defined(undefined, 'the rung row')).toThrow('expected the rung row to be defined')
  })
})
