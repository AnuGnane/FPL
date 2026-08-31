import { useEffect, useRef, useState } from 'react'
import { apiPost, errorText } from '../../api/client'
import { toast } from '../../kit'
import type { OverrideRequest, OverridesPanel } from '../../types'

const FIELD = 'rounded-card border border-border bg-base px-2 py-1 text-text'

/** `overrides.NOTE_MAX`. The store refuses a longer note rather than
 *  truncating it — a silently halved note is a sentence the user did not
 *  write — so the input stops at the same number instead of collecting
 *  characters that will be thrown back. */
const NOTE_MAX = 200
/** Where the counter appears. Early enough to be a warning, late enough not
 *  to be clutter on a five-word note. */
const NOTE_HINT = 160

/** One field's value: `null` for blank, a number, or the reason it is
 *  neither. The same three ranges `overrides.set_override` enforces, checked
 *  here so a typo is answered by the dialog instead of a round trip. */
function parse(raw: string, lo: number, hi: number, label: string):
{ value: number | null } | { error: string } {
  if (raw.trim() === '') return { value: null }
  const value = Number(raw)
  if (!Number.isFinite(value)) return { error: `${label} must be a number` }
  if (value < lo || value > hi) {
    return { error: `${label} must be between ${lo} and ${hi}` }
  }
  return { value }
}

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
  // Accepted and stored, but worth reading before the dialog goes away — so
  // the pin is saved and the dialog stays up carrying the sentence.
  const [warning, setWarning] = useState<string | null>(null)
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
    setWarning(null)
    const play = parse(pPlay, 0, 1, 'probability of playing')
    const mins = parse(eMin, 0, 90, 'expected minutes')
    if ('error' in play) return setError(play.error)
    if ('error' in mins) return setError(mins.error)
    if (play.value === null && mins.value === null) {
      return setError('an override must pin p_play, e_min or both')
    }
    try {
      const body: OverrideRequest = {
        code, p_play: play.value, e_min: mins.value, note,
      }
      const panel = await apiPost<OverridesPanel>('/api/overrides', body)
      onSaved?.(panel)
      // True on the warning path too: the pin *was* taken, and the dialog
      // stays up with its sentence.
      toast('positive', `Pinned ${name}. It applies to this gameweek only.`)
      // A pin the server took but wants a second look at keeps the dialog up
      // with its reason; anything else is done.
      if (panel.warning) setWarning(panel.warning)
      else onClose()
    } catch (e) {
      const text = errorText(e)
      setError(text)
      // Both: the inline line is for the person still looking at the dialog,
      // the toast is for the one whose eyes went back to the table.
      toast('negative', `Could not pin ${name} — ${text}`)
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
            <span className="flex items-center gap-2">
              {note.length > NOTE_HINT && (
                <span className="num text-text-faint">
                  {note.length}/{NOTE_MAX}
                </span>
              )}
              <input className={FIELD} value={note} aria-label="why"
                     maxLength={NOTE_MAX}
                     onChange={(e) => setNote(e.target.value)} />
            </span>
          </label>
          {error && <p className="text-rust">{error}</p>}
          {warning && <p className="text-info">{warning}</p>}
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
