import { useState } from 'react'
import { writeToken } from '../api/client'
import Button from './Button'
import { INPUT_CLASS } from './field'

/**
 * The distinctive half of the LAN refusal `web/app.py:202` sends.
 *
 * Matched on the sentence rather than on the status because the eight panels
 * that render a failed write keep `errorText(e)` — a string — and not the
 * `ApiError` it came from (v19b §2.5). The header's name is in no other
 * message the server can send, so the test is narrow enough to be safe and
 * the alternative was re-plumbing a status through every one of them.
 */
const REFUSAL = 'X-Gaffer-Token'

/** Whether a rendered error sentence is the LAN write refusal. */
export function isTokenRefusal(sentence: unknown): boolean {
  return typeof sentence === 'string' && sentence.includes(REFUSAL)
}

export interface TokenPromptProps {
  /** The sentence being rendered above; anything else renders nothing. */
  sentence: unknown
  /** Fired after the token is stored, so the caller can make the write
   *  again. Optional: a panel with no handle on the write it just lost still
   *  gets the field, and the manager clicks the control again. */
  onRetry?: () => void
}

/**
 * Somewhere to type the write token, beneath the refusal that asks for it
 * (v19b §2.5).
 *
 * A phone opened on a bare LAN URL — no `?token=` — gets the sentence and,
 * until now, nowhere to put the token the terminal printed. Reads are open,
 * so this appears only under a refused *write*, which is the only thing the
 * middleware guards.
 */
export default function TokenPrompt({ sentence, onRetry }: TokenPromptProps) {
  const [value, setValue] = useState('')
  const [saved, setSaved] = useState(false)

  if (!isTokenRefusal(sentence)) return null

  const use = () => {
    writeToken(value.trim())
    setSaved(true)
    onRetry?.()
  }

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <input
        aria-label="write token"
        className={INPUT_CLASS}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => { if (event.key === 'Enter') use() }}
      />
      <Button onClick={use}>Use token</Button>
      {saved && (
        <span className="text-text-muted" data-testid="token-saved">
          Token saved — this tab will send it from now on.
        </span>
      )}
    </div>
  )
}
