import { useEffect, useState } from 'react'
import {
  CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis,
  YAxis,
} from 'recharts'
import { apiGet } from '../../api/client'
import {
  type Column, Card, DataTable, EmptyState, TONE_CLASS, fmtDelta, toneOf,
} from '../../kit'
import type { JournalData, JournalRow } from '../../types'

const COLUMNS: Column<JournalRow>[] = [
  { key: 'gw', header: 'GW', primary: true, numeric: true, value: (r) => r.gw },
  { key: 'model_pts', header: 'Model', primary: true, numeric: true,
    value: (r) => r.model_pts },
  { key: 'actual_pts', header: 'You', primary: true, numeric: true,
    value: (r) => r.actual_pts },
  {
    key: 'delta', header: 'Δ', numeric: true, value: (r) => r.delta,
    render: (r) => (
      <span className={TONE_CLASS[toneOf(r.delta)]}>{fmtDelta(r.delta, 0)}</span>
    ),
  },
  { key: 'model_captain', header: 'Model C',
    value: (r) => r.model_captain ?? '—' },
  { key: 'actual_captain', header: 'Your C',
    value: (r) => r.actual_captain ?? '—' },
  { key: 'model_buys', header: 'Model in',
    value: (r) => r.model_buys.join(', ') || '—' },
]

export default function JournalTab() {
  const [data, setData] = useState<JournalData | null>(null)

  useEffect(() => {
    apiGet<JournalData>('/api/journal').then(setData)
      .catch(() => setData({ rows: [], cumulative: [], built_at: null }))
  }, [])

  if (!data) return <p className="text-text-muted">Loading…</p>
  if (data.rows.length === 0) {
    return (
      <EmptyState
        title="Nothing to compare yet"
        detail="The journal scores the model's XI against the one you played,
                so it needs a gameweek with both a banked advice run and a
                finished result."
        action="Run advise"
      />
    )
  }

  return (
    <div>
      <Card title="Model vs you, cumulative" className="mb-4">
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={data.cumulative}>
            <CartesianGrid stroke="var(--color-divider)" vertical={false} />
            <XAxis dataKey="gw" stroke="var(--color-text-muted)" />
            <YAxis stroke="var(--color-text-muted)" />
            <Tooltip contentStyle={{
              background: 'var(--color-card)',
              border: '1px solid var(--color-border)',
            }} />
            <Legend />
            <Line type="monotone" dataKey="model" dot={false}
                  stroke="var(--color-sage)" strokeWidth={2} />
            <Line type="monotone" dataKey="actual" dot={false}
                  stroke="var(--color-info)" strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </Card>
      <Card title="By gameweek">
        <DataTable columns={COLUMNS} rows={data.rows} rowKey={(r) => r.gw}
                   rowLabel={(r) => `GW${r.gw}`} initialSort="gw" />
      </Card>
    </div>
  )
}
