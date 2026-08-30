import { useState } from 'react'
import { ApiError, apiPost } from '../../api/client'
import { useJob } from '../../api/useJob'
import { Card } from '../../kit'
import type { WhatIfRequest, WhatIfResult } from '../../types'
import ConstraintsPanel from './ConstraintsPanel'
import FixtureTicker from './FixtureTicker'
import PlanDiffTable from './PlanDiffTable'

const EMPTY: WhatIfRequest = {
  lock: [], ban: [], force_in: [], max_hits: 0, chip: 'none', horizon: null,
}

interface StructuredError {
  constraint: string
  error: string
  players: number[]
}

export default function WhatIfTab() {
  const [request, setRequest] = useState<WhatIfRequest>(EMPTY)
  const [invalid, setInvalid] = useState<StructuredError | null>(null)
  const job = useJob()

  const solve = async () => {
    setInvalid(null)
    job.reset()
    try {
      // Submitted here rather than through useJob.start so a structured 422
      // renders next to the inputs instead of becoming a generic job error.
      const { job_id } = await apiPost<{ job_id: string }>('/api/whatif',
        request)
      job.attach(job_id)
    } catch (e) {
      if (e instanceof ApiError && typeof e.detail === 'object'
        && e.detail !== null) {
        setInvalid(e.detail as StructuredError)
      } else {
        setInvalid({ constraint: 'request',
          error: e instanceof Error ? e.message : String(e), players: [] })
      }
    }
  }

  const busy = job.status === 'queued' || job.status === 'running'
  const diff = job.result as WhatIfResult | null

  return (
    <>
      <ConstraintsPanel value={request} onChange={setRequest} />
      {/* The one control on the tab, so it sits on the page rather than
          inside a card of its own. */}
      <button
        type="button"
        onClick={solve}
        disabled={busy}
        className="mb-4 rounded-card border border-border bg-card px-3 py-2
                   text-text-secondary hover:text-text
                   disabled:text-text-faint"
      >
        {busy ? 'Solving…' : 'Re-solve'}
      </button>
      {invalid && (
        <Card title="Infeasible" className="mb-4">
          <p className="text-rust">{invalid.error}</p>
          <p className="mt-1">
            <span className="label">Constraint</span>{' '}
            <span className="text-text-secondary">{invalid.constraint}</span>
          </p>
        </Card>
      )}
      {job.status === 'error' && (
        <Card title="Solver failed" className="mb-4">
          <p className="text-rust">{job.error}</p>
        </Card>
      )}
      {diff && <PlanDiffTable diff={diff} />}
      <FixtureTicker weeks={6} />
    </>
  )
}
