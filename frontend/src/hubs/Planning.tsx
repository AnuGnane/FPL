import * as Tabs from '@radix-ui/react-tabs'
import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'
import { EmptyState, PageHeader } from '../kit'
import type { AdviceLatest } from '../types'
import ChipsTab from './planning/ChipsTab'
import TickerTab from './planning/TickerTab'
import Timeline from './planning/Timeline'
import WhatIfTab from './planning/WhatIfTab'

const TAB_CLASS = 'px-3 py-2 text-text-muted data-[state=active]:text-text '
  + 'data-[state=active]:border-b data-[state=active]:border-text'

export default function Planning() {
  const [gw, setGw] = useState<number | null>(null)
  const [missing, setMissing] = useState(false)

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
          <Tabs.Trigger value="chips" className={TAB_CLASS}>Chips</Tabs.Trigger>
          <Tabs.Trigger value="ticker" className={TAB_CLASS}>Ticker</Tabs.Trigger>
        </Tabs.List>
        <Tabs.Content value="timeline">
          {gw !== null && <Timeline gw={gw} />}
        </Tabs.Content>
        <Tabs.Content value="whatif"><WhatIfTab /></Tabs.Content>
        <Tabs.Content value="chips"><ChipsTab /></Tabs.Content>
        <Tabs.Content value="ticker"><TickerTab /></Tabs.Content>
      </Tabs.Root>
    </>
  )
}
