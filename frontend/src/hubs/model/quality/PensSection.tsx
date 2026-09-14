import { usePageData } from '../../../api/pageData'
import {
  type Column, Callout, Card, Chip, DataTable, EmptyState, Stat, StatRow,
  fmtNum, fmtPct,
} from '../../../kit'
import type { PenTrackerData, PenTrackerGw } from '../../../types'

/**
 * Cut from `QualityTab.tsx` in v18f §2.1 — the tab was a thousand lines with
 * a natural seam at its self-fetching sections. This one reads `/api/pens`
 * itself, so it moved with `InstrumentCell` and the column table nothing else
 * uses.
 */

// The instrument is the first thing to read on a pen row: an xg-gap week
// counts penalties, a pens_missed_only week can only see the ones that were
// missed, so every number beside it is a floor rather than a count.
function InstrumentCell({ row }: { row: PenTrackerGw }) {
  if (row.error) {
    return (
      <span className="text-text-muted" title={row.error}>unreadable</span>
    )
  }
  if (row.instrument === 'pens_missed_only') {
    // A floor is doubt about the count, not a bad number (rule 2).
    return (
      <Chip tone="warn"
            title="counted from missed penalties only — converted spot kicks
                   are invisible, so every count on this row is a floor">
        floor
      </Chip>
    )
  }
  return <Chip>{row.instrument ?? '—'}</Chip>
}

const PEN_COLUMNS: Column<PenTrackerGw>[] = [
  { key: 'gw', header: 'GW', primary: true, value: (r) => r.gw,
    render: (r) => (
      <span className={r.error ? 'tn text-text-muted' : 'tn text-text'}>
        GW{r.gw}
      </span>
    ) },
  { key: 'instrument', header: 'Instrument', primary: true,
    value: (r) => (r.error ? 'unreadable' : r.instrument ?? '—'),
    render: (r) => <InstrumentCell row={r} /> },
  { key: 'covered_rows', header: 'Covered', numeric: true,
    value: (r) => r.covered_rows ?? null,
    render: (r) => fmtNum(r.covered_rows, 0) },
  { key: 'pens_taken', header: 'Pens', primary: true, numeric: true,
    value: (r) => r.pens_taken ?? null,
    render: (r) => fmtNum(r.pens_taken) },
  { key: 'taker_hit_rate', header: 'Hit rate', numeric: true,
    value: (r) => r.taker_hit_rate ?? null,
    render: (r) => fmtPct(r.taker_hit_rate) },
]

/**
 * The v6 penalty term, measured forward. Its own fetch, like every other
 * section here: the tracker is a separate artifact with its own "not written
 * yet" state, and folding it into /api/quality would make one missing file
 * blank the other's page.
 */
export default function PensSection() {
  // v18e §2.3. The status split this section already made by hand — 422 is
  // "nobody has run it yet", anything else is a server that cannot answer,
  // said in this card and no louder because the page above still has its
  // numbers — is exactly `Loaded`'s, so it is spelt with the hook's status
  // rather than by re-reading the exception.
  const page = usePageData<PenTrackerData>('/api/pens')
  const absent = page.status === 404 || page.status === 422

  if (page.error !== null && !absent) {
    return (
      <Card title="Penalty term unavailable" className="mt-4">
        {/* A read the server refused, in `down` ink (plan R4). */}
        <Callout tone="error">{page.error}</Callout>
      </Card>
    )
  }
  if (page.error !== null) {
    return (
      <EmptyState
        title="No penalty tracker yet"
        // The server's own sentence for why there is nothing to show.
        detail={page.error}
        action="gaffer track-pens"
      />
    )
  }
  const data = page.data
  // A payload without a gws array is not a tracker: render nothing rather
  // than crash the tab on an artifact half-written by an older version.
  if (!data || !Array.isArray(data.gws)) return null

  const totals = data.season_totals ?? {}
  return (
    <Card title={`Penalty term — ${data.season || 'season unknown'}`}
          className="mt-4">
      <StatRow>
        <Stat label="Pens taken" value={fmtNum(totals.pens_taken)} />
        <Stat label="Taker hit rate" value={fmtPct(totals.taker_hit_rate)} />
        <Stat
          label="Pens / team-game"
          value={`${fmtNum(totals.pens_per_team_game, 3)} vs `
            + `${fmtNum(totals.league_pens_pg_served, 2)} served`}
        />
        <Stat
          label="Predicted EP / realized"
          value={`${fmtNum(totals.predicted_ep_pen_taker)} / `
            + `${fmtNum(totals.realized_pen_points)}`}
        />
      </StatRow>
      <DataTable
        columns={PEN_COLUMNS}
        rows={data.gws}
        rowKey={(r) => r.gw}
        rowLabel={(r) => `GW${r.gw}`}
        initialSort="gw"
        empty={<p className="text-text-muted">No finished gameweek yet.</p>}
      />
      {data.notes.map((note) => (
        <p key={note} className="mt-2 text-text-faint">{note}</p>
      ))}
    </Card>
  )
}
