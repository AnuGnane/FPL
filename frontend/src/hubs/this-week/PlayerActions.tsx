import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { useNavigate } from 'react-router-dom'
import type { WhatIfRequest } from '../../types'
import { EMPTY_WHATIF } from '../planning/WhatIfTab'

/**
 * Lock, ban or must-sell the player the reader is looking at (v19e §2.4).
 *
 * The What-If lab could already express all three, and the only way to reach
 * it was to type a name into the constraints panel or to press a Try-it
 * button on the planner board — so the squad on This Week, the one place the
 * reader is actually looking at his own players, was the one place he could
 * not act on one. Each item hands the lab a request through `location.state`
 * rather than a query string: a constraint list is a body, not a URL, and
 * Planning already owns the state the lab reads.
 *
 * Deliberately one code and nothing else. The menu starts a solve the reader
 * then edits in the panel; prefilling more of it here would be this component
 * guessing at a plan.
 */

/** *Must sell* is `force_out`, not `ban`: banning an owned player takes him
 *  out of the candidate pool, so he never leaves the squad and the sale money
 *  never arrives (`WhatIfRequest.force_out`, v12 W3 §4.1). */
const ITEMS: Array<[string, 'lock' | 'ban' | 'force_out']> = [
  ['Lock', 'lock'], ['Ban', 'ban'], ['Must sell', 'force_out'],
]

export interface PlayerActionsProps {
  code: number
  name: string
  /** Where the trigger sits. The pitch's card is drawn by a closed kit
   *  primitive, so its menu is laid over the card's own corner rather than
   *  inside it — which is also what keeps the pitch's first paint where it
   *  was (v19e §2.4). */
  className?: string
}

export default function PlayerActions(
  { code, name, className = '' }: PlayerActionsProps,
) {
  const navigate = useNavigate()

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger
        aria-label={`actions for ${name}`}
        className={`rounded-chip px-1 leading-none text-text-muted
                    hover:text-text ${className}`}
      >
        ⋯
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content className="rounded-ctl border border-border
          bg-raised p-1 text-text-secondary">
          {ITEMS.map(([label, field]) => (
            <DropdownMenu.Item
              key={field}
              onSelect={() => {
                const request: WhatIfRequest = {
                  ...EMPTY_WHATIF, [field]: [code],
                }
                navigate('/planning?tab=whatif', { state: { whatif: request } })
              }}
              className="cursor-pointer rounded-chip px-2 py-1 outline-none
                         data-[highlighted]:bg-base data-[highlighted]:text-text"
            >
              {label}
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}
