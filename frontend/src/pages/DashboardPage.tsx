import { useEffect, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import {
  TrendingUp, TrendingDown, Minus, Activity, BarChart2, Zap,
  ShoppingCart, FlaskConical, Calendar, ArrowUpRight, ArrowDownRight,
  Users, DollarSign, AlertCircle, Wifi, WifiOff, RefreshCw,
} from 'lucide-react'
import { useAppSelector, useAppDispatch } from '../store/hooks'
import { setIndices, setBreadth, setFiiDii, setMarketStatus } from '../store/slices/marketSlice'
import { setPositions, setOrders } from '../store/slices/tradingSlice'
import { api } from '../services/api'
import { clsx } from 'clsx'

// ─── Types ─────────────────────────────────────────────────────────────────────

interface Event {
  id: number
  title: string
  date: string
  time: string | null
  impact: 'HIGH' | 'MEDIUM' | 'LOW'
  category: string
  symbol?: string
}

// ─── Sub-components ─────────────────────────────────────────────────────────────

function IndexCard({ name, ltp, change, change_pct }: {
  name: string; ltp: number; change: number; change_pct: number
}) {
  const up = change_pct >= 0
  return (
    <div className={clsx(
      'panel p-3 relative overflow-hidden',
      up
        ? 'border-green-500/20 bg-gradient-to-br from-green-500/5 to-transparent'
        : 'border-red-500/20 bg-gradient-to-br from-red-500/5 to-transparent'
    )}>
      <div className="flex items-start justify-between mb-2">
        <span className="text-[10px] font-semibold text-[#8b949e] uppercase tracking-wider">{name}</span>
        {up
          ? <ArrowUpRight size={14} className="text-green-400" />
          : <ArrowDownRight size={14} className="text-red-400" />}
      </div>
      <div className="font-mono text-xl font-bold text-white leading-none mb-1">
        {ltp.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
      </div>
      <div className="flex items-center gap-2">
        <span className={clsx('text-xs font-semibold font-mono', up ? 'text-green-400' : 'text-red-400')}>
          {up ? '+' : ''}{change.toFixed(2)}
        </span>
        <span className={clsx(
          'text-[10px] px-1.5 py-0.5 rounded font-semibold',
          up ? 'bg-green-500/15 text-green-400' : 'bg-red-500/15 text-red-400'
        )}>
          {up ? '+' : ''}{change_pct.toFixed(2)}%
        </span>
      </div>
    </div>
  )
}

function SignalRow({ sig }: { sig: any }) {
  const isBuy = sig.signal_type === 'BUY'
  const isSell = sig.signal_type === 'SELL'
  const Icon = isBuy ? TrendingUp : isSell ? TrendingDown : Minus
  return (
    <div className={clsx(
      'flex items-center gap-3 px-3 py-2.5 rounded border transition-colors hover:bg-[#21262d]',
      isBuy ? 'border-green-500/20' : isSell ? 'border-red-500/20' : 'border-[#30363d]'
    )}>
      <Icon size={14} className={isBuy ? 'text-green-400' : isSell ? 'text-red-400' : 'text-gray-500'} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-white">{sig.symbol}</span>
          <span className={clsx('chip text-[10px]', isBuy ? 'chip-buy' : isSell ? 'chip-sell' : 'chip-hold')}>
            {sig.signal_type}
          </span>
          <span className="text-[10px] text-[#8b949e]">{sig.timeframe}</span>
        </div>
        <div className="text-[10px] text-[#8b949e] truncate mt-0.5">
          Entry <span className="text-blue-400 font-mono">{sig.entry_price?.toFixed(2)}</span>
          {' · '}SL <span className="text-red-400 font-mono">{sig.stop_loss?.toFixed(2)}</span>
          {' · '}T1 <span className="text-green-400 font-mono">{sig.target_1?.toFixed(2)}</span>
        </div>
      </div>
      <div className="shrink-0 text-right">
        <div className="text-[10px] text-[#8b949e]">Strength</div>
        <div className={clsx('text-xs font-bold font-mono',
          (sig.strength ?? 0) >= 0.7 ? 'text-green-400' : (sig.strength ?? 0) >= 0.4 ? 'text-yellow-400' : 'text-[#8b949e]'
        )}>
          {((sig.strength ?? 0) * 100).toFixed(0)}%
        </div>
      </div>
    </div>
  )
}

function BreadthBar({ label, value, total, color }: {
  label: string; value: number; total: number; color: string
}) {
  const pct = total > 0 ? (value / total) * 100 : 0
  return (
    <div>
      <div className="flex justify-between text-[10px] mb-1">
        <span className="text-[#8b949e]">{label}</span>
        <span className="font-mono text-white">{value}</span>
      </div>
      <div className="h-1.5 bg-[#21262d] rounded-full overflow-hidden">
        <div className={clsx('h-full rounded-full transition-all', color)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function StatBox({ label, value, sub, accent }: {
  label: string; value: string; sub?: string; accent?: 'green' | 'red' | 'blue' | 'yellow'
}) {
  const color = accent === 'green' ? 'text-green-400'
    : accent === 'red' ? 'text-red-400'
    : accent === 'blue' ? 'text-blue-400'
    : accent === 'yellow' ? 'text-yellow-400'
    : 'text-white'
  return (
    <div className="panel p-3">
      <div className="text-[10px] text-[#8b949e] mb-1">{label}</div>
      <div className={clsx('text-base font-bold font-mono leading-none', color)}>{value}</div>
      {sub && <div className="text-[10px] text-[#8b949e] mt-0.5">{sub}</div>}
    </div>
  )
}

function QuickLink({ to, icon: Icon, label, color }: {
  to: string; icon: any; label: string; color: string
}) {
  return (
    <Link to={to} className={clsx(
      'flex items-center gap-2.5 px-4 py-3 rounded-lg border transition-all hover:scale-[1.02] active:scale-[0.98]',
      color
    )}>
      <Icon size={15} />
      <span className="text-xs font-semibold">{label}</span>
      <ArrowUpRight size={11} className="ml-auto opacity-60" />
    </Link>
  )
}

const IMPACT_COLOR: Record<string, string> = {
  HIGH:   'text-red-400 bg-red-500/10',
  MEDIUM: 'text-yellow-400 bg-yellow-500/10',
  LOW:    'text-gray-400 bg-gray-500/10',
}

// ─── Dashboard ─────────────────────────────────────────────────────────────────

function getISTMarketStatus(): 'PRE_OPEN' | 'OPEN' | 'POST_CLOSE' | 'CLOSED' {
  const ist = new Date().toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false })
  const [h, m] = ist.split(':').map(Number)
  const mins = h * 60 + m
  if (mins >= 555 && mins < 555 + 15) return 'PRE_OPEN'   // 09:15
  if (mins >= 555 + 15 && mins <= 930) return 'OPEN'       // 09:15 – 15:30
  if (mins > 930 && mins <= 960) return 'POST_CLOSE'       // 15:30 – 16:00
  return 'CLOSED'
}

export default function DashboardPage() {
  const dispatch = useAppDispatch()
  const { indices, breadth, fiiDii, connected, marketStatus } = useAppSelector(s => s.market)
  const { history: signals } = useAppSelector(s => s.signals)
  const { positions, dailyPnl, isPaperMode } = useAppSelector(s => s.trading)
  const [events, setEvents] = useState<Event[]>([])
  const [eventsLoading, setEventsLoading] = useState(true)
  const [lastRefresh, setLastRefresh] = useState(new Date())
  const [loading, setLoading] = useState(true)

  const fetchAll = useCallback(async () => {
    dispatch(setMarketStatus(getISTMarketStatus()))

    const [indRes, brdRes, fiiRes, posRes, ordRes, evtRes] = await Promise.allSettled([
      api.getIndices(),
      api.getBreadth(),
      api.getFiiDii(),
      api.getPositions(),
      api.getOrders(),
      api.getEvents(14),
    ])

    if (indRes.status === 'fulfilled' && Array.isArray(indRes.value?.data)) {
      dispatch(setIndices(indRes.value.data))
    }
    if (brdRes.status === 'fulfilled' && brdRes.value?.advances != null) {
      dispatch(setBreadth(brdRes.value))
    }
    if (fiiRes.status === 'fulfilled' && fiiRes.value?.fii_net != null) {
      dispatch(setFiiDii(fiiRes.value))
    }
    if (posRes.status === 'fulfilled') {
      dispatch(setPositions(posRes.value?.positions ?? []))
    }
    if (ordRes.status === 'fulfilled') {
      dispatch(setOrders(ordRes.value?.orders ?? []))
    }
    if (evtRes.status === 'fulfilled') {
      setEvents((evtRes.value?.events ?? []).slice(0, 5))
    }
    setEventsLoading(false)
    setLoading(false)
    setLastRefresh(new Date())
  }, [dispatch])

  useEffect(() => {
    fetchAll()
    const id = setInterval(fetchAll, 60_000)
    return () => clearInterval(id)
  }, [fetchAll])

  const refresh = () => {
    setLoading(true)
    setEventsLoading(true)
    fetchAll()
  }

  const latestSignals = signals.slice(0, 6)
  const openPositions = positions.length

  return (
    <div className="p-4 space-y-4 h-full overflow-auto">

      {/* ── Page Header ──────────────────────────────────────────────── */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-base font-bold text-white">Market Dashboard</h1>
          <p className="text-[10px] text-[#8b949e] mt-0.5">
            {new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {isPaperMode && (
            <span className="text-[10px] px-2 py-0.5 rounded bg-yellow-500/20 text-yellow-400 font-semibold border border-yellow-500/30">
              PAPER MODE
            </span>
          )}
          <span className={clsx(
            'text-[10px] px-2 py-0.5 rounded font-semibold border',
            marketStatus === 'OPEN'
              ? 'bg-green-500/15 text-green-400 border-green-500/30'
              : 'bg-gray-500/10 text-gray-400 border-gray-500/20'
          )}>
            {marketStatus}
          </span>
          <div className="flex items-center gap-1.5">
            {connected
              ? <Wifi size={12} className="text-green-400" />
              : <WifiOff size={12} className="text-red-400" />}
            <span className={clsx('text-[10px] font-semibold', connected ? 'text-green-400' : 'text-red-400')}>
              {connected ? 'LIVE' : 'OFFLINE'}
            </span>
          </div>
          <button
            onClick={refresh}
            className="p-1.5 rounded hover:bg-[#1c2128] text-[#8b949e] hover:text-white transition-colors"
            title="Refresh"
          >
            <RefreshCw size={12} />
          </button>
        </div>
      </div>

      {/* ── Index Cards ─────────────────────────────────────────────── */}
      {indices.length > 0 ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {indices.slice(0, 4).map(idx => (
            <IndexCard key={idx.name} {...idx} />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {['NIFTY 50', 'BANK NIFTY', 'FIN NIFTY', 'SENSEX'].map(n => (
            <div key={n} className={clsx('panel p-3', loading && 'animate-pulse')}>
              <div className="text-[10px] text-[#8b949e] mb-2">{n}</div>
              {loading
                ? <><div className="h-6 bg-[#21262d] rounded w-24 mb-1" /><div className="h-4 bg-[#21262d] rounded w-16" /></>
                : <div className="text-xs text-[#8b949e]">No data — backend may be offline</div>
              }
            </div>
          ))}
        </div>
      )}

      {/* ── Main Grid ──────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-3">

        {/* AI Signals — 5 cols */}
        <div className="col-span-1 md:col-span-5 panel p-3">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Zap size={13} className="text-yellow-400" />
              <span className="text-xs font-semibold text-white">AI Signals</span>
              {latestSignals.length > 0 && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/15 text-blue-400 font-semibold">
                  {latestSignals.length}
                </span>
              )}
            </div>
            <Link to="/signals" className="text-[10px] text-blue-400 hover:text-blue-300 flex items-center gap-0.5">
              View All <ArrowUpRight size={10} />
            </Link>
          </div>
          {latestSignals.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <Zap size={24} className="text-[#30363d] mb-2" />
              <p className="text-[10px] text-[#8b949e]">No signals yet</p>
              <p className="text-[10px] text-[#8b949e]">Signals auto-generate every 15 min during market hours</p>
            </div>
          ) : (
            <div className="space-y-1.5">
              {latestSignals.map((sig, i) => <SignalRow key={i} sig={sig} />)}
            </div>
          )}
        </div>

        {/* Middle — breadth + FII/DII + portfolio — 4 cols */}
        <div className="col-span-1 md:col-span-4 space-y-3">

          {/* Market Breadth */}
          <div className="panel p-3">
            <div className="flex items-center gap-2 mb-3">
              <Activity size={13} className="text-blue-400" />
              <span className="text-xs font-semibold text-white">Market Breadth</span>
            </div>
            {breadth ? (
              <div className="space-y-2.5">
                <BreadthBar label="Advances" value={breadth.advances} total={breadth.total} color="bg-green-500" />
                <BreadthBar label="Declines" value={breadth.declines} total={breadth.total} color="bg-red-500" />
                <BreadthBar label="Unchanged" value={breadth.unchanged} total={breadth.total} color="bg-gray-500" />
                <div className="flex justify-between items-center pt-1 border-t border-[#30363d]">
                  <span className="text-[10px] text-[#8b949e]">A/D Ratio</span>
                  <span className={clsx('text-xs font-bold font-mono',
                    breadth.ad_ratio >= 1 ? 'text-green-400' : 'text-red-400'
                  )}>
                    {breadth.ad_ratio.toFixed(2)}
                  </span>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                {[1,2,3].map(i => <div key={i} className="h-4 bg-[#21262d] rounded animate-pulse" />)}
              </div>
            )}
          </div>

          {/* FII / DII */}
          <div className="panel p-3">
            <div className="flex items-center gap-2 mb-3">
              <Users size={13} className="text-purple-400" />
              <span className="text-xs font-semibold text-white">FII / DII Flow</span>
            </div>
            {fiiDii ? (
              <div className="grid grid-cols-2 gap-2">
                <div className={clsx('p-2 rounded border text-center',
                  fiiDii.fii_net >= 0 ? 'bg-green-500/5 border-green-500/20' : 'bg-red-500/5 border-red-500/20'
                )}>
                  <div className="text-[10px] text-[#8b949e] mb-1">FII Net</div>
                  <div className={clsx('text-sm font-bold font-mono',
                    fiiDii.fii_net >= 0 ? 'text-green-400' : 'text-red-400'
                  )}>
                    {fiiDii.fii_net >= 0 ? '+' : ''}
                    {(fiiDii.fii_net / 100).toFixed(0)}Cr
                  </div>
                </div>
                <div className={clsx('p-2 rounded border text-center',
                  fiiDii.dii_net >= 0 ? 'bg-green-500/5 border-green-500/20' : 'bg-red-500/5 border-red-500/20'
                )}>
                  <div className="text-[10px] text-[#8b949e] mb-1">DII Net</div>
                  <div className={clsx('text-sm font-bold font-mono',
                    fiiDii.dii_net >= 0 ? 'text-green-400' : 'text-red-400'
                  )}>
                    {fiiDii.dii_net >= 0 ? '+' : ''}
                    {(fiiDii.dii_net / 100).toFixed(0)}Cr
                  </div>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                {[1,2].map(i => <div key={i} className="h-14 bg-[#21262d] rounded animate-pulse" />)}
              </div>
            )}
          </div>

          {/* Portfolio Stats */}
          <div className="panel p-3">
            <div className="flex items-center gap-2 mb-3">
              <DollarSign size={13} className="text-green-400" />
              <span className="text-xs font-semibold text-white">Portfolio</span>
              <Link to="/trading" className="ml-auto text-[10px] text-blue-400 hover:text-blue-300 flex items-center gap-0.5">
                Manage <ArrowUpRight size={10} />
              </Link>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <StatBox
                label="Daily P&L"
                value={`${dailyPnl >= 0 ? '+' : ''}₹${Math.abs(dailyPnl).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`}
                accent={dailyPnl >= 0 ? 'green' : 'red'}
              />
              <StatBox
                label="Open Positions"
                value={String(openPositions)}
                sub={openPositions === 0 ? 'No open trades' : `${openPositions} active`}
                accent="blue"
              />
            </div>
          </div>
        </div>

        {/* Right — events + quick links — 3 cols */}
        <div className="col-span-1 md:col-span-3 space-y-3">

          {/* Upcoming Events */}
          <div className="panel p-3">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Calendar size={13} className="text-orange-400" />
                <span className="text-xs font-semibold text-white">Upcoming Events</span>
              </div>
              <Link to="/events" className="text-[10px] text-blue-400 hover:text-blue-300 flex items-center gap-0.5">
                All <ArrowUpRight size={10} />
              </Link>
            </div>
            {eventsLoading ? (
              <div className="space-y-2">
                {[1,2,3].map(i => <div key={i} className="h-10 bg-[#21262d] rounded animate-pulse" />)}
              </div>
            ) : events.length === 0 ? (
              <div className="flex items-center gap-2 py-4 text-[10px] text-[#8b949e]">
                <AlertCircle size={12} />
                <span>No upcoming events</span>
              </div>
            ) : (
              <div className="space-y-1.5">
                {events.map(ev => (
                  <div key={ev.id} className="border border-[#30363d] rounded p-2 hover:bg-[#21262d] transition-colors">
                    <div className="flex items-start gap-1.5 mb-0.5">
                      <span className={clsx('text-[9px] px-1 py-0.5 rounded font-semibold shrink-0 mt-0.5',
                        IMPACT_COLOR[ev.impact] ?? IMPACT_COLOR.LOW
                      )}>
                        {ev.impact}
                      </span>
                      <span className="text-[10px] text-white leading-tight">{ev.title}</span>
                    </div>
                    <div className="text-[9px] text-[#8b949e] pl-7">
                      {new Date(ev.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                      {ev.time ? ` · ${ev.time}` : ''}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Quick Navigation */}
          <div className="panel p-3">
            <div className="text-xs font-semibold text-white mb-2.5">Quick Navigate</div>
            <div className="space-y-1.5">
              <QuickLink to="/chart"    icon={BarChart2}    label="Chart & Analysis" color="border-blue-500/20 text-blue-400 hover:bg-blue-500/5" />
              <QuickLink to="/signals"  icon={Zap}          label="AI Signals"       color="border-yellow-500/20 text-yellow-400 hover:bg-yellow-500/5" />
              <QuickLink to="/options"  icon={Activity}     label="Options Chain"    color="border-purple-500/20 text-purple-400 hover:bg-purple-500/5" />
              <QuickLink to="/trading"  icon={ShoppingCart} label="Trading"          color="border-green-500/20 text-green-400 hover:bg-green-500/5" />
              <QuickLink to="/backtest" icon={FlaskConical} label="Backtest"         color="border-orange-500/20 text-orange-400 hover:bg-orange-500/5" />
            </div>
          </div>
        </div>
      </div>

      {/* ── Last updated ─────────────────────────────────────────────── */}
      <div className="text-[9px] text-[#8b949e] text-right pb-1">
        Last updated: {lastRefresh.toLocaleTimeString()}
        {connected && <span className="ml-2 inline-flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse inline-block" />
          Live
        </span>}
      </div>
    </div>
  )
}
