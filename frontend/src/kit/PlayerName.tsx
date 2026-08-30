import { useState } from 'react'
import ExplainModal from './ExplainModal'
import PosBadge from './PosBadge'

export interface PlayerNameProps {
  code: number
  name: string
  /** When the row's payload carries it, the identity dot rides along. */
  pos?: string | null
}

/**
 * A player's name, everywhere: the one control that opens his EP breakdown.
 *
 * Styled as text rather than as a button, because a squad list of fifteen
 * buttons reads as a toolbar. The underline on hover is the only affordance
 * it needs.
 */
export default function PlayerName({ code, name, pos }: PlayerNameProps) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <span className="inline-flex items-center gap-1.5">
        {pos !== undefined && <PosBadge pos={pos} variant="dot" />}
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="text-text hover:underline"
        >
          {name}
        </button>
      </span>
      {open && <ExplainModal code={code} onClose={() => setOpen(false)} />}
    </>
  )
}
