import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  Button, Callout, Card, Chip, EmptyState, Segmented, TABLE_CLASS,
  THEAD_CLASS, TR_CLASS, TR_SELECTED_CLASS, fmtNum, tdClass, thClass,
} from '../../kit'
import type { LeaguesOverview, PrivateLeagueRow } from '../../types'

/** The four words `[league] stance` may be (v15 §3.2). */
export const STANCES = ['auto', 'chase', 'defend', 'neutral'] as const
export type Stance = typeof STANCES[number]

export interface LeaguesTabProps {
  overview: LeaguesOverview
  /** A settings write is in flight: the controls stay put until it lands. */
  busy: boolean
  onFocus: (leagueId: number) => void
  onStance: (stance: Stance) => void
}

const n = (value: number) => value.toLocaleString('en-GB')

/** Rank movement since last week. FPL sends 0 for "no last rank". */
function Move({ rank, last_rank }: { rank: number | null
                                     last_rank: number | null }): ReactNode {
  if (!rank || !last_rank) return <span className="text-text-muted">—</span>
  const delta = last_rank - rank
  if (delta === 0) return <span className="text-text-muted">=</span>
  // Up the table is a direction relative to where you were (rule 1).
  return (
    <Chip tone={delta > 0 ? 'up' : 'down'}>
      {`${delta > 0 ? '▲' : '▼'} ${n(Math.abs(delta))}`}
    </Chip>
  )
}

function gapText(row: PrivateLeagueRow): string {
  if (!row.started) return 'not started'
  if (row.gap === null || row.gap_kind === null) return '—'
  return row.gap_kind === 'ahead'
    ? `+${n(row.gap)} on 2nd` : `−${n(row.gap)} to 1st`
}

/** λ with its sign, the minus a real minus like every other number here. */
function lamText(lam: number): string {
  const body = fmtNum(Math.abs(lam), 2)
  return lam < 0 ? `−${body}` : `+${body}`
}

export default function LeaguesTab(
  { overview, busy, onFocus, onStance }: LeaguesTabProps,
) {
  const autoLabel = `Auto · ${overview.focus_stance}`
  const stanceOptions = STANCES.map((s) => ({
    value: s,
    label: s === 'auto' ? autoLabel : s[0].toUpperCase() + s.slice(1),
  }))

  return (
    <>
      {overview.focus_warning && (
        <Callout tone="warn" className="mb-4" data-testid="focus-warning">
          {overview.focus_warning}
        </Callout>
      )}
      <Card title="Private leagues" className="mb-4">
        {overview.private.length === 0 ? (
          <EmptyState
            title="You are in no private leagues"
            detail="Join or create a mini-league on the FPL site; it appears here on the next load."
            action="fantasy.premierleague.com"
          />
        ) : (
          <div className="overflow-x-auto">
            <table className={TABLE_CLASS}>
              <thead className={THEAD_CLASS}>
                <tr>
                  <th className={thClass()}>League</th>
                  <th className={thClass(true)}>Rank</th>
                  <th className={thClass(true)}>Of</th>
                  <th className={thClass(true)}>Move</th>
                  <th className={thClass(true)}>Gap</th>
                  <th className={thClass()}>Would</th>
                  <th className={thClass()}></th>
                </tr>
              </thead>
              <tbody>
                {overview.private.map((row) => (
                  <tr key={row.league_id}
                      data-testid={`league-${row.league_id}`}
                      data-focus={String(row.is_focus)}
                      className={`${TR_CLASS}${row.is_focus
                        ? ` ${TR_SELECTED_CLASS}` : ''}`}>
                    <td className={`${tdClass()} ${row.is_focus
                      ? 'text-text' : 'text-text-secondary'}`}>
                      {row.started ? (
                        <Link to={`/league?tab=race&league=${row.league_id}`}
                              className="text-accent-text hover:underline">
                          {row.name}
                        </Link>
                      ) : row.name}
                    </td>
                    <td className={`${tdClass(true)} text-text`}>
                      {row.rank === null ? '—' : n(row.rank)}
                    </td>
                    <td className={`${tdClass(true)} text-text-muted`}>
                      {row.entries === null ? '—' : n(row.entries)}
                    </td>
                    <td className={tdClass(true)}>
                      <Move rank={row.rank} last_rank={row.last_rank} />
                    </td>
                    <td className={`${tdClass(true)} ${row.started
                      ? 'text-text' : 'text-text-muted'}`}>
                      {gapText(row)}
                    </td>
                    <td className={`${tdClass()} text-text-muted`}>
                      {row.is_focus ? (
                        <span className="inline-flex items-center gap-1.5">
                          <span className="text-text">
                            {`${overview.focus_stance} · λ ${lamText(overview.focus_lam)}`}
                          </span>
                          {overview.stance !== 'auto' && (
                            <Chip tone="warn">manual</Chip>
                          )}
                        </span>
                      ) : row.would ? `would ${row.would}` : '—'}
                    </td>
                    <td className={tdClass()}>
                      {row.is_focus ? (
                        <Chip tone="neutral" className="text-accent-text">focus</Chip>
                      ) : row.started ? (
                        <Button variant="ghost" disabled={busy}
                                onClick={() => onFocus(row.league_id)}>
                          make focus
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {overview.private.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <span className="label">Stance · focus league</span>
            <Segmented
              label="Stance"
              options={stanceOptions}
              value={overview.stance}
              onChange={(next) => { if (!busy) onStance(next) }}
            />
          </div>
        )}
      </Card>
      <Card title="Public leagues">
        <div className="overflow-x-auto">
          <table className={TABLE_CLASS}>
            <thead className={THEAD_CLASS}>
              <tr>
                <th className={thClass()}>League</th>
                <th className={thClass(true)}>Rank</th>
                <th className={thClass(true)}>Of</th>
                <th className={thClass(true)}>Move</th>
              </tr>
            </thead>
            <tbody>
              {overview.public.map((row) => (
                <tr key={row.league_id}
                    data-testid={`public-${row.league_id}`}
                    className={TR_CLASS}>
                  <td className={`${tdClass()} text-text-secondary`}>{row.name}</td>
                  <td className={`${tdClass(true)} text-text`}>
                    {row.rank === null ? '—' : n(row.rank)}
                  </td>
                  <td className={`${tdClass(true)} text-text-muted`}>
                    {row.entries === null ? '—' : n(row.entries)}
                  </td>
                  <td className={tdClass(true)}>
                    <Move rank={row.rank} last_rank={row.last_rank} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  )
}
