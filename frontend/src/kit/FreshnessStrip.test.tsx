import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import FreshnessStrip, { ageText, tone } from './FreshnessStrip'

// v12 W1 §2.9. Every hub in this app can be read as if it were current — a page
// of ownership figures from Saturday's scrape looks exactly like a page from an
// hour ago. This strip is the cure, so its own failure modes matter: it must
// show all five sources even when the payload carries fewer, and it must never
// draw five nevers over a question it could not ask (v18e ruling 7).
const { apiGet, FakeApiError } = vi.hoisted(() => {
  class FakeApiError extends Error {
    status: number

    constructor(status: number, message: string) {
      super(message)
      this.status = status
    }
  }
  return { apiGet: vi.fn(), FakeApiError }
})
vi.mock('../api/client', () => ({
  ApiError: FakeApiError,
  errorText: (e: unknown) => (e instanceof Error ? e.message : String(e)),
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

function serve(rows: unknown[]) {
  apiGet.mockImplementation(async () => ({ rows }))
}

const row = (source: string, age_hours: number | null,
             modified_at: string | null = null, cadence_hours = 24) => ({
  source, age_hours, modified_at, path: null, cadence_hours,
})

beforeEach(() => { apiGet.mockReset() })

const SOURCES = ['refresh', 'odds', 'field', 'advise', 'backup', 'prices',
  'snapshot']

describe('the strip', () => {
  it('names all seven sources, in the order the server sends them', async () => {
    serve(SOURCES.map((source) => row(source, 1)))
    render(<FreshnessStrip />)
    const strip = await screen.findByTestId('freshness-strip')
    // v19a §2.2: prices and the availability snapshot join the five, at the
    // end, so the strip a reader already scans left to right does not move.
    for (const label of ['data', 'odds', 'field EO', 'advice', 'backup',
      'prices', 'availability']) {
      expect(screen.getByText(label, { exact: false })).toBeInTheDocument()
    }
    expect(strip.textContent).toMatch(/backup.*prices.*availability/)
  })

  it('shows seven rows even when the payload carries fewer', async () => {
    // An older server, or a payload that lost a row. A shorter strip is a
    // strip nobody notices is shorter.
    serve([row('refresh', 1)])
    render(<FreshnessStrip />)
    await screen.findByTestId('freshness-strip')
    for (const source of SOURCES) {
      expect(screen.getByTestId(`freshness-${source}`)).toBeInTheDocument()
    }
    expect(screen.getByTestId('freshness-backup')).toHaveTextContent('never')
  })

  it('reads the same age as fine weekly and stale daily', async () => {
    // The whole point of the cadence (v19a §2.2): 90 hours is three missed
    // nightly runs and half of one weekly one, and the old absolute
    // thresholds called both of them amber.
    serve([row('advise', 90, null, 168), row('prices', 90, null, 24)])
    render(<MemoryRouter><FreshnessStrip /></MemoryRouter>)
    await screen.findByTestId('freshness-strip')
    expect(screen.getByTestId('freshness-advise'))
      .toHaveClass('text-text-muted')
    expect(screen.getByTestId('freshness-prices')).toHaveClass('text-down')
  })

  it('sends a stale cell to Health, and leaves a fresh one as text', async () => {
    // A cell that has just said a job stopped and left the reader nowhere to
    // go is half a sentence; Health is where the plists and their last runs
    // are. Six links for six fresh sources would be a nav bar.
    serve([row('refresh', 1), row('prices', 90)])
    render(<MemoryRouter><FreshnessStrip /></MemoryRouter>)
    await screen.findByTestId('freshness-strip')
    const stale = screen.getByTestId('freshness-prices')
    expect(stale.tagName).toBe('A')
    expect(stale).toHaveAttribute('href', '/model?tab=health')
    expect(screen.getByTestId('freshness-refresh').tagName).toBe('SPAN')
  })

  // Until v18e this was the strip's one loud claim — that it stayed on screen
  // with five nevers whatever happened — and it was the worst of the nine
  // synthesised empties, because "never" is the strip saying nothing is
  // stale. It is on every page, so it says that everywhere at once.
  it('says the failure instead of five nevers when its own fetch fails',
     async () => {
       apiGet.mockRejectedValue(new FakeApiError(500, 'offline'))
       render(<FreshnessStrip />)
       const callout = await screen.findByText(/offline/)
       expect(callout.closest('[data-tone="error"]')).not.toBeNull()
       expect(screen.queryByTestId('freshness-strip')).toBeNull()
     })

  // The cold clone is the other half of the split: nothing has run, which is
  // not a failure to report on every page in the app.
  it('draws nothing at all on a cold clone', async () => {
    apiGet.mockRejectedValue(new FakeApiError(422, 'nothing dated yet'))
    const { container } = render(<FreshnessStrip />)
    // Settled, then still empty: without the await this passes on the frame
    // before the rejection lands.
    await waitFor(() => { expect(apiGet).toHaveBeenCalled() })
    expect(container).toBeEmptyDOMElement()
    expect(screen.queryByTestId('freshness-strip')).toBeNull()
  })

  it('carries the timestamp in the title', async () => {
    serve([row('refresh', 2, '2026-09-02T08:00:00+00:00')])
    render(<FreshnessStrip />)
    const cell = await screen.findByTestId('freshness-refresh')
    expect(cell).toHaveAttribute('title', '2026-09-02T08:00:00+00:00')
    expect(screen.getByTestId('freshness-odds'))
      .toHaveAttribute('title', 'never run')
  })

  it('contains no links while every source is fresh', async () => {
    // AppShell.test.tsx asserts the shell holds exactly six links, and this
    // renders inside it: on a healthy tree the strip must still add none. The
    // seventh link is a fault report, and it appears only when there is one.
    serve(SOURCES.map((source) => row(source, 1)))
    const { container } = render(<FreshnessStrip />)
    await screen.findByTestId('freshness-strip')
    expect(container.querySelectorAll('a')).toHaveLength(0)
  })
})

describe('the colouring', () => {
  it('is grey for never, and never red', () => {
    // "Never" and "very old" are different states: a cold clone has not
    // failed at anything, so painting it red would be an invented alarm.
    expect(tone(null, 24)).toBe('text-text-faint')
  })

  it('is grey inside one cadence, amber inside two, down beyond', () => {
    expect(tone(0.5, 24)).toBe('text-text-muted')
    expect(tone(23.9, 24)).toBe('text-text-muted')
    expect(tone(24, 24)).toBe('text-warn')
    expect(tone(47.9, 24)).toBe('text-warn')
    expect(tone(48, 24)).toBe('text-down')
  })

  it('asks the same ratio of a weekly job as of a nightly one', () => {
    expect(tone(90, 168)).toBe('text-text-muted')
    expect(tone(180, 168)).toBe('text-warn')
    expect(tone(340, 168)).toBe('text-down')
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

describe('the screen reader', () => {
  it('announces the strip without interrupting, and each age in words', async () => {
    // `status` and not `alert`: this is ambient state on every page, and an
    // assertive live region would interrupt on every navigation. The age is
    // in the label because the only other thing carrying it is the colour.
    serve([row('refresh', 2), row('backup', null)])
    render(<FreshnessStrip />)
    const strip = await screen.findByTestId('freshness-strip')
    expect(strip).toHaveAttribute('role', 'status')
    expect(strip).toHaveAttribute('aria-label', 'data freshness')
    expect(screen.getByTestId('freshness-refresh'))
      .toHaveAttribute('aria-label', 'data last updated 2h')
    expect(screen.getByTestId('freshness-backup'))
      .toHaveAttribute('aria-label', 'backup last updated never')
  })
})
