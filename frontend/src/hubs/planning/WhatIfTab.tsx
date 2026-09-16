import { useState } from 'react'
import { ApiError, errorText } from '../../api/client'
import { useJob } from '../../api/useJob'
import { Button, Callout, Card, Skeleton } from '../../kit'
import type { WhatIfRequest, WhatIfResult } from '../../types'
import LadderCard from '../this-week/LadderCard'
import ConstraintsPanel from './ConstraintsPanel'
import FixtureTicker from './FixtureTicker'
import OverridesCard from './OverridesCard'
import PlanDiffTable from './PlanDiffTable'
import SensitivityCard from './SensitivityCard'
import { useWhatIfSubmit } from './useWhatIfSubmit'

/** The unconstrained request the lab opens on.
 *
 *  Exported since v19e §2.4: the squad's row menu builds its handoff from the
 *  same object the lab itself starts from, so a field added to the request
 *  cannot arrive in one of them and not the other. */
export const EMPTY_WHATIF: WhatIfRequest = {
  lock: [], ban: [], force_in: [], force_out: [], max_hits: 0,
  max_transfers: null, chip: 'none', horizon: null,
}

interface StructuredError {
  constraint: string
  error: string
  players: number[]
}

export default function WhatIfTab({ value, onChange }: {
  value?: WhatIfRequest
  onChange?: (next: WhatIfRequest) => void
} = {}) {
  // Controlled when Planning hands the constraints down (so the Drafts tab
  // can save them), uncontrolled when the tab is rendered on its own.
  const [own, setOwn] = useState<WhatIfRequest>(EMPTY_WHATIF)
  const request = value ?? own
  const setRequest = onChange ?? setOwn
  const [invalid, setInvalid] = useState<StructuredError | null>(null)
  const job = useJob({ slot: 'whatif' })

  // Submitted through the shared submit rather than useJob.start so a
  // structured 422 renders next to the inputs instead of becoming a generic
  // job error (v18f §2.1 — one copy of the two lines both tabs wrote).
  const submit = useWhatIfSubmit(job, (e) => {
    if (e instanceof ApiError && typeof e.detail === 'object'
      && e.detail !== null) {
      setInvalid(e.detail as StructuredError)
    } else {
      setInvalid({ constraint: 'request', error: errorText(e),
        players: [] })
    }
  })

  const solve = async () => {
    setInvalid(null)
    await submit(request)
  }

  const busy = job.status === 'queued' || job.status === 'running'
  const diff = job.result as WhatIfResult | null

  return (
    <>
      <ConstraintsPanel value={request} onChange={setRequest} />
      {/* The one control on the tab, so it sits on the page rather than
          inside a card of its own. */}
      <Button className="mb-4" onClick={solve} disabled={busy}>
        {busy ? 'Solving…' : 'Re-solve'}
      </Button>
      {invalid && (
        <Card title="Infeasible" className="mb-4">
          <p className="text-down">{invalid.error}</p>
          <p className="mt-1">
            <span className="label">Constraint</span>{' '}
            <span className="text-text-secondary">{invalid.constraint}</span>
          </p>
        </Card>
      )}
      {job.status === 'error' && (
        <Card title="Solver failed" className="mb-4">
          <Callout tone="error">{job.error}</Callout>
        </Card>
      )}
      {busy && (
        <Skeleton title="Re-solving" lines={5}
                  label="Re-solving the board with your constraints…" />
      )}
      {/* `!busy` on the diff so a *second* solve blanks the stale answer
          rather than pulsing beneath a result from the previous run — which
          is the specific lie this pair exists to remove. */}
      {diff && !busy && <PlanDiffTable diff={diff} />}
      {/* v13: the ladder prices the appetite the panel above caps. */}
      <LadderCard />
      <SensitivityCard />
      <OverridesCard />
      <FixtureTicker weeks={6} />
    </>
  )
}
