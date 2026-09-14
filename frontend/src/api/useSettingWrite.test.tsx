import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ToastOutlet, { resetToasts } from '../kit/Toast'
import { type SettingWriteOptions, useSettingWrite } from './useSettingWrite'

// v18f §2.1: the three lines the League hub, the ladder card and the Settings
// tab all wrote. What the hook owns is the POST, the sentence a refusal says
// when the caller has no place of its own to print one, and the order the
// cached URLs are cleared in — each caller's own wording and its own extra
// URLs are tested where that caller lives.

const { apiPost, cleared } = vi.hoisted(() => ({
  apiPost: vi.fn(), cleared: [] as string[],
}))

vi.mock('./client', () => ({
  ApiError: class extends Error { status = 0; detail: unknown = null },
  apiGet: vi.fn(),
  apiPost: (path: string, body: unknown) => apiPost(path, body),
  errorText: (e: unknown) => (e instanceof Error ? e.message : String(e)),
}))

// One list for both, because the assertion is the order they are called in:
// two spies could each be in order and still have been interleaved wrongly.
// The rest of the module is the real one — the shared setup resets the cache
// between tests through it.
vi.mock('./pageData', async (importOriginal) => ({
  ...await importOriginal<typeof import('./pageData')>(),
  invalidate: (path: string) => { cleared.push(path) },
  invalidatePrefix: (prefix: string) => { cleared.push(`${prefix}*`) },
}))

function Probe({ options }: { options?: SettingWriteOptions }) {
  const write = useSettingWrite(options)
  return (
    <button type="button" onClick={() => write('stance', 'chase',
                                               'set the stance')}>
      Chase
    </button>
  )
}

beforeEach(() => {
  resetToasts()
  cleared.length = 0
  apiPost.mockReset()
  apiPost.mockResolvedValue({})
})

describe('useSettingWrite', () => {
  it('posts the key and the value to the settings endpoint', async () => {
    render(<Probe />)
    await userEvent.click(screen.getByRole('button'))
    await waitFor(() => { expect(apiPost).toHaveBeenCalled() })
    expect(apiPost.mock.calls[0]).toEqual(
      ['/api/settings', { key: 'stance', value: 'chase' }])
  })

  it('clears the settings panel first and the caller’s URLs after it',
     async () => {
       render(<Probe options={{ also: ['/api/league/leagues'],
                                alsoPrefix: ['/api/league/'] }} />)
       await userEvent.click(screen.getByRole('button'))
       await waitFor(() => { expect(cleared.length).toBe(3) })
       expect(cleared).toEqual(['/api/settings', '/api/league/leagues',
                                '/api/league/*'])
     })

  it('asks the caller which URLs the key it just wrote disturbs', async () => {
    // The Settings tab's guard: a horizon moves nothing in a league overview,
    // and the hook is handed the whitelist rather than a fixed list.
    render(<Probe options={{ also: (key) => (key === 'horizon'
      ? ['/api/league/leagues'] : []) }} />)
    await userEvent.click(screen.getByRole('button'))
    await waitFor(() => { expect(cleared.length).toBe(1) })
    expect(cleared).toEqual(['/api/settings'])
  })

  it('toasts the caller’s own sentence when the write is refused', async () => {
    apiPost.mockRejectedValue(
      new Error('Stance is one of auto, chase, defend, neutral'))
    render(<><Probe /><ToastOutlet /></>)
    await userEvent.click(screen.getByRole('button'))
    expect(await screen.findByText(
      /Could not set the stance — Stance is one of auto/)).toBeInTheDocument()
  })

  it('clears nothing at all when the write is refused', async () => {
    // A cleared URL is a re-read, and re-reading after a refusal would print
    // the value that was already on screen as though the write had landed.
    apiPost.mockRejectedValue(new Error('nope'))
    render(<><Probe options={{ also: ['/api/league/leagues'] }} /><ToastOutlet /></>)
    await userEvent.click(screen.getByRole('button'))
    await screen.findByText(/nope/)
    expect(cleared).toEqual([])
  })

  it('hands a refusal to the caller that prints it beside the control',
     async () => {
       // Two of the three callers show the reason next to the row that failed
       // rather than in a toast, so they are given the exception and the key.
       apiPost.mockRejectedValue(new Error('cap must be an integer'))
       const onError = vi.fn()
       render(<><Probe options={{ onError }} /><ToastOutlet /></>)
       await userEvent.click(screen.getByRole('button'))
       await waitFor(() => { expect(onError).toHaveBeenCalled() })
       expect(onError.mock.calls[0][1]).toBe('stance')
       expect(screen.queryByText(/Could not set the stance/)).toBeNull()
     })

  it('says whether the write landed, so the caller can act on it', async () => {
    // The ladder card rebuilds after a saved cap and must not rebuild after a
    // refused one; the boolean is how it tells them apart.
    const landed: boolean[] = []
    function Report() {
      const write = useSettingWrite({ onError: () => {} })
      return (
        <button type="button"
                onClick={() => write('max_hits', 1)
                  .then((ok) => { landed.push(ok) })}>
          Save
        </button>
      )
    }
    render(<Report />)
    await userEvent.click(screen.getByRole('button'))
    await waitFor(() => { expect(landed).toEqual([true]) })
    apiPost.mockRejectedValue(new Error('nope'))
    await userEvent.click(screen.getByRole('button'))
    await waitFor(() => { expect(landed).toEqual([true, false]) })
  })
})
