import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { TOKEN_KEY } from '../api/client'
import Callout from './Callout'
import TokenPrompt, { isTokenRefusal } from './TokenPrompt'

/**
 * v19b §2.5. A phone opened on a bare LAN URL — no `?token=` — was told its
 * write needed a header and given nowhere to put it.
 *
 * The real `api/client` throughout, because the claim under test is that the
 * field writes the token to the key `readToken` reads. A spy on `writeToken`
 * would pass with the two halves naming different keys, which is the one bug
 * worth having a test for here.
 */

/** `web/app.py:202`, verbatim — the sentence the middleware refuses with. */
const REFUSED = 'this gaffer is served to the network; writes need the '
  + 'X-Gaffer-Token header printed when `gaffer ui --lan` started'

beforeEach(() => {
  localStorage.clear()
})

describe('the write-token prompt', () => {
  it('appears under the refusal that asks for a token', () => {
    render(<Callout tone="error">{REFUSED}</Callout>)
    expect(screen.getByLabelText('write token')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Use token' }))
      .toBeInTheDocument()
  })

  it('stays away from every other refused write', () => {
    render(<Callout tone="error">an override must pin p_play, e_min or both</Callout>)
    expect(screen.queryByLabelText('write token')).not.toBeInTheDocument()
  })

  it('stays away from a note and a warning carrying the same words', () => {
    render(<Callout tone="warn">{REFUSED}</Callout>)
    expect(screen.queryByLabelText('write token')).not.toBeInTheDocument()
  })

  it('stores the token under the key every request reads, and retries', async () => {
    const retry = vi.fn()
    render(<Callout tone="error" onRetry={retry}>{REFUSED}</Callout>)
    await userEvent.type(screen.getByLabelText('write token'), 'hunter2')
    await userEvent.click(screen.getByRole('button', { name: 'Use token' }))
    expect(localStorage.getItem(TOKEN_KEY)).toBe('hunter2')
    expect(retry).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('token-saved')).toBeInTheDocument()
  })

  it('takes the token on Enter, so a phone keyboard is enough', async () => {
    const retry = vi.fn()
    render(<TokenPrompt sentence={REFUSED} onRetry={retry} />)
    await userEvent.type(screen.getByLabelText('write token'), 'hunter2{Enter}')
    expect(localStorage.getItem(TOKEN_KEY)).toBe('hunter2')
    expect(retry).toHaveBeenCalledTimes(1)
  })

  it('trims what was pasted, because a copied token carries a newline',
    async () => {
      render(<TokenPrompt sentence={REFUSED} />)
      await userEvent.type(screen.getByLabelText('write token'), '  hunter2  ')
      await userEvent.click(screen.getByRole('button', { name: 'Use token' }))
      expect(localStorage.getItem(TOKEN_KEY)).toBe('hunter2')
    })

  it('reads the refusal by the header it names, and nothing else', () => {
    expect(isTokenRefusal(REFUSED)).toBe(true)
    expect(isTokenRefusal('the solver refused this squad')).toBe(false)
    expect(isTokenRefusal(null)).toBe(false)
    expect(isTokenRefusal({ error: REFUSED })).toBe(false)
  })
})
