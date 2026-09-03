import { useCallback, useEffect, useState } from 'react'
import { apiDelete, apiGet, errorText } from '../../api/client'
import { Card, fmtNum, toast } from '../../kit'
import type { OverridesPanel } from '../../types'

export default function OverridesCard() {
  const [data, setData] = useState<OverridesPanel | null>(null)
  const load = useCallback(() => {
    apiGet<OverridesPanel>('/api/overrides').then(setData).catch(
      () => setData(null))
  }, [])
  useEffect(() => { load() }, [load])

  // A row that simply disappears is indistinguishable from a delete that
  // failed and a refetch that followed it, so both halves say what happened.
  const drop = async (code: number, name: string) => {
    try {
      setData(await apiDelete<OverridesPanel>(`/api/overrides/${code}`))
      toast('positive', `Unpinned ${name}. The model's own minutes apply again.`)
    } catch (e) {
      toast('negative', `Could not unpin ${name} — ${errorText(e)}`)
      load()
    }
  }

  if (!data) return null
  return (
    <Card title="Your pins" className="mb-4">
      <p className="mb-3 text-text-muted">
        Minutes you have overruled the model on. Applied last, over every
        automated source, to the coming gameweek only. Set them from a
        player's row on the Players page.
      </p>
      {!data.active && (
        <p className="mb-3 rounded-card border-l-2 border-rust bg-base px-3
                      py-2 text-text-muted">
          These are saved but not being applied: <code>[news] overrides</code>
          {' '}is false in config.toml.
        </p>
      )}
      {data.rows.length === 0
        ? <p className="text-text-muted">Nothing pinned.</p>
        : (
          <ul className="flex flex-col gap-2">
            {data.rows.map((row) => (
              <li key={row.code}
                  className="flex items-baseline justify-between gap-3">
                <span className="text-text">
                  {row.name}
                  {row.p_play !== null && (
                    <span className="text-text-secondary">
                      {` · p_play ${fmtNum(row.p_play, 2)}`}
                      {row.model_p_play !== null
                        && ` (model had ${fmtNum(row.model_p_play, 2)})`}
                    </span>
                  )}
                  {row.e_min !== null && (
                    <span className="text-text-secondary">
                      {` · minutes ${fmtNum(row.e_min, 0)}`}
                    </span>
                  )}
                  {row.note && (
                    <span className="text-text-muted">{` — ${row.note}`}</span>
                  )}
                </span>
                <button
                  type="button"
                  aria-label={`unpin ${row.name}`}
                  onClick={() => drop(row.code, row.name)}
                  className="rounded-card border border-border px-2 py-1
                             text-text-muted hover:text-text"
                >
                  Unpin
                </button>
              </li>
            ))}
          </ul>
          )}
    </Card>
  )
}
