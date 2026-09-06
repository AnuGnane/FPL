import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BriefCard from './BriefCard'

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('../../api/client', () => ({
  apiGet: (p: string) => apiGet(p), apiPost: (p: string, b: unknown) => apiPost(p, b),
  errorText: (e: unknown) => String(e), ApiError: class extends Error {},
}))
vi.mock('../../api/useJobStream', () => ({
  useJobStream: () => ({ status: 'idle', lines: [], error: null, jobId: null,
    start: vi.fn(), attach: vi.fn(), reset: vi.fn() }),
}))

const BRIEF = { gw: 4, prose: 'The ladder chose free transfers only.\n\nGuéhi keeps the armband.',
  checked_at: '2026-09-05T09:00:00+00:00', run_stamp: 's', model_command: 'claude',
  note: null, fallback: null }
const NONE = { gw: null, prose: null, checked_at: null, run_stamp: null, model_command: null,
  note: 'the brief did not pass its check this week (number 52 is not in the facts)',
  fallback: { available: false, digest: null } }

function serve(panel: unknown) {
  apiGet.mockImplementation((path: string) => {
    if (path.startsWith('/api/brief')) return Promise.resolve(panel)
    if (path.startsWith('/api/jobs/')) return Promise.resolve({ id: 'j', status: 'done', result: {}, error: null })
    return Promise.resolve(null)
  })
}
beforeEach(() => { apiGet.mockReset(); apiPost.mockReset(); apiPost.mockResolvedValue({ job_id: 'j' }) })

describe('BriefCard', () => {
  it('renders the prose in paragraphs with the stamp and the model', async () => {
    serve(BRIEF)
    render(<BriefCard />)
    expect(await screen.findByText('The ladder chose free transfers only.')).toBeInTheDocument()
    expect(screen.getByText('Guéhi keeps the armband.')).toBeInTheDocument()
    expect(screen.getByText(/GW4 · claude/)).toBeInTheDocument()
  })

  it('falls back to the digest card with the note when there is no brief', async () => {
    serve(NONE)
    render(<BriefCard />)
    expect(await screen.findByText(/No digest yet/)).toBeInTheDocument()
    expect(screen.getByText(/did not pass its check/)).toBeInTheDocument()
  })

  it('writes a brief on the button and reloads', async () => {
    serve(BRIEF)
    render(<BriefCard />)
    await userEvent.click(await screen.findByRole('button', { name: 'Write the brief' }))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/brief', undefined))
  })
})
