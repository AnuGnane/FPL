import {
  Activity, CalendarCheck, type LucideIcon, Radio, Route, Trophy, Users,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import FreshnessStrip from './FreshnessStrip'
import ThemeToggle from './ThemeToggle'
import ToastOutlet from './Toast'
import { useIsMobile } from './useMediaQuery'

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

export default function AppShell({ children }: { children: ReactNode }) {
  const mobile = useIsMobile()

  // Active: accent text and a 2px accent bar on the left edge (sidebar) —
  // rule 3, "blue means it is active". No fill, no card.
  const links = HUBS.map(([path, label, Icon]) => (
    <NavLink
      key={path}
      to={path}
      end={path === '/'}
      className={({ isActive }) => (mobile
        ? `flex flex-col items-center gap-0.5 px-3 py-1.5 text-[11px] ${isActive
            ? 'text-accent-text' : 'text-text-muted hover:text-text'}`
        : `flex items-center gap-2.5 border-l-2 py-1.5 pl-2.5 pr-3 text-[13px]
           ${isActive
             ? 'border-accent text-accent-text'
             : 'border-transparent text-text-muted hover:text-text'}`)}
    >
      <Icon aria-hidden size={16} className="shrink-0" />
      {label}
    </NavLink>
  ))

  if (mobile) {
    return (
      <div className="min-h-screen bg-base pb-16">
        {/* Mounted here rather than in each hub or in PageHeader (A12):
            AppShell wraps <Routes> and stays mounted across every navigation,
            so this is one mount and one fetch, and it covers /league/rival/:id
            which has no hub wrapper at all. */}
        <main className="p-4"><FreshnessStrip />{children}</main>
        <nav
          data-testid="nav"
          data-mode="tabbar"
          className="fixed inset-x-0 bottom-0 flex justify-around border-t
                     border-border bg-base py-1"
        >
          {links}
          {/* The seventh slot. Six hubs already fill this row, so the theme
              control gets an icon and carries its state in the label. */}
          <ThemeToggle compact />
        </nav>
        {/* One outlet per layout: it is `position: fixed`, so where it sits
            in the tree does not matter visually — but it must exist in both
            branches or a phone silently loses every acknowledgement. */}
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
        {links}
        {/* Footer, under the nav: chrome about the app rather than a place
            in it, so it sits below every destination and off the tab order
            of the six. */}
        <div className="mt-auto pl-3 pt-3">
          <ThemeToggle />
        </div>
      </nav>
      <main className="max-w-[1180px] p-6"><FreshnessStrip />{children}</main>
      <ToastOutlet />
    </div>
  )
}
