import { NavLink } from 'react-router-dom'

const PAGES: Array<[string, string]> = [
  ['/', 'This Week'],
  ['/whatif', 'What-If Lab'],
  ['/league', 'League Race'],
  ['/live', 'Live'],
  ['/players', 'Players'],
  ['/history', 'History'],
  ['/quality', 'Model Quality'],
  ['/health', 'Runs & Health'],
  ['/ticker', 'Fixture Ticker'],
]

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <h1>gaffer</h1>
      <nav>
        {PAGES.map(([path, label]) => (
          <NavLink
            key={path}
            to={path}
            end={path === '/'}
            className={({ isActive }) => (isActive ? 'active' : undefined)}
          >
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
