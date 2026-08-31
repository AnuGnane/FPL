import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import DigestCard from './DigestCard'

// This repo mocks the api client rather than the network (no MSW anywhere in
// the suite), so the card's own GET and the two JobButtons' `/api/jobs/current`
// probe are answered by path from one implementation.
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../../api/client', () => ({
  ApiError: class extends Error {},
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

const DIGEST = {
  available: true,
  digest: {
    kind: 'friday', generated_at: '2026-08-28T17:00:00+00:00', gw: 5,
    headline: 'GW5: captain Haaland, 1 transfer.',
    sections: [
      { key: 'move', title: 'The plan',
        bits: ['Haaland in, Rice out', 'Captain Haaland.'] },
      { key: 'movers', title: 'Prices tonight',
        bits: ['Saka may rise tonight (98%)'] },
    ],
  },
}

function serve(panel: unknown = DIGEST) {
  apiGet.mockImplementation((path: string) => {
    if (path.startsWith('/api/digest')) {
      return panel instanceof Error
        ? Promise.reject(panel) : Promise.resolve(panel)
    }
    return Promise.resolve(null)          // nothing is running
  })
}

beforeEach(() => {
  apiGet.mockReset()
  serve()
})

describe('DigestCard', () => {
  it('renders the headline and every section', async () => {
    render(<DigestCard />)
    expect(await screen.findByText(DIGEST.digest.headline))
      .toBeInTheDocument()
    expect(screen.getByText('The plan')).toBeInTheDocument()
    expect(screen.getByText('Prices tonight')).toBeInTheDocument()
  })

  it('joins each section\'s bits into one sentence', async () => {
    render(<DigestCard />)
    expect(await screen.findByText(/Haaland in, Rice out.*Captain Haaland/))
      .toBeInTheDocument()
  })

  it('names which digest it is and when it was made', async () => {
    render(<DigestCard />)
    // The stamp line, not the build button that carries the same words.
    expect(await screen.findByText(/Friday briefing ·/)).toBeInTheDocument()
  })

  it('offers the two buttons when there is no digest yet', async () => {
    serve({ available: false, digest: null })
    render(<DigestCard />)
    expect(await screen.findByText(/No digest yet/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Friday briefing/ }))
      .toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Tuesday debrief/ }))
      .toBeInTheDocument()
  })

  it('renders nothing at all when the endpoint is down', async () => {
    // The card is decoration on a page that already has its advice: a failure
    // is silence, never an error state above the recommended moves.
    serve(new Error('network'))
    const { container } = render(<DigestCard />)
    await new Promise((r) => { setTimeout(r, 0) })
    expect(container.textContent).toBe('')
  })
})
