import { Route, Routes } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import ChipWorkbench from './pages/ChipWorkbench'
import Health from './pages/Health'
import History from './pages/History'
import LeagueRace from './pages/LeagueRace'
import Live from './pages/Live'
import Players from './pages/Players'
import Quality from './pages/Quality'
import RivalDetail from './pages/RivalDetail'
import Rivals from './pages/Rivals'
import ThisWeek from './hubs/ThisWeek'
import Ticker from './pages/Ticker'
import WhatIf from './pages/WhatIf'
import './styles/tokens.css'

export default function App() {
  return (
    <div className="layout">
      <Sidebar />
      <main className="content">
        <Routes>
          <Route path="/" element={<ThisWeek />} />
          <Route path="/whatif" element={<WhatIf />} />
          <Route path="/chips" element={<ChipWorkbench />} />
          <Route path="/league" element={<LeagueRace />} />
          <Route path="/league/rivals" element={<Rivals />} />
          <Route path="/league/rivals/:entryId" element={<RivalDetail />} />
          <Route path="/live" element={<Live />} />
          <Route path="/players" element={<Players />} />
          <Route path="/history" element={<History />} />
          <Route path="/quality" element={<Quality />} />
          <Route path="/health" element={<Health />} />
          <Route path="/ticker" element={<Ticker />} />
        </Routes>
      </main>
    </div>
  )
}
