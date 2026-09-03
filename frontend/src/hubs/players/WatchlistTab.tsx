import { useEffect, useRef, useState } from 'react'
import { apiDelete, apiGet, apiPost, errorText } from '../../api/client'
import { Card, EmptyState, Loading, PlayerName } from '../../kit'
import type { WatchRow, WatchlistPanel } from '../../types'

/**
 * v12 W5 §6.3 — the starred players, with their notes.
 *
 * The endpoint has carried `note` and `set_at` since v8e and nothing had ever
 * rendered either. This is the only surface that *writes* one: the explorer's
 * ☆ posts `{ code }` with no note at all, which the store reads as "say
 * nothing about the note" and leaves the row's note and date alone.
 *
 * It did not always. The star used to post `note: ''`, and `''` was the same
 * request as "no note", so one click on the explorer's ☆ destroyed a sentence
 * typed here. The tri-state on `WatchRequest.note` is the fix, and it is
 * server-side, because a second tab, a second device and a failed watchlist
 * read all reach the same click.
 *
 * `set_at` is still labelled "Noted" and not "watching since": a *write* —
 * `''` or text — stamps the row with the time it happened, so the date is
 * when the note was last touched and not when the star went on.
 *
 * Each row seeds its field from the panel it was mounted with and keeps the
 * manager's typing thereafter, so a note changed by another surface while
 * this tab is open shows up on the next mount rather than under the cursor.
 * Radix unmounts inactive tab content, so that is the next visit to the tab.
 * Remounting rows on every write would be the alternative, and it would throw
 * away a half-typed note to display a value nobody in front of the screen
 * changed.
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
  const saveRef = useRef<HTMLButtonElement>(null)
  const restore = useRef(false)

  // `disabled` on the control that has focus drops focus to `<body>`, and a
  // keyboard user's next Tab then starts again from the top of the page.
  // Focus is returned once the button is enabled again — in an effect and not
  // in the promise's `.finally`, because at that moment React has not
  // re-rendered and `focus()` on a still-disabled button does nothing.
  //
  // Only when focus is nowhere: if the manager moved on during the write —
  // to the next row's field, say — taking it back would be this view typing
  // over him, which is worse than the lost tab stop it fixes.
  //
  // The `nowhere` branch has no test, and cannot have one: jsdom does not
  // blur on `disabled` and refuses `blur()` and `body.focus()` while the
  // element is disabled, so the browser behaviour this repairs is
  // unreachable from the suite. The branch that *is* tested is the other
  // one — that focus the manager moved himself is left alone.
  useEffect(() => {
    if (busy || !restore.current) return
    restore.current = false
    const active = document.activeElement
    if (!active || active === document.body) saveRef.current?.focus()
  }, [busy])

  function save() {
    setBusy(true)
    setError(null)
    restore.current = true
    apiPost<WatchlistPanel>('/api/watchlist', { code: row.code, note: draft })
      .then(onSaved)
      .catch((e) => setError(errorText(e)))
      .finally(() => setBusy(false))
  }

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
      {/* A form, so Enter in the field saves the note the manager just
          typed. A note is one short line and reaching for the mouse to
          commit it is the wrong shape for the input. */}
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(e) => { e.preventDefault(); save() }}
      >
        <input
          aria-label={`note for ${row.name}`}
          className="min-w-0 flex-1 rounded-card border border-border bg-base
                     px-2 py-1"
          value={draft}
          disabled={busy}
          onChange={(e) => setDraft(e.target.value)}
        />
        <button
          ref={saveRef}
          type="submit"
          className="rounded-card border border-border bg-base px-2 py-1
                     text-text-secondary hover:text-text"
          disabled={busy}
        >
          {`Save note for ${row.name}`}
        </button>
      </form>
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
      {panel.rows.map((row) => (
        <Row key={row.code} row={row} onSaved={adopt} onRemoved={adopt} />
      ))}
      <p data-testid="watchlist-caveat" className="mt-2 text-text-faint">
        {'Starring a player again from the Explorer no longer touches a note. '
         + 'This is the only view that writes one, and the date beside each '
         + 'name is when its note was last saved here.'}
      </p>
    </Card>
  )
}
