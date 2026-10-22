import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { routerFuture } from './router'

describe('routerFuture', () => {
  it('opts into both v7 flags react-router-dom 6.26 warns about', () => {
    expect(routerFuture.future).toEqual({
      v7_startTransition: true, v7_relativeSplatPath: true,
    })
  })

  // Holiday F-187: the notice is what the console guard used to allow; a
  // router mounted with the constant prints nothing at all.
  it('mounts a router that prints no future-flag notice', () => {
    const warn = vi.spyOn(console, 'warn')
    render(<MemoryRouter {...routerFuture}><p>page</p></MemoryRouter>)
    expect(warn).not.toHaveBeenCalled()
    warn.mockRestore()
  })
})
