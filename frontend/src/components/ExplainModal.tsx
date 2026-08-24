import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'
import type { PlayerExplain } from '../types'

// One modal, reachable from every player name on every page (spec §3.6).
export default function ExplainModal(
  { code, onClose }: { code: number; onClose: () => void },
) {
  const [data, setData] = useState<PlayerExplain | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    apiGet<PlayerExplain>(`/api/players/${code}/explain`)
      .then((body) => { if (live) setData(body) })
      .catch((e: Error) => { if (live) setError(e.message) })
    return () => { live = false }
  }, [code])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal card"
        role="dialog"
        aria-modal="true"
        aria-label="Expected points explained"
        onClick={(event) => event.stopPropagation()}
      >
        <button onClick={onClose}>Close</button>
        {error && <p className="bad">{error}</p>}
        {!data && !error && <p className="muted">Loading…</p>}
        {data && (
          <>
            <h2>
              {data.name} · {data.position} · {data.team_name} ·{' '}
              {data.ep_next} xPts
            </h2>
            {data.fixtures.map((fixture) => (
              <section key={`${fixture.gw}-${fixture.opponent}`}>
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
