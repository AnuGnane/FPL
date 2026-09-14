import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { resetPageData } from '../api/pageData'
import Live from '../hubs/Live'
import DraftsTab from '../hubs/planning/DraftsTab'
import FixtureMatrix from '../hubs/players/FixtureMatrix'
import JournalTab from '../hubs/model/JournalTab'
import QualityTab from '../hubs/model/QualityTab'
import ReviewTab from '../hubs/model/ReviewTab'
import SeasonTab from '../hubs/model/SeasonTab'
import type { WhatIfRequest } from '../types'
import FreshnessStrip from './FreshnessStrip'

/**
 * A 500 is not an empty page (v18e §1 part 3, design ruling 7).
 *
 * Nine components used to synthesise an empty body in a `.catch` — an empty
 * journal, an ungraded season, a fixture matrix with no team model, a
 * freshness strip reading "never" on all five sources. Every one of them drew
 * a healthy page over a server that could not answer, and most of them put a
 * command under it that would not have helped. The rule they now share is
 * `Loaded`'s: a 404 or a 422 is the artifact not being written yet and keeps
 * the sentence each component already had, and every other status is the
 * error callout with the server's own words in it.
 *
 * One table over all nine, and two cases per row, because the claim is a pair
 * — the split is worthless if either half is wrong, and nine files each
 * asserting one half is how the halves drift apart. Each row names the URL it
 * fails and the sentence its own empty state prints; the two rows whose
 * honest drawing of an absent artifact is *nothing* say so with `empty: null`
 * and name what must not be on the page instead.
 */

const { FakeApiError, apiGet } = vi.hoisted(() => {
  class FakeApiError extends Error {
    status: number
    detail: unknown

    constructor(status: number, detail: unknown) {
      super(typeof detail === 'string' ? detail : `request failed (${status})`)
      this.status = status
      this.detail = detail
    }
  }
  return { FakeApiError, apiGet: vi.fn() }
})

vi.mock('../api/client', () => ({
  ApiError: FakeApiError,
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
  apiDelete: vi.fn(),
  errorText: (e: unknown) => (e instanceof Error ? e.message : String(e)),
}))

const CURRENT: WhatIfRequest = {
  lock: [], ban: [], force_in: [], force_out: [], max_hits: 0,
  max_transfers: null, chip: 'none', horizon: null,
}

/**
 * The smallest body each URL a row does *not* fail can answer with.
 *
 * Small on purpose: the claim is about the failing read, and a rich fixture
 * here would let a second card's contents stand in for the sentence under
 * test. Anything not named answers `null`, which every caller reads as "still
 * loading" and none reads as an error.
 */
const BODIES: Record<string, unknown> = {
  '/api/quality': {
    benchmark: null, current: null, decomposition: null, flag_latency: null,
    news_shadow: null, presser_grades: null,
  },
  '/api/model/calibration': {
    available: false, run_at: null, git_sha: null, season: '2026-27',
    gameweeks: [], cumulative: {}, omitted: {}, per_gw_omitted: {},
    excluded: [], missing: [], note: 'Nothing graded yet.',
  },
  '/api/pens': {
    gws: [], notes: [], season: '2026-27',
    season_totals: { players: 0, penalties: 0 },
  },
  '/api/review': { gws: [], summary: null },
  '/api/misses': { gw: null, rows: [] },
}

interface Row {
  name: string
  /** The URL this row makes fail. */
  url: string
  render: () => void
  /**
   * The sentence the component prints for an artifact that is not written
   * yet, copied from the component. `null` where its honest drawing of one is
   * nothing at all, in which case `absent` names what must not be on the page.
   */
  empty: RegExp | null
  absent?: RegExp
}

const TABLE: Row[] = [
  {
    name: 'JournalTab',
    url: '/api/journal',
    render: () => { render(<JournalTab />) },
    empty: /Nothing to compare yet/,
  },
  {
    name: 'ReviewTab',
    url: '/api/review',
    render: () => { render(<ReviewTab />) },
    empty: /Nothing reviewed yet/,
  },
  {
    name: 'SeasonTab',
    url: '/api/review',
    render: () => { render(<SeasonTab />) },
    // Its own sentence, not `ReviewTab`'s: the two tabs read one artifact and
    // are waiting on different things in it — a review at all, and a lane
    // graded.
    empty: /Nothing graded yet/,
  },
  {
    name: 'FixtureMatrix',
    url: '/api/fixtures/matrix?from=5&n=6',
    render: () => { render(<FixtureMatrix from={5} />) },
    empty: /No fixture difficulty yet/,
  },
  {
    name: 'FreshnessStrip',
    url: '/api/meta/freshness',
    render: () => { render(<FreshnessStrip />) },
    // A strip is on every page in the app, so a cold clone must not put a red
    // line across all of them — but it must not read "never" five times over
    // a question nobody could ask either.
    empty: null,
    absent: /as of/,
  },
  {
    name: "QualityTab's review section",
    url: '/api/review',
    render: () => { render(<MemoryRouter><QualityTab /></MemoryRouter>) },
    empty: /No graded gameweek yet/,
  },
  {
    name: "QualityTab's misses section",
    url: '/api/misses',
    render: () => { render(<MemoryRouter><QualityTab /></MemoryRouter>) },
    // No scored gameweek is an absent card, which is why the failure was
    // invisible: the card was not there either way.
    empty: null,
    absent: /Biggest misses/,
  },
  {
    name: 'DraftsTab',
    url: '/api/drafts',
    render: () => {
      render(<MemoryRouter><DraftsTab current={CURRENT} /></MemoryRouter>)
    },
    empty: /No drafts yet/,
  },
  {
    name: 'Live',
    url: '/api/live',
    render: () => { render(<MemoryRouter><Live /></MemoryRouter>) },
    empty: /No live data yet/,
  },
]

/** Every URL answered but `url`, which rejects with `error`. */
function failing(url: string, error: Error) {
  apiGet.mockImplementation((path: string) => (path === url
    ? Promise.reject(error)
    : Promise.resolve(BODIES[path] ?? null)))
}

beforeEach(() => {
  // The shared setup clears it before every test; called here too because a
  // body held from the row above would be served with no request at all, and
  // this file renders the same component on two different answers.
  resetPageData()
  apiGet.mockReset()
})

describe('a failed read is an error, and an absent one is the empty state',
         () => {
  for (const row of TABLE) {
    it(`${row.name} says what broke on a 500`, async () => {
      failing(row.url, new FakeApiError(500, 'boom'))
      row.render()
      const said = await screen.findByText(/boom/)
      expect(said.closest('[data-tone="error"]')).not.toBeNull()
      if (row.empty !== null) {
        expect(screen.queryByText(row.empty)).toBeNull()
      }
    })

    it(`${row.name} keeps its empty state on a 404`, async () => {
      failing(row.url, new FakeApiError(404, 'not yet'))
      row.render()
      if (row.empty !== null) {
        expect(await screen.findByText(row.empty)).toBeInTheDocument()
      } else {
        // Settled, not merely unrendered: without waiting for the rejection
        // to land this passes on the first frame, when nothing is on the page
        // for any reason at all.
        await vi.waitFor(() => { expect(apiGet).toHaveBeenCalledWith(row.url) })
        expect(screen.queryByText(row.absent!)).toBeNull()
      }
      expect(document.querySelector('[data-tone="error"]')).toBeNull()
    })
  }
})
