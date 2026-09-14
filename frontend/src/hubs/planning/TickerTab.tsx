import { useState } from 'react'
import { usePageData } from '../../api/pageData'
import { Card, INPUT_CLASS } from '../../kit'
import FixtureTicker from './FixtureTicker'
import type { HealthData } from '../../types'

export default function TickerTab() {
  const [weeks, setWeeks] = useState(8)
  // Elo difficulty is the fallback, but it is only worth nagging about when
  // there is no odds key to blame — /api/health is the one place that knows.
  // Undefined while it loads and after any failure, which is the third state
  // the ticker's nag already reads: this is a hint about a hint, and it has
  // no error state of its own to render.
  const health = usePageData<HealthData>('/api/health')
  const oddsKey = health.data?.odds_key_present

  return (
    <>
      <Card className="mb-4">
        <label className="flex items-center gap-2">
          <span className="label">Weeks</span>
          <select
            value={weeks}
            onChange={(event) => setWeeks(Number(event.target.value))}
            className={`${INPUT_CLASS} tn`}
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
