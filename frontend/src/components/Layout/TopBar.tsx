import { Link, useLocation } from 'react-router-dom'
import { Activity, BarChart2, Zap, ShoppingCart, FlaskConical, Calendar, Settings, Wifi, WifiOff, LayoutDashboard } from 'lucide-react'
import { useAppSelector } from '../../store/hooks'
import { clsx } from 'clsx'

const NAV = [
  { to: '/',          label: 'Dashboard',    icon: LayoutDashboard, exact: true },
  { to: '/chart',     label: 'Chart',        icon: BarChart2    },
  { to: '/signals',   label: 'AI Signals',   icon: Zap          },
  { to: '/options',   label: 'Options Chain',icon: Activity     },
  { to: '/trading',   label: 'Trading',      icon: ShoppingCart },
  { to: '/backtest',  label: 'Backtest',     icon: FlaskConical },
  { to: '/events',    label: 'Events',       icon: Calendar     },
  { to: '/settings',  label: 'Settings',     icon: Settings     },
]

export default function TopBar() {
  const location = useLocation()
  const { connected, marketStatus } = useAppSelector(s => s.market)
  const { isPaperMode } = useAppSelector(s => s.trading)

  return (
    <header className="flex items-center justify-between px-3 py-1.5 bg-[#161b22] border-b border-[#30363d] shrink-0">
      {/* Logo */}
      <div className="flex items-center gap-2 mr-6">
        <div className="w-6 h-6 rounded bg-blue-500 flex items-center justify-center">
          <span className="text-white font-bold text-xs">AV</span>
        </div>
        <span className="font-semibold text-sm text-white">AlgoVision Pro</span>
      </div>

      {/* Navigation */}
      <nav className="flex items-center gap-1">
        {NAV.map(({ to, label, icon: Icon, exact }) => {
          const active = exact ? location.pathname === to : location.pathname.startsWith(to)
          return (
            <Link
              key={to}
              to={to}
              className={clsx(
                'flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors',
                active
                  ? 'bg-blue-500/20 text-blue-400'
                  : 'text-[#8b949e] hover:text-white hover:bg-[#1c2128]'
              )}
            >
              <Icon size={13} />
              {label}
            </Link>
          )
        })}
      </nav>

      {/* Right status area */}
      <div className="flex items-center gap-3 ml-6">
        {/* Paper mode badge */}
        {isPaperMode && (
          <span className="text-xs px-2 py-0.5 rounded bg-yellow-500/20 text-yellow-400 font-medium">
            PAPER
          </span>
        )}

        {/* Market status */}
        <span className={clsx(
          'text-xs px-2 py-0.5 rounded font-medium',
          marketStatus === 'OPEN'
            ? 'bg-green-500/20 text-green-400'
            : 'bg-gray-500/20 text-gray-400'
        )}>
          {marketStatus}
        </span>

        {/* Live connection indicator */}
        <div className="flex items-center gap-1">
          {connected
            ? <Wifi size={13} className="text-green-400" />
            : <WifiOff size={13} className="text-red-400" />
          }
          <span className={clsx('text-xs', connected ? 'text-green-400' : 'text-red-400')}>
            {connected ? 'LIVE' : 'OFFLINE'}
          </span>
        </div>
      </div>
    </header>
  )
}
