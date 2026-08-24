import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'
import FixtureTicker from '../components/FixtureTicker'
import type { HealthData } from '../types'

export default function Ticker() {
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
      <h2>Fixture Ticker</h2>
      <div className="card">
        <label>
          Weeks
          <select value={weeks}
            onChange={(event) => setWeeks(Number(event.target.value))}>
            {[4, 6, 8, 10, 12].map((n) =>
              <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
      </div>
      <FixtureTicker weeks={weeks} oddsKeyPresent={oddsKey} />
    </>
  )
}
