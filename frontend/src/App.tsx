import { Route, Routes, useLocation } from 'react-router-dom'
import Live from './hubs/Live'
import League from './hubs/League'
import Model from './hubs/Model'
import Planning from './hubs/Planning'
import Players from './hubs/Players'
import ThisWeek from './hubs/ThisWeek'
import RivalDetail from './hubs/league/RivalDetail'
import { AppShell, ErrorBoundary } from './kit'

export default function App() {
  // The boundary resets on the path, so a hub that threw is not still broken
  // after the user navigates away from it (v18e §2.4).
  const { pathname } = useLocation()
  return (
    <AppShell>
      <ErrorBoundary resetKey={pathname}>
        <Routes>
          <Route path="/" element={<ThisWeek />} />
          <Route path="/planning" element={<Planning />} />
          <Route path="/players" element={<Players />} />
          <Route path="/league" element={<League />} />
          <Route path="/league/rival/:id" element={<RivalDetail />} />
          <Route path="/live" element={<Live />} />
          <Route path="/model" element={<Model />} />
        </Routes>
      </ErrorBoundary>
    </AppShell>
  )
}
