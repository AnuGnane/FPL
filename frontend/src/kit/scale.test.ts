import { describe, expect, it } from 'vitest'
import { difficultyBackground } from './scale'

describe('difficultyBackground', () => {
  it('mixes toward sage for an easy fixture', () => {
    expect(difficultyBackground(0.1)).toContain('var(--color-sage)')
  })

  it('mixes toward rust for a hard one', () => {
    expect(difficultyBackground(0.9)).toContain('var(--color-rust)')
  })

  it('lands on the card colour at the midpoint', () => {
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
