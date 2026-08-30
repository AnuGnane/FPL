import { useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import { useDebounced } from '../../api/useDebounced'
import { Card, PosBadge, fmtNum } from '../../kit'
import type { PlayerRow, WhatIfRequest } from '../../types'

type ListKey = 'lock' | 'ban' | 'force_in'

const LABELS: Record<ListKey, string> = {
  lock: 'Lock', ban: 'Ban', force_in: 'Force in',
}

const FIELD = 'rounded-card border border-border bg-base px-2 py-1 text-text'

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
    <div className="relative">
      <label className="flex flex-col gap-1">
        <span className="label">{label}</span>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="search a player"
          className={FIELD}
        />
      </label>
      {codes.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {codes.map((code) => (
            <span
              key={code}
              className="inline-flex items-center gap-1 rounded border
                         border-border px-1.5 py-0.5 text-[11px]
                         text-text-secondary"
            >
              {names[code] ?? code}
              <button
                type="button"
                aria-label={`remove ${names[code] ?? code}`}
                onClick={() => onRemove(code)}
                className="text-text-faint hover:text-rust"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      {matches.length > 0 && (
        <div className="absolute z-10 mt-1 flex w-full flex-col rounded-card
                        border border-border bg-card p-1">
          {matches.map((player) => (
            <button
              key={player.code}
              type="button"
              onClick={() => { onAdd(player); setQuery('') }}
              className="flex items-center gap-2 rounded px-2 py-1 text-left
                         text-text-secondary hover:bg-base hover:text-text"
            >
              <PosBadge pos={player.position} variant="dot" />
              {player.name}
              <span className="num ml-auto text-text-faint">
                {fmtNum(player.price)}
              </span>
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
    <Card title="Constraints" className="mb-4">
      <div className="grid gap-3 sm:grid-cols-3">
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
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <div>
          <label className="flex flex-col gap-1">
            <span className="label">Max hits</span>
            <select
              value={value.max_hits}
              onChange={(event) =>
                onChange({ ...value, max_hits: Number(event.target.value) })}
              className={FIELD}
            >
              {[0, 1, 2, 3].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          {/* Kept outside the label so it stays out of the select's accessible
              name: 0 is a real, active choice here, not an empty state. */}
          <p className="mt-1 text-text-faint">
            0 is the default and forbids hits in your version; the original
            plan is solved unconstrained.
          </p>
        </div>
        <label className="flex h-fit flex-col gap-1">
          <span className="label">Chip</span>
          <select
            value={value.chip}
            onChange={(event) => onChange({
              ...value, chip: event.target.value as WhatIfRequest['chip'],
            })}
            className={FIELD}
          >
            <option value="none">none</option>
            <option value="wc">wildcard</option>
            <option value="bb">bench boost</option>
            <option value="fh">free hit</option>
            <option value="tc">triple captain</option>
          </select>
        </label>
        <label className="flex h-fit flex-col gap-1">
          <span className="label">Horizon</span>
          <select
            value={value.horizon ?? ''}
            onChange={(event) => onChange({
              ...value,
              horizon: event.target.value === '' ? null
                : Number(event.target.value),
            })}
            className={FIELD}
          >
            <option value="">config default</option>
            {[1, 2, 3, 4, 5, 6].map((n) =>
              <option key={n} value={n}>{n} GW</option>)}
          </select>
        </label>
      </div>
    </Card>
  )
}
