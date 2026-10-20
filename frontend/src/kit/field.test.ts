/**
 * Holiday F-153 — the input class (spec §5): input surface, hairline, the
 * control radius, accent border on focus and 28px tall like a button.
 */
import { describe, expect, it } from 'vitest'
import { INPUT_CLASS } from './field'

const classes = INPUT_CLASS.split(/\s+/)

describe('INPUT_CLASS', () => {
  it('is 28px tall on the input surface with a hairline', () => {
    expect(classes).toEqual(expect.arrayContaining(
      ['h-7', 'bg-input', 'border', 'border-border', 'rounded-ctl']))
  })

  it('takes the accent border on focus instead of an outline', () => {
    expect(classes).toEqual(expect.arrayContaining(
      ['focus:border-accent', 'focus:outline-none']))
  })
})
