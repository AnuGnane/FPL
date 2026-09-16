import { useState } from 'react'
import { useJob } from '../../api/useJob'
import { Button, Callout, INPUT_CLASS } from '../../kit'
import type { AskAnswer } from '../../types'

/** How many of the session's answers stay on the page (v19f §2.3). Three,
 *  because the reader's second question is nearly always about the first and
 *  almost never about the fifth, and a box that grows into a transcript is a
 *  box nobody scrolls. Component state: a reload clears them, which is the
 *  honest thing to do with answers the server never banked. */
const KEPT = 3

/**
 * One answer with its check (v19f §2.3).
 *
 * An answer that failed `check_brief` is neither hidden nor served as prose:
 * it is struck through with every offence beneath it. Hiding it would leave
 * the reader wondering what was asked; serving it plain would put a number
 * that is not in the facts next to fifteen that are, which is the one thing
 * the brief's check exists to prevent.
 */
function CheckedAnswer({ answer }: { answer: AskAnswer }) {
  const failed = answer.offences.length > 0
  return (
    <>
      <p className={failed
        ? 'max-w-prose text-text-muted line-through'
        : 'max-w-prose text-text'}>
        {answer.answer}
      </p>
      {answer.offences.map((offence) => (
        <p key={offence} className="text-down">{offence}</p>
      ))}
    </>
  )
}

export interface QuestionBoxProps {
  /** The brief panel's `model_command`. Null is the panel saying no command
   *  is configured — the same field the card's own stamp reads — and with no
   *  command there is nothing to ask, so the box says so instead of offering
   *  a button whose only possible answer is a failure. */
  modelCommand: string | null
}

/**
 * The manager's second question (v19f §2.3).
 *
 * The brief answers the week's question once; this asks another of the same
 * facts, through the same command and the same truth check. It fetches
 * nothing until it is asked, so This Week's first render is unchanged.
 *
 * The answer under the input and the session's list are one list, newest
 * first, rather than a current answer plus a history: two renderings of the
 * same thing would have to agree about the strike, and the newest entry of
 * the list already sits directly under the input.
 */
export default function QuestionBox({ modelCommand }: QuestionBoxProps) {
  const [question, setQuestion] = useState('')
  const [answers, setAnswers] = useState<AskAnswer[]>([])
  const job = useJob({ path: '/api/ask', slot: 'ask' })
  const busy = job.status === 'queued' || job.status === 'running'
  const result = job.status === 'done' ? (job.result as AskAnswer | null) : null

  // Adjusted during render, not in an effect: React re-runs this component
  // before painting and nothing outside it is being synchronised, so an
  // effect would only buy a second render and a lint warning. Keyed on the
  // job id, which is the hook's own name for "a different answer".
  const [banked, setBanked] = useState<string | null>(null)
  if (result !== null && job.jobId !== banked) {
    setBanked(job.jobId)
    setAnswers((prev) => [result, ...prev].slice(0, KEPT))
  }

  if (modelCommand === null) {
    return (
      <p className="text-text-muted">
        No model command is configured, so there is nothing to ask.
      </p>
    )
  }

  const ask = () => {
    const asked = question.trim()
    if (asked === '' || busy) return
    setQuestion('')
    void job.start({ question: asked })
  }

  return (
    <>
      <form
        className="mb-2 flex flex-wrap items-center gap-2"
        onSubmit={(e) => { e.preventDefault(); ask() }}
      >
        <input
          className={`${INPUT_CLASS} min-w-0 flex-1`}
          aria-label="ask about this week"
          placeholder="Ask about this week's plan"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <Button type="submit" disabled={busy || question.trim() === ''}>
          {busy ? 'Asking…' : 'Ask'}
        </Button>
      </form>
      {job.status === 'error' && (
        <Callout tone="error" className="mb-2">{job.error}</Callout>
      )}
      {answers.map((answer) => (
        <div key={answer.at} className="mb-2">
          <p className="text-text-muted">{answer.question}</p>
          <CheckedAnswer answer={answer} />
        </div>
      ))}
    </>
  )
}
