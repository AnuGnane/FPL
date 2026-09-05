import { describe, expect, it } from 'vitest'
import { difficultyBackground, difficultyTone } from './scale'

describe('difficultyBackground', () => {
  it('mixes toward up for an easy fixture', () => {
    expect(difficultyBackground(0.1)).toContain('var(--color-up)')
  })

  it('mixes toward down for a hard one', () => {
    expect(difficultyBackground(0.9)).toContain('var(--color-down)')
  })

  it('lands on the base colour at the midpoint', () => {
    expect(difficultyBackground(0.5)).toContain('0%')
  })

  it('clamps scores that arrive outside [0, 1]', () => {
    expect(difficultyBackground(-3)).toBe(difficultyBackground(0))
    expect(difficultyBackground(9)).toBe(difficultyBackground(1))
  })

  it('never paints a position hue', () => {
    for (const score of [0, 0.25, 0.5, 0.75, 1]) {
      expect(difficultyBackground(score)).not.toContain('--color-pos-')
    }
  })
})

describe('difficultyTone', () => {
  it('is up below .35, down above .65, grey between and for no rating', () => {
    expect(difficultyTone(0.1)).toBe('up')
    expect(difficultyTone(0.5)).toBe('neutral')
    expect(difficultyTone(0.9)).toBe('down')
    expect(difficultyTone(null)).toBe('neutral')
    expect(difficultyTone(NaN)).toBe('neutral')
  })
})
