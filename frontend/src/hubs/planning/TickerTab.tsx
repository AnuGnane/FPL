import { useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import { Card } from '../../kit'
import FixtureTicker from './FixtureTicker'
import type { HealthData } from '../../types'

export default function TickerTab() {
  const [weeks, setWeeks] = useState(8)
  // Elo difficulty is the fallback, but it is only worth nagging about when
  // there is no odds key to blame — /api/health is the one place that knows.
  const [oddsKey, setOddsKey] = useState<boolean | undefined>(undefined)

  useEffect(() => {
    apiGet<HealthData>('/api/health')
      .then((body) => setOddsKey(body.odds_key_present))
      .catch(() => setOddsKey(undefined))
  }, [])

  return (
    <>
      <Card className="mb-4">
        <label className="flex items-center gap-2">
          <span className="label">Weeks</span>
          <select
            value={weeks}
            onChange={(event) => setWeeks(Number(event.target.value))}
            className="num rounded-card border border-border bg-base px-2 py-1
                       text-text"
          >
            {[4, 6, 8, 10, 12].map((n) =>
              <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
      </Card>
      <FixtureTicker weeks={weeks} oddsKeyPresent={oddsKey} />
    </>
  )
}
