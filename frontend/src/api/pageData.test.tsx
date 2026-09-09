import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  invalidate, invalidatePrefix, resetPageData, seedPageData, usePageData,
} from './pageData'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('./client', () => ({
  apiGet: (path: string) => apiGet(path),
  errorText: (e: unknown) => (e instanceof Error ? e.message : String(e)),
}))

/** A reader of one URL, printing what it has. */
function Reader({ path, name = 'a' }: { path: string | null; name?: string }) {
  const { data, error, reload } = usePageData<{ n: number }>(path)
  return (
    <div>
      <span data-testid={`${name}-data`}>{data ? String(data.n) : '—'}</span>
      <span data-testid={`${name}-error`}>{error ?? '—'}</span>
      <button onClick={reload}>reload {name}</button>
    </div>
  )
}

beforeEach(() => {
  resetPageData()
  apiGet.mockReset()
})

describe('usePageData', () => {
  it('fetches once for two readers of the same URL', async () => {
    apiGet.mockResolvedValue({ n: 1 })
    render(<><Reader path="/api/x" name="a" /><Reader path="/api/x" name="b" /></>)
    await waitFor(() =>
      expect(screen.getByTestId('a-data')).toHaveTextContent('1'))
    expect(screen.getByTestId('b-data')).toHaveTextContent('1')
    expect(apiGet).toHaveBeenCalledTimes(1)
  })

  it('serves a resolved body to a later reader without a second request',
     async () => {
       apiGet.mockResolvedValue({ n: 2 })
       const first = render(<Reader path="/api/x" />)
       await waitFor(() =>
         expect(screen.getByTestId('a-data')).toHaveTextContent('2'))
       first.unmount()
       render(<Reader path="/api/x" />)
       expect(screen.getByTestId('a-data')).toHaveTextContent('2')
       expect(apiGet).toHaveBeenCalledTimes(1)
     })

  it('asks for nothing at all when the path is null', () => {
    render(<Reader path={null} />)
    expect(apiGet).not.toHaveBeenCalled()
    expect(screen.getByTestId('a-data')).toHaveTextContent('—')
  })

  it('gives each reader its own error and keeps the other reader intact',
     async () => {
       apiGet.mockImplementation((path: string) => (path === '/api/bad'
         ? Promise.reject(new Error('nope'))
         : Promise.resolve({ n: 3 })))
       render(<><Reader path="/api/x" name="a" />
               <Reader path="/api/bad" name="b" /></>)
       await waitFor(() =>
         expect(screen.getByTestId('b-error')).toHaveTextContent('nope'))
       expect(screen.getByTestId('a-data')).toHaveTextContent('3')
       expect(screen.getByTestId('a-error')).toHaveTextContent('—')
     })

  it('never caches an error, so the next mount tries again', async () => {
    apiGet.mockRejectedValueOnce(new Error('cold'))
    apiGet.mockResolvedValue({ n: 4 })
    const first = render(<Reader path="/api/x" />)
    await waitFor(() =>
      expect(screen.getByTestId('a-error')).toHaveTextContent('cold'))
    first.unmount()
    render(<Reader path="/api/x" />)
    await waitFor(() =>
      expect(screen.getByTestId('a-data')).toHaveTextContent('4'))
    expect(apiGet).toHaveBeenCalledTimes(2)
  })

  it('refetches for every mounted reader on invalidate, once between them',
     async () => {
       apiGet.mockResolvedValueOnce({ n: 5 }).mockResolvedValueOnce({ n: 6 })
       render(<><Reader path="/api/x" name="a" />
               <Reader path="/api/x" name="b" /></>)
       await waitFor(() =>
         expect(screen.getByTestId('a-data')).toHaveTextContent('5'))
       invalidate('/api/x')
       await waitFor(() =>
         expect(screen.getByTestId('a-data')).toHaveTextContent('6'))
       expect(screen.getByTestId('b-data')).toHaveTextContent('6')
       expect(apiGet).toHaveBeenCalledTimes(2)
     })

  it('invalidates a URL nobody is mounted on, so the next mount refetches',
     async () => {
       apiGet.mockResolvedValueOnce({ n: 7 }).mockResolvedValueOnce({ n: 8 })
       const first = render(<Reader path="/api/x" />)
       await waitFor(() =>
         expect(screen.getByTestId('a-data')).toHaveTextContent('7'))
       first.unmount()
       invalidate('/api/x')
       render(<Reader path="/api/x" />)
       await waitFor(() =>
         expect(screen.getByTestId('a-data')).toHaveTextContent('8'))
     })

  it('reloads only the URL the reader asked for', async () => {
    apiGet.mockResolvedValue({ n: 9 })
    render(<><Reader path="/api/x" name="a" /><Reader path="/api/y" name="b" /></>)
    await waitFor(() =>
      expect(screen.getByTestId('b-data')).toHaveTextContent('9'))
    apiGet.mockClear()
    screen.getByText('reload a').click()
    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(1))
    expect(apiGet).toHaveBeenCalledWith('/api/x')
  })

  it('refetches every held URL under a prefix and nothing beside it',
     async () => {
       apiGet.mockResolvedValue({ n: 11 })
       render(<><Reader path="/api/news/5" name="a" />
               <Reader path="/api/news/6" name="b" />
               <Reader path="/api/newsletter" name="c" />
               <Reader path="/api/players" name="d" /></>)
       await waitFor(() => { expect(apiGet).toHaveBeenCalledTimes(4) })
       apiGet.mockClear()
       invalidatePrefix('/api/news/')
       await waitFor(() => { expect(apiGet).toHaveBeenCalledTimes(2) })
       expect(apiGet.mock.calls.map((call) => call[0] as string).sort())
         .toEqual(['/api/news/5', '/api/news/6'])
     })

  // The prefix is a prefix, not a path segment: `/api/news/` matches the
  // gameweek URLs and stops short of `/api/newsletter`, which is the whole of
  // the discipline the caller owes it.
  it('leaves a URL that merely starts with the same letters alone',
     async () => {
       apiGet.mockResolvedValue({ n: 12 })
       render(<Reader path="/api/newsletter" />)
       await waitFor(() => { expect(apiGet).toHaveBeenCalledTimes(1) })
       invalidatePrefix('/api/news/')
       await new Promise((r) => { setTimeout(r, 0) })
       expect(apiGet).toHaveBeenCalledTimes(1)
     })

  it('invalidates a URL under the prefix that nobody is mounted on',
     async () => {
       apiGet.mockResolvedValueOnce({ n: 13 }).mockResolvedValueOnce({ n: 14 })
       const first = render(<Reader path="/api/news/5" />)
       await waitFor(() =>
         expect(screen.getByTestId('a-data')).toHaveTextContent('13'))
       first.unmount()
       invalidatePrefix('/api/news/')
       render(<Reader path="/api/news/5" />)
       await waitFor(() =>
         expect(screen.getByTestId('a-data')).toHaveTextContent('14'))
     })

  it('serves a seeded body without any request', () => {
    seedPageData({ '/api/x': { n: 10 } })
    render(<Reader path="/api/x" />)
    expect(screen.getByTestId('a-data')).toHaveTextContent('10')
    expect(apiGet).not.toHaveBeenCalled()
  })

  it('drops an answer invalidated while it was still in flight', async () => {
    let settle: (body: unknown) => void = () => {}
    apiGet.mockReturnValueOnce(new Promise((r) => { settle = r }))
    apiGet.mockResolvedValue({ n: 12 })
    render(<Reader path="/api/x" />)
    invalidate('/api/x')   // the card's job finished during the cold start
    settle({ n: 11 })      // and the pre-job artifact arrives afterwards
    await waitFor(() =>
      expect(screen.getByTestId('a-data')).toHaveTextContent('12'))
    // Neither on screen nor in the cache for the next mount to be handed.
    const later = render(<Reader path="/api/x" name="b" />)
    expect(later.getByTestId('b-data')).toHaveTextContent('12')
  })

  it('leaves the second request holding the cache when the first one fails '
     + 'after it', async () => {
       let failFirst: (e: unknown) => void = () => {}
       let settleSecond: (body: unknown) => void = () => {}
       apiGet.mockReturnValueOnce(new Promise((_, reject) => { failFirst = reject }))
       apiGet.mockReturnValueOnce(new Promise((r) => { settleSecond = r }))
       apiGet.mockResolvedValue({ n: 99 })   // a third request would take this
       render(<Reader path="/api/x" />)
       invalidate('/api/x')                  // the second request starts
       failFirst(new Error('late'))          // the first one dies after it
       await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(2))
       settleSecond({ n: 15 })
       await waitFor(() =>
         expect(screen.getByTestId('a-data')).toHaveTextContent('15'))
       // The dead request must not have cleared the live one's slot on its way
       // out: a request nothing holds is a body nothing caches, and the next
       // mount would open a third while the second was still in flight.
       render(<Reader path="/api/x" name="b" />)
       expect(screen.getByTestId('b-data')).toHaveTextContent('15')
       expect(apiGet).toHaveBeenCalledTimes(2)
     })

  it('paints nothing from the old URL when the path changes', async () => {
    apiGet.mockImplementation((path: string) =>
      Promise.resolve({ n: path === '/api/x' ? 13 : 14 }))
    const view = render(<Reader path="/api/x" />)
    await waitFor(() =>
      expect(screen.getByTestId('a-data')).toHaveTextContent('13'))
    view.rerender(<Reader path="/api/y" />)
    expect(screen.getByTestId('a-data')).toHaveTextContent('—')
    await waitFor(() =>
      expect(screen.getByTestId('a-data')).toHaveTextContent('14'))
  })

  it('drops the old URL\'s error when the path changes', async () => {
    apiGet.mockImplementation((path: string) => (path === '/api/x'
      ? Promise.reject(new Error('stale'))
      : Promise.resolve({ n: 16 })))
    const view = render(<Reader path="/api/x" />)
    await waitFor(() =>
      expect(screen.getByTestId('a-error')).toHaveTextContent('stale'))
    view.rerender(<Reader path="/api/y" />)
    // The new URL is loading, not failing. Carrying the error over would put
    // one code list's failure over the next one's empty frame.
    expect(screen.getByTestId('a-error')).toHaveTextContent('—')
    await waitFor(() =>
      expect(screen.getByTestId('a-data')).toHaveTextContent('16'))
  })

  it('forgets what it held when the path goes back to null', async () => {
    apiGet.mockResolvedValue({ n: 17 })
    const view = render(<Reader path="/api/x" />)
    await waitFor(() =>
      expect(screen.getByTestId('a-data')).toHaveTextContent('17'))
    // A card can return to not-yet: the gameweek or the code list it was
    // waiting for goes away again, and it must go back to waiting.
    view.rerender(<Reader path={null} />)
    expect(screen.getByTestId('a-data')).toHaveTextContent('—')
  })

  it('caches a null body — 204 is an answer, not an absence', async () => {
    apiGet.mockResolvedValue(null)
    const first = render(<Reader path="/api/x" />)
    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(1))
    first.unmount()
    render(<Reader path="/api/x" />)
    expect(apiGet).toHaveBeenCalledTimes(1)
  })
})
