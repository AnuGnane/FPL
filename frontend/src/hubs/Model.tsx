import * as Tabs from '@radix-ui/react-tabs'
import { useCallback, useState } from 'react'
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
  // A finished job has just rewritten reports/, and the tab underneath was
  // still showing the numbers from before it ran with nothing to say they were
  // stale. Bumping the key remounts that tab, which is how each one fetches.
  // Evaluate writes the quality artifact; refresh-data moves what Health
  // grades. Neither touches the other's tab, so neither disturbs it.
  const [qualityNonce, setQualityNonce] = useState(0)
  const [healthNonce, setHealthNonce] = useState(0)
  const reloadQuality = useCallback(() => setQualityNonce((n) => n + 1), [])
  const reloadHealth = useCallback(() => setHealthNonce((n) => n + 1), [])
  const [reviewNonce, setReviewNonce] = useState(0)
  const reloadReview = useCallback(() => setReviewNonce((n) => n + 1), [])

  // The second class of writer (v17h §5): not a request that writes, but a job
  // that rewrites the file another hub's card is reading. Before the cycle a
  // navigation refetched and neither of these could strand anything; now This
  // Week holds /api/players and /api/news/{gw} until something clears them,
  // and the nonces above only remount the tab under this header.
  //
  // `refresh-data` rewrites live/players.parquet, which is the explorer's
  // table and the names, clubs and official flags every news panel joins
  // against; the panel's URL carries a gameweek this hub has no way to name,
  // hence the prefix. `field-scrape` rewrites the top-10k sample behind the
  // three EO columns. The other four write reports/ — and Snapshot news the
  // availability log, which feeds the *next* advise run and Health, not a
  // cached URL — so they clear nothing.
  const refreshedData = useCallback(() => {
    reloadHealth()
    invalidate('/api/players')
    invalidatePrefix('/api/news/')
  }, [reloadHealth])
  const scrapedField = useCallback(() => {
    reloadHealth()
    invalidate('/api/players')
  }, [reloadHealth])

  return (
    <>
      <PageHeader
        title="Model"
        context="How well it forecasts, what it decided, and whether the data
                 under it is fresh."
        action={(
          // The header is the hub's one control lane: every job that rewrites
          // something a tab under it renders lives here, and each says which
          // tab it invalidates. Track pens rewrites the quality artifact's
          // neighbour; snapshot moves what Health grades.
          <div className="flex flex-wrap gap-2">
            <JobButton kind="evaluate" label="Evaluate"
                       onDone={reloadQuality} />
            <JobButton kind="track-pens" label="Track pens"
                       onDone={reloadQuality} />
            <JobButton kind="review" label="Review last week"
                       onDone={reloadReview} />
            <JobButton kind="refresh-data" label="Refresh data"
                       onDone={refreshedData} />
            <JobButton kind="snapshot" label="Snapshot news"
                       onDone={reloadHealth} />
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
        <Tabs.Content value="quality">
          <QualityTab key={qualityNonce} />
        </Tabs.Content>
        <Tabs.Content value="journal"><JournalTab /></Tabs.Content>
        <Tabs.Content value="review"><ReviewTab key={reviewNonce} /></Tabs.Content>
        {/* Keyed off the same nonce as Review: a fresh grade must
            refresh both views, not one of them. */}
        <Tabs.Content value="season"><SeasonTab key={reviewNonce} /></Tabs.Content>
        <Tabs.Content value="history"><HistoryTab /></Tabs.Content>
        <Tabs.Content value="health"><HealthTab key={healthNonce} /></Tabs.Content>
        <Tabs.Content value="settings"><SettingsTab /></Tabs.Content>
      </Tabs.Root>
    </>
  )
}
