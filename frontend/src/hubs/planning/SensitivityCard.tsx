import { useCallback, useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import { Card, JobButton, fmtNum } from '../../kit'
import type { SensitivityReport } from '../../types'

/** The move kinds this card lists. No frequency cut at all: the ones that are
 *  neither certain nor negligible are the whole point, but a 100% row is the
 *  reassurance and a 5% row is the warning, so both stay.
 *
 *  No 'chip' row. The sweep's plans carry no chip — `optimize.milp.Plan` has
 *  no such field — so a chip frequency is a row that can never appear, and an
 *  empty column reads as "the sweep never played one". */
const KINDS = ['buy', 'sell', 'captain']

function pct(frequency: number): string {
  return `${Math.round(frequency * 100)}%`
}

/** The margin is signed and the sign is the whole sentence: it is
 *  modal-minus-runner-up, so a negative one means the plan the sweep reached
 *  most often is priced *below* one it reached less often, which is the
 *  opposite recommendation and must not be printed as "behind".
 *
 *  The noise qualifier is the v8g honesty line. `decision_sigma` is the
 *  sweep's own σ on the players that actually separate the two plans, in
 *  quadrature — so a margin inside it is a margin the forecast error could
 *  have produced on its own, and saying "0.6 ahead" without saying that is
 *  the false precision this cycle exists to remove. Only ever said when it is
 *  true: a margin larger than the noise gets the bare sentence. */
function marginLine(margin: number | null,
                    sigma: number | null = null): string {
  if (margin === null) return 'Every re-solve reached the same decision.'
  const inside = sigma !== null && sigma > 0 && Math.abs(margin) < sigma
  const caveat = inside
    ? ` — smaller than the ${fmtNum(sigma, 1)}-point noise on the players `
      + 'that separate the two plans, so the ranking is not solid'
    : ''
  if (margin < 0) {
    return `The best differing plan is ${fmtNum(-margin, 1)} expected points `
      + `ahead${caveat}${inside ? '' : ' — the most frequent plan is not the '
        + 'highest-scoring one'}.`
  }
  return `The best differing plan is ${fmtNum(margin, 1)} expected points `
    + `behind${caveat}.`
}

export default function SensitivityCard() {
  const [data, setData] = useState<SensitivityReport | null>(null)
  // A GET that failed is not a week nobody has swept. The endpoint is a 200
  // for every empty state it knows about, so a rejection here means the
  // server did not answer, and "no report yet" would send the user to press
  // a button that is not the problem.
  const [failed, setFailed] = useState(false)
  const load = useCallback(() => {
    apiGet<SensitivityReport>('/api/sensitivity')
      .then((report) => { setFailed(false); setData(report) })
      .catch(() => { setFailed(true); setData(null) })
  }, [])
  useEffect(() => { load() }, [load])

  const rows = (data?.frequencies ?? [])
    .filter((r) => KINDS.includes(r.kind))
    .sort((a, b) => b.frequency - a.frequency)
    .slice(0, 12)

  return (
    <Card
      title="How robust is this plan?"
      className="mb-4"
      action={<JobButton kind="sensitivity" onDone={load} />}
    >
      <p className="mb-3 text-text-muted">
        The same board re-solved {data?.k ? `${data.k} times` : 'twenty times'}
        {' '}with every expected-points cell knocked by its own plausible
        error. A move that survives most of them is an edge; one that does not
        is the optimizer reading the noise.
      </p>
      {!data?.available && (
        <p className="text-text-muted">
          {failed
            ? 'The sensitivity report could not be read — the server did not '
              + 'answer.'
            : data?.notice ?? 'No sensitivity report yet.'}
        </p>
      )}
      {data?.available && (
        <>
          {data.verdict && <p className="mb-3 text-text">{data.verdict}</p>}
          {data.notice && (
            <p className="mb-3 rounded-card border-l-2 border-info bg-base
                          px-3 py-2 text-text-muted">
              {data.notice}
            </p>
          )}
          <table className="w-full">
            <thead>
              <tr>
                <th className="label pb-1 text-left">Move</th>
                <th className="label pb-1 text-left">Player</th>
                <th className="label pb-1 text-right">Solves</th>
                <th className="label pb-1 text-right">Share</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.kind}-${r.code}-${r.gw}`}>
                  <td className="py-1.5 text-text-secondary">{r.label}</td>
                  <td className="py-1.5 text-text">{r.name || '—'}</td>
                  <td className="num py-1.5 text-right text-text-secondary">
                    {r.count}/{data.completed}
                  </td>
                  <td className="num py-1.5 text-right">{pct(r.frequency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.failures > 0 && (
            <p className="mt-3 text-rust">
              {`${data.failures} of the ${data.k} re-solves failed; every `}
              share above is out of the {data.completed} that finished.
            </p>
          )}
          <p className="mt-3 text-text-muted">
            {marginLine(data.margin, data.decision_sigma ?? null)}
            {data.wall_s != null && ` Swept in ${fmtNum(data.wall_s, 0)}s, `}
            {data.seed != null && `seed ${data.seed}, `}
            {data.generated_at != null
              && `run ${data.generated_at.slice(0, 16).replace('T', ' ')}.`}
          </p>
        </>
      )}
    </Card>
  )
}
