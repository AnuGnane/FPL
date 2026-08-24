import { useEffect, useRef, useState } from 'react'
import { apiGet } from '../api/client'
import type { PlayerExplain } from '../types'

// One modal, reachable from every player name on every page (spec §3.6).
export default function ExplainModal(
  { code, onClose }: { code: number; onClose: () => void },
) {
  const [data, setData] = useState<PlayerExplain | null>(null)
  const [error, setError] = useState<string | null>(null)
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    // A second click while the first request is in flight must not repaint
    // the modal with the player the user already moved off.
    let live = true
    setData(null)
    setError(null)
    apiGet<PlayerExplain>(`/api/players/${code}/explain`)
      .then((body) => { if (live) setData(body) })
      .catch((e: Error) => { if (live) setError(e.message) })
    return () => { live = false }
  }, [code])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // Enough of a focus trap for a modal this small: the close button is the
  // first thing keyboard and screen-reader users land on.
  useEffect(() => { closeRef.current?.focus() }, [])

  return (
    <div
      className="modal-backdrop"
      data-testid="modal-backdrop"
      onClick={onClose}
    >
      <div
        className="modal card"
        role="dialog"
        aria-modal="true"
        aria-label="Expected points explained"
        onClick={(event) => event.stopPropagation()}
      >
        <button ref={closeRef} onClick={onClose}>Close</button>
        {error && <p className="bad">{error}</p>}
        {!data && !error && <p className="muted">Loading…</p>}
        {data && (
          <>
            <h2>
              {data.name} · {data.position} · {data.team_name} ·{' '}
              {data.ep_next} xPts
            </h2>
            {/* A double gameweek arrives as two fixture blocks; the sum is
                the number that decides a captaincy, so state it. */}
            {Object.entries(
              data.fixtures.reduce<Record<number, number[]>>((acc, fixture) => {
                acc[fixture.gw] = [...(acc[fixture.gw] ?? []), fixture.ep]
                return acc
              }, {}),
            )
              .filter(([, eps]) => eps.length > 1)
              .map(([gw, eps]) => (
                <p key={gw} className="muted">
                  GW{gw} total: {Math.round(
                    eps.reduce((a, b) => a + b, 0) * 100) / 100} xPts across{' '}
                  {eps.length} fixtures
                </p>
              ))}
            {data.fixtures.map((fixture, index) => (
              // A double can be two fixtures against the same opponent, so
              // the index is part of the key.
              <section key={`${fixture.gw}-${fixture.opponent}-${index}`}>
                <h3>
                  GW{fixture.gw} {fixture.home ? 'vs' : 'at'}{' '}
                  {fixture.opponent} — {fixture.ep} xPts
                </h3>
                <table>
                  <tbody>
                    {fixture.components.map((component) => (
                      <tr key={component.label}>
                        <td>{component.label}</td>
                        <td>{component.points}</td>
                        <td style={{ width: '50%' }}>
                          <div
                            className="bar"
                            style={{
                              width: `${Math.min(
                                Math.abs(component.points) * 12, 100)}%`,
                              background: component.points < 0
                                ? 'var(--bad)' : 'var(--pitch-500)',
                            }}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="muted">
                  Minutes: P(play) {fixture.minutes.p_play}, P(60+){' '}
                  {fixture.minutes.p60} · calibration{' '}
                  {fixture.calibration_delta >= 0 ? '+' : ''}
                  {fixture.calibration_delta}
                </p>
                <p className="muted">
                  {fixture.odds.weight > 0
                    ? `Odds blend ${Math.round(fixture.odds.weight * 100)}%: `
                      + `clean sheet ${fixture.odds.p_cs_model} (model) → `
                      + `${fixture.odds.p_cs_blended} (blended), goals `
                      + `against ${fixture.odds.e_gc_model} → `
                      + `${fixture.odds.e_gc_blended}`
                    : 'No market odds for this fixture — model output only. '
                      + 'Add an odds key for market-implied numbers.'}
                </p>
              </section>
            ))}
            <h3>Next fixtures</h3>
            <ul>
              {data.next_fixtures.map((fixture) => (
                <li key={`${fixture.gw}-${fixture.opponent}`}>
                  GW{fixture.gw} {fixture.home ? 'vs' : 'at'} {fixture.opponent}
                </li>
              ))}
            </ul>
            <p className="muted">
              Set pieces — penalties: {data.set_pieces.penalties ?? '–'},
              free kicks: {data.set_pieces.free_kicks ?? '–'},
              corners: {data.set_pieces.corners ?? '–'}
            </p>
          </>
        )}
      </div>
    </div>
  )
}
