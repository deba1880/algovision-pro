import { useEffect } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { useAppDispatch } from './store/hooks'
import { initWebSocket } from './services/websocket'
import Layout from './components/Layout/Layout'
import DashboardPage from './pages/DashboardPage'
import ChartPage from './pages/ChartPage'
import OptionsChainPage from './pages/OptionsChainPage'
import SignalsPage from './pages/SignalsPage'
import TradingPage from './pages/TradingPage'
import BacktestPage from './pages/BacktestPage'
import EventsPage from './pages/EventsPage'
import SettingsPage from './pages/SettingsPage'
import RobotPage from './pages/RobotPage'

export default function App() {
  const dispatch = useAppDispatch()

  useEffect(() => {
    // Connect to market-wide WebSocket on app start
    initWebSocket(dispatch)
  }, [dispatch])

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="chart" element={<ChartPage />} />
          <Route path="options" element={<OptionsChainPage />} />
          <Route path="signals" element={<SignalsPage />} />
          <Route path="trading" element={<TradingPage />} />
          <Route path="backtest" element={<BacktestPage />} />
          <Route path="events" element={<EventsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="robot" element={<RobotPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
