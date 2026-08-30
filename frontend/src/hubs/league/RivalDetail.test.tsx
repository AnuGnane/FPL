import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RivalDetail from './RivalDetail'

// vi.mock's factory is hoisted above the file body, so the spy has to be
// hoisted with it.
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../../api/client', () => ({
  ApiError: class extends Error {},
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

const DETAIL = {
  entry: 2,
  name: 'Ten Hag Hive',
  player_name: 'Riv',
  total: 190,
  team_value: 101.8,
  chips_used: ['bboost'],
  captain: {
    code: 100, element: 7, name: 'Salah', position: 'MID', price: 13.0,
    is_captain: true, multiplier: 2,
  },
  squad_gw: 2,
  squad: [
    {
      code: 100, element: 7, name: 'Salah', position: 'MID', price: 13.0,
      is_captain: true, multiplier: 2,
    },
    {
      code: 101, element: 8, name: 'Bloke', position: 'DEF', price: 4.5,
      is_captain: false, multiplier: 1,
    },
  ],
  shared: [{
    code: 100, element: 7, name: 'Salah', position: 'MID', price: 13.0,
    is_captain: true, multiplier: 2,
  }],
  their_differentials: [{
    code: 101, element: 8, name: 'Bloke', position: 'DEF', price: 4.5,
    is_captain: false, multiplier: 1,
  }],
  your_differentials: [],
  live_points: 74,
}

function renderDetail() {
  render(
    <MemoryRouter initialEntries={['/league/rival/2']}>
      <Routes>
        <Route path="/league/rival/:id" element={<RivalDetail />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockResolvedValue(DETAIL)
})

describe('Rival detail', () => {
  it('shows squad, captain, chips, value, overlap and live points',
    async () => {
      renderDetail()
      expect(await screen.findByRole('heading', { name: /Ten Hag Hive/ }))
        .toBeInTheDocument()
      expect(screen.getByText(/£101.8m/)).toBeInTheDocument()
      expect(screen.getByText(/Captain: Salah/)).toBeInTheDocument()
      expect(screen.getByText('bboost')).toBeInTheDocument()
      // The count is its own <span className="num">, so match across children.
      expect(screen.getByText(
        (_, el) => el?.tagName === 'P'
          && /74 live points/.test(el.textContent ?? ''),
      )).toBeInTheDocument()
      expect(screen.getByText('Shared (1)')).toBeInTheDocument()
      expect(screen.getByText('Their differentials (1)')).toBeInTheDocument()
      expect(screen.getByText('Your differentials (0)')).toBeInTheDocument()
    })

  // The squad is the last finished gameweek's public picks while live points
  // come from the gameweek in progress; say which gameweek the squad is.
  it('labels the squad with the gameweek it was picked in', async () => {
    renderDetail()
    expect(await screen.findByText('Squad · GW2 (2)')).toBeInTheDocument()
  })
})
