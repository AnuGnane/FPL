import { useEffect, useState } from 'react'
import { apiGet, apiPost, errorText } from '../../api/client'
import { Card, EmptyState, Loading } from '../../kit'
import type { SettingRow, SettingsPanel } from '../../types'

/**
 * v12 W5 §6.2 — the nine settings the UI may edit.
 *
 * It writes `config.local.toml` through `/api/settings` and never touches
 * `config.toml`, which carries the odds API key. The server owns the
 * whitelist, the bounds, the refusal text and the sentence about what a save
 * reaches; this file renders them and adds no rule of its own. A second
 * statement of a bound here would be a second thing to keep in step with the
 * dataclass.
 *
 * One save per field, deliberately: a form with one Save button has to decide
 * what to do when the third of five writes is refused, and the honest answers
 * are all worse than never being in that state.
 */

function label(row: SettingRow): string {
  return row.label
}

function Field(
  { row, onSave, error, busy }: {
    row: SettingRow
    onSave: (value: unknown) => void
    /** The server's refusal for this row, or null. Rendered below by the
     *  caller; the control needs it too, so a screen reader is told the field
     *  is invalid and where the sentence explaining it is. */
    error: string | null
    busy: boolean
  },
) {
  const serialized = JSON.stringify(row.value)
  const [draft, setDraft] = useState(() => serialized)

  // Re-seed when the server sends a new value — after a save, or after a
  // reset. Keyed on the serialized value so a re-render with the same answer
  // does not stamp on what the user is typing.
  useEffect(() => { setDraft(serialized) }, [serialized])

  if (row.kind === 'bool') {
    return (
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={row.value === true}
          disabled={busy}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `settings-error-${row.key}` : undefined}
          onChange={(e) => onSave(e.target.checked)}
        />
        <span>{label(row)}</span>
      </label>
    )
  }

  const numeric = row.kind === 'int' || row.kind === 'float'
  return (
    <div className="flex flex-wrap items-center gap-2">
      <label className="flex items-center gap-2">
        <span>{label(row)}</span>
        <input
          className="w-32 rounded-card border border-border bg-base px-2 py-1"
          type={numeric ? 'number' : 'text'}
          step={row.kind === 'float' ? 0.01 : 1}
          value={numeric ? draft.replace(/"/g, '') : draft}
          disabled={busy}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `settings-error-${row.key}` : undefined}
          onChange={(e) => setDraft(e.target.value)}
        />
      </label>
      <button
        type="button"
        disabled={busy}
        className="rounded-card border border-border bg-base px-2 py-1
                   text-text-secondary hover:text-text"
        onClick={() => {
          if (numeric) {
            const n = Number(draft)
            // NaN is sent as the raw string so the *server* refuses it and
            // says why. A client-side "that is not a number" would be a
            // second validator saying almost the same thing.
            onSave(draft.trim() === '' || Number.isNaN(n) ? draft : n)
          } else {
            try {
              onSave(JSON.parse(draft))
            } catch {
              onSave(draft)
            }
          }
        }}
      >
        {`Save ${label(row)}`}
      </button>
    </div>
  )
}

export default function SettingsTab() {
  const [panel, setPanel] = useState<SettingsPanel | null>(null)
  const [failed, setFailed] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState<string | null>(null)

  useEffect(() => {
    apiGet<SettingsPanel>('/api/settings')
      .then(setPanel)
      .catch(() => setFailed(true))
  }, [])

  function save(key: string, value: unknown) {
    setBusy(key)
    setErrors((prev) => ({ ...prev, [key]: '' }))
    apiPost<SettingsPanel>('/api/settings', { key, value })
      // The response is the whole panel, so a save re-seeds every row's
      // `source` as well as its value — which is what turns the Reset button
      // on for the field that was just written.
      .then((body) => setPanel(body))
      .catch((e) => setErrors((prev) => ({ ...prev, [key]: errorText(e) })))
      .finally(() => setBusy(null))
  }

  if (failed) {
    return (
      <EmptyState
        title="Settings unavailable"
        detail="The server could not be asked what is configurable."
        action="Check that the app is running"
      />
    )
  }
  if (!panel) return <Loading />
  if (panel.rows.length === 0) {
    return (
      <EmptyState
        title="Nothing to configure yet"
        detail={panel.overlay_error
          ?? 'This build exposes none of the editable settings.'}
        action="cp config.example.toml config.toml"
      />
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {panel.overlay_error && (
        // A save can turn this on without anything else moving on the page,
        // so it is announced rather than only drawn. `polite` and not
        // `assertive`: the reader is mid-form, and the overlay being ignored
        // is news he needs at the end of his sentence, not in the middle of it.
        <p
          data-testid="settings-overlay-error"
          role="status"
          aria-live="polite"
          className="rounded-card border border-rust bg-card px-3 py-2
                     text-rust"
        >
          {panel.overlay_error}
        </p>
      )}
      <Card title="Settings">
        <div className="flex flex-col gap-4">
          {panel.rows.map((row) => (
            <div key={row.key} className="flex flex-col gap-1">
              <Field
                row={row}
                busy={busy === row.key}
                error={errors[row.key] || null}
                onSave={(value) => save(row.key, value)}
              />
              <p className="text-text-faint">{row.help}</p>
              {row.source === 'local' && (
                <button
                  type="button"
                  className="self-start text-text-muted hover:text-text"
                  onClick={() => save(row.key, null)}
                >
                  {`Reset ${label(row)}`}
                </button>
              )}
              {errors[row.key] && (
                <p data-testid={`settings-error-${row.key}`}
                   id={`settings-error-${row.key}`}
                   role="status"
                   aria-live="polite"
                   className="text-rust">
                  {errors[row.key]}
                </p>
              )}
            </div>
          ))}
        </div>
      </Card>
      {panel.unavailable.length > 0 && (
        <p data-testid="settings-unavailable" className="text-text-muted">
          {`Not in this build: ${panel.unavailable.join(', ')}. `
           + 'These arrive with the workstreams that introduce them.'}
        </p>
      )}
      {/* The server's own sentence, verbatim — the same convention This Week
          uses for the captain's field note. */}
      <p data-testid="settings-apply-note" className="text-text-muted">
        {panel.apply_note}
      </p>
    </div>
  )
}
