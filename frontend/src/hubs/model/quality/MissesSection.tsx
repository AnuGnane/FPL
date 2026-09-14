import { usePageData } from '../../../api/pageData'
import {
  type Column, Card, DataTable, Loaded, PlayerName, PosBadge, fmtNum,
} from '../../../kit'
import type { MissRow, MissesData } from '../../../types'

/**
 * Cut from `QualityTab.tsx` in v18f §2.1 — the tab was a thousand lines with
 * a natural seam at its self-fetching sections. This one reads `/api/misses`
 * itself, so it moved with the column table and the card only it draws.
 */

const MISS_COLUMNS: Column<MissRow>[] = [
  { key: 'name', header: 'Player', primary: true, value: (r) => r.name,
    render: (r) => (
      <span className="flex items-center gap-1.5">
        <PlayerName code={r.code} name={r.name} />
        <PosBadge pos={r.position} variant="dot" />
      </span>
    ) },
  { key: 'price', header: 'Price', numeric: true, value: (r) => r.price,
    render: (r) => fmtNum(r.price, 1) },
  { key: 'ep', header: 'Forecast', primary: true, numeric: true,
    value: (r) => r.ep, render: (r) => fmtNum(r.ep) },
  { key: 'actual', header: 'Scored', primary: true, numeric: true,
    value: (r) => r.actual, render: (r) => r.actual },
  { key: 'minutes', header: 'Mins', numeric: true, value: (r) => r.minutes,
    render: (r) => r.minutes },
  { key: 'miss', header: 'Miss', primary: true, numeric: true,
    value: (r) => Math.abs(r.miss),
    // Over or under what the model forecast: a direction (rule 1).
    render: (r) => (
      <span className={r.miss >= 0 ? 'tn text-up' : 'tn text-down'}>
        {`${r.miss >= 0 ? '+' : ''}${r.miss.toFixed(1)}`}
      </span>
    ) },
]

/**
 * Who the model got most wrong last week.
 *
 * The aggregates above say the heads are calibrated in the mean, which is a
 * claim nobody can check against their own memory of the football. This is
 * the card a manager argues with, so it keeps both signs: an over-forecast is
 * a transfer the tool may have talked somebody into, an under-forecast is a
 * captaincy it talked them out of.
 */
export default function MissesSection() {
  // v18e §2.3, ruling 7: `.catch(() => setData(null))` made a server that
  // could not answer look exactly like a week nobody has scored — the card
  // simply was not there. No scored gameweek is still an absent card, because
  // that is the honest drawing of an artifact with nothing in it; a 500 now
  // says so.
  const page = usePageData<MissesData>('/api/misses')

  return (
    <Loaded
      page={page}
      // No scored gameweek is an absent card, not a card of zeros — and a
      // payload without a rows array is not a misses report at all, so render
      // nothing rather than crash the tab on an artifact an older version
      // half-wrote.
      isEmpty={(data) => !data.gw || !Array.isArray(data.rows)
        || data.rows.length === 0}
    >
      {(data) => <MissesCard data={data} />}
    </Loaded>
  )
}

function MissesCard({ data }: { data: MissesData }) {
  return (
    <Card title={`Biggest misses — GW${data.gw}`} className="mt-4">
      <p className="mb-3 text-text-muted">
        Forecast against what he actually scored, largest gap first. A positive
        miss is a player the model under-rated.
      </p>
      <DataTable
        columns={MISS_COLUMNS}
        rows={data.rows}
        rowKey={(r) => r.code}
        rowLabel={(r) => r.name}
        initialSort="miss"
        empty={<p className="text-text-muted">Nothing scored yet.</p>}
      />
    </Card>
  )
}
