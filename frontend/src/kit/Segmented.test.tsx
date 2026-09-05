import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import Segmented, { segmentClass } from './Segmented'

const OPTIONS = [
  { value: 'pitch', label: 'Pitch' },
  { value: 'table', label: 'Table' },
] as const

describe('Segmented', () => {
  it('is a labelled group of pressed/unpressed buttons', () => {
    render(<Segmented label="Squad view" options={[...OPTIONS]}
                      value="pitch" onChange={() => {}} />)
    const group = screen.getByRole('group', { name: 'Squad view' })
    expect(within(group).getByRole('button', { name: 'Pitch' }))
      .toHaveAttribute('aria-pressed', 'true')
    expect(within(group).getByRole('button', { name: 'Table' }))
      .toHaveAttribute('aria-pressed', 'false')
  })

  it('paints the active segment accent on the raised surface', () => {
    render(<Segmented label="Squad view" options={[...OPTIONS]}
                      value="table" onChange={() => {}} />)
    expect(screen.getByRole('button', { name: 'Table' }))
      .toHaveClass('text-accent-text')
    expect(screen.getByRole('button', { name: 'Table' }))
      .toHaveClass('bg-raised')
    expect(screen.getByRole('button', { name: 'Pitch' }))
      .toHaveClass('text-text-muted')
  })

  it('reports the clicked value', async () => {
    const onChange = vi.fn()
    render(<Segmented label="Squad view" options={[...OPTIONS]}
                      value="pitch" onChange={onChange} />)
    await userEvent.click(screen.getByRole('button', { name: 'Table' }))
    expect(onChange).toHaveBeenCalledWith('table')
  })

  it('exposes the segment classes for controls with their own ARIA', () => {
    expect(segmentClass(true)).toContain('text-accent-text')
    expect(segmentClass(false)).toContain('text-text-muted')
  })
})
