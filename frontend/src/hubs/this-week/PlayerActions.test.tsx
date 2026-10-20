import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import PlayerActions from './PlayerActions'

// Holiday F-155: the v19e §2.4 menu, alone. Its use inside the squad table
// is `SquadTable.test.tsx`'s; here each item's request is pinned.

const navigate = vi.hoisted(() => vi.fn())
vi.mock('react-router-dom', async () => ({
  ...await vi.importActual<typeof import('react-router-dom')>(
    'react-router-dom'),
  useNavigate: () => navigate,
}))

async function choose(item: string) {
  navigate.mockReset()
  render(<MemoryRouter><PlayerActions code={7} name="Saka" /></MemoryRouter>)
  await userEvent.click(screen.getByRole('button', { name: 'actions for Saka' }))
  await userEvent.click(screen.getByRole('menuitem', { name: item }))
}

describe('PlayerActions', () => {
  it('offers lock, ban and must sell, in that order', async () => {
    render(<MemoryRouter><PlayerActions code={7} name="Saka" /></MemoryRouter>)
    await userEvent.click(screen.getByRole('button', { name: 'actions for Saka' }))
    expect(screen.getAllByRole('menuitem').map((item) => item.textContent))
      .toEqual(['Lock', 'Ban', 'Must sell'])
  })

  it('hands the lab a lock on the player’s code and nothing else', async () => {
    await choose('Lock')
    expect(navigate).toHaveBeenCalledWith('/planning?tab=whatif', {
      state: { whatif: expect.objectContaining({ lock: [7], ban: [],
                                                 force_out: [] }) },
    })
  })

  it('hands the lab a ban on the player’s code', async () => {
    await choose('Ban')
    expect(navigate).toHaveBeenCalledWith('/planning?tab=whatif', {
      state: { whatif: expect.objectContaining({ ban: [7], lock: [],
                                                 force_out: [] }) },
    })
  })

  it('makes must sell a force_out, not a ban', async () => {
    await choose('Must sell')
    expect(navigate).toHaveBeenCalledWith('/planning?tab=whatif', {
      state: { whatif: expect.objectContaining({ force_out: [7], ban: [],
                                                 lock: [] }) },
    })
  })
})
