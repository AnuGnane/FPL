import { useState } from 'react'
import { usePageData } from '../../api/pageData'
import {
  Card, Chip, EmptyState, Loaded, Loading, Segmented, TABLE_CLASS,
  THEAD_CLASS, TR_CLASS, difficultyTone, difficultyWord, tdClass, thClass,
} from '../../kit'
import type { FixtureMatrixData, MatrixCell } from '../../types'

type View = 'attack' | 'defence'

export default function FixtureMatrix({ from }: { from: number }) {
  const page = usePageData<FixtureMatrixData>(
    `/api/fixtures/matrix?from=${from}&n=6`)

  // The catch this replaces synthesised `{ gws: [], teams: [], source:
  // 'none' }` — so a server that broke drew "no team model has been fitted",
  // which sent the reader to train a model that was already there. The
  // sentence now belongs to the two states that mean it: a 404, and a served
  // matrix with no teams in it (v18e §2.2, ruling 7).
  return (
    <Loaded
      page={page}
      loading={<Loading />}
      empty={(
        <EmptyState
          title="No fixture difficulty yet"
          detail="The matrix prices fixtures with the trained Dixon-Coles team
                  model, and no team model has been fitted on this machine."
          action="gaffer train"
        />
      )}
      isEmpty={(d) => d.source === 'none' || d.teams.length === 0}
    >
      {(data) => <Matrix data={data} />}
    </Loaded>
  )
}

/** The grid itself, and the lens the reader put on it. */
function Matrix({ data }: { data: FixtureMatrixData }) {
  const [view, setView] = useState<View>('attack')

  const score = (cell: MatrixCell) => view === 'attack' ? cell.attack : cell.defence

  return (
    <Card
      title="Fixture difficulty"
      action={(
        <span className="text-text-muted">
          Home in caps, away in lower case.
        </span>
      )}
    >
      <div className="mb-3">
        <Segmented
          label="Difficulty view"
          value={view}
          onChange={setView}
          options={[{ value: 'attack', label: 'Attacking' },
                    { value: 'defence', label: 'Clean sheet' }]}
        />
      </div>
      <div className="overflow-x-auto">
        <table className={TABLE_CLASS}>
          <thead className={THEAD_CLASS}>
            <tr>
              <th scope="col" className={thClass()}>Team</th>
              {data.gws.map((gw) => (
                <th scope="col" key={gw} className={thClass()}>GW{gw}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.teams.map((team) => (
              <tr key={team.code} className={TR_CLASS}>
                <th scope="row" className={`${thClass()} text-text`}>
                  {team.short_name}
                </th>
                {data.gws.map((gw) => {
                  const cell = team.cells.find((c) => c.gw === gw)
                  if (!cell) {
                    return (
                      <td key={gw}
                          className={`${tdClass()} text-text-faint`}>—</td>
                    )
                  }
                  // A grid of chips: the same tint language every other
                  // fixture on the page speaks (rule 1 on the meaning scale),
                  // rather than a per-cell ramp only this table used.
                  return (
                    <td
                      key={gw}
                      data-testid={`matrix-cell-${team.code}-${gw}`}
                      data-score={String(score(cell))}
                      className={tdClass()}
                    >
                      <Chip tone={difficultyTone(score(cell))}
                            className="w-full justify-center">
                        {/* v18f §2.2. The tint is the whole of what this cell
                            says about difficulty, and a tint is nothing to a
                            screen reader. `sr-only` is absolutely positioned,
                            so the word costs no space in the grid. */}
                        <span className="sr-only">
                          {difficultyWord(score(cell))} fixture,{' '}
                        </span>
                        {cell.home ? cell.opponent
                                   : cell.opponent.toLowerCase()}
                      </Chip>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
