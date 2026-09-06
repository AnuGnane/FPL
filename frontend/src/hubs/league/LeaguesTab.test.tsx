import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import type { LeaguesOverview } from '../../types'
import LeaguesTab from './LeaguesTab'

const OVERVIEW: LeaguesOverview = {
  focus_league_id: 5, focus_name: 'Focus FC League', stance: 'auto',
  focus_stance: 'chase', focus_lam: 0.31, focus_warning: null, gw: 5,
  private: [
    { league_id: 5, name: 'Focus FC League', rank: 15, last_rank: 80,
      entries: 138, started: true, gap: 12, gap_kind: 'behind',
      would: 'chase', is_focus: true },
    { league_id: 9, name: 'NLT', rank: 1, last_rank: 3, entries: 7,
      started: true, gap: 9, gap_kind: 'ahead', would: 'defend',
      is_focus: false },
    { league_id: 99, name: 'Next Season', rank: 3, last_rank: 0,
      entries: null, started: false, gap: null, gap_kind: null,
      would: null, is_focus: false },
  ],
  public: [
    { league_id: 314, name: 'Overall', rank: 430473, last_rank: 2562053,
      entries: 10409391 },
  ],
}

function mount(overview = OVERVIEW, props = {}) {
  const onFocus = vi.fn()
  const onStance = vi.fn()
  render(
    <MemoryRouter>
      <LeaguesTab overview={overview} busy={false} onFocus={onFocus}
                  onStance={onStance} {...props} />
    </MemoryRouter>,
  )
  return { onFocus, onStance }
}

describe('LeaguesTab', () => {
  it('lists every private league with rank, size, move and gap', () => {
    mount()
    const focus = screen.getByTestId('league-5')
    expect(within(focus).getByText('15')).toBeInTheDocument()
    expect(within(focus).getByText('138')).toBeInTheDocument()
    expect(within(focus).getByText('▲ 65')).toBeInTheDocument()
    expect(within(focus).getByText('−12 to 1st')).toBeInTheDocument()
    const nlt = screen.getByTestId('league-9')
    expect(within(nlt).getByText('+9 on 2nd')).toBeInTheDocument()
    expect(within(nlt).getByText('would defend')).toBeInTheDocument()
  })

  it('marks the focus row and shows its live stance and tilt', () => {
    mount()
    const focus = screen.getByTestId('league-5')
    expect(focus).toHaveAttribute('data-focus', 'true')
    expect(within(focus).getByText('focus')).toBeInTheDocument()
    expect(within(focus).getByText('chase · λ +0.31')).toBeInTheDocument()
    expect(within(focus).queryByRole('button', { name: /make focus/ }))
      .toBeNull()
  })

  it('links a private league to its race', () => {
    mount()
    expect(screen.getByRole('link', { name: 'NLT' }))
      .toHaveAttribute('href', '/league?tab=race&league=9')
  })

  it('offers make focus on the other started leagues and reports the id', async () => {
    const { onFocus } = mount()
    const nlt = screen.getByTestId('league-9')
    await userEvent.click(within(nlt).getByRole('button', { name: 'make focus' }))
    expect(onFocus).toHaveBeenCalledWith(9)
  })

  it('shows a league that has not started as such, with no action', () => {
    mount()
    const row = screen.getByTestId('league-99')
    expect(within(row).getByText('not started')).toBeInTheDocument()
    expect(within(row).queryByRole('button')).toBeNull()
    expect(within(row).queryByRole('link')).toBeNull()
  })

  it('names the stance control with the live word on auto', () => {
    mount()
    const group = screen.getByRole('group', { name: 'Stance' })
    expect(within(group).getByRole('button', { name: 'Auto · chase' }))
      .toHaveAttribute('aria-pressed', 'true')
  })

  it('reports a stance click', async () => {
    const { onStance } = mount()
    const group = screen.getByRole('group', { name: 'Stance' })
    await userEvent.click(within(group).getByRole('button', { name: 'Defend' }))
    expect(onStance).toHaveBeenCalledWith('defend')
  })

  it('flags a manual stance on the focus row', () => {
    mount({ ...OVERVIEW, stance: 'defend', focus_stance: 'defend',
            focus_lam: -0.5 })
    const focus = screen.getByTestId('league-5')
    expect(within(focus).getByText('manual')).toBeInTheDocument()
    expect(within(focus).getByText('defend · λ −0.50')).toBeInTheDocument()
  })

  it('lists public leagues as a rank line', () => {
    mount()
    const row = screen.getByTestId('public-314')
    expect(within(row).getByText('430,473')).toBeInTheDocument()
    expect(within(row).getByText('10,409,391')).toBeInTheDocument()
    expect(within(row).queryByRole('button')).toBeNull()
  })

  it('shows the focus warning as a warn callout', () => {
    mount({ ...OVERVIEW, focus_name: null,
            focus_warning: 'focus league 42 is not one of your private leagues' })
    const callout = screen.getByTestId('focus-warning')
    expect(callout).toHaveAttribute('data-tone', 'warn')
    expect(callout).toHaveTextContent('42')
  })

  it('has an empty state with no private leagues, and still the public table', () => {
    mount({ ...OVERVIEW, private: [], focus_name: null })
    expect(screen.getByText('You are in no private leagues')).toBeInTheDocument()
    expect(screen.getByTestId('public-314')).toBeInTheDocument()
  })
})
