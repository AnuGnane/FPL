import * as Dialog from '@radix-ui/react-dialog'
import { useState } from 'react'
import { apiPost, errorText } from '../api/client'
import { invalidate } from '../api/pageData'
import type { OverrideRequest, OverridesPanel } from '../types'
// v19b §2.3: the dialog is kit now — This Week's news rows open it as well as
// the Players explorer — so its siblings are imported by file rather than
// through the barrel, which would import this file back.
import Button, { buttonClass } from './Button'
import Callout from './Callout'
import { INPUT_CLASS } from './field'
import { toast } from './Toast'
import useOpener from './useOpener'

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
  const returnFocus = useOpener()

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
      // The dialog's caller is re-seeded from the answer above, but the Why
      // panel on This Week reads the same pins through the cache (v17h §5),
      // and "your pins are in this plan" has to be true of the pin just taken.
      invalidate('/api/overrides')
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

  // v18f §2.2. Radix owns what two hand-rolled effects used to: the focus
  // trap, the return of focus to the row that opened the dialog, Escape, the
  // overlay click, and the `aria-hidden` over the table behind. The caller
  // mounts this only while a player is being pinned, so `open` is the
  // constant `true` and closing is an unmount.
  return (
    <Dialog.Root open onOpenChange={(next) => { if (!next) onClose() }}>
      <Dialog.Portal>
        {/* Content nests inside the overlay because the overlay is also the
            scroll container, as it was before Radix. */}
        <Dialog.Overlay
          className="fixed inset-0 z-50 flex items-start justify-center
                     overflow-y-auto bg-scrim p-4 sm:p-8"
          data-testid="modal-backdrop"
        >
          <Dialog.Content
            className="w-full max-w-md rounded-ctl border border-border bg-base"
            aria-label={`Pin availability for ${name}`}
            // Radix marks the page behind with `aria-hidden` and leaves this
            // off; the attribute was on the hand-rolled dialog and costs
            // nothing beside it, so the modal keeps saying it is one.
            aria-modal="true"
            // The heading says "Pin Salah"; the label says what pinning
            // him is. One name, the sentence, exactly as before Radix — so
            // the title is left out of the naming and kept as the heading.
            aria-labelledby={undefined}
            onCloseAutoFocus={returnFocus}
          >
            <header className="flex items-start justify-between gap-3 border-b
                               border-divider px-4 py-3">
              <div>
                <Dialog.Title className="text-base text-text">
                  Pin {name}
                </Dialog.Title>
                <Dialog.Description className="label mt-1">
                  Applied over the model, this gameweek
                </Dialog.Description>
              </div>
              <Dialog.Close className={buttonClass('ghost')}>
                Close
              </Dialog.Close>
            </header>
            <div className="flex flex-col gap-3 p-4">
              <p className="text-text-muted">
                Leave a field blank to leave the model's own number alone. A
                probability of playing is 0 to 1; expected minutes are 0 to 90.
              </p>
              <label className="flex items-center justify-between gap-3">
                <span className="label">Probability of playing</span>
                <input className={INPUT_CLASS} inputMode="decimal" value={pPlay}
                       aria-label="probability of playing"
                       onChange={(e) => setPPlay(e.target.value)} />
              </label>
              <label className="flex items-center justify-between gap-3">
                <span className="label">Expected minutes</span>
                <input className={INPUT_CLASS} inputMode="decimal" value={eMin}
                       aria-label="expected minutes"
                       onChange={(e) => setEMin(e.target.value)} />
              </label>
              <label className="flex items-center justify-between gap-3">
                <span className="label">Why</span>
                <span className="flex items-center gap-2">
                  {note.length > NOTE_HINT && (
                    <span className="tn text-text-faint">
                      {note.length}/{NOTE_MAX}
                    </span>
                  )}
                  <input className={INPUT_CLASS} value={note} aria-label="why"
                         maxLength={NOTE_MAX}
                         onChange={(e) => setNote(e.target.value)} />
                </span>
              </label>
              {/* v19b §2.5: `onRetry` is the same `save`, so a token typed
                  into the refusal takes the pin that was refused rather than
                  making the manager fill the dialog in again. */}
              {error && (
                <Callout tone="error" onRetry={() => { void save() }}>
                  {error}
                </Callout>
              )}
              {warning && <Callout tone="warn">{warning}</Callout>}
              <Button variant="primary" className="self-end" onClick={save}>
                Pin
              </Button>
            </div>
          </Dialog.Content>
        </Dialog.Overlay>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
