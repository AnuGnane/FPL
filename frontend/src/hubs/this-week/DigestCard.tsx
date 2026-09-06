import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { apiGet } from '../../api/client'
import { Callout, Card, EmptyState, JobButton } from '../../kit'
import { JOB_KIND_LABEL, type DigestPanel } from '../../types'

const KIND_LABEL: Record<string, string> = {
  friday: 'Friday briefing',
  tuesday: 'Tuesday debrief',
}

export interface DigestCardProps {
  /** Rendered in the button row, before the two job buttons. */
  extra?: ReactNode
  /** Shown above the card's content, in the note voice. */
  note?: string | null
  /** The panel to render. Omitted, the card fetches its own as it always has;
   *  given (even as null) it renders that and makes no request. */
  panel?: DigestPanel | null
}

/**
 * The newest banked digest, rendered as prose.
 *
 * Self-fetching on `NewsPanel`'s pattern, and deliberately silent on
 * failure: This Week already has its advice by the time this mounts, and a
 * missing digest must never put an error above the recommended moves.
 *
 * The card renders what the schedule banked — it never builds one, because
 * building reads seven files and a page load cannot wait for that. The two
 * job buttons are how a user builds one on demand.
 *
 * v16: BriefCard renders this card as its fallback, so it lends the card a
 * control of its own (`extra`) and the sentence saying why there is no brief
 * (`note`). It can also hand over the panel it was already served — the
 * brief endpoint carries the digest panel with it — which is `given`.
 */
export default function DigestCard(
  { extra, note, panel: given }: DigestCardProps = {},
) {
  const [fetched, setFetched] = useState<DigestPanel | null>(null)

  const load = useCallback(() => {
    apiGet<DigestPanel>('/api/digest').then(setFetched).catch(() => {})
  }, [])
  const owned = given === undefined
  useEffect(() => { if (owned) load() }, [owned, load])

  const panel = given === undefined ? fetched : given
  if (panel === null) return null

  const buttons = (
    <div className="flex flex-wrap gap-2">
      {extra}
      <JobButton kind="digest-friday" onDone={load} />
      <JobButton kind="digest-tuesday" onDone={load} />
    </div>
  )

  const noteLine = note
    ? <Callout tone="note" className="mb-2">{note}</Callout>
    : null

  if (!panel.available || panel.digest === null) {
    return (
      <Card title="Digest" className="mb-4" action={buttons}>
        {noteLine}
        <EmptyState
          title="No digest yet"
          detail="The Friday briefing is written at 17:00 and the Tuesday
                  debrief at 09:30, by the scheduled jobs. Neither has run
                  since the last artifact was cleared — the two buttons above
                  build one now, from the files already on disk."
          // The label on the card's own Friday button, read from the same
          // table it renders, so a rename cannot make this line stale.
          action={JOB_KIND_LABEL['digest-friday']}
        />
      </Card>
    )
  }

  const { digest } = panel
  const stamp = digest.generated_at
    ? new Date(digest.generated_at).toLocaleString()
    : ''
  return (
    <Card
      title="Digest"
      className="mb-4"
      action={(
        <div className="flex flex-wrap items-baseline gap-3">
          <span className="text-text-muted">
            {KIND_LABEL[digest.kind] ?? digest.kind}
            {stamp && ` · ${stamp}`}
          </span>
          {buttons}
        </div>
      )}
    >
      {noteLine}
      <p className="text-text">{digest.headline}</p>
      {/* A digest that failed to build still banks an artifact, so it must
          read as a failure rather than as a briefing with nothing in it. */}
      {digest.error && (
        <Callout tone="error" className="mt-2">{digest.error}</Callout>
      )}
      <dl className="mt-3 space-y-2">
        {digest.sections.map((section) => (
          <div key={section.key}>
            <dt className="label">{section.title}</dt>
            {/* The bits[] prose idiom: the server assembled the clauses and
                the client joins them, which is why nothing in this feature
                needs a markdown renderer. About half the builders end their
                bit in a period and half do not, so the join strips one before
                adding its own rather than rendering "away..". */}
            <dd className="text-text-secondary">
              {`${section.bits.map((b) => b.replace(/\.$/, '')).join('. ')}.`}
            </dd>
          </div>
        ))}
      </dl>
    </Card>
  )
}
