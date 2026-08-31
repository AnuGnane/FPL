import { useCallback, useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import { Card, JobButton } from '../../kit'
import type { DigestPanel } from '../../types'

const KIND_LABEL: Record<string, string> = {
  friday: 'Friday briefing',
  tuesday: 'Tuesday debrief',
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
 */
export default function DigestCard() {
  const [panel, setPanel] = useState<DigestPanel | null>(null)

  const load = useCallback(() => {
    apiGet<DigestPanel>('/api/digest').then(setPanel).catch(() => {})
  }, [])
  useEffect(load, [load])

  if (panel === null) return null

  const buttons = (
    <div className="flex flex-wrap gap-2">
      <JobButton kind="digest-friday" onDone={load} />
      <JobButton kind="digest-tuesday" onDone={load} />
    </div>
  )

  if (!panel.available || panel.digest === null) {
    return (
      <Card title="Digest" className="mb-4" action={buttons}>
        <p className="text-text-muted">
          No digest yet — the Friday briefing runs at 17:00 and the Tuesday
          debrief at 09:30, or build one now.
        </p>
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
      <p className="text-text">{digest.headline}</p>
      {/* A digest that failed to build still banks an artifact, so it must
          read as a failure rather than as a briefing with nothing in it. */}
      {digest.error && (
        <p className="mt-2 text-text-muted">{digest.error}</p>
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
