import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { PageData } from '../api/pageData'
import Loaded from './Loaded'

interface Body { rows: string[] }

/** A settled `PageData` by hand — no hook, no cache, no timing. */
function page(over: Partial<PageData<Body>> = {}): PageData<Body> {
  return { data: null, error: null, status: null, reload: vi.fn(), ...over }
}

const body = (data: Body) => <p>{data.rows.join(', ')}</p>
const EMPTY = <p>nothing here yet</p>

describe('Loaded', () => {
  it('states a server failure in an error callout', () => {
    render(
      <Loaded page={page({ error: 'advise failed', status: 500 })}
              empty={EMPTY}>
        {body}
      </Loaded>,
    )
    const box = screen.getByText(/advise failed/).closest('[data-tone]')!
    expect(box).toHaveAttribute('data-tone', 'error')
    expect(screen.queryByText('nothing here yet')).toBeNull()
  })

  it('shows the empty slot for a 404, not the failure (ruling 7)', () => {
    render(
      <Loaded page={page({ error: 'no advice yet', status: 404 })}
              empty={EMPTY}>
        {body}
      </Loaded>,
    )
    expect(screen.getByText('nothing here yet')).toBeInTheDocument()
    expect(screen.queryByText(/no advice yet/)).toBeNull()
  })

  it('shows the empty slot for a 422 too: a GafferError is the cold clone', () => {
    // `web/app.py` answers every GafferError with 422 — "run gaffer advise
    // first" — so the same slot; the sentence reaches a function slot.
    render(
      <Loaded page={page({ error: 'run gaffer advise first', status: 422 })}
              empty={(message) => <p>empty: {message}</p>}>
        {body}
      </Loaded>,
    )
    expect(screen.getByText('empty: run gaffer advise first')).toBeInTheDocument()
    expect(screen.queryByText('Retry')).toBeNull()
  })

  it('shows the loading slot while there is no body', () => {
    render(
      <Loaded page={page()} empty={EMPTY} loading={<p>waiting</p>}>
        {body}
      </Loaded>,
    )
    expect(screen.getByText('waiting')).toBeInTheDocument()
  })

  it('shows the empty slot for a body that says nothing', () => {
    render(
      <Loaded page={page({ data: { rows: [] } })} empty={EMPTY}
              isEmpty={(d) => d.rows.length === 0}>
        {body}
      </Loaded>,
    )
    expect(screen.getByText('nothing here yet')).toBeInTheDocument()
  })

  it('renders the body when there is one', () => {
    render(
      <Loaded page={page({ data: { rows: ['Salah', 'Haaland'] } })}
              empty={EMPTY} isEmpty={(d) => d.rows.length === 0}>
        {body}
      </Loaded>,
    )
    expect(screen.getByText('Salah, Haaland')).toBeInTheDocument()
  })

  it('reloads the page once when Retry is clicked', async () => {
    const reload = vi.fn()
    render(
      <Loaded page={page({ error: 'advise failed', status: 500, reload })}>
        {body}
      </Loaded>,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(reload).toHaveBeenCalledTimes(1)
  })
})
