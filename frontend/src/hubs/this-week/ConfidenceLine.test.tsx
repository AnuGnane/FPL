import { act, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ConfidenceLine from './ConfidenceLine'
import * as client from '../../api/client'

function mock(body: unknown) {
  vi.spyOn(client, 'apiGet').mockResolvedValue(body as never)
}

describe('ConfidenceLine', () => {
  it('prints the sentence the ledger produced', async () => {
    mock({ captain: { tier: 'backed', reviewed: 8, graded: 5, wins: 4,
                      losses: 1, aligned: 2,
                      text: 'The model’s captain outscored yours in 4 of '
                        + '5 comparable gameweeks (2 you agreed on).' } })
    render(<ConfidenceLine />)
    expect(await screen.findByText(/4 of 5 comparable gameweeks/))
      .toBeInTheDocument()
  })

  it('renders the too-early branch as prose, not as a warning', async () => {
    // The sentence `confidence.captain_confidence` actually ships at n=1:
    // a count of what was looked at, and no ratio to read a verdict out of.
    mock({ captain: { tier: 'early', reviewed: 1, graded: 1, wins: 1,
                      losses: 0, aligned: 0,
                      text: 'Too early to grade — 1 gameweek reviewed, '
                        + '1 gradeable so far.' } })
    render(<ConfidenceLine />)
    expect(await screen.findByText(/Too early to grade/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  // Holiday F-159: the hook had no reader. The line is the server's sentence
  // and nothing else, so an answer with no sentence draws no line at all.
  it('marks the line it draws from the sentence', async () => {
    mock({ captain: { tier: 'early', reviewed: 0, graded: 0, wins: 0,
                      losses: 0, aligned: 0, text: 'Nothing graded yet.' } })
    render(<ConfidenceLine />)
    expect(await screen.findByTestId('captain-confidence'))
      .toHaveTextContent('Nothing graded yet.')
  })

  it('draws no line when the answer carries no sentence', async () => {
    // Waits on the answer itself, not on the request: absence asserted
    // before the data lands would pass whatever the guard did.
    const answer = Promise.resolve({ captain: null })
    vi.spyOn(client, 'apiGet').mockReturnValue(answer as never)
    const { container } = render(<ConfidenceLine />)
    await act(async () => { await answer })
    expect(screen.queryByTestId('captain-confidence')).toBeNull()
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing at all when the endpoint cannot answer', async () => {
    vi.spyOn(client, 'apiGet').mockRejectedValue(new Error('down'))
    const { container } = render(<ConfidenceLine />)
    await waitFor(() => expect(container).toBeEmptyDOMElement())
  })
})
