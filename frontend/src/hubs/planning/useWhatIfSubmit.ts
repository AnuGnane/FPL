import { apiPost } from '../../api/client'
import type { Job } from '../../api/useJob'
import type { WhatIfRequest } from '../../types'

/**
 * Post a What-If solve and hand the job id to the caller's `useJob` slot.
 *
 * One copy of a solve that was written twice — `WhatIfTab.tsx:42` and
 * `ChipsTab.tsx:184` — and cut out in v18f §2.1. Both tabs post the request
 * here rather than through `useJob.start` for the same stated reason: a
 * structured 422 has to render next to the inputs instead of becoming a
 * generic job error. What differs between them is what they *say* about a
 * refusal — the lab reads a `{constraint, error, players}` body into its own
 * card, the chips panel prints one sentence — so the wording stays with each
 * tab, in `onError`, and only the two lines they agreed on live here.
 *
 * Not a stateful hook: the tabs keep their own `useJob({ slot })` and their
 * own error state, and this returns the submit they share.
 */
export function useWhatIfSubmit(
  job: Job,
  onError: (e: unknown) => void,
): (request: WhatIfRequest) => Promise<void> {
  return async (request: WhatIfRequest) => {
    job.reset()
    try {
      const { job_id } = await apiPost<{ job_id: string }>('/api/whatif',
        request)
      job.attach(job_id)
    } catch (e) {
      onError(e)
    }
  }
}
