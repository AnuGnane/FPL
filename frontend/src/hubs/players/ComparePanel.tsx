import { useEffect, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis,
  YAxis,
} from 'recharts'
import { apiGet } from '../../api/client'
import { Badge, Card, PosBadge, Sparkline, fmtNum } from '../../kit'
import type {
  ComponentsBreakdown, FixtureMatrixData, PlayerRow,
} from '../../types'

const SERIES_COLOURS = ['var(--color-sage)', 'var(--color-info)',
  'var(--color-rust)', 'var(--color-text-muted)']

export interface ComparePanelProps {
  gw: number
  players: PlayerRow[]
}

export default function ComparePanel({ gw, players }: ComparePanelProps) {
  const [components, setComponents] = useState<ComponentsBreakdown | null>(null)
  const [matrix, setMatrix] = useState<FixtureMatrixData | null>(null)

  useEffect(() => {
    apiGet<ComponentsBreakdown>(`/api/components/${gw}`).then(setComponents)
      .catch(() => setComponents(null))
    apiGet<FixtureMatrixData>(`/api/fixtures/matrix?from=${gw}&n=6`)
      .then(setMatrix).catch(() => setMatrix(null))
  }, [gw])

  if (players.length < 2) {
    return <p className="text-text-muted">Pick at least two players to compare.</p>
  }
  if (players.length > 4) {
    return <p className="text-text-muted">Compare at most four players at once.</p>
  }

  // One row per component label, one bar series per player: the shape Recharts
  // stacks, and the shape that makes "where does his EP come from" readable.
  const labels = new Set<string>()
  for (const player of components?.players ?? []) {
    for (const fixture of player.fixtures) {
      for (const component of fixture.components) labels.add(component.label)
    }
  }
  const chart = [...labels].map((label) => {
    const row: Record<string, string | number> = { label }
    for (const player of players) {
      const found = components?.players.find((p) => p.code === player.code)
      row[player.name] = found?.fixtures.reduce((total, fixture) => (
        total + (fixture.components.find((c) => c.label === label)?.points ?? 0)
      ), 0) ?? 0
    }
    return row
  })

  return (
    <div>
      <Card title="EP components" className="mb-4">
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={chart}>
            <CartesianGrid stroke="var(--color-divider)" vertical={false} />
            <XAxis dataKey="label" stroke="var(--color-text-muted)" />
            <YAxis stroke="var(--color-text-muted)" />
            <Tooltip contentStyle={{ background: 'var(--color-card)',
                                     border: '1px solid var(--color-border)' }} />
            <Legend />
            {players.map((player, i) => (
              <Bar key={player.code} dataKey={player.name}
                   fill={SERIES_COLOURS[i % SERIES_COLOURS.length]} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </Card>
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
        {players.map((player) => {
          const team = matrix?.teams.find((t) => t.code === player.team_code)
          return (
            <div key={player.code} data-testid={`compare-${player.code}`}>
              <Card title={player.name}
                    action={<PosBadge pos={player.position} />}>
                <dl className="grid grid-cols-2 gap-1">
                  <dt className="label">Price</dt>
                  <dd className="num text-right text-text">
                    {fmtNum(player.price)}
                  </dd>
                  <dt className="label">xPts</dt>
                  <dd className="num text-right text-text">
                    {fmtNum(player.ep_next)}
                  </dd>
                  <dt className="label">EO%</dt>
                  <dd className="num text-right text-text">
                    {fmtNum(player.league_eo)}
                  </dd>
                  <dt className="label">Own%</dt>
                  <dd className="num text-right text-text">
                    {fmtNum(player.ownership)}
                  </dd>
                </dl>
                <div className="mt-2">
                  <p className="label">Last 4</p>
                  <Sparkline values={player.last4} />
                </div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {(team?.cells ?? []).map((cell) => {
                    // The cell carries two scores because a fixture is two
                    // different questions. `attack` is how freely the opponent
                    // concedes; `defence` is how hard they make a clean sheet.
                    // Colouring every card by `attack` told a goalkeeper's
                    // owner about his chances of scoring.
                    const score = player.position === 'GKP'
                      || player.position === 'DEF'
                      ? cell.defence
                      : cell.attack
                    return (
                      <Badge
                        key={cell.gw}
                        variant={score < 0.4 ? 'positive'
                          : score > 0.6 ? 'negative' : 'neutral'}
                        title={`GW${cell.gw} · ${cell.home ? 'home' : 'away'}`}
                      >
                        {cell.opponent}
                      </Badge>
                    )
                  })}
                </div>
              </Card>
            </div>
          )
        })}
      </div>
    </div>
  )
}
