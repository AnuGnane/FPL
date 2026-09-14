import { useCallback, useState } from 'react'
import { usePageData } from '../../api/pageData'
import {
  Bar, Callout, Card, EmptyState, JobButton, Skeleton, TABLE_CLASS,
  THEAD_CLASS, TR_CLASS, fmtNum, tdClass, thClass,
} from '../../kit'
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
  const page = usePageData<SensitivityReport>('/api/sensitivity')
  const data = page.data
  // A GET that failed is not a week nobody has swept. The endpoint is a 200
  // for every empty state it knows about — `sensitivity.py:110` answers an
  // un-advised tree with an empty report, not a refusal — so in practice
  // `absent` never fires here and a rejection means the server did not
  // answer. It is spelled anyway, in `Loaded`'s words, so this card cannot
  // drift from the ruling if the route ever learns to 404 (v18e ruling 7).
  // Split inline rather than through `Loaded` because the card draws its
  // header, its blurb and its Run button above whichever state this is.
  const absent = page.status === 404 || page.status === 422
  const failed = page.error !== null && !absent
  // The button owns the stream, so it is the button that says when the sweep
  // is running (plan A10). Wrapped so the effect inside it does not refire on
  // every render of this card.
  const [running, setRunning] = useState(false)
  const onRunning = useCallback((r: boolean) => setRunning(r), [])

  const rows = (data?.frequencies ?? [])
    .filter((r) => KINDS.includes(r.kind))
    .sort((a, b) => b.frequency - a.frequency)
    .slice(0, 12)

  return (
    <Card
      title="How robust is this plan?"
      className="mb-4"
      action={<JobButton kind="sensitivity" onDone={page.reload}
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
      {/* A server that did not answer is not an empty state, and it must not
          send the reader to press a button that is not the problem — so it
          gets the callout every other broken read gets, carrying the server's
          own sentence rather than this card's guess at one (ruling 7). */}
      {!running && !data?.available && (failed
        ? <Callout tone="error">{page.error}</Callout>
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
            <Callout className="mb-3">{data.notice}</Callout>
          )}
          <div className="overflow-x-auto">
          <table className={TABLE_CLASS}>
            <thead className={THEAD_CLASS}>
              <tr>
                <th scope="col" className={thClass()}>Move</th>
                <th scope="col" className={thClass()}>Player</th>
                <th scope="col" className={thClass(true)}>Solves</th>
                <th scope="col" className={thClass()}>Share</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.kind}-${r.code}-${r.gw}`} className={TR_CLASS}>
                  <td className={`${tdClass()} text-text-secondary`}>{r.label}</td>
                  <td className={`${tdClass()} text-text`}>{r.name || '—'}</td>
                  <td className={`${tdClass(true)} text-text-secondary`}>
                    {r.count}/{data.completed}
                  </td>
                  <td className={tdClass()}>
                    <Bar testId="share" fraction={r.frequency}
                         text={pct(r.frequency)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          {data.failures > 0 && (
            <p className="mt-3 text-down">
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
