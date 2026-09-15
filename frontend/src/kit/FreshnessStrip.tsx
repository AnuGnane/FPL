import { Link } from 'react-router-dom'
import { usePageData } from '../api/pageData'
import type { Freshness, FreshnessRow } from '../types'
import Loaded from './Loaded'

const LABELS: Record<string, string> = {
  refresh: 'data', odds: 'odds', field: 'field EO',
  advise: 'advice', backup: 'backup', prices: 'prices',
  snapshot: 'availability',
}

/** What a source the server does not describe is assumed to run at (v19a
 *  §2.2). Daily is the safer guess of the two: it calls an old file stale
 *  rather than calling a stale one fine. */
const DEFAULT_CADENCE = 24

/** Where a reader goes to find out which job stopped (v19a §2.2). */
export const HEALTH_PATH = '/model?tab=health'

/**
 * Grey inside one cadence (information), amber inside two (doubt, rule 2),
 * down beyond (behind where it should be, rule 1), faint for never.
 *
 * v19a §2.2: the ratio, not the hours. Absolute thresholds asked one question
 * of every source and got both answers wrong — a 90-hour-old nightly price
 * bank has missed three runs and read amber, and a 90-hour-old weekly advice
 * artifact is doing exactly what it should and read down.
 *
 * `null` is checked before the number and not folded into it: "never" and
 * "very old" are different states, and a ratio branch would paint a cold
 * clone red as if something had gone wrong rather than not yet happened.
 */
export function tone(age: number | null, cadence: number): string {
  if (age === null) return 'text-text-faint'
  const ratio = age / cadence
  if (ratio < 1) return 'text-text-muted'
  if (ratio < 2) return 'text-warn'
  return 'text-down'
}

export function ageText(age: number | null): string {
  if (age === null) return 'never'
  if (age < 1) return 'just now'
  if (age < 48) return `${Math.round(age)}h`
  return `${Math.round(age / 24)}d`
}

export default function FreshnessStrip() {
  // v18e §2.3, ruling 7. The `.catch(() => setRows([]))` here was the worst
  // of the nine synthesised empties, because this strip is on every page: a
  // server that could not be asked drew five greys reading "never", which is
  // the strip saying nothing is stale. A cold clone with no artifacts at all
  // (404 or 422) still draws nothing rather than a red line across the top of
  // every page; anything else is one error callout where the strip goes.
  const page = usePageData<Freshness>('/api/meta/freshness')

  return (
    <Loaded page={page} isEmpty={(data) => data.rows.length === 0}>
      {(data) => <Strip rows={data.rows} />}
    </Loaded>
  )
}

function Strip({ rows }: { rows: FreshnessRow[] }) {
  const known = new Map<string, FreshnessRow>(rows.map((r) => [r.source, r]))
  return (
    <div
      data-testid="freshness-strip"
      // `role="status"` rather than `alert`: this is ambient state on every
      // page, and an assertive live region would interrupt a screen reader on
      // every navigation. The per-cell label carries the age in words because
      // the colour is the only other thing saying it, and colour is not a
      // thing every reader has.
      role="status"
      aria-label="data freshness"
      className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]
                 text-text-muted"
    >
      <span className="text-text-faint">as of</span>
      {/* Driven by LABELS rather than by `rows`, so an older server or a
          payload that lost a row still renders seven greys — a shorter strip
          is a strip nobody notices is shorter. */}
      {Object.entries(LABELS).map(([source, label]) => {
        const row = known.get(source)
        const age = row?.age_hours ?? null
        const cls = tone(age, row?.cadence_hours ?? DEFAULT_CADENCE)
        // v19a §2.2. A cell that has gone amber or red has just told the
        // reader a job has stopped and left them nowhere to go; Health is
        // where the plists and their last runs are. The fresh cells stay
        // spans: a link on every one of the seven would make the strip look
        // like a nav bar, and six of them would lead somewhere that had
        // nothing to say.
        const stale = cls === 'text-warn' || cls === 'text-down'
        const cell = {
          className: cls,
          title: row?.modified_at ?? 'never run',
          'aria-label': `${label} last updated ${ageText(age)}`,
          'data-testid': `freshness-${source}`,
        }
        return (
          <span key={source} className="whitespace-nowrap">
            {`${label} `}
            {stale
              ? <Link to={HEALTH_PATH} {...cell}>{ageText(age)}</Link>
              : <span {...cell}>{ageText(age)}</span>}
          </span>
        )
      })}
    </div>
  )
}
