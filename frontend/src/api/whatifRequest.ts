import type { WhatIfRequest } from '../types'

/** The unconstrained request the lab opens on.
 *
 *  Exported since v19e §2.4: the squad's row menu builds its handoff from the
 *  same object the lab itself starts from, so a field added to the request
 *  cannot arrive in one of them and not the other. In `api/` since holiday
 *  F-156, so the squad's menu on This Week reads it without importing a
 *  Planning file. */
export const EMPTY_WHATIF: WhatIfRequest = {
  lock: [], ban: [], force_in: [], force_out: [], max_hits: 0,
  max_transfers: null, chip: 'none', horizon: null,
}
