import * as Tabs from '@radix-ui/react-tabs'
import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'
import { EmptyState, PageHeader } from '../kit'
import type { AdviceLatest, WhatIfRequest } from '../types'
import ChipsTab from './planning/ChipsTab'
import DraftsTab from './planning/DraftsTab'
import TickerTab from './planning/TickerTab'
import Timeline from './planning/Timeline'
import WhatIfTab from './planning/WhatIfTab'

const TAB_CLASS = 'px-3 py-2 text-text-muted data-[state=active]:text-text '
  + 'data-[state=active]:border-b data-[state=active]:border-text'

// Radix keeps an unselected tab unmounted, so the constraints have to live
// above both tabs or a draft saved from the Drafts tab would save whatever
// the last remount defaulted to.
const EMPTY_WHATIF: WhatIfRequest = {
  lock: [], ban: [], force_in: [], max_hits: 0, chip: 'none', horizon: null,
}

export default function Planning() {
  const [gw, setGw] = useState<number | null>(null)
  const [missing, setMissing] = useState(false)
  const [whatif, setWhatif] = useState<WhatIfRequest>(EMPTY_WHATIF)

  useEffect(() => {
    apiGet<AdviceLatest>('/api/advice/latest')
      .then((body) => setGw(body.gw))
      .catch(() => setMissing(true))
  }, [])

  if (missing) {
    return (
      <>
        <PageHeader title="Planning" />
        <EmptyState
          title="Nothing planned yet"
          detail="Every panel here reads the last advice run — the horizon it
                  solved, the chips it scored and the pool it optimised over."
          action="Run advise"
        />
      </>
    )
  }

  return (
    <>
      <PageHeader title="Planning"
                  context={gw === null ? undefined : `GW${gw} horizon`} />
      <Tabs.Root defaultValue="timeline">
        <Tabs.List className="mb-4 flex border-b border-divider">
          <Tabs.Trigger value="timeline" className={TAB_CLASS}>Timeline</Tabs.Trigger>
          <Tabs.Trigger value="whatif" className={TAB_CLASS}>What-If</Tabs.Trigger>
          <Tabs.Trigger value="drafts" className={TAB_CLASS}>Drafts</Tabs.Trigger>
          <Tabs.Trigger value="chips" className={TAB_CLASS}>Chips</Tabs.Trigger>
          <Tabs.Trigger value="ticker" className={TAB_CLASS}>Ticker</Tabs.Trigger>
        </Tabs.List>
        <Tabs.Content value="timeline">
          {gw !== null && <Timeline gw={gw} />}
        </Tabs.Content>
        <Tabs.Content value="whatif">
          <WhatIfTab value={whatif} onChange={setWhatif} />
        </Tabs.Content>
        <Tabs.Content value="drafts"><DraftsTab current={whatif} /></Tabs.Content>
        <Tabs.Content value="chips"><ChipsTab /></Tabs.Content>
        <Tabs.Content value="ticker"><TickerTab /></Tabs.Content>
      </Tabs.Root>
    </>
  )
}
