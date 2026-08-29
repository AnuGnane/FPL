import * as Tabs from '@radix-ui/react-tabs'
import { JobButton, PageHeader } from '../kit'
import HealthTab from './model/HealthTab'
import HistoryTab from './model/HistoryTab'
import JournalTab from './model/JournalTab'
import QualityTab from './model/QualityTab'

const TAB_CLASS = 'px-3 py-2 text-text-muted data-[state=active]:text-text '
  + 'data-[state=active]:border-b data-[state=active]:border-text'

export default function Model() {
  return (
    <>
      <PageHeader
        title="Model"
        action={(
          <div className="flex flex-wrap gap-2">
            <JobButton kind="evaluate" label="Evaluate" />
            <JobButton kind="refresh-data" label="Refresh data" />
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
        <Tabs.Content value="quality"><QualityTab /></Tabs.Content>
        <Tabs.Content value="journal"><JournalTab /></Tabs.Content>
        <Tabs.Content value="history"><HistoryTab /></Tabs.Content>
        <Tabs.Content value="health"><HealthTab /></Tabs.Content>
      </Tabs.Root>
    </>
  )
}
