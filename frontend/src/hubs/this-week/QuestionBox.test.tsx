import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { POLL_MS } from '../../api/useJob'
import QuestionBox from './QuestionBox'

// v19f §2.3. The answer arrives through the anonymous runner, which `useJob`
// polls, so the clock is faked and a wait is an advance by the hook's own
// POLL_MS rather than a real second spent sitting there. `shouldAdvanceTime`
// because userEvent schedules its own keystroke timers and would otherwise
// sit for ever behind a clock only this file moves.
const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('../../api/client', () => ({
  apiGet: (p: string) => apiGet(p), apiPost: (p: string, b: unknown) => apiPost(p, b),
  errorText: (e: unknown) => String(e), ApiError: class extends Error {},
}))

const FAKE_TIMERS = ['setTimeout', 'setInterval', 'clearTimeout',
  'clearInterval'] as const

function answer(over: Record<string, unknown> = {}) {
  return {
    gw: 5, question: 'Why is Salah captain?', answer: 'He has the highest ep.',
    offences: [], model_command: 'claude', at: '2026-09-16T09:00:00+00:00',
    ...over,
  }
}

/** One poll interval, and the promises the request it fires resolves through. */
async function tick() {
  await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS) })
}

/** Types a question and presses Ask, then lets the poll deliver the answer. */
async function ask(user: ReturnType<typeof userEvent.setup>, text: string) {
  await user.type(screen.getByLabelText('ask about this week'), text)
  await user.click(screen.getByRole('button', { name: 'Ask' }))
  await tick()
}

let jobs = 0

beforeEach(() => {
  vi.useFakeTimers({ toFake: [...FAKE_TIMERS], shouldAdvanceTime: true })
  jobs = 0
  apiGet.mockReset()
  apiPost.mockReset()
  apiPost.mockImplementation(async (_path: string, body: unknown) => {
    jobs += 1
    const question = (body as { question: string }).question
    apiGet.mockImplementation(async () => ({
      id: `j${jobs}`, status: 'done', error: null,
      result: answer({ question, at: `2026-09-16T09:0${jobs}:00+00:00` }),
    }))
    return { job_id: `j${jobs}` }
  })
})
afterEach(() => { vi.useRealTimers() })

describe('QuestionBox', () => {
  it('posts the question that was typed and shows the answer beneath', async () => {
    const user = userEvent.setup()
    render(<QuestionBox modelCommand="claude" />)
    await ask(user, 'Why is Salah captain?')
    expect(apiPost).toHaveBeenCalledWith('/api/ask',
      { question: 'Why is Salah captain?' })
    await waitFor(() =>
      expect(screen.getByText('He has the highest ep.')).toBeInTheDocument())
  })

  it('strikes an answer through and lists every offence when the check fails',
    async () => {
      const user = userEvent.setup()
      apiPost.mockImplementation(async () => {
        apiGet.mockImplementation(async () => ({
          id: 'j', status: 'done', error: null,
          result: answer({
            answer: 'He is worth 52 points.',
            offences: ['52 is not in the facts', 'no such reason in the facts'],
          }),
        }))
        return { job_id: 'j' }
      })
      render(<QuestionBox modelCommand="claude" />)
      await ask(user, 'Why?')
      const prose = await screen.findByText('He is worth 52 points.')
      expect(prose.className).toContain('line-through')
      expect(screen.getByText('52 is not in the facts')).toBeInTheDocument()
      expect(screen.getByText('no such reason in the facts')).toBeInTheDocument()
    })

  it('keeps the last three answers and drops the oldest on the fourth',
    async () => {
      const user = userEvent.setup()
      render(<QuestionBox modelCommand="claude" />)
      await ask(user, 'first')
      await ask(user, 'second')
      await ask(user, 'third')
      await waitFor(() => expect(screen.getByText('third')).toBeInTheDocument())
      expect(screen.getByText('first')).toBeInTheDocument()
      await ask(user, 'fourth')
      await waitFor(() => expect(screen.getByText('fourth')).toBeInTheDocument())
      expect(screen.queryByText('first')).not.toBeInTheDocument()
      expect(screen.getByText('second')).toBeInTheDocument()
      expect(screen.getByText('third')).toBeInTheDocument()
    })

  it('says so instead of asking when no model command is configured', async () => {
    render(<QuestionBox modelCommand={null} />)
    expect(screen.getByText(/No model command is configured/)).toBeInTheDocument()
    expect(screen.queryByLabelText('ask about this week')).not.toBeInTheDocument()
    expect(apiPost).not.toHaveBeenCalled()
  })
})
