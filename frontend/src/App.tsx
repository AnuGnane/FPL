import { Route, Routes } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Live from './hubs/Live'
import Model from './hubs/Model'
import League from './hubs/League'
import RivalDetail from './hubs/league/RivalDetail'
import Players from './hubs/Players'
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
          <Route path="/model" element={<Model />} />
        </Routes>
      </main>
    </div>
  )
}
