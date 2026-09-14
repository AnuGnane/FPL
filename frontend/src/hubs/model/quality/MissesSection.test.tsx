import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MissesSection from './MissesSection'

// Moved beside the section in v18f §2.1, out of the tab's `v8g calibration`
// block.

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../../../api/client', () => ({
  ApiError: class ApiError extends Error {
    status = 422
    detail: unknown = null
  },
  errorText: (e: unknown) => (e instanceof Error ? e.message : String(e)),
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

function mockMisses(body: unknown) {
  apiGet.mockImplementation(() => Promise.resolve(body))
}

beforeEach(() => {
  apiGet.mockReset()
  mockMisses({ gw: null, rows: [] })
})

describe('the biggest misses', () => {
  it('lists the biggest misses with their sign', async () => {
    mockMisses({ gw: 5, rows: [
      { code: 11, name: 'Saka', position: 'MID', price: 10.0, ep: 5.5,
        actual: 16, minutes: 90, miss: 10.5 },
      { code: 22, name: 'Sub', position: 'FWD', price: 6.0, ep: 7.0,
        actual: 1, minutes: 12, miss: -6.0 },
    ] })
    render(<MemoryRouter><MissesSection /></MemoryRouter>)
    expect(await screen.findByText('Saka')).toBeInTheDocument()
    expect(screen.getByText('+10.5')).toBeInTheDocument()
    expect(screen.getByText('-6.0')).toBeInTheDocument()
  })

  it('renders no misses card when no week has been scored', async () => {
    // The card is absent before the read lands and after it, so the wait is
    // on the read: rendered alone, there is no sibling heading to await the
    // way this case did inside the tab (v18f §2.1).
    mockMisses({ gw: null, rows: [] })
    const { container } = render(
      <MemoryRouter><MissesSection /></MemoryRouter>)
    await waitFor(() => { expect(apiGet).toHaveBeenCalledWith('/api/misses') })
    expect(screen.queryByText(/Biggest misses/)).toBeNull()
    expect(container).toBeEmptyDOMElement()
  })
})
