import * as Tabs from '@radix-ui/react-tabs'
import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'
import { EmptyState, PageHeader } from '../kit'
import type { AdviceLatest, WhatIfRequest } from '../types'
import ChipsTab from './planning/ChipsTab'
import DraftsTab from './planning/DraftsTab'
import PlannerBoard from './planning/PlannerBoard'
import TickerTab from './planning/TickerTab'
import Timeline from './planning/Timeline'
import WhatIfTab from './planning/WhatIfTab'

// `shrink-0 whitespace-nowrap` so a trigger scrolls out of the strip rather
// than compressing into two lines of one word at 390px.
const TAB_CLASS = 'shrink-0 whitespace-nowrap px-3 py-2 text-text-muted '
  + 'data-[state=active]:text-text '
  + 'data-[state=active]:border-b data-[state=active]:border-text'

// Radix keeps an unselected tab unmounted, so the constraints have to live
// above both tabs or a draft saved from the Drafts tab would save whatever
// the last remount defaulted to.
//
// Since v11 the *selection* lives up here too, for the same reason turned
// round: the board's "Try these changes" writes the constraints and then has
// to move the reader to the tab that reads them, which an uncontrolled
// `Tabs.Root` gives no way to do. Not persisted — a view preference is a real
// feature with real questions behind it (`ThisWeek.tsx:31-34`).
const EMPTY_WHATIF: WhatIfRequest = {
  lock: [], ban: [], force_in: [], max_hits: 0, chip: 'none', horizon: null,
}

export default function Planning() {
  const [gw, setGw] = useState<number | null>(null)
  // code → team code, from the six player keys v9a's identity.py decorates on
  // the way out of /api/advice/latest. Built from the response Planning
  // already makes, so the timeline's fixture chips cost no extra request
  // (plan A11). A player the advice never named is simply absent, and the
  // timeline draws no chip for him.
  const [teamByCode, setTeamByCode] = useState<Map<number, number>>(new Map())
  const [missing, setMissing] = useState(false)
  const [whatif, setWhatif] = useState<WhatIfRequest>(EMPTY_WHATIF)
  const [tab, setTab] = useState('timeline')

  useEffect(() => {
    apiGet<AdviceLatest>('/api/advice/latest')
      .then((body) => {
        setGw(body.gw)
        const map = new Map<number, number>()
        const a = body.advice
        // captain and vice are single refs, not arrays; a payload written
        // before v9a's enrichment carries `team_code: undefined`, which the
        // typeof guard covers along with an explicit null.
        // `?? []` on the lists: the map is a decoration on the timeline, and
        // an advice payload that is missing one of them must not take the
        // whole hub to its "nothing planned yet" state.
        for (const ref of [...(a?.xi ?? []), ...(a?.bench ?? []),
          ...(a?.buys ?? []), ...(a?.sells ?? []), a?.captain, a?.vice]) {
          if (ref && typeof ref.team_code === 'number') {
            map.set(ref.code, ref.team_code)
          }
        }
        setTeamByCode(map)
      })
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
      <Tabs.Root value={tab} onValueChange={setTab}>
        <Tabs.List className="mb-4 flex overflow-x-auto border-b
                              border-divider">
          <Tabs.Trigger value="timeline" className={TAB_CLASS}>Timeline</Tabs.Trigger>
          <Tabs.Trigger value="board" className={TAB_CLASS}>Board</Tabs.Trigger>
          <Tabs.Trigger value="whatif" className={TAB_CLASS}>What-If</Tabs.Trigger>
          <Tabs.Trigger value="drafts" className={TAB_CLASS}>Drafts</Tabs.Trigger>
          <Tabs.Trigger value="chips" className={TAB_CLASS}>Chips</Tabs.Trigger>
          <Tabs.Trigger value="ticker" className={TAB_CLASS}>Ticker</Tabs.Trigger>
        </Tabs.List>
        <Tabs.Content value="timeline">
          {gw !== null && <Timeline gw={gw} teamByCode={teamByCode} />}
        </Tabs.Content>
        <Tabs.Content value="board">
          {gw !== null && (
            <PlannerBoard
              gw={gw}
              onTry={(request) => { setWhatif(request); setTab('whatif') }}
            />
          )}
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
