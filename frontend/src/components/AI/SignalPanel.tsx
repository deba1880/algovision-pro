import { useEffect, useMemo } from 'react'
import { AlertTriangle, TrendingUp, TrendingDown, Minus, RefreshCw } from 'lucide-react'
import { useAppSelector, useAppDispatch } from '../../store/hooks'
import { setSignal, setLoading, setError } from '../../store/slices/signalSlice'
import { api } from '../../services/api'
import { clsx } from 'clsx'

function getSignalColor(type: string | undefined) {
  if (type === 'BUY') return 'text-green-400'
  if (type === 'SELL') return 'text-red-400'
  return 'text-gray-400'
}

function getSignalBg(type: string | undefined) {
  if (type === 'BUY') return 'bg-green-500/10 border-green-500/30'
  if (type === 'SELL') return 'bg-red-500/10 border-red-500/30'
  return 'bg-gray-500/10 border-gray-500/30'
}

function getSignalBar(type: string | undefined) {
  if (type === 'BUY') return 'bg-green-400'
  if (type === 'SELL') return 'bg-red-400'
  return 'bg-gray-400'
}

export default function SignalPanel() {
  const dispatch = useAppDispatch()
  const { current: signal, loading, error } = useAppSelector(s => s.signals)
  const { activeSymbol, timeframe } = useAppSelector(s => s.chart)

  const fetchSignal = async () => {
    dispatch(setLoading(true))
    dispatch(setError(null))
    try {
      const data = await api.getSignal(activeSymbol.symbol, activeSymbol.exchange, timeframe)
      dispatch(setSignal(data))
    } catch (e: any) {
      dispatch(setError(e.message || 'Signal generation failed'))
    } finally {
      dispatch(setLoading(false))
    }
  }

  useEffect(() => {
    fetchSignal()
    const interval = setInterval(fetchSignal, 120_000) // refresh every 2 min
    return () => clearInterval(interval)
  }, [activeSymbol.symbol, activeSymbol.exchange, timeframe])

  const SignalIcon = useMemo(() => {
    if (signal?.signal_type === 'BUY') return TrendingUp
    if (signal?.signal_type === 'SELL') return TrendingDown
    return Minus
  }, [signal?.signal_type])

  return (
    <div className="p-3 flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-[#8b949e] uppercase tracking-wider">AI Signal</span>
        <button
          onClick={fetchSignal}
          disabled={loading}
          className="text-[#8b949e] hover:text-white transition-colors"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {error && (
        <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded p-2">
          {error}
        </div>
      )}

      {signal && (
        <>
          {/* Main signal */}
          <div className={clsx('rounded-lg p-3 border', getSignalBg(signal.signal_type))}>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <SignalIcon size={18} className={getSignalColor(signal.signal_type)} />
                <span className={clsx('text-lg font-bold', getSignalColor(signal.signal_type))}>
                  {signal.signal_type}
                </span>
              </div>
              <div className="text-right">
                <div className="text-xs text-[#8b949e]">Confidence</div>
                <div className="text-sm font-semibold text-white">
                  {(signal.strength * 100).toFixed(0)}%
                </div>
              </div>
            </div>

            {/* Confidence bar */}
            <div className="h-1 bg-[#30363d] rounded-full overflow-hidden">
              <div
                className={clsx('h-full rounded-full transition-all', getSignalBar(signal.signal_type))}
                style={{ width: `${signal.strength * 100}%` }}
              />
            </div>
          </div>

          {/* Levels */}
          {signal.signal_type !== 'HOLD' && (
            <div className="panel p-3 space-y-1.5">
              <div className="text-xs font-semibold text-[#8b949e] uppercase tracking-wider mb-2">Levels</div>
              <LevelRow label="Entry"    value={signal.entry_price} color="text-blue-400" />
              <LevelRow label="Stop Loss" value={signal.stop_loss}  color="text-red-400" />
              <div className="border-t border-[#30363d] my-1.5" />
              <LevelRow label="Target 1"  value={signal.target_1}   color="text-green-400" />
              <LevelRow label="Target 2"  value={signal.target_2}   color="text-green-300" />
              <LevelRow label="Target 3"  value={signal.target_3}   color="text-green-200" />
              <div className="border-t border-[#30363d] my-1.5" />
              <div className="flex justify-between text-xs">
                <span className="text-[#8b949e]">Risk : Reward</span>
                <span className="text-white font-mono">1 : {signal.risk_reward.toFixed(2)}</span>
              </div>
            </div>
          )}

          {/* Stop hunt warnings */}
          {signal.warnings.length > 0 && (
            <div className="panel p-3 border-yellow-500/30 bg-yellow-500/5">
              <div className="flex items-center gap-1.5 mb-2">
                <AlertTriangle size={12} className="text-yellow-400" />
                <span className="text-xs font-semibold text-yellow-400">ALERTS</span>
              </div>
              {signal.warnings.map((w, i) => (
                <p key={i} className="text-xs text-yellow-300/80 leading-relaxed">{w}</p>
              ))}
            </div>
          )}

          {/* Reasons */}
          {signal.reasons.length > 0 && (
            <div className="panel p-3">
              <div className="text-xs font-semibold text-[#8b949e] uppercase tracking-wider mb-2">Analysis</div>
              <ul className="space-y-1">
                {signal.reasons.map((r, i) => (
                  <li key={i} className="text-xs text-[#8b949e] flex gap-1.5">
                    <span className="text-blue-400 shrink-0">•</span>
                    <span>{r}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="text-[10px] text-[#8b949e] text-center">
            Strategy: {signal.strategy} • {signal.timeframe}
          </div>
        </>
      )}

      {loading && !signal && (
        <div className="text-xs text-[#8b949e] text-center py-8">Analyzing {activeSymbol.symbol}...</div>
      )}
    </div>
  )
}

function LevelRow({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="flex justify-between text-xs">
      <span className="text-[#8b949e]">{label}</span>
      <span className={clsx('font-mono font-semibold', color)}>{value.toFixed(2)}</span>
    </div>
  )
}
