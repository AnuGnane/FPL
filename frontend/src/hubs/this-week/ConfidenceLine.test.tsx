import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ConfidenceLine from './ConfidenceLine'
import * as client from '../../api/client'

function mock(body: unknown) {
  vi.spyOn(client, 'apiGet').mockResolvedValue(body as never)
}

describe('ConfidenceLine', () => {
  it('prints the sentence the ledger produced', async () => {
    mock({ captain: { tier: 'backed', reviewed: 6, graded: 5, wins: 4,
                      losses: 1, aligned: 0,
                      text: 'The model’s captain outscored yours in 4 of '
                        + '5 comparable gameweeks (0 you agreed on).' } })
    render(<ConfidenceLine />)
    expect(await screen.findByText(/4 of 5 comparable gameweeks/))
      .toBeInTheDocument()
  })

  it('renders the too-early branch as prose, not as a warning', async () => {
    mock({ captain: { tier: 'early', reviewed: 1, graded: 1, wins: 1,
                      losses: 0, aligned: 0,
                      text: 'Too early to grade — the model’s '
                        + 'captain has been comparable to yours in 1 of 1 '
                        + 'reviewed gameweeks.' } })
    render(<ConfidenceLine />)
    expect(await screen.findByText(/Too early to grade/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('renders nothing at all when the endpoint cannot answer', async () => {
    vi.spyOn(client, 'apiGet').mockRejectedValue(new Error('down'))
    const { container } = render(<ConfidenceLine />)
    await waitFor(() => expect(container).toBeEmptyDOMElement())
  })
})
