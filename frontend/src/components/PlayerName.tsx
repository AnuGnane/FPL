import { useState } from 'react'
import ExplainModal from './ExplainModal'

export default function PlayerName(
  { code, name }: { code: number; name: string },
) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button className="player-link" onClick={() => setOpen(true)}>
        {name}
      </button>
      {open && <ExplainModal code={code} onClose={() => setOpen(false)} />}
    </>
  )
}
