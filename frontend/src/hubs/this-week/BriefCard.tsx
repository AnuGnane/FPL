import { useEffect } from 'react'
import { usePageData } from '../../api/pageData'
import { useJob } from '../../api/useJob'
import { Button, Callout, Card, JobButton } from '../../kit'
import type { BriefPanel } from '../../types'
import DigestCard from './DigestCard'

/** The week, written (v16 §6). A brief that exists replaces the digest's
 *  prose; the two digest buttons stay. The button posts an anonymous job
 *  (plan R1) exactly as the ladder's Rebuild does. */
export default function BriefCard() {
  const brief = usePageData<BriefPanel>('/api/brief')
  const panel = brief.data
  const job = useJob({ path: '/api/brief', slot: 'brief' })

  // This card's own job rewrote this card's own artifact, and nobody else's
  // (v17h §5).
  const reload = brief.reload
  useEffect(() => { if (job.status === 'done') reload() }, [job.status, reload])

  const busy = job.status === 'queued' || job.status === 'running'
  const write = (
    <Button onClick={() => job.start()} disabled={busy}>
      {busy ? 'Writing…' : 'Write the brief'}
    </Button>
  )

  if (panel === null) return null
  if (!panel.prose) {
    // The server already answered "is there a digest": `fallback` is the very
    // panel `/api/digest` would serve. Handing it over saves the card a
    // second round trip and, more to the point, keeps the two answers from
    // disagreeing. `?? undefined` when the server sent none, which leaves
    // DigestCard fetching for itself exactly as it does everywhere else.
    return (
      <DigestCard
        extra={write}
        note={panel.note}
        panel={panel.fallback ?? undefined}
      />
    )
  }

  const stamp = panel.checked_at ? new Date(panel.checked_at).toLocaleString() : ''
  return (
    <Card
      title="The week"
      className="mb-4"
      action={(
        <div className="flex flex-wrap items-baseline gap-3">
          <span className="text-text-muted">
            {`GW${panel.gw} · ${panel.model_command ?? 'llm'}${stamp ? ` · ${stamp}` : ''}`}
          </span>
          {write}
          <JobButton kind="digest-friday" onDone={reload} />
          <JobButton kind="digest-tuesday" onDone={reload} />
        </div>
      )}
    >
      {job.status === 'error' && <Callout tone="error" className="mb-2">{job.error}</Callout>}
      {panel.prose.split(/\n\s*\n/).map((para, i) => (
        <p key={i} className="mb-2 max-w-prose text-text">{para.trim()}</p>
      ))}
      <p className="text-text-faint">
        Written from the banked facts and checked against them: every number
        and every name above is in the advice, the ladder or the ledger.
      </p>
    </Card>
  )
}
