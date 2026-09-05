import type { ChipTone } from './Chip'

/**
 * Fixture difficulty, on the meaning scale (rule 1: easy/hard is a
 * direction relative to the player). The server sends [0, 1]; the chip is
 * `up` below 0.35, `down` above 0.65, grey between — three words the eye
 * can tell apart at 10px, rather than a continuous ramp nobody could read.
 */
export function difficultyTone(score: number | null | undefined): ChipTone {
  if (typeof score !== 'number' || !Number.isFinite(score)) return 'neutral'
  if (score < 0.35) return 'up'
  if (score > 0.65) return 'down'
  return 'neutral'
}

/** Pre-v14 continuous ramp. Kept until the sweep has moved every fixture
 *  cell onto `difficultyTone` (Tasks 7, 10, 11); deleted in Task 12. */
export function difficultyBackground(score: number): string {
  const eased = Math.min(Math.max(score, 0), 1)
  return eased < 0.5
    ? `color-mix(in srgb, var(--color-up) ${
        Math.round((0.5 - eased) * 160)}%, var(--color-base))`
    : `color-mix(in srgb, var(--color-down) ${
        Math.round((eased - 0.5) * 160)}%, var(--color-base))`
}
