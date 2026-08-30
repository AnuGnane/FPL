import { useEffect, useRef, useState } from 'react'
import { apiGet } from '../api/client'
import type { PlayerExplain } from '../types'
import PosBadge from './PosBadge'
import { fmtNum, fmtPct } from './format'

/** A term's weight, drawn against a fixed 12-points-wide scale so bars are
 *  comparable between two players rather than only within one. */
function TermBar({ points }: { points: number }) {
  return (
    <span
      aria-hidden
      className="block h-1.5 rounded-full"
      style={{
        width: `${Math.max(2, Math.min(Math.abs(points) * 12, 100))}%`,
        background: points < 0 ? 'var(--color-rust)' : 'var(--color-sage)',
      }}
    />
  )
}

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
      className="fixed inset-0 z-50 flex items-start justify-center
                 overflow-y-auto bg-black/70 p-4 sm:p-8"
      data-testid="modal-backdrop"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl rounded-card border border-border bg-card"
        role="dialog"
        aria-modal="true"
        aria-label="Expected points explained"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-3 border-b
                           border-divider px-4 py-3">
          <div>
            {data
              ? (
                <>
                  <h2 className="flex items-center gap-2 text-base text-text">
                    <PosBadge pos={data.position} />
                    {data.name}
                  </h2>
                  <p className="label mt-1">
                    {data.team_name} · {fmtNum(data.ep_next)} xPts
                  </p>
                </>
                )
              : <h2 className="label">Expected points</h2>}
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            className="rounded-card border border-border px-2 py-1
                       text-text-muted hover:text-text"
          >
            Close
          </button>
        </header>
        <div className="flex flex-col gap-4 p-4">
          {error && <p className="text-rust">{error}</p>}
          {!data && !error && <p className="text-text-muted">Loading…</p>}
          {data && (
            <>
              {/* A double gameweek arrives as two fixture blocks; the sum is
                  the number that decides a captaincy, so state it. */}
              {Object.entries(
                data.fixtures.reduce<Record<number, number[]>>(
                  (acc, fixture) => {
                    acc[fixture.gw] = [...(acc[fixture.gw] ?? []), fixture.ep]
                    return acc
                  }, {}),
              )
                .filter(([, eps]) => eps.length > 1)
                .map(([gw, eps]) => (
                  <p key={gw} className="num rounded-card border-l-2 border-info
                                         bg-base px-3 py-2 text-text-secondary">
                    GW{gw} total:{' '}
                    {Math.round(eps.reduce((a, b) => a + b, 0) * 100) / 100}
                    {' '}xPts across {eps.length} fixtures
                  </p>
                ))}
              {data.fixtures.map((fixture, index) => (
                // A double can be two fixtures against the same opponent, so
                // the index is part of the key.
                <section key={`${fixture.gw}-${fixture.opponent}-${index}`}>
                  <h3 className="label mb-2">
                    GW{fixture.gw} {fixture.home ? 'vs' : 'at'}{' '}
                    {fixture.opponent} — {fmtNum(fixture.ep)} xPts
                  </h3>
                  <table className="w-full">
                    <tbody>
                      {fixture.components.map((component) => (
                        <tr key={component.label}
                            className="border-t border-divider">
                          <td className="py-1 text-text-secondary">
                            {component.label}
                          </td>
                          <td className="num w-16 py-1 text-right text-text">
                            {fmtNum(component.points)}
                          </td>
                          <td className="w-1/2 py-1 pl-3">
                            <TermBar points={component.points} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="mt-2 text-text-muted">
                    Minutes: P(play) {fmtPct(fixture.minutes.p_play)},
                    P(60+) {fmtPct(fixture.minutes.p60)} · calibration{' '}
                    <span className="num">
                      {fixture.calibration_delta >= 0 ? '+' : ''}
                      {fixture.calibration_delta}
                    </span>
                  </p>
                  <p className="mt-1 text-text-muted">
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
              <section>
                <h3 className="label mb-2">Next fixtures</h3>
                <ul className="flex flex-wrap gap-2">
                  {data.next_fixtures.map((fixture) => (
                    <li key={`${fixture.gw}-${fixture.opponent}`}
                        className="rounded-card border border-border bg-base
                                   px-2 py-1 text-text-secondary">
                      <span className="num">GW{fixture.gw}</span>{' '}
                      {fixture.home ? 'vs' : 'at'} {fixture.opponent}
                    </li>
                  ))}
                </ul>
              </section>
              <p className="text-text-muted">
                <span className="label">Set pieces</span>{' '}
                penalties <span className="num">
                  {data.set_pieces.penalties ?? '–'}
                </span>, free kicks <span className="num">
                  {data.set_pieces.free_kicks ?? '–'}
                </span>, corners <span className="num">
                  {data.set_pieces.corners ?? '–'}
                </span>
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
