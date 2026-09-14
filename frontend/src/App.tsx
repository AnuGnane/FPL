import { Suspense, lazy } from 'react'
import { Route, Routes, useLocation } from 'react-router-dom'
import { AppShell, ErrorBoundary, Loading } from './kit'

// v18f §2.2. One chunk per hub. Recharts is 400 kB and is imported by League,
// Live, four Model tabs and two Players panels — never by This Week, which is
// the page every session opens on. Bundled together, the reader waiting on
// Thursday's advice downloaded the whole charting library first; split, the
// first paint carries only the hub it is painting, and the gate checks the
// entry chunk for the string `recharts`.
const ThisWeek = lazy(() => import('./hubs/ThisWeek'))
const Planning = lazy(() => import('./hubs/Planning'))
const Players = lazy(() => import('./hubs/Players'))
const League = lazy(() => import('./hubs/League'))
const Live = lazy(() => import('./hubs/Live'))
const Model = lazy(() => import('./hubs/Model'))
const RivalDetail = lazy(() => import('./hubs/league/RivalDetail'))

export default function App() {
  // The boundary resets on the path, so a hub that threw is not still broken
  // after the user navigates away from it (v18e §2.4).
  const { pathname } = useLocation()
  return (
    <AppShell>
      <ErrorBoundary resetKey={pathname}>
        {/* Inside the boundary, so a chunk that fails to load is reported by
            the same card that reports a hub that threw. The fallback is the
            kit's one loading state, which is the frame the hub is about to
            fill rather than a bare word on the page background. */}
        <Suspense fallback={<Loading />}>
          <Routes>
            <Route path="/" element={<ThisWeek />} />
            <Route path="/planning" element={<Planning />} />
            <Route path="/players" element={<Players />} />
            <Route path="/league" element={<League />} />
            <Route path="/league/rival/:id" element={<RivalDetail />} />
            <Route path="/live" element={<Live />} />
            <Route path="/model" element={<Model />} />
          </Routes>
        </Suspense>
      </ErrorBoundary>
    </AppShell>
  )
}
