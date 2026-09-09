import { useEffect, useState } from 'react'
import { apiPost, errorText } from '../../api/client'
import { invalidate, usePageData } from '../../api/pageData'
import {
  Button, Callout, Card, Chip, INPUT_CLASS, Segmented, fmtDelta,
} from '../../kit'
import type { DecisionNote } from '../../types'

export const REASONS = [
  'injury', 'fixtures', 'eye_test', 'price', 'chip', 'rival', 'gut', 'other',
] as const
export type Reason = typeof REASONS[number]

export const REASON_LABEL: Record<Reason, string> = {
  injury: 'Injury', fixtures: 'Fixtures', eye_test: 'Eye test', price: 'Price',
  chip: 'Chip', rival: 'Rival', gut: 'Gut', other: 'Other',
}

const TEXT_MAX = 280

/** "What I did and why" (v16 §5): a reason from eight and one line of text,
 *  editable from the deadline until the gameweek is graded. */
export default function DecisionPanel({ gw }: { gw: number }) {
  const banked = usePageData<DecisionNote>(`/api/decisions/${gw}`)
  // The note the panel is editing, which is the banked one until this panel
  // writes one of its own: the POST answers with the row the server stored and
  // that answer is what the graded strip reads back (v17h §5).
  const [note, setNote] = useState<DecisionNote | null>(null)
  const [reason, setReason] = useState<Reason | null>(null)
  const [text, setText] = useState('')
  const [saved, setSaved] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)

  const read = banked.data
  useEffect(() => {
    setNote(read)
    if (read === null) return
    setReason((read.reason as Reason | null) ?? null)
    setText(read.text ?? '')
  }, [read])

  if (note === null) return null

  const save = async () => {
    if (!reason) return
    setFailed(null)
    try {
      const out = await apiPost<DecisionNote>(`/api/decisions/${gw}`,
                                              { reason, text })
      setNote(out)
      setSaved(true)
      // The POST's answer is what this panel paints, but the cache still
      // holds the note as it was before the save (v17h §5) — and the review
      // reads the same URL. Cheap, because the one re-request is shared.
      invalidate(`/api/decisions/${gw}`)
    } catch (e) {
      setFailed(errorText(e))
    }
  }

  const grade = note.grade
  return (
    <div data-testid="decision-panel">
      <Card title="What I did and why" className="mb-4">
        {note.state === 'before_deadline' && (
          <p className="text-text-muted">
            The note opens at the deadline
            {note.deadline ? ` (${new Date(note.deadline).toLocaleString()})` : ''}
            . Record why you did something other than the advice, and the review
            will grade the reason as well as the move.
          </p>
        )}
        {note.state === 'graded' && (
          <div className="flex flex-wrap items-baseline gap-2">
            {note.reason
              ? <Chip>{REASON_LABEL[note.reason as Reason] ?? note.reason}</Chip>
              : <span className="text-text-muted">No note for this gameweek.</span>}
            {note.text && <span className="text-text-secondary">{note.text}</span>}
            {grade?.label && (
              <span className="inline-flex items-center gap-1.5">
                <Chip tone={(grade.delta_pts ?? 0) >= 0 ? 'up' : 'down'}>
                  {grade.label}
                </Chip>
                <span className="tn text-text-muted">
                  {grade.delta_pts === null ? '' : `${fmtDelta(grade.delta_pts, 0)} pts`}
                </span>
              </span>
            )}
          </div>
        )}
        {note.state === 'open' && (
          <div className="flex flex-col gap-2">
            <Segmented
              label="Reason"
              value={(reason ?? '') as Reason}
              onChange={(v) => { setReason(v as Reason); setSaved(false) }}
              options={REASONS.map((r) => ({ value: r, label: REASON_LABEL[r] }))}
            />
            <label className="flex items-center gap-2">
              <span className="label">Note</span>
              <input
                aria-label="Note"
                className={`${INPUT_CLASS} flex-1`}
                maxLength={TEXT_MAX}
                value={text}
                onChange={(e) => { setText(e.target.value); setSaved(false) }}
                placeholder="one line, optional"
              />
            </label>
            <div className="flex items-center gap-3">
              <Button variant="primary" onClick={save} disabled={!reason}>
                Save
              </Button>
              {saved && <span className="text-text-muted">Saved.</span>}
            </div>
            {failed && <Callout tone="error">{failed}</Callout>}
          </div>
        )}
      </Card>
    </div>
  )
}
