import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Ticker from './Ticker'

const apiGet = vi.hoisted(() => vi.fn())
vi.mock('../api/client', () => ({
  ApiError: class extends Error {},
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockImplementation(async (path: string) => {
    if (path.startsWith('/api/health')) {
      return { data: [], models: [], odds_key_present: false,
               launchd: { log: '', present: false, modified_at: null,
                          last_line: null },
               model_health: null, artifacts: [] }
    }
    return {
      gws: [3], source: 'elo',
      teams: [{ code: 300, name: 'Liverpool', short_name: 'LIV',
                mean_difficulty: 0.2,
                cells: [{ gw: 3, opponent: 'ARS', home: true,
                          difficulty: 0.2 }] }],
    }
  })
})

describe('Ticker page', () => {
  it('nudges towards an odds key when Elo is standing in for one',
    async () => {
      render(<Ticker />)
      expect(await screen.findByText(/Elo-implied/)).toBeInTheDocument()
      expect(screen.getByText(/add an odds key/i)).toBeInTheDocument()
      expect(apiGet).toHaveBeenCalledWith('/api/health')
    })
})
