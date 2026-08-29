import { Route, Routes } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Health from './pages/Health'
import History from './pages/History'
import Live from './hubs/Live'
import League from './hubs/League'
import RivalDetail from './hubs/league/RivalDetail'
import Players from './hubs/Players'
import Quality from './pages/Quality'
import Planning from './hubs/Planning'
import ThisWeek from './hubs/ThisWeek'
import './styles/tokens.css'

export default function App() {
  return (
    <div className="layout">
      <Sidebar />
      <main className="content">
        <Routes>
          <Route path="/" element={<ThisWeek />} />
          <Route path="/planning" element={<Planning />} />
          <Route path="/league" element={<League />} />
          <Route path="/league/rival/:id" element={<RivalDetail />} />
          <Route path="/live" element={<Live />} />
          <Route path="/players" element={<Players />} />
          <Route path="/history" element={<History />} />
          <Route path="/quality" element={<Quality />} />
          <Route path="/health" element={<Health />} />
        </Routes>
      </main>
    </div>
  )
}
