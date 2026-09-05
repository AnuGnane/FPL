import { describe, expect, it } from 'vitest'
import { difficultyTone } from './scale'

describe('difficultyTone', () => {
  it('is up below .35, down above .65, grey between and for no rating', () => {
    expect(difficultyTone(0.1)).toBe('up')
    expect(difficultyTone(0.5)).toBe('neutral')
    expect(difficultyTone(0.9)).toBe('down')
    expect(difficultyTone(null)).toBe('neutral')
    expect(difficultyTone(NaN)).toBe('neutral')
  })
})
