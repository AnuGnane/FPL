import { useState } from 'react'
import { usePageData } from '../../api/pageData'
import {
  Button, Card, Chip, PinDialog, PlayerName, TABLE_CLASS, THEAD_CLASS,
  TR_CLASS, tdClass, thClass,
} from '../../kit'
import type { NewsPanelData, NewsRow } from '../../types'

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
  // The error is deliberately unread: a panel nobody can fetch and a week the
  // news moved nobody render identically, which is the rule above.
  const { data } = usePageData<NewsPanelData>(`/api/news/${gw}`)
  // v19b §2.3: the row the manager is overruling, or null. This panel is
  // where a disagreement with the news layer is *read*, and until now acting
  // on it meant finding the same player again on the Players hub — the pin
  // now starts where the doubt is.
  const [pinning, setPinning] = useState<NewsRow | null>(null)

  if (!data || data.moved === 0) return null

  return (
    <Card
      title="News"
      className="mb-4"
      action={(
        <span className="text-text-muted">
          news moved {data.moved} player{data.moved === 1 ? '' : 's'}
        </span>
      )}
    >
      <div className="overflow-x-auto">
      <table className={TABLE_CLASS}>
        <thead className={THEAD_CLASS}>
          <tr>
            <th scope="col" className={thClass()}>Player</th>
            <th scope="col" className={thClass(true)}>P(plays) news / flags</th>
            <th scope="col" className={thClass(true)}>xMins news / flags</th>
            <th scope="col" className={thClass()}>Why</th>
            <th scope="col" className={thClass()} />
          </tr>
        </thead>
        <tbody>
          {data.rows.map((row) => (
            <tr key={row.code} className={TR_CLASS}>
              <td className={tdClass()}>
                <PlayerName code={row.code} name={row.name} />
                <span className="ml-1.5 text-text-faint">{row.team_name}</span>
              </td>
              {/* Rule 1: the pair is a direction — the news layer either
                  raised this player's chances or cut them. */}
              <td className={`${tdClass(true)} ${row.p_play_news
                < row.p_play_flags ? 'text-down' : 'text-up'}`}>
                {pct(row.p_play_news)} / {pct(row.p_play_flags)}
              </td>
              <td className={`${tdClass(true)} text-text`}>
                {Math.round(row.e_min_news)} / {Math.round(row.e_min_flags)}
              </td>
              <td className={tdClass()}>
                <span className="flex flex-wrap gap-1">
                  {evidence(row).map((bit) => (
                    <Chip key={bit}>{bit}</Chip>
                  ))}
                </span>
              </td>
              <td className={`${tdClass()} text-right`}>
                <Button
                  variant="ghost"
                  aria-label={`pin ${row.name}`}
                  title="Pin this player's availability over the model"
                  onClick={() => setPinning(row)}
                >
                  ☆
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      {/* No `onSaved`: the dialog invalidates `/api/overrides`, and both the
          moves card's pins line and the Why panel's list read that URL
          through the cache, so the write reaches them without being handed
          back up (v18e §2.3, v19b §2.2). */}
      {pinning && (
        <PinDialog code={pinning.code} name={pinning.name}
                   onClose={() => setPinning(null)} />
      )}
    </Card>
  )
}
