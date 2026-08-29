// Every number the UI prints goes through here. A hub that reads a partial
// artifact will hand a component null, undefined or NaN sooner or later, and
// "NaN" on screen is the failure mode spec §9 forbids.
const DASH = '—'

function finite(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

export function fmtNum(value: number | null | undefined, dp = 1): string {
  return finite(value) ? value.toFixed(dp) : DASH
}

export function fmtPct(value: number | null | undefined): string {
  return finite(value) ? `${Math.round(value * 100)}%` : DASH
}

export function fmtPrice(tenths: number | null | undefined): string {
  return finite(tenths) ? (tenths / 10).toFixed(1) : DASH
}

export function fmtDelta(value: number | null | undefined, dp = 1): string {
  if (!finite(value)) return DASH
  return value > 0 ? `+${value.toFixed(dp)}` : value.toFixed(dp)
}

export type Tone = 'positive' | 'negative' | 'neutral'

export function toneOf(value: number | null | undefined): Tone {
  if (!finite(value) || value === 0) return 'neutral'
  return value > 0 ? 'positive' : 'negative'
}

export const TONE_CLASS: Record<Tone, string> = {
  positive: 'text-sage',
  negative: 'text-rust',
  neutral: 'text-text-muted',
}
