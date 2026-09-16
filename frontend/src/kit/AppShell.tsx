import {
  Activity, CalendarCheck, type LucideIcon, Radio, Route, Trophy, Users,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import FreshnessStrip from './FreshnessStrip'
import ThemeToggle from './ThemeToggle'
import ToastOutlet from './Toast'
import { useIsCompact, useIsMobile, useIsWide } from './useMediaQuery'

/** The six hubs, in the order the spec lists them, each with its icon
 *  (spec §5: calendar-check, route, users, trophy, radio, activity). */
const HUBS: Array<[string, string, LucideIcon]> = [
  ['/', 'This Week', CalendarCheck],
  ['/planning', 'Planning', Route],
  ['/players', 'Players', Users],
  ['/league', 'League', Trophy],
  ['/live', 'Live', Radio],
  ['/model', 'Model', Activity],
]

/** The three shapes the nav takes, by width (v19c §2.2–§2.3). */
type NavMode = 'tabbar' | 'rail' | 'sidebar'

export default function AppShell({ children }: { children: ReactNode }) {
  const mobile = useIsMobile()
  const compact = useIsCompact()
  // v19c §2.4: the route decides the cap, and it is read here rather than in
  // the hub so the rule about how wide a page may be lives in the one file
  // that owns the page frame. Only Players opts out, and only past 1440.
  const { pathname } = useLocation()
  const wide = useIsWide() && pathname.startsWith('/players')

  // Active: accent text and a 2px accent bar on the left edge (sidebar) —
  // rule 3, "blue means it is active". No fill, no card.
  //
  // v19c §2.3: one builder for all three modes, so the rail cannot drift from
  // the sidebar and the sidebar's markup is what it was before the rail
  // existed — the desktop first paint does not move in this sub-cycle.
  const links = (mode: NavMode) => HUBS.map(([path, label, Icon]) => (
    <NavLink
      key={path}
      to={path}
      end={path === '/'}
      // The rail draws the icon alone, so the name has to be said instead:
      // aria-label for a screen reader, title for a pointer.
      aria-label={mode === 'rail' ? label : undefined}
      title={mode === 'rail' ? label : undefined}
      className={({ isActive }) => {
        if (mode === 'tabbar') {
          return `flex flex-col items-center gap-0.5 px-3 py-1.5 text-[11px] ${isActive
            ? 'text-accent-text' : 'text-text-muted hover:text-text'}`
        }
        if (mode === 'rail') {
          return `flex items-center justify-center border-l-2 py-2
           ${isActive
             ? 'border-accent text-accent-text'
             : 'border-transparent text-text-muted hover:text-text'}`
        }
        return `flex items-center gap-2.5 border-l-2 py-1.5 pl-2.5 pr-3 text-[13px]
           ${isActive
             ? 'border-accent text-accent-text'
             : 'border-transparent text-text-muted hover:text-text'}`
      }}
    >
      <Icon aria-hidden size={16} className="shrink-0" />
      {mode !== 'rail' && label}
    </NavLink>
  ))

  if (mobile) {
    return (
      // The bar is fixed to the bottom edge, so the page has to end above
      // it *and* above the home indicator (v19c §2.2) — otherwise the last
      // row of every hub sits under the glass on a modern phone.
      <div className="min-h-screen bg-base
                      pb-[calc(4rem+env(safe-area-inset-bottom))]">
        {/* Mounted here rather than in each hub or in PageHeader (A12):
            AppShell wraps <Routes> and stays mounted across every navigation,
            so this is one mount and one fetch, and it covers /league/rival/:id
            which has no hub wrapper at all. */}
        <main id="main" className="p-4">
          {/* v19c §2.2: the theme control leaves the tab bar, which the six
              hubs now fill on their own, for the one corner of a phone page
              that is chrome rather than content. `items-start` keeps the
              strip's first line where it was. */}
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1"><FreshnessStrip /></div>
            <ThemeToggle compact />
          </div>
          {children}
        </main>
        <nav
          data-testid="nav"
          data-mode="tabbar"
          className="fixed inset-x-0 bottom-0 flex justify-around border-t
                     border-border bg-base py-1
                     pb-[calc(0.25rem+env(safe-area-inset-bottom))]"
        >
          {links('tabbar')}
        </nav>
        {/* One outlet per layout: it is `position: fixed`, so where it sits
            in the tree does not matter visually — but it must exist in both
            branches or a phone silently loses every acknowledgement. */}
        <ToastOutlet />
      </div>
    )
  }

  if (compact) {
    // v19c §2.3: between 768 and 1023 the labels cost more than they are
    // worth — 60 px the table beside them needed to stop double-scrolling.
    return (
      <div className="grid min-h-screen grid-cols-[56px_1fr] bg-base">
        <nav
          data-testid="nav"
          data-mode="rail"
          className="flex flex-col gap-0.5 border-r border-border py-4"
        >
          <p aria-label="gaffer"
             className="mb-3 text-center text-[15px] font-semibold text-text">
            g
          </p>
          {links('rail')}
          <div className="mt-auto flex justify-center pt-3">
            <ThemeToggle compact />
          </div>
        </nav>
        <main id="main" className="max-w-[1180px] p-6">
          <FreshnessStrip />{children}
        </main>
        <ToastOutlet />
      </div>
    )
  }

  return (
    <div className="grid min-h-screen grid-cols-[200px_1fr] bg-base">
      <nav
        data-testid="nav"
        data-mode="sidebar"
        className="flex flex-col gap-0.5 border-r border-border py-4 pr-3"
      >
        <p className="mb-3 pl-5 text-[15px] font-semibold text-text">gaffer</p>
        {links('sidebar')}
        {/* Footer, under the nav: chrome about the app rather than a place
            in it, so it sits below every destination and off the tab order
            of the six. */}
        <div className="mt-auto pl-3 pt-3">
          <ThemeToggle />
        </div>
      </nav>
      <main id="main" className={`${wide ? 'max-w-none' : 'max-w-[1180px]'} p-6`}>
        <FreshnessStrip />{children}
      </main>
      <ToastOutlet />
    </div>
  )
}
