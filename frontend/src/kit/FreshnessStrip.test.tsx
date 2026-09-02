import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import FreshnessStrip, { ageText, tone } from './FreshnessStrip'

// v12 W1 §2.9. Every hub in this app can be read as if it were current — a page
// of ownership figures from Saturday's scrape looks exactly like a page from an
// hour ago. This strip is the cure, so its own failure modes matter: it must
// stay on screen when its fetch fails, and it must show all five sources even
// when the payload carries fewer.
const apiGet = vi.hoisted(() => vi.fn())
vi.mock('../api/client', () => ({
  ApiError: class extends Error {},
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

function serve(rows: unknown[]) {
  apiGet.mockImplementation(async () => ({ rows }))
}

const row = (source: string, age_hours: number | null,
             modified_at: string | null = null) => ({
  source, age_hours, modified_at, path: null,
})

beforeEach(() => { apiGet.mockReset() })

describe('the strip', () => {
  it('names all five sources', async () => {
    serve([row('refresh', 1), row('odds', 1), row('field', 1),
           row('advise', 1), row('backup', 1)])
    render(<FreshnessStrip />)
    await screen.findByTestId('freshness-strip')
    for (const label of ['data', 'odds', 'field EO', 'advice', 'backup']) {
      expect(screen.getByText(label, { exact: false })).toBeInTheDocument()
    }
  })

  it('shows five rows even when the payload carries fewer', async () => {
    // An older server, or a payload that lost a row. A shorter strip is a
    // strip nobody notices is shorter.
    serve([row('refresh', 1)])
    render(<FreshnessStrip />)
    await screen.findByTestId('freshness-strip')
    for (const source of ['refresh', 'odds', 'field', 'advise', 'backup']) {
      expect(screen.getByTestId(`freshness-${source}`)).toBeInTheDocument()
    }
    expect(screen.getByTestId('freshness-backup')).toHaveTextContent('never')
  })

  it('stays visible with five nevers when its own fetch fails', async () => {
    // The one that matters most. A strip that vanished on an error would
    // teach the reader that no strip means nothing is stale.
    apiGet.mockRejectedValue(new Error('offline'))
    render(<FreshnessStrip />)
    await screen.findByTestId('freshness-strip')
    for (const source of ['refresh', 'odds', 'field', 'advise', 'backup']) {
      expect(screen.getByTestId(`freshness-${source}`))
        .toHaveTextContent('never')
    }
  })

  it('carries the timestamp in the title', async () => {
    serve([row('refresh', 2, '2026-09-02T08:00:00+00:00')])
    render(<FreshnessStrip />)
    const cell = await screen.findByTestId('freshness-refresh')
    expect(cell).toHaveAttribute('title', '2026-09-02T08:00:00+00:00')
    expect(screen.getByTestId('freshness-odds'))
      .toHaveAttribute('title', 'never run')
  })

  it('contains no links', async () => {
    // AppShell.test.tsx asserts the shell holds exactly six links, and this
    // now renders inside it. There is nothing here to navigate to anyway.
    serve([row('refresh', 1)])
    const { container } = render(<FreshnessStrip />)
    await screen.findByTestId('freshness-strip')
    expect(container.querySelectorAll('a')).toHaveLength(0)
  })
})

describe('the colouring', () => {
  it('is grey for never, and never red', () => {
    // "Never" and "very old" are different states: a cold clone has not
    // failed at anything, so painting it red would be an invented alarm.
    expect(tone(null)).toBe('text-text-faint')
  })

  it('is green under a day, amber under three, red beyond', () => {
    expect(tone(0.5)).toBe('text-moss')
    expect(tone(23.9)).toBe('text-moss')
    expect(tone(24)).toBe('text-amber')
    expect(tone(71.9)).toBe('text-amber')
    expect(tone(72)).toBe('text-rust')
  })
})

describe('the age text', () => {
  it('reads never, just now, hours then days', () => {
    expect(ageText(null)).toBe('never')
    expect(ageText(0.4)).toBe('just now')
    expect(ageText(5.2)).toBe('5h')
    expect(ageText(47)).toBe('47h')
    expect(ageText(50)).toBe('2d')
  })
})
