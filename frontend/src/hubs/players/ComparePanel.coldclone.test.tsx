/**
 * The comparison on a cold clone (plan A18).
 *
 * Its own file, because the panel's ordinary empty states are about *selection
 * count* — fewer than two ticked, more than four — and this one is about data.
 * `coldclone.test.tsx` cannot reach it either: Radix renders only each hub's
 * default tab, and Compare is behind Players' non-default tab *and* a
 * `players.length < 2` guard.
 *
 * The honest cold-clone answer for this view is not an empty state. The rows
 * came in as props, so the panel degrades to what the explorer already knew:
 * both cards, no components, no matrix, no breakdown, no chips — and no
 * console error.
 */
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ComparePanel from './ComparePanel'
import type { PlayerRow } from '../../types'

const { apiGet, ApiError } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  ApiError: class ApiError extends Error {
    status = 422
    detail: unknown = null
  },
}))

vi.mock('../../api/client', () => ({
  ApiError,
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts')
  const { cloneElement, isValidElement } = await import('react')
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div style={{ width: 400, height: 200 }}>
        {isValidElement(children)
          ? cloneElement(children as React.ReactElement<Record<string, unknown>>,
                         { width: 400, height: 200 })
          : children}
      </div>
    ),
  }
})

function player(over: Partial<PlayerRow>): PlayerRow {
  return {
    code: 1, element: 1, name: 'Salah', position: 'MID', team_code: 300,
    team_name: 'Liverpool', price: 13, ep_next: 6.4, ep_horizon: 12,
    ownership: 42.1, league_eo: 61.5, field_eo: null, field_se: null,
    field_n: null, field_eo_deadline: null, field_eo_delta: null,
    field_class: null, available: true, status: 'a', news: '',
    chance_of_playing: null, penalties_order: null, free_kicks_order: null,
    corners_order: null, in_squad: false, last4: [], ep_lo: null,
    ep_hi: null, p_haul: null, p_blank: null, ...over,
  }
}

describe('ComparePanel on a cold clone', () => {
  it('still draws both cards, with no decoration and no console error',
    async () => {
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
      apiGet.mockRejectedValue(new ApiError('nothing on disk yet'))
      render(<ComparePanel gw={5} players={[
        player({}), player({ code: 2, name: 'Saka', team_code: 301 })]} />)

      const salah = await screen.findByTestId('compare-1')
      expect(within(salah).getByRole('heading', { name: 'Salah' }))
        .toBeInTheDocument()
      expect(screen.getByTestId('compare-2')).toBeInTheDocument()
      // What the row itself knew survives; everything fetched is absent.
      expect(salah).toHaveTextContent('13.0')
      expect(screen.queryByTestId('breakdown-1')).toBeNull()
      expect(screen.queryByTestId('minutes-1')).toBeNull()
      expect(within(salah).queryAllByTitle(/^GW/)).toHaveLength(0)
      // Absent, never zero: no field log means no EO and no error bar.
      expect(within(salah).getByTestId('field-eo-1')).toHaveTextContent('—')
      expect(within(salah).getByTestId('field-eo-1')).not.toHaveTextContent('±')

      expect(spy).not.toHaveBeenCalled()
      spy.mockRestore()
    })
})
