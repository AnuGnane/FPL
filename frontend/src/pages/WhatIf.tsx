import { useState } from 'react'
import { ApiError, apiPost } from '../api/client'
import { useJob } from '../api/useJob'
import ConstraintsPanel from '../components/ConstraintsPanel'
import FixtureTicker from '../components/FixtureTicker'
import PlanDiffTable from '../components/PlanDiffTable'
import type { WhatIfRequest, WhatIfResult } from '../types'

const EMPTY: WhatIfRequest = {
  lock: [], ban: [], force_in: [], max_hits: 0, chip: 'none', horizon: null,
}

interface StructuredError {
  constraint: string
  error: string
  players: number[]
}

export default function WhatIf() {
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
      <h2>What-If Lab</h2>
      <ConstraintsPanel value={request} onChange={setRequest} />
      <button onClick={solve} disabled={busy}>
        {busy ? 'Solving…' : 'Re-solve'}
      </button>
      {invalid && (
        <div className="card">
          <p className="bad">{invalid.error}</p>
          <p className="muted">constraint: {invalid.constraint}</p>
        </div>
      )}
      {job.status === 'error' && <p className="bad">{job.error}</p>}
      {diff && <PlanDiffTable diff={diff} />}
      <FixtureTicker weeks={6} />
    </>
  )
}
