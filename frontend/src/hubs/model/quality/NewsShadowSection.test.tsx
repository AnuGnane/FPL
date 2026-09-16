import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { NewsShadowData } from '../../../types'
import NewsShadowSection from './NewsShadowSection'

// Moved beside the section in v19h §2.1. The `rows > 0` gate that decides
// whether the card is drawn at all belongs to the tab, so that case stays in
// `QualityTab.test.tsx`.

const shadow = {
  run_at: '2026-09-12T00:00:00+00:00', git_sha: 'abc1234', rows: 1400,
  overall: { brier_news: 0.091, brier_flags: 0.102, mae_news: 12.4,
             mae_flags: 14.1, rows: 1400 },
  by_gw: [
    { gw: 3, brier_news: 0.095, brier_flags: 0.11, mae_news: 12.9,
      mae_flags: 14.8, rows: 700, cum_brier_news: 0.095,
      cum_brier_flags: 0.11, cum_mae_news: 12.9, cum_mae_flags: 14.8 },
    { gw: 4, brier_news: 0.087, brier_flags: 0.094, mae_news: 11.9,
      mae_flags: 13.4, rows: 700, cum_brier_news: 0.091,
      cum_brier_flags: 0.102, cum_mae_news: 12.4, cum_mae_flags: 14.1 },
  ],
} as NewsShadowData

describe('NewsShadowSection', () => {
  it('scores the news layer against the flags per gameweek', () => {
    render(<NewsShadowSection shadow={shadow} />)
    expect(screen.getByRole('heading', { name: /news layer/i }))
      .toBeInTheDocument()
    expect(screen.getByText('GW3')).toBeInTheDocument()
    expect(screen.getByText('GW4')).toBeInTheDocument()
    expect(screen.getByText('0.095')).toBeInTheDocument()
    expect(screen.getByText('0.11')).toBeInTheDocument()
  })

  it('states the verdict in a sentence', () => {
    render(<NewsShadowSection shadow={shadow} />)
    expect(screen.getByText(/news is ahead on both/i)).toBeInTheDocument()
  })

  it('says nothing is scored yet when the summary is the empty object', () => {
    // `overall` is `{}` until a gameweek has been graded, so the verdict reads
    // the two numbers by type rather than by presence.
    render(<NewsShadowSection
      shadow={{ ...shadow, overall: {} } as unknown as NewsShadowData} />)
    expect(screen.getByText('Nothing scored yet.')).toBeInTheDocument()
  })
})
