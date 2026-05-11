import { Outlet } from 'react-router-dom'
import TopBar from './TopBar'
import Sidebar from './Sidebar'
import MarketTicker from './MarketTicker'

export default function Layout() {
  return (
    <div className="flex flex-col h-screen bg-[#0d1117] overflow-hidden">
      {/* Scrolling market ticker at very top */}
      <MarketTicker />

      {/* Top navigation bar */}
      <TopBar />

      <div className="flex flex-1 overflow-hidden">
        {/* Left sidebar — watchlist */}
        <Sidebar />

        {/* Main content area */}
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
