import { Card } from '../../../kit'
import type { FlagLatencyData, PresserGradesData } from '../../../types'
import FlagLatencySection from './FlagLatencySection'
import PresserGradesSection from './PresserGradesSection'

// Cut from `QualityTab.tsx` in v19h §2.1: the tab was 546 lines of
// hand tables, and a section nobody can find is a section nobody checks.
// Markup and class strings are the v18f ones, byte for byte — the Model
// screenshot pair is the proof.

export default function AvailabilitySection({ flag, presser }:
                             { flag: FlagLatencyData | null
                               presser: PresserGradesData | null }) {
  return (
    <Card title="Availability signal" className="mt-4">
      {flag && <FlagLatencySection data={flag} />}
      {presser && <PresserGradesSection data={presser} />}
    </Card>
  )
}
