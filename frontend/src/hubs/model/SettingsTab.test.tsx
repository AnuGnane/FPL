import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SettingsTab from './SettingsTab'
import type { SettingsPanel } from '../../types'

const { apiGet, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPost: vi.fn(),
}))

vi.mock('../../api/client', () => ({
  apiGet: (p: string) => apiGet(p),
  apiPost: (p: string, b: unknown) => apiPost(p, b),
  // The real helper's ApiError branch (`client.ts:24-33`): a 422 from this
  // endpoint carries `{constraint, error, players}` and the sentence the user
  // needs is `detail.error`. Mocked faithfully rather than as `String(e)`,
  // because a stand-in that threw the server's sentence away would let the
  // component pass this file while showing "Error: bad" in the browser.
  errorText: (e: unknown) => {
    const detail = (e as { detail?: { error?: unknown } }).detail
    return detail && detail.error !== undefined
      ? String(detail.error)
      : String(e)
  },
  ApiError: class extends Error { status = 422; detail: unknown = null },
}))

const PANEL: SettingsPanel = {
  rows: [
    { key: 'horizon', label: 'Horizon (gameweeks)', kind: 'int', value: 3,
      lo: 1, hi: 8, section: 'optimizer', help: 'How far it plans.',
      source: 'base' },
    { key: 'decision_priors', label: 'Use calibrated θ/λ priors', kind: 'bool',
      value: true, lo: null, hi: null, section: 'scenarios',
      help: 'Off falls back to flat thresholds.', source: 'local' },
  ],
  unavailable: ['price_timing'],
  overlay_error: null,
  apply_note: 'A job already running keeps the value it started with.',
}

beforeEach(() => {
  apiGet.mockReset()
  apiPost.mockReset()
  apiGet.mockResolvedValue(PANEL)
  apiPost.mockResolvedValue(PANEL)
})

describe('SettingsTab', () => {
  it('renders a control per served row, labelled', async () => {
    render(<SettingsTab />)
    expect(await screen.findByLabelText('Horizon (gameweeks)'))
      .toHaveValue(3)
    expect(screen.getByLabelText('Use calibrated θ/λ priors')).toBeChecked()
  })

  it('names a setting this build does not have', async () => {
    render(<SettingsTab />)
    expect(await screen.findByTestId('settings-unavailable'))
      .toHaveTextContent('price_timing')
  })

  it('saves one key at a time and says so', async () => {
    render(<SettingsTab />)
    const field = await screen.findByLabelText('Horizon (gameweeks)')
    await userEvent.clear(field)
    await userEvent.type(field, '5')
    await userEvent.click(screen.getByRole('button', { name: 'Save Horizon (gameweeks)' }))
    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/settings',
        { key: 'horizon', value: 5 })
    })
  })

  it('saves a boolean on the toggle itself, with no second click', async () => {
    render(<SettingsTab />)
    await userEvent.click(await screen.findByLabelText('Use calibrated θ/λ priors'))
    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/settings',
        { key: 'decision_priors', value: false })
    })
  })

  it('offers a reset only where the overlay is what set the value', async () => {
    render(<SettingsTab />)
    await screen.findByLabelText('Horizon (gameweeks)')
    expect(screen.queryByRole('button', { name: /Reset Horizon/ })).toBeNull()
    expect(screen.getByRole('button', { name: /Reset Use calibrated/ }))
      .toBeInTheDocument()
  })

  it('resets by sending a null value', async () => {
    render(<SettingsTab />)
    await userEvent.click(await screen.findByRole('button',
      { name: /Reset Use calibrated/ }))
    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/settings',
        { key: 'decision_priors', value: null })
    })
  })

  it('shows the refusal beside the field that caused it', async () => {
    const boom = Object.assign(new Error('bad'),
      { detail: { error: 'Horizon (gameweeks) is between 1 and 8' } })
    apiPost.mockRejectedValueOnce(boom)
    render(<SettingsTab />)
    const field = await screen.findByLabelText('Horizon (gameweeks)')
    await userEvent.clear(field)
    await userEvent.type(field, '9')
    await userEvent.click(screen.getByRole('button', { name: 'Save Horizon (gameweeks)' }))
    expect(await screen.findByTestId('settings-error-horizon'))
      .toHaveTextContent('between 1 and 8')
  })

  it('tells a screen reader which field was refused and where to read why',
    async () => {
      const boom = Object.assign(new Error('bad'),
        { detail: { error: 'Horizon (gameweeks) is between 1 and 8' } })
      apiPost.mockRejectedValueOnce(boom)
      render(<SettingsTab />)
      const field = await screen.findByLabelText('Horizon (gameweeks)')
      expect(field).not.toHaveAttribute('aria-invalid')
      await userEvent.click(screen.getByRole('button', { name: 'Save Horizon (gameweeks)' }))
      await waitFor(() => {
        expect(field).toHaveAttribute('aria-invalid', 'true')
      })
      // The sentence is not just near the control, it is *named* by it: the
      // refusal is the server's own text and a reader who cannot see the red
      // paragraph beside the box has no other way to reach it.
      expect(field).toHaveAttribute('aria-describedby', 'settings-error-horizon')
      expect(document.getElementById('settings-error-horizon'))
        .toHaveTextContent('between 1 and 8')
      // And it is announced. A refusal that only changes colour is a save the
      // user believes worked.
      expect(screen.getByTestId('settings-error-horizon'))
        .toHaveAttribute('aria-live', 'polite')
    })

  it('announces an overlay error rather than only drawing it', async () => {
    apiGet.mockResolvedValue({ ...PANEL, overlay_error: 'config.local.toml is not readable TOML' })
    render(<SettingsTab />)
    const banner = await screen.findByTestId('settings-overlay-error')
    expect(banner).toHaveAttribute('aria-live', 'polite')
    expect(banner).toHaveAttribute('role', 'status')
  })

  it('renders the apply note verbatim', async () => {
    render(<SettingsTab />)
    expect(await screen.findByTestId('settings-apply-note'))
      .toHaveTextContent('A job already running keeps the value it started with.')
  })

  it('renders an overlay error where it cannot be missed', async () => {
    apiGet.mockResolvedValue({ ...PANEL, overlay_error: 'config.local.toml is not readable TOML' })
    render(<SettingsTab />)
    expect(await screen.findByTestId('settings-overlay-error'))
      .toHaveTextContent('not readable')
  })

  it('has an honest empty state on a cold clone', async () => {
    apiGet.mockResolvedValue({
      rows: [], unavailable: ['horizon'], apply_note: 'x',
      overlay_error: 'no config.toml — copy config.example.toml to config.toml',
    })
    render(<SettingsTab />)
    expect(await screen.findByTestId('empty-state')).toHaveTextContent(
      'config.example.toml')
  })

  it('does not blank the form while a save is in flight', async () => {
    render(<SettingsTab />)
    await userEvent.click(await screen.findByLabelText('Use calibrated θ/λ priors'))
    expect(screen.getByLabelText('Horizon (gameweeks)')).toBeInTheDocument()
  })
})
