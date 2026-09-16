import {
  Bar, Callout, Card, TABLE_CLASS, THEAD_CLASS, TR_CLASS, tdClass, thClass,
} from '../../../kit'
import type { NewsShadowData, NewsShadowSummary } from '../../../types'

// Cut from `QualityTab.tsx` in v19h §2.1: the tab was 546 lines of
// hand tables, and a section nobody can find is a section nobody checks.
// Markup and class strings are the v18f ones, byte for byte — the Model
// screenshot pair is the proof.

// Lower is better for both metrics, so "ahead" means a smaller number. Said
// in a sentence as well as drawn, because a pair of bars two hundredths apart
// is not a verdict anyone should have to squint at.
function verdict(shadow: NewsShadowData): string {
  // `overall` is `NewsShadowSummary | dict` on the server (`schemas.py:1156`):
  // an empty object until a gameweek has been scored, a full summary after.
  // Read the two numbers by type rather than by presence — the empty case is
  // `{}`, so `=== undefined` and `?? 0` both walk straight into it.
  const o = shadow.overall as Partial<NewsShadowSummary>
  if (typeof o.brier_news !== 'number' || typeof o.mae_news !== 'number') {
    return 'Nothing scored yet.'
  }
  const brier = (o.brier_flags ?? 0) - o.brier_news
  const mae = (o.mae_flags ?? 0) - o.mae_news
  if (brier > 0 && mae > 0) {
    return `News is ahead on both: Brier ${brier.toFixed(4)} better, `
      + `minutes MAE ${mae.toFixed(2)} better, over ${shadow.rows} `
      + 'player-gameweeks.'
  }
  if (brier <= 0 && mae <= 0) {
    return `Flags are ahead on both, over ${shadow.rows} player-gameweeks — `
      + 'the news layer is not earning its place yet.'
  }
  return `Split: Brier ${brier > 0 ? 'news' : 'flags'}, minutes `
    + `${mae > 0 ? 'news' : 'flags'}, over ${shadow.rows} player-gameweeks.`
}

// Paired bars, per gameweek, both metrics. Each pair is scaled to its own
// row's larger value: the two Brier numbers differ in the third decimal and a
// shared axis across gameweeks would draw every pair as one flat line.
function PairedBar({ news, flags }: { news: number; flags: number }) {
  const top = Math.max(news, flags) || 1
  // Both grey: the pair compares two instruments measuring the same thing,
  // and neither of them is a direction the reader is ahead or behind on.
  return (
    <span className="inline-flex flex-col gap-0.5 align-middle">
      <Bar fraction={news / top} width={112} testId="paired-news"
           aria-label={`news ${news}`} />
      <Bar fraction={flags / top} width={112} testId="paired-flags"
           aria-label={`flags ${flags}`} />
    </span>
  )
}

export default function NewsShadowSection(
  { shadow }: { shadow: NewsShadowData },
) {
  return (
    <Card title="News layer">
      {/* Information, not a warning (plan R5): grey bar, raised surface. */}
      <Callout className="mb-3">{verdict(shadow)}</Callout>
      <div className="overflow-x-auto">
        <table className={TABLE_CLASS}>
          <thead className={THEAD_CLASS}>
            <tr>
              <th scope="col" className={thClass()}>GW</th>
              <th scope="col" className={thClass(true)}>Brier news</th>
              <th scope="col" className={thClass(true)}>Brier flags</th>
              <th scope="col" />
              <th scope="col" className={thClass(true)}>Minutes MAE news</th>
              <th scope="col" className={thClass(true)}>MAE flags</th>
              <th scope="col" />
              <th scope="col" className={thClass(true)}>Rows</th>
            </tr>
          </thead>
          <tbody>
            {shadow.by_gw.map((row) => (
              <tr key={row.gw} className={TR_CLASS}>
                <td className={`${tdClass()} tn text-text`}>GW{row.gw}</td>
                {/* News against flags is two instruments, not better against
                    worse: the verdict sentence above says which is ahead. */}
                <td className={`${tdClass(true)} text-text`}>
                  {row.brier_news}
                </td>
                <td className={`${tdClass(true)} text-text-muted`}>
                  {row.brier_flags}
                </td>
                <td className={tdClass()}>
                  <PairedBar news={row.brier_news} flags={row.brier_flags} />
                </td>
                <td className={`${tdClass(true)} text-text`}>
                  {row.mae_news}
                </td>
                <td className={`${tdClass(true)} text-text-muted`}>
                  {row.mae_flags}
                </td>
                <td className={tdClass()}>
                  <PairedBar news={row.mae_news} flags={row.mae_flags} />
                </td>
                <td className={`${tdClass(true)} text-text-secondary`}>
                  {row.rows}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
