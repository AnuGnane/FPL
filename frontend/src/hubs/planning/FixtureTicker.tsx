import { useState } from 'react'
import { usePageData } from '../../api/pageData'
import {
  Callout, Card, Chip, TABLE_CLASS, THEAD_CLASS, TR_CLASS, difficultyTone,
  fmtNum, tdClass, thClass,
} from '../../kit'
import type { TickerData } from '../../types'

export default function FixtureTicker(
  { weeks, oddsKeyPresent }: { weeks: number; oddsKeyPresent?: boolean },
) {
  // Keyed by the window, so the eight-week table and the six-week one on the
  // What-If tab are two entries and neither can answer for the other; the
  // hook's ask counter is the `live` guard this effect used to carry.
  const page = usePageData<TickerData>(`/api/fixtures/ticker?weeks=${weeks}`)

  const [sortGw, setSortGw] = useState<number | null>(null)
  const [ascending, setAscending] = useState(true)
  const data = page.data

  // The endpoint is a 200 for a season with no banked fixtures at all, so
  // there is no 404 to tell from a failure here and the two branches below
  // are the ones this card has always had. What changed is the sentence: the
  // hook reads every rejection through `errorText`, so a refusal that carries
  // a structured body prints its `error` rather than `[object Object]`.
  if (page.error !== null) {
    return (
      <Card title="Fixture ticker" className="mb-4">
        <Callout tone="error">{page.error}</Callout>
      </Card>
    )
  }
  if (!data) {
    return (
      <Card title="Fixture ticker" className="mb-4">
        <p className="text-text-muted">Loading…</p>
      </Card>
    )
  }

  const teams = [...data.teams]
  if (sortGw !== null) {
    teams.sort((a, b) => {
      const av = a.cells.find((c) => c.gw === sortGw)?.difficulty ?? 1
      const bv = b.cells.find((c) => c.gw === sortGw)?.difficulty ?? 1
      return ascending ? av - bv : bv - av
    })
  }

  const toggle = (gw: number) => {
    if (sortGw === gw) setAscending(!ascending)
    else { setSortGw(gw); setAscending(true) }
  }

  return (
    <Card
      title="Fixture ticker"
      className="mb-4"
      action={(
        <span className="text-text-muted">
          {data.source === 'odds'
            ? 'Difficulty is odds-implied, from banked bookmaker prices.'
            : 'Difficulty is Elo-implied, from finished results.'}
        </span>
      )}
    >
      {data.source === 'elo' && oddsKeyPresent !== true && (
        <Callout className="mb-3">
          No banked odds for these gameweeks — add an odds key for
          market-implied numbers.
        </Callout>
      )}
      <div className="overflow-x-auto">
        <table className={TABLE_CLASS}>
          <thead className={THEAD_CLASS}>
            <tr>
              <th className={thClass()}>Team</th>
              {data.gws.map((gw) => (
                <th key={gw} className={thClass()}>
                  <button type="button" onClick={() => toggle(gw)}
                          className="label block w-full hover:text-text">
                    GW{gw}
                    {sortGw === gw ? (ascending ? ' ▴' : ' ▾') : ''}
                  </button>
                </th>
              ))}
              <th className={thClass(true)}>Mean</th>
            </tr>
          </thead>
          <tbody>
            {teams.map((team) => (
              <tr key={team.code} className={TR_CLASS}>
                <th scope="row"
                    className={`${tdClass()} font-normal text-text`}>
                  {team.name}
                </th>
                {data.gws.map((gw) => {
                  const cell = team.cells.find((c) => c.gw === gw)
                  if (!cell) {
                    return (
                      <td key={gw}
                          className={`${tdClass()} text-text-faint`}>
                        <span className="flex justify-center">–</span>
                      </td>
                    )
                  }
                  // The tint moves onto the chip (rule 1's three words); the
                  // cell keeps the title and carries the tone for the tests.
                  const tone = difficultyTone(cell.difficulty)
                  return (
                    <td
                      key={gw}
                      data-tone={tone}
                      className={tdClass()}
                      title={`${team.short_name} ${cell.home ? 'vs' : 'at'} `
                        + `${cell.opponent} (GW${gw}) — ${cell.difficulty}`}
                    >
                      <span className="flex justify-center">
                        <Chip tone={tone}>
                          {cell.opponent} ({cell.home ? 'H' : 'A'})
                        </Chip>
                      </span>
                    </td>
                  )
                })}
                <td className={`${tdClass(true)} text-text-secondary`}>
                  {fmtNum(team.mean_difficulty, 2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
