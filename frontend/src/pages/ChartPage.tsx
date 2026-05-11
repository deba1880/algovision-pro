import { useState } from 'react'
import { useAppSelector, useAppDispatch } from '../store/hooks'
import { setTimeframe, toggleIndicator, toggleSMCZones, toggleSignals } from '../store/slices/chartSlice'
import TradingChart from '../components/Chart/TradingChart'
import SignalPanel from '../components/AI/SignalPanel'
import { clsx } from 'clsx'

const TIMEFRAMES = ['1m','3m','5m','10m','15m','30m','1h','2h','4h','1d','1w'] as const
const INDICATORS = ['EMA20','EMA50','EMA200','VWAP','RSI','MACD','BB','SUPERTREND']

export default function ChartPage() {
  const dispatch = useAppDispatch()
  const { activeSymbol, timeframe, indicators, showSMCZones, showSignals } = useAppSelector(s => s.chart)
  const { quotes } = useAppSelector(s => s.market)
  const quote = quotes[activeSymbol.symbol]
  const [showIndicatorMenu, setShowIndicatorMenu] = useState(false)

  return (
    <div className="flex h-full">
      {/* Chart area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Chart header */}
        <div className="flex items-center justify-between px-3 py-1.5 bg-[#161b22] border-b border-[#30363d]">
          {/* Symbol info */}
          <div className="flex items-center gap-4">
            <div>
              <span className="text-sm font-bold text-white">{activeSymbol.symbol}</span>
              <span className="text-xs text-[#8b949e] ml-2">{activeSymbol.exchange}</span>
            </div>
            {quote && (
              <div className="flex items-center gap-3 font-mono text-sm">
                <span className="text-white font-semibold">{quote.ltp.toFixed(2)}</span>
                <span className={clsx(quote.change_pct >= 0 ? 'text-green-400' : 'text-red-400')}>
                  {quote.change_pct >= 0 ? '+' : ''}{quote.change_pct.toFixed(2)}%
                </span>
                <span className="text-[#8b949e] text-xs">Vol: {(quote.volume/1000).toFixed(0)}K</span>
              </div>
            )}
          </div>

          {/* Timeframe selector */}
          <div className="flex items-center gap-1">
            {TIMEFRAMES.map(tf => (
              <button
                key={tf}
                onClick={() => dispatch(setTimeframe(tf as any))}
                className={clsx(
                  'px-2 py-0.5 rounded text-xs font-medium transition-colors',
                  timeframe === tf
                    ? 'bg-blue-500 text-white'
                    : 'text-[#8b949e] hover:text-white hover:bg-[#1c2128]'
                )}
              >
                {tf}
              </button>
            ))}
          </div>

          {/* Tools */}
          <div className="flex items-center gap-2">
            <div className="relative">
              <button
                onClick={() => setShowIndicatorMenu(v => !v)}
                className="px-2 py-0.5 rounded text-xs text-[#8b949e] hover:text-white hover:bg-[#1c2128] transition-colors"
              >
                Indicators
              </button>
              {showIndicatorMenu && (
                <div className="absolute right-0 top-7 z-50 bg-[#1c2128] border border-[#30363d] rounded shadow-xl w-40 p-2">
                  {INDICATORS.map(ind => (
                    <label key={ind} className="flex items-center gap-2 py-1 px-1 hover:bg-[#30363d] rounded cursor-pointer">
                      <input
                        type="checkbox"
                        checked={indicators.includes(ind)}
                        onChange={() => dispatch(toggleIndicator(ind))}
                        className="accent-blue-500"
                      />
                      <span className="text-xs text-[#8b949e]">{ind}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>

            <button
              onClick={() => dispatch(toggleSMCZones())}
              className={clsx('px-2 py-0.5 rounded text-xs font-medium transition-colors',
                showSMCZones ? 'bg-purple-500/20 text-purple-400' : 'text-[#8b949e] hover:text-white hover:bg-[#1c2128]'
              )}
            >
              SMC Zones
            </button>

            <button
              onClick={() => dispatch(toggleSignals())}
              className={clsx('px-2 py-0.5 rounded text-xs font-medium transition-colors',
                showSignals ? 'bg-green-500/20 text-green-400' : 'text-[#8b949e] hover:text-white hover:bg-[#1c2128]'
              )}
            >
              Signals
            </button>
          </div>
        </div>

        {/* Chart */}
        <div className="flex-1 p-1">
          <TradingChart height={undefined as any} />
        </div>
      </div>

      {/* Right panel — AI signals */}
      {showSignals && (
        <div className="w-72 border-l border-[#30363d] overflow-y-auto">
          <SignalPanel />
        </div>
      )}
    </div>
  )
}
