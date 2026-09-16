import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import FixtureMatrix from './FixtureMatrix'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../../api/client', () => ({
  ApiError: class extends Error { status = 0; detail: unknown = null },
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

const MATRIX = {
  gws: [5, 6],
  source: 'dixon_coles',
  teams: [
    {
      code: 300, name: 'Liverpool', short_name: 'LIV', mean_attack: 0.2,
      mean_defence: 0.3,
      cells: [
        { gw: 5, opponent: 'EVE', home: true, attack: 0.1, defence: 0.2 },
        { gw: 6, opponent: 'ARS', home: false, attack: 0.8, defence: 0.9 },
      ],
    },
  ],
}

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockResolvedValue(MATRIX)
})

describe('FixtureMatrix', () => {
  // v19b §2.6, the v18e residual. The panel used to be handed `gw ?? 1` and
  // ask for gameweek 1's matrix before the advice had said which week this
  // is — an answer nothing ever rendered, because the real request followed
  // the moment `gw` landed.
  it('asks for nothing until the gameweek is known', async () => {
    render(<FixtureMatrix from={null} />)
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(apiGet).not.toHaveBeenCalled()
  })

  it('draws a row per team and a column per gameweek', async () => {
    render(<FixtureMatrix from={5} />)
    expect(await screen.findByText('LIV')).toBeInTheDocument()
    expect(screen.getByText('GW5')).toBeInTheDocument()
    expect(screen.getByText('GW6')).toBeInTheDocument()
  })

  it('shows the opponent, capitalised at home and lowercase away', async () => {
    render(<FixtureMatrix from={5} />)
    expect(await screen.findByText('EVE')).toBeInTheDocument()
    expect(screen.getByText('ars')).toBeInTheDocument()
  })

  it('colours cells by the attack score by default', async () => {
    render(<FixtureMatrix from={5} />)
    const cell = await screen.findByTestId('matrix-cell-300-5')
    expect(cell).toHaveAttribute('data-score', '0.1')
  })

  it('switches to the defence view', async () => {
    render(<FixtureMatrix from={5} />)
    await userEvent.click(await screen.findByRole('button',
                                                  { name: 'Clean sheet' }))
    expect(screen.getByTestId('matrix-cell-300-5'))
      .toHaveAttribute('data-score', '0.2')
  })

  it('shows an empty state naming the command when there is no team model',
    async () => {
      apiGet.mockResolvedValue({ gws: [], teams: [], source: 'none' })
      render(<FixtureMatrix from={5} />)
      expect(await screen.findByText(/no fixture difficulty/i))
        .toBeInTheDocument()
      expect(screen.getByText('gaffer train')).toBeInTheDocument()
    })
})
