import { Routes, Route } from 'react-router-dom'
import Sidebar from './components/layout/Sidebar'
import TopBar from './components/layout/TopBar'
import DatasetsPage from './pages/DatasetsPage'
import TrainingPage from './pages/TrainingPage'
import ModelsPage from './pages/ModelsPage'
import ArenaPage from './pages/ArenaPage'
import LeaderboardPage from './pages/LeaderboardPage'
import { ToastProvider } from './components/Toast'

export default function App() {
  return (
    <ToastProvider>
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <TopBar />
          <main className="flex-1 overflow-auto">
            <Routes>
              <Route path="/" element={<DatasetsPage />} />
              <Route path="/training" element={<TrainingPage />} />
              <Route path="/models" element={<ModelsPage />} />
              <Route path="/arena" element={<ArenaPage />} />
              <Route path="/leaderboard" element={<LeaderboardPage />} />
            </Routes>
          </main>
        </div>
      </div>
    </ToastProvider>
  )
}
