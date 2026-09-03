import { useEffect, useState } from 'react'
import { apiDelete, apiGet, apiPost, errorText } from '../../api/client'
import { Card, EmptyState, Loading, PlayerName } from '../../kit'
import type { WatchRow, WatchlistPanel } from '../../types'

/**
 * v12 W5 §6.3 — the starred players, with their notes.
 *
 * The endpoint has carried `note` and `set_at` since v8e and nothing has ever
 * rendered either, because the explorer's star posts `{ code, note: '' }` for
 * every click (`Players.tsx:83`). This is the only surface from which a note
 * can be written or read.
 *
 * `set_at` is labelled "noted" and not "watching since", and the caveat under
 * the table says why: `watchlist.watch` replaces *both* the note and the
 * timestamp on every star (`watchlist.py:107`), so re-starring from the
 * explorer wipes a note and resets the date. That is the store's behaviour,
 * not this view's to change — but a column headed "watching since" would be a
 * claim the data does not support.
 */

function stamp(iso: string): string {
  const at = new Date(iso)
  return Number.isNaN(at.getTime()) ? '—' : at.toISOString().slice(0, 10)
}

function Row(
  { row, onSaved, onRemoved }: {
    row: WatchRow
    onSaved: (panel: WatchlistPanel) => void
    onRemoved: (panel: WatchlistPanel) => void
  },
) {
  const [draft, setDraft] = useState(row.note)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  return (
    <div className="flex flex-col gap-1 border-b border-divider py-2">
      <div className="flex flex-wrap items-center gap-2">
        <PlayerName code={row.code} name={row.name} />
        <span className="text-text-faint">{`Noted ${stamp(row.set_at)}`}</span>
        <button
          type="button"
          className="ml-auto text-text-muted hover:text-text"
          disabled={busy}
          onClick={() => {
            setBusy(true)
            apiDelete<WatchlistPanel>(`/api/watchlist/${row.code}`)
              .then(onRemoved)
              .catch((e) => setError(errorText(e)))
              .finally(() => setBusy(false))
          }}
        >
          {`Unstar ${row.name}`}
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <input
          aria-label={`note for ${row.name}`}
          className="min-w-0 flex-1 rounded-card border border-border bg-base
                     px-2 py-1"
          value={draft}
          disabled={busy}
          onChange={(e) => setDraft(e.target.value)}
        />
        <button
          type="button"
          className="rounded-card border border-border bg-base px-2 py-1
                     text-text-secondary hover:text-text"
          disabled={busy}
          onClick={() => {
            setBusy(true)
            setError(null)
            apiPost<WatchlistPanel>('/api/watchlist',
              { code: row.code, note: draft })
              .then(onSaved)
              .catch((e) => setError(errorText(e)))
              .finally(() => setBusy(false))
          }}
        >
          {`Save note for ${row.name}`}
        </button>
      </div>
      {error && (
        <p data-testid={`watchlist-error-${row.code}`} className="text-rust">
          {error}
        </p>
      )}
    </div>
  )
}

export default function WatchlistTab(
  { onChange }: { onChange: (codes: number[]) => void },
) {
  const [panel, setPanel] = useState<WatchlistPanel | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    apiGet<WatchlistPanel>('/api/watchlist')
      .then(setPanel)
      .catch(() => setFailed(true))
  }, [])

  // Every write returns the whole panel, so the hub's star column and this
  // table are re-seeded from the same answer rather than from two guesses.
  function adopt(next: WatchlistPanel) {
    setPanel(next)
    onChange(next.rows.map((r) => r.code))
  }

  if (failed) {
    return (
      <EmptyState
        title="Watchlist unavailable"
        detail="The starred list could not be read. It lives in the tool's
                own store, not in FPL."
        action="Check that the app is running"
      />
    )
  }
  if (!panel) return <Loading />
  if (panel.rows.length === 0) {
    return (
      <EmptyState
        title="Nobody starred yet"
        detail="Star a player from the Explorer tab and he appears here with
                room for a note."
        action="Explorer → star"
      />
    )
  }

  return (
    <Card title="Watchlist">
      <div className="overflow-x-auto">
        {panel.rows.map((row) => (
          <Row key={row.code} row={row} onSaved={adopt} onRemoved={adopt} />
        ))}
      </div>
      <p data-testid="watchlist-caveat" className="mt-2 text-text-faint">
        {'Starring a player again from the Explorer replaces the note and the '
         + 'date, so edit notes here rather than re-starring.'}
      </p>
    </Card>
  )
}
