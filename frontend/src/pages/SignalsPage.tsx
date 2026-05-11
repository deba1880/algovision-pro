import { useAppSelector } from '../store/hooks'
import { clsx } from 'clsx'
import { TrendingUp, TrendingDown, Minus, AlertTriangle } from 'lucide-react'

export default function SignalsPage() {
  const { history } = useAppSelector(s => s.signals)

  return (
    <div className="p-4">
      <h2 className="text-sm font-semibold text-white mb-4">Signal History</h2>
      {history.length === 0 && (
        <div className="text-[#8b949e] text-xs text-center py-12">
          No signals yet. Open the chart and let the AI analyze a symbol.
        </div>
      )}
      <div className="grid gap-3">
        {history.map((sig, i) => {
          const positive = sig.signal_type === 'BUY'
          const negative = sig.signal_type === 'SELL'
          const Icon = positive ? TrendingUp : negative ? TrendingDown : Minus
          return (
            <div key={i} className={clsx(
              'panel p-4 rounded-lg border',
              positive ? 'border-green-500/30' : negative ? 'border-red-500/30' : 'border-[#30363d]'
            )}>
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Icon size={16} className={positive ? 'text-green-400' : negative ? 'text-red-400' : 'text-gray-400'} />
                  <span className="font-semibold text-white">{sig.symbol}</span>
                  <span className="text-xs text-[#8b949e]">{sig.exchange} · {sig.timeframe}</span>
                  <span className={clsx('chip text-xs',
                    positive ? 'chip-buy' : negative ? 'chip-sell' : 'chip-hold'
                  )}>
                    {sig.signal_type}
                  </span>
                </div>
                <span className="text-xs text-[#8b949e]">{new Date(sig.generated_at).toLocaleTimeString()}</span>
              </div>

              <div className="grid grid-cols-4 gap-3 text-xs mb-3">
                <div><div className="text-[#8b949e]">Entry</div><div className="font-mono text-blue-400">{sig.entry_price.toFixed(2)}</div></div>
                <div><div className="text-[#8b949e]">Stop Loss</div><div className="font-mono text-red-400">{sig.stop_loss.toFixed(2)}</div></div>
                <div><div className="text-[#8b949e]">Target 1</div><div className="font-mono text-green-400">{sig.target_1.toFixed(2)}</div></div>
                <div><div className="text-[#8b949e]">R:R</div><div className="font-mono text-white">1:{sig.risk_reward.toFixed(2)}</div></div>
              </div>

              {sig.warnings.length > 0 && (
                <div className="flex items-start gap-1.5 bg-yellow-500/10 rounded p-2 mb-2">
                  <AlertTriangle size={11} className="text-yellow-400 mt-0.5 shrink-0" />
                  <div className="text-xs text-yellow-300">{sig.warnings[0]}</div>
                </div>
              )}

              <div className="text-xs text-[#8b949e]">
                Confidence: <span className="text-white">{(sig.strength * 100).toFixed(0)}%</span>
                {' · '}{sig.strategy}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
