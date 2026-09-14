import * as Tabs from '@radix-ui/react-tabs'
import { useCallback } from 'react'
import { invalidate, invalidatePrefix } from '../api/pageData'
import {
  JobButton, PageHeader, TAB_CLASS, TAB_LIST_CLASS, useTabParam,
} from '../kit'
import HealthTab from './model/HealthTab'
import HistoryTab from './model/HistoryTab'
import JournalTab from './model/JournalTab'
import QualityTab from './model/QualityTab'
import ReviewTab from './model/ReviewTab'
import SeasonTab from './model/SeasonTab'
import SettingsTab from './model/SettingsTab'

// The strip's values, in strip order. Named so `useTabParam` can reject a
// `?tab=` this hub does not have rather than rendering an empty panel.
const TABS = ['quality', 'journal', 'review', 'season', 'history',
              'health', 'settings'] as const

export default function Model() {
  const [tab, setTab] = useTabParam(TABS, 'quality')

  // The second class of writer (v17h §5): not a request that writes, but a job
  // that rewrites the file a card is reading. Until v18e each tab under this
  // header did its own fetching on mount, so a finished job could be answered
  // by remounting the tab on a nonce; since §2.3 every tab reads through the
  // page-data cache, where a remount is served from the entry and asks the
  // server nothing. So the nonces are gone and each job names the URLs it
  // disturbed — which is the same list, said where the rest of the app can
  // hear it: the Health tab, the freshness strip in the shell and This Week's
  // explorer are three readers of what these buttons rewrite.
  //
  // `refresh-data` rewrites live/players.parquet — the explorer's table, the
  // names, clubs and official flags every news panel joins against, and the
  // fixtures behind every ticker and matrix; the news and fixture URLs carry
  // a gameweek and a horizon this hub has no way to name, hence the two
  // prefixes. `field-scrape` rewrites the top-10k sample behind the three EO
  // columns.
  //
  // The three that move a *file on disk* — refresh, field scrape, snapshot —
  // are the three the Health tab grades and the shell's freshness strip
  // dates, and they are the three the health nonce used to remount. The other
  // three write reports/ and clear the report each one wrote.
  const dated = useCallback(() => {
    invalidate('/api/health')
    invalidate('/api/meta/freshness')
  }, [])
  const evaluated = useCallback(() => { invalidate('/api/quality') }, [])
  const trackedPens = useCallback(() => { invalidate('/api/pens') }, [])
  // Review banks the decision ledger, which the Review and Season tabs read
  // and the journal is built from — the two tabs the one nonce used to key,
  // plus the one it always missed.
  const reviewed = useCallback(() => {
    invalidate('/api/review')
    invalidate('/api/journal')
  }, [])
  const refreshedData = useCallback(() => {
    dated()
    invalidate('/api/players')
    invalidatePrefix('/api/news/')
    invalidatePrefix('/api/fixtures/')
  }, [dated])
  const scrapedField = useCallback(() => {
    dated()
    invalidate('/api/players')
  }, [dated])

  return (
    <>
      <PageHeader
        title="Model"
        context="How well it forecasts, what it decided, and whether the data
                 under it is fresh."
        action={(
          // The header is the hub's one control lane: every job that
          // rewrites something a tab under it renders lives here, and each
          // names the URLs it disturbed above.
          <div className="flex flex-wrap gap-2">
            <JobButton kind="evaluate" label="Evaluate"
                       onDone={evaluated} />
            <JobButton kind="track-pens" label="Track pens"
                       onDone={trackedPens} />
            <JobButton kind="review" label="Review last week"
                       onDone={reviewed} />
            <JobButton kind="refresh-data" label="Refresh data"
                       onDone={refreshedData} />
            <JobButton kind="snapshot" label="Snapshot news"
                       onDone={dated} />
            <JobButton kind="field-scrape" label="Field scrape"
                       onDone={scrapedField} />
          </div>
        )}
      />
      <Tabs.Root value={tab} onValueChange={setTab}>
        <Tabs.List className={TAB_LIST_CLASS}>
          <Tabs.Trigger value="quality" className={TAB_CLASS}>Quality</Tabs.Trigger>
          <Tabs.Trigger value="journal" className={TAB_CLASS}>Journal</Tabs.Trigger>
          <Tabs.Trigger value="review" className={TAB_CLASS}>Review</Tabs.Trigger>
          <Tabs.Trigger value="season" className={TAB_CLASS}>Season</Tabs.Trigger>
          <Tabs.Trigger value="history" className={TAB_CLASS}>History</Tabs.Trigger>
          <Tabs.Trigger value="health" className={TAB_CLASS}>Health</Tabs.Trigger>
          <Tabs.Trigger value="settings" className={TAB_CLASS}>Settings</Tabs.Trigger>
        </Tabs.List>
        <Tabs.Content value="quality"><QualityTab /></Tabs.Content>
        <Tabs.Content value="journal"><JournalTab /></Tabs.Content>
        <Tabs.Content value="review"><ReviewTab /></Tabs.Content>
        <Tabs.Content value="season"><SeasonTab /></Tabs.Content>
        <Tabs.Content value="history"><HistoryTab /></Tabs.Content>
        <Tabs.Content value="health"><HealthTab /></Tabs.Content>
        <Tabs.Content value="settings"><SettingsTab /></Tabs.Content>
      </Tabs.Root>
    </>
  )
}
