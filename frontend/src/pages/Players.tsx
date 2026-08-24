import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'
import { useDebounced } from '../api/useDebounced'
import PlayerName from '../components/PlayerName'
import type { PlayerRow } from '../types'

const SORTS = ['ep_next', 'ep_horizon', 'price', 'ownership', 'league_eo',
  'name']
const POSITIONS = ['', 'GKP', 'DEF', 'MID', 'FWD']

function setPieces(player: PlayerRow): string {
  const parts = [player.penalties_order, player.free_kicks_order,
    player.corners_order]
  if (parts.every((part) => part === null)) return '–'
  return parts.map((part) => part ?? '–').join(' / ')
}

export default function Players() {
  const [rows, setRows] = useState<PlayerRow[]>([])
  const [error, setError] = useState<string | null>(null)
  const [position, setPosition] = useState('')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState('ep_next')
  const query = useDebounced(search)

  useEffect(() => {
    const params = new URLSearchParams({ sort })
    if (position) params.set('position', position)
    if (query) params.set('search', query)
    let live = true
    apiGet<PlayerRow[]>(`/api/players?${params.toString()}`)
      .then((body) => { if (live) { setRows(body); setError(null) } })
      .catch((e: Error) => { if (live) setError(e.message) })
    return () => { live = false }
  }, [position, query, sort])

  return (
    <>
      <h2>Players</h2>
      <div className="card">
        <label>
          Position
          <select value={position}
            onChange={(event) => setPosition(event.target.value)}>
            {POSITIONS.map((value) => (
              <option key={value} value={value}>{value || 'all'}</option>
            ))}
          </select>
        </label>
        <label>
          Search
          <input value={search}
            onChange={(event) => setSearch(event.target.value)} />
        </label>
        <label>
          Sort
          <select value={sort}
            onChange={(event) => setSort(event.target.value)}>
            {SORTS.map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        </label>
      </div>
      {error && <p className="bad">{error}</p>}
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Player</th><th>Pos</th><th>Team</th><th>£</th>
              <th>xPts</th><th>Horizon</th><th>Own%</th><th>League EO</th>
              <th>Set pieces</th><th />
            </tr>
          </thead>
          <tbody>
            {rows.map((player) => (
              <tr key={player.code}>
                <td>
                  <PlayerName code={player.code} name={player.name} />
                  {!player.available && (
                    <span className="bad" title={player.news}> ⚠</span>
                  )}
                </td>
                <td>{player.position}</td>
                <td>{player.team_name}</td>
                <td>{player.price}</td>
                <td>{player.ep_next}</td>
                <td>{player.ep_horizon}</td>
                <td>{player.ownership}</td>
                <td>{player.league_eo}</td>
                <td>{setPieces(player)}</td>
                <td>{player.in_squad ? 'owned' : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
