import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { invalidate, resetPageData, seedPageData, usePageData } from './pageData'

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

  it('caches a null body — 204 is an answer, not an absence', async () => {
    apiGet.mockResolvedValue(null)
    const first = render(<Reader path="/api/x" />)
    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(1))
    first.unmount()
    render(<Reader path="/api/x" />)
    expect(apiGet).toHaveBeenCalledTimes(1)
  })
})
