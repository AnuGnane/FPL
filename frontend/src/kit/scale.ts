/**
 * Fixture difficulty, painted on the meaning scale.
 *
 * Difficulty arrives normalised to [0, 1] from the server, so the surface is
 * a straight mix between sage (easy) and rust (hard) through the card colour
 * at the midpoint. Two views used to disagree about this — the ticker drew a
 * raw green-to-red HSL ramp that belonged to no palette — so both now read
 * the same function and a 0.3 means the same shade wherever it is drawn.
 */
export function difficultyBackground(score: number): string {
  const eased = Math.min(Math.max(score, 0), 1)
  return eased < 0.5
    ? `color-mix(in srgb, var(--color-sage) ${
        Math.round((0.5 - eased) * 160)}%, var(--color-card))`
    : `color-mix(in srgb, var(--color-rust) ${
        Math.round((eased - 0.5) * 160)}%, var(--color-card))`
}
