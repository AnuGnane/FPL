import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'
import { useDebounced } from '../api/useDebounced'
import type { PlayerRow, WhatIfRequest } from '../types'

type ListKey = 'lock' | 'ban' | 'force_in'

const LABELS: Record<ListKey, string> = {
  lock: 'Lock', ban: 'Ban', force_in: 'Force in',
}

function PlayerPicker(
  { label, codes, names, onAdd, onRemove }: {
    label: string
    codes: number[]
    names: Record<number, string>
    onAdd: (player: PlayerRow) => void
    onRemove: (code: number) => void
  },
) {
  const [query, setQuery] = useState('')
  const [matches, setMatches] = useState<PlayerRow[]>([])
  const search = useDebounced(query)

  useEffect(() => {
    if (search.length < 2) { setMatches([]); return }
    let live = true
    apiGet<PlayerRow[]>(`/api/players?search=${encodeURIComponent(search)}`)
      .then((rows) => { if (live) setMatches(rows.slice(0, 8)) })
      .catch(() => { if (live) setMatches([]) })
    return () => { live = false }
  }, [search])

  return (
    <div className="picker">
      <label>
        {label}
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="search a player"
        />
      </label>
      <div className="chips">
        {codes.map((code) => (
          <span className="tag" key={code}>
            {names[code] ?? code}
            <button className="player-link" onClick={() => onRemove(code)}>
              ×
            </button>
          </span>
        ))}
      </div>
      {matches.length > 0 && (
        <div className="matches">
          {matches.map((player) => (
            <button
              key={player.code}
              onClick={() => { onAdd(player); setQuery('') }}
            >
              {player.name} · {player.position} · £{player.price}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default function ConstraintsPanel(
  { value, onChange }: {
    value: WhatIfRequest
    onChange: (next: WhatIfRequest) => void
  },
) {
  const [names, setNames] = useState<Record<number, string>>({})

  const add = (key: ListKey) => (player: PlayerRow) => {
    setNames((prev) => ({ ...prev, [player.code]: player.name }))
    if (value[key].includes(player.code)) return
    onChange({ ...value, [key]: [...value[key], player.code] })
  }

  const remove = (key: ListKey) => (code: number) =>
    onChange({ ...value, [key]: value[key].filter((c) => c !== code) })

  return (
    <div className="card">
      <h2>Constraints</h2>
      {(Object.keys(LABELS) as ListKey[]).map((key) => (
        <PlayerPicker
          key={key}
          label={LABELS[key]}
          codes={value[key]}
          names={names}
          onAdd={add(key)}
          onRemove={remove(key)}
        />
      ))}
      <label>
        Max hits
        <select
          value={value.max_hits}
          onChange={(event) =>
            onChange({ ...value, max_hits: Number(event.target.value) })}
        >
          {[0, 1, 2, 3].map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
      </label>
      {/* Kept outside the label so it stays out of the select's accessible
          name: 0 is a real, active choice here, not an empty state. */}
      <p className="muted">
        0 is the default and forbids hits in your version; the original plan
        is solved unconstrained.
      </p>
      <label>
        Chip
        <select
          value={value.chip}
          onChange={(event) => onChange({
            ...value, chip: event.target.value as WhatIfRequest['chip'],
          })}
        >
          <option value="none">none</option>
          <option value="wc">wildcard</option>
          <option value="bb">bench boost</option>
          <option value="fh">free hit</option>
          <option value="tc">triple captain</option>
        </select>
      </label>
      <label>
        Horizon
        <select
          value={value.horizon ?? ''}
          onChange={(event) => onChange({
            ...value,
            horizon: event.target.value === '' ? null
              : Number(event.target.value),
          })}
        >
          <option value="">config default</option>
          {[1, 2, 3, 4, 5, 6].map((n) =>
            <option key={n} value={n}>{n} GW</option>)}
        </select>
      </label>
    </div>
  )
}
