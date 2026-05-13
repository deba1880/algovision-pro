import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Activity, BarChart2, Zap, ShoppingCart, FlaskConical, Calendar, Settings, Wifi, WifiOff, LayoutDashboard, Menu, X, Bot } from 'lucide-react'
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
  { to: '/robot',     label: 'Robot',        icon: Bot          },
  { to: '/settings',  label: 'Settings',     icon: Settings     },
]

export default function TopBar() {
  const location = useLocation()
  const { connected, marketStatus } = useAppSelector(s => s.market)
  const { isPaperMode } = useAppSelector(s => s.trading)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  return (
    <>
      <header className="flex items-center justify-between px-3 py-1.5 bg-[#161b22] border-b border-[#30363d] shrink-0">
        {/* Logo */}
        <div className="flex items-center gap-2 mr-4">
          <div className="w-6 h-6 rounded bg-blue-500 flex items-center justify-center shrink-0">
            <span className="text-white font-bold text-xs">AV</span>
          </div>
          <span className="font-semibold text-sm text-white hidden sm:inline">AlgoVision Pro</span>
        </div>

        {/* Desktop Navigation */}
        <nav className="hidden md:flex items-center gap-1 flex-1">
          {NAV.map(({ to, label, icon: Icon, exact }) => {
            const active = exact ? location.pathname === to : location.pathname.startsWith(to)
            return (
              <Link
                key={to}
                to={to}
                className={clsx(
                  'flex items-center gap-1.5 px-2 lg:px-3 py-1.5 rounded text-xs font-medium transition-colors',
                  active
                    ? 'bg-blue-500/20 text-blue-400'
                    : 'text-[#8b949e] hover:text-white hover:bg-[#1c2128]'
                )}
              >
                <Icon size={13} />
                <span className="hidden lg:inline">{label}</span>
              </Link>
            )
          })}
        </nav>

        {/* Right status area */}
        <div className="flex items-center gap-2 ml-auto md:ml-4">
          {isPaperMode && (
            <span className="text-xs px-2 py-0.5 rounded bg-yellow-500/20 text-yellow-400 font-medium hidden sm:inline">
              PAPER
            </span>
          )}
          <span className={clsx(
            'text-xs px-2 py-0.5 rounded font-medium hidden sm:inline',
            marketStatus === 'OPEN'
              ? 'bg-green-500/20 text-green-400'
              : 'bg-gray-500/20 text-gray-400'
          )}>
            {marketStatus}
          </span>
          <div className="flex items-center gap-1">
            {connected
              ? <Wifi size={13} className="text-green-400" />
              : <WifiOff size={13} className="text-red-400" />
            }
            <span className={clsx('text-xs hidden sm:inline', connected ? 'text-green-400' : 'text-red-400')}>
              {connected ? 'LIVE' : 'OFF'}
            </span>
          </div>
          {/* Mobile menu toggle */}
          <button
            className="md:hidden p-1.5 rounded text-[#8b949e] hover:text-white hover:bg-[#1c2128]"
            onClick={() => setMobileMenuOpen(v => !v)}
          >
            {mobileMenuOpen ? <X size={16} /> : <Menu size={16} />}
          </button>
        </div>
      </header>

      {/* Mobile slide-down nav */}
      {mobileMenuOpen && (
        <nav className="md:hidden bg-[#161b22] border-b border-[#30363d] px-2 py-2 flex flex-col gap-0.5 z-50">
          {NAV.map(({ to, label, icon: Icon, exact }) => {
            const active = exact ? location.pathname === to : location.pathname.startsWith(to)
            return (
              <Link
                key={to}
                to={to}
                onClick={() => setMobileMenuOpen(false)}
                className={clsx(
                  'flex items-center gap-2.5 px-3 py-2 rounded text-sm font-medium transition-colors',
                  active
                    ? 'bg-blue-500/20 text-blue-400'
                    : 'text-[#8b949e] hover:text-white hover:bg-[#1c2128]'
                )}
              >
                <Icon size={15} />
                {label}
              </Link>
            )
          })}
        </nav>
      )}
    </>
  )
}
