import { useCallback, useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import { Card, EmptyState, JobButton, Skeleton, fmtNum } from '../../kit'
import { JOB_KIND_LABEL, type SensitivityReport } from '../../types'

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
 *  The noise qualifier is the v8g honesty line, and it **appends**. A
 *  negative margin inside the noise is two separate facts — the runner-up is
 *  ahead, and the ordering is not solid — and the first cut substituted the
 *  caveat for the "most frequent plan is not the highest-scoring one" clause,
 *  so the case where the reader most needed both got only one.
 *
 *  `decision_sigma` is *estimation* σ: how far gaffer's own forecast of the
 *  players separating these two plans would move if it were refit, summed in
 *  quadrature. Deliberately not the outcome σ behind the EP bands — both
 *  plans are solved off the same board, so football's own variance cannot
 *  reorder them and folding it in would turn every margin into a coin flip.
 *  The sentence says which of the two it means. */
function marginLine(margin: number | null,
                    sigma: number | null = null): string {
  if (margin === null) return 'Every re-solve reached the same decision.'
  const inside = sigma !== null && sigma > 0 && Math.abs(margin) < sigma
  const caveat = inside
    ? ` It is smaller than the ${fmtNum(sigma, 1)}-point spread on how wrong `
      + 'the forecast for the players that separate the two plans might be, '
      + 'so the ranking is not solid.'
    : ''
  if (margin < 0) {
    return `The best differing plan is ${fmtNum(-margin, 1)} expected points `
      + 'ahead — the most frequent plan is not the highest-scoring one.'
      + caveat
  }
  return `The best differing plan is ${fmtNum(margin, 1)} expected points `
    + `behind.${caveat}`
}

export default function SensitivityCard() {
  const [data, setData] = useState<SensitivityReport | null>(null)
  // A GET that failed is not a week nobody has swept. The endpoint is a 200
  // for every empty state it knows about, so a rejection here means the
  // server did not answer, and "no report yet" would send the user to press
  // a button that is not the problem.
  const [failed, setFailed] = useState(false)
  // The button owns the stream, so it is the button that says when the sweep
  // is running (plan A10). Wrapped so the effect inside it does not refire on
  // every render of this card.
  const [running, setRunning] = useState(false)
  const onRunning = useCallback((r: boolean) => setRunning(r), [])
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
      action={<JobButton kind="sensitivity" onDone={load}
                         onRunning={onRunning} />}
    >
      <p className="mb-3 text-text-muted">
        The same board re-solved {data?.k ? `${data.k} times` : 'twenty times'}
        {' '}with every expected-points cell knocked by its own plausible
        error. A move that survives most of them is an edge; one that does not
        is the optimizer reading the noise.
      </p>
      {/* The skeleton replaces this card's *body*, never the card: a Card
          inside a Card is two borders for one idea. `Skeleton bare` is the
          same bars with no frame of its own. */}
      {running && (
        <Skeleton
          bare
          lines={4}
          label="Re-solving the board twenty times with knocked expected
                 points…"
        />
      )}
      {/* The failed branch stays prose: a server that did not answer is not
          an empty state, and it must not send the reader to press a button
          that is not the problem. */}
      {!running && !data?.available && (failed
        ? (
          <p className="text-text-muted">
            The sensitivity report could not be read — the server did not
            answer.
          </p>
          )
        : (
          <EmptyState
            title="No sensitivity report yet"
            detail={data?.notice ?? 'The sweep re-solves the same board with '
              + 'every expected-points cell knocked by its own plausible '
              + 'error, and nothing has swept this board yet.'}
            action={JOB_KIND_LABEL.sensitivity}
          />
          ))}
      {!running && data?.available && (
        <>
          {data.verdict && <p className="mb-3 text-text">{data.verdict}</p>}
          {data.notice && (
            <p className="mb-3 rounded-card border-l-2 border-info bg-base
                          px-3 py-2 text-text-muted">
              {data.notice}
            </p>
          )}
          <div className="overflow-x-auto">
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
          </div>
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
