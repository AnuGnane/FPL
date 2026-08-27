import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'
import PlayerName from './PlayerName'
import type { NewsPanelData, NewsRow } from '../types'

const pct = (value: number) => `${Math.round(value * 100)}%`

// The evidence, in the order the layer weighed it: what the game says, what
// the injury feed says, what the predicted line-up says. Missing sources are
// left out rather than printed as "unknown" — a source that said nothing is
// not a source that said "no".
function evidence(row: NewsRow): string[] {
  const bits: string[] = []
  if (row.chance_of_playing !== null) {
    bits.push(`official ${row.chance_of_playing}%`)
  } else if (row.status) {
    bits.push(`official ${row.status}`)
  }
  if (row.injury_type) {
    bits.push(row.expected_return_gw !== null
      ? `${row.injury_type}, back GW${row.expected_return_gw}`
      : row.injury_type)
  }
  if (row.lineup_hint) bits.push(`line-up: ${row.lineup_hint}`)
  return bits
}

/**
 * What the news layer changed this week, and on whose word.
 *
 * Hidden whenever there is nothing to show — no shadow log, no artifacts, a
 * week where every source agreed with the official flags. "The news moved
 * nobody" and "we have not looked" render identically on purpose: neither is
 * something the manager has to act on.
 */
export default function NewsPanel({ gw }: { gw: number }) {
  const [data, setData] = useState<NewsPanelData | null>(null)

  useEffect(() => {
    apiGet<NewsPanelData>(`/api/news/${gw}`).then(setData)
      .catch(() => setData(null))
  }, [gw])

  if (!data || data.moved === 0) return null

  return (
    <div className="card">
      <h2>
        News moved {data.moved} player{data.moved === 1 ? '' : 's'}
      </h2>
      <table>
        <thead>
          <tr>
            <th>Player</th>
            <th>P(plays) news / flags</th>
            <th>xMins news / flags</th>
            <th>Why</th>
          </tr>
        </thead>
        <tbody>
          {data.rows.map((row) => (
            <tr key={row.code}>
              <td>
                <PlayerName code={row.code} name={row.name} />{' '}
                <span className="muted">{row.team_name}</span>
              </td>
              <td className={row.p_play_news < row.p_play_flags
                ? 'bad' : 'good'}>
                {pct(row.p_play_news)} / {pct(row.p_play_flags)}
              </td>
              <td>
                {Math.round(row.e_min_news)} / {Math.round(row.e_min_flags)}
              </td>
              <td className="muted">{evidence(row).join(' · ')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
