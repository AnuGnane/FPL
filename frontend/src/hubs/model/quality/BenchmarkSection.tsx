import { Card } from '../../../kit'
import type { BenchmarkEvaluation, StratifiedTable } from '../../../types'
import StratifiedTableView from './StratifiedTableView'

// Cut from `QualityTab.tsx` in v19h §2.1: the tab was 546 lines of
// hand tables, and a section nobody can find is a section nobody checks.
// Markup and class strings are the v18f ones, byte for byte — the Model
// screenshot pair is the proof.

const SOURCE_LABELS: Record<string, string> = {
  openfpl: 'OpenFPL',
  fplreview: 'FPL Review',
}

export default function BenchmarkSection(
  { benchmark }: { benchmark: BenchmarkEvaluation },
) {
  const references: Array<[string, StratifiedTable]> = Object.entries(
    benchmark.references,
  ).map(([source, table]) => [
    SOURCE_LABELS[source] ?? source,
    Object.fromEntries(Object.entries(table).map(([cat, m]) => [
      cat, { rmse: m.rmse, mae: m.mae, n: 0 },
    ])) as StratifiedTable,
  ])
  return (
    <Card title={`Benchmark — ${benchmark.test_season}`} className="mb-4">
      <StratifiedTableView
        columns={[['Ours', benchmark.stratified.all ?? {}], ...references]}
      />
      <p className="mt-3 text-text-muted">{benchmark.caveat}</p>
    </Card>
  )
}
