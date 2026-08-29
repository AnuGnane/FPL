import * as Tabs from '@radix-ui/react-tabs'
import { useCallback, useState } from 'react'
import { JobButton, PageHeader } from '../kit'
import HealthTab from './model/HealthTab'
import HistoryTab from './model/HistoryTab'
import JournalTab from './model/JournalTab'
import QualityTab from './model/QualityTab'

const TAB_CLASS = 'px-3 py-2 text-text-muted data-[state=active]:text-text '
  + 'data-[state=active]:border-b data-[state=active]:border-text'

export default function Model() {
  // A finished job has just rewritten reports/, and the tab underneath was
  // still showing the numbers from before it ran with nothing to say they were
  // stale. Bumping the key remounts that tab, which is how each one fetches.
  // Evaluate writes the quality artifact; refresh-data moves what Health
  // grades. Neither touches the other's tab, so neither disturbs it.
  const [qualityNonce, setQualityNonce] = useState(0)
  const [healthNonce, setHealthNonce] = useState(0)
  const reloadQuality = useCallback(() => setQualityNonce((n) => n + 1), [])
  const reloadHealth = useCallback(() => setHealthNonce((n) => n + 1), [])

  return (
    <>
      <PageHeader
        title="Model"
        action={(
          <div className="flex flex-wrap gap-2">
            <JobButton kind="evaluate" label="Evaluate"
                       onDone={reloadQuality} />
            <JobButton kind="refresh-data" label="Refresh data"
                       onDone={reloadHealth} />
          </div>
        )}
      />
      <Tabs.Root defaultValue="quality">
        <Tabs.List className="mb-4 flex border-b border-divider">
          <Tabs.Trigger value="quality" className={TAB_CLASS}>Quality</Tabs.Trigger>
          <Tabs.Trigger value="journal" className={TAB_CLASS}>Journal</Tabs.Trigger>
          <Tabs.Trigger value="history" className={TAB_CLASS}>History</Tabs.Trigger>
          <Tabs.Trigger value="health" className={TAB_CLASS}>Health</Tabs.Trigger>
        </Tabs.List>
        <Tabs.Content value="quality">
          <QualityTab key={qualityNonce} />
        </Tabs.Content>
        <Tabs.Content value="journal"><JournalTab /></Tabs.Content>
        <Tabs.Content value="history"><HistoryTab /></Tabs.Content>
        <Tabs.Content value="health"><HealthTab key={healthNonce} /></Tabs.Content>
      </Tabs.Root>
    </>
  )
}
