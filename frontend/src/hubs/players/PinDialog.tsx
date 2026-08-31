import { useEffect, useRef, useState } from 'react'
import { ApiError, apiPost } from '../../api/client'
import type { OverridesPanel } from '../../types'

const FIELD = 'rounded-card border border-border bg-base px-2 py-1 text-text'

export default function PinDialog(
  { code, name, onClose, onSaved }: {
    code: number
    name: string
    onClose: () => void
    onSaved?: (panel: OverridesPanel) => void
  },
) {
  const [pPlay, setPPlay] = useState('')
  const [eMin, setEMin] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  useEffect(() => { closeRef.current?.focus() }, [])

  const save = async () => {
    setError(null)
    try {
      const panel = await apiPost<OverridesPanel>('/api/overrides', {
        code,
        p_play: pPlay === '' ? null : Number(pPlay),
        e_min: eMin === '' ? null : Number(eMin),
        note,
      })
      onSaved?.(panel)
      onClose()
    } catch (e) {
      const detail = e instanceof ApiError ? e.detail : null
      const message = (detail && typeof detail === 'object'
        && 'error' in detail) ? String((detail as { error: string }).error)
        : (e as Error).message
      setError(message)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center
                 overflow-y-auto bg-black/70 p-4 sm:p-8"
      data-testid="modal-backdrop"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-card border border-border bg-card"
        role="dialog"
        aria-modal="true"
        aria-label={`Pin availability for ${name}`}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-3 border-b
                           border-divider px-4 py-3">
          <div>
            <h2 className="text-base text-text">Pin {name}</h2>
            <p className="label mt-1">Applied over the model, this gameweek</p>
          </div>
          <button ref={closeRef} type="button" onClick={onClose}
                  className="rounded-card border border-border px-2 py-1
                             text-text-muted hover:text-text">
            Close
          </button>
        </header>
        <div className="flex flex-col gap-3 p-4">
          <p className="text-text-muted">
            Leave a field blank to leave the model's own number alone. A
            probability of playing is 0 to 1; expected minutes are 0 to 90.
          </p>
          <label className="flex items-center justify-between gap-3">
            <span className="label">Probability of playing</span>
            <input className={FIELD} inputMode="decimal" value={pPlay}
                   aria-label="probability of playing"
                   onChange={(e) => setPPlay(e.target.value)} />
          </label>
          <label className="flex items-center justify-between gap-3">
            <span className="label">Expected minutes</span>
            <input className={FIELD} inputMode="decimal" value={eMin}
                   aria-label="expected minutes"
                   onChange={(e) => setEMin(e.target.value)} />
          </label>
          <label className="flex items-center justify-between gap-3">
            <span className="label">Why</span>
            <input className={FIELD} value={note} aria-label="why"
                   onChange={(e) => setNote(e.target.value)} />
          </label>
          {error && <p className="text-rust">{error}</p>}
          <button type="button" onClick={save}
                  className="self-end rounded-card border border-border
                             bg-card px-3 py-2 text-text-secondary
                             hover:text-text">
            Pin
          </button>
        </div>
      </div>
    </div>
  )
}
