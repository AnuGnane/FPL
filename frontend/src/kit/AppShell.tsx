import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import ThemeToggle from './ThemeToggle'
import ToastOutlet from './Toast'
import { useIsMobile } from './useMediaQuery'

/** The six hubs, in the order the spec lists them (§4). */
const HUBS: Array<[string, string, string]> = [
  ['/', 'This Week', '◎'],
  ['/planning', 'Planning', '▤'],
  ['/players', 'Players', '☰'],
  ['/league', 'League', '⚑'],
  ['/live', 'Live', '◉'],
  ['/model', 'Model', '◍'],
]

export default function AppShell({ children }: { children: ReactNode }) {
  const mobile = useIsMobile()

  const links = HUBS.map(([path, label, icon]) => (
    <NavLink
      key={path}
      to={path}
      end={path === '/'}
      className={({ isActive }) => (
        `flex items-center gap-2 rounded-card px-3 py-2 ${isActive
          ? 'bg-card text-text' : 'text-text-muted hover:text-text'}
         ${mobile ? 'flex-col gap-0.5 text-[11px]' : ''}`
      )}
    >
      <span aria-hidden>{icon}</span>
      {label}
    </NavLink>
  ))

  if (mobile) {
    return (
      <div className="min-h-screen bg-base pb-16">
        <main className="p-4">{children}</main>
        <nav
          data-testid="nav"
          data-mode="tabbar"
          className="fixed inset-x-0 bottom-0 flex justify-around border-t
                     border-border bg-card py-1"
        >
          {links}
          {/* The seventh slot. Six hubs already fill this row, so the theme
              control gets an icon and carries its state in the label. */}
          <ThemeToggle compact />
        </nav>
        {/* One outlet per layout. It is `position: fixed`, so where it sits
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
        className="flex flex-col gap-1 border-r border-border p-3"
      >
        <p className="mb-3 px-3 text-lg font-semibold text-text">gaffer</p>
        {links}
        {/* Footer, under the nav: chrome about the app rather than a place
            in it, so it sits below every destination and off the tab order
            of the six. */}
        <div className="mt-auto pt-3">
          <ThemeToggle />
        </div>
      </nav>
      <main className="max-w-[1180px] p-6">{children}</main>
      <ToastOutlet />
    </div>
  )
}
