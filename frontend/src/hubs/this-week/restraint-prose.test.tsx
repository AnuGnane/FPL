// v17b §5 — the cross-language half of the rail: MovesCard and LadderCard
// render the fixture's served strings character for character. The fixture
// is built by `tests/test_v17b_prose.py`, the same file the Python rail
// checks against the server.
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import MovesCard from './MovesCard'
import LadderCard from './LadderCard'

const { apiGet, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPost: vi.fn(),
}))

vi.mock('../../api/client', () => ({
  apiGet: (p: string) => apiGet(p),
  apiPost: (p: string, b: unknown) => apiPost(p, b),
  errorText: (e: unknown) => String(e),
  ApiError: class extends Error { status = 422; detail: unknown = null },
}))

// No `resolveJsonModule` in tsconfig (v17b §5 note): read the fixture as
// text, the way `types.generated.test.ts` reads `schemas.json`.
const HERE = dirname(fileURLToPath(import.meta.url))
const fixture = JSON.parse(readFileSync(
  join(HERE, 'restraint-prose.fixture.json'), 'utf8',
)) as { cases: Array<{
  key: string
  hits: number
  restraint: { line: string; agrees: boolean; hit_cost: number | null }
  objective: { line: string }
  payload: {
    rungs: Array<{ label: string }>
    steps: Array<{ line: string }>
  }
}> }

afterEach(() => {
  cleanup()
  apiGet.mockReset()
  apiPost.mockReset()
})

describe.each(fixture.cases.map((c) => [c.key, c] as const))(
  'renders the served strings for the %s rung', (_key, c) => {
  it('MovesCard prints the served restraint and objective lines and price', () => {
    render(<MovesCard buys={[]} sells={[]} hits={c.hits}
                      restraint={c.restraint as never} objective={c.objective as never} />)
    expect(screen.getByTestId('moves-restraint-line').textContent).toBe(c.restraint.line)
    if (!c.restraint.agrees) {
      expect(screen.getByTestId('moves-objective-line').textContent).toBe(c.objective.line)
    }
    if (c.hits > 0) {
      expect(screen.getByText(
        `−${c.hits * (c.restraint.hit_cost ?? 0)} pts`,
      )).toBeInTheDocument()
    }
  })

  it('LadderCard prints the served rung labels and step lines', async () => {
    apiGet.mockImplementation(async (path: string) => {
      if (path === '/api/ladder') return c.payload
      throw new Error(`unexpected GET ${path}`)
    })
    render(<LadderCard />)
    await screen.findByTestId('ladder-steps')

    const table = screen.getByRole('table')
    const rows = within(table).getAllByRole('row')
    for (const r of c.payload.rungs) {
      const match = rows.find((row) => {
        const span = row.querySelectorAll('td')[0]?.querySelector('span')
        return span?.childNodes[0]?.textContent?.trim() === r.label
      })
      expect(match, `no row labelled ${JSON.stringify(r.label)}`).toBeTruthy()
    }

    const list = screen.getByTestId('ladder-steps')
    for (const s of c.payload.steps) {
      expect(within(list).getByText(s.line, { selector: 'li' })).toBeInTheDocument()
    }
  })
})
