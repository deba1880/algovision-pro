import { useAppSelector } from '../../store/hooks'
import { clsx } from 'clsx'

export default function MarketTicker() {
  const { indices } = useAppSelector(s => s.market)

  if (!indices.length) return null

  const items = [...indices, ...indices] // duplicate for seamless scroll
  const duration = Math.max(indices.length * 4, 20)

  return (
    <div className="bg-[#0d1117] border-b border-[#30363d] overflow-hidden h-7 flex items-center">
      <div className="animate-ticker flex gap-8 whitespace-nowrap px-4" style={{ animationDuration: `${duration}s` }}>
        {items.map((idx, i) => {
          const positive = idx.change_pct >= 0
          return (
            <span key={i} className="inline-flex items-center gap-2 text-[11px] font-mono">
              <span className="text-[#8b949e]">{idx.name}</span>
              <span className="text-white font-semibold">{idx.ltp?.toFixed(2)}</span>
              <span className={clsx('font-medium', positive ? 'text-green-400' : 'text-red-400')}>
                {positive ? '+' : ''}{idx.change_pct?.toFixed(2)}%
              </span>
            </span>
          )
        })}
      </div>
    </div>
  )
}
